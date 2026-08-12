"""Authentication for GitHub Report HTTP endpoints.

Only two endpoints in this project actually need protection: the report
generator and the publisher. Both were previously unauthenticated, which
meant any reachable caller could consume GitHub API quota, retrieve org
activity, publish arbitrary content, and cause `git push` from the
service's credentials.

Contract
--------

Three modes, in the order the dependency checks them:

1. ``AUTH_TOKEN`` set → every protected route requires
   ``Authorization: Bearer <token>`` and matches with
   ``hmac.compare_digest`` (constant-time). Missing/mismatched → 401.
2. ``AUTH_TOKEN`` unset AND ``ALLOW_ANONYMOUS=1`` (or truthy) → local
   development mode; anonymous access is allowed with a WARNING logged
   once. This is the ergonomic path for ``uvicorn --reload``.
3. ``AUTH_TOKEN`` unset AND ``ALLOW_ANONYMOUS`` unset → fail-closed:
   every protected route returns 503 with a clear misconfig message.

Rationale: PROJECT_REVIEW.md flagged the previous behavior (default
anonymous unless AUTH_TOKEN was set) as a fail-open trap — the shipped
Compose deployment forgot to pass the variable and was silently open.
Fail-closed makes that failure loud instead of silent. Setting
``ALLOW_ANONYMOUS=1`` is a deliberate, greppable acknowledgement in
dev workflows.

The dependency is intentionally minimal: no user model, no sessions.
Anything richer (per-key rate limits, scoped tokens, OAuth) is a
follow-up; this module just closes the anonymous-access hole.
"""

from __future__ import annotations

import hmac
import logging
import os
import threading
from typing import Optional

from fastapi import Header, HTTPException, status

_logger = logging.getLogger(__name__)
_warn_once_lock = threading.Lock()
_warned_anonymous_dev_mode = False

_TRUTHY = frozenset({"1", "true", "yes", "on"})


def _get_configured_token() -> Optional[str]:
    """Return the configured token, or None if auth is not configured."""
    token = os.environ.get("AUTH_TOKEN")
    if token is None:
        return None
    token = token.strip()
    return token or None


def _anonymous_dev_mode() -> bool:
    """Explicit opt-in for anonymous access when no token is configured.

    Must be a deliberate operator choice — never assumed by default —
    so a missing AUTH_TOKEN in a production deployment fails 503
    rather than silently going open.
    """
    return os.environ.get("ALLOW_ANONYMOUS", "").strip().lower() in _TRUTHY


def _warn_anonymous_dev_mode_once() -> None:
    """Emit the 'endpoints are open' warning exactly once per process."""
    global _warned_anonymous_dev_mode
    with _warn_once_lock:
        if _warned_anonymous_dev_mode:
            return
        _warned_anonymous_dev_mode = True
    _logger.warning(
        "ALLOW_ANONYMOUS is set and AUTH_TOKEN is not; report endpoints "
        "are unauthenticated. This is the dev mode contract — never "
        "expose the service on an untrusted network in this state."
    )


def _extract_bearer(authorization: Optional[str]) -> Optional[str]:
    """Parse an ``Authorization: Bearer <token>`` header, tolerating
    whitespace variations. Returns None when the header is absent or
    not a bearer credential."""
    if not authorization:
        return None
    parts = authorization.strip().split(None, 1)
    if len(parts) != 2:
        return None
    scheme, credentials = parts
    if scheme.lower() != "bearer":
        return None
    return credentials.strip() or None


async def require_auth(authorization: Optional[str] = Header(default=None)) -> None:
    """FastAPI dependency: enforce bearer-token auth on the route.

    Behavior:

    * AUTH_TOKEN configured → require ``Authorization: Bearer <token>``,
      401 on missing/mismatched.
    * AUTH_TOKEN unset + ALLOW_ANONYMOUS truthy → allow anonymous with
      a one-shot warning.
    * AUTH_TOKEN unset + ALLOW_ANONYMOUS unset/false → 503 (fail-closed).
    """
    expected = _get_configured_token()
    if expected is None:
        if _anonymous_dev_mode():
            _warn_anonymous_dev_mode_once()
            return
        # Fail-closed: no token AND no explicit dev opt-in. Refuse the
        # request rather than serve it open. 503 signals "server is
        # not correctly configured" — distinguishable from 401 (bad
        # credentials) or 403 (authorization denied), so operators
        # can spot a misconfig in logs immediately.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Server misconfiguration: AUTH_TOKEN is required. Set "
                "AUTH_TOKEN in the environment, or set ALLOW_ANONYMOUS=1 "
                "to permit anonymous access for local development."
            ),
        )

    presented = _extract_bearer(authorization)
    if presented is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    # Constant-time compare so token length / prefix leaks nothing.
    if not hmac.compare_digest(presented.encode("utf-8"), expected.encode("utf-8")):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def reset_warning_state_for_tests() -> None:
    """Test helper: reset the 'warned once' flag so unit tests can
    verify the warning re-fires under a fresh configuration."""
    global _warned_anonymous_dev_mode
    with _warn_once_lock:
        _warned_anonymous_dev_mode = False
