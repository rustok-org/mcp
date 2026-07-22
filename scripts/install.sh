#!/bin/sh
# rustok installer — one command to a verified wallet shim.
#
#   curl --proto '=https' --tlsv1.2 -fsSL \
#     https://raw.githubusercontent.com/rustok-org/mcp/vX.Y.Z/scripts/install.sh | sh
#
# What it does: pulls the wallet image BY DIGEST (content-addressed — you get
# exactly those bytes or nothing), installs the `rustok` shim into ~/.local/bin,
# and adds it to PATH. If cosign is available it ALSO verifies the image's
# signature against THIS repo's publishing workflow — an optional provenance
# layer, never a prerequisite: integrity comes from the digest, cosign proves
# who built it. A signature that fails to verify still refuses to install.
#
# What it deliberately does NOT do (epic invariant #1): it never touches a
# secret, a keystore volume or your wallet. Creating the wallet — the 12-word
# phrase and the approval PIN — is a separate step YOU run in your own terminal
# afterwards: `rustok init`. The installer runs over a pipe; the recovery phrase
# must never pass through one.
#
# POSIX sh on purpose: `curl | sh` ignores the shebang and runs under /bin/sh.
set -eu

: "${SHELL:=/bin/sh}"

# --- release-pinned constants (filled by the 4.2 release step) ----------------
# WALLET_DIGEST and SHIM_COMMIT are immutable identities, NOT mutable tags: the
# tag :vX.Y.Z can be repointed at a different image, and a git tag can be force-
# pushed to a different commit, but a @sha256: digest and a commit SHA are bound
# to their exact bytes. Both start as fail-closed placeholders — an unfilled
# release cannot pull or fetch anything (the all-zero refs 404 / have no
# signature), it fails loudly instead of installing something unverified.
WALLET_VERSION="0.8.1"
WALLET_DIGEST="sha256:5225bdb1e9ea27e329aead0b6ceec156172174545d3eaddeb18bde5313670d74"
SHIM_COMMIT="bdcb118ca0f6287e17f65186b96357e5aa7e7bed"

IMAGE_REPO="ghcr.io/rustok-org/rustok-wallet-tui"
RAW_BASE="https://raw.githubusercontent.com/rustok-org/mcp"
# The one identity cosign pins to: the workflow that builds AND signs the image.
# The ref MUST match the ref the publish ran on. wallet-publish.yml is
# workflow_dispatch, and its own self-verify pins `@${github.ref}` — so signer
# and verifier agree only if both use the SAME ref. Pinned to refs/heads/main:
# that is the default ref a workflow_dispatch runs on, so the RELEASE PROCESS
# (4.2) dispatches wallet-publish from main. If a future release instead tags
# the commit and dispatches FROM that tag, this must change to
# @refs/tags/v<version> — it is a FIELD change, not a value the release fills.
COSIGN_IDENTITY="https://github.com/rustok-org/mcp/.github/workflows/wallet-publish.yml@refs/heads/main"
COSIGN_ISSUER="https://token.actions.githubusercontent.com"

INSTALL_DIR="$HOME/.local/bin"
SHIM_PATH="$INSTALL_DIR/rustok"

say() { printf 'rustok-install: %s\n' "$*"; }
die() { printf 'rustok-install: %s\n' "$*" 1>&2; exit 1; }

detect_engine() {
    if command -v podman >/dev/null 2>&1; then
        echo podman
    elif command -v docker >/dev/null 2>&1; then
        echo docker
    else
        die "neither podman nor docker found — install podman (recommended): https://podman.io/getting-started/installation"
    fi
}

cosign_state() {
    # Answers "can cosign RUN here", not "is there a file called cosign in
    # PATH" — `command -v` answers the second question, and answers it
    # differently per shell: for a present-but-non-executable file /bin/sh in
    # POSIX mode reports FALSE while bash reports TRUE. A cosign that exists but
    # cannot execute (no +x, wrong architecture, missing libc, truncated
    # download) would then reach `cosign verify`, whose non-zero exit is
    # indistinguishable from a bad signature — and we would accuse a healthy
    # image of being tampered with when the only broken thing is the verifier.
    # `version` is the probe: offline, cheap, and it fails exactly when the
    # binary cannot run.
    command -v cosign >/dev/null 2>&1 || { echo absent; return 0; }
    cosign version >/dev/null 2>&1 || { echo broken; return 0; }
    echo works
}

skip_provenance() {
    # $1 — the honest reason, $2 — the image ref. Never phrased as a security
    # event: nothing here says anything about the image, only about the tool.
    say "$1 — skipping the signature check."
    say "this is not an error: the image is pinned by digest ($WALLET_DIGEST),"
    say "so you get exactly those bytes or nothing. cosign proves WHO built them (provenance),"
    say "which you can check any time later, once cosign works:"
    say "  cosign verify $2 --certificate-identity $COSIGN_IDENTITY --certificate-oidc-issuer $COSIGN_ISSUER"
}

profile_file() {
    # Match the shell so the PATH line is actually sourced; `uninstall` removes
    # the same marker block from any of these three, so writing to one is safe.
    case "${SHELL##*/}" in
        bash) echo "$HOME/.bashrc" ;;
        zsh) echo "$HOME/.zshrc" ;;
        *) echo "$HOME/.profile" ;;
    esac
}

add_to_path() {
    # The 2.3c uninstall contract: the PATH edit lives between these EXACT
    # markers and nothing else touches the profile. RUSTOK_NO_MODIFY_PATH opts
    # out entirely (prints the manual line). Idempotent: an existing block is
    # never duplicated.
    case ":$PATH:" in
        *":$INSTALL_DIR:"*) already_on_path=1 ;;
        *) already_on_path=0 ;;
    esac
    if [ -n "${RUSTOK_NO_MODIFY_PATH:-}" ]; then
        say "RUSTOK_NO_MODIFY_PATH set — not editing your shell profile."
        say "Add this line yourself: export PATH=\"$INSTALL_DIR:\$PATH\""
        return 0
    fi
    prof="$(profile_file)"
    if [ -f "$prof" ] && grep -q '^# >>> rustok installer >>>$' "$prof"; then
        say "PATH block already present in $prof — left as is."
        return 0
    fi
    {
        printf '# >>> rustok installer >>>\n'
        # $INSTALL_DIR expands now (via %s); $PATH MUST stay literal so it
        # expands at the user's shell startup, not at install time.
        # shellcheck disable=SC2016
        printf 'export PATH="%s:$PATH"\n' "$INSTALL_DIR"
        printf '# <<< rustok installer <<<\n'
    } >>"$prof"
    say "added $INSTALL_DIR to PATH in $prof — open a new shell or: . $prof"
    [ "$already_on_path" -eq 1 ] && say "(it was already on PATH for this session)"
    return 0
}

main() {
    engine="$(detect_engine)"
    command -v curl >/dev/null 2>&1 \
        || die "curl is required to fetch the shim — install it (dnf/apt install curl)"

    image="${IMAGE_REPO}@${WALLET_DIGEST}"

    # 1) Provenance FIRST when it is possible at all (cheapest gate, downloads
    #    no image bytes): a wrong-identity image is rejected before anything
    #    lands on disk. Ratified order (decision #2) is unchanged — what changed
    #    (Р-7а) is that a MISSING or UNRUNNABLE cosign no longer stops the
    #    install. Integrity does not depend on it: the pull below is by digest.
    #    Only a working cosign that says "no" refuses, and it refuses hard.
    case "$(cosign_state)" in
        works)
            say "verifying the wallet image signature ($WALLET_VERSION)…"
            cosign verify "$image" \
                --certificate-identity "$COSIGN_IDENTITY" \
                --certificate-oidc-issuer "$COSIGN_ISSUER" >/dev/null 2>&1 \
                || die "cosign could NOT verify $image against this repo's publishing workflow — refusing to install.
  Either the signature does not match (an unsigned or tampered image, or a release whose signed
  publish has not run yet), OR the check could not complete — keyless verification reaches the
  Sigstore transparency log over the network, so no connectivity, a rate limit or an outdated
  cosign fail here too. Nothing has been installed. Retry later, or see docs/TROUBLESHOOTING.md."
            say "signature verified — built by this repo's publishing workflow."
            ;;
        broken)
            skip_provenance "cosign is installed but will not run (no execute bit, wrong architecture, missing libc or a truncated download)" "$image"
            ;;
        *)
            skip_provenance "cosign is not installed (optional — it is a provenance tool, not a prerequisite)" "$image"
            ;;
    esac

    # 2) Pull by digest. NOT called "the verified image" — two of the three
    #    branches above skipped verification, and the pull is what the digest
    #    guarantees, not what cosign did.
    say "pulling the image by digest…"
    "$engine" pull "$image" >/dev/null \
        || die "'$engine' failed to pull the image — check the daemon/machine and your network"

    # 3) Fetch the shim from a COMMIT-pinned raw URL (immutable; a force-pushed
    #    tag cannot swap it) over a hardened TLS channel, then install atomically.
    mkdir -p "$INSTALL_DIR"
    shim_tmp="$SHIM_PATH.rustok-tmp"
    say "fetching the rustok shim…"
    curl --proto '=https' --tlsv1.2 -fsSL \
        "$RAW_BASE/$SHIM_COMMIT/cli/rustok" -o "$shim_tmp" \
        || { rm -f "$shim_tmp"; die "failed to fetch the shim over TLS — refusing to install a partial copy"; }
    chmod +x "$shim_tmp"
    mv "$shim_tmp" "$SHIM_PATH" \
        || { rm -f "$shim_tmp"; die "failed to install the shim into $INSTALL_DIR"; }
    say "installed the rustok shim -> $SHIM_PATH"

    # 4) PATH.
    add_to_path

    # 5) Next steps — the installer's job ends here; the wallet is the human's.
    say "done. Before running, you can inspect this script and the shim you just installed."
    say "next (in YOUR terminal, never through an agent): rustok init   — creates the wallet and prints your 12-word phrase + PIN once"
    say "to roll back to a previous version, re-run the installer from that version's tag: $RAW_BASE/wallet-tui-v<older>/scripts/install.sh"
}

main "$@"
