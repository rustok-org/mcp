"""Black-box release trust and client migration checks; no real credentials/network."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import shlex
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
INSTALLER = ROOT / "scripts/install.sh"
SHIM = ROOT / "cli/rustok"
COMMIT = "1111111111111111111111111111111111111111"
RUNTIME_DIGEST = "a" * 64


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def grant_args(grant: str, form: str) -> list[str]:
    literal = f"RUSTOK_MCP_CAPABILITIES={grant}"
    return {
        "short": ["-e", literal],
        "long": ["--env", literal],
        "joined_long": ["--env=" + literal],
        "joined_short": ["-e" + literal],
    }[form]


@dataclass
class Host:
    home: Path
    assets: Path
    state: Path
    log: Path
    env: dict[str, str]

    def run(self, script: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(  # noqa: S603 — fixed checkout script and fixture arguments
            ["/bin/sh", str(script), *args],
            env=self.env,
            cwd=self.assets,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )

    def install(self) -> subprocess.CompletedProcess[str]:
        return self.run(
            INSTALLER,
            "--manifest",
            str(self.assets / "release.manifest"),
            "--bundle",
            str(self.assets / "release.manifest.sigstore.json"),
        )

    def calls(self) -> str:
        return self.log.read_text() if self.log.exists() else ""

    def record(self, *, runtime: bool = False) -> None:
        text = INSTALLER.read_text()
        version = re.search(r'^WALLET_VERSION="([^"]+)"$', text, re.MULTILINE)
        digest = re.search(r'^WALLET_DIGEST="([^"]+)"$', text, re.MULTILINE)
        assert version and digest
        fields = {
            "format": "rustok-wallet-release-v1",
            "wallet_version": version[1],
            "source_commit": COMMIT,
            "image_ref": "ghcr.io/rustok-org/rustok-wallet-tui@"
            + (f"sha256:{RUNTIME_DIGEST}" if runtime else digest[1]),
            "installer_sha256": sha(INSTALLER),
            "shim_sha256": sha(SHIM),
        }
        manifest = "".join(f"{key}={value}\n" for key, value in fields.items())
        if runtime:
            path = Path(self.env["XDG_DATA_HOME"]) / "rustok/release.manifest"
            path.parent.mkdir(parents=True, exist_ok=True)
        else:
            path = self.assets / "release.manifest"
        path.write_text(manifest)


@pytest.fixture
def host(tmp_path: Path) -> Host:
    home, assets, state, bin_dir = (tmp_path / name for name in ("home", "assets", "state", "bin"))
    for path in (home, assets, state, bin_dir):
        path.mkdir()
    log = tmp_path / "calls.log"
    for tool in (
        "cat",
        "grep",
        "sed",
        "tail",
        "od",
        "tr",
        "cut",
        "mkdir",
        "rm",
        "mv",
        "cp",
        "chmod",
        "rmdir",
        "mktemp",
        "sha256sum",
        "env",
        "sort",
        "head",
        "basename",
        "date",
        "sh",
        "cmp",
        "wc",
        "uname",
    ):
        source = shutil.which(tool)
        assert source, tool
        (bin_dir / tool).symlink_to(source)
    (bin_dir / "podman").symlink_to(ROOT / "tests/shim/stub-bin/podman")
    (bin_dir / "claude").symlink_to(ROOT / "tests/shim/stub-bin/claude")
    jq = shutil.which("jq")
    assert jq
    (bin_dir / "jq").symlink_to(jq)
    cosign = bin_dir / "cosign"
    cosign.write_text(
        '#!/bin/sh\nprintf "cosign %s\\n" "$*" >> "$STUB_LOG"\n'
        'case "$1" in version) echo "GitVersion: v${STUB_COSIGN_VERSION:-3.0.3}";; '
        'verify-blob) exit "${STUB_BLOB_FAIL:-0}";; '
        'verify) exit "${STUB_OCI_FAIL:-0}";; *) exit 64;; esac\n'
    )
    cosign.chmod(0o755)
    curl = bin_dir / "curl"
    curl.write_text(
        '#!/bin/sh\nprintf "curl %s\\n" "$*" >> "$STUB_LOG"\n'
        'out=""; url=""\nwhile [ "$#" -gt 0 ]; do\n'
        'case "$1" in -o) out=$2; shift 2;; https://*) url=$1; shift;; *) shift;; esac\ndone\n'
        '[ "${STUB_CURL_FAIL:-0}" = 0 ] || exit 22\n'
        'case "$url" in */cli/rustok) cp "$STUB_SHIM_SRC" "$out";; '
        '*) cp "$STUB_RELEASE_DIR/${url##*/}" "$out";; esac\n'
    )
    curl.chmod(0o755)
    env = {
        "PATH": str(bin_dir),
        "HOME": str(home),
        "SHELL": "/bin/bash",
        "XDG_CONFIG_HOME": str(home / ".config"),
        "XDG_DATA_HOME": str(home / ".local/share"),
        "STUB_LOG": str(log),
        "STUB_STATE": str(state),
        "STUB_SHIM_SRC": str(SHIM),
        "STUB_RELEASE_DIR": str(assets),
    }
    instance = Host(home, assets, state, log, env)
    instance.record()
    (assets / "release.manifest.sigstore.json").write_text("{}\n")
    shutil.copyfile(INSTALLER, assets / "install.sh")
    for agent in ("claude", "cursor"):
        (state / f"secret-rustok-keyring-{agent}").write_text("fixture-password")
        (
            state / ("volume-rustok-wallet-tui" if agent == "claude" else f"volume-rustok-{agent}")
        ).touch()
    return instance


def test_native_platform_runner_exercises_install_and_refusals(host: Host) -> None:
    """Runner control flow only; actual signatures are checked on all native runners."""
    shutil.copyfile(SHIM, host.assets / "rustok")
    manifest_sha = sha(host.assets / "release.manifest")
    cosign = Path(host.env["PATH"]) / "cosign"
    # Fixed independent fixture identity and bytes, rather than accepting every
    # verifier call. This is a protocol stub, not cryptographic evidence.
    cosign.write_text(
        "#!/bin/sh\nset -eu\n"
        'case "$1" in\n'
        'version) echo "GitVersion: v3.0.3";;\n'
        "verify) exit 0;;\n"
        "verify-blob)\n"
        f' [ "$(sha256sum "$2" | cut -d " " -f1)" = "{manifest_sha}" ] || exit 1\n'
        " shift 2\n"
        ' while [ "$#" -gt 0 ]; do\n'
        '  case "$1" in\n'
        '   --certificate-identity) [ "$2" = '
        '"https://github.com/rustok-org/mcp/.github/workflows/release-shelf.yml@refs/tags/wallet-tui-v0.12.0" ] || exit 1; shift 2;;\n'
        '   --certificate-oidc-issuer) [ "$2" = '
        '"https://token.actions.githubusercontent.com" ] || exit 1; shift 2;;\n'
        "   *) shift;;\n"
        "  esac\n"
        " done;;\n"
        "*) exit 1;;\nesac\n"
    )
    result = host.run(ROOT / "scripts/check-wallet-platform.sh", str(host.assets), "0.12.0", COMMIT)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS native signed installation" in result.stdout
    assert "PASS native manifest/signature/hash/old-verifier refusals" in result.stdout
    assert "PASS native installed-manifest refusal" in result.stdout


@pytest.mark.parametrize(
    "defect", ["extra", "duplicate", "missing", "crlf", "nul", "hostile", "unterminated"]
)
def test_invalid_manifest_has_no_persistent_effect(host: Host, defect: str) -> None:
    path = host.assets / "release.manifest"
    data = path.read_bytes()
    if defect == "extra":
        data += b"unrecognized=1\n"
    elif defect == "duplicate":
        data += b"format=rustok-wallet-release-v1\n"
    elif defect == "missing":
        data = b"\n".join(data.split(b"\n")[1:])
    elif defect == "crlf":
        data = data.replace(b"\n", b"\r\n")
    elif defect == "nul":
        data = data.replace(b"format=", b"format=\x00")
    elif defect == "hostile":
        data = data.replace(COMMIT.encode(), b"$(touch compromised)")
    else:
        data = data.rstrip(b"\n")
    path.write_bytes(data)
    result = host.install()
    assert result.returncode != 0, result.stdout + result.stderr
    assert not host.calls()
    assert not (host.home / ".local").exists()
    assert not (host.home / ".bashrc").exists()


@pytest.mark.parametrize("failure", ["blob", "oci", "missing", "broken", "old"])
def test_signature_verifier_failure_never_pulls_or_installs(host: Host, failure: str) -> None:
    if failure == "blob":
        host.env["STUB_BLOB_FAIL"] = "1"
    elif failure == "oci":
        host.env["STUB_OCI_FAIL"] = "1"
    elif failure == "old":
        host.env["STUB_COSIGN_VERSION"] = "2.4.0"
    else:
        verifier = Path(host.env["PATH"]) / "cosign"
        verifier.unlink()
        if failure == "broken":
            verifier.write_text("#!/bin/sh\nexit 126\n")
            verifier.chmod(0o755)
    result = host.install()
    assert result.returncode != 0
    assert "podman pull" not in host.calls()
    assert not (host.home / ".local").exists()


def test_signed_install_commits_manifest_and_immutable_runtime(host: Host) -> None:
    result = host.install()
    assert result.returncode == 0, result.stdout + result.stderr
    record = host.home / ".local/share/rustok/release.manifest"
    assert record.read_bytes() == (host.assets / "release.manifest").read_bytes()
    assert sha(host.home / ".local/bin/rustok") == sha(SHIM)
    calls = host.calls()
    assert (
        calls.index("cosign verify-blob")
        < calls.index("cosign verify ghcr")
        < calls.index("podman pull")
    )
    assert f"/{COMMIT}/cli/rustok" in calls
    assert "release-shelf.yml@refs/tags/wallet-tui-v" in calls
    assert "wallet-publish.yml@refs/heads/main" in calls
    assert "podman run" not in calls and "secret create" not in calls


@pytest.mark.parametrize(
    "grant", [None, "none", "read_wallet,preview_tx", "execute_tx", "read_wallet,typo"]
)
@pytest.mark.parametrize("form", ["short", "long", "joined_long", "joined_short"])
def test_reconnect_preserves_explicit_grants_and_narrows_implicit(
    host: Host, grant: str | None, form: str
) -> None:
    host.record(runtime=True)
    args = ["run", "--label", "rustok.agent=claude"]
    if grant is not None:
        args += grant_args(grant, form)
    config = {
        "mcpServers": {"rustok": {"command": "podman", "args": args}, "other": {"command": "other"}}
    }
    (host.home / ".claude.json").write_text(json.dumps(config))
    host.env["RUSTOK_MCP_CAPABILITIES"] = "read_wallet,preview_tx,execute_tx"
    result = host.run(SHIM, "connect", "claude", "--force")
    assert result.returncode == 0, result.stderr
    expected = grant if grant in ("none", "read_wallet,preview_tx", "execute_tx") else "read_wallet"
    added = next(line for line in host.calls().splitlines() if line.startswith("claude mcp add"))
    assert added.count("RUSTOK_MCP_CAPABILITIES=") == 1
    assert f"RUSTOK_MCP_CAPABILITIES={expected}" in added
    assert f"@sha256:{RUNTIME_DIGEST}" in added


def test_expansion_refuses_non_tty_before_any_secret_or_registration_write(host: Host) -> None:
    host.record(runtime=True)
    host.env["RUSTOK_RPC_URLS_1"] = "https://example.test/fixture"
    result = host.run(
        SHIM, "connect", "claude", "--capabilities", "read_wallet,preview_tx,execute_tx"
    )
    assert result.returncode != 0
    assert "own terminal" in result.stderr
    assert "secret create" not in host.calls()
    assert "claude mcp add" not in host.calls()


def test_duplicate_grants_preserve_old_config(host: Host) -> None:
    host.record(runtime=True)
    path = host.home / ".claude.json"
    path.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "rustok": {
                        "args": [
                            "-e",
                            "RUSTOK_MCP_CAPABILITIES=read_wallet",
                            "-e",
                            "RUSTOK_MCP_CAPABILITIES=execute_tx",
                        ]
                    }
                }
            }
        )
    )
    before = path.read_bytes()
    result = host.run(SHIM, "connect", "claude", "--force")
    assert result.returncode != 0
    assert path.read_bytes() == before
    assert "secret create" not in host.calls()
    assert "claude mcp remove" not in host.calls()


@pytest.mark.parametrize("previous", [False, True])
def test_failure_between_atomic_commits_retains_previous_digest_or_refuses_fresh(
    host: Host, previous: bool
) -> None:
    if previous:
        host.record(runtime=True)
    record = host.home / ".local/share/rustok/release.manifest"
    old = record.read_bytes() if previous else None
    mv = Path(host.env["PATH"]) / "mv"
    mv.unlink()
    real_mv = shutil.which("mv")
    assert real_mv
    mv.write_text(
        f'#!/bin/sh\ncase "$2" in */release.manifest) exit 1;; esac\nexec "{real_mv}" "$@"\n'
    )
    mv.chmod(0o755)
    result = host.install()
    assert result.returncode != 0
    installed = host.home / ".local/bin/rustok"
    assert sha(installed) == sha(SHIM)
    if previous:
        assert record.read_bytes() == old
        assert RUNTIME_DIGEST in host.run(installed, "version").stdout
    else:
        assert not record.exists()
        assert host.run(installed, "start").returncode != 0
        assert "podman run" not in host.calls()
    assert not (record.parent / "install.lock").exists()


def test_concurrent_commit_refuses_second_installer(host: Host) -> None:
    mv = Path(host.env["PATH"]) / "mv"
    mv.unlink()
    real_mv, sleep = shutil.which("mv"), shutil.which("sleep")
    assert real_mv and sleep
    barrier = host.assets / "entered"
    release = host.assets / "continue"
    mv.write_text(
        f'#!/bin/sh\ncase "$2" in */bin/rustok) : > "{barrier}"; '
        f'while [ ! -f "{release}" ]; do "{sleep}" 0.05; done;; esac\n'
        f'exec "{real_mv}" "$@"\n'
    )
    mv.chmod(0o755)
    first = subprocess.Popen(  # noqa: S603 — fixed fixture script, no shell
        [
            "/bin/sh",
            str(INSTALLER),
            "--manifest",
            str(host.assets / "release.manifest"),
            "--bundle",
            str(host.assets / "release.manifest.sigstore.json"),
        ],
        env=host.env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        deadline = time.monotonic() + 10
        while not barrier.exists():
            assert time.monotonic() < deadline and first.poll() is None
            time.sleep(0.05)
        second = host.install()
        assert second.returncode != 0 and "installation is busy" in second.stderr
    finally:
        release.touch()
        stdout, stderr = first.communicate(timeout=10)
    assert first.returncode == 0, stdout + stderr
    assert (host.home / ".local/share/rustok/release.manifest").read_bytes() == (
        host.assets / "release.manifest"
    ).read_bytes()


def test_failed_claude_add_restores_a_config_actually_removed_by_cli(host: Host) -> None:
    host.record(runtime=True)
    path = host.home / ".claude.json"
    path.write_text(
        json.dumps({"mcpServers": {"rustok": {"args": []}, "keep": {"command": "stay"}}})
    )
    before = path.read_bytes()
    cli = Path(host.env["PATH"]) / "claude"
    cli.unlink()
    cli.write_text(
        f"#!{sys.executable}\nimport json,os,sys,pathlib\n"
        'p=pathlib.Path(os.environ["HOME"])/".claude.json"\n'
        'if sys.argv[2]=="remove":\n'
        ' d=json.loads(p.read_text()); del d["mcpServers"]["rustok"]; p.write_text(json.dumps(d))\n'
        "else: sys.exit(1)\n"
    )
    cli.chmod(0o755)
    result = host.run(SHIM, "connect", "claude", "--force")
    assert result.returncode != 0 and "previous registration restored" in result.stderr
    assert path.read_bytes() == before


@pytest.mark.parametrize("asset", ["install.sh", "rustok"])
def test_packaging_rejects_asset_substitution_before_verifying_or_publishing(
    host: Host, asset: str
) -> None:
    spec = importlib.util.spec_from_file_location(
        "release_builder", ROOT / "scripts/build-wallet-release.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.build(host.assets, "0.12.0", COMMIT, package=False)
    (host.assets / asset).write_text("tampered")
    with pytest.raises(ValueError, match="asset differs"):
        module.build(host.assets, "0.12.0", COMMIT, package=True)
    assert not (host.assets / "wallet-skill.zip").exists()


@pytest.mark.parametrize("answer,granted", [("GRANT", True), ("CANCEL", False)])
def test_only_a_human_terminal_can_expand_the_grant(host: Host, answer: str, granted: bool) -> None:
    host.record(runtime=True)
    result = subprocess.run(  # noqa: S603 — real pty around fixed fixture command
        [
            sys.executable,
            str(ROOT / "tests/shim/pty-init.py"),
            "/bin/sh",
            str(SHIM),
            "connect",
            "claude",
            "--capabilities",
            "read_wallet,preview_tx,execute_tx",
        ],
        env=host.env,
        input=answer + "\n",
        capture_output=True,
        text=True,
        timeout=40,
        check=False,
    )
    assert (result.returncode == 0) is granted, result.stdout + result.stderr
    assert "full balance" in result.stdout
    assert ("claude mcp add" in host.calls()) is granted
    if granted:
        assert "RUSTOK_MCP_CAPABILITIES=read_wallet,preview_tx,execute_tx" in host.calls()
    else:
        assert "secret create" not in host.calls()


@pytest.mark.parametrize("answer,stopped", [("FINISHED", True), ("UNKNOWN", False)])
def test_human_stop_attestation_or_cancellation(host: Host, answer: str, stopped: bool) -> None:
    host.record(runtime=True)
    host.env["STUB_CONTAINERS"] = "fixture;rustok=wallet;rustok.agent=claude"
    result = subprocess.run(  # noqa: S603 — fixed fixture command on a real pty
        [sys.executable, str(ROOT / "tests/shim/pty-init.py"), "/bin/sh", str(SHIM), "stop"],
        env=host.env,
        input=answer + "\n",
        capture_output=True,
        text=True,
        timeout=40,
        check=False,
    )
    assert (result.returncode == 0) is stopped
    assert "Unknown outcomes" in result.stdout
    assert ("podman stop fixture" in host.calls()) is stopped


def test_profile_quotes_a_home_with_spaces_apostrophe_and_shell_metacharacters(host: Host) -> None:
    hostile = host.home.parent / "home ' $(touch INJECTED)"
    hostile.mkdir()
    host.home = hostile
    host.env.update(HOME=str(hostile), XDG_DATA_HOME=str(hostile / ".local/share"))
    result = host.install()
    assert result.returncode == 0, result.stderr
    # Source the real generated profile in a shell and inspect PATH. Injection
    # changes both this exact value and the filesystem independently.
    script = host.assets / "profile-probe.sh"
    script.write_text('. "$HOME/.bashrc"\nprintf "%s" "$PATH"\n')
    probed = host.run(script)
    assert probed.returncode == 0
    assert probed.stdout == str(hostile / ".local/bin") + ":" + host.env["PATH"]
    assert not (host.assets / "INJECTED").exists()


def test_registry_runtime_refs_are_exactly_the_installer_pin() -> None:
    installer_digest = re.search(r'^WALLET_DIGEST="([^"]+)"$', INSTALLER.read_text(), re.MULTILINE)
    assert installer_digest
    expected = "ghcr.io/rustok-org/rustok-wallet-tui@" + installer_digest[1]
    assert json.loads((ROOT / "server.json").read_text())["packages"][0]["identifier"] == expected
    smithery = (ROOT / "smithery.yaml").read_text()
    refs = re.findall(r"ghcr\.io/rustok-org/rustok-wallet-tui[^\s'\"]+", smithery)
    assert len(refs) == 2 and all(ref == expected for ref in refs)


@pytest.mark.parametrize("command", ["connect", "update"])
def test_openclaw_read_error_is_reported_without_overwriting_registration(
    host: Host, command: str
) -> None:
    host.record(runtime=True)
    config = host.home / ".openclaw/openclaw.json"
    config.parent.mkdir()
    config.write_text('{"fixture":"retained"}')
    before = config.read_bytes()
    (host.state / "secret-rustok-keyring-openclaw").write_text("fixture-password")
    (host.state / "volume-rustok-openclaw").touch()
    cli = Path(host.env["PATH"]) / "openclaw"
    cli.write_text('#!/bin/sh\nprintf "openclaw %s\\n" "$*" >> "$STUB_LOG"\nexit 2\n')
    cli.chmod(0o755)
    args = ("connect", "openclaw", "--force") if command == "connect" else ("update",)
    result = host.run(SHIM, *args)
    assert result.returncode != 0
    assert "cannot read" in result.stderr
    assert "openclaw" in (result.stdout + result.stderr).lower()
    assert config.read_bytes() == before
    assert "openclaw mcp set" not in host.calls()
    assert "secret create" not in host.calls()


@pytest.mark.parametrize("client", ["cursor", "hermes", "openclaw"])
@pytest.mark.parametrize("grant", ["none", "read_wallet,preview_tx", "execute_tx"])
@pytest.mark.parametrize("form", ["short", "long", "joined_long", "joined_short"])
def test_other_client_reconnects_preserve_the_literal_subset(
    host: Host, client: str, grant: str, form: str
) -> None:
    host.record(runtime=True)
    args = ["run", "--label", f"rustok.agent={client}", *grant_args(grant, form)]
    entry = {"command": "podman", "args": args}
    (host.state / f"secret-rustok-keyring-{client}").write_text("fixture-password")
    (host.state / f"volume-rustok-{client}").touch()
    if client == "cursor":
        path = host.home / ".cursor/mcp.json"
        path.parent.mkdir()
        path.write_text(json.dumps({"mcpServers": {"rustok": entry, "keep": {"command": "stay"}}}))
    elif client == "hermes":
        path = host.home / ".hermes/config.yaml"
        path.parent.mkdir()
        scripts = path.parent / "scripts"
        scripts.mkdir()
        (scripts / "rustok-mcp-server.py").touch()
        path.write_text(
            yaml.safe_dump({"mcp_servers": {"rustok": entry, "keep": {"command": "stay"}}})
        )
        python = Path(host.env["PATH"]) / "python3"
        python.write_text(f'#!/bin/sh\nexec {shlex.quote(sys.executable)} "$@"\n')
        python.chmod(0o755)
    else:
        path = host.assets / "openclaw-entry.json"
        path.write_text(json.dumps(entry))
        cli = Path(host.env["PATH"]) / "openclaw"
        cli.write_text(
            f"#!{sys.executable}\nimport pathlib,sys\n"
            f"p=pathlib.Path({str(path)!r})\n"
            'if sys.argv[2]=="show": print(p.read_text())\n'
            'elif sys.argv[2]=="set": p.write_text(sys.argv[4])\n'
        )
        cli.chmod(0o755)
    result = host.run(SHIM, "connect", client, "--force")
    assert result.returncode == 0, result.stderr
    if client == "cursor":
        config = json.loads(path.read_text())["mcpServers"]
        assert config["keep"] == {"command": "stay"}
        new_entry = config["rustok"]
    elif client == "hermes":
        config = yaml.safe_load(path.read_text())["mcp_servers"]
        assert config["keep"] == {"command": "stay"}
        new_entry = config["rustok"]
    else:
        new_entry = json.loads(path.read_text())
    new_args = new_entry["args"]
    assert new_args.count(f"RUSTOK_MCP_CAPABILITIES={grant}") == 1
    assert sum(arg.startswith("RUSTOK_MCP_CAPABILITIES=") for arg in new_args) == 1
    assert f"ghcr.io/rustok-org/rustok-wallet-tui@sha256:{RUNTIME_DIGEST}" in new_args


def test_parser_copies_have_identical_contract() -> None:
    def parser(path: Path) -> str:
        return (
            path.read_text()
            .split("# BEGIN release manifest v1 parser", 1)[1]
            .split("# END release manifest v1 parser.", 1)[0]
        )

    assert parser(INSTALLER) == parser(SHIM)


def inherited_grant_args(name: str, form: str) -> list[str]:
    return {
        "short": ["-e", name],
        "long": ["--env", name],
        "joined_long": ["--env=" + name],
        "joined_short": ["-e" + name],
    }[form]


def store_client_registration(host: Host, client: str, args: list[str]) -> Path:
    entry = {"command": "podman", "args": ["run", "--label", f"rustok.agent={client}", *args]}
    (host.state / f"secret-rustok-keyring-{client}").write_text("fixture-password")
    (host.state / f"volume-rustok-{client}").touch()
    if client in ("claude", "cursor"):
        path = host.home / (".claude.json" if client == "claude" else ".cursor/mcp.json")
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps({"mcpServers": {"rustok": entry, "keep": {"command": "stay"}}}))
    elif client == "hermes":
        path = host.home / ".hermes/config.yaml"
        path.parent.mkdir()
        scripts = path.parent / "scripts"
        scripts.mkdir()
        (scripts / "rustok-mcp-server.py").touch()
        path.write_text(
            yaml.safe_dump({"mcp_servers": {"rustok": entry, "keep": {"command": "stay"}}})
        )
        python = Path(host.env["PATH"]) / "python3"
        python.write_text(f'#!/bin/sh\nexec {shlex.quote(sys.executable)} "$@"\n')
        python.chmod(0o755)
    else:
        path = host.assets / "openclaw-entry.json"
        path.write_text(json.dumps(entry))
        cli = Path(host.env["PATH"]) / "openclaw"
        cli.write_text(
            f"#!{sys.executable}\nimport pathlib,sys\n"
            f"p=pathlib.Path({str(path)!r})\n"
            'if sys.argv[2]=="show": print(p.read_text())\n'
            'elif sys.argv[2]=="set": p.write_text(sys.argv[4])\n'
        )
        cli.chmod(0o755)
    return path


@pytest.mark.parametrize("client", ["claude", "cursor", "hermes", "openclaw"])
@pytest.mark.parametrize("form", ["short", "long", "joined_long", "joined_short"])
@pytest.mark.parametrize("inherited", ["RUSTOK_MCP_CAPABILITIES", "RUSTOK_MCP_*"])
@pytest.mark.parametrize("operation", ["connect", "update"])
def test_mixed_inherited_grant_refuses_before_client_or_secret_mutation(
    host: Host, client: str, form: str, inherited: str, operation: str
) -> None:
    host.record(runtime=True)
    path = store_client_registration(
        host, client, grant_args("execute_tx", "short") + inherited_grant_args(inherited, form)
    )
    before = path.read_bytes()
    host.env["RUSTOK_MCP_CAPABILITIES"] = "read_wallet"
    result = (
        host.run(SHIM, "connect", client, "--force")
        if operation == "connect"
        else host.run(SHIM, "update", "--release", "0.12.0")
    )
    assert result.returncode != 0, result.stdout + result.stderr
    assert path.read_bytes() == before
    calls = host.calls()
    assert "secret create" not in calls
    assert "claude mcp remove" not in calls and "claude mcp add" not in calls
    assert "unambiguous" in result.stderr or "ambiguous" in result.stderr
    if operation == "update":
        assert client in result.stdout + result.stderr
        assert "podman stop" not in calls


@pytest.mark.parametrize("client", ["claude", "cursor", "hermes", "openclaw"])
@pytest.mark.parametrize("form", ["short", "long", "joined_long", "joined_short"])
@pytest.mark.parametrize("inherited", ["RUSTOK_MCP_CAPABILITIES", "RUSTOK_MCP_*"])
def test_single_inherited_grant_migrates_to_literal_read_without_using_ambient(
    host: Host, client: str, form: str, inherited: str
) -> None:
    host.record(runtime=True)
    path = store_client_registration(host, client, inherited_grant_args(inherited, form))
    host.env["RUSTOK_MCP_CAPABILITIES"] = "execute_tx"
    result = host.run(SHIM, "connect", client, "--force")
    assert result.returncode == 0, result.stderr
    if client == "claude":
        added = next(
            line for line in host.calls().splitlines() if line.startswith("claude mcp add")
        )
        assert added.count("RUSTOK_MCP_CAPABILITIES=") == 1
        assert "RUSTOK_MCP_CAPABILITIES=read_wallet" in added
    else:
        data = (
            yaml.safe_load(path.read_text()) if client == "hermes" else json.loads(path.read_text())
        )
        entry = (
            data["mcp_servers"]["rustok"]
            if client == "hermes"
            else data["mcpServers"]["rustok"]
            if client == "cursor"
            else data
        )
        assert entry["args"].count("RUSTOK_MCP_CAPABILITIES=read_wallet") == 1
        assert not any("execute_tx" in arg for arg in entry["args"])


@pytest.mark.parametrize("client", ["claude", "cursor", "hermes", "openclaw"])
@pytest.mark.parametrize("operation", ["connect", "update"])
@pytest.mark.parametrize(
    "setter",
    [
        ["--env-merge", "RUSTOK_MCP_CAPABILITIES=${RUSTOK_MCP_CAPABILITIES}suffix"],
        ["--env-merge=RUSTOK_MCP_CAPABILITIES=${RUSTOK_MCP_CAPABILITIES}suffix"],
        ["--secret", "fixture,type=env,target=RUSTOK_MCP_CAPABILITIES"],
        ["--secret=fixture,target=RUSTOK_MCP_CAPABILITIES,type=env"],
        ["--secret", "RUSTOK_MCP_CAPABILITIES,type=env"],
    ],
)
def test_indirect_capability_setters_are_ambiguous_with_a_literal(
    host: Host, client: str, operation: str, setter: list[str]
) -> None:
    host.record(runtime=True)
    path = store_client_registration(host, client, grant_args("execute_tx", "short") + setter)
    before = path.read_bytes()
    result = (
        host.run(SHIM, "connect", client, "--force")
        if operation == "connect"
        else host.run(SHIM, "update", "--release", "0.12.0")
    )
    assert result.returncode != 0
    assert path.read_bytes() == before
    assert "secret create" not in host.calls()
    assert "claude mcp add" not in host.calls() and "claude mcp remove" not in host.calls()


@pytest.mark.parametrize("client", ["claude", "cursor", "hermes", "openclaw"])
def test_unrelated_environment_carriers_do_not_invalidate_an_explicit_grant(
    host: Host, client: str
) -> None:
    host.record(runtime=True)
    store_client_registration(
        host,
        client,
        [
            "-e",
            "RUSTOK_KEYRING_PASSWORD_FILE=/run/fixture",
            "--env=RUSTOK_OTHER_*",
            "--secret=fixture,type=mount",
            "--secret=RUSTOK_MCP_CAPABILITIES,type=env,target=OTHER",
            "--env-merge=OTHER=suffix",
            *grant_args("execute_tx", "short"),
        ],
    )
    result = host.run(SHIM, "connect", client, "--force")
    assert result.returncode == 0, result.stderr
