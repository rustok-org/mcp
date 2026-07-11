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
    "sign_message": Capability.EXECUTE_TX,
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


def parse_capabilities(values: Iterable[str]) -> set[Capability]:
    """Parse raw capability strings into a validated set."""
    result: set[Capability] = set()
    for val in values:
        try:
            result.add(Capability(val))
        except ValueError:
            logger.warning("Unknown capability ignored: %s", val)
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
    """Resolve the capabilities granted to the process-trusted stdio transport.

    Whoever launches the stdio container owns the local machine, so stdio is not
    a security boundary — it defaults to *all* capabilities (matching the
    "stdio is not gated" contract). An explicit comma-separated value restricts
    it (e.g. ``read_wallet`` for a read-only agent). A set-but-unparseable value
    resolves to the empty set and logs a warning, so a typo never silently gates
    every tool.

    Args:
        raw: The raw ``RUSTOK_MCP_CAPABILITIES`` value, or ``None`` when unset.

    Returns:
        The granted capability set.
    """
    if raw is None or not raw.strip():
        return set(Capability)
    caps = parse_capabilities(part.strip() for part in raw.split(","))
    if not caps:
        logger.warning(
            "RUSTOK_MCP_CAPABILITIES set but no valid capabilities parsed (%r) — "
            "all tools are gated",
            raw,
        )
    return caps


def has_capability(tool_name: str, capabilities: set[Capability]) -> bool:
    """Check whether the given capabilities allow access to a tool.

    Unmapped tools are denied by default (fail-closed).
    """
    required = CAPABILITY_MAP.get(tool_name)
    if required is None:
        return False
    return required in capabilities
