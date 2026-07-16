#!/bin/sh
# Shim test suite — plain POSIX sh, zero dependencies (bats-free by design: runs
# identically on this repo's CI and any dev machine). Engine calls go to the
# stub in stub-bin/, never to a real podman/docker.
#
# Every assertion is a STRICT text/exit predicate (assert_resident precedent):
# "the shim answered" is never enough — twice an omnivorous harness let real
# bugs ship.
set -u

TESTS_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$TESTS_DIR/../.." && pwd)"
SHIM="$REPO_ROOT/cli/rustok"

PASS=0
FAIL=0
N=0

# Per-run scratch; wiped per test case.
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

fresh() {
    # Reset the world HERMETICALLY: the shim sees ONLY $WORK/bin — the stub
    # engine(s) this test plants plus symlinks to the coreutils the shim needs.
    # No /usr/bin: whether "docker exists" is decided by the TEST, never by the
    # machine (ubuntu-latest ships a real docker; a dev box may not).
    rm -rf "${WORK:?}/home" "${WORK:?}/log" "${WORK:?}/bin" "${WORK:?}/state"
    mkdir -p "$WORK/home" "$WORK/bin" "$WORK/state"
    : >"$WORK/log"
    # env hygiene: a previous test's exported wallet config must not leak in
    unset RUSTOK_RPC_URLS_1 RUSTOK_KEYRING_PASSWORD RUSTOK_IMAGE 2>/dev/null || true
    for tool in sh cat sed head sort awk mkdir basename cut tr rm mv grep env sleep stty; do
        ln -s "$(command -v "$tool")" "$WORK/bin/$tool"
    done
    ln -s "$TESTS_DIR/stub-bin/podman" "$WORK/bin/podman"
    STUB_CONTAINERS=""
    STUB_LEGACY=""
    STUB_INFO_FAIL=0
    STUB_PS_FAIL=0
    TEST_PATH="$WORK/bin"
}

plant_docker_stub() { ln -s "$TESTS_DIR/stub-bin/podman" "$WORK/bin/docker"; }
remove_podman_stub() { rm "$WORK/bin/podman"; }

run_shim() {
    # run_shim <args…> — capture stdout+stderr and exit code, stub-injected.
    OUT="$(HOME="$WORK/home" XDG_CONFIG_HOME="$WORK/home/.config" \
        PATH="$TEST_PATH" STUB_LOG="$WORK/log" STUB_STATE="$WORK/state" \
        STUB_CONTAINERS="$STUB_CONTAINERS" STUB_LEGACY="$STUB_LEGACY" \
        STUB_INFO_FAIL="$STUB_INFO_FAIL" STUB_PS_FAIL="$STUB_PS_FAIL" \
        sh "$SHIM" "$@" 2>&1)" && RC=0 || RC=$?
}

PY3="$(command -v python3)"

run_init_pty() {
    # run_init_pty <pw1> <pw2> [shim args…] — drives init on a real pty (the
    # /dev/tty gate) feeding the two password lines like a human would.
    pw1="$1"
    pw2="$2"
    shift 2
    OUT="$(printf '%s\n%s\n' "$pw1" "$pw2" | \
        HOME="$WORK/home" XDG_CONFIG_HOME="$WORK/home/.config" \
        PATH="$TEST_PATH" STUB_LOG="$WORK/log" STUB_STATE="$WORK/state" \
        STUB_CONTAINERS="$STUB_CONTAINERS" STUB_LEGACY="$STUB_LEGACY" \
        STUB_INFO_FAIL="$STUB_INFO_FAIL" STUB_PS_FAIL="$STUB_PS_FAIL" \
        "$PY3" "$TESTS_DIR/pty-init.py" sh "$SHIM" init "$@" 2>&1)" && RC=0 || RC=$?
}

ok() {
    N=$((N + 1))
    PASS=$((PASS + 1))
    echo "ok $N - $1"
}

not_ok() {
    N=$((N + 1))
    FAIL=$((FAIL + 1))
    echo "not ok $N - $1"
    echo "    exit: $RC"
    echo "$OUT" | sed 's/^/    out: /'
}

assert_exit() { [ "$RC" -eq "$1" ]; }
assert_has() { case "$OUT" in *"$1"*) return 0 ;; *) return 1 ;; esac; }
assert_not_has() { ! assert_has "$1"; }

# --- basics -------------------------------------------------------------------

fresh
run_shim version
if assert_exit 0 && assert_has "rustok "; then ok "version exits 0"; else not_ok "version exits 0"; fi

fresh
run_shim help
if assert_exit 0 && assert_has "Usage: rustok"; then ok "help shows usage"; else not_ok "help shows usage"; fi

fresh
run_shim help
if assert_exit 0 && assert_has "podman inspect" && assert_has "RUSTOK_RPC_URLS"; then
    ok "help documents the keyed-RPC inspect-visibility interim (escalation #2)"
else not_ok "help documents the keyed-RPC inspect-visibility interim (escalation #2)"; fi

fresh
run_shim frobnicate
if assert_exit 2 && assert_has "unknown command 'frobnicate'"; then
    ok "unknown command exits 2"
else not_ok "unknown command exits 2"; fi

# --- engine resolution / stickiness (epic М-3) ---------------------------------

fresh
run_shim status
if assert_exit 0 && assert_has "engine: podman" \
    && [ "$(cat "$WORK/home/.config/rustok/config")" = "engine=podman" ]; then
    ok "first run pins engine=podman in the config"
else not_ok "first run pins engine=podman in the config"; fi

fresh
mkdir -p "$WORK/home/.config/rustok"
echo "engine=docker" >"$WORK/home/.config/rustok/config"
# docker deliberately NOT planted: its absence is the test's decision, hermetic
# from whatever the host machine has installed.
run_shim status
if assert_exit 1 && assert_has "configured engine 'docker'" && assert_has "not installed" \
    && assert_not_has "engine: podman"; then
    ok "pinned-but-missing engine fails loudly, never silently re-picks"
else not_ok "pinned-but-missing engine fails loudly, never silently re-picks"; fi

fresh
plant_docker_stub
remove_podman_stub
mkdir -p "$WORK/home/.config/rustok"
echo "engine=docker" >"$WORK/home/.config/rustok/config"
STUB_CONTAINERS="abc1;rustok=wallet;rustok.agent=claude;image=img"
run_shim status
if assert_exit 0 && assert_has "engine: docker" && assert_has "claude" \
    && grep -q '^docker ps' "$WORK/log"; then
    ok "pinned docker engine dispatches to docker (hermetic stub)"
else not_ok "pinned docker engine dispatches to docker (hermetic stub)"; fi

# --- console: discovery by BOTH labels -----------------------------------------

fresh
run_shim console
if assert_exit 1 && assert_has "no wallet running — the agent session starts it"; then
    ok "console with no wallet: named error"
else not_ok "console with no wallet: named error"; fi

fresh
STUB_CONTAINERS="abc123def456;rustok=wallet;rustok.agent=claude;image=ghcr.io/rustok-org/rustok-wallet-tui:v0.7.1"
run_shim console
if assert_exit 0 && assert_has "EXEC:abc123def456:rustok-console"; then
    ok "console with one wallet execs rustok-console in it"
else not_ok "console with one wallet execs rustok-console in it"; fi

fresh
# A container with the agent sub-label but WITHOUT rustok=wallet must be
# invisible: proves the shim sends the rustok=wallet filter.
STUB_CONTAINERS="imposter1;rustok.agent=claude;image=nginx"
run_shim console
if assert_exit 1 && assert_has "no wallet running"; then
    ok "agent-labeled non-wallet container is not matched (both labels sent)"
else not_ok "agent-labeled non-wallet container is not matched (both labels sent)"; fi

fresh
# The loud N>1 refusal — the exact named error, never the first match.
STUB_CONTAINERS="aaa1;rustok=wallet;rustok.agent=hermes;image=img bbb2;rustok=wallet;rustok.agent=claude;image=img"
run_shim console
if assert_exit 1 \
    && assert_has "multiple wallets running: claude, hermes — use --agent <name>" \
    && assert_not_has "EXEC:"; then
    ok "two wallets: loud refusal listing agents, no first-match exec"
else not_ok "two wallets: loud refusal listing agents, no first-match exec"; fi

fresh
STUB_CONTAINERS="aaa1;rustok=wallet;rustok.agent=hermes;image=img bbb2;rustok=wallet;rustok.agent=claude;image=img"
run_shim console --agent hermes
if assert_exit 0 && assert_has "EXEC:aaa1:rustok-console"; then
    ok "console --agent hermes picks exactly the hermes wallet"
else not_ok "console --agent hermes picks exactly the hermes wallet"; fi

fresh
STUB_CONTAINERS="bbb2;rustok=wallet;rustok.agent=claude;image=img"
run_shim console --agent ghost
if assert_exit 1 && assert_has "no wallet running for agent 'ghost'"; then
    ok "console --agent with no such agent: named error"
else not_ok "console --agent with no such agent: named error"; fi

fresh
STUB_CONTAINERS="abc123def456;rustok=wallet;rustok.agent=claude;image=img"
run_shim console
if grep -q -- "--filter label=rustok=wallet" "$WORK/log"; then
    ok "discovery call carries the rustok=wallet label filter (call log)"
else RC=0 OUT="$(cat "$WORK/log")"; not_ok "discovery call carries the rustok=wallet label filter (call log)"; fi

# --- status --------------------------------------------------------------------

fresh
STUB_CONTAINERS="aaa1;rustok=wallet;rustok.agent=hermes;image=img1 bbb2;rustok=wallet;rustok.agent=claude;image=img2"
run_shim status
if assert_exit 0 && assert_has "engine: podman" && assert_has "hermes" \
    && assert_has "claude" && assert_has "img1" && assert_has "img2"; then
    ok "status lists every running wallet with its agent"
else not_ok "status lists every running wallet with its agent"; fi

fresh
run_shim status
if assert_exit 0 && assert_has "no wallet running"; then
    ok "status with no wallet says so"
else not_ok "status with no wallet says so"; fi

# --- doctor --------------------------------------------------------------------

fresh
run_shim doctor
if assert_exit 0 && assert_has "ok: podman is responding" \
    && assert_has "warn: ~/.local/bin is NOT on PATH"; then
    ok "doctor: healthy engine, PATH warning without ~/.local/bin"
else not_ok "doctor: healthy engine, PATH warning without ~/.local/bin"; fi

fresh
TEST_PATH="$TESTS_DIR/stub-bin:$WORK/home/.local/bin:/usr/bin:/bin"
mkdir -p "$WORK/home/.local/bin"
run_shim doctor
if assert_exit 0 && assert_has "ok: ~/.local/bin is on PATH"; then
    ok "doctor: PATH ok when ~/.local/bin present"
else not_ok "doctor: PATH ok when ~/.local/bin present"; fi

fresh
STUB_INFO_FAIL=1
run_shim doctor
if assert_exit 1 && assert_has "fail: 'podman' is installed but not usable"; then
    ok "doctor: unresponsive engine is a fail and exit 1"
else not_ok "doctor: unresponsive engine is a fail and exit 1"; fi

fresh
STUB_LEGACY="deadbeef1234"
run_shim doctor
if assert_exit 0 && assert_has "leftover fixed-name container 'rustok-wallet-tui'" \
    && assert_has "rm -f rustok-wallet-tui"; then
    ok "doctor: legacy fixed-name container gets a removal hint"
else not_ok "doctor: legacy fixed-name container gets a removal hint"; fi

fresh
STUB_CONTAINERS="aaa1;rustok=wallet;rustok.agent=hermes;image=img"
run_shim doctor
if assert_exit 0 && assert_has "1 wallet(s) running: hermes"; then
    ok "doctor: reports running wallets by agent"
else not_ok "doctor: reports running wallets by agent"; fi

# --- installed-but-dead engine: named error, not raw ps stderr -----------------

fresh
STUB_PS_FAIL=1
run_shim console
if assert_exit 1 && assert_has "'podman' failed listing containers" \
    && assert_has "try: rustok doctor"; then
    ok "console with a dead engine: named error, not raw ps output"
else not_ok "console with a dead engine: named error, not raw ps output"; fi

# --- transition: pre-label wallets (no rustok.agent at all) --------------------
# Real production state: wallets launched before the label model carry only
# rustok=wallet. They must be readable, selectable-around, and nudged to migrate.

fresh
STUB_CONTAINERS="old111;rustok=wallet;image=img"
run_shim status
if assert_exit 0 && assert_has "(unlabeled)"; then
    ok "status shows a pre-label wallet as (unlabeled), not an empty cell"
else not_ok "status shows a pre-label wallet as (unlabeled), not an empty cell"; fi

fresh
STUB_CONTAINERS="old111;rustok=wallet;image=img bbb2;rustok=wallet;rustok.agent=claude;image=img"
run_shim console
if assert_exit 1 \
    && assert_has "multiple wallets running: (unlabeled), claude — use --agent <name>" \
    && assert_has "hint: an '(unlabeled)' wallet predates the label model"; then
    ok "refusal names (unlabeled) and hints at the label migration"
else not_ok "refusal names (unlabeled) and hints at the label migration"; fi

fresh
STUB_CONTAINERS="old111;rustok=wallet;image=img"
run_shim doctor
if assert_exit 0 && assert_has "warn: 1 wallet(s) without a rustok.agent label"; then
    ok "doctor warns about pre-label wallets"
else not_ok "doctor warns about pre-label wallets"; fi

# --- init: the trust boundary ---------------------------------------------------

# shellcheck disable=SC2016  # literal $x is the point: the password must NOT expand
PW_QUOTED='pa"ss$x'

fresh
run_shim init
if assert_exit 1 && assert_has "needs your own terminal" \
    && assert_has "never run it through an agent"; then
    ok "init without a tty: named refusal (Rule of two windows)"
else not_ok "init without a tty: named refusal (Rule of two windows)"; fi

fresh
run_init_pty "$PW_QUOTED" "$PW_QUOTED"
if assert_exit 0 && assert_has "keyring password stored" \
    && assert_has "STUB-SEED-BANNER" && assert_has "wallet created" \
    && [ "$(cat "$WORK/state/secret-rustok-keyring-claude")" = "$PW_QUOTED" ] \
    && ! grep -qF "$PW_QUOTED" "$WORK/log"; then
    ok "init: quote-safe password stored byte-exact, never in engine argv; seed banner passes through"
else not_ok "init: quote-safe password stored byte-exact, never in engine argv; seed banner passes through"; fi

fresh
run_init_pty "one-password" "different-password"
if assert_exit 1 && assert_has "passwords do not match — nothing stored" \
    && [ ! -f "$WORK/state/secret-rustok-keyring-claude" ]; then
    ok "init: password mismatch refuses and stores nothing"
else not_ok "init: password mismatch refuses and stores nothing"; fi

fresh
: >"$WORK/state/volume-rustok-wallet-tui"
run_shim init
if assert_exit 1 && assert_has "wallet volume 'rustok-wallet-tui' already exists" \
    && assert_has "never touches keystores"; then
    ok "init refuses when the keystore volume exists (no password even asked)"
else not_ok "init refuses when the keystore volume exists (no password even asked)"; fi

fresh
printf 'old-password' >"$WORK/state/secret-rustok-keyring-claude"
run_shim init
if assert_exit 1 && assert_has "stored keyring password for agent 'claude' already exists" \
    && assert_has "--force"; then
    ok "init refuses when the secret exists without --force"
else not_ok "init refuses when the secret exists without --force"; fi

fresh
: >"$WORK/state/volume-rustok-wallet-tui"
printf 'old-password' >"$WORK/state/secret-rustok-keyring-claude"
run_init_pty "new-password" "new-password" --force
if assert_exit 0 && assert_has "password re-stored, wallet untouched" \
    && [ "$(cat "$WORK/state/secret-rustok-keyring-claude")" = "new-password" ] \
    && ! grep -qE '(run .*create-wallet|volume rm)' "$WORK/log"; then
    ok "init --force re-stores the secret ONLY: no create-wallet, no volume rm"
else not_ok "init --force re-stores the secret ONLY: no create-wallet, no volume rm"; fi

fresh
run_shim status --force
if assert_exit 1 && assert_has "force is an init-only flag"; then
    ok "--force outside init is refused"
else not_ok "--force outside init is refused"; fi

# --- BLOCKER #1: --agent argument injection ------------------------------------
# The threat model is a pasted untrusted command. A crafted --agent must be a
# named refusal BEFORE any engine call, and the injected flag must never reach
# the engine argv (stub log).

fresh
run_shim status --agent 'x -e INJECTED=pwn z'
if assert_exit 1 && assert_has "is invalid" \
    && ! grep -q 'INJECTED' "$WORK/log"; then
    ok "injected --agent is refused and the flag never reaches the engine argv"
else not_ok "injected --agent is refused and the flag never reaches the engine argv"; fi

fresh
# a newline-bearing agent name — the other half of the injection class
run_shim status --agent "$(printf 'a\n-e X=1')"
if assert_exit 1 && assert_has "is invalid" && ! grep -q 'X=1' "$WORK/log"; then
    ok "newline in --agent is refused, nothing injected"
else not_ok "newline in --agent is refused, nothing injected"; fi

fresh
run_shim status --agent -e
if assert_exit 1 && assert_has "is invalid"; then
    ok "a --agent that looks like a flag is refused"
else not_ok "a --agent that looks like a flag is refused"; fi

fresh
STUB_CONTAINERS="aaa1;rustok=wallet;rustok.agent=my-agent_2;image=img"
run_shim status --agent my-agent_2
if assert_exit 0 && assert_has "my-agent_2"; then
    ok "a valid --agent (letters, digits, - and _) is accepted"
else not_ok "a valid --agent (letters, digits, - and _) is accepted"; fi

# --- start / stop ---------------------------------------------------------------

fresh
run_shim start
if assert_exit 1 && assert_has "no stored keyring password for agent 'claude'" \
    && assert_has "rustok init"; then
    ok "start without init: named error pointing at init"
else not_ok "start without init: named error pointing at init"; fi

fresh
printf '%s' pw >"$WORK/state/secret-rustok-keyring-claude"
: >"$WORK/state/volume-rustok-wallet-tui"
export RUSTOK_RPC_URLS_1="https://rpc.example/with-key"
export RUSTOK_KEYRING_PASSWORD="sneaky-env-password"
run_shim start
unset RUSTOK_RPC_URLS_1 RUSTOK_KEYRING_PASSWORD
if assert_exit 0 && assert_has "starting in the background" \
    && grep -q -- '--label rustok=wallet --label rustok.agent=claude' "$WORK/log" \
    && grep -q -- '--secret rustok-keyring-claude,type=env,target=RUSTOK_KEYRING_PASSWORD' "$WORK/log" \
    && grep -q -- '-e RUSTOK_RPC_URLS_1 ' "$WORK/log" \
    && ! grep -q 'with-key' "$WORK/log" \
    && ! grep -qE -- '-e RUSTOK_KEYRING_PASSWORD|KEYRING_PASSWORD=|sneaky' "$WORK/log"; then
    ok "start: labeled detached run, secret delivery, RPC by NAME only, keyring env never forwarded"
else not_ok "start: labeled detached run, secret delivery, RPC by NAME only, keyring env never forwarded"; fi

fresh
printf '%s' pw >"$WORK/state/secret-rustok-keyring-claude"
: >"$WORK/state/volume-rustok-wallet-tui"
run_shim start
run_shim start
if assert_exit 1 && assert_has "already running"; then
    ok "second start refuses: already running"
else not_ok "second start refuses: already running"; fi

fresh
STUB_CONTAINERS="aaa1;rustok=wallet;rustok.agent=claude;image=img"
run_shim stop
if assert_exit 0 && assert_has "wallet stopped" && grep -q '^podman stop aaa1' "$WORK/log"; then
    ok "stop stops the single running wallet"
else not_ok "stop stops the single running wallet"; fi

fresh
run_shim stop
if assert_exit 0 && assert_has "nothing to stop"; then
    ok "stop with nothing running says so"
else not_ok "stop with nothing running says so"; fi

# --- console exec-or-start (epic pain #6) ----------------------------------------

fresh
printf '%s' pw >"$WORK/state/secret-rustok-keyring-claude"
: >"$WORK/state/volume-rustok-wallet-tui"
run_shim console
if assert_exit 0 && assert_has "starting in the background" && assert_has "EXEC:" \
    && assert_has ":rustok-console" && grep -q 'run -d' "$WORK/log"; then
    ok "console with initialized-but-stopped wallet: starts it, then execs the console"
else not_ok "console with initialized-but-stopped wallet: starts it, then execs the console"; fi

fresh
run_shim console
if assert_exit 1 && assert_has "no wallet running" && assert_has "rustok init"; then
    ok "console with nothing initialized points at init"
else not_ok "console with nothing initialized points at init"; fi

# --- docker parity: init stores a 0600 file, not a podman secret -----------------

fresh
plant_docker_stub
remove_podman_stub
mkdir -p "$WORK/home/.config/rustok"
echo "engine=docker" >"$WORK/home/.config/rustok/config"
run_init_pty "$PW_QUOTED" "$PW_QUOTED"
PWFILE="$WORK/home/.config/rustok/keyring-pass-claude"
if assert_exit 0 && [ -f "$PWFILE" ] \
    && [ "$(cat "$PWFILE")" = "$PW_QUOTED" ] \
    && [ "$(stat -c '%a' "$PWFILE")" = "600" ] \
    && ! grep -q 'secret create' "$WORK/log" \
    && ! grep -qF "$PW_QUOTED" "$WORK/log"; then
    ok "docker init: 0600 password file, byte-exact, no secret store, argv clean"
else not_ok "docker init: 0600 password file, byte-exact, no secret store, argv clean"; fi

# --- static invariant: init/start never destroy keystore volumes ------------------

N=$((N + 1))
if sed 's/^[[:space:]]*#.*//' "$SHIM" | grep -qE 'volume (rm|prune)|system prune'; then
    FAIL=$((FAIL + 1))
    echo "not ok $N - shim code never removes volumes (keystore data-safety)"
else
    PASS=$((PASS + 1))
    echo "ok $N - shim code never removes volumes (keystore data-safety)"
fi

# --- static invariant: the shim never uses --name ------------------------------

N=$((N + 1))
# Comments may EXPLAIN the fixed-name bug; code lines must never pass --name.
if sed 's/^[[:space:]]*#.*//' "$SHIM" | grep -q -- '--name'; then
    FAIL=$((FAIL + 1))
    echo "not ok $N - shim never passes --name (the fixed-name bug stays buried)"
else
    PASS=$((PASS + 1))
    echo "ok $N - shim never passes --name (the fixed-name bug stays buried)"
fi

# --- summary -------------------------------------------------------------------

echo "# $PASS passed, $FAIL failed, $N total"
[ "$FAIL" -eq 0 ]
