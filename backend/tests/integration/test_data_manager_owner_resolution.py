"""Owner auto-linking: HubSpot lookup by e-mail and SQL fallback by e-mail column."""
from __future__ import annotations

import asyncio
from contextlib import contextmanager

import pytest
import responses
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import ExternalUserMapping
from app.services.data_manager import DataManager

from ..fakes import FakeDriver

run = asyncio.run
OWNERS_URL = "https://api.hubapi.com/crm/v3/owners/"


def hubspot_dm(make_org, make_user, email="ann@acme.test"):
    org = make_org(connector_type="hubspot", connector_config={"api_key": "k"})
    user = make_user(org, email=email)
    driver = FakeDriver({"api_key": "k"})
    dm = DataManager(org, driver)
    dm.authorized_user_id, dm.authorized_user = str(user.id), user
    return dm, user


@responses.activate
def test_hubspot_owner_is_linked_by_email_and_persisted(make_org, make_user):
    dm, user = hubspot_dm(make_org, make_user)
    responses.add(
        responses.GET, OWNERS_URL,
        json={"results": [{"id": "1", "email": "other@x.io"}, {"id": "42", "email": "ANN@acme.test"}]},
    )
    assert run(dm._resolve_external_owner_id()) == "42"
    assert ExternalUserMapping.query.filter_by(user_id=user.id, crm_type="hubspot").one().external_user_id == "42"
    assert responses.calls[0].request.headers["Authorization"] == "Bearer k"
    # second resolution is served from the stored mapping: no extra HTTP call
    assert run(dm._resolve_external_owner_id()) == "42"
    assert len(responses.calls) == 1


@responses.activate
@pytest.mark.parametrize(
    "reply",
    [
        {"status": 500},
        {"json": {"results": []}},
        {"json": {"results": [{"id": "not-numeric", "email": "ann@acme.test"}]}},
        {"json": {"results": [{"id": "x"}, "junk"]}},
    ],
)
def test_hubspot_owner_lookup_failures_return_none(make_org, make_user, reply):
    dm, _ = hubspot_dm(make_org, make_user)
    responses.add(responses.GET, OWNERS_URL, **reply)
    assert run(dm._resolve_external_owner_id()) is None


@responses.activate
def test_hubspot_owner_lookup_network_error_is_swallowed(make_org, make_user):
    dm, _ = hubspot_dm(make_org, make_user)
    responses.add(responses.GET, OWNERS_URL, body=ConnectionError("down"))
    assert run(dm._resolve_external_owner_id()) is None


@responses.activate
def test_hubspot_save_meeting_looks_up_owner_when_unmapped(make_org, make_user):
    dm, user = hubspot_dm(make_org, make_user)
    responses.add(responses.GET, OWNERS_URL, json={"results": [{"id": "77", "email": "ann@acme.test"}]})
    seen = {}
    original = dm.driver.save_meeting

    def spy(user_id, payload):
        seen["owner"] = dm.driver.request_owner_id
        return original(user_id, payload)

    dm.driver.save_meeting = spy
    dm.save_meeting(str(user.id), {"summary": "s"})
    assert seen["owner"] == "77" and dm.driver.request_owner_id is None


@responses.activate
def test_hubspot_save_meeting_survives_lookup_failure(make_org, make_user):
    dm, user = hubspot_dm(make_org, make_user)
    responses.add(responses.GET, OWNERS_URL, body=ConnectionError("down"))
    assert dm.save_meeting(str(user.id), {"summary": "s"})["id"]


# ------------------------------------------------------------------ SQL fallback


class SqlFakeDriver(FakeDriver):
    """FakeDriver with a real (SQLite) engine so the e-mail lookup can run real SQL."""

    def __init__(self, config, engine):
        super().__init__(config)
        self.engine = engine
        self._sessions = sessionmaker(bind=engine)

    @contextmanager
    def get_session(self):
        session = self._sessions()
        try:
            yield session
            session.commit()
        finally:
            session.close()


@pytest.fixture
def sql_dm(make_org, make_user):
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE doctors (doctor_id INTEGER PRIMARY KEY, work_email TEXT)"))
        conn.execute(text("CREATE TABLE patients (id INTEGER PRIMARY KEY, doctor_id INTEGER REFERENCES doctors(doctor_id))"))
        conn.execute(text("INSERT INTO doctors VALUES (5, 'Doc@Acme.test'), (6, 'twin@acme.test'), (7, 'twin@acme.test')"))
    config = {"schema_mappings": {"patient": {"table_name": "patients", "column_mapping": {"title": "id"}}}}
    org = make_org(connector_type="postgresql", connector_config=config)
    user = make_user(org, email="doc@acme.test")
    dm = DataManager(org, SqlFakeDriver(config, engine))
    dm.authorized_user_id, dm.authorized_user = str(user.id), user
    return dm, user


def test_sql_owner_resolved_by_email_column_and_persisted(sql_dm):
    dm, user = sql_dm
    assert run(dm._resolve_external_owner_id(owner_column="doctor_id")) == "5"
    mapping = ExternalUserMapping.query.filter_by(user_id=user.id, crm_type="postgresql").one()
    assert (mapping.external_user_id, mapping.external_email) == ("5", "doc@acme.test")


def test_sql_owner_ambiguous_email_is_not_linked(sql_dm, make_user):
    dm, user = sql_dm
    dm.authorized_user = type("U", (), {"email": "twin@acme.test"})()
    assert run(dm._resolve_external_owner_id()) is None
    assert ExternalUserMapping.query.count() == 0


def test_sql_owner_unknown_email_returns_none(sql_dm):
    dm, _ = sql_dm
    dm.authorized_user = type("U", (), {"email": "nobody@acme.test"})()
    assert run(dm._resolve_external_owner_id()) is None


def test_sql_owner_without_email_returns_none(sql_dm):
    dm, _ = sql_dm
    dm.authorized_user = type("U", (), {"email": None})()
    assert run(dm._resolve_external_owner_id()) is None
