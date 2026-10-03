import socket

import pytest

from app import security
from app.security import (
    MASK,
    is_valid_email,
    mask_connector_config,
    merge_connector_config,
    normalize_email,
    parse_int_arg,
    validate_connector_config,
    validate_dynamics_config,
    validate_password,
    validate_salesforce_instance_url,
)


def test_mask_hides_secrets_but_keeps_other_values():
    config = {
        "host": "db.internal",
        "user": "lia",
        "password": "hunter2",
        "api_key": "k",
        "client_secret": "s",
        "nested": {"access_token": "t", "port": 5432},
        "empty_password": "",
        "schema_mappings": {"meeting": {"table_name": "calls"}},
    }
    masked = mask_connector_config(config)
    assert masked["host"] == "db.internal" and masked["user"] == "lia"
    assert masked["password"] == masked["api_key"] == masked["client_secret"] == MASK
    assert masked["nested"] == {"access_token": MASK, "port": 5432}
    assert masked["empty_password"] == ""
    assert masked["schema_mappings"] == config["schema_mappings"]
    assert config["password"] == "hunter2"  # input untouched


def test_mask_handles_lists_and_scalars():
    assert mask_connector_config([{"password": "x"}, 1]) == [{"password": MASK}, 1]
    assert mask_connector_config(None) is None


def test_merge_restores_masked_values_and_accepts_new_ones():
    existing = {"host": "old", "password": "stored-secret", "nested": {"token": "stored-token"}}
    incoming = {"host": "new", "password": MASK, "nested": {"token": MASK, "extra": 1}, "api_key": "fresh"}
    merged = merge_connector_config(existing, incoming)
    assert merged == {
        "host": "new",
        "password": "stored-secret",
        "nested": {"token": "stored-token", "extra": 1},
        "api_key": "fresh",
    }


def test_merge_never_persists_the_mask_literal():
    assert merge_connector_config({}, {"password": MASK}) == {}


@pytest.mark.parametrize(
    "value,ok",
    [("a@b.co", True), ("a b@c.de", False), ("nodomain", False), ("", False), ("a@b", False)],
)
def test_is_valid_email(value, ok):
    assert is_valid_email(value) is ok


def test_normalize_email():
    assert normalize_email("  Foo@BAR.com ") == "foo@bar.com"
    assert normalize_email(None) == ""
    assert normalize_email(5) == ""


@pytest.mark.parametrize(
    "password,fragment",
    [(None, "required"), ("", "required"), ("short", "at least 8"), ("é" * 40, "at most 72")],
)
def test_validate_password_rejects(password, fragment):
    assert fragment in validate_password(password)


def test_validate_password_accepts():
    assert validate_password("long-enough-password") is None


@pytest.mark.parametrize("raw,expected", [("5", 5), ("abc", 20), (None, 20), ("-3", 1), ("999", 50)])
def test_parse_int_arg(raw, expected):
    assert parse_int_arg(raw, default=20, minimum=1, maximum=50) == expected


@pytest.mark.parametrize(
    "url,ok",
    [
        ("https://acme.my.salesforce.com", True),
        ("https://test.salesforce.com", True),
        ("https://acme.force.com", True),
        ("http://acme.my.salesforce.com", False),
        ("https://evil.example.com", False),
        ("https://salesforce.com.evil.io", False),
        ("https://evil.io/.salesforce.com", False),
        ("", False),
        (None, False),
    ],
)
def test_salesforce_instance_url(url, ok):
    assert (validate_salesforce_instance_url(url) is None) is ok


def test_salesforce_extra_suffixes_from_env(monkeypatch):
    monkeypatch.setenv("SALESFORCE_EXTRA_HOST_SUFFIXES", ".sf.corp.example")
    assert validate_salesforce_instance_url("https://a.sf.corp.example") is None


@pytest.mark.parametrize(
    "tenant,url,ok",
    [
        ("11111111-2222-3333-4444-555555555555", "https://org.crm4.dynamics.com", True),
        ("contoso.onmicrosoft.com", "https://org.crm.dynamics.com", True),
        ("../evil", "https://org.crm.dynamics.com", False),
        ("tenant/with/slash", "https://org.crm.dynamics.com", False),
        ("11111111-2222-3333-4444-555555555555", "https://evil.example.com", False),
        ("11111111-2222-3333-4444-555555555555", "http://org.crm.dynamics.com", False),
        (None, "https://org.crm.dynamics.com", False),
    ],
)
def test_dynamics_config(tenant, url, ok):
    assert (validate_dynamics_config(tenant, url) is None) is ok


def test_validate_connector_config_type_and_shape():
    assert validate_connector_config("nosql", {}) is not None
    assert validate_connector_config(None, {}) is not None
    assert validate_connector_config("HubSpot", {"api_key": "x"}) is None
    assert validate_connector_config("hubspot", None) is None
    assert validate_connector_config("hubspot", ["x"]) == "connector_config must be an object"
    too_big = {"blob": "x" * (security.MAX_CONNECTOR_CONFIG_CHARS + 1)}
    assert validate_connector_config("hubspot", too_big) == "connector_config is too large"


def test_validate_connector_config_per_type():
    assert validate_connector_config("salesforce", {"instance_url": "https://evil.io"}) is not None
    assert validate_connector_config("salesforce", {"instance_url": "https://a.my.salesforce.com"}) is None
    bad = {"tenant_id": "../x", "dynamics_url": "https://a.crm.dynamics.com"}
    assert validate_connector_config("dynamics", bad) is not None


def test_private_host_blocking(monkeypatch):
    def fake_getaddrinfo(host, *_):
        ip = {"db.internal": "10.0.0.5", "localhost": "127.0.0.1", "db.public": "93.184.216.34"}[host]
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 0))]

    monkeypatch.setattr(security.socket, "getaddrinfo", fake_getaddrinfo)
    for host in ("db.internal", "localhost"):
        assert validate_connector_config("postgresql", {"host": host}, block_private_hosts=True) is not None
    assert validate_connector_config("mysql", {"host": "db.public"}, block_private_hosts=True) is None
    # disabled by default: internal databases are legitimate in many deployments
    assert validate_connector_config("postgresql", {"host": "db.internal"}) is None


def test_private_host_unresolvable_is_not_blocked(monkeypatch):
    def boom(*_):
        raise socket.gaierror("nope")

    monkeypatch.setattr(security.socket, "getaddrinfo", boom)
    assert security._host_is_private("does-not-exist.invalid") is False
