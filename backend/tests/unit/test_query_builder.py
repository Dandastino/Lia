import pytest

from app.schema.query_builder import MAX_LIMIT, DynamicQueryBuilder, is_safe_identifier


def make_mapping(**overrides):
    mapping = {
        "entity_type": "meeting",
        "table_name": "crm_calls",
        "id_column": "call_id",
        "column_mapping": {
            "title": "call_subject",
            "summary": "call_notes",
            "created_at": "created_on",
            "user_id": "owner_id",
        },
        "table_columns": ["call_id", "call_subject", "call_notes", "created_on", "owner_id", "extra_col"],
    }
    mapping.update(overrides)
    return mapping


@pytest.fixture
def builder():
    return DynamicQueryBuilder(make_mapping())


@pytest.mark.parametrize("value", ["users", "public.users", "_x1", "tabelle_è", "a"])
def test_safe_identifiers(value):
    assert is_safe_identifier(value)


@pytest.mark.parametrize(
    "value",
    ["", "1abc", "a b", "a;b", "a--b", "a.b.c", "users; DROP TABLE x", "a' OR '1'='1", "a)", None, 5, "x\ny"],
)
def test_unsafe_identifiers(value):
    assert not is_safe_identifier(value)


@pytest.mark.parametrize("field,value", [("table_name", "calls; DROP TABLE users"), ("id_column", "id) OR (1=1")])
def test_constructor_rejects_unsafe_table_or_id(field, value):
    with pytest.raises(ValueError, match="plain SQL identifier"):
        DynamicQueryBuilder(make_mapping(**{field: value}))


def test_constructor_requires_table_and_id():
    with pytest.raises(ValueError, match="table_name"):
        DynamicQueryBuilder(make_mapping(table_name=None))
    with pytest.raises(ValueError, match="id_column"):
        DynamicQueryBuilder(make_mapping(id_column=""))


def test_constructor_rejects_bad_column_mapping_shapes():
    with pytest.raises(ValueError, match="must be dict"):
        DynamicQueryBuilder(make_mapping(column_mapping=["x"]))
    with pytest.raises(ValueError, match="no usable mapped columns"):
        DynamicQueryBuilder(make_mapping(column_mapping={}))


def test_unsafe_required_column_is_rejected_but_optional_is_dropped():
    with pytest.raises(ValueError, match="Invalid required fields"):
        DynamicQueryBuilder(make_mapping(column_mapping={"title": "x; DROP TABLE y"}))
    builder = DynamicQueryBuilder(make_mapping(column_mapping={"title": "call_subject", "summary": "bad col"}))
    assert "summary" not in builder.column_mapping


def test_placeholder_values_are_not_usable():
    builder = DynamicQueryBuilder(make_mapping(column_mapping={"title": "call_subject", "summary": "NULL", "user_id": None}))
    assert builder.column_mapping == {"title": "call_subject"}


def test_unsafe_table_columns_and_owner_column_are_discarded():
    builder = DynamicQueryBuilder(make_mapping(table_columns=["ok_col", "bad col", 5], owner_column="x;y"))
    assert builder.table_columns == {"ok_col"}
    assert builder.owner_column is None


def test_insert_maps_fields_and_whitelisted_direct_columns(builder):
    sql, params = builder.build_insert(
        {"title": "Hello", "participants": ["a"], "extra_col": {"k": 1}, "not_a_column": "ignored", "summary": None}
    )
    assert sql == "INSERT INTO crm_calls (call_subject, extra_col) VALUES (:call_subject, :extra_col) RETURNING *"
    assert params == {"call_subject": "Hello", "extra_col": '{"k": 1}'}
    assert "not_a_column" not in sql


def test_insert_with_nothing_mappable_fails(builder):
    with pytest.raises(ValueError, match="Cannot map payload"):
        builder.build_insert({"bogus": 1})


def test_select_without_filters(builder):
    sql, params = builder.build_select()
    assert sql == "SELECT * FROM crm_calls WHERE 1=1 ORDER BY call_id DESC LIMIT 20"
    assert params == {}


def test_select_filters_are_bound_not_interpolated(builder):
    sql, params = builder.build_select(
        {"title": "x'; DROP TABLE users;--", "created_at_gte": "2024-01-01", "created_at_lte": "2024-12-31"}
    )
    assert "DROP" not in sql
    assert sql.count(":filter_") == 3
    assert "call_subject = :filter_0" in sql
    assert "created_on >= :filter_1" in sql and "created_on <= :filter_2" in sql
    assert params["filter_0"] == "x'; DROP TABLE users;--"


@pytest.mark.parametrize(
    "key",
    ["1=1; DROP TABLE users; --", "title) OR (1=1", "unknown_col", "call_subject OR 1", "x_gte"],
)
def test_select_rejects_unknown_or_malicious_filter_keys(builder, key):
    with pytest.raises(ValueError, match="Unknown filter column"):
        builder.build_select({key: "v"})


def test_select_accepts_table_columns_and_id_column(builder):
    sql, _ = builder.build_select({"extra_col": 1, "call_id": 5})
    assert "extra_col = :filter_0" in sql and "call_id = :filter_1" in sql


def test_select_accepts_trusted_owner_column_only_when_declared(builder):
    with pytest.raises(ValueError):
        builder.build_select({"tenant_fk": 1})
    sql, _ = builder.build_select({"tenant_fk": 1}, trusted_columns=["tenant_fk"])
    assert "tenant_fk = :filter_0" in sql
    with pytest.raises(ValueError):
        builder.build_select({"evil;": 1}, trusted_columns=["evil;"])


def test_select_owned_entity_ids_uses_in_clause_with_bound_params(builder):
    sql, params = builder.build_select({"owned_entity_ids": ["1", "2'; --"]})
    assert "call_id IN (:owned_id_0, :owned_id_1)" in sql
    assert params == {"owned_id_0": "1", "owned_id_1": "2'; --"}


def test_select_ignores_empty_owned_entity_ids(builder):
    sql, params = builder.build_select({"owned_entity_ids": []})
    assert "IN" not in sql and params == {}


@pytest.mark.parametrize(
    "limit,expected",
    [(5, 5), ("7", 7), (0, 1), (-9, 1), (10**6, MAX_LIMIT), ("1; DROP TABLE x", 20), (None, 20)],
)
def test_limit_is_always_a_clamped_integer(builder, limit, expected):
    sql, _ = builder.build_select(limit=limit)
    assert sql.endswith(f"LIMIT {expected}")


def test_limit_and_offset_inside_filters_are_extracted_not_filtered(builder):
    sql, params = builder.build_select({"limit": 3, "offset": 6, "title": "x"})
    assert sql.endswith("LIMIT 3 OFFSET 6")
    assert "offset" not in sql.split("WHERE")[1].split("ORDER")[0]
    assert params == {"filter_0": "x"}


@pytest.mark.parametrize("offset,expected", [("abc", 0), (-4, 0), (5, 5)])
def test_offset_is_sanitised(builder, offset, expected):
    sql, _ = builder.build_select({"offset": offset})
    assert (f"OFFSET {expected}" in sql) is (expected > 0)


def test_update_maps_fields_and_whitelists_columns(builder):
    sql, params = builder.build_update("5", {"title": "New", "extra_col": 1, "evil_col": 2, "summary": {"a": 1}})
    assert sql == (
        "UPDATE crm_calls SET call_subject = :call_subject, extra_col = :extra_col, call_notes = :call_notes "
        "WHERE call_id = :entity_id RETURNING *"
    )
    assert params["entity_id"] == "5" and params["call_notes"] == '{"a": 1}'
    assert "evil_col" not in sql


def test_update_without_valid_fields_fails(builder):
    with pytest.raises(ValueError, match="No fields to update"):
        builder.build_update("1", {"nope": 1})


def test_delete(builder):
    assert builder.build_delete("9") == ("DELETE FROM crm_calls WHERE call_id = :entity_id", {"entity_id": "9"})


def test_normalize_row_reverse_maps_and_adds_id(builder):
    row = {"call_id": 4, "call_subject": "T", "other": 1}
    assert builder.normalize_row(row) == {"call_id": 4, "title": "T", "other": 1, "id": 4}
    assert builder.normalize_rows([row]) == [builder.normalize_row(row)]


def test_schema_qualified_table_is_allowed():
    sql, _ = DynamicQueryBuilder(make_mapping(table_name="crm.calls")).build_delete("1")
    assert "crm.calls" in sql
