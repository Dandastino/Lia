"""PostgreSQL and MySQL connector drivers against REAL database servers.

Enabled by environment variables (skipped otherwise, so the default suite needs no services):

    POSTGRES_TEST_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/lia_test
    MYSQL_TEST_URL=mysql+pymysql://root:root@localhost:3306/lia_test

The same scenarios run against both dialects.
"""
from __future__ import annotations

import asyncio
import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.drivers.mysql_driver import MySQLDriver
from app.drivers.postgresql_driver import PostgreSQLDriver

pytestmark = pytest.mark.integration

DDL = {
    "postgresql": [
        "DROP TABLE IF EXISTS patients, contacts, doctors, lia_meetings CASCADE",
        "CREATE TABLE doctors (id SERIAL PRIMARY KEY, first_name VARCHAR(50), last_name VARCHAR(50))",
        "CREATE TABLE contacts (id SERIAL PRIMARY KEY, full_name VARCHAR(100) NOT NULL, notes TEXT, "
        "owner_id INTEGER, created_at TIMESTAMPTZ DEFAULT now())",
        "CREATE TABLE patients (id SERIAL PRIMARY KEY, full_name VARCHAR(100) NOT NULL, "
        "doctor_id INTEGER NOT NULL REFERENCES doctors(id))",
        "CREATE TABLE lia_meetings (id VARCHAR(36) PRIMARY KEY, title VARCHAR(255), summary TEXT NOT NULL, "
        "participants JSONB, meeting_metadata JSONB, created_at TIMESTAMPTZ DEFAULT now())",
    ],
    "mysql": [
        "SET FOREIGN_KEY_CHECKS = 0",
        "DROP TABLE IF EXISTS patients, contacts, doctors, lia_meetings",
        "SET FOREIGN_KEY_CHECKS = 1",
        "CREATE TABLE doctors (id INT AUTO_INCREMENT PRIMARY KEY, first_name VARCHAR(50), last_name VARCHAR(50))",
        "CREATE TABLE contacts (id INT AUTO_INCREMENT PRIMARY KEY, full_name VARCHAR(100) NOT NULL, notes TEXT, "
        "owner_id INT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)",
        "CREATE TABLE patients (id INT AUTO_INCREMENT PRIMARY KEY, full_name VARCHAR(100) NOT NULL, "
        "doctor_id INT NOT NULL, FOREIGN KEY (doctor_id) REFERENCES doctors(id))",
        "CREATE TABLE lia_meetings (id VARCHAR(36) PRIMARY KEY, title VARCHAR(255), summary TEXT NOT NULL, "
        "participants JSON, metadata JSON, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)",
    ],
}

CONTACT_MAPPING = {
    "entity_type": "contact",
    "table_name": "contacts",
    "id_column": "id",
    "column_mapping": {"title": "full_name", "summary": "notes", "created_at": "created_at"},
    "table_columns": ["id", "full_name", "notes", "owner_id", "created_at"],
    "owner_column": "owner_id",
}
PATIENT_MAPPING = {
    "entity_type": "patient",
    "table_name": "patients",
    "id_column": "id",
    "column_mapping": {"title": "full_name"},
    "table_columns": ["id", "full_name", "doctor_id"],
}

PROVIDERS = {
    "postgresql": ("POSTGRES_TEST_URL", PostgreSQLDriver),
    "mysql": ("MYSQL_TEST_URL", MySQLDriver),
}


def run(coro):
    return asyncio.run(coro)


@pytest.fixture(params=sorted(PROVIDERS))
def provider(request):
    name = request.param
    env_var, driver_cls = PROVIDERS[name]
    url = os.getenv(env_var)
    if not url:
        pytest.skip(f"{env_var} not set")
    parsed = make_url(url)
    engine = create_engine(url)
    with engine.begin() as conn:
        for statement in DDL[name]:
            conn.execute(text(statement))
    config = {
        "host": parsed.host,
        "port": parsed.port,
        "database": parsed.database,
        "user": parsed.username,
        "password": parsed.password,
        "schema_mappings": {"contact": dict(CONTACT_MAPPING), "patient": dict(PATIENT_MAPPING)},
    }
    config.update({"sslmode": "disable"} if name == "postgresql" else {"ssl": False})
    driver = driver_cls(config)
    yield name, driver, engine
    driver.engine.dispose()
    engine.dispose()


@pytest.fixture
def driver(provider):
    return provider[1]


@pytest.fixture
def engine(provider):
    return provider[2]


def as_owner(driver, owner_id):
    driver.request_owner_column = "owner_id" if owner_id is not None else None
    driver.request_owner_id = owner_id


def test_requires_credentials():
    with pytest.raises(ValueError, match="credentials"):
        PostgreSQLDriver({"host": "x"})
    with pytest.raises(ValueError, match="credentials"):
        MySQLDriver({"host": "x"})


def test_schema_introspection_lists_tables_and_columns(driver):
    schema = run(driver.get_schema_info())
    tables = {t.get("table_name") or t.get("name"): t for t in schema["tables"]}
    assert {"contacts", "patients", "doctors"} <= set(tables)
    assert "full_name" in str(tables["contacts"])


def test_create_and_read_roundtrip(driver):
    created = run(driver.create_entity("contact", {"title": "Alice", "summary": "first call"}))
    assert created["id"] and created["title"] == "Alice" and created["summary"] == "first call"
    rows = run(driver.read_entities("contact"))
    assert [r["title"] for r in rows] == ["Alice"]


def test_create_missing_required_column_gives_actionable_error(driver):
    with pytest.raises(ValueError, match="missing required columns"):
        run(driver.create_entity("contact", {"summary": "no name"}))


def test_values_are_bound_never_interpolated(driver, engine):
    nasty = "Robert'); DROP TABLE contacts;--"
    run(driver.create_entity("contact", {"title": nasty}))
    assert run(driver.read_entities("contact", filters={"title": nasty}))[0]["title"] == nasty
    with engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM contacts")).scalar() == 1


def test_read_filters_limit_and_offset(driver):
    for i in range(5):
        run(driver.create_entity("contact", {"title": f"c{i}"}))
    assert len(run(driver.read_entities("contact", filters={"limit": 2}))) == 2
    page1 = run(driver.read_entities("contact", filters={"limit": 2, "offset": 0}))
    page2 = run(driver.read_entities("contact", filters={"limit": 2, "offset": 2}))
    assert not {r["id"] for r in page1} & {r["id"] for r in page2}
    assert [r["title"] for r in run(driver.read_entities("contact", filters={"title": "c3"}))] == ["c3"]


def test_read_rejects_unknown_and_malicious_filter_columns(driver):
    run(driver.create_entity("contact", {"title": "x"}))
    for key in ("1=1; DROP TABLE contacts; --", "no_such_column", "full_name) OR (1=1"):
        with pytest.raises(ValueError, match="Unknown filter column"):
            run(driver.read_entities("contact", filters={key: "v"}))


def test_limit_injection_is_neutralised(driver):
    run(driver.create_entity("contact", {"title": "x"}))
    rows = run(driver.read_entities("contact", filters={"limit": "1; DROP TABLE contacts"}))
    assert len(rows) == 1
    assert len(run(driver.read_entities("contact"))) == 1  # table still exists


def test_owned_entity_ids_filter(driver):
    ids = [run(driver.create_entity("contact", {"title": f"c{i}"}))["id"] for i in range(3)]
    rows = run(driver.read_entities("contact", filters={"owned_entity_ids": [str(ids[0]), str(ids[2])]}))
    assert sorted(r["id"] for r in rows) == sorted([ids[0], ids[2]])


def test_owner_scope_isolates_rows_between_users(driver):
    as_owner(driver, 1)
    mine = run(driver.create_entity("contact", {"title": "mine"}))
    as_owner(driver, 2)
    theirs = run(driver.create_entity("contact", {"title": "theirs"}))

    as_owner(driver, 1)
    assert [r["title"] for r in run(driver.read_entities("contact"))] == ["mine"]
    as_owner(driver, 2)
    assert [r["title"] for r in run(driver.read_entities("contact"))] == ["theirs"]

    # user 2 can neither update nor delete user 1's row
    with pytest.raises(ValueError, match="not found"):
        run(driver.update_entity("contact", str(mine["id"]), {"title": "hacked"}))
    assert run(driver.delete_entity("contact", str(mine["id"]))) is False

    as_owner(driver, 1)
    assert run(driver.read_entities("contact"))[0]["title"] == "mine"
    assert theirs["id"] != mine["id"]


def test_owner_value_supplied_by_caller_is_overridden(driver, engine):
    as_owner(driver, 1)
    created = run(driver.create_entity("contact", {"title": "spoof", "owner_id": 999}))
    with engine.connect() as conn:
        owner = conn.execute(text("SELECT owner_id FROM contacts WHERE id = :i"), {"i": created["id"]}).scalar()
    assert owner == 1


def test_update_and_delete(driver):
    created = run(driver.create_entity("contact", {"title": "old"}))
    updated = run(driver.update_entity("contact", str(created["id"]), {"title": "new", "summary": "s"}))
    assert updated["title"] == "new" and updated["summary"] == "s"
    assert run(driver.delete_entity("contact", str(created["id"]))) is True
    assert run(driver.delete_entity("contact", str(created["id"]))) is False
    with pytest.raises(ValueError):
        run(driver.update_entity("contact", str(created["id"]), {"title": "ghost"}))


def test_update_with_no_valid_fields(driver):
    created = run(driver.create_entity("contact", {"title": "x"}))
    with pytest.raises(ValueError, match="No fields to update"):
        run(driver.update_entity("contact", str(created["id"]), {"bogus": 1}))


def test_unmapped_entity_type(driver):
    with pytest.raises(ValueError, match="No schema mapping"):
        run(driver.read_entities("deal"))


def test_foreign_key_resolved_from_name_hint(driver, engine):
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO doctors (first_name, last_name) VALUES ('Ada', 'Lovelace'), ('Alan', 'Turing')"))
    created = run(driver.create_entity("patient", {"title": "Pat", "related_entities": {"doctor": "Ada Lovelace"}}))
    assert created["title"] == "Pat"
    with engine.connect() as conn:
        doctor = conn.execute(
            text("SELECT d.last_name FROM patients p JOIN doctors d ON d.id = p.doctor_id")
        ).scalar()
    assert doctor == "Lovelace"


def test_foreign_key_unresolved_hint_fails_fast(driver, engine):
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO doctors (first_name, last_name) VALUES ('Ada', 'Lovelace')"))
    with pytest.raises(ValueError, match="unresolved relationship hints"):
        run(driver.create_entity("patient", {"title": "Pat", "related_entities": {"doctor": "Nobody Known"}}))


def test_foreign_key_required_but_missing(driver):
    with pytest.raises(ValueError, match="missing required columns"):
        run(driver.create_entity("patient", {"title": "Pat"}))


def test_legacy_meeting_save_and_history(driver):
    saved = driver.save_meeting("user-1", {"title": "Kickoff", "summary": "Plan", "participants": ["a", "b"], "metadata": {"k": 1}})
    assert saved["title"] == "Kickoff" and saved["id"]
    driver.save_meeting("user-1", {"title": "Second", "summary": "More"})
    history = driver.get_meeting_history("user-1")
    assert {m["title"] for m in history} == {"Kickoff", "Second"}
    assert len(driver.get_meeting_history("user-1", {"limit": 1})) == 1
    scoped = driver.get_meeting_history("user-1", {"owned_entity_ids": [saved["id"]]})
    assert [m["id"] for m in scoped] == [saved["id"]]
    assert driver.get_meeting_history("user-1", {"start_date": "2999-01-01"}) == []
    assert len(driver.get_meeting_history("user-1", {"end_date": "2999-01-01"})) == 2


def test_failed_connection_raises_quickly():
    bad = {"host": "127.0.0.1", "port": 1, "database": "x", "user": "u", "password": "p", "connect_timeout": 1, "sslmode": "disable"}
    driver = PostgreSQLDriver(bad)
    with pytest.raises(Exception):  # noqa: B017 - any driver-level connection error is acceptable
        run(driver.get_schema_info())
