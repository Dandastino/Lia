"""Meetings, generic entity CRUD and LiveKit token routes (driver replaced by an in-memory fake)."""
from __future__ import annotations

import copy

import jwt as pyjwt
import pytest

from app.models import DatabaseDriver
from app.services import data_manager as dm_module
from app.services.data_manager import DataManager

from ..fakes import MEETING_MAPPING, FakeDriver


@pytest.fixture
def fake_driver(monkeypatch):
    driver = FakeDriver()
    monkeypatch.setattr(dm_module, "PostgreSQLDriver", lambda config: _bind(driver, config))
    return driver


def _bind(driver, config):
    driver.config = copy.deepcopy(config)
    return driver


@pytest.fixture
def pg_org(make_org):
    return make_org(connector_type="postgresql", connector_config={"schema_mappings": {"meeting": copy.deepcopy(MEETING_MAPPING)}})


@pytest.fixture
def doc(make_user, pg_org):
    return make_user(pg_org, email="doc@acme.test")


@pytest.fixture
def doc_headers(login, doc):
    return login(doc.email)


# ------------------------------------------------------------------ livekit


def test_get_token_requires_auth(client):
    assert client.get("/getToken").status_code == 401


def test_get_token_ignores_client_supplied_room(client, member, member_headers, monkeypatch):
    monkeypatch.setenv("LIVEKIT_API_KEY", "devkey")
    monkeypatch.setenv("LIVEKIT_API_SECRET", "s" * 40)
    monkeypatch.setenv("LIVEKIT_URL", "wss://lk.example.com")
    body = client.get("/getToken?room=victim-room&name=" + "x" * 500, headers=member_headers).get_json()
    assert body["room"].startswith("room-") and body["room"] != "victim-room" and len(body["room"]) == 37
    assert body["url"] == "wss://lk.example.com"
    claims = pyjwt.decode(body["token"], "s" * 40, algorithms=["HS256"])
    assert claims["sub"] == f"User_{member.id}"
    assert claims["video"]["room"] == body["room"] and claims["video"]["roomJoin"] is True
    assert len(claims["name"]) == 64
    assert claims["exp"] - claims["nbf"] <= 3600


def test_each_token_gets_a_fresh_unguessable_room(client, member_headers, monkeypatch):
    monkeypatch.setenv("LIVEKIT_API_KEY", "devkey")
    monkeypatch.setenv("LIVEKIT_API_SECRET", "s" * 40)
    rooms = {client.get("/getToken", headers=member_headers).get_json()["room"] for _ in range(5)}
    assert len(rooms) == 5


def test_get_token_missing_credentials_is_generic_500(client, member_headers, monkeypatch):
    monkeypatch.delenv("LIVEKIT_API_KEY", raising=False)
    monkeypatch.delenv("LIVEKIT_API_SECRET", raising=False)
    response = client.get("/getToken", headers=member_headers)
    assert response.status_code == 500
    assert response.get_json() == {"error": "Internal server error"}


# ------------------------------------------------------------------ meetings


def test_meetings_require_auth(client):
    assert client.get("/meetings").status_code == 401
    assert client.post("/meetings", json={"summary": "x"}).status_code == 401


def test_create_and_list_meetings(client, fake_driver, doc_headers, pg_org):
    created = client.post("/meetings", headers=doc_headers, json={"title": "Kickoff", "summary": "Plan", "participants": ["a@b.co"]})
    assert created.status_code == 201
    body = created.get_json()
    assert body["org"] == "Acme" and body["meeting"]["title"] == "Kickoff"
    listing = client.get("/meetings?limit=5", headers=doc_headers).get_json()
    assert listing["user_email"] == "doc@acme.test" and len(listing["meetings"]) == 1


def test_create_meeting_defaults_title_and_requires_summary(client, fake_driver, doc_headers):
    assert client.post("/meetings", headers=doc_headers, json={"title": "x"}).status_code == 400
    client.post("/meetings", headers=doc_headers, json={"summary": "only summary"})
    assert fake_driver.rows[0]["title"] == "Meeting"


@pytest.mark.parametrize("limit,expected", [("abc", 20), ("0", 1), ("9999", 50)])
def test_meeting_limit_is_sanitised(client, fake_driver, doc_headers, limit, expected):
    client.get(f"/meetings?limit={limit}", headers=doc_headers)
    sent = [c for c in fake_driver.calls if c[0] == "prepare"][0][1]
    assert sent["limit"] == expected


def test_meeting_errors_do_not_leak_internals(client, fake_driver, doc_headers):
    fake_driver.fail_with = RuntimeError("password=hunter2 host=10.0.0.5")
    response = client.post("/meetings", headers=doc_headers, json={"summary": "x"})
    assert response.status_code == 500
    assert "hunter2" not in response.get_data(as_text=True)


def test_user_without_org_cannot_use_meetings(client, make_user, login):
    make_user(None, email="orphan@acme.test")
    # login itself refuses users without an organization
    assert client.post("/login", json={"email": "orphan@acme.test", "password": "CorrectHorse1"}).status_code == 403


def test_org_id_mismatch_in_request_is_forbidden(client, fake_driver, doc_headers, make_org):
    other = make_org(name="Other")
    response = client.get(f"/meetings?org_id={other.id}", headers=doc_headers)
    assert response.status_code == 403
    assert response.get_json() == {"error": "Forbidden"}


# ------------------------------------------------------------------ entities


def own(user, entity_id, entity_type="meeting"):
    DatabaseDriver().assign_entity_to_user(user.id, user.org_id, entity_type, entity_id)


def test_entities_require_auth(client):
    assert client.get("/entities/meeting").status_code == 401


def test_create_entity_assigns_ownership(client, fake_driver, doc_headers, doc):
    response = client.post("/entities/meeting", headers=doc_headers, json={"title": "T", "summary": "S"})
    assert response.status_code == 201
    assert DatabaseDriver().user_owns_entity(doc.id, "meeting", response.get_json()["id"])
    assert client.post("/entities/meeting", headers=doc_headers, json={}).status_code == 400


def test_create_entity_value_error_is_400(client, fake_driver, doc_headers):
    fake_driver.fail_with = ValueError("missing required columns ['title']")
    response = client.post("/entities/meeting", headers=doc_headers, json={"summary": "S"})
    assert response.status_code == 400 and "title" in response.get_json()["error"]


def test_list_only_returns_owned_entities(client, fake_driver, doc_headers, doc):
    fake_driver.rows = [{"id": "1", "title": "mine"}, {"id": "2", "title": "not mine"}]
    own(doc, "1")
    rows = client.get("/entities/meeting", headers=doc_headers).get_json()
    assert [r["id"] for r in rows] == ["1"]
    read = [c for c in fake_driver.calls if c[0] == "read"][0]
    assert read[3]["owned_entity_ids"] == ["1"]


def test_list_with_no_ownership_returns_empty(client, fake_driver, doc_headers):
    assert client.get("/entities/meeting", headers=doc_headers).get_json() == []


def test_list_pagination_params_are_sanitised(client, fake_driver, doc_headers, doc):
    own(doc, "1")
    fake_driver.rows = [{"id": "1"}]
    client.get("/entities/meeting?limit=100000&offset=-3", headers=doc_headers)
    read = [c for c in fake_driver.calls if c[0] == "read"][0]
    assert read[3]["limit"] == 100 and read[3]["offset"] == 0


def test_cannot_get_update_or_delete_unowned_entity(client, fake_driver, doc_headers):
    fake_driver.rows = [{"id": "9", "title": "secret"}]
    assert client.get("/entities/meeting/9", headers=doc_headers).status_code == 403
    assert client.put("/entities/meeting/9", headers=doc_headers, json={"title": "x"}).status_code == 403
    assert client.delete("/entities/meeting/9", headers=doc_headers).status_code == 403
    assert fake_driver.rows[0]["title"] == "secret"


def test_get_update_delete_owned_entity(client, fake_driver, doc_headers, doc):
    fake_driver.rows = [{"id": "5", "title": "mine"}]
    own(doc, "5")
    assert client.get("/entities/meeting/5", headers=doc_headers).get_json()["title"] == "mine"
    assert client.put("/entities/meeting/5", headers=doc_headers, json={"title": "new"}).get_json()["title"] == "new"
    assert client.put("/entities/meeting/5", headers=doc_headers, json={}).status_code == 400
    assert client.delete("/entities/meeting/5", headers=doc_headers).get_json() == {"success": True}
    assert not DatabaseDriver().user_owns_entity(doc.id, "meeting", "5")


def test_get_owned_but_vanished_entity_is_404(client, fake_driver, doc_headers, doc):
    own(doc, "404")
    assert client.get("/entities/meeting/404", headers=doc_headers).status_code == 404


def test_delete_failure_is_reported(client, fake_driver, doc_headers, doc):
    own(doc, "7")  # owned in Lia, but already gone in the external system
    assert client.delete("/entities/meeting/7", headers=doc_headers).status_code == 500


def test_entity_routes_do_not_leak_driver_errors(client, fake_driver, doc_headers, doc):
    own(doc, "1")
    fake_driver.fail_with = RuntimeError("connection string postgresql://u:pw@10.0.0.9/db")
    for response in (
        client.get("/entities/meeting", headers=doc_headers),
        client.get("/entities/meeting/1", headers=doc_headers),
        client.put("/entities/meeting/1", headers=doc_headers, json={"title": "x"}),
        client.delete("/entities/meeting/1", headers=doc_headers),
    ):
        assert response.status_code == 500
        assert "pw@" not in response.get_data(as_text=True)


def test_tenant_isolation_between_two_users_of_same_org(client, fake_driver, doc_headers, doc, make_user, pg_org, login):
    fake_driver.rows = [{"id": "1", "title": "doc's"}]
    own(doc, "1")
    colleague = make_user(pg_org, email="colleague@acme.test")
    headers = login(colleague.email)
    assert client.get("/entities/meeting", headers=headers).get_json() == []
    assert client.get("/entities/meeting/1", headers=headers).status_code == 403
    assert DataManager is not None
