import pytest

from app.config import (
    build_postgres_uri,
    load_config,
    parse_cors_origins,
    validate_jwt_secret,
)

STRONG = "x" * 40


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in (
        "ENV",
        "CORS_ORIGINS",
        "DEBUG",
        "JWT_SECRET_KEY",
        "DATABASE_URL",
        "DB_USER",
        "DB_PASSWORD",
        "DB_HOST",
        "DB_PORT",
        "DB_NAME",
        "JWT_ACCESS_TOKEN_EXPIRES_MINUTES",
        "TRUSTED_PROXY_COUNT",
    ):
        monkeypatch.delenv(name, raising=False)


def test_missing_secret_is_rejected():
    with pytest.raises(RuntimeError, match="JWT_SECRET_KEY is required"):
        validate_jwt_secret(None, "development")


@pytest.mark.parametrize("secret", ["dev_secret_key_change_in_production", "short", "CHANGEME"])
def test_weak_secret_rejected_in_production_only(secret):
    with pytest.raises(RuntimeError, match="too weak"):
        validate_jwt_secret(secret, "production")
    assert validate_jwt_secret(secret, "development") == secret


def test_strong_secret_accepted_in_production():
    assert validate_jwt_secret(STRONG, "production") == STRONG


def test_parse_cors_origins():
    assert parse_cors_origins(" http://a.test , ,http://b.test") == ["http://a.test", "http://b.test"]
    assert parse_cors_origins("") == []


def test_build_postgres_uri_lists_missing_variables(monkeypatch):
    monkeypatch.setenv("DB_USER", "u")
    with pytest.raises(RuntimeError) as exc:
        build_postgres_uri()
    assert "DB_PASSWORD" in str(exc.value) and "DB_USER" not in str(exc.value)


def test_build_postgres_uri(monkeypatch):
    for key, value in {"DB_USER": "u", "DB_PASSWORD": "p", "DB_HOST": "h", "DB_PORT": "5432", "DB_NAME": "n"}.items():
        monkeypatch.setenv(key, value)
    assert build_postgres_uri() == "postgresql+psycopg2://u:p@h:5432/n"


def test_load_config_development_defaults(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("JWT_SECRET_KEY", "dev-secret")
    config = load_config()
    assert config["ENV"] == "development"
    assert "*" not in config["CORS_ORIGINS"]
    assert config["SQLALCHEMY_DATABASE_URI"] == "sqlite://"
    assert config["JWT_ACCESS_TOKEN_EXPIRES"].total_seconds() == 480 * 60


def test_load_config_production_requires_explicit_cors(monkeypatch):
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("JWT_SECRET_KEY", STRONG)
    with pytest.raises(RuntimeError, match="CORS_ORIGINS"):
        load_config()
    monkeypatch.setenv("CORS_ORIGINS", "*")
    with pytest.raises(RuntimeError, match="CORS_ORIGINS"):
        load_config()
    monkeypatch.setenv("CORS_ORIGINS", "https://app.example.com")
    assert load_config()["CORS_ORIGINS"] == ["https://app.example.com"]


def test_production_forces_debug_off(monkeypatch):
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("DEBUG", "true")
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("JWT_SECRET_KEY", STRONG)
    monkeypatch.setenv("CORS_ORIGINS", "https://app.example.com")
    assert load_config()["DEBUG"] is False
