"""DatabaseDriver helper, CRM identity mapper and the authorization helpers."""
from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import text

from app.extensions import db
from app.models import DatabaseDriver, ExternalUserMapping, User
from app.services.crm_mapper import CRMEntityMapper
from app.tools import authorization as authz

from ..conftest import TEST_PASSWORD


@pytest.fixture
def dbd():
    return DatabaseDriver()


# ------------------------------------------------------------------ password hashing


def test_password_hash_roundtrip_and_edge_cases(org, make_user):
    user = make_user(org)
    assert user.check_password(TEST_PASSWORD) is True
    assert user.check_password("wrong") is False
    assert user.password_hash != TEST_PASSWORD
    assert user.check_password("x" * 100) is False  # > 72 bytes: bcrypt refuses, must not raise
    user.password_hash = ""
    assert user.check_password(TEST_PASSWORD) is False
    user.password_hash = "not-a-bcrypt-hash"
    assert user.check_password(TEST_PASSWORD) is False


def test_guid_rejects_garbage_with_400_not_500(client, admin_headers):
    assert client.get("/admin/users/zzz/entity-ownership", headers=admin_headers).status_code == 400


# ------------------------------------------------------------------ DatabaseDriver


def test_create_and_get_user(dbd, org):
    user = dbd.create_user("a@b.co", "Passw0rd!", org.id, role="owner")
    assert user.role == "owner" and dbd.get_user_by_email("a@b.co").id == user.id
    assert dbd.get_user_by_id(str(user.id)).email == "a@b.co"
    assert dbd.create_user("a@b.co", "x", org.id) is None  # duplicate
    assert dbd.create_user("c@d.co", "x", uuid4()) is None  # unknown org


def test_sync_log(dbd, org):
    log = dbd.create_sync_log(str(org.id), "failed", "hubspot", "boom")
    assert (log.status, log.target_system, log.error_message) == ("failed", "hubspot", "boom")
    assert dbd._uuid_any(None) is None


def test_entity_ownership_lifecycle(dbd, org, member):
    first = dbd.assign_entity_to_user(member.id, org.id, "contact", 1)
    again = dbd.assign_entity_to_user(str(member.id), str(org.id), "contact", "1")
    assert first.id == again.id  # idempotent
    dbd.assign_entity_to_user(member.id, org.id, "deal", "2")
    assert dbd.get_user_entity_ids(member.id, "contact") == ["1"]
    assert dbd.get_user_entity_ids(member.id, "contact", org_id=uuid4()) == []
    assert dbd.user_owns_entity(member.id, "contact", "1") and not dbd.user_owns_entity(member.id, "contact", "2")
    assert {e["entity_type"] for e in dbd.get_user_owned_entities_safe(member.id)} == {"contact", "deal"}
    assert len(dbd.get_user_owned_entities_safe(member.id, "deal")) == 1
    assert dbd.remove_entity_from_user_safe(member.id, "deal", "2") is True
    assert dbd.remove_entity_from_user_safe(member.id, "deal", "2") is False


def test_assign_entity_invalid_user_returns_none(dbd, org):
    assert dbd.assign_entity_to_user("not-a-uuid", org.id, "contact", "1") is None


def test_ownership_helpers_fail_closed_when_table_is_missing(dbd, member):
    db.session.execute(text("DROP TABLE user_entity_ownership"))
    db.session.commit()
    assert dbd.table_exists("user_entity_ownership") is False
    assert dbd.get_user_entity_ids(member.id, "contact") == []
    assert dbd.user_owns_entity(member.id, "contact", "1") is False  # deny by default
    assert dbd.get_user_owned_entities_safe(member.id) == []
    assert dbd.remove_entity_from_user_safe(member.id, "contact", "1") is False
    assert dbd.table_exists(123) is False


def test_external_user_mapping_crud(dbd, org, member, make_user):
    mapping = dbd.create_external_user_mapping(member.id, org.id, "hubspot", 77, "m@hs.test")
    assert mapping.external_user_id == "77"
    replaced = dbd.create_external_user_mapping(member.id, org.id, "hubspot", "88")
    assert replaced.external_user_id == "88"
    assert ExternalUserMapping.query.filter_by(user_id=member.id).count() == 1
    assert dbd.get_external_user_id(member.id, "hubspot") == "88"
    assert dbd.get_external_user_id(member.id, "salesforce") is None
    assert dbd.get_external_user_mapping(member.id, "hubspot").external_user_id == "88"
    dbd.create_external_user_mapping(member.id, org.id, "salesforce", "S1")
    assert {m.crm_type for m in dbd.get_all_external_mappings(member.id)} == {"hubspot", "salesforce"}
    assert dbd.find_user_by_external_id(org.id, "hubspot", 88).id == member.id
    assert dbd.find_user_by_external_id(org.id, "hubspot", "nope") is None
    assert dbd.create_external_user_mapping("garbage", org.id, "x", "1") is None


def test_legacy_schema_is_reconciled(dbd, org, member):
    db.session.execute(text("ALTER TABLE external_user_mapping DROP COLUMN external_email"))
    db.session.commit()
    dbd._ensure_external_user_mapping_schema()
    cols = {c["name"] for c in db.inspect(db.engine).get_columns("external_user_mapping")}
    assert "external_email" in cols
    dbd._ensure_external_user_mapping_schema()  # idempotent


# ------------------------------------------------------------------ CRM mapper


def test_crm_mapper_roundtrip(org, member):
    mapper = CRMEntityMapper()
    assert mapper.register_doctor_to_crm(str(member.id), str(org.id), "hubspot", "5", "m@hs.test") is True
    assert mapper.resolve_doctor_in_crm(str(member.id), "hubspot") == "5"
    assert mapper.resolve_user_from_crm(str(org.id), "hubspot", "5").id == member.id
    assert mapper.get_doctor_crm_profile(str(member.id)) == {"hubspot": "5"}
    assert mapper.validate_mapping_exists(str(member.id), "hubspot") is True
    assert mapper.validate_mapping_exists(str(member.id), "dynamics") is False
    assert mapper.register_doctor_to_crm("garbage", str(org.id), "hubspot", "5") is False


# ------------------------------------------------------------------ authorization helpers


def test_get_authorized_user_and_org(org, member, make_org):
    user, got_org = authz.get_authorized_user_and_org(str(member.id), str(org.id))
    assert user.id == member.id and got_org.id == org.id
    assert authz.get_authorized_user_and_org(str(member.id))[1].id == org.id
    with pytest.raises(ValueError, match="No user_id"):
        authz.get_authorized_user_and_org(None)
    with pytest.raises(ValueError, match="not found"):
        authz.get_authorized_user_and_org(str(uuid4()))
    with pytest.raises(ValueError, match="tried to access org"):
        authz.get_authorized_user_and_org(str(member.id), str(make_org(name="Other").id))


def test_get_authorized_user_without_org(make_user):
    orphan = make_user(None, email="o@acme.test")
    with pytest.raises(ValueError, match="not associated"):
        authz.get_authorized_user_and_org(str(orphan.id))


def test_verification_helpers(org, member, make_org):
    assert authz.verify_user_in_organization(str(member.id), str(org.id)) is True
    assert authz.verify_user_in_organization(str(member.id), str(make_org(name="O").id)) is False
    assert authz.verify_user_in_organization(str(uuid4()), str(org.id)) is False
    assert authz.verify_user_by_email("  MEMBER@acme.test ").id == member.id
    assert authz.verify_user_by_email("") is None
    DatabaseDriver().assign_entity_to_user(member.id, org.id, "contact", "1")
    assert authz.verify_user_owns_entity(str(member.id), "contact", "1") is True


def test_require_admin_and_require_auth_user_decorators(app, client, org, admin, member, login):
    admin_headers, member_headers = login(admin.email), login(member.email)
    assert client.get("/_t/admin", headers=admin_headers).get_json() == {"admin": admin.email}
    assert client.get("/_t/admin", headers=member_headers).status_code == 403
    assert client.get("/_t/scoped", headers=member_headers).get_json()["org"] == "Acme"
    assert client.get(f"/_t/scoped?org_id={uuid4()}", headers=member_headers).status_code == 403
    db.session.delete(db.session.get(User, member.id))
    db.session.commit()
    assert client.get("/_t/scoped", headers=member_headers).status_code == 403
    assert client.get("/_t/admin", headers=member_headers).status_code == 403
