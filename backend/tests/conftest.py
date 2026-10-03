"""Shared fixtures.

The Flask app runs against an in-memory SQLite database so the API test-suite needs no
external service. Tests that need a real PostgreSQL/MySQL server live in
``tests/integration`` and are driven by ``POSTGRES_TEST_URL`` / ``MYSQL_TEST_URL``.
"""
from __future__ import annotations

import functools
import os
import sys
from datetime import timedelta
from pathlib import Path

import bcrypt
import pytest
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.pop("CONNECTOR_ENCRYPTION_KEY", None)

# Cheap bcrypt cost keeps the suite fast; production uses the library default (12 rounds).
bcrypt.gensalt = functools.partial(bcrypt.gensalt, rounds=4)

from app import create_app  # noqa: E402
from app.extensions import db as _db  # noqa: E402
from app.models import Organization, User  # noqa: E402

TEST_PASSWORD = "CorrectHorse1"


def build_test_config(**overrides):
    config = {
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite://",
        "SQLALCHEMY_ENGINE_OPTIONS": {
            "poolclass": StaticPool,
            "connect_args": {"check_same_thread": False},
        },
        "SQLALCHEMY_TRACK_MODIFICATIONS": False,
        "JWT_SECRET_KEY": "test-secret-key-test-secret-key-0123456789",
        "JWT_ACCESS_TOKEN_EXPIRES": timedelta(minutes=5),
        "CORS_ORIGINS": ["http://localhost:3000"],
        "ENV": "testing",
        "DEBUG": False,
        "MAX_CONTENT_LENGTH": 1024 * 1024,
        "RATELIMIT_ENABLED": False,
        "RATELIMIT_STORAGE_URI": "memory://",
        "LOGIN_RATE_LIMIT": "5 per minute",
        "TRUSTED_PROXY_COUNT": 0,
        "BLOCK_PRIVATE_CONNECTOR_HOSTS": False,
    }
    config.update(overrides)
    return config


def _register_test_routes(app):
    """Routes that exercise the authorization decorators in isolation."""
    from flask import jsonify
    from flask_jwt_extended import jwt_required

    from app.tools import authorization as authz

    @app.route("/_t/admin")
    @jwt_required()
    @authz.require_admin
    def _admin_only(admin_user):
        return jsonify({"admin": admin_user.email})

    @app.route("/_t/scoped")
    @jwt_required()
    @authz.require_auth_user
    def _scoped(authorized_user, authorized_org):
        return jsonify({"org": authorized_org.name, "user": authorized_user.email})


@pytest.fixture(scope="session")
def app():
    application = create_app(build_test_config())
    _register_test_routes(application)
    return application


@pytest.fixture(autouse=True)
def _clean_db(app):
    with app.app_context():
        _db.drop_all()
        _db.create_all()
        yield
        _db.session.remove()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def make_org(app):
    def _make(name="Acme", connector_type="internal", connector_config=None, industry="Tech"):
        org = Organization(
            name=name,
            industry=industry,
            connector_type=connector_type,
            connector_config=connector_config if connector_config is not None else {},
        )
        _db.session.add(org)
        _db.session.commit()
        return org

    return _make


@pytest.fixture
def make_user(app):
    def _make(org, email="user@acme.test", role="user", password=TEST_PASSWORD):
        user = User(email=email, org_id=org.id if org else None, role=role)
        user.set_password(password)
        _db.session.add(user)
        _db.session.commit()
        return user

    return _make


@pytest.fixture
def login(client):
    def _login(email, password=TEST_PASSWORD):
        response = client.post("/login", json={"email": email, "password": password})
        assert response.status_code == 200, response.get_json()
        return {"Authorization": f"Bearer {response.get_json()['access_token']}"}

    return _login


@pytest.fixture
def org(make_org):
    return make_org()


@pytest.fixture
def admin(make_user, org):
    return make_user(org, email="admin@acme.test", role="admin")


@pytest.fixture
def member(make_user, org):
    return make_user(org, email="member@acme.test", role="user")


@pytest.fixture
def admin_headers(login, admin):
    return login(admin.email)


@pytest.fixture
def member_headers(login, member):
    return login(member.email)
