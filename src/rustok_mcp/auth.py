"""Inbound bearer authentication for the network-facing MCP transport.

A single shared secret (``RUSTOK_MCP_INBOUND_API_KEY``) gates the SSE routes.
The stdio transport is local and process-trusted, so it is not covered here.
When no key is configured the dependency passes (loopback dev flow); a startup
warning is emitted elsewhere. Public exposure without a key is prevented one
layer up by the deployment profile (Caddy injects a required key).
"""

import logging
import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from rustok_mcp.config import Settings, get_settings

logger = logging.getLogger(__name__)

# auto_error=False: missing/blank credentials yield None instead of a 403, so we
# return a uniform 401 for both "no header" and "wrong token".
_bearer = HTTPBearer(auto_error=False)


def _unauthorized() -> HTTPException:
    """Build a fresh 401 — avoid raising a shared exception instance."""
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Unauthorized",
        headers={"WWW-Authenticate": "Bearer"},
    )


BearerCredentials = Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


async def require_auth(
    credentials: BearerCredentials,
    settings: SettingsDep,
) -> None:
    """Reject requests lacking a valid inbound bearer token.

    No-op when ``inbound_api_key`` is unset (dev). The token is compared in
    constant time; failures are logged without the token or header value.
    """
    expected = settings.inbound_api_key
    if expected is None:
        return

    presented = credentials.credentials if credentials is not None else ""
    if secrets.compare_digest(presented.encode(), expected.encode()):
        return

    logger.warning("rejected MCP request: invalid or missing bearer token")
    raise _unauthorized()
