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
    NO_MODIFY=""
    TEST_PATH="$WORK/bin"
}

plant_podman() { ln -s "$TESTS_DIR/stub-bin/podman" "$WORK/bin/podman"; }
plant_docker() { ln -s "$TESTS_DIR/stub-bin/podman" "$WORK/bin/docker"; }

run_install() {
    # SHELL fixed to bash so the profile target is deterministic (-> .bashrc).
    OUT="$(HOME="$WORK/home" PATH="$TEST_PATH" SHELL=/bin/bash \
        STUB_LOG="$WORK/log" \
        STUB_CURL_FAIL="$STUB_CURL_FAIL" STUB_PULL_FAIL="$STUB_PULL_FAIL" \
        STUB_COSIGN_FAIL="$STUB_COSIGN_FAIL" \
        RUSTOK_NO_MODIFY_PATH="$NO_MODIFY" \
        sh "$INSTALL" </dev/null 2>&1)" && RC=0 || RC=$?
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
log_has() { grep -q "$1" "$WORK/log"; }

# --- happy path ---------------------------------------------------------------

fresh
plant_podman
run_install
SHIMOK=0
[ -f "$WORK/home/.local/bin/rustok" ] && [ -x "$WORK/home/.local/bin/rustok" ] \
    && grep -q "STUB-SHIM-BODY" "$WORK/home/.local/bin/rustok" && SHIMOK=1
if assert_exit 0 && [ "$SHIMOK" = "1" ] \
    && log_has 'cosign verify' && log_has 'wallet-publish.yml' \
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

fresh
plant_podman
STUB_COSIGN_FAIL=1
run_install
if assert_exit 1 && assert_has "signature" \
    && [ ! -e "$WORK/home/.local/bin/rustok" ] \
    && [ ! -e "$WORK/home/.bashrc" ]; then
    ok "install: a failed cosign verify aborts BEFORE writing the shim or the PATH block (fail-closed)"
else not_ok "install: a failed cosign verify aborts BEFORE writing the shim or the PATH block (fail-closed)"; fi

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
