"""Redaction helpers for operational audit metadata."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

REDACTED = "[REDACTED]"

_SECRET_KEY_RE = re.compile(
    r"(api[_-]?key|authorization|callback[_-]?secret|cookie|download[_-]?token|dsn|"
    r"password|passwd|secret|token)",
    re.IGNORECASE,
)
_ADDRESS_KEY_RE = re.compile(
    r"(address|addr|jibun|roadaddr|road_address|parcel_address|query|keyword)",
    re.IGNORECASE,
)


def redact_audit_payload(payload: Mapping[str, Any] | None) -> tuple[dict[str, Any], str]:
    """Return a redacted JSON payload and a canonical hash of the original payload."""

    raw: Mapping[str, Any] = payload or {}
    return _redact_mapping(raw), canonical_payload_hash(raw)


def canonical_payload_hash(payload: Any) -> str:
    """Hash a payload after stable JSON canonicalization."""

    encoded = json.dumps(
        _json_safe(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def hash_confirmation(confirmation: str) -> str:
    """Hash a typed confirmation string before persistence."""

    return hashlib.sha256(confirmation.encode("utf-8")).hexdigest()


def hash_identifier(value: str) -> str:
    """Hash IP/user-agent-like identifiers without keeping the original text."""

    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _redact_mapping(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {str(key): _redact_value(str(key), value) for key, value in payload.items()}


def _redact_value(key: str, value: Any) -> Any:
    if _SECRET_KEY_RE.search(key):
        return REDACTED
    if _ADDRESS_KEY_RE.search(key) and isinstance(value, str):
        return _hash_marker(value, label="ADDRESS")
    if isinstance(value, Mapping):
        return _redact_mapping(value)
    if isinstance(value, str):
        return value
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return [_redact_value(key, item) for item in value]
    return _json_safe(value)


def _hash_marker(value: str, *, label: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return f"[{label}_SHA256:{digest[:16]}:LEN:{len(value)}]"


def _json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)
