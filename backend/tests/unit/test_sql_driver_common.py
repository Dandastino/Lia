from types import SimpleNamespace

import pytest

from app.drivers import sql_driver_common as common
from app.schema.query_builder import DynamicQueryBuilder


def builder(**mapping_overrides):
    mapping = {
        "table_name": "patients",
        "id_column": "id",
        "column_mapping": {"title": "full_name", "user_id": "doctor_id"},
        "table_columns": ["id", "full_name", "doctor_id"],
    }
    mapping.update(mapping_overrides)
    return DynamicQueryBuilder(mapping)


def test_get_entity_mapping():
    config = {"schema_mappings": {"patient": {"table_name": "p"}}}
    assert common.get_entity_mapping(config, "patient") == {"table_name": "p"}
    with pytest.raises(ValueError, match="No schema mapping"):
        common.get_entity_mapping(config, "deal")
    with pytest.raises(ValueError):
        common.get_entity_mapping({}, "patient")


def test_get_owner_scope():
    driver = SimpleNamespace(request_owner_column="doctor_id", request_owner_id="7")
    assert common.get_owner_scope(driver) == ("doctor_id", "7")
    assert common.get_owner_scope(SimpleNamespace()) == (None, None)


def test_apply_owner_scope_to_params():
    params = {}
    assert common.apply_owner_scope_to_params(params, "doctor_id", "7") is True
    assert params == {"doctor_id": "7"}
    # authoritative: a caller-supplied owner value is overridden, never trusted
    assert common.apply_owner_scope_to_params(params, "doctor_id", "8") is True
    assert params == {"doctor_id": "8"}
    spoofed = {"doctor_id": "attacker-chosen"}
    common.apply_owner_scope_to_params(spoofed, "doctor_id", "7")
    assert spoofed == {"doctor_id": "7"}
    assert common.apply_owner_scope_to_params({}, None, "7") is False
    assert common.apply_owner_scope_to_params({}, "doctor_id", None) is False


def test_apply_owner_scope_rejects_unsafe_column():
    with pytest.raises(ValueError, match="Unsafe owner column"):
        common.apply_owner_scope_to_params({}, "x; DROP TABLE y", "7")


def test_add_owner_constraint_with_returning():
    sql, params = common.add_owner_constraint_to_sql(
        "UPDATE t SET a = :a WHERE id = :entity_id RETURNING *", "doctor_id", "7"
    )
    assert sql == "UPDATE t SET a = :a WHERE id = :entity_id AND doctor_id = :__owner_id RETURNING *"
    assert params == {"__owner_id": "7"}


def test_add_owner_constraint_without_returning_and_noop():
    sql, params = common.add_owner_constraint_to_sql("DELETE FROM t WHERE id = :entity_id", "doctor_id", "7")
    assert sql.endswith("AND doctor_id = :__owner_id")
    assert common.add_owner_constraint_to_sql("DELETE FROM t", None, "7") == ("DELETE FROM t", {})
    assert common.add_owner_constraint_to_sql("DELETE FROM t", "doctor_id", None) == ("DELETE FROM t", {})


def test_add_owner_constraint_rejects_unsafe_column():
    with pytest.raises(ValueError, match="Unsafe owner column"):
        common.add_owner_constraint_to_sql("DELETE FROM t WHERE id = 1", "a OR 1=1", "7")


def test_split_limit_and_filters_adds_user_and_owner_scope():
    limit, filters = common.split_limit_and_query_filters(
        {"limit": 5, "title": "x", "skip": None}, "u1", builder(), "doctor_id", "7"
    )
    assert limit == 5
    assert filters == {"title": "x", "user_id": "u1", "doctor_id": "7"}


def test_split_limit_defaults_and_does_not_mutate_input():
    original = {"limit": 3}
    limit, filters = common.split_limit_and_query_filters(original, None, builder(), None, None)
    assert (limit, filters) == (3, {})
    assert original == {"limit": 3}
    assert common.split_limit_and_query_filters(None, None, builder(), None, None) == (20, {})


def test_split_skips_user_filter_when_unmapped():
    b = builder(column_mapping={"title": "full_name"})
    assert common.split_limit_and_query_filters({}, "u1", b, None, None)[1] == {}


class FakeInspector:
    def __init__(self, columns=None, fks=None, raises=False):
        self._columns = columns or []
        self._fks = fks or []
        self._raises = raises

    def get_columns(self, table):
        if self._raises:
            raise RuntimeError("no introspection")
        return self._columns

    def get_foreign_keys(self, table):
        return self._fks


def test_resolve_required_columns_from_live_schema():
    inspector = FakeInspector(
        columns=[
            {"name": "id", "nullable": False},
            {"name": "name", "nullable": False},
            {"name": "age", "nullable": True},
            {"name": "status", "nullable": False, "default": "x"},
            {"name": "seq", "nullable": False, "autoincrement": True},
        ]
    )
    assert common.resolve_required_columns(inspector, {}, "t", "id") == ["name"]


def test_resolve_required_columns_falls_back_to_mapping():
    inspector = FakeInspector(raises=True)
    assert common.resolve_required_columns(inspector, {"required_columns": ["a"]}, "t", "id") == ["a"]
    assert common.resolve_required_columns(inspector, {}, "t", "id") == []


def test_missing_required_and_alias_hints():
    assert common.find_missing_required_columns(["a", "b"], {"a": 1}) == ["b"]
    b = builder()
    assert common.build_required_alias_hints(b, ["full_name", "unmapped"]) == {"full_name": "title"}


@pytest.mark.parametrize(
    "value,expected",
    [("123", True), ("550e8400-e29b-41d4-a716-446655440000", True), ("John Smith", False), ("", False), (None, False), ("  ", False)],
)
def test_looks_like_id(value, expected):
    assert common.looks_like_id(value) is expected


def test_safe_identifier():
    assert common._is_safe_identifier("users_1")
    assert not common._is_safe_identifier("users;")
    assert not common._is_safe_identifier("")


def test_label_candidates_from_mapping_prefers_semantic_fields():
    config = {
        "schema_mappings": {
            "patient": {"table_name": "patients", "column_mapping": {"title": "full_name", "summary": "notes", "x": "zzz"}}
        }
    }
    result = common._build_label_candidates_from_mapping(config, "patients", ["full_name", "notes", "zzz"])
    assert result[:2] == ["full_name", "notes"]
    assert common._build_label_candidates_from_mapping(None, "patients", []) == []
    assert common._build_label_candidates_from_mapping({"schema_mappings": []}, "patients", []) == []
    assert common._build_label_candidates_from_mapping(config, "other", ["full_name"]) == []


def test_fallback_label_candidates_skip_ids_and_non_text():
    meta = [
        {"name": "id", "type": "INTEGER"},
        {"name": "patient_id", "type": "VARCHAR"},
        {"name": "first_name", "type": "VARCHAR(20)"},
        {"name": "age", "type": "INTEGER"},
        {"name": "uuid_col", "type": "UUID"},
    ]
    assert common._build_fallback_label_candidates(meta, [m["name"] for m in meta]) == ["first_name", "uuid_col"]


class FakeSession:
    def __init__(self, rows_by_call):
        self.rows_by_call = list(rows_by_call)
        self.executed = []

    def execute(self, statement, params=None):
        self.executed.append((str(statement), params))
        rows = self.rows_by_call.pop(0) if self.rows_by_call else []
        return SimpleNamespace(fetchall=lambda: rows)


class FakeSessionFactory:
    def __init__(self, session):
        self.session = session

    def __call__(self):
        return self

    def __enter__(self):
        return self.session

    def __exit__(self, *exc):
        return False


class FKInspector(FakeInspector):
    def __init__(self, fks, ref_columns):
        super().__init__(fks=fks)
        self.ref_columns = ref_columns

    def get_columns(self, table):
        return self.ref_columns


FK = [{"constrained_columns": ["doctor_id"], "referred_columns": ["id"], "referred_table": "doctors"}]
DOCTOR_COLUMNS = [
    {"name": "id", "type": "INTEGER"},
    {"name": "first_name", "type": "VARCHAR"},
    {"name": "last_name", "type": "VARCHAR"},
]


def run_fk(hint_payload, rows, owner_scope=None, fks=FK, config=None):
    params = {}
    session = FakeSession(rows)
    unresolved = common.resolve_foreign_key_values(
        inspector=FKInspector(fks, DOCTOR_COLUMNS),
        table_name="patients",
        params=params,
        payload=hint_payload,
        session_factory=FakeSessionFactory(session),
        cast_as="TEXT",
        logger=SimpleNamespace(debug=lambda *a, **k: None, info=lambda *a, **k: None, warning=lambda *a, **k: None),
        config=config,
        owner_scope=owner_scope,
    )
    return unresolved, params, session


def test_fk_numeric_and_id_like_hints_are_used_directly():
    assert run_fk({"doctor_id": 5}, [])[:2] == ([], {"doctor_id": 5})
    assert run_fk({"doctor": "42"}, [])[:2] == ([], {"doctor_id": "42"})


def test_fk_no_hint_and_non_string_hint_are_skipped():
    assert run_fk({}, [])[:2] == ([], {})
    assert run_fk({"doctor_id": ["x"]}, [])[:2] == ([], {})
    assert run_fk({"doctor_id": "   "}, [])[:2] == ([], {})


def test_fk_resolves_by_label_unique_match_and_scopes_to_owner():
    unresolved, params, session = run_fk(
        {"doctor": "Alice"}, [[(11,)]], owner_scope=("id", "9")
    )
    assert unresolved == [] and params == {"doctor_id": "11"}
    sql, bound = session.executed[0]
    assert "LOWER(CAST(first_name AS TEXT)) = LOWER(:lookup_value)" in sql
    assert ":owner_scope_id" in sql and bound == {"lookup_value": "Alice", "owner_scope_id": "9"}


def test_fk_ambiguous_label_is_unresolved():
    unresolved, params, _ = run_fk({"doctor": "Alice"}, [[(1,), (2,)]])
    assert unresolved == ["doctor_id"] and params == {}


def test_fk_unmatched_is_unresolved():
    unresolved, params, _ = run_fk({"doctor": "Nobody"}, [[], [], []])
    assert unresolved == ["doctor_id"] and params == {}


def test_fk_full_name_lookup_after_label_lookups_fail():
    unresolved, params, session = run_fk({"doctor": "Alice Smith"}, [[], [], [(3,)]])
    assert unresolved == [] and params == {"doctor_id": "3"}
    assert any("CONCAT" in sql for sql, _ in session.executed)


def test_fk_skips_composite_and_unsafe_identifiers():
    composite = [{"constrained_columns": ["a", "b"], "referred_columns": ["id"], "referred_table": "doctors"}]
    assert run_fk({"doctor": "Alice"}, [], fks=composite)[:2] == ([], {})
    unsafe = [{"constrained_columns": ["doctor_id"], "referred_columns": ["id"], "referred_table": "d; DROP"}]
    assert run_fk({"doctor": "Alice"}, [], fks=unsafe)[:2] == ([], {})


def test_fk_already_present_param_is_not_overwritten():
    params = {"doctor_id": "keep"}
    session = FakeSession([])
    common.resolve_foreign_key_values(
        FKInspector(FK, DOCTOR_COLUMNS), "patients", params, {"doctor": "X"}, FakeSessionFactory(session), "TEXT",
        SimpleNamespace(debug=lambda *a, **k: None),
    )
    assert params == {"doctor_id": "keep"} and session.executed == []
