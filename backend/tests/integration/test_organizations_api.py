"""Tenant isolation and secret handling on the organization endpoints."""
from __future__ import annotations

from app.extensions import db
from app.models import Organization
from app.security import MASK

SECRET = {"host": "db.example.com", "user": "lia", "password": "s3cr3t-pass", "database": "crm"}


def test_list_requires_auth(client):
    assert client.get("/organizations").status_code == 401


def test_member_lists_only_own_org(client, make_org, member, member_headers):
    make_org(name="Other Co")
    body = client.get("/organizations", headers=member_headers).get_json()
    assert [o["name"] for o in body["organizations"]] == ["Acme"]
    assert "connector_config" not in body["organizations"][0]


def test_admin_lists_all_orgs(client, make_org, admin_headers):
    make_org(name="Other Co")
    names = {o["name"] for o in client.get("/organizations", headers=admin_headers).get_json()["organizations"]}
    assert names == {"Acme", "Other Co"}


def test_member_cannot_read_other_org_and_gets_404_not_403(client, make_org, member_headers):
    other = make_org(name="Other Co", connector_type="postgresql", connector_config=SECRET)
    response = client.get(f"/organizations/{other.id}", headers=member_headers)
    assert response.status_code == 404
    assert "s3cr3t-pass" not in response.get_data(as_text=True)


def test_member_reads_own_org_without_connector_config(client, org, member_headers):
    body = client.get(f"/organizations/{org.id}", headers=member_headers).get_json()["organization"]
    assert body["name"] == "Acme"
    assert "connector_config" not in body


def test_admin_sees_masked_config_never_plaintext(client, make_org, admin_headers):
    other = make_org(name="Other Co", connector_type="postgresql", connector_config=SECRET)
    response = client.get(f"/organizations/{other.id}", headers=admin_headers)
    config = response.get_json()["organization"]["connector_config"]
    assert config["password"] == MASK
    assert config["host"] == "db.example.com"
    assert "s3cr3t-pass" not in response.get_data(as_text=True)


def test_get_unknown_and_malformed_ids(client, admin_headers):
    assert client.get("/organizations/00000000-0000-0000-0000-000000000000", headers=admin_headers).status_code == 404
    assert client.get("/organizations/not-a-uuid", headers=admin_headers).status_code == 400


def test_update_connector_requires_admin_role(client, org, member_headers):
    response = client.patch(
        f"/organizations/{org.id}/connector", headers=member_headers, json={"connector_type": "hubspot", "connector_config": {}}
    )
    assert response.status_code == 403


def test_update_connector_cannot_touch_other_org(client, make_org, admin_headers):
    other = make_org(name="Other Co")
    response = client.patch(
        f"/organizations/{other.id}/connector", headers=admin_headers, json={"connector_type": "hubspot", "connector_config": {}}
    )
    assert response.status_code == 403


def test_update_connector_validates_input(client, org, admin_headers):
    url = f"/organizations/{org.id}/connector"
    assert client.patch(url, headers=admin_headers, json={}).status_code == 400
    assert client.patch(url, headers=admin_headers, json={"connector_type": "oracle"}).status_code == 400
    assert client.patch(url, headers=admin_headers, json={"connector_type": "hubspot", "connector_config": "x"}).status_code == 400
    bad_sf = {"connector_type": "salesforce", "connector_config": {"instance_url": "https://evil.example.com"}}
    assert client.patch(url, headers=admin_headers, json=bad_sf).status_code == 400


def test_update_connector_stores_secrets_but_returns_masked(client, org, admin_headers):
    response = client.patch(
        f"/organizations/{org.id}/connector",
        headers=admin_headers,
        json={"connector_type": "PostgreSQL", "connector_config": SECRET},
    )
    assert response.status_code == 200
    assert response.get_json()["organization"]["connector_config"]["password"] == MASK
    assert "s3cr3t-pass" not in response.get_data(as_text=True)
    db.session.expire_all()
    stored = db.session.get(Organization, org.id)
    assert stored.connector_type == "postgresql"
    assert stored.connector_config["password"] == "s3cr3t-pass"


def test_update_connector_keeps_stored_secret_when_mask_is_echoed_back(client, org, admin_headers):
    url = f"/organizations/{org.id}/connector"
    client.patch(url, headers=admin_headers, json={"connector_type": "postgresql", "connector_config": SECRET})
    echoed = {**SECRET, "password": MASK, "host": "new-host.example.com"}
    assert client.patch(url, headers=admin_headers, json={"connector_type": "postgresql", "connector_config": echoed}).status_code == 200
    db.session.expire_all()
    config = db.session.get(Organization, org.id).connector_config
    assert config["password"] == "s3cr3t-pass" and config["host"] == "new-host.example.com"


def test_private_hosts_rejected_when_policy_enabled(app, client, org, admin_headers, monkeypatch):
    monkeypatch.setitem(app.config, "BLOCK_PRIVATE_CONNECTOR_HOSTS", True)
    response = client.patch(
        f"/organizations/{org.id}/connector",
        headers=admin_headers,
        json={"connector_type": "postgresql", "connector_config": {**SECRET, "host": "localhost"}},
    )
    assert response.status_code == 400
