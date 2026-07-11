"""The human's side of the wallet: the console TUI, driven through a pty.

Two things this module exists to get right:

* **Assertions run against a RENDERED screen.** The console is a full-screen ratatui
  app: the raw pty stream interleaves ANSI escapes with text, so a regex over the raw
  bytes matches nothing reliable. `pyte` replays the stream into a terminal buffer,
  and the tests read that buffer — the same pixels a human would see.
* **Every step waits for its screen, never for a clock.** The console polls the queue
  every 2.5 s (console `main.rs`), so a keystroke sent "after a sleep" can land on a
  screen that has not caught up yet — a false red.

The pty is deliberately large: the console refuses to approve a card whose priority
fields do not fit the terminal (`ui.rs::priority_fields_fit`), and the pexpect default
of 80x24 would trip that gate instead of the behaviour under test.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from types import TracebackType

import pexpect
import pyte

from tests.e2e.podman import PODMAN

ROWS = 50
COLS = 140
DEFAULT_TIMEOUT = 40.0


class ConsoleTimeout(AssertionError):
    """The expected screen never appeared — carries the last rendered screen."""


class Console:
    """A `podman exec -it <wallet> rustok-console` session on a pty."""

    def __init__(self, container: str) -> None:
        self._screen = pyte.Screen(COLS, ROWS)
        self._stream = pyte.ByteStream(self._screen)
        self._child = pexpect.spawn(
            PODMAN,
            ["exec", "-it", container, "rustok-console"],
            dimensions=(ROWS, COLS),
            timeout=1,
        )

    def _pump(self, seconds: float = 0.4) -> None:
        """Drain whatever the console has emitted into the terminal emulator.

        EOF ends the pumping immediately. Treating it like a timeout would turn the
        loop into a busy-spin the moment the console exits or crashes — burning a core
        for the rest of the budget exactly when something has gone wrong.
        """
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            try:
                chunk = self._child.read_nonblocking(size=65536, timeout=0.2)
            except pexpect.TIMEOUT:
                continue
            except pexpect.EOF:
                return
            self._stream.feed(chunk)

    @property
    def screen(self) -> str:
        """The rendered screen, as the human sees it."""
        return "\n".join(self._screen.display)

    def visible(self) -> str:
        """The rendered screen without its blank lines — for failure messages."""
        return "\n".join(row.rstrip() for row in self._screen.display if row.strip())

    def wait_for(
        self,
        predicate: Callable[[str], bool],
        what: str,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        """Block until the rendered screen satisfies `predicate`."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self._pump()
            if predicate(self.screen):
                return
            if not self._child.isalive():
                raise ConsoleTimeout(
                    f"the console exited before {what} appeared.\nLast screen:\n{self.visible()}"
                )
        raise ConsoleTimeout(f"never saw {what} within {timeout}s.\nLast screen:\n{self.visible()}")

    def wait_for_text(self, needle: str, timeout: float = DEFAULT_TIMEOUT) -> None:
        """Block until `needle` shows up on the rendered screen."""
        self.wait_for(lambda screen: needle in screen, repr(needle), timeout)

    def send(self, keys: str) -> None:
        """Send keystrokes to the TUI."""
        self._child.send(keys)

    def submit_pin(self, pin: str) -> None:
        """Type a PIN and press Enter."""
        self._child.send(pin + "\r")

    def wait_exit(self, timeout: float = DEFAULT_TIMEOUT) -> int:
        """Dismiss the outcome screen, then return the console's exit code (invariant #7).

        On a terminal outcome the console shows the answer and blocks in `wait_for_key`
        (console `main.rs`) — the human is meant to read what happened to their money
        before the window disappears. A harness that does not press a key waits forever.
        """
        self.send("\r")
        deadline = time.monotonic() + timeout
        while self._child.isalive():
            if time.monotonic() > deadline:
                # A console that hangs instead of exiting is a real regression: report it
                # with the screen the human would be staring at, not a bare pexpect error.
                raise ConsoleTimeout(
                    f"the console never exited within {timeout}s.\nLast screen:\n{self.visible()}"
                )
            self._pump(0.3)

        self._child.close()
        status = self._child.exitstatus
        if status is None:
            raise ConsoleTimeout(
                f"the console was killed by signal {self._child.signalstatus} instead of "
                f"exiting.\nLast screen:\n{self.visible()}"
            )
        return int(status)

    def close(self) -> None:
        """Tear the session down without asserting anything about the exit."""
        if self._child.isalive():
            self._child.terminate(force=True)
        self._child.close()

    def __enter__(self) -> Console:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()
