"""Capability-based security for MCP sessions."""

from __future__ import annotations

import asyncio
import logging
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
    "preview_send": Capability.PREVIEW_TX,
    "execute_send": Capability.EXECUTE_TX,
    "sign_message": Capability.EXECUTE_TX,
}


@dataclass
class Session:
    """An MCP session with capability state."""

    session_id: str
    capabilities: set[Capability] = field(default_factory=set)
    queue: asyncio.Queue[str] | None = field(default=None)


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


def has_capability(tool_name: str, capabilities: set[Capability]) -> bool:
    """Check whether the given capabilities allow access to a tool.

    Unmapped tools are denied by default (fail-closed).
    """
    required = CAPABILITY_MAP.get(tool_name)
    if required is None:
        return False
    return required in capabilities
