#!/bin/sh
# rustok installer — one command to a verified wallet shim.
#
#   curl --proto '=https' --tlsv1.2 -fsSL \
#     https://raw.githubusercontent.com/rustok-org/mcp/vX.Y.Z/scripts/install.sh | sh
#
# What it does: pulls the wallet image BY DIGEST, verifies its cosign signature
# against THIS repo's publishing workflow (a mutable tag cannot be swapped in),
# installs the `rustok` shim into ~/.local/bin, and adds it to PATH.
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
WALLET_VERSION="0.7.1"
WALLET_DIGEST="sha256:0000000000000000000000000000000000000000000000000000000000000000"
SHIM_COMMIT="0000000000000000000000000000000000000000"

IMAGE_REPO="ghcr.io/rustok-org/rustok-wallet-tui"
RAW_BASE="https://raw.githubusercontent.com/rustok-org/mcp"
# The one identity cosign pins to: the workflow that builds AND signs the image.
COSIGN_IDENTITY="https://github.com/rustok-org/mcp/.github/workflows/wallet-publish.yml@refs/tags/v${WALLET_VERSION}"
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
    command -v cosign >/dev/null 2>&1 \
        || die "cosign is required to verify the wallet image signature — install it: https://docs.sigstore.dev/cosign/installation (no other step needs it)"
    command -v curl >/dev/null 2>&1 \
        || die "curl is required to fetch the shim — install it (dnf/apt install curl)"

    image="${IMAGE_REPO}@${WALLET_DIGEST}"

    # 1) Verify the signature FIRST (cheapest gate, downloads no image bytes):
    #    an unsigned or wrong-identity image is rejected before anything lands
    #    on disk. Ratified order (decision #2): nothing is written until the
    #    image is proven to come from this repo's signing workflow.
    say "verifying the wallet image signature ($WALLET_VERSION)…"
    cosign verify "$image" \
        --certificate-identity "$COSIGN_IDENTITY" \
        --certificate-oidc-issuer "$COSIGN_ISSUER" >/dev/null 2>&1 \
        || die "cosign could NOT verify $image against this repo's publishing workflow — refusing to install (an unsigned or tampered image, or a release that has not run its signed publish yet)"

    # 2) Pull the verified image by digest.
    say "pulling the verified image…"
    "$engine" pull "$image" >/dev/null \
        || die "'$engine' failed to pull the verified image — check the daemon/machine and your network"

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
    say "to roll back to a previous version, re-run the installer from that version's tag: $RAW_BASE/v<older>/scripts/install.sh"
}

main "$@"
