"""Capability-based security for MCP sessions."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import StrEnum

logger = logging.getLogger(__name__)


class Capability(StrEnum):
    """Client capabilities that gate access to tool categories."""

    READ_WALLET = "read_wallet"
    PREVIEW_TX = "preview_tx"
    EXECUTE_TX = "execute_tx"


# Map tool name -> required capability
CAPABILITY_MAP: dict[str, Capability] = {
    "get_wallet_context": Capability.READ_WALLET,
    "get_balances": Capability.READ_WALLET,
    "get_positions": Capability.READ_WALLET,
    "preview_transaction": Capability.PREVIEW_TX,
    "execute_transaction": Capability.EXECUTE_TX,
    "get_execution_status": Capability.EXECUTE_TX,
}


@dataclass
class Session:
    """An MCP session with capability state."""

    session_id: str
    capabilities: set[Capability] = field(default_factory=set)
    queue: asyncio.Queue[str] | None = field(default=None)
    last_seen: float = field(default_factory=time.monotonic)
    initialized: bool = False


def parse_capabilities(values: Iterable[str]) -> set[Capability]:
    """Parse raw capability strings into a validated set."""
    result: set[Capability] = set()
    for val in values:
        try:
            result.add(Capability(val))
        except ValueError:
            logger.warning("Unknown capability ignored")
            continue
    return result


def extract_rustok_capabilities(params: object) -> set[Capability]:
    """Extract the rustok-specific capability *list* from initialize params.

    Returns the empty set when params is not a dict, when ``capabilities`` is not
    a list (e.g. the standard MCP capabilities *object*), or when nothing valid
    parses — so a standard MCP client correctly ends up with no tools.
    """
    if not isinstance(params, dict):
        return set()
    raw = params.get("capabilities", [])
    if not isinstance(raw, list):
        return set()
    return parse_capabilities(raw)


def resolve_stdio_capabilities(raw: str | None) -> set[Capability]:
    """Resolve the process ceiling: implicit grants are read-only.

    Explicit lists grant exactly their names; any unknown nonempty token denies
    the entire grant. ``none`` selects no tools. Empty list items are ignored.
    The separate historical SSE initialization contract is unchanged.
    """
    if raw is None or not raw.strip():
        return {Capability.READ_WALLET}
    if raw.strip() == "none":
        return set()
    caps: set[Capability] = set()
    for part in raw.split(","):
        name = part.strip()
        if not name:
            continue
        try:
            caps.add(Capability(name))
        except ValueError:
            logger.warning("Invalid RUSTOK_MCP_CAPABILITIES — all tools are gated")
            return set()
    return caps


def has_capability(tool_name: str, capabilities: set[Capability]) -> bool:
    """Check whether the given capabilities allow access to a tool.

    Unmapped tools are denied by default (fail-closed).
    """
    required = CAPABILITY_MAP.get(tool_name)
    if required is None:
        return False
    return required in capabilities


def ceiling_for_policy_mode(mode: str | None) -> set[Capability] | None:
    """Map the core's policy mode (`policy_mode` in WalletContext) to a ceiling.

    Increment-1 semantics: ``read_only`` leaves read + preview; ``supervised``
    and ``autonomous`` keep the full set (the core parks/denies writes
    itself). Returns ``None`` when the mode is unknown or unavailable — the
    caller then falls back to the transport-seeded ceiling alone, because
    MCP-side filtering is advisory; enforcement lives in the core.
    """
    if mode == "read_only":
        return {Capability.READ_WALLET, Capability.PREVIEW_TX}
    if mode in ("supervised", "autonomous"):
        return set(Capability)
    return None


def resolve_sse_capabilities(raw: str | None) -> set[Capability] | None:
    """Operator ceiling for SSE sessions (audit B1), or ``None`` when unset.

    Unlike stdio (defaults to read-only), an unset value keeps
    the historical SSE contract: the session starts gated and the first
    ``initialize`` declares the set. A set value seeds the session ceiling —
    the first ``initialize`` may then only narrow it, matching stdio.
    """
    if raw is None or not raw.strip():
        return None
    return parse_capabilities(part.strip() for part in raw.split(","))
