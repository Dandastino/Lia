"""Shared input validation and secret-handling helpers."""
from __future__ import annotations

import copy
import ipaddress
import logging
import os
import re
import socket
from typing import Any, Optional
from urllib.parse import urlparse

from flask import jsonify
from sqlalchemy.exc import StatementError

logger = logging.getLogger(__name__)

MASK = "********"
ALLOWED_ROLES = {"user", "admin", "owner"}
ALLOWED_CONNECTOR_TYPES = {"internal", "postgresql", "mysql", "hubspot", "salesforce", "dynamics"}
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 72  # bcrypt ignores bytes beyond 72
MAX_CONNECTOR_CONFIG_CHARS = 256 * 1024

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_SECRET_KEY_TOKENS = ("password", "secret", "token", "api_key", "apikey", "private_key", "credential")
_SALESFORCE_HOST_SUFFIXES = (".salesforce.com", ".force.com", ".salesforce.mil")
_DYNAMICS_HOST_SUFFIXES = (".dynamics.com", ".dynamics.cn", ".microsoftdynamics.us", ".microsoftdynamics.de")
_TENANT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.\-]{0,252}$")


def server_error(exc: Exception, message: str = "Internal server error"):
    """Log the real exception, return a generic body (never leak internals to clients)."""
    if isinstance(exc, StatementError) and isinstance(exc.orig, ValueError):
        # e.g. a malformed UUID in the URL or in a JWT identity
        return jsonify({"error": "Invalid identifier"}), 400
    logger.exception("Unhandled error: %s", exc)
    return jsonify({"error": message}), 500


def parse_int_arg(raw: Any, default: int, minimum: int, maximum: int) -> int:
    """Parse an integer query argument, clamping to [minimum, maximum]; default on garbage."""
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(value, maximum))


def normalize_email(value: Any) -> str:
    return value.strip().lower() if isinstance(value, str) else ""


def is_valid_email(value: str) -> bool:
    return bool(value) and len(value) <= 255 and bool(_EMAIL_RE.match(value))


def validate_password(password: Any) -> Optional[str]:
    """Return an error message if the password is unacceptable, otherwise None."""
    if not isinstance(password, str) or not password:
        return "Password is required"
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"Password must be at least {MIN_PASSWORD_LENGTH} characters"
    if len(password.encode("utf-8")) > MAX_PASSWORD_LENGTH:
        return f"Password must be at most {MAX_PASSWORD_LENGTH} bytes"
    return None


def _is_secret_key(name: Any) -> bool:
    lowered = str(name).lower()
    return any(token in lowered for token in _SECRET_KEY_TOKENS)


def mask_connector_config(config: Any) -> Any:
    """Return a copy of ``config`` with secret values replaced by ``MASK``."""
    if isinstance(config, dict):
        masked = {}
        for key, value in config.items():
            if _is_secret_key(key) and value not in (None, "") and not isinstance(value, (dict, list)):
                masked[key] = MASK
            else:
                masked[key] = mask_connector_config(value)
        return masked
    if isinstance(config, list):
        return [mask_connector_config(v) for v in config]
    return config


def merge_connector_config(existing: Any, incoming: Any) -> Any:
    """Restore values the client echoed back as ``MASK`` from the stored config."""
    if isinstance(incoming, dict):
        existing_dict = existing if isinstance(existing, dict) else {}
        merged = {}
        for key, value in incoming.items():
            if value == MASK:
                if key in existing_dict:
                    merged[key] = copy.deepcopy(existing_dict[key])
                continue
            merged[key] = merge_connector_config(existing_dict.get(key), value)
        return merged
    return incoming


def _host_is_private(host: str) -> bool:
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            return True
    return False


def validate_salesforce_instance_url(url: Any) -> Optional[str]:
    """Salesforce credentials are posted to ``instance_url``; restrict it to Salesforce domains."""
    if not isinstance(url, str) or not url:
        return "instance_url is required"
    parsed = urlparse(url)
    suffixes = _SALESFORCE_HOST_SUFFIXES + tuple(
        s.strip() for s in os.getenv("SALESFORCE_EXTRA_HOST_SUFFIXES", "").split(",") if s.strip()
    )
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not any(host.endswith(s) for s in suffixes):
        return "instance_url must be an https URL on a Salesforce domain"
    return None


def validate_dynamics_config(tenant_id: Any, dynamics_url: Any) -> Optional[str]:
    """Bearer tokens are sent to ``dynamics_url`` and ``tenant_id`` is part of a URL path."""
    if not isinstance(tenant_id, str) or not _TENANT_ID_RE.match(tenant_id):
        return "tenant_id is invalid"
    parsed = urlparse(dynamics_url) if isinstance(dynamics_url, str) else None
    host = ((parsed.hostname if parsed else "") or "").lower()
    if not parsed or parsed.scheme != "https" or not any(host.endswith(s) for s in _DYNAMICS_HOST_SUFFIXES):
        return "dynamics_url must be an https URL on a Dynamics 365 domain"
    return None


def validate_connector_config(
    connector_type: Any,
    config: Any,
    block_private_hosts: bool = False,
) -> Optional[str]:
    """Validate connector type/config coming from an API client. Returns an error or None."""
    if not isinstance(connector_type, str) or connector_type.lower() not in ALLOWED_CONNECTOR_TYPES:
        return f"connector_type must be one of: {', '.join(sorted(ALLOWED_CONNECTOR_TYPES))}"
    if config is None:
        return None
    if not isinstance(config, dict):
        return "connector_config must be an object"
    if len(str(config)) > MAX_CONNECTOR_CONFIG_CHARS:
        return "connector_config is too large"

    ctype = connector_type.lower()
    if ctype == "salesforce" and config.get("instance_url"):
        error = validate_salesforce_instance_url(config.get("instance_url"))
        if error:
            return error
    if ctype == "dynamics" and (config.get("dynamics_url") or config.get("tenant_id")):
        error = validate_dynamics_config(config.get("tenant_id"), config.get("dynamics_url"))
        if error:
            return error
    if block_private_hosts and ctype in {"postgresql", "mysql"} and config.get("host"):
        if _host_is_private(str(config["host"])):
            return "connector host resolves to a private or loopback address"
    return None
