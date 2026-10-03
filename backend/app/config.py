from __future__ import annotations

import os
from datetime import timedelta
from typing import Any, Dict, List

from dotenv import load_dotenv

load_dotenv()

# Values that have shipped in docs/compose files; never acceptable in production.
_KNOWN_WEAK_SECRETS = {
    "dev_secret_key_change_in_production",
    "your_secret_key_change_this",
    "changeme",
    "secret",
}
_MIN_SECRET_LENGTH = 32
_DEV_CORS_ORIGINS = "http://localhost:3000,http://localhost:3001,http://localhost:5173"


def build_postgres_uri() -> str:
    user = os.getenv("DB_USER")
    password = os.getenv("DB_PASSWORD")
    host = os.getenv("DB_HOST")
    port = os.getenv("DB_PORT")
    dbname = os.getenv("DB_NAME")
    missing = [
        k
        for k, v in [
            ("DB_USER", user),
            ("DB_PASSWORD", password),
            ("DB_HOST", host),
            ("DB_PORT", port),
            ("DB_NAME", dbname),
        ]
        if not v
    ]
    if missing:
        raise RuntimeError(
            f"Missing required environment variables for DB config: {', '.join(missing)}"
        )
    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{dbname}"


def _env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def parse_cors_origins(raw: str) -> List[str]:
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


def validate_jwt_secret(secret: str | None, env: str) -> str:
    """Return the secret if acceptable, otherwise raise RuntimeError."""
    if not secret:
        raise RuntimeError("JWT_SECRET_KEY is required. Generate one with: openssl rand -hex 32")
    if env == "production":
        if secret.lower() in _KNOWN_WEAK_SECRETS or len(secret) < _MIN_SECRET_LENGTH:
            raise RuntimeError(
                f"JWT_SECRET_KEY is too weak for production (need >= {_MIN_SECRET_LENGTH} chars, "
                "not a documented placeholder)."
            )
    return secret


def load_config() -> Dict[str, Any]:
    """Build the Flask configuration from the environment, failing fast when unsafe."""
    env = os.getenv("ENV", "development").strip().lower()
    cors_raw = os.getenv("CORS_ORIGINS", "" if env == "production" else _DEV_CORS_ORIGINS)
    cors_origins = parse_cors_origins(cors_raw)
    if env == "production" and (not cors_origins or "*" in cors_origins):
        raise RuntimeError("CORS_ORIGINS must list explicit origins in production (no '*').")

    debug = _env_bool("DEBUG", False)
    if env == "production":
        debug = False

    return {
        "SQLALCHEMY_DATABASE_URI": os.getenv("DATABASE_URL") or build_postgres_uri(),
        "SQLALCHEMY_TRACK_MODIFICATIONS": False,
        "JWT_SECRET_KEY": validate_jwt_secret(os.getenv("JWT_SECRET_KEY"), env),
        "JWT_ACCESS_TOKEN_EXPIRES": timedelta(
            minutes=int(os.getenv("JWT_ACCESS_TOKEN_EXPIRES_MINUTES", "480"))
        ),
        "CORS_ORIGINS": cors_origins,
        "DEBUG": debug,
        "ENV": env,
        "MAX_CONTENT_LENGTH": int(os.getenv("MAX_CONTENT_LENGTH", str(1024 * 1024))),
        "RATELIMIT_STORAGE_URI": os.getenv("RATELIMIT_STORAGE_URI", "memory://"),
        "RATELIMIT_ENABLED": _env_bool("RATELIMIT_ENABLED", True),
        "LOGIN_RATE_LIMIT": os.getenv("LOGIN_RATE_LIMIT", "5 per minute;30 per hour"),
        "TRUSTED_PROXY_COUNT": int(os.getenv("TRUSTED_PROXY_COUNT", "0")),
        "BLOCK_PRIVATE_CONNECTOR_HOSTS": _env_bool("BLOCK_PRIVATE_CONNECTOR_HOSTS", False),
    }
