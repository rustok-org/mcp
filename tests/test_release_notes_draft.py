"""The release-notes draft: what it refuses, and where its ranges come from.

Every test here is hermetic. The script's real subject is a range between two
release tags, and CI checks this repository out shallow and without tags — so a
test that leaned on the tags in *this* clone would pass on a laptop and skip, or
lie, in the job that matters. Each test that needs history builds its own
throwaway repository instead.

No network: the two calls that would reach GitHub live behind `--ranges-only`
and `--classify`, which are the seams these tests use.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
SCRIPT = REPO_ROOT / "scripts" / "release-notes-draft.sh"
SH = shutil.which("sh")

# pytest itself runs under CI, and the script refuses to run there — on purpose.
# Every invocation below therefore starts from an environment with those markers
# removed, and the one test that asserts the refusal puts one back.
CLEAN_ENV = {k: v for k, v in os.environ.items() if k not in ("CI", "GITHUB_ACTIONS")}


def _run(
    *args: str, env: dict[str, str] | None = None, cwd: Path | None = None
) -> subprocess.CompletedProcess[str]:
    assert SH, "no POSIX sh on this machine"
    return subprocess.run(  # noqa: S603  # fixed argv, no shell, no user input
        [SH, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        env=env or CLEAN_ENV,
        cwd=cwd or REPO_ROOT,
        check=False,
    )


def _git(repo: Path, *args: str) -> None:
    assert (git := shutil.which("git")), "no git on this machine"
    subprocess.run(  # noqa: S603  # fixed argv, no shell, no user input
        [git, *args], cwd=repo, check=True, capture_output=True, text=True
    )


def _dockerfile(core: str, console: str) -> str:
    return f"ARG CORE_IMAGE=ghcr.io/rustok-org/rustok-core:v{core}\nARG CONSOLE_IMAGE=ghcr.io/rustok-org/rustok-console:v{console}\n"


@pytest.fixture
def release_repo(tmp_path: Path) -> Path:
    """A repository shaped like this one: a release tag, then pins that moved."""
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    shutil.copy(SCRIPT, repo / "scripts" / SCRIPT.name)
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "test")

    (repo / "Dockerfile.wallet").write_text(_dockerfile("0.4.4", "0.3.2"), encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "the release that shipped")
    _git(repo, "tag", "wallet-tui-v0.10.0")

    (repo / "Dockerfile.wallet").write_text(_dockerfile("0.4.5", "0.3.3"), encoding="utf-8")
    _git(repo, "commit", "-qam", "the pins move")
    return repo


def _in(
    repo: Path, *args: str, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    assert SH, "no POSIX sh on this machine"
    return subprocess.run(  # noqa: S603  # fixed argv, no shell, no user input
        [SH, str(repo / "scripts" / SCRIPT.name), *args],
        capture_output=True,
        text=True,
        env=env or CLEAN_ENV,
        cwd=repo,
        check=False,
    )


def test_it_refuses_to_run_under_ci() -> None:
    """The refusal is the perimeter, not a convenience.

    Reading the private `core` needs a person's own credentials. Wired into a
    workflow of this PUBLIC repository, it would need a token for a private one
    — so the script says no before anyone builds on it.
    """
    result = _run(env={**CLEAN_ENV, "CI": "true"})
    assert result.returncode == 3, result.stderr
    assert "refusing to run under CI" in result.stderr
    assert "private" in result.stderr.lower()


def test_the_other_marker_is_honoured_too() -> None:
    """`GITHUB_ACTIONS` without `CI` is the same situation."""
    result = _run(env={**CLEAN_ENV, "GITHUB_ACTIONS": "true"})
    assert result.returncode == 3, result.stderr


def test_it_runs_when_no_ci_marker_is_set(release_repo: Path) -> None:
    """The other side of the refusal — proof it is not refusing everything.

    A guard only tested on the failing side cannot be told apart from a script
    that never works.
    """
    result = _in(release_repo, "--ranges-only")
    assert result.returncode == 0, result.stderr


def test_the_range_comes_from_the_pins_the_repo_already_carries(release_repo: Path) -> None:
    """Nobody types the neighbours' versions: they are read from the pins.

    The previous release's `Dockerfile.wallet` is fetched out of the tag, the
    current one out of the working tree, and the two ends of the range fall out
    of that comparison. This is the whole reason the draft can be assembled
    without being told anything.
    """
    result = _in(release_repo, "--ranges-only")
    assert result.returncode == 0, result.stderr
    assert "Previous release: wallet-tui-v0.10.0" in result.stdout
    assert "core:    v0.4.4 -> v0.4.5" in result.stdout
    assert "console: v0.3.3" not in result.stdout, "console range read the wrong end"
    assert "console: v0.3.2 -> v0.3.3" in result.stdout


def test_a_tag_that_is_not_a_release_does_not_decide_the_range(release_repo: Path) -> None:
    """`wallet-tui-v0.0.0-shelf-test` exists in this repo, and it is not a release.

    `git describe --match 'wallet-tui-v*'` would take it: --match is a glob, and
    a glob cannot say "digits to the end". The tag here sorts ABOVE the real one,
    so a version-sorted list would hand it over first.
    """
    _git(release_repo, "tag", "wallet-tui-v9.9.9-shelf-test")
    result = _in(release_repo, "--ranges-only")
    assert result.returncode == 0, result.stderr
    assert "Previous release: wallet-tui-v0.10.0" in result.stdout


def test_a_tag_on_another_branch_does_not_decide_the_range(release_repo: Path) -> None:
    """Shape is not enough — the tag also has to be behind us."""
    _git(release_repo, "checkout", "-q", "-b", "elsewhere", "HEAD~1")
    _git(release_repo, "commit", "-q", "--allow-empty", "-m", "a release that never landed")
    _git(release_repo, "tag", "wallet-tui-v9.9.9")
    _git(release_repo, "checkout", "-q", "main")
    result = _in(release_repo, "--ranges-only")
    assert result.returncode == 0, result.stderr
    assert "Previous release: wallet-tui-v0.10.0" in result.stdout


def test_it_refuses_when_no_release_tag_is_reachable(tmp_path: Path) -> None:
    """An empty answer here would read as "nothing changed", which is a lie.

    This is also exactly the state of a CI checkout: shallow, no tags.
    """
    repo = tmp_path / "bare"
    (repo / "scripts").mkdir(parents=True)
    shutil.copy(SCRIPT, repo / "scripts" / SCRIPT.name)
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "test")
    (repo / "Dockerfile.wallet").write_text(_dockerfile("0.4.5", "0.3.3"), encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "no tags here")

    result = _in(repo, "--ranges-only")
    assert result.returncode == 4, result.stdout
    assert "no previous release tag" in result.stderr
    assert "RELEASE_NOTES_PREV_TAG" in result.stderr, "the refusal must say how to proceed"


@pytest.mark.parametrize(
    ("subject", "expected"),
    [
        (
            "chore(deps): h2 0.4.16 — unbounded empty DATA frames (RUSTSEC-2026-0258) (#126)",
            "user-facing",
        ),
        ("chore(deps): bump something (CVE-2026-1111)", "user-facing"),
        ("chore(deps): bump something (GHSA-xxxx-yyyy-zzzz)", "user-facing"),
        ("fix: two memories that outlive their usefulness (#124)", "user-facing"),
        ("The mode switch on the Dashboard — pick, read the risk, PIN (#25)", "user-facing"),
        ("docs(specs): A0 plan — the queue number", "internal"),
        ("ci: a hang costs twenty minutes, not six hours (#127)", "internal"),
        ("chore(release): 0.4.5 — the wallet arrives", "internal"),
    ],
)
def test_where_a_commit_lands(subject: str, expected: str) -> None:
    """The prefix is a hint; a security identifier is not.

    0.11.0 shipped `chore(deps): h2 … (RUSTSEC-2026-0258)` — a fix users wanted,
    wearing the prefix of a chore. The block a tired reader skims is the wrong
    place for it, so the identifier overrides the prefix.
    """
    assert SH
    result = subprocess.run(  # noqa: S603  # fixed argv, no shell, no user input
        [SH, str(SCRIPT), "--classify"],
        input=subject + "\n",
        capture_output=True,
        text=True,
        env=CLEAN_ENV,
        cwd=REPO_ROOT,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == expected


def test_an_unknown_argument_is_refused() -> None:
    """A typo in a flag must not quietly produce a different draft."""
    result = _run("--everything")
    assert result.returncode == 2
    assert "unknown argument" in result.stderr
