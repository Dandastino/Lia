import pytest
from cryptography.fernet import Fernet
from sqlalchemy import text

from app import crypto
from app.crypto import decrypt_value, encrypt_value, is_encrypted_payload
from app.extensions import db
from app.models import Organization


@pytest.fixture
def key(monkeypatch):
    value = Fernet.generate_key().decode()
    monkeypatch.setenv("CONNECTOR_ENCRYPTION_KEY", value)
    return value


def test_roundtrip(key):
    secret = {"api_key": "abc", "n": [1, 2]}
    stored = encrypt_value(secret)
    assert is_encrypted_payload(stored)
    assert "abc" not in str(stored)
    assert decrypt_value(stored) == secret


def test_without_key_values_pass_through(monkeypatch):
    monkeypatch.delenv("CONNECTOR_ENCRYPTION_KEY", raising=False)
    assert encrypt_value({"a": 1}) == {"a": 1}
    assert encrypt_value(None) is None


def test_legacy_plaintext_is_readable_with_or_without_key(key):
    assert decrypt_value({"api_key": "plain"}) == {"api_key": "plain"}
    assert decrypt_value(None) is None


def test_encrypted_value_without_key_fails_loudly(key, monkeypatch):
    stored = encrypt_value({"a": 1})
    monkeypatch.delenv("CONNECTOR_ENCRYPTION_KEY")
    with pytest.raises(RuntimeError, match="CONNECTOR_ENCRYPTION_KEY"):
        decrypt_value(stored)


def test_key_rotation(monkeypatch):
    old, new = Fernet.generate_key().decode(), Fernet.generate_key().decode()
    monkeypatch.setenv("CONNECTOR_ENCRYPTION_KEY", old)
    stored = encrypt_value({"a": 1})
    monkeypatch.setenv("CONNECTOR_ENCRYPTION_KEY", f"{new},{old}")
    assert decrypt_value(stored) == {"a": 1}
    rotated = encrypt_value({"a": 1})
    monkeypatch.setenv("CONNECTOR_ENCRYPTION_KEY", new)
    assert decrypt_value(rotated) == {"a": 1}


def test_wrong_key_cannot_decrypt(key, monkeypatch):
    stored = encrypt_value({"a": 1})
    monkeypatch.setenv("CONNECTOR_ENCRYPTION_KEY", Fernet.generate_key().decode())
    with pytest.raises(Exception):  # noqa: B017 - cryptography raises InvalidToken
        decrypt_value(stored)


def test_plaintext_warning_logged_once(monkeypatch, caplog):
    monkeypatch.delenv("CONNECTOR_ENCRYPTION_KEY", raising=False)
    monkeypatch.setattr(crypto, "_warned_plaintext", False)
    with caplog.at_level("WARNING"):
        encrypt_value({"a": 1})
        encrypt_value({"a": 2})
    assert sum("plaintext" in r.message for r in caplog.records) == 1


def test_column_encrypts_at_rest(app, key):
    org = Organization(name="Enc", connector_type="hubspot", connector_config={"api_key": "super-secret-value"})
    db.session.add(org)
    db.session.commit()
    raw = db.session.execute(text("SELECT connector_config FROM organizations")).scalar()
    assert "super-secret-value" not in str(raw)
    db.session.expire_all()
    assert db.session.get(Organization, org.id).connector_config == {"api_key": "super-secret-value"}
