from __future__ import annotations

from typing import Any, Dict, Optional

from flask import Flask, jsonify
from flask_cors import CORS
from sqlalchemy import text
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix

from .config import load_config
from .extensions import db, jwt, limiter
from .routes import register_blueprints

_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    "Cache-Control": "no-store",
}


def create_app(config_overrides: Optional[Dict[str, Any]] = None) -> Flask:
    app = Flask(__name__)
    app.config.update(load_config() if config_overrides is None else {})
    if config_overrides:
        app.config.update(config_overrides)

    proxies = int(app.config.get("TRUSTED_PROXY_COUNT", 0))
    if proxies:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=proxies, x_proto=proxies, x_host=proxies)

    # Auth uses the Authorization header (no cookies), so credentialed CORS is not needed.
    CORS(
        app,
        resources={r"/*": {"origins": app.config.get("CORS_ORIGINS", [])}},
        supports_credentials=False,
        allow_headers=["Content-Type", "Authorization"],
        expose_headers=["Content-Type"],
    )

    db.init_app(app)
    jwt.init_app(app)
    limiter.init_app(app)

    register_blueprints(app)
    _register_hooks(app)

    with app.app_context():
        _init_schema()

    return app


_SCHEMA_LOCK_KEY = 726_001  # arbitrary application-wide advisory-lock id


def _init_schema() -> None:
    """Create tables once even when several gunicorn workers boot on an empty database."""
    if db.engine.dialect.name != "postgresql":
        db.create_all()
        return
    with db.engine.connect() as conn:
        conn.execute(text("SELECT pg_advisory_lock(:key)"), {"key": _SCHEMA_LOCK_KEY})
        try:
            _ensure_uuid_extension()
            db.create_all()
        finally:
            conn.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": _SCHEMA_LOCK_KEY})
            conn.commit()


def _ensure_uuid_extension() -> None:
    """Column server defaults use uuid_generate_v4(); make sure the extension exists on PostgreSQL."""
    if db.engine.dialect.name != "postgresql":
        return
    try:
        db.session.execute(text('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"'))
        db.session.commit()
    except Exception:  # noqa: BLE001 - lacking privilege is fine when the DB was initialised by init_db.sql
        db.session.rollback()


def _register_hooks(app: Flask) -> None:
    @app.after_request
    def add_security_headers(response):
        for header, value in _SECURITY_HEADERS.items():
            response.headers.setdefault(header, value)
        if app.config.get("ENV") == "production":
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        return response

    @app.errorhandler(HTTPException)
    def handle_http_exception(exc: HTTPException):
        return jsonify({"error": exc.name}), exc.code or 500

    @app.errorhandler(Exception)
    def handle_unexpected_exception(exc: Exception):
        app.logger.exception("Unhandled exception: %s", exc)
        return jsonify({"error": "Internal server error"}), 500
