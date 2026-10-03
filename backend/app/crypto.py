"""Encryption at rest for tenant connector credentials.

``EncryptedJSON`` is a drop-in replacement for a JSONB column. Values are stored as
``{"__enc": 1, "v": "<fernet token>"}``. Rows written before encryption was introduced
(plain JSON) are still readable and are encrypted the next time they are saved; run
``python manage.py encrypt-connectors`` to migrate them in bulk.

Key management: ``CONNECTOR_ENCRYPTION_KEY`` holds one or more comma-separated Fernet keys.
The first key encrypts; all keys can decrypt, which allows rotation. Generate a key with
``python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"``.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Optional

from cryptography.fernet import Fernet, MultiFernet
from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import TypeDecorator

logger = logging.getLogger(__name__)

ENCRYPTED_MARKER = "__enc"
_warned_plaintext = False


def _get_fernet() -> Optional[MultiFernet]:
    raw = os.getenv("CONNECTOR_ENCRYPTION_KEY", "").strip()
    if not raw:
        return None
    keys = [Fernet(k.strip().encode()) for k in raw.split(",") if k.strip()]
    return MultiFernet(keys) if keys else None


def is_encrypted_payload(value: Any) -> bool:
    return isinstance(value, dict) and value.get(ENCRYPTED_MARKER) == 1 and "v" in value


def encrypt_value(value: Any) -> Any:
    """Encrypt a JSON-serialisable value; returns it unchanged when no key is configured."""
    global _warned_plaintext
    if value is None:
        return None
    fernet = _get_fernet()
    if fernet is None:
        if not _warned_plaintext:
            logger.warning(
                "CONNECTOR_ENCRYPTION_KEY is not set: connector credentials are stored in plaintext."
            )
            _warned_plaintext = True
        return value
    token = fernet.encrypt(json.dumps(value).encode("utf-8")).decode("utf-8")
    return {ENCRYPTED_MARKER: 1, "v": token}


def decrypt_value(value: Any) -> Any:
    if not is_encrypted_payload(value):
        return value
    fernet = _get_fernet()
    if fernet is None:
        raise RuntimeError("Encrypted connector_config found but CONNECTOR_ENCRYPTION_KEY is not set.")
    return json.loads(fernet.decrypt(value["v"].encode("utf-8")).decode("utf-8"))


class EncryptedJSON(TypeDecorator):
    """JSON(B) column transparently encrypted with Fernet."""

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(JSONB())
        return dialect.type_descriptor(JSON())

    def process_bind_param(self, value, dialect):
        return encrypt_value(value)

    def process_result_value(self, value, dialect):
        return decrypt_value(value)
