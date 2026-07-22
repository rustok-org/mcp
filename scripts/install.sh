#!/bin/sh
# rustok installer — one command to a verified wallet shim.
#
#   curl --proto '=https' --tlsv1.2 -fsSL \
#     https://raw.githubusercontent.com/rustok-org/mcp/wallet-tui-vX.Y.Z/scripts/install.sh | sh
#
# The tag namespace is wallet-tui-vX.Y.Z. A bare vX.Y.Z tag does not exist and
# that URL 404s — this header is copied by people, so it must be runnable.
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
WALLET_VERSION="0.8.2"
WALLET_DIGEST="sha256:ca3a9088ed821e03f5019ba3dc0e5fefda9a0b4d19a8d3a2e4791054d6aeec05"
SHIM_COMMIT="20bf07f7cf5786cf6b0c1f2020d4f39151aed080"

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

say() { printf 'rustok-install: %s\n' "$*"; }
die() { printf 'rustok-install: %s\n' "$*" 1>&2; exit 1; }

# Guarded before use: under `set -u` a missing HOME (stripped containers, CI,
# systemd units without Environment=HOME) would abort with the shell's own
# message instead of ours, from a line the reader cannot map to a cause.
[ -n "${HOME:-}" ] \
    || die "HOME is not set, so there is nowhere to install to — expected ~/.local/bin"

INSTALL_DIR="$HOME/.local/bin"
SHIM_PATH="$INSTALL_DIR/rustok"

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
    # Two states on purpose, keyed on whether cosign RUNS — not on whether a
    # file by that name is in PATH.
    #
    # `command -v` answers the wrong question and answers it differently per
    # shell: for a present-but-non-executable file /bin/sh in POSIX mode says
    # no while bash says yes. Since we ship as `curl … | sh`, keying on it made
    # the most common breakage (a download that lost its +x bit) report
    # "cosign is not installed" — a lie about the user's machine.
    #
    # Nor is there a usable exit code to split "missing" from "broken": an
    # executable file the kernel refuses returns 2, 126 or 127 depending on its
    # bytes (measured: random garbage 2, truncated ELF 126, near-text 127). Any
    # single-code rule misfiles one of them. Both states lead to the same
    # action anyway — install by digest, provenance unchecked — so we do not
    # pretend to distinguish them and say both possibilities out loud instead.
    cosign version >/dev/null 2>&1 && { echo works; return 0; }
    echo unavailable
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
    # the same marker block from any of these, so writing to one is safe.
    # Empty means "this shell reads none of the files we know how to edit" —
    # fish and csh/tcsh do not read ~/.profile and do not speak `export VAR=val`,
    # so writing one and then telling the user to open a new shell would simply
    # be false. For those we print their own syntax and touch nothing.
    case "${SHELL##*/}" in
        bash) echo "$HOME/.bashrc" ;;
        zsh) echo "$HOME/.zshrc" ;;
        sh | ksh | dash | ash) echo "$HOME/.profile" ;;
        *) echo "" ;;
    esac
}

manual_path_line() {
    # $PATH and $path stay literal on purpose — they must expand in the user's
    # shell when they paste the line, not here.
    # shellcheck disable=SC2016
    case "${SHELL##*/}" in
        fish) printf 'fish_add_path %s' "$INSTALL_DIR" ;;
        csh | tcsh) printf 'set path = (%s $path)' "$INSTALL_DIR" ;;
        *) printf 'export PATH="%s:$PATH"' "$INSTALL_DIR" ;;
    esac
}

add_to_path() {
    # The 2.3c uninstall contract: the PATH edit lives between these EXACT
    # markers and nothing else touches the profile. RUSTOK_NO_MODIFY_PATH opts
    # out entirely (prints the manual line). Idempotent: an existing block is
    # never duplicated.
    if [ -n "${RUSTOK_NO_MODIFY_PATH:-}" ]; then
        say "RUSTOK_NO_MODIFY_PATH set — not editing your shell profile."
        say "Add this line yourself: $(manual_path_line)"
        return 0
    fi
    prof="$(profile_file)"
    if [ -z "$prof" ]; then
        say "your shell (${SHELL##*/}) does not read a POSIX profile — leaving your config alone."
        say "Add this yourself: $(manual_path_line)"
        return 0
    fi
    if [ -f "$prof" ] && grep -q '^# >>> rustok installer >>>$' "$prof"; then
        say "PATH block already present in $prof — left as is."
        return 0
    fi
    # Gate on the PROFILE, not on this session's PATH. A directory that is on
    # PATH only because a parent process exported it is gone in the next
    # terminal — skipping the edit for that user would cost them `rustok`
    # everywhere. Conversely, if the profile already adds it, a second entry is
    # pure noise in someone else's dotfile.
    if [ -f "$prof" ] && grep -qF "$INSTALL_DIR" "$prof"; then
        say "$prof already puts $INSTALL_DIR on PATH — left as is."
        return 0
    fi
    # Not fatal: by now the shim is fetched, executable and in place. Dying here
    # would report a failed install that in fact succeeded (an unwritable
    # dotfile is a real case — root-owned after a sudo, immutable bit, NFS home).
    {
        printf '# >>> rustok installer >>>\n'
        # $INSTALL_DIR expands now (via %s); $PATH MUST stay literal so it
        # expands at the user's shell startup, not at install time.
        # shellcheck disable=SC2016
        printf 'export PATH="%s:$PATH"\n' "$INSTALL_DIR"
        printf '# <<< rustok installer <<<\n'
    } >>"$prof" 2>/dev/null || true
    # Report what is actually in the file, not whether the write "returned" ok.
    # A failed redirection on a compound command does NOT reliably surface as a
    # non-zero status, so trusting it printed "added … to PATH" over a file the
    # shell had just refused to open — the exact class of lie this release is
    # about. Checking the outcome cannot drift from reality.
    if [ -f "$prof" ] && grep -q '^# <<< rustok installer <<<$' "$prof"; then
        say "added $INSTALL_DIR to PATH in $prof — open a new shell or: . $prof"
    else
        say "could not write $prof — the shim is installed and working, only the PATH line is missing."
        say "Add this yourself: $(manual_path_line)"
    fi
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
  cosign fail here too.
  On 'no signatures found', check your version first: cosign 2.x cannot SEE our signatures at all
  (they are stored as OCI referrers, and 2.x looks for a .sig tag). Two ways forward, both fine:
  upgrade to cosign 3+ and re-run, or remove cosign and re-run — provenance is optional, the
  install then proceeds by digest, which is what fixes the bytes you get either way.
  Nothing has been installed. See https://github.com/rustok-org/mcp/blob/main/docs/TROUBLESHOOTING.md
  (an absolute link on purpose: installing over a pipe, you have no docs/ tree here)."
            say "signature verified — built by this repo's publishing workflow."
            ;;
        *)
            skip_provenance "cosign is unavailable — either it is not installed, or it is there but will not run (no execute bit, wrong architecture, missing libc, a truncated download)" "$image"
            ;;
    esac

    # 2) Pull by digest. NOT called "the verified image" — the branch above may
    #    have skipped verification, and the pull is what the digest guarantees,
    #    not what cosign did.
    say "pulling the image by digest…"
    "$engine" pull "$image" >/dev/null \
        || die "'$engine' failed to pull the image — check the daemon/machine and your network"

    # 3) Fetch the shim from a COMMIT-pinned raw URL (immutable; a force-pushed
    #    tag cannot swap it) over a hardened TLS channel, then install atomically.
    # Every write below is checked. They used to be bare: a failure produced the
    # shell's own unbranded error, and two of them fired AFTER the work had
    # already succeeded — reporting a failed install that had in fact worked.
    mkdir -p "$INSTALL_DIR" \
        || die "could not create $INSTALL_DIR — check the permissions on your home directory"
    shim_tmp="$SHIM_PATH.rustok-tmp"
    say "fetching the rustok shim…"
    curl --proto '=https' --tlsv1.2 -fsSL \
        "$RAW_BASE/$SHIM_COMMIT/cli/rustok" -o "$shim_tmp" \
        || { rm -f "$shim_tmp"; die "failed to fetch the shim over TLS — refusing to install a partial copy"; }
    chmod +x "$shim_tmp" \
        || { rm -f "$shim_tmp"; die "could not make the shim executable in $INSTALL_DIR — check its permissions"; }
    # Say it out loud: whatever was there is about to be gone. A `rustok` from
    # another source, or a symlink someone set up by hand, is replaced silently
    # otherwise — and the log gives them nothing to notice it by.
    if [ -e "$SHIM_PATH" ] || [ -L "$SHIM_PATH" ]; then
        say "replacing the existing $SHIM_PATH"
    fi
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
