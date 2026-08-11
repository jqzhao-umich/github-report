"""Peer-agent wire format helpers.

Historically the agents serialized dicts by passing them through ``str()``
(effectively ``repr``) and the receiver used ``eval()`` to reconstruct.
That's a Remote Code Execution vector: a malicious or compromised peer can
run arbitrary Python. This module replaces that with a plain-JSON round
trip. The only special case is ``datetime`` objects — encoded as ISO 8601
strings and decoded back to naive/aware datetimes on the read side.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any


class _AgentJSONEncoder(json.JSONEncoder):
    def default(self, obj: Any) -> Any:
        if isinstance(obj, datetime):
            return {"__datetime__": obj.isoformat()}
        return super().default(obj)


def _datetime_hook(dct: dict) -> Any:
    if "__datetime__" in dct and len(dct) == 1:
        return datetime.fromisoformat(dct["__datetime__"])
    return dct


def encode(payload: Any) -> str:
    """Serialize ``payload`` to a wire-safe JSON string.

    Datetimes are wrapped as ``{"__datetime__": iso_string}`` so the reader
    can rehydrate them without ``eval``. Any object json can't handle raises
    a normal TypeError — callers must pass dicts of plain data + datetimes.
    """
    return json.dumps(payload, cls=_AgentJSONEncoder)


def decode(text: str) -> Any:
    """Inverse of :func:`encode`. Never executes untrusted code."""
    return json.loads(text, object_hook=_datetime_hook)
