"""Drive `rustok init` under a real pty (test helper, not a pytest module).

The shim reads the keyring password from /dev/tty — the Rule-of-two-windows
gate. Tests need a controlling terminal to walk that path: this helper forks
the shim onto a pty, feeds it the lines given on OUR stdin (one per password
prompt), relays everything the child prints, and exits with the child's code.
"""

import os
import pty
import select
import sys

TIMEOUT_S = 30


def main() -> int:
    feed_lines = [line.encode() for line in sys.stdin.read().splitlines()]
    pid, fd = pty.fork()
    if pid == 0:  # child: the shim on the pty
        os.execvp(sys.argv[1], sys.argv[1:])  # noqa: S606  # fixed argv from the runner, no shell — the safe form S606 exists to steer toward

    captured = b""
    fed = 0
    prompts_seen = 0
    while True:
        ready, _, _ = select.select([fd], [], [], TIMEOUT_S)
        if not ready:
            os.kill(pid, 9)
            print("pty-init: TIMEOUT waiting for the shim", file=sys.stderr)
            return 124
        try:
            chunk = os.read(fd, 4096)
        except OSError:  # child closed the pty
            break
        if not chunk:
            break
        captured += chunk
        # Each password prompt ends with ': ' and echo is off — feed one line
        # per prompt, exactly as a human would type.
        while fed < len(feed_lines) and captured.count(b": ") > prompts_seen:
            prompts_seen = captured.count(b": ")
            os.write(fd, feed_lines[fed] + b"\n")
            fed += 1
    sys.stdout.buffer.write(captured)
    _, status = os.waitpid(pid, 0)
    return os.waitstatus_to_exitcode(status)


if __name__ == "__main__":
    sys.exit(main())
