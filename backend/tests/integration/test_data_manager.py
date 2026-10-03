"""DataManager: driver selection, tenant isolation and ownership bookkeeping."""
from __future__ import annotations

import asyncio
import copy
from uuid import uuid4

import pytest

from app.drivers.dynamics_driver import DynamicsDriver
from app.drivers.hubspot_driver import HubSpotDriver
from app.drivers.mysql_driver import MySQLDriver
from app.drivers.postgresql_driver import PostgreSQLDriver
from app.drivers.salesforce_driver import SalesforceDriver
from app.extensions import db
from app.models import DatabaseDriver, ExternalUserMapping, SyncLog
from app.services import data_manager as dm_module
from app.services.data_manager import DataManager

from ..fakes import MEETING_MAPPING, FakeDriver

run = asyncio.run


@pytest.fixture
def org_with_mapping(make_org):
    return make_org(
        connector_type="postgresql",
        connector_config={"schema_mappings": {"meeting": copy.deepcopy(MEETING_MAPPING)}},
    )


@pytest.fixture
def dm(org_with_mapping, make_user):
    """DataManager wired to an in-memory driver for a user of ``org_with_mapping``."""
    user = make_user(org_with_mapping, email="doc@acme.test")
    manager = DataManager(org_with_mapping, FakeDriver(org_with_mapping.connector_config))
    manager.authorized_user_id = str(user.id)
    manager.authorized_user = user
    return manager


# ------------------------------------------------------------------ from_user_id


@pytest.mark.parametrize(
    "connector,driver_cls",
    [("postgresql", PostgreSQLDriver), ("mysql", MySQLDriver), ("hubspot", HubSpotDriver),
     ("salesforce", SalesforceDriver), ("dynamics", DynamicsDriver)],
)
def test_from_user_id_selects_driver_per_connector(monkeypatch, make_org, make_user, connector, driver_cls):
    created = {}

    class Spy(FakeDriver):
        def __init__(self, config=None):
            super().__init__(config)
            created["config"] = config

    monkeypatch.setattr(dm_module, driver_cls.__name__, Spy)
    org = make_org(connector_type=connector.upper(), connector_config={"marker": 1})
    user = make_user(org)
    manager = DataManager.from_user_id(str(user.id))
    assert isinstance(manager.driver, Spy) and created["config"] == {"marker": 1}
    assert manager.authorized_user_id == str(user.id)


def test_from_user_id_rejects_bad_input(make_org, make_user):
    with pytest.raises(ValueError, match="invalid user_id"):
        DataManager.from_user_id("not-a-uuid")
    with pytest.raises(ValueError, match="User not found"):
        DataManager.from_user_id(str(uuid4()))
    orphan = make_user(None, email="orphan@acme.test")
    with pytest.raises(ValueError, match="not associated"):
        DataManager.from_user_id(str(orphan.id))
    org = make_org(connector_type="oracle")
    user = make_user(org, email="o@acme.test")
    with pytest.raises(ValueError, match="Unsupported connector_type"):
        DataManager.from_user_id(str(user.id))


# ------------------------------------------------------------------ legacy meeting path


def test_save_meeting_logs_sync_and_assigns_ownership(dm):
    result = dm.save_meeting(dm.authorized_user_id, {"title": "Kickoff", "summary": "s"})
    assert result["title"] == "Kickoff"
    assert DatabaseDriver().get_user_entity_ids(dm.authorized_user_id, "meeting") == [result["id"]]
    log = SyncLog.query.one()
    assert (log.status, log.target_system) == ("success", "postgresql")


def test_failed_driver_call_is_logged_with_truncated_error(dm):
    dm.driver.fail_with = RuntimeError("x" * 2000)
    with pytest.raises(RuntimeError):
        dm.save_meeting(dm.authorized_user_id, {"summary": "s"})
    log = SyncLog.query.one()
    assert log.status == "failed" and len(log.error_message) == 500


def test_meeting_history_is_scoped_to_owned_ids(dm):
    first = dm.save_meeting(dm.authorized_user_id, {"title": "a", "summary": "s"})
    dm.get_meeting_history(dm.authorized_user_id, {"limit": 5})
    prepared = [c for c in dm.driver.calls if c[0] == "prepare"][-1][1]
    assert prepared["owned_entity_ids"] == [first["id"]]


def test_meeting_history_unowned_blocked_when_disallowed(dm):
    assert dm.get_meeting_history(dm.authorized_user_id, {"allow_unowned_read": False}) == []


def test_meeting_history_user_only_false_skips_scoping(dm):
    dm.get_meeting_history(dm.authorized_user_id, {"user_only": False})
    prepared = [c for c in dm.driver.calls if c[0] == "prepare"][-1][1]
    assert "owned_entity_ids" not in prepared


def test_hubspot_save_meeting_sets_and_clears_owner_from_mapping(make_org, make_user):
    org = make_org(connector_type="hubspot", connector_config={"api_key": "k"})
    user = make_user(org)
    db.session.add(ExternalUserMapping(user_id=user.id, org_id=org.id, crm_type="hubspot", external_user_id="123"))
    db.session.commit()
    driver = FakeDriver({"api_key": "k"})
    seen = {}
    original = driver.save_meeting

    def spy(user_id, payload):
        seen["owner"] = driver.request_owner_id
        return original(user_id, payload)

    driver.save_meeting = spy
    manager = DataManager(org, driver)
    manager.authorized_user_id, manager.authorized_user = str(user.id), user
    manager.save_meeting(str(user.id), {"summary": "s"})
    assert seen["owner"] == "123" and driver.request_owner_id is None


# ------------------------------------------------------------------ generic CRUD


def test_create_entity_auto_assigns_ownership(dm):
    created = run(dm.create_entity("meeting", {"title": "T"}))
    assert DatabaseDriver().user_owns_entity(dm.authorized_user_id, "meeting", created["id"])


def test_create_entity_owner_stamp_is_authoritative(dm, monkeypatch):
    async def fake_owner(self, owner_column=None):
        return "ext-7"

    monkeypatch.setattr(DataManager, "_resolve_external_owner_id", fake_owner)
    dm.driver.config["schema_mappings"]["meeting"]["owner_column"] = "owner_id"
    dm.org.connector_config = copy.deepcopy(dm.driver.config)
    run(dm.create_entity("meeting", {"title": "T", "owner_id": "attacker-chosen"}))
    create_call = [c for c in dm.driver.calls if c[0] == "create"][0]
    assert create_call[2]["owner_id"] == "ext-7"
    assert dm.driver.request_owner_id is None  # context cleared afterwards


def test_owner_context_is_cleared_even_when_driver_fails(dm):
    dm.driver.fail_with = RuntimeError("boom")
    with pytest.raises(RuntimeError):
        run(dm.create_entity("meeting", {"title": "T"}))
    assert dm.driver.request_owner_column is None and dm.driver.request_owner_id is None


def test_read_entities_default_mode_bootstraps_ownership(dm):
    dm.driver.rows = [{"id": "1", "title": "pre-existing"}, {"id": "2", "title": "pre-existing 2"}]
    rows = run(dm.read_entities("meeting"))
    assert len(rows) == 2
    assert set(DatabaseDriver().get_user_entity_ids(dm.authorized_user_id, "meeting")) == {"1", "2"}


def test_read_entities_restrict_to_owned(dm):
    dm.org.connector_config = {**dm.org.connector_config, "restrict_to_owned_entities": True}
    db.session.commit()
    dm.driver.rows = [{"id": "1"}, {"id": "2"}]
    assert run(dm.read_entities("meeting")) == []  # owns nothing yet
    DatabaseDriver().assign_entity_to_user(dm.authorized_user_id, dm.org.id, "meeting", "2")
    assert [r["id"] for r in run(dm.read_entities("meeting"))] == ["2"]


def test_read_entities_unowned_fallback_can_be_disabled(dm):
    dm.org.connector_config = {**dm.org.connector_config, "allow_unowned_read": False}
    db.session.commit()
    dm.driver.rows = [{"id": "1"}]
    assert run(dm.read_entities("meeting")) == []


def test_read_entities_applies_owner_scope_filter(dm, monkeypatch):
    async def fake_owner(self, owner_column=None):
        return "ext-7"

    monkeypatch.setattr(DataManager, "_resolve_external_owner_id", fake_owner)
    dm.driver.config["schema_mappings"]["meeting"]["owner_column"] = "owner_id"
    dm.org.connector_config = copy.deepcopy(dm.driver.config)
    run(dm.read_entities("meeting", filters={"limit": 5}))
    read_call = [c for c in dm.driver.calls if c[0] == "read"][0]
    assert read_call[3]["owner_id"] == "ext-7"


def test_read_entities_rejects_user_from_other_org(dm, make_org, make_user):
    outsider = make_user(make_org(name="Other"), email="x@other.test")
    dm.authorized_user = outsider
    with pytest.raises(ValueError, match="organization mismatch"):
        run(dm.read_entities("meeting"))


def test_read_entities_requires_a_user(dm):
    del dm.authorized_user_id
    with pytest.raises(ValueError, match="No user_id"):
        run(dm.read_entities("meeting"))


def test_update_and_delete_require_ownership(dm):
    created = run(dm.create_entity("meeting", {"title": "T"}))
    other = run(dm.driver.create_entity("meeting", {"title": "someone else's"}))
    with pytest.raises(ValueError, match="Unauthorized update"):
        run(dm.update_entity("meeting", other["id"], {"title": "x"}))
    with pytest.raises(ValueError, match="Unauthorized delete"):
        run(dm.delete_entity("meeting", other["id"]))
    assert run(dm.update_entity("meeting", created["id"], {"title": "New"}))["title"] == "New"
    assert run(dm.delete_entity("meeting", created["id"])) is True


# ------------------------------------------------------------------ mapping + owner resolution helpers


def test_ensure_mapping_uses_cached_mapping(dm):
    run(dm.ensure_entity_mapping("meeting"))
    assert dm.driver.config["schema_mappings"]["meeting"]["table_name"] == "meetings"


def test_ensure_mapping_rebuilds_when_table_vanished(dm, monkeypatch):
    dm.org.connector_config["schema_mappings"]["meeting"]["table_name"] = "gone"
    dm.driver.config = copy.deepcopy(dm.org.connector_config)

    async def fake_auto_map(entity_type, schema_info, connector_config):
        return copy.deepcopy(MEETING_MAPPING)

    monkeypatch.setattr(dm.schema_mapper, "auto_map_entity", fake_auto_map)
    run(dm.ensure_entity_mapping("meeting"))
    db.session.expire_all()
    assert dm.org.connector_config["schema_mappings"]["meeting"]["table_name"] == "meetings"


def test_ensure_mapping_backfills_missing_metadata(dm):
    mapping = dm.org.connector_config["schema_mappings"]["meeting"]
    mapping.pop("table_columns")
    mapping.pop("column_types")
    dm.driver.config = copy.deepcopy(dm.org.connector_config)
    run(dm.ensure_entity_mapping("meeting"))
    assert "id" in dm.org.connector_config["schema_mappings"]["meeting"]["table_columns"]


def test_ensure_mapping_propagates_automap_failure(make_org, make_user, monkeypatch):
    org = make_org(connector_type="postgresql", connector_config={})
    user = make_user(org)
    manager = DataManager(org, FakeDriver({}))
    manager.authorized_user_id, manager.authorized_user = str(user.id), user

    async def boom(**kwargs):
        raise RuntimeError("llm down")

    monkeypatch.setattr(manager.schema_mapper, "auto_map_entity", boom)
    with pytest.raises(RuntimeError, match="llm down"):
        run(manager.ensure_entity_mapping("meeting"))


@pytest.mark.parametrize(
    "mapping,expected",
    [
        ({"owner_column": " doctor_id "}, "doctor_id"),
        ({"column_mapping": {"owner_id": "dr"}}, "dr"),
        ({"column_mapping": {"user_id": "usr"}}, "usr"),
        ({"table_columns": ["ID", "Created_By"]}, "Created_By"),
        ({"table_columns": ["id", "title"]}, None),
        ({"table_columns": "nope"}, None),
        ({}, None),
    ],
)
def test_resolve_owner_column(dm, mapping, expected):
    dm.driver.config = {"schema_mappings": {"meeting": mapping}}
    assert dm._resolve_owner_column("meeting") == expected


def test_resolve_external_owner_uses_stored_mapping(dm):
    db.session.add(ExternalUserMapping(user_id=dm.authorized_user.id, org_id=dm.org.id, crm_type="postgresql", external_user_id="42"))
    db.session.commit()
    assert run(dm._resolve_external_owner_id()) == "42"


def test_resolve_external_owner_none_without_mapping_for_crm(dm):
    dm.org.connector_type = "salesforce"
    assert run(dm._resolve_external_owner_id()) is None


def test_resolve_external_owner_requires_authorized_user(dm):
    del dm.authorized_user_id
    assert run(dm._resolve_external_owner_id()) is None


def test_safe_sql_identifier():
    assert DataManager._is_safe_sql_identifier("good_name1")
    assert not DataManager._is_safe_sql_identifier("bad name;")
    assert not DataManager._is_safe_sql_identifier("")


def test_compact_error():
    assert DataManager._compact_error(RuntimeError("line one\nline two")) == "line one"
    assert DataManager._compact_error(RuntimeError("")) == "unknown error"
