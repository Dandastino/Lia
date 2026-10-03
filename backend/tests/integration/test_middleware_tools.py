"""Agent tool layer (what the LLM can call): payload shaping, strategy selection, error handling."""
from __future__ import annotations

import asyncio
import copy
from datetime import date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine

from app.models import DatabaseDriver
from app.services import data_manager as dm_module
from app.tools.middleware import MiddlewareTools
from app.tools.middleware_base import BaseMiddlewareTools
from app.tools.middleware_crm import CRMMiddlewareTools
from app.tools.middleware_factory import resolve_middleware_class
from app.tools.middleware_sql import SQLMiddlewareTools

from ..fakes import MEETING_MAPPING, FakeDriver

run = asyncio.run


@pytest.fixture
def driver(monkeypatch):
    fake = FakeDriver()
    for name in ("PostgreSQLDriver", "MySQLDriver", "HubSpotDriver", "SalesforceDriver", "DynamicsDriver"):
        monkeypatch.setattr(dm_module, name, lambda config, _fake=fake: _bind(_fake, config))
    return fake


def _bind(fake, config):
    fake.config = copy.deepcopy(config)
    return fake


def make_tools(make_org, make_user, connector="postgresql", cls=None):
    org = make_org(connector_type=connector, connector_config={"schema_mappings": {"meeting": copy.deepcopy(MEETING_MAPPING)}})
    user = make_user(org, email=f"{connector}@acme.test")
    tools = (cls or MiddlewareTools)(str(user.id))
    return tools, user


@pytest.mark.parametrize(
    "connector,expected",
    [("postgresql", SQLMiddlewareTools), ("mysql", SQLMiddlewareTools), ("hubspot", CRMMiddlewareTools),
     ("salesforce", CRMMiddlewareTools), ("dynamics", CRMMiddlewareTools), ("internal", BaseMiddlewareTools)],
)
def test_strategy_selection(make_org, make_user, connector, expected):
    tools, user = make_tools(make_org, make_user, connector)
    assert type(tools) is expected
    assert resolve_middleware_class(str(user.id)) is expected


def test_strategy_selection_without_user_falls_back_to_base():
    assert resolve_middleware_class(None) is BaseMiddlewareTools
    assert resolve_middleware_class("not-a-uuid") is BaseMiddlewareTools


def test_get_tools_exposes_the_seven_tools(make_org, make_user):
    tools, _ = make_tools(make_org, make_user)
    assert len(tools.get_tools()) == 7


def test_save_entity_merges_fields_with_priority_and_ownership(make_org, make_user, driver):
    tools, user = make_tools(make_org, make_user)
    result = run(tools._save_entity("meeting", title="T", summary="S", fields={"title": "overridden", "extra": 1}, metadata={"k": 2}))
    created = [c for c in driver.calls if c[0] == "create"][0][2]
    assert created["title"] == "T" and created["extra"] == 1 and created["k"] == 2  # SQL: metadata becomes field overrides
    assert result["id"] and DatabaseDriver().user_owns_entity(user.id, "meeting", result["id"])


def test_sql_strategy_normalises_foreign_key_hints(make_org, make_user, driver):
    tools, _ = make_tools(make_org, make_user)
    run(tools._save_entity("meeting", title="T", related_entities={"doctor": {"id": 7}, "clinic": "42", "ward_id": 3, "name": "Dr Who"}))
    payload = [c for c in driver.calls if c[0] == "create"][0][2]
    assert payload["doctor_id"] == 7 and payload["clinic_id"] == "42" and payload["ward_id"] == 3
    assert "name_id" not in payload and payload["related_entities"]["name"] == "Dr Who"


def test_crm_strategy_keeps_metadata_nested(make_org, make_user, driver):
    tools, _ = make_tools(make_org, make_user, "hubspot")
    run(tools._save_entity("meeting", title="T", metadata={"k": 1}, related_entities={"company": "ACME"}))
    payload = [c for c in driver.calls if c[0] == "create"][0][2]
    assert payload["metadata"] == {"k": 1} and payload["related_entities"] == {"company": "ACME"} and "k" not in payload


def test_save_entity_derives_contact_hints_from_participants(make_org, make_user, driver):
    tools, _ = make_tools(make_org, make_user, "hubspot")
    run(tools._save_entity("meeting", title="T", participants=[{"name": "Ann"}, {"name": "Bob", "email": "bob@x.io"}]))
    payload = [c for c in driver.calls if c[0] == "create"][0][2]
    assert payload["contact_email"] == "bob@x.io" and payload["contact_name"] == "Bob"


def test_save_entity_without_fields_asks_for_required_columns(make_org, make_user, driver):
    tools, _ = make_tools(make_org, make_user)
    result = run(tools._save_entity("meeting"))
    assert result["action"] == "ask_user_for_missing_fields" and result["missing_required_fields"] == ["title"]


def test_save_entity_without_fields_and_no_requirements_lists_available(make_org, make_user, driver):
    tools, _ = make_tools(make_org, make_user)
    mapping = driver_mapping(tools)
    mapping["required_columns"] = []
    result = run(_with_config(tools, driver, mapping)._save_entity("meeting"))
    assert result["action"] == "ask_user_for_fields" and "title" in result["available_fields"]


def driver_mapping(tools):
    return copy.deepcopy(MEETING_MAPPING)


def _with_config(tools, driver, mapping):
    from app.extensions import db
    from app.models import User

    user = db.session.get(User, tools.user_id)
    user.organization.connector_config = {"schema_mappings": {"meeting": mapping}}
    db.session.commit()
    return tools


def test_save_entity_missing_required_columns_error_is_structured(make_org, make_user, driver):
    tools, _ = make_tools(make_org, make_user)
    driver.fail_with = ValueError("Cannot create meeting: missing required columns ['title', 'owner'] for table x")
    result = run(tools._save_entity("meeting", summary="S"))
    assert result["missing_required_fields"] == ["title", "owner"] and result["action"] == "ask_user_for_missing_fields"


def test_save_entity_other_value_error_and_unexpected_error(make_org, make_user, driver):
    tools, _ = make_tools(make_org, make_user)
    driver.fail_with = ValueError("nope")
    assert run(tools._save_entity("meeting", title="T")) == {"error": "Cannot create record: nope"}
    driver.fail_with = RuntimeError("connection refused by host")
    assert "unavailable" in run(tools._save_entity("meeting", title="T"))["error"]
    driver.fail_with = RuntimeError("weird")
    assert "Failed to access 'meeting' records" in run(tools._save_entity("meeting", title="T"))["error"]


def test_get_entities_scopes_and_clamps_limit(make_org, make_user, driver):
    tools, _ = make_tools(make_org, make_user)
    driver.rows = [{"id": "1", "title": "a", "created": datetime(2024, 1, 2), "n": Decimal("1.5"), "d": date(2024, 1, 1)}]
    out = run(tools._get_entities("meeting", limit=10_000))
    assert out["count"] == 1 and out["records"][0]["created"] == "2024-01-02T00:00:00" and out["records"][0]["n"] == 1.5
    read = [c for c in driver.calls if c[0] == "read"][0]
    assert read[3]["limit"] == 50 and read[2] == tools.user_id
    run(tools._get_entities("meeting", user_only=False))
    assert [c for c in driver.calls if c[0] == "read"][1][2] in (None, tools.user_id)


def test_get_entities_degrades_gracefully(make_org, make_user, driver):
    tools, _ = make_tools(make_org, make_user)
    driver.fail_with = ValueError("table gone")
    assert run(tools._get_entities("meeting")) == {"entity_type": "meeting", "records": [], "count": 0, "error": "table gone"}
    driver.fail_with = RuntimeError("boom")
    assert run(tools._get_entities("meeting"))["records"] == []


def test_update_entity_flow(make_org, make_user, driver):
    tools, _ = make_tools(make_org, make_user)
    created = run(tools._save_entity("meeting", title="old"))
    updated = run(tools._update_entity("meeting", created["id"], title="new", fields={"extra": 1}))
    assert updated["title"] == "new" and updated["extra"] == 1
    assert run(tools._update_entity("meeting", created["id"])) == {"error": "No fields provided to update record."}
    assert "Cannot update record" in run(tools._update_entity("meeting", "999", title="x"))["error"]  # not owned


def test_update_payload_drops_related_entities_for_sql_engines(make_org, make_user, driver):
    tools, _ = make_tools(make_org, make_user)
    created = run(tools._save_entity("meeting", title="old"))
    driver.engine = create_engine("sqlite://")  # looks like a SQL driver (no tables to probe)
    run(tools._update_entity("meeting", created["id"], title="new", related_entities={"doctor": "x"}))
    sent = [c for c in driver.calls if c[0] == "update"][0][3]
    assert "related_entities" not in sent


def test_update_entity_unexpected_error(make_org, make_user, driver):
    tools, _ = make_tools(make_org, make_user)
    created = run(tools._save_entity("meeting", title="old"))
    driver.fail_with = RuntimeError("operationalerror")
    assert "unavailable" in run(tools._update_entity("meeting", created["id"], title="x"))["error"]


def test_delete_entity_flow(make_org, make_user, driver):
    tools, _ = make_tools(make_org, make_user)
    created = run(tools._save_entity("meeting", title="x"))
    assert run(tools._delete_entity("meeting", created["id"])) == {"deleted": True}
    refused = run(tools._delete_entity("meeting", "123"))
    assert refused["deleted"] is False and "Cannot delete record" in refused["error"]
    driver.rows.append({"id": "55"})
    DatabaseDriver().assign_entity_to_user(tools.user_id, __import__("app.models", fromlist=["User"]).User.query.get(tools.user_id).org_id, "meeting", "55")
    driver.fail_with = RuntimeError("kaboom")
    assert run(tools._delete_entity("meeting", "55"))["deleted"] is False


def test_requirements_tool_reports_schema_and_enums(make_org, make_user, driver):
    tools, _ = make_tools(make_org, make_user)
    mapping = copy.deepcopy(MEETING_MAPPING)
    mapping["enum_values"] = {"status": ["open", "closed"], "empty": []}
    _with_config(tools, driver, mapping)
    out = run(tools._get_entity_requirements("meeting"))
    assert out["table_name"] == "meetings" and out["required_fields"] == ["title"]
    assert out["field_constraints"] == {"status": {"type": "enum", "values": ["open", "closed"]}}


def test_requirements_tool_error_is_reported(make_org, make_user, driver):
    tools, _ = make_tools(make_org, make_user)
    driver.fail_with = RuntimeError("down")
    org_cfg = {"schema_mappings": {"meeting": {**MEETING_MAPPING, "table_name": "other"}}}
    _with_config(tools, driver, org_cfg["schema_mappings"]["meeting"])
    assert "error" in run(tools._get_entity_requirements("meeting"))


def test_legacy_save_meeting_extracts_hints_from_metadata(make_org, make_user, driver):
    tools, _ = make_tools(make_org, make_user, "hubspot")
    run(tools._save_meeting("Summary", title="T", participants=[{"email": "p@x.io"}],
                            metadata={"related_client_id": "9", "account_id": "A1", "contact_email": "c@x.io",
                                      "contact_name": "Cee", "company_name": "ACME", "related_entities": {"deal": "D"}}))
    payload = [c for c in driver.calls if c[0] == "save_meeting"][0][1]
    assert payload["contact_id"] == "9" and payload["company_id"] == "A1"
    assert payload["contact_email"] == "c@x.io" and payload["company_name"] == "ACME"
    assert payload["related_entities"] == {"deal": "D"}


def test_legacy_save_meeting_uses_participants_as_fallback_hint(make_org, make_user, driver):
    tools, _ = make_tools(make_org, make_user, "hubspot")
    run(tools._save_meeting("Summary", participants=["Zed Zee"]))
    assert [c for c in driver.calls if c[0] == "save_meeting"][0][1]["contact_name"] == "Zed Zee"


def test_history_tool_clamps_limit(make_org, make_user, driver):
    tools, _ = make_tools(make_org, make_user)
    run(tools._save_meeting("S", title="T"))
    assert len(run(tools._get_history(limit=999))) == 1
    prepared = [c for c in driver.calls if c[0] == "prepare"][-1][1]
    assert prepared["limit"] == 50


def test_tools_without_user_context_fail_safely():
    tools = BaseMiddlewareTools("")
    assert "Missing user context" in run(tools._save_meeting("S"))["error"]
    assert run(tools._get_history()) == []
    assert "Missing user context" in run(tools._save_entity("x", title="T"))["error"]
    assert run(tools._get_entities("x"))["records"] == []
    assert "Missing user context" in run(tools._get_entity_requirements("x"))["error"]
    assert "Missing user context" in run(tools._update_entity("x", "1", title="T"))["error"]
    assert run(tools._delete_entity("x", "1"))["deleted"] is False


@pytest.mark.parametrize(
    "participants,expected",
    [
        (None, {}),
        ([], {}),
        (["", "  "], {}),
        (["a@b.io"], {"contact_email": "a@b.io"}),
        (["Ann"], {"contact_name": "Ann"}),
        ([{"first_name": "A", "last_name": "B"}], {"contact_name": "A B"}),
        ([{"full_name": "Dee"}, {"mail": "d@e.io"}], {"contact_email": "d@e.io"}),
        ([{"display_name": "X", "contact_email": "x@y.io"}], {"contact_email": "x@y.io", "contact_name": "X"}),
        ([5, {"foo": 1}], {}),
    ],
)
def test_contact_hint_extraction(participants, expected):
    assert BaseMiddlewareTools._extract_contact_hints_from_participants(participants) == expected


def test_missing_required_columns_parser_and_json_safe():
    assert BaseMiddlewareTools._extract_missing_required_columns("x missing required columns ['a', \"b\"] y") == ["a", "b"]
    assert BaseMiddlewareTools._extract_missing_required_columns("nothing") == []
    safe = BaseMiddlewareTools._json_safe({"s": {1, 2}, "o": object, "t": (1, 2), "n": None})
    assert sorted(safe["s"]) == [1, 2] and safe["t"] == [1, 2] and safe["n"] is None and isinstance(safe["o"], str)


def test_base_metadata_hook_variants():
    tools = BaseMiddlewareTools("")
    payload = {}
    tools._merge_metadata_into_payload(payload, None)
    tools._merge_metadata_into_payload(payload, "raw")
    assert payload == {"metadata": "raw"}
    tools._merge_related_entities_into_payload(payload, "not a dict")
    assert "related_entities" not in payload
