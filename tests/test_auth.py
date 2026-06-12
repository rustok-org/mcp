"""Inbound bearer auth dependency tests."""

import logging

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from rustok_mcp.auth import require_auth
from rustok_mcp.config import Settings


def _settings(inbound_api_key: str | None) -> Settings:
    return Settings(inbound_api_key=inbound_api_key)


def _bearer(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


async def test_passes_when_no_key_configured() -> None:
    """With no inbound key, any request passes (dev flow)."""
    await require_auth(credentials=None, settings=_settings(None))


async def test_passes_with_valid_token() -> None:
    """A matching bearer token is accepted."""
    await require_auth(
        credentials=_bearer("right-token"),
        settings=_settings("right-token"),
    )


async def test_rejects_wrong_token() -> None:
    """A non-matching token yields 401."""
    with pytest.raises(HTTPException) as exc_info:
        await require_auth(
            credentials=_bearer("wrong-token"),
            settings=_settings("right-token"),
        )
    assert exc_info.value.status_code == 401


async def test_rejects_missing_header() -> None:
    """A configured key with no credentials yields 401 (not 403)."""
    with pytest.raises(HTTPException) as exc_info:
        await require_auth(credentials=None, settings=_settings("right-token"))
    assert exc_info.value.status_code == 401


async def test_rejects_empty_bearer_token() -> None:
    """An empty bearer token never matches a configured key."""
    with pytest.raises(HTTPException) as exc_info:
        await require_auth(
            credentials=_bearer(""),
            settings=_settings("right-token"),
        )
    assert exc_info.value.status_code == 401


async def test_401_detail_does_not_leak_token() -> None:
    """The 401 body must not echo the presented or expected token."""
    with pytest.raises(HTTPException) as exc_info:
        await require_auth(
            credentials=_bearer("super-secret-presented"),
            settings=_settings("expected-key"),
        )
    detail = str(exc_info.value.detail)
    assert "super-secret-presented" not in detail
    assert "expected-key" not in detail


async def test_failed_attempt_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    """A rejected request emits a warning without the token value."""
    with (
        caplog.at_level(logging.WARNING, logger="rustok_mcp.auth"),
        pytest.raises(HTTPException),
    ):
        await require_auth(
            credentials=_bearer("leak-me"),
            settings=_settings("right-token"),
        )
    assert any(record.levelno == logging.WARNING for record in caplog.records)
    assert "leak-me" not in caplog.text
    assert "right-token" not in caplog.text
