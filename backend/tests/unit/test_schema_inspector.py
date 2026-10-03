import asyncio

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from app.schema.inspector import BaseSQLSchemaInspector, SchemaInspector

run = asyncio.run


@pytest.fixture
def inspector():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE doctors (id INTEGER PRIMARY KEY, name TEXT)"))
        conn.execute(
            text(
                "CREATE TABLE patients (pid INTEGER PRIMARY KEY, name TEXT NOT NULL, doctor_id INTEGER "
                "REFERENCES doctors(id))"
            )
        )
        conn.execute(text("CREATE INDEX idx_patients_name ON patients(name)"))
        conn.execute(text("CREATE TABLE no_pk (a TEXT)"))
    return BaseSQLSchemaInspector(engine)


def test_abstract_base_cannot_be_instantiated():
    with pytest.raises(TypeError):
        SchemaInspector()


def test_introspect_tables(inspector):
    tables = {t["name"]: t for t in run(inspector.introspect_tables())}
    assert set(tables) == {"doctors", "patients", "no_pk"}
    assert tables["patients"]["columns"] == ["pid", "name", "doctor_id"]
    assert "INTEGER" in tables["patients"]["column_types"]["pid"]


def test_introspect_table_details(inspector):
    detail = run(inspector.introspect_table("patients"))
    assert detail["primary_keys"] == ["pid"]
    assert [c["name"] for c in detail["columns"]] == ["pid", "name", "doctor_id"]
    assert next(c for c in detail["columns"] if c["name"] == "name")["nullable"] is False
    assert detail["foreign_keys"][0]["referred_table"] == "doctors"
    assert any(i["name"] == "idx_patients_name" for i in detail["indexes"])


def test_infer_id_column(inspector):
    assert run(inspector.infer_id_column("patients")) == "pid"
    assert run(inspector.infer_id_column("no_pk")) is None
