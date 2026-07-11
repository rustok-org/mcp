"""JSON-RPC client for the local anvil chain the acceptance suite broadcasts into.

The wallet container reaches anvil by its name on the podman network; the suite
reaches the same node through a published localhost port (there is no DNS for the
network's names on the host).
"""

from __future__ import annotations

from typing import Any

import httpx

WEI_PER_ETH = 10**18


class Anvil:
    """Minimal JSON-RPC client: fund an address, read a transaction back."""

    def __init__(self, rpc_url: str) -> None:
        self.rpc_url = rpc_url

    def rpc(self, method: str, params: list[Any] | None = None) -> Any:
        """Call a JSON-RPC method and return its result."""
        response = httpx.post(
            self.rpc_url,
            json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or []},
            timeout=10,
        )
        response.raise_for_status()
        payload = response.json()
        if "error" in payload:
            raise RuntimeError(f"anvil {method} failed: {payload['error']}")
        return payload["result"]

    def is_up(self) -> bool:
        """Whether the node answers — used to wait out container start-up."""
        try:
            self.rpc("eth_chainId")
        except (httpx.HTTPError, RuntimeError):
            return False
        return True

    def set_balance(self, address: str, wei: int) -> None:
        """Fund an address with anvil's cheat code (no faucet, no mining)."""
        self.rpc("anvil_setBalance", [address, hex(wei)])

    def balance(self, address: str) -> int:
        """Native balance in wei."""
        return int(self.rpc("eth_getBalance", [address, "latest"]), 16)

    def transaction(self, tx_hash: str) -> dict[str, Any] | None:
        """The mined transaction, or None when the chain never saw that hash."""
        result: dict[str, Any] | None = self.rpc("eth_getTransactionByHash", [tx_hash])
        return result
