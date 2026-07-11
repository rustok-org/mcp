"""Thin podman wrapper for the acceptance suite.

Every call is a fixed argv with no shell and no user input — the S603/S607
preconditions hold (see the per-file-ignores in ``pyproject.toml``).
"""

from __future__ import annotations

import shutil
import socket
import subprocess

PODMAN = shutil.which("podman") or "podman"


class PodmanError(RuntimeError):
    """A podman command failed — carries the stderr that says why."""


def podman(
    *args: str, check: bool = True, timeout: float = 180
) -> subprocess.CompletedProcess[str]:
    """Run a podman command and return the finished process.

    On failure the stderr is raised with the command: `CalledProcessError` would report
    only the exit code, and "podman run exited 125" tells a debugger nothing — the
    reason ("image not known", "port is already allocated") lives in stderr.
    """
    done = subprocess.run(
        [PODMAN, *args],
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )
    if check and done.returncode != 0:
        raise PodmanError(
            f"podman {' '.join(args)} exited {done.returncode}\n{done.stderr.strip()}"
        )
    return done


def rm_force(*names: str) -> None:
    """Remove containers, ignoring the ones that are already gone."""
    for name in names:
        podman("rm", "-f", name, check=False)


def volume_rm(*names: str) -> None:
    """Remove volumes, ignoring the ones that are already gone."""
    for name in names:
        podman("volume", "rm", "-f", name, check=False)


def network_rm(*names: str) -> None:
    """Remove networks, ignoring the ones that are already gone."""
    for name in names:
        podman("network", "rm", "-f", name, check=False)


def free_port() -> int:
    """Pick a free localhost TCP port for publishing a container port."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port: int = probe.getsockname()[1]
        return port
