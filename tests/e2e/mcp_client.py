"""The agent's side of the wallet: MCP JSON-RPC over the container's stdio.

`podman run -i <wallet image>` IS the MCP server — its stdin/stdout are the JSON-RPC
channel (all backend logs go to stderr). This client speaks that channel exactly the
way a real MCP host would.
"""

from __future__ import annotations

import json
import selectors
import subprocess
import time
from pathlib import Path
from types import TracebackType
from typing import Any

# The entrypoint starts core + gateway and waits for both before the MCP server
# answers, so the very first request is the slow one.
FIRST_CALL_TIMEOUT = 90.0
CALL_TIMEOUT = 30.0


class WalletDied(RuntimeError):
    """The wallet container exited while the suite was talking to it."""


class McpStdio:
    """JSON-RPC client over a `podman run -i` wallet container."""

    def __init__(self, argv: list[str], stderr_path: Path) -> None:
        self._argv = argv
        self._stderr_path = stderr_path
        self._stderr = stderr_path.open("wb")
        self._proc = subprocess.Popen(
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self._stderr,
            text=True,
            bufsize=1,
        )
        self._next_id = 0
        self._selector = selectors.DefaultSelector()
        assert self._proc.stdout is not None
        self._selector.register(self._proc.stdout, selectors.EVENT_READ)

    def _read_line(self, timeout: float) -> str:
        """Read one JSON-RPC line, bounding the WHOLE line by the deadline.

        A readable fd only proves that a byte arrived, not that a line did: a response
        split across writes that then stalls would hang a plain `readline()` forever,
        and a hang is the one failure a test harness must never produce — it reports
        nothing. So the deadline is re-checked before every chunk.
        """
        deadline = time.monotonic() + timeout
        buffer = ""
        assert self._proc.stdout is not None
        while not buffer.endswith("\n"):
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not self._selector.select(remaining):
                raise WalletDied(
                    f"no complete MCP response within {timeout}s "
                    f"(read so far: {buffer!r}); container stderr: {self.stderr_tail()}"
                )
            chunk = self._proc.stdout.readline()
            if not chunk:
                raise WalletDied(f"wallet container exited; stderr: {self.stderr_tail()}")
            buffer += chunk
        return buffer

    def call(
        self, method: str, params: dict[str, Any] | None = None, timeout: float = CALL_TIMEOUT
    ) -> Any:
        """Send a JSON-RPC request and return its `result`."""
        self._next_id += 1
        request: dict[str, Any] = {"jsonrpc": "2.0", "id": self._next_id, "method": method}
        if params is not None:
            request["params"] = params
        assert self._proc.stdin is not None
        self._proc.stdin.write(json.dumps(request) + "\n")
        self._proc.stdin.flush()

        response = json.loads(self._read_line(timeout))
        # The server answers with both keys present — `error` is null on success, so
        # its mere presence means nothing.
        if response.get("error") is not None:
            raise RuntimeError(f"MCP {method} failed: {response['error']}")
        return response["result"]

    def initialize(self) -> dict[str, Any]:
        """Perform the MCP handshake (this is what waits for core + gateway)."""
        result: dict[str, Any] = self.call(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "rustok-e2e", "version": "1"},
            },
            timeout=FIRST_CALL_TIMEOUT,
        )
        return result

    def tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Call a tool and return its JSON payload (the text content, parsed)."""
        result = self.call("tools/call", {"name": name, "arguments": arguments})
        payload: dict[str, Any] = json.loads(result["content"][0]["text"])
        return payload

    def stderr_tail(self, lines: int = 15) -> str:
        """The container's last stderr lines — the only place backend errors surface."""
        try:
            text = self._stderr_path.read_text(errors="replace")
        except OSError:
            return "(no stderr captured)"
        return "\n".join(text.splitlines()[-lines:])

    def close(self) -> None:
        """Close the channel and let the container go."""
        self._selector.close()
        if self._proc.stdin is not None:
            self._proc.stdin.close()
        if self._proc.stdout is not None:
            self._proc.stdout.close()
        self._proc.terminate()
        try:
            self._proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            self._proc.kill()
        self._stderr.close()

    def __enter__(self) -> McpStdio:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()
