#!/bin/sh
# install.sh test suite — plain POSIX sh, zero dependencies, engine/curl/cosign
# all stubbed (no network, no real pull, no real signature). Mirrors the shim
# suite's hermetic style: whether a tool "exists" is decided by the TEST, and
# every assertion is a strict text/exit predicate.
#
# The installer is driven with its network side replaced by stubs and its target
# dirs pointed inside $WORK — a real curl|sh only differs in the stubs.
set -u

TESTS_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$TESTS_DIR/../.." && pwd)"
INSTALL="$REPO_ROOT/scripts/install.sh"

PASS=0
FAIL=0
N=0

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

fresh() {
    rm -rf "${WORK:?}/home" "${WORK:?}/bin" "${WORK:?}/log"
    mkdir -p "$WORK/home" "$WORK/bin"
    : >"$WORK/log"
    for tool in sh cat sed head grep mkdir chmod rm mv cut env printf command basename; do
        ln -s "$(command -v "$tool")" "$WORK/bin/$tool" 2>/dev/null || true
    done
    ln -s "$TESTS_DIR/stub-bin/curl" "$WORK/bin/curl"
    ln -s "$TESTS_DIR/stub-bin/cosign" "$WORK/bin/cosign"
    STUB_CURL_FAIL=0
    STUB_PULL_FAIL=0
    STUB_COSIGN_FAIL=0
    STUB_COSIGN_BROKEN=0
    NO_MODIFY=""
    TEST_PATH="$WORK/bin"
    RUN_SHELL="sh"
}

plant_podman() { ln -s "$TESTS_DIR/stub-bin/podman" "$WORK/bin/podman"; }
plant_docker() { ln -s "$TESTS_DIR/stub-bin/podman" "$WORK/bin/docker"; }

# cosign is planted by fresh(); these two take it away in the two ways the real
# world does. They are NOT interchangeable, and the difference is the whole
# reason this branch exists:
#   unplant_cosign  -> not in PATH at all.
#   unexec_cosign   -> in PATH, real file, no +x. Under `sh` (POSIX mode)
#                      `command -v` reports FALSE, under `bash` TRUE — so this
#                      one is only meaningful with RUN_SHELL=bash, and it is the
#                      literal state of the machine that triggered this fix.
unplant_cosign() { rm -f "$WORK/bin/cosign"; }
unexec_cosign() {
    rm -f "$WORK/bin/cosign"
    printf '#!/bin/sh\necho unreachable\n' >"$WORK/bin/cosign"
    chmod 644 "$WORK/bin/cosign"
    ln -s "$(command -v bash)" "$WORK/bin/bash" 2>/dev/null || true
}

run_install() {
    # SHELL fixed to bash so the profile target is deterministic (-> .bashrc).
    OUT="$(HOME="$WORK/home" PATH="$TEST_PATH" SHELL=/bin/bash \
        STUB_LOG="$WORK/log" \
        STUB_CURL_FAIL="$STUB_CURL_FAIL" STUB_PULL_FAIL="$STUB_PULL_FAIL" \
        STUB_COSIGN_FAIL="$STUB_COSIGN_FAIL" \
        STUB_COSIGN_BROKEN="$STUB_COSIGN_BROKEN" \
        RUSTOK_NO_MODIFY_PATH="$NO_MODIFY" \
        "$RUN_SHELL" "$INSTALL" </dev/null 2>&1)" && RC=0 || RC=$?
}

ok() { N=$((N + 1)); PASS=$((PASS + 1)); echo "ok $N - $1"; }
not_ok() {
    N=$((N + 1)); FAIL=$((FAIL + 1))
    echo "not ok $N - $1"
    echo "    exit: $RC"
    echo "$OUT" | sed 's/^/    out: /'
}
assert_exit() { [ "$RC" -eq "$1" ]; }
assert_has() { case "$OUT" in *"$1"*) return 0 ;; *) return 1 ;; esac; }
assert_lacks() { case "$OUT" in *"$1"*) return 1 ;; *) return 0 ;; esac; }
log_has() { grep -q "$1" "$WORK/log"; }
log_lacks() { ! grep -q "$1" "$WORK/log"; }
shim_installed() { [ -f "$WORK/home/.local/bin/rustok" ] && [ -x "$WORK/home/.local/bin/rustok" ]; }

# --- happy path ---------------------------------------------------------------

fresh
plant_podman
run_install
SHIMOK=0
[ -f "$WORK/home/.local/bin/rustok" ] && [ -x "$WORK/home/.local/bin/rustok" ] \
    && grep -q "STUB-SHIM-BODY" "$WORK/home/.local/bin/rustok" && SHIMOK=1
if assert_exit 0 && [ "$SHIMOK" = "1" ] \
    && log_has 'cosign verify' && log_has 'wallet-publish.yml' \
    && log_has 'certificate-identity.*wallet-publish.yml@refs/heads/main' \
    && log_has 'token.actions.githubusercontent.com' \
    && log_has 'podman pull .*@sha256:' \
    && grep -q '^# >>> rustok installer >>>$' "$WORK/home/.bashrc" \
    && grep -q '^# <<< rustok installer <<<$' "$WORK/home/.bashrc"; then
    ok "install: shim placed +x, image pulled by digest, cosign verify pinned to the workflow identity, PATH block written"
else not_ok "install: shim placed +x, image pulled by digest, cosign verify pinned to the workflow identity, PATH block written"; fi

# --- fetch is TLS-hardened and pins the shim by COMMIT SHA, not a tag ----------

fresh
plant_podman
run_install
if assert_exit 0 \
    && log_has "curl .*--proto =https" && log_has "curl .*--tlsv1.2" \
    && grep -E "curl .*raw.githubusercontent.com/rustok-org/mcp/[0-9a-f]{7,40}/cli/rustok" "$WORK/log" >/dev/null; then
    ok "install: shim fetched over --proto=https --tlsv1.2 from a commit-SHA-pinned raw URL (not a mutable tag)"
else not_ok "install: shim fetched over --proto=https --tlsv1.2 from a commit-SHA-pinned raw URL (not a mutable tag)"; fi

# --- fail-closed: a bad signature installs NOTHING ----------------------------
# A WORKING cosign whose verify says no. The only branch that may refuse.

fresh
plant_podman
STUB_COSIGN_FAIL=1
run_install
if assert_exit 1 && assert_has "signature" \
    && [ ! -e "$WORK/home/.local/bin/rustok" ] \
    && [ ! -e "$WORK/home/.bashrc" ]; then
    ok "install: a failed cosign verify aborts BEFORE writing the shim or the PATH block (fail-closed)"
else not_ok "install: a failed cosign verify aborts BEFORE writing the shim or the PATH block (fail-closed)"; fi

# The refusal must stay fail-closed but stop CLAIMING sabotage: keyless verify
# reaches Rekor over the network, so a non-zero exit is "signature did not match
# OR the check could not finish". Naming only tampering turns an outage into an
# accusation — the same wall we are tearing down, one step later.
if assert_exit 1 && assert_has "signature" && assert_has "transparency log"; then
    ok "install: the refusal names BOTH causes (bad signature / check could not complete), not tampering alone"
else not_ok "install: the refusal names BOTH causes (bad signature / check could not complete), not tampering alone"; fi

# cosign 2.x cannot see our signatures at all (they are OCI referrers; 2.x looks
# for a .sig tag), so a whole class of users lands in this branch through no
# fault of the image. Being told the cause without being told the way out reads
# as "you are stuck" — and the second way out (remove the optional tool) is
# counter-intuitive enough that it has to be spelled out.
if assert_exit 1 && assert_has "cosign 3+" && assert_has "remove cosign"; then
    ok "install: the refusal names both ways forward (upgrade to cosign 3+, or remove cosign and install by digest)"
else not_ok "install: the refusal names both ways forward (upgrade to cosign 3+, or remove cosign and install by digest)"; fi

# --- cosign ABSENT: provenance is skipped, the install still happens ----------

fresh
plant_podman
unplant_cosign
run_install
if assert_exit 0 && shim_installed \
    && assert_has "digest" \
    && assert_lacks "tampered" \
    && log_has 'podman pull .*@sha256:' \
    && grep -q '^# >>> rustok installer >>>$' "$WORK/home/.bashrc"; then
    ok "install: no cosign at all -> warns about provenance, still installs by digest (cosign is not a wall)"
else not_ok "install: no cosign at all -> warns about provenance, still installs by digest (cosign is not a wall)"; fi

# --- cosign PRESENT but NOT RUNNABLE (wrong arch / missing libc) --------------
# Executable, so `command -v` says yes in every shell — only running it tells
# the truth. Without the `version` probe this lands in verify and dies with
# "tampered" on a perfectly good image.

fresh
plant_podman
STUB_COSIGN_BROKEN=1
run_install
if assert_exit 0 && shim_installed \
    && assert_lacks "tampered" \
    && log_has 'cosign version' \
    && log_lacks 'cosign verify' \
    && log_has 'podman pull .*@sha256:'; then
    ok "install: cosign present but unrunnable -> probed, treated as absent, installs by digest (never called a tamper)"
else not_ok "install: cosign present but unrunnable -> probed, treated as absent, installs by digest (never called a tamper)"; fi

# --- cosign PRESENT but not +x, run under bash -------------------------------
# The literal machine state that triggered this fix. Under `sh` the file reads
# as absent; under `bash` `command -v` returns TRUE and the exec fails with 126.
# Both must end in the same place: installed, no accusation.

fresh
plant_podman
unexec_cosign
RUN_SHELL="bash"
run_install
if assert_exit 0 && shim_installed \
    && assert_lacks "tampered" \
    && log_has 'podman pull .*@sha256:'; then
    ok "install: cosign present without +x under bash -> installs by digest instead of crying tamper (the reported incident)"
else not_ok "install: cosign present without +x under bash -> installs by digest instead of crying tamper (the reported incident)"; fi

# --- fail-closed: a failed pull installs nothing ------------------------------

fresh
plant_podman
STUB_PULL_FAIL=1
run_install
if assert_exit 1 && [ ! -e "$WORK/home/.local/bin/rustok" ]; then
    ok "install: a failed image pull aborts, shim not written"
else not_ok "install: a failed image pull aborts, shim not written"; fi

# --- fail-closed: a failed shim fetch leaves nothing half-written -------------

fresh
plant_podman
STUB_CURL_FAIL=1
run_install
if assert_exit 1 && [ ! -e "$WORK/home/.local/bin/rustok" ]; then
    ok "install: a failed shim fetch aborts, no half-written shim"
else not_ok "install: a failed shim fetch aborts, no half-written shim"; fi

# --- RUSTOK_NO_MODIFY_PATH leaves the profile untouched -----------------------

fresh
plant_podman
NO_MODIFY=1
run_install
if assert_exit 0 && [ -f "$WORK/home/.local/bin/rustok" ] \
    && [ ! -e "$WORK/home/.bashrc" ] \
    && assert_has "PATH"; then
    ok "install: RUSTOK_NO_MODIFY_PATH=1 installs the shim but never edits a profile, prints the manual PATH line"
else not_ok "install: RUSTOK_NO_MODIFY_PATH=1 installs the shim but never edits a profile, prints the manual PATH line"; fi

# --- idempotent: a second run does not duplicate the PATH block ---------------

fresh
plant_podman
run_install
run_install
BLOCKS="$(grep -c '^# >>> rustok installer >>>$' "$WORK/home/.bashrc")"
if assert_exit 0 && [ "$BLOCKS" = "1" ]; then
    ok "install: a second run does not duplicate the installer PATH block (idempotent)"
else RC="$RC blocks=$BLOCKS"; not_ok "install: a second run does not duplicate the installer PATH block (idempotent)"; fi

# --- engine detection: docker fallback, then a named refusal ------------------

fresh
plant_docker
run_install
if assert_exit 0 && log_has 'docker pull .*@sha256:'; then
    ok "install: no podman -> docker fallback pulls by digest"
else not_ok "install: no podman -> docker fallback pulls by digest"; fi

fresh
run_install
if assert_exit 1 && assert_has "podman" && [ ! -e "$WORK/home/.local/bin/rustok" ]; then
    ok "install: neither engine -> named refusal pointing at podman, nothing installed"
else not_ok "install: neither engine -> named refusal pointing at podman, nothing installed"; fi

# --- static invariant: install.sh NEVER touches a secret/keystore/init --------

N=$((N + 1))
# The invariant is about ACTIONS on money-critical material, not the words: the
# installer may PRINT "rustok init" as the next-step hint, but it must never run
# create-wallet, name the keyring password env var, or create/remove a secret.
STRIPPED="$(sed 's/^[[:space:]]*#.*//' "$INSTALL")"
if printf '%s\n' "$STRIPPED" | grep -qE 'create-wallet|RUSTOK_KEYRING_PASSWORD|secret (create|rm)'; then
    FAIL=$((FAIL + 1))
    echo "not ok $N - install.sh never touches a secret, keystore or wallet init (epic invariant #1)"
else
    PASS=$((PASS + 1))
    echo "ok $N - install.sh never touches a secret, keystore or wallet init (epic invariant #1)"
fi

echo "# $PASS passed, $FAIL failed, $N total"
[ "$FAIL" -eq 0 ]
