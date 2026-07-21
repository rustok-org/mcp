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
    for tool in sh cat sed head sort awk mkdir basename cut tr rm mv grep env sleep stty date cp; do
        ln -s "$(command -v "$tool")" "$WORK/bin/$tool"
    done
    ln -s "$TESTS_DIR/stub-bin/podman" "$WORK/bin/podman"
    STUB_CONTAINERS=""
    STUB_LEGACY=""
    STUB_INFO_FAIL=0
    STUB_PS_FAIL=0
    STUB_CLAUDE_ADD_FAIL=0
    STUB_CLAUDE_REMOVE_FAIL=0
    STUB_SECRET_LS_FAIL=0
    STUB_PULL_FAIL=0
    TEST_PATH="$WORK/bin"
}

plant_docker_stub() { ln -s "$TESTS_DIR/stub-bin/podman" "$WORK/bin/docker"; }
remove_podman_stub() { rm "$WORK/bin/podman"; }
plant_claude_stub() { ln -s "$TESTS_DIR/stub-bin/claude" "$WORK/bin/claude"; }
# jq is a host tool (like python3 for the pty driver): planted per-test so its
# ABSENCE stays a testable state, not an accident of the machine.
plant_jq() { ln -s "$(command -v jq)" "$WORK/bin/jq"; }
plant_python3() { ln -s "$(command -v python3)" "$WORK/bin/python3"; }
seed_wallet() {
    printf '%s' pw >"$WORK/state/secret-rustok-keyring-claude"
    : >"$WORK/state/volume-rustok-wallet-tui"
}

run_shim() {
    # run_shim <args…> — capture stdout+stderr and exit code, stub-injected.
    # stdin is ALWAYS /dev/null: the pipe/agent environment is the hermetic
    # default (a dev's interactive terminal must never leak into a test —
    # the purge-refusal test would otherwise hang waiting on a real tty).
    OUT="$(HOME="$WORK/home" XDG_CONFIG_HOME="$WORK/home/.config" \
        PATH="$TEST_PATH" STUB_LOG="$WORK/log" STUB_STATE="$WORK/state" \
        STUB_CONTAINERS="$STUB_CONTAINERS" STUB_LEGACY="$STUB_LEGACY" \
        STUB_INFO_FAIL="$STUB_INFO_FAIL" STUB_PS_FAIL="$STUB_PS_FAIL" \
        STUB_CLAUDE_ADD_FAIL="$STUB_CLAUDE_ADD_FAIL" \
        STUB_CLAUDE_REMOVE_FAIL="$STUB_CLAUDE_REMOVE_FAIL" \
        STUB_SECRET_LS_FAIL="$STUB_SECRET_LS_FAIL" \
        STUB_PULL_FAIL="$STUB_PULL_FAIL" \
        sh "$SHIM" "$@" </dev/null 2>&1)" && RC=0 || RC=$?
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

count_secrets() { set -- "$WORK/state"/secret-*; [ -e "$1" ] && echo $# || echo 0; }
count_volumes() { set -- "$WORK/state"/volume-*; [ -e "$1" ] && echo $# || echo 0; }

run_purge_pty() {
    # run_purge_pty <confirmation-line> — drives `uninstall --purge-keys` on a
    # real pty (the /dev/tty confirmation gate), feeding the one literal a
    # human would type at the "confirm: " prompt.
    OUT="$(printf '%s\n' "$1" | \
        HOME="$WORK/home" XDG_CONFIG_HOME="$WORK/home/.config" \
        PATH="$TEST_PATH" STUB_LOG="$WORK/log" STUB_STATE="$WORK/state" \
        STUB_CONTAINERS="$STUB_CONTAINERS" STUB_LEGACY="$STUB_LEGACY" \
        STUB_INFO_FAIL="$STUB_INFO_FAIL" STUB_PS_FAIL="$STUB_PS_FAIL" \
        STUB_CLAUDE_ADD_FAIL="$STUB_CLAUDE_ADD_FAIL" \
        STUB_CLAUDE_REMOVE_FAIL="$STUB_CLAUDE_REMOVE_FAIL" \
        STUB_PULL_FAIL="$STUB_PULL_FAIL" \
        "$PY3" "$TESTS_DIR/pty-init.py" sh "$SHIM" uninstall --purge-keys 2>&1)" && RC=0 || RC=$?
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
if assert_exit 0 && assert_has "RUSTOK_RPC_URLS" && assert_has "connect" \
    && assert_has "secret" && assert_not_has "until"; then
    ok "help documents secret-based RPC delivery — the inspect-visibility interim is CLOSED"
else not_ok "help documents secret-based RPC delivery — the inspect-visibility interim is CLOSED"; fi

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
STUB_CONTAINERS="abc123def456;rustok=wallet;rustok.agent=claude;image=ghcr.io/rustok-org/rustok-wallet-tui:v0.8.0"
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
if assert_exit 1 && assert_has "force is an init/connect-only flag"; then
    ok "--force outside init/connect is refused"
else not_ok "--force outside init/connect is refused"; fi

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

# --- start + RPC secrets: the inspect-visibility interim is CLOSED ---------------

fresh
seed_wallet
printf '%s' 'stored-url' >"$WORK/state/secret-rustok-rpc-claude-1"
export RUSTOK_RPC_URLS_1="https://rpc.example/with-key"
run_shim start
unset RUSTOK_RPC_URLS_1
if assert_exit 0 \
    && grep -q -- '--secret rustok-rpc-claude-1,type=env,target=RUSTOK_RPC_URLS_1' "$WORK/log" \
    && ! grep -q -- '-e RUSTOK_RPC_URLS_1 ' "$WORK/log" \
    && ! grep -q 'with-key' "$WORK/log"; then
    ok "start with an RPC secret delivers via the secret, drops the name-forward (interim closed)"
else not_ok "start with an RPC secret delivers via the secret, drops the name-forward (interim closed)"; fi

# --- connect: registration through the agent config ------------------------------
# The trust rules: existence probe reads $HOME/.claude.json (jq, read-only) —
# never `claude mcp get`/`list`, which health-check and START a wallet container
# on the shared keystore just to answer a question. Writes go through the CLI.

fresh
plant_claude_stub
plant_jq
seed_wallet
export RUSTOK_RPC_URLS_1="https://rpc.example/with-key"
export RUSTOK_ALLOWED_CHAINS="1"
run_shim connect claude
unset RUSTOK_RPC_URLS_1 RUSTOK_ALLOWED_CHAINS
EXPECTED="claude mcp add -s user rustok -- podman run -i --rm --init --label rustok=wallet --label rustok.agent=claude -v rustok-wallet-tui:/data --secret rustok-keyring-claude,type=env,target=RUSTOK_KEYRING_PASSWORD --secret rustok-rpc-claude-1,type=env,target=RUSTOK_RPC_URLS_1 -e RUSTOK_ALLOWED_CHAINS=1 ghcr.io/rustok-org/rustok-wallet-tui:v0.8.0"
if assert_exit 0 \
    && [ "$(grep '^claude mcp add' "$WORK/log")" = "$EXPECTED" ] \
    && [ "$(cat "$WORK/state/secret-rustok-rpc-claude-1")" = "https://rpc.example/with-key" ]; then
    ok "connect: registration argv is byte-exact (labels, volume, both secrets, frozen -e, image)"
else RC="$RC (log: $(grep '^claude' "$WORK/log" || echo none))"; not_ok "connect: registration argv is byte-exact (labels, volume, both secrets, frozen -e, image)"; fi

fresh
plant_claude_stub
plant_jq
seed_wallet
# shellcheck disable=SC2016,SC2089,SC2090  # literal quotes/$ in the URL are the point: byte-exactness probe
RPCV='https://u:p@rpc.example/?key=a"b$c&d'
export RUSTOK_RPC_URLS_1="$RPCV"
run_shim connect claude
unset RUSTOK_RPC_URLS_1
if assert_exit 0 \
    && [ "$(cat "$WORK/state/secret-rustok-rpc-claude-1")" = "$RPCV" ] \
    && grep -q 'secret create --replace rustok-rpc-claude-1' "$WORK/log" \
    && ! grep -q 'secret rm ' "$WORK/log" \
    && ! grep -qF "$RPCV" "$WORK/log"; then
    ok "connect: RPC secret byte-exact via --replace, value never in any argv, no secret rm anywhere"
else not_ok "connect: RPC secret byte-exact via --replace, value never in any argv, no secret rm anywhere"; fi

fresh
plant_claude_stub
plant_jq
run_shim connect claude
if assert_exit 1 && assert_has "run: rustok init" && ! grep -q '^claude' "$WORK/log"; then
    ok "connect on a blank machine points at init, no registration attempted"
else not_ok "connect on a blank machine points at init, no registration attempted"; fi

fresh
plant_claude_stub
plant_jq
: >"$WORK/state/volume-rustok-wallet-tui"
run_shim connect claude
if assert_exit 1 && assert_has "env-file-era" && assert_has "rustok init --force" \
    && ! grep -q '^claude' "$WORK/log"; then
    ok "connect over a volume without a stored secret prints the migration path (Blocker-1)"
else not_ok "connect over a volume without a stored secret prints the migration path (Blocker-1)"; fi

fresh
plant_claude_stub
plant_jq
seed_wallet
printf '%s' '{"mcpServers":{"rustok":{"command":"podman","args":["run"]}}}' >"$WORK/home/.claude.json"
run_shim connect claude
if assert_exit 1 && assert_has "already registered" && assert_has "--force" \
    && ! grep -q '^claude mcp' "$WORK/log"; then
    ok "connect over an existing registration refuses without --force"
else not_ok "connect over an existing registration refuses without --force"; fi

fresh
plant_claude_stub
plant_jq
seed_wallet
printf '%s' '{"mcpServers":{"rustok":{"command":"podman","args":["run","--env-file","/x/wallet.env"]}}}' >"$WORK/home/.claude.json"
# shellcheck disable=SC2090  # false positive: the var NAME is tainted by the byte-exactness probe above
export RUSTOK_RPC_URLS_1="url"
run_shim connect claude --force
unset RUSTOK_RPC_URLS_1
n_sec="$(grep -n 'secret create --replace' "$WORK/log" | head -n 1 | cut -d: -f1)"
n_rm="$(grep -n '^claude mcp remove -s user rustok$' "$WORK/log" | head -n 1 | cut -d: -f1)"
n_add="$(grep -n '^claude mcp add' "$WORK/log" | head -n 1 | cut -d: -f1)"
if assert_exit 0 && [ -n "$n_sec" ] && [ -n "$n_rm" ] && [ -n "$n_add" ] \
    && [ "$n_sec" -lt "$n_rm" ] && [ "$n_rm" -lt "$n_add" ] \
    && assert_has "env-file registration"; then
    ok "connect --force: secrets first, then remove, then add; env-file replacement is announced"
else not_ok "connect --force: secrets first, then remove, then add; env-file replacement is announced"; fi

fresh
plant_claude_stub
plant_jq
seed_wallet
# no .claude.json at all (jq exit 2) — the fresh-machine path this epic exists for
run_shim connect claude
if assert_exit 0 && grep -q '^claude mcp add' "$WORK/log"; then
    ok "connect with no agent config file yet proceeds (fresh machine = free)"
else not_ok "connect with no agent config file yet proceeds (fresh machine = free)"; fi

fresh
plant_claude_stub
plant_jq
seed_wallet
printf '%s' '{"mcpServers":{' >"$WORK/home/.claude.json"
run_shim connect claude
if assert_exit 1 && assert_has "broken JSON" && ! grep -q '^claude' "$WORK/log"; then
    ok "connect over a broken agent config: named refusal, nothing written"
else not_ok "connect over a broken agent config: named refusal, nothing written"; fi

fresh
plant_claude_stub
seed_wallet
# jq deliberately NOT planted
run_shim connect claude
if assert_exit 1 && assert_has "connect needs jq" && ! grep -q '^claude' "$WORK/log"; then
    ok "connect without jq: named refusal before any engine or claude call"
else not_ok "connect without jq: named refusal before any engine or claude call"; fi

fresh
plant_claude_stub
plant_jq
seed_wallet
# a live-machine-shaped container: on the keystore volume, NO rustok.agent label
STUB_CONTAINERS="livec1;rustok=wallet;volume=rustok-wallet-tui;image=img"
run_shim connect claude
if assert_exit 0 && assert_has "1 container(s) already use keystore volume 'rustok-wallet-tui'" \
    && assert_has "UNVERIFIED"; then
    ok "connect warns by VOLUME about containers sharing the keystore (agent-label-blind)"
else not_ok "connect warns by VOLUME about containers sharing the keystore (agent-label-blind)"; fi

fresh
run_shim connect vscode
if assert_exit 2 && assert_has "unknown connect target 'vscode'"; then
    ok "connect with an unknown target: named refusal listing the supported set"
else not_ok "connect with an unknown target: named refusal listing the supported set"; fi

fresh
run_shim connect
if assert_exit 2 && assert_has "connect needs a target"; then
    ok "connect without a target: named usage error"
else not_ok "connect without a target: named usage error"; fi

fresh
plant_claude_stub
plant_jq
seed_wallet
printf '%s' '{"mcpServers":{"rustok-wallet-tui":{"command":"podman","args":[]}}}' >"$WORK/home/.claude.json"
run_shim connect claude
if assert_exit 0 && assert_has "doc-era" \
    && assert_has "claude mcp remove -s user rustok-wallet-tui"; then
    ok "connect warns about a doc-era rustok-wallet-tui entry with the removal command"
else not_ok "connect warns about a doc-era rustok-wallet-tui entry with the removal command"; fi

fresh
plant_claude_stub
plant_jq
plant_docker_stub
remove_podman_stub
mkdir -p "$WORK/home/.config/rustok"
echo "engine=docker" >"$WORK/home/.config/rustok/config"
printf '%s' pw >"$WORK/home/.config/rustok/keyring-pass-claude"
: >"$WORK/state/volume-rustok-wallet-tui"
export RUSTOK_RPC_URLS_1="https://rpc.example/with-key"
run_shim connect claude
unset RUSTOK_RPC_URLS_1
ADD_LINE="$(grep '^claude mcp add' "$WORK/log" || echo none)"
if assert_exit 0 \
    && case "$ADD_LINE" in *"docker run -i --rm --init"*) true ;; *) false ;; esac \
    && case "$ADD_LINE" in *"-e RUSTOK_RPC_URLS_1=https://rpc.example/with-key"*) true ;; *) false ;; esac \
    && case "$ADD_LINE" in *"keyring-pass-claude:/run/keyring-pass:ro -e RUSTOK_KEYRING_PASSWORD_FILE=/run/keyring-pass"*) true ;; *) false ;; esac \
    && assert_has "second tier"; then
    ok "connect on docker: _FILE keyring mount, RPC as honest bare -e, tier note printed"
else not_ok "connect on docker: _FILE keyring mount, RPC as honest bare -e, tier note printed"; fi

fresh
plant_claude_stub
plant_jq
seed_wallet
STUB_CLAUDE_ADD_FAIL=1
run_shim connect claude
if assert_exit 1 && assert_has "re-run it manually" \
    && assert_has "claude mcp add -s user rustok"; then
    ok "connect surfaces a failed mcp add with the exact retry command"
else not_ok "connect surfaces a failed mcp add with the exact retry command"; fi

fresh
plant_claude_stub
plant_jq
seed_wallet
printf '%s' '{"mcpServers":{"rustok":{"command":"podman","args":["run"]}}}' >"$WORK/home/.claude.json"
STUB_CLAUDE_REMOVE_FAIL=1
run_shim connect claude --force
if assert_exit 1 && assert_has "registration left unchanged" \
    && ! grep -q '^claude mcp add' "$WORK/log"; then
    ok "connect --force with a failing mcp remove dies named, never runs add"
else not_ok "connect --force with a failing mcp remove dies named, never runs add"; fi

fresh
plant_claude_stub
plant_jq
seed_wallet
# a FOREIGN agent's secret sharing the hyphenated prefix: claude-backup is a
# valid --agent name, its secrets must NEVER leak into claude's container
printf '%s' 'foreign-url' >"$WORK/state/secret-rustok-rpc-claude-backup-1"
run_shim connect claude
if assert_exit 0 \
    && ! grep -q 'claude-backup' "$WORK/log"; then
    ok "connect for claude never attaches claude-backup's RPC secret (prefix isolation)"
else not_ok "connect for claude never attaches claude-backup's RPC secret (prefix isolation)"; fi

fresh
plant_claude_stub
plant_jq
seed_wallet
# THREE literals exported as the permutation C,N,A — unsorted BOTH as-is
# (dash environ = insertion order) and reversed (bash rebuilds environ in
# reverse) — so on either shell only the shim's own LC_ALL=C sort can
# produce the expected argv; dropping the sort goes red, not lucky-green.
# (A 2-name set cannot do this: the reverse of an unsorted pair is sorted.)
export RUSTOK_RPC_URLS_8453="url-base"
export RUSTOK_RPC_URLS_1="url-one"
export RUSTOK_CHAIN_LABELS="mainnet,base"
export RUSTOK_NETWORK_MODE="live"
export RUSTOK_ALLOWED_CHAINS="1,8453"
run_shim connect claude
unset RUSTOK_RPC_URLS_1 RUSTOK_RPC_URLS_8453 RUSTOK_ALLOWED_CHAINS RUSTOK_CHAIN_LABELS RUSTOK_NETWORK_MODE
EXPECTED="claude mcp add -s user rustok -- podman run -i --rm --init --label rustok=wallet --label rustok.agent=claude -v rustok-wallet-tui:/data --secret rustok-keyring-claude,type=env,target=RUSTOK_KEYRING_PASSWORD --secret rustok-rpc-claude-1,type=env,target=RUSTOK_RPC_URLS_1 --secret rustok-rpc-claude-8453,type=env,target=RUSTOK_RPC_URLS_8453 -e RUSTOK_ALLOWED_CHAINS=1,8453 -e RUSTOK_CHAIN_LABELS=mainnet,base -e RUSTOK_NETWORK_MODE=live ghcr.io/rustok-org/rustok-wallet-tui:v0.8.0"
if assert_exit 0 && [ "$(grep '^claude mcp add' "$WORK/log")" = "$EXPECTED" ]; then
    ok "connect with two chains and three literals: full argv byte-exact in sorted order"
else not_ok "connect with two chains and three literals: full argv byte-exact in sorted order"; fi

fresh
plant_claude_stub
plant_jq
seed_wallet
printf '%s' '{"mcpServers":{"rustok":{"command":"podman","args":["run"]}}}' >"$WORK/home/.claude.json"
# the secret EXISTS but its env var is NOT exported this run — spec decision #3:
# the secret store is the source of truth, the registration must still carry it
printf '%s' 'stored-url' >"$WORK/state/secret-rustok-rpc-claude-1"
run_shim connect claude --force
if assert_exit 0 \
    && grep '^claude mcp add' "$WORK/log" | grep -q -- '--secret rustok-rpc-claude-1,type=env,target=RUSTOK_RPC_URLS_1'; then
    ok "connect --force keeps a stored RPC secret in the registration without its env var"
else not_ok "connect --force keeps a stored RPC secret in the registration without its env var"; fi

# --- guard tests for the load-bearing preflights (Gate-2 round-2 gaps) -----------

fresh
plant_claude_stub
plant_jq
# secret present but NO volume — reachable state: init stores the secret BEFORE
# create-wallet registers the volume, and this machine has already proven that
# a power cut can land between any two steps
printf '%s' pw >"$WORK/state/secret-rustok-keyring-claude"
run_shim connect claude
if assert_exit 1 && assert_has "no wallet volume 'rustok-wallet-tui'" \
    && assert_has "rustok init" && ! grep -q '^claude' "$WORK/log"; then
    ok "connect with a secret but no volume: named error, no registration"
else not_ok "connect with a secret but no volume: named error, no registration"; fi

fresh
plant_claude_stub
plant_jq
plant_docker_stub
remove_podman_stub
mkdir -p "$WORK/home/.config/rustok"
echo "engine=docker" >"$WORK/home/.config/rustok/config"
printf '%s' pw >"$WORK/home/.config/rustok/keyring-pass-claude"
: >"$WORK/state/volume-rustok-wallet-tui"
# a leftover podman-era rpc secret FILE in the store: the docker tier must not
# see the secret channel at all — dropping the engine gate would double-deliver
printf '%s' 'stored-url' >"$WORK/state/secret-rustok-rpc-claude-1"
export RUSTOK_RPC_URLS_1="https://rpc.example/with-key"
run_shim connect claude
unset RUSTOK_RPC_URLS_1
ADD_LINE="$(grep '^claude mcp add' "$WORK/log" || echo none)"
if assert_exit 0 \
    && case "$ADD_LINE" in *"--secret rustok-rpc-"*) false ;; *) true ;; esac \
    && case "$ADD_LINE" in *"-e RUSTOK_RPC_URLS_1=https://rpc.example/with-key"*) true ;; *) false ;; esac; then
    ok "docker tier never rides the podman secret channel, even with a stored rpc secret"
else not_ok "docker tier never rides the podman secret channel, even with a stored rpc secret"; fi

fresh
plant_claude_stub
plant_jq
seed_wallet
# TWO wallets on DIFFERENT volumes: the warn must count by the TARGET volume
# only — a dropped/typoed filter would count both (or none)
STUB_CONTAINERS="livec1;rustok=wallet;volume=rustok-wallet-tui;image=img otherc2;rustok=wallet;volume=rustok-hermes;image=img"
run_shim connect claude
if assert_exit 0 && assert_has "1 container(s) already use keystore volume 'rustok-wallet-tui'" \
    && assert_not_has "2 container(s)"; then
    ok "multiplicity warn counts only the target volume's containers (filter is live)"
else not_ok "multiplicity warn counts only the target volume's containers (filter is live)"; fi

fresh
plant_claude_stub
plant_jq
seed_wallet
STUB_SECRET_LS_FAIL=1
run_shim connect claude
if assert_exit 1 && assert_has "failed listing secrets" \
    && ! grep -q '^claude mcp add' "$WORK/log"; then
    ok "connect with a failing secret ls dies named — never registers without RPC silently"
else not_ok "connect with a failing secret ls dies named — never registers without RPC silently"; fi

fresh
plant_claude_stub
plant_jq
seed_wallet
printf '%s' '{"mcpServers":{"rustok":{"command":"podman","args":["run","OLDMARKER"]}}}' >"$WORK/home/.claude.json"
STUB_CLAUDE_ADD_FAIL=1
run_shim connect claude --force
if assert_exit 1 && assert_has "NOT registered" && assert_has "OLDMARKER" \
    && assert_has "re-run it manually"; then
    ok "connect --force with a failing add says the old entry is gone and prints it back"
else not_ok "connect --force with a failing add says the old entry is gone and prints it back"; fi

# --- connect cursor: the shim writes ~/.cursor/mcp.json itself (no CLI exists) ---

seed_cursor() {
    printf '%s' pw >"$WORK/state/secret-rustok-keyring-cursor"
    : >"$WORK/state/volume-rustok-cursor"
}

fresh
plant_claude_stub
plant_jq
seed_cursor
export RUSTOK_RPC_URLS_1="https://rpc.example/with-key"
export RUSTOK_ALLOWED_CHAINS="1"
run_shim connect cursor
unset RUSTOK_RPC_URLS_1 RUSTOK_ALLOWED_CHAINS
CJSON="$(jq -cS '.mcpServers.rustok' "$WORK/home/.cursor/mcp.json" 2>/dev/null || echo none)"
CEXP='{"args":["run","-i","--rm","--init","--label","rustok=wallet","--label","rustok.agent=cursor","-v","rustok-cursor:/data","--secret","rustok-keyring-cursor,type=env,target=RUSTOK_KEYRING_PASSWORD","--secret","rustok-rpc-cursor-1,type=env,target=RUSTOK_RPC_URLS_1","-e","RUSTOK_ALLOWED_CHAINS=1","ghcr.io/rustok-org/rustok-wallet-tui:v0.8.0"],"command":"podman"}'
if assert_exit 0 && [ "$CJSON" = "$CEXP" ] \
    && [ "$(cat "$WORK/state/secret-rustok-rpc-cursor-1")" = "https://rpc.example/with-key" ]; then
    ok "connect cursor: entry byte-exact (default agent=cursor, own volume, leading-dash args survive)"
else RC="$RC json=$CJSON"; not_ok "connect cursor: entry byte-exact (default agent=cursor, own volume, leading-dash args survive)"; fi

fresh
plant_claude_stub
plant_jq
seed_wallet
export RUSTOK_RPC_URLS_1="https://rpc.example/with-key"
export RUSTOK_ALLOWED_CHAINS="1"
run_shim connect cursor --agent claude
unset RUSTOK_RPC_URLS_1 RUSTOK_ALLOWED_CHAINS
OJSON="$(jq -cS '.mcpServers.rustok' "$WORK/home/.cursor/mcp.json" 2>/dev/null || echo none)"
OEXP='{"args":["run","-i","--rm","--init","--label","rustok=wallet","--label","rustok.agent=claude","-v","rustok-wallet-tui:/data","--secret","rustok-keyring-claude,type=env,target=RUSTOK_KEYRING_PASSWORD","--secret","rustok-rpc-claude-1,type=env,target=RUSTOK_RPC_URLS_1","-e","RUSTOK_ALLOWED_CHAINS=1","ghcr.io/rustok-org/rustok-wallet-tui:v0.8.0"],"command":"podman"}'
if assert_exit 0 && [ "$OJSON" = "$OEXP" ] \
    && [ "$(cat "$WORK/state/secret-rustok-rpc-claude-1")" = "https://rpc.example/with-key" ]; then
    ok "connect cursor --agent claude: explicit override drives label/volume/secrets (one resolve line for all clients)"
else RC="$RC json=$OJSON"; not_ok "connect cursor --agent claude: explicit override drives label/volume/secrets (one resolve line for all clients)"; fi

fresh
plant_claude_stub
plant_jq
seed_cursor
mkdir -p "$WORK/home/.cursor"
printf '%s' '{"mcpServers":{"other":{"command":"keepme"}}}' >"$WORK/home/.cursor/mcp.json"
run_shim connect cursor
if assert_exit 0 \
    && [ "$(jq -r '.mcpServers.other.command' "$WORK/home/.cursor/mcp.json")" = "keepme" ] \
    && jq -e '.mcpServers.rustok' "$WORK/home/.cursor/mcp.json" >/dev/null; then
    ok "connect cursor preserves foreign mcpServers keys"
else not_ok "connect cursor preserves foreign mcpServers keys"; fi

fresh
plant_claude_stub
plant_jq
seed_cursor
run_shim connect cursor
if assert_exit 0 && jq -e '.mcpServers.rustok' "$WORK/home/.cursor/mcp.json" >/dev/null 2>&1; then
    ok "connect cursor creates mcp.json from nothing (fresh machine)"
else not_ok "connect cursor creates mcp.json from nothing (fresh machine)"; fi

fresh
plant_claude_stub
plant_jq
seed_cursor
mkdir -p "$WORK/home/.cursor"
printf '%s' '{"mcpServers":{"rustok":{"command":"old","args":["CURSOROLD"]}}}' >"$WORK/home/.cursor/mcp.json"
run_shim connect cursor
CUNCHANGED="$(jq -r '.mcpServers.rustok.command' "$WORK/home/.cursor/mcp.json")"
if assert_exit 1 && assert_has "already registered" && assert_has "--force" \
    && [ "$CUNCHANGED" = "old" ]; then
    ok "connect cursor over an existing entry refuses without --force, file untouched"
else not_ok "connect cursor over an existing entry refuses without --force, file untouched"; fi

fresh
plant_claude_stub
plant_jq
seed_cursor
mkdir -p "$WORK/home/.cursor"
printf '%s' '{"mcpServers":{"rustok":{"command":"old","args":["CURSOROLD"]}}}' >"$WORK/home/.cursor/mcp.json"
run_shim connect cursor --force
if assert_exit 0 && assert_has "CURSOROLD" \
    && [ "$(jq -r '.mcpServers.rustok.command' "$WORK/home/.cursor/mcp.json")" = "podman" ]; then
    ok "connect cursor --force prints the old entry back and replaces it"
else not_ok "connect cursor --force prints the old entry back and replaces it"; fi

fresh
plant_claude_stub
plant_jq
seed_cursor
mkdir -p "$WORK/home/.cursor"
printf '%s' '{"mcpServers":{' >"$WORK/home/.cursor/mcp.json"
run_shim connect cursor
if assert_exit 1 && assert_has "broken JSON" \
    && [ "$(cat "$WORK/home/.cursor/mcp.json")" = '{"mcpServers":{' ]; then
    ok "connect cursor over broken JSON: named refusal, file untouched"
else not_ok "connect cursor over broken JSON: named refusal, file untouched"; fi

fresh
plant_claude_stub
plant_jq
seed_cursor
mkdir -p "$WORK/home/.cursor"
printf '%s' '{"mcpServers":{"other":{"command":"keepme"}}}' >"$WORK/home/.cursor/mcp.json"
chmod 500 "$WORK/home/.cursor"
run_shim connect cursor
CAFTER="$(cat "$WORK/home/.cursor/mcp.json")"
chmod 755 "$WORK/home/.cursor"
if assert_exit 1 && assert_has "could not update" \
    && [ "$CAFTER" = '{"mcpServers":{"other":{"command":"keepme"}}}' ]; then
    ok "connect cursor with an unwritable dir dies named, config intact (atomic write)"
else not_ok "connect cursor with an unwritable dir dies named, config intact (atomic write)"; fi

# --- connect hermes: YAML round-trip into ~/.hermes/config.yaml -------------------

seed_hermes() {
    printf '%s' pw >"$WORK/state/secret-rustok-keyring-hermes"
    : >"$WORK/state/volume-rustok-hermes"
    mkdir -p "$WORK/home/.hermes"
    cat >"$WORK/home/.hermes/config.yaml" <<'YEOF'
model: test-model
workspace: /tmp/x
mcp_servers:
  rustok-wallet:
    command: python3
    args: ['["/home/x/wrap.py"]']
    enabled: false
  other-srv:
    command: foo
    args: [a]
channels:
  cli: on
YEOF
}

fresh
plant_claude_stub
plant_jq
plant_python3
seed_hermes
mkdir -p "$WORK/home/.hermes/scripts"
: >"$WORK/home/.hermes/scripts/rustok-mcp-server.py"
run_shim connect hermes
HCHECK="$("$PY3" - "$WORK/home/.hermes/config.yaml" <<'PEOF'
import sys, yaml
c = yaml.safe_load(open(sys.argv[1]))
r = c["mcp_servers"]["rustok"]
assert r["command"] == "podman", r
assert isinstance(r["args"], list) and r["args"][0] == "run", r
assert "rustok.agent=hermes" in r["args"] and "rustok-hermes:/data" in r["args"], r
assert r["enabled"] is True, r
assert "rustok-wallet" not in c["mcp_servers"]
assert c["mcp_servers"]["other-srv"]["command"] == "foo"
assert c["model"] == "test-model" and c["workspace"] == "/tmp/x"
assert c["channels"] == {"cli": True}
print("HOK")
PEOF
)" || HCHECK="HFAIL"
if assert_exit 0 && [ "$HCHECK" = "HOK" ] \
    && assert_has "legacy" && assert_has "rustok-mcp-server.py" \
    && ls "$WORK/home/.hermes/"config.yaml.rustok-bak-* >/dev/null 2>&1; then
    ok "connect hermes: real args list, enabled true, legacy dropped+noted, keys survive, backup made, wrapper hint"
else RC="$RC hcheck=$HCHECK"; not_ok "connect hermes: real args list, enabled true, legacy dropped+noted, keys survive, backup made, wrapper hint"; fi

fresh
plant_claude_stub
plant_jq
plant_python3
seed_hermes
"$PY3" - "$WORK/home/.hermes/config.yaml" <<'PEOF'
import sys, yaml
p = sys.argv[1]
c = yaml.safe_load(open(p))
c["mcp_servers"]["rustok"] = {"command": "old", "args": ["HERMESOLD"], "enabled": True}
yaml.safe_dump(c, open(p, "w"), sort_keys=False)
PEOF
cp "$WORK/home/.hermes/config.yaml" "$WORK/hermes-before"
run_shim connect hermes
if assert_exit 1 && assert_has "already registered" && assert_has "--force" \
    && cmp -s "$WORK/home/.hermes/config.yaml" "$WORK/hermes-before"; then
    ok "connect hermes over an existing entry refuses without --force, file untouched"
else not_ok "connect hermes over an existing entry refuses without --force, file untouched"; fi

fresh
plant_claude_stub
plant_jq
plant_python3
printf '%s' pw >"$WORK/state/secret-rustok-keyring-hermes"
: >"$WORK/state/volume-rustok-hermes"
mkdir -p "$WORK/home/.hermes"
printf 'a: [unclosed\n' >"$WORK/home/.hermes/config.yaml"
run_shim connect hermes
if assert_exit 1 && assert_has "unreadable YAML" \
    && ! ls "$WORK/home/.hermes/"config.yaml.rustok-bak-* >/dev/null 2>&1; then
    ok "connect hermes over broken YAML: named refusal, no backup, no write"
else not_ok "connect hermes over broken YAML: named refusal, no backup, no write"; fi

fresh
plant_claude_stub
plant_jq
seed_hermes
# python3 deliberately NOT planted
run_shim connect hermes
if assert_exit 1 && assert_has "needs python3"; then
    ok "connect hermes without python3: named refusal"
else not_ok "connect hermes without python3: named refusal"; fi

fresh
plant_claude_stub
plant_jq
plant_python3
printf '%s' pw >"$WORK/state/secret-rustok-keyring-hermes"
: >"$WORK/state/volume-rustok-hermes"
run_shim connect hermes
if assert_exit 1 && assert_has "is Hermes installed"; then
    ok "connect hermes without a Hermes config: named refusal"
else not_ok "connect hermes without a Hermes config: named refusal"; fi

fresh
plant_claude_stub
plant_jq
plant_python3
seed_hermes
cp "$WORK/home/.hermes/config.yaml" "$WORK/hermes-before"
chmod 500 "$WORK/home/.hermes"
run_shim connect hermes
HAFTER_OK=0
cmp -s "$WORK/home/.hermes/config.yaml" "$WORK/hermes-before" && HAFTER_OK=1
chmod 755 "$WORK/home/.hermes"
if assert_exit 1 && [ "$HAFTER_OK" = "1" ] \
    && { assert_has "cannot write backup" || assert_has "could not update"; }; then
    ok "connect hermes with an unwritable dir dies named, config intact"
else not_ok "connect hermes with an unwritable dir dies named, config intact"; fi

# --- update: pull first, then re-register every one of OUR registrations ---------

plant_all_three() {
    # A machine with all three clients registered; every entry carries a marker
    # value so the old-entry print is assertable per client, and its own
    # rustok.agent label so extraction (not the default) is what update proves.
    seed_wallet
    printf '%s' pw >"$WORK/state/secret-rustok-keyring-cursor"
    : >"$WORK/state/volume-rustok-cursor"
    printf '%s' pw >"$WORK/state/secret-rustok-keyring-hermes"
    : >"$WORK/state/volume-rustok-hermes"
    printf '%s' '{"mcpServers":{"rustok":{"command":"podman","args":["run","--label","rustok.agent=claude","CLAUDEOLD"]},"keep":{"command":"stay"}}}' >"$WORK/home/.claude.json"
    mkdir -p "$WORK/home/.cursor"
    printf '%s' '{"mcpServers":{"rustok":{"command":"podman","args":["run","--label","rustok.agent=cursor","CURSOROLD"]},"other":{"command":"keepme"}}}' >"$WORK/home/.cursor/mcp.json"
    mkdir -p "$WORK/home/.hermes"
    cat >"$WORK/home/.hermes/config.yaml" <<'YEOF'
model: test-model
mcp_servers:
  rustok:
    command: podman
    args: [run, --label, rustok.agent=hermes, HERMESOLD]
    enabled: true
  other-srv:
    command: foo
YEOF
}

fresh
plant_claude_stub
plant_jq
plant_python3
plant_all_three
run_shim update
CJSON="$(jq -cS '.mcpServers.rustok' "$WORK/home/.cursor/mcp.json" 2>/dev/null || echo none)"
CEXP='{"args":["run","-i","--rm","--init","--label","rustok=wallet","--label","rustok.agent=cursor","-v","rustok-cursor:/data","--secret","rustok-keyring-cursor,type=env,target=RUSTOK_KEYRING_PASSWORD","ghcr.io/rustok-org/rustok-wallet-tui:v0.8.0"],"command":"podman"}'
HCHECK="$("$PY3" - "$WORK/home/.hermes/config.yaml" <<'PEOF'
import sys, yaml
c = yaml.safe_load(open(sys.argv[1]))
r = c["mcp_servers"]["rustok"]
assert r["command"] == "podman" and r["args"][0] == "run", r
assert "rustok.agent=hermes" in r["args"] and "rustok-hermes:/data" in r["args"], r
assert r["enabled"] is True, r
assert c["mcp_servers"]["other-srv"]["command"] == "foo"
assert c["model"] == "test-model"
print("HOK")
PEOF
)" || HCHECK="HFAIL"
PULL_BEFORE_ADD=0
awk '/^podman pull /{p=NR} /^claude mcp add /{a=NR} END{exit !(p && a && p<a)}' "$WORK/log" && PULL_BEFORE_ADD=1
if assert_exit 0 && [ "$CJSON" = "$CEXP" ] && [ "$HCHECK" = "HOK" ] \
    && grep -q '^podman pull ghcr.io/rustok-org/rustok-wallet-tui:v0.8.0' "$WORK/log" \
    && [ "$PULL_BEFORE_ADD" = "1" ] \
    && grep -q '^claude mcp add -s user rustok -- podman run .* rustok.agent=claude .* rustok-wallet-tui:/data ' "$WORK/log" \
    && assert_has "CLAUDEOLD" && assert_has "CURSOROLD" && assert_has "HERMESOLD" \
    && assert_has "updated 3 client(s)" && assert_has "re-run the installer"; then
    ok "update: pull first, all three re-registered with their own agents, old entries printed"
else RC="$RC cjson=$CJSON hcheck=$HCHECK" && not_ok "update: pull first, all three re-registered with their own agents, old entries printed"; fi

fresh
plant_claude_stub
plant_jq
seed_wallet
mkdir -p "$WORK/home/.cursor"
printf '%s' '{"mcpServers":{"rustok":{"command":"podman","args":["run","--label","rustok.agent=claude","OVERRIDE"]}}}' >"$WORK/home/.cursor/mcp.json"
run_shim update
CJSON="$(jq -cS '.mcpServers.rustok.args' "$WORK/home/.cursor/mcp.json" 2>/dev/null || echo none)"
if assert_exit 0 && assert_has "updated 1 client(s)" \
    && printf '%s' "$CJSON" | grep -q '"rustok.agent=claude"' \
    && printf '%s' "$CJSON" | grep -q '"rustok-wallet-tui:/data"'; then
    ok "update preserves a cross-wired agent override read from the entry itself (claude volume on the cursor client)"
else RC="$RC cjson=$CJSON"; not_ok "update preserves a cross-wired agent override read from the entry itself (claude volume on the cursor client)"; fi

fresh
plant_claude_stub
plant_jq
plant_python3
plant_all_three
cp "$WORK/home/.claude.json" "$WORK/cb"
cp "$WORK/home/.cursor/mcp.json" "$WORK/mb"
cp "$WORK/home/.hermes/config.yaml" "$WORK/hb"
STUB_PULL_FAIL=1
run_shim update
if assert_exit 1 && assert_has "pull failed" \
    && cmp -s "$WORK/home/.claude.json" "$WORK/cb" \
    && cmp -s "$WORK/home/.cursor/mcp.json" "$WORK/mb" \
    && cmp -s "$WORK/home/.hermes/config.yaml" "$WORK/hb" \
    && ! grep -q '^claude mcp' "$WORK/log"; then
    ok "update with a failing pull dies named BEFORE touching any registration"
else not_ok "update with a failing pull dies named BEFORE touching any registration"; fi

fresh
plant_claude_stub
plant_jq
run_shim update
if assert_exit 0 && assert_has "nothing to update"; then
    ok "update with no registrations anywhere: honest no-op, exit 0"
else not_ok "update with no registrations anywhere: honest no-op, exit 0"; fi

fresh
plant_claude_stub
plant_jq
plant_python3
seed_hermes
"$PY3" - "$WORK/home/.hermes/config.yaml" <<'PEOF'
import sys, yaml
p = sys.argv[1]
c = yaml.safe_load(open(p))
c["mcp_servers"]["rustok"] = {"command": "podman",
    "args": ["run", "--label", "rustok.agent=hermes", "HERMESOLD"], "enabled": True}
yaml.safe_dump(c, open(p, "w"), sort_keys=False)
PEOF
mkdir -p "$WORK/home/.cursor"
printf '%s' '{"mcpServers":{"rustok":{"command":"podman","args":["run","NOAGENTMARK"]}}}' >"$WORK/home/.cursor/mcp.json"
cp "$WORK/home/.cursor/mcp.json" "$WORK/mb"
run_shim update
HOK=0
"$PY3" - "$WORK/home/.hermes/config.yaml" <<'PEOF' && HOK=1
import sys, yaml
c = yaml.safe_load(open(sys.argv[1]))
assert "rustok-hermes:/data" in c["mcp_servers"]["rustok"]["args"]
PEOF
if assert_exit 1 && assert_has "no rustok.agent" \
    && cmp -s "$WORK/home/.cursor/mcp.json" "$WORK/mb" \
    && [ "$HOK" = "1" ]; then
    ok "update: an entry without an agent label fails NAMED for that client only — the rest still update"
else not_ok "update: an entry without an agent label fails NAMED for that client only — the rest still update"; fi

fresh
plant_claude_stub
plant_jq
mkdir -p "$WORK/home/.cursor"
printf '%s' '{"mcpServers":{"rustok":{"command":"podman","args":["run","--label","rustok.agent=e;vil"]}}}' >"$WORK/home/.cursor/mcp.json"
cp "$WORK/home/.cursor/mcp.json" "$WORK/mb"
run_shim update
if assert_exit 1 && assert_has "invalid agent name" \
    && cmp -s "$WORK/home/.cursor/mcp.json" "$WORK/mb" \
    && ! grep -q 'e;vil' "$WORK/log"; then
    ok "update: a poisoned agent name in a registration is refused named — never reaches an engine argv"
else not_ok "update: a poisoned agent name in a registration is refused named — never reaches an engine argv"; fi

fresh
run_shim update --agent claude
if assert_exit 1 && assert_has "agent is not a"; then
    ok "update --agent: named refusal (update follows each registration's own agent)"
else not_ok "update --agent: named refusal (update follows each registration's own agent)"; fi

# --- old-entry print on replace: ONE recovery path across all three writers ------

fresh
plant_claude_stub
plant_jq
seed_wallet
printf '%s' '{"mcpServers":{"rustok":{"command":"podman","args":["CLAUDEOLD"]}}}' >"$WORK/home/.claude.json"
run_shim connect claude --force
if assert_exit 0 && assert_has "replacing the previous entry" && assert_has "CLAUDEOLD"; then
    ok "connect claude --force prints the old entry on a SUCCESSFUL replace (not only on a failed add)"
else not_ok "connect claude --force prints the old entry on a SUCCESSFUL replace (not only on a failed add)"; fi

fresh
plant_claude_stub
plant_jq
plant_python3
seed_hermes
"$PY3" - "$WORK/home/.hermes/config.yaml" <<'PEOF'
import sys, yaml
p = sys.argv[1]
c = yaml.safe_load(open(p))
c["mcp_servers"]["rustok"] = {"command": "old", "args": ["HERMESOLD"], "enabled": True}
yaml.safe_dump(c, open(p, "w"), sort_keys=False)
PEOF
run_shim connect hermes --force
if assert_exit 0 && assert_has "replacing the previous entry" && assert_has "HERMESOLD"; then
    ok "connect hermes --force prints the old entry on replace (Gate-1 finding: parity with claude/cursor)"
else not_ok "connect hermes --force prints the old entry on replace (Gate-1 finding: parity with claude/cursor)"; fi

# --- uninstall: data-safe teardown; keystore volumes only behind the double gate --

plant_uninstall_world() {
    plant_all_three
    printf '%s' "https://rpc.example/with-key" >"$WORK/state/secret-rustok-rpc-claude-1"
    STUB_CONTAINERS="cafe01;rustok=wallet;rustok.agent=claude;volume=rustok-wallet-tui;image=stub-img"
    mkdir -p "$WORK/home/.local/bin"
    printf '#!/bin/sh\n' >"$WORK/home/.local/bin/rustok"
    cat >"$WORK/home/.bashrc" <<'BEOF'
alias keepme1='true'
# >>> rustok installer >>>
export PATH="$HOME/.local/bin:$PATH"
# <<< rustok installer <<<
alias keepme2='true'
BEOF
}

fresh
plant_claude_stub
plant_jq
plant_python3
plant_uninstall_world
run_shim uninstall
CKEEP="$(jq -r '.mcpServers.keep.command' "$WORK/home/.claude.json" 2>/dev/null || echo none)"
CGONE="$(jq -r '.mcpServers | has("rustok")' "$WORK/home/.cursor/mcp.json" 2>/dev/null || echo err)"
COTHER="$(jq -r '.mcpServers.other.command' "$WORK/home/.cursor/mcp.json" 2>/dev/null || echo none)"
HOK=0
"$PY3" - "$WORK/home/.hermes/config.yaml" <<'PEOF' && HOK=1
import sys, yaml
c = yaml.safe_load(open(sys.argv[1]))
assert "rustok" not in c["mcp_servers"], c
assert c["mcp_servers"]["other-srv"]["command"] == "foo"
assert c["model"] == "test-model"
PEOF
SECRETS_LEFT="$(count_secrets)"
VOLUMES_LEFT="$(count_volumes)"
if assert_exit 0 \
    && grep -q '^claude mcp remove -s user rustok' "$WORK/log" \
    && [ "$CKEEP" = "stay" ] && [ "$CGONE" = "false" ] && [ "$COTHER" = "keepme" ] \
    && [ "$HOK" = "1" ] \
    && grep -q '^podman stop cafe01' "$WORK/log" \
    && [ "$SECRETS_LEFT" = "0" ] && [ "$VOLUMES_LEFT" = "3" ] \
    && assert_has "keys intact" \
    && grep -q "keepme1" "$WORK/home/.bashrc" && grep -q "keepme2" "$WORK/home/.bashrc" \
    && ! grep -q "rustok installer" "$WORK/home/.bashrc" \
    && [ ! -f "$WORK/home/.local/bin/rustok" ] \
    && [ ! -d "$WORK/home/.config/rustok" ]; then
    ok "uninstall: deregisters all three (foreign keys intact), stops wallets, removes secrets+PATH-block+shim+config — volumes UNTOUCHED, keys-intact printed"
else RC="$RC ckeep=$CKEEP cgone=$CGONE hok=$HOK sl=$SECRETS_LEFT vl=$VOLUMES_LEFT"; not_ok "uninstall: deregisters all three (foreign keys intact), stops wallets, removes secrets+PATH-block+shim+config — volumes UNTOUCHED, keys-intact printed"; fi

fresh
plant_claude_stub
plant_jq
plant_python3
plant_uninstall_world
run_shim uninstall --purge-keys
VOLUMES_LEFT="$(count_volumes)"
if assert_exit 1 && assert_has "terminal" && [ "$VOLUMES_LEFT" = "3" ]; then
    ok "uninstall --purge-keys through a pipe: named refusal, volumes intact (Rule of two windows)"
else RC="$RC vl=$VOLUMES_LEFT"; not_ok "uninstall --purge-keys through a pipe: named refusal, volumes intact (Rule of two windows)"; fi

fresh
plant_claude_stub
plant_jq
plant_python3
plant_uninstall_world
run_purge_pty "not the literal"
VOLUMES_LEFT="$(count_volumes)"
if assert_exit 1 && assert_has "confirmation mismatch" && [ "$VOLUMES_LEFT" = "3" ]; then
    ok "uninstall --purge-keys with a wrong confirmation: named refusal, volumes intact"
else RC="$RC vl=$VOLUMES_LEFT"; not_ok "uninstall --purge-keys with a wrong confirmation: named refusal, volumes intact"; fi

fresh
plant_claude_stub
plant_jq
plant_python3
plant_uninstall_world
run_purge_pty "delete my keys"
VOLUMES_LEFT="$(count_volumes)"
if assert_exit 0 && [ "$VOLUMES_LEFT" = "0" ] \
    && grep -q '^podman volume rm' "$WORK/log" \
    && assert_has "destroys the keys"; then
    ok "uninstall --purge-keys with the exact literal removes the keystore volumes (the ONE gated path)"
else RC="$RC vl=$VOLUMES_LEFT"; not_ok "uninstall --purge-keys with the exact literal removes the keystore volumes (the ONE gated path)"; fi

fresh
plant_claude_stub
plant_jq
plant_python3
plant_uninstall_world
# A twice-pasted installer block: two starts before one end. sed's range does
# not re-arm, so a blind delete would eat the user line between the starts.
cat >"$WORK/home/.bashrc" <<'BEOF'
alias keepme1='true'
# >>> rustok installer >>>
export PATH="$HOME/.local/bin:$PATH"
alias between='survives'
# >>> rustok installer >>>
export PATH="$HOME/.local/bin:$PATH"
# <<< rustok installer <<<
alias keepme2='true'
BEOF
run_shim uninstall
if assert_exit 0 && assert_has "expected exactly one pair" \
    && grep -q "alias between='survives'" "$WORK/home/.bashrc" \
    && grep -q "rustok installer" "$WORK/home/.bashrc"; then
    ok "uninstall refuses to edit a profile with duplicate installer markers — no silent data loss between the starts"
else not_ok "uninstall refuses to edit a profile with duplicate installer markers — no silent data loss between the starts"; fi

fresh
run_shim status --purge-keys
if assert_exit 1 && assert_has "purge-keys is an uninstall-only flag"; then
    ok "--purge-keys outside uninstall: named refusal"
else not_ok "--purge-keys outside uninstall: named refusal"; fi

fresh
run_shim uninstall --agent claude
if assert_exit 1 && assert_has "agent is not a"; then
    ok "uninstall --agent: named refusal (uninstall covers every agent)"
else not_ok "uninstall --agent: named refusal (uninstall covers every agent)"; fi

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
# PR-2.3c evolved the absolute ban: `volume rm` is allowed EXACTLY once, inside
# cmd_uninstall's doubly-gated purge block. A second call-site, or any prune,
# stays forbidden — the gate must remain the ONLY road to a keystore volume.
STRIPPED="$(sed 's/^[[:space:]]*#.*//' "$SHIM")"
VRM_TOTAL="$(printf '%s\n' "$STRIPPED" | grep -cE 'volume rm')"
VRM_IN_UNINSTALL="$(printf '%s\n' "$STRIPPED" | awk '/^cmd_uninstall\(\)/,/^}/' | grep -cE 'volume rm')"
if [ "$VRM_TOTAL" = "1" ] && [ "$VRM_IN_UNINSTALL" = "1" ] \
    && ! printf '%s\n' "$STRIPPED" | grep -qE 'volume prune|system prune'; then
    PASS=$((PASS + 1))
    echo "ok $N - volume rm appears exactly once, inside cmd_uninstall's gated purge block (no prune anywhere)"
else
    FAIL=$((FAIL + 1))
    echo "not ok $N - volume rm appears exactly once, inside cmd_uninstall's gated purge block (no prune anywhere)"
    echo "    total=$VRM_TOTAL in_uninstall=$VRM_IN_UNINSTALL"
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
