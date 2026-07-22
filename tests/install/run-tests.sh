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
    TEST_SHELL="/bin/bash"
}

# Replace a real tool with one that always fails, to exercise the filesystem
# error paths. The suite could previously only fail curl/cosign/podman, which is
# exactly why three unguarded writes shipped through a green suite.
break_tool() {
    rm -f "$WORK/bin/$1"
    { printf '#!/bin/sh\n'
      printf 'echo "%s: stub simulated failure" 1>&2\n' "$1"
      printf 'exit 1\n'; } >"$WORK/bin/$1"
    chmod +x "$WORK/bin/$1"
}

# A cosign that IS executable but cannot run as a program. The kernel refuses
# the exec, the shell falls back to interpreting it, and the resulting exit code
# depends on the bytes: garbage -> 2, truncated ELF -> 126, near-text -> 127.
# All three are the same real-world failure and must land in the same branch.
plant_unrunnable_cosign() {
    rm -f "$WORK/bin/cosign"
    case "$1" in
        garbage) head -c 400 /dev/urandom >"$WORK/bin/cosign" ;;
        elf) printf '\177ELF\002\001\001' >"$WORK/bin/cosign"; head -c 200 /dev/zero >>"$WORK/bin/cosign" ;;
        text) printf 'this is not a program\nnor a script\n' >"$WORK/bin/cosign" ;;
    esac
    chmod +x "$WORK/bin/cosign"
}

plant_podman() { ln -s "$TESTS_DIR/stub-bin/podman" "$WORK/bin/podman"; }
plant_docker() { ln -s "$TESTS_DIR/stub-bin/podman" "$WORK/bin/docker"; }

# cosign is planted by fresh(); these two take it away in the two ways the real
# world does:
#   unplant_cosign  -> not in PATH at all.
#   unexec_cosign   -> in PATH, real file, no +x — the literal state of the
#                      machine that triggered this fix. `command -v` disagrees
#                      about it per shell (FALSE under sh, TRUE under bash),
#                      which is exactly why detection no longer asks it; both
#                      shells are exercised below and must reach the same branch.
unplant_cosign() { rm -f "$WORK/bin/cosign"; }
unexec_cosign() {
    rm -f "$WORK/bin/cosign"
    printf '#!/bin/sh\necho unreachable\n' >"$WORK/bin/cosign"
    chmod 644 "$WORK/bin/cosign"
    ln -s "$(command -v bash)" "$WORK/bin/bash" 2>/dev/null || true
}

run_install() {
    # SHELL fixed to bash so the profile target is deterministic (-> .bashrc);
    # TEST_SHELL overrides it for the fish/csh cases.
    OUT="$(HOME="$WORK/home" PATH="$TEST_PATH" SHELL="$TEST_SHELL" \
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

# --- cosign present but not executable, under sh — the DELIVERY path ----------
# The installer ships as `curl … | sh`. Under sh a non-executable file is
# invisible to `command -v`, so the previous detector called a broken cosign
# "not installed" and the branch written for it was unreachable on the very path
# users take. Probing by running it is shell-independent.

fresh
plant_podman
unexec_cosign
run_install
if assert_exit 0 && shim_installed \
    && assert_has "will not run" \
    && assert_lacks "tampered" \
    && log_lacks 'cosign verify'; then
    ok "install: under sh, a present-but-unrunnable cosign is reported as unrunnable — not as 'not installed'"
else not_ok "install: under sh, a present-but-unrunnable cosign is reported as unrunnable — not as 'not installed'"; fi

# --- the three ways an executable cosign still cannot run ---------------------
# Same real failure (corrupt/foreign binary), three different exit codes
# depending on the bytes: 2, 126, 127. A detector keyed on any single code gets
# one of them wrong; keying on "non-zero" cannot.

for VARIANT in garbage elf text; do
    fresh
    plant_podman
    plant_unrunnable_cosign "$VARIANT"
    run_install
    if assert_exit 0 && shim_installed && assert_has "will not run" && assert_lacks "tampered"; then
        ok "install: an executable-but-unrunnable cosign ($VARIANT) lands in the same branch, install proceeds"
    else not_ok "install: an executable-but-unrunnable cosign ($VARIANT) lands in the same branch, install proceeds"; fi
done

# --- filesystem failures are branded, clean up, and do not lie ----------------

fresh
plant_podman
break_tool mkdir
run_install
# Asserting on the installer's OWN wording, not merely on the prefix appearing
# somewhere: earlier lines already carry the prefix, so a prefix check here
# would pass no matter how the script died.
if assert_exit 1 && assert_has "could not create" && ! shim_installed; then
    ok "install: a failed mkdir aborts with a branded error, nothing installed"
else not_ok "install: a failed mkdir aborts with a branded error, nothing installed"; fi

fresh
plant_podman
break_tool chmod
run_install
if assert_exit 1 && assert_has "could not make the shim executable" \
    && [ ! -e "$WORK/home/.local/bin/rustok.rustok-tmp" ]; then
    ok "install: a failed chmod aborts with a branded error AND removes the temp file it created"
else not_ok "install: a failed chmod aborts with a branded error AND removes the temp file it created"; fi

# The shim is already installed and working by the time the profile is touched.
# Dying here would report a failed install that actually succeeded.
fresh
plant_podman
: >"$WORK/home/.bashrc"
chmod 444 "$WORK/home/.bashrc"
run_install
RC_PROF="$RC"
chmod 644 "$WORK/home/.bashrc"
if [ "$RC_PROF" -eq 0 ] && shim_installed && assert_has "could not write" && assert_has "export PATH="; then
    ok "install: an unwritable profile does not fail the install — shim stays, the manual PATH line is printed"
else RC="$RC_PROF"; not_ok "install: an unwritable profile does not fail the install — shim stays, the manual PATH line is printed"; fi

# --- the profile gate looks at the PROFILE, not at this session's PATH --------
# Gating on the live PATH would skip the edit for someone whose PATH comes from
# a parent shell — and they would lose `rustok` in every new terminal.

fresh
plant_podman
# shellcheck disable=SC2016  # $PATH stays literal: this mimics a real profile line
printf 'export PATH="%s:$PATH"\n' "$WORK/home/.local/bin" >"$WORK/home/.bashrc"
run_install
BLOCKS="$(grep -c '^# >>> rustok installer >>>$' "$WORK/home/.bashrc" || true)"
if assert_exit 0 && [ "$BLOCKS" = "0" ]; then
    ok "install: the profile already puts the dir on PATH -> no block appended (no pointless dotfile edit)"
else RC="$RC blocks=$BLOCKS"; not_ok "install: the profile already puts the dir on PATH -> no block appended (no pointless dotfile edit)"; fi

# --- replacing an existing rustok is announced, not silent -------------------

fresh
plant_podman
mkdir -p "$WORK/home/.local/bin"
printf '#!/bin/sh\necho someone elses rustok\n' >"$WORK/home/.local/bin/rustok"
chmod +x "$WORK/home/.local/bin/rustok"
run_install
if assert_exit 0 && shim_installed && assert_has "replac"; then
    ok "install: an existing rustok is replaced with a line saying so, not silently"
else not_ok "install: an existing rustok is replaced with a line saying so, not silently"; fi

# --- shells that never read the file we would have written -------------------

fresh
plant_podman
TEST_SHELL="/usr/bin/fish"
run_install
if assert_exit 0 && shim_installed \
    && [ ! -e "$WORK/home/.profile" ] \
    && assert_has "fish"; then
    ok "install: under fish, no POSIX profile is written and fish-specific instructions are printed"
else not_ok "install: under fish, no POSIX profile is written and fish-specific instructions are printed"; fi

# --- the refusal points somewhere a curl|sh user can actually reach ----------

fresh
plant_podman
STUB_COSIGN_FAIL=1
run_install
if assert_exit 1 && assert_has "https://"; then
    ok "install: the refusal links an absolute URL — a curl|sh user has no local docs/ tree"
else not_ok "install: the refusal links an absolute URL — a curl|sh user has no local docs/ tree"; fi

# --- an unset HOME fails in our voice, not the shell's ----------------------

fresh
plant_podman
OUT="$(env -u HOME PATH="$TEST_PATH" SHELL=/bin/bash sh "$INSTALL" </dev/null 2>&1)" && RC=0 || RC=$?
if [ "$RC" -ne 0 ] && assert_has "rustok-install:"; then
    ok "install: an unset HOME is reported in the installer's own voice"
else not_ok "install: an unset HOME is reported in the installer's own voice"; fi

# --- the script's own header must teach the tag namespace that exists --------

N=$((N + 1))
if grep -qE '^#.*raw\.githubusercontent\.com/rustok-org/mcp/v[X0-9]' "$INSTALL"; then
    FAIL=$((FAIL + 1))
    echo "not ok $N - install.sh header shows a tag pattern that 404s (tags are wallet-tui-vX.Y.Z)"
else
    PASS=$((PASS + 1))
    echo "ok $N - install.sh header shows the tag namespace that actually exists"
fi

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
