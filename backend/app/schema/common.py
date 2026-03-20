"""Shared schema-mapping utilities used across schema modules."""
from __future__ import annotations

from typing import Any

PLACEHOLDER_COLUMN_TOKENS = {
    "null",
    "none",
    "n/a",
    "na",
    "nil",
    "undefined",
    "unknown",
}


def is_usable_column_name(value: Any) -> bool:
    """Return True when a value is a non-placeholder, non-empty DB column name."""
    if not isinstance(value, str):
        return False
    stripped = value.strip()
    if not stripped:
        return False
    return stripped.lower() not in PLACEHOLDER_COLUMN_TOKENS


def strip_fenced_json(text: str) -> str:
    """Strip optional markdown code fences around JSON payloads."""
    clean = (text or "").strip()
    if clean.startswith("```json"):
        clean = clean[7:]
    if clean.startswith("```"):
        clean = clean[3:]
    if clean.endswith("```"):
        clean = clean[:-3]
    return clean.strip()
