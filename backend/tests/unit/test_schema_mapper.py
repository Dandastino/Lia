import asyncio
import json
from types import SimpleNamespace

import pytest

from app.schema import mapper as mapper_module
from app.schema.common import is_usable_column_name, strip_fenced_json
from app.schema.mapper import SchemaMappingService

run = asyncio.run

SCHEMA = {
    "tables": [
        {"name": "crm_calls", "columns": ["call_id", "subject", "notes", "created_on", "owner_id"]},
        {"name": "users", "columns": [{"name": "id"}, {"name": "email"}]},
    ]
}
GOOD = {
    "table_name": "crm_calls",
    "id_column": "call_id",
    "column_mapping": {"title": "subject", "summary": "notes", "created_at": None, "user_id": None, "owner_id": "owner_id"},
    "confidence": 0.9,
}


class FakeLLM:
    def __init__(self, replies):
        self.replies = list(replies)
        self.prompts = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, **kwargs):
        self.prompts.append(kwargs["messages"][0]["content"])
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=reply))])


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    async def instant(_):
        return None

    monkeypatch.setattr(mapper_module.asyncio, "sleep", instant)


def service(*replies, **kwargs):
    return SchemaMappingService(llm_model=FakeLLM(replies), **kwargs)


def test_common_helpers():
    assert strip_fenced_json("```json\n{\"a\": 1}\n```") == '{"a": 1}'
    assert strip_fenced_json("```\n{}\n```") == "{}"
    assert strip_fenced_json(None) == ""
    for bad in (None, "", "  ", "NULL", "n/a", "None", 5):
        assert not is_usable_column_name(bad)
    assert is_usable_column_name("col")


def test_auto_map_entity_happy_path_sanitises_and_caches():
    svc = service(json.dumps(GOOD))
    mapping = run(svc.auto_map_entity("meeting", SCHEMA))
    assert mapping["entity_type"] == "meeting"
    assert mapping["column_mapping"] == {"title": "subject", "summary": "notes", "owner_id": "owner_id"}
    again = run(svc.auto_map_entity("meeting", SCHEMA))  # second call served from cache: no more replies queued
    assert again is mapping
    assert svc.get_mapping("meeting") is mapping


def test_cache_expiry_triggers_new_llm_call():
    svc = service(json.dumps(GOOD), json.dumps(GOOD))
    run(svc.auto_map_entity("meeting", SCHEMA))
    for key in svc._cache_expiry:
        svc._cache_expiry[key] = svc._cache_expiry[key].replace(year=2000)
    run(svc.auto_map_entity("meeting", SCHEMA))
    assert len(svc.llm_model.prompts) == 2


def test_fenced_json_response_is_accepted():
    svc = service("```json\n" + json.dumps(GOOD) + "\n```")
    assert run(svc.auto_map_entity("meeting", SCHEMA))["table_name"] == "crm_calls"


def test_prompt_contains_hints_and_compact_schema():
    svc = service(json.dumps(GOOD))
    run(svc.auto_map_entity("meeting", SCHEMA, {"industry": "Health", "name": "Clinic"}))
    prompt = svc.llm_model.prompts[0]
    assert "Industry: Health" in prompt and "Organization: Clinic" in prompt and "crm_calls" in prompt


@pytest.mark.parametrize(
    "mutation,message",
    [
        (lambda m: m.pop("table_name"), "missing required field"),
        (lambda m: m.update(column_mapping=[1]), "must be a dict"),
        (lambda m: m.update(table_name=" "), "non-empty string"),
        (lambda m: m.update(id_column=""), "non-empty string"),
        (lambda m: m.update(table_name="ghost_table"), "not found in introspected schema"),
        (lambda m: m.update(id_column="nope"), "is not a column"),
        (lambda m: m.update(column_mapping={"title": None}), "required column_mapping fields"),
        (lambda m: m.update(column_mapping={"title": 5}), "required column_mapping fields"),
        # a placeholder *string* (instead of JSON null) for an optional field is rejected, not silently dropped
        (lambda m: m["column_mapping"].update(user_id="null"), "required column_mapping fields"),
        (lambda m: m.update(column_mapping={"summary": None}), "no usable column mappings"),
    ],
)
def test_invalid_mappings_are_rejected(mutation, message):
    bad = json.loads(json.dumps(GOOD))
    mutation(bad)
    with pytest.raises(ValueError, match=message):
        run(service(json.dumps(bad), max_retries=0).auto_map_entity("meeting", SCHEMA))


def test_llm_cannot_choose_a_table_outside_the_introspected_schema():
    """Guardrail against prompt injection through schema names: unknown tables never reach the query builder."""
    evil = {**GOOD, "table_name": "pg_catalog.pg_shadow"}
    with pytest.raises(ValueError, match="not found in introspected schema"):
        run(service(json.dumps(evil)).auto_map_entity("meeting", SCHEMA))


def test_invalid_json_response():
    with pytest.raises(ValueError, match="not valid JSON"):
        run(service("this is not json").auto_map_entity("meeting", SCHEMA))


def test_llm_retries_then_succeeds_and_then_gives_up():
    svc = service(RuntimeError("rate limited"), RuntimeError("again"), json.dumps(GOOD))
    assert run(svc.auto_map_entity("meeting", SCHEMA))["table_name"] == "crm_calls"
    failing = service(*[RuntimeError("down")] * 3, max_retries=2)
    with pytest.raises(RuntimeError, match="down"):
        run(failing.auto_map_entity("meeting", SCHEMA))


def test_empty_llm_response_is_an_error():
    with pytest.raises(ValueError, match="Empty response"):
        run(service("  ", max_retries=0).auto_map_entity("meeting", SCHEMA))


def test_compact_schema_orders_matches_first_and_caps_size():
    svc = SchemaMappingService(llm_model=FakeLLM([]))
    tables = [{"name": f"t{i}", "columns": [f"c{j}" for j in range(100)]} for i in range(60)]
    tables.append({"name": "patient_records", "columns": ["id"]})
    compact = svc._build_compact_schema_for_prompt({"tables": tables}, "patient")
    assert compact["tables"][0]["name"] == "patient_records"
    assert len(compact["tables"]) <= mapper_module._PROMPT_MAX_TABLES
    assert len(json.dumps(compact)) <= mapper_module._PROMPT_SCHEMA_MAX_CHARS + 2000
    assert svc._build_compact_schema_for_prompt("junk", "x") == {"tables": []}
    assert svc._build_compact_schema_for_prompt({"tables": "junk"}, "x") == {"tables": []}
    assert svc._build_compact_schema_for_prompt({"tables": [5, {"name": ""}]}, "x") == {"tables": []}


def test_save_and_get_mapping_from_config():
    svc = SchemaMappingService(llm_model=FakeLLM([]))
    config = {}
    svc.save_mapping_to_config({"entity_type": "deal", "table_name": "deals"}, config)
    assert svc.get_mapping("deal", config)["table_name"] == "deals"
    assert svc.get_mapping("other", config) is None
    assert svc.get_mapping("deal") is None


def test_identify_owner_column_and_validation():
    svc = service(json.dumps({"owner_column": "owner_id", "confidence": 0.8, "owner_type": "owner"}))
    schema = {"columns": ["id", "owner_id"], "column_types": {"id": "int"}}
    result = run(svc.identify_owner_column("t", schema, "contact"))
    assert result["owner_column"] == "owner_id"
    assert run(svc.identify_owner_column("t", schema, "contact")) is result  # cached
    with pytest.raises(ValueError, match="owner_column"):
        run(service(json.dumps({"confidence": 1}), max_retries=0).identify_owner_column("t", schema, "c"))
    with pytest.raises(ValueError, match="confidence"):
        run(service(json.dumps({"owner_column": "x"}), max_retries=0).identify_owner_column("t", schema, "c"))
    with pytest.raises(ValueError, match="not valid JSON"):
        run(service("nope", max_retries=0).identify_owner_column("t", schema, "c"))


def test_identify_email_column_by_pattern():
    svc = SchemaMappingService(llm_model=FakeLLM([]))
    found = run(svc.identify_email_column("users", {"columns": ["id", "E_Mail"]}, "owner"))
    assert found["email_column"] == "E_Mail" and found["method"] == "pattern_matching"
    assert run(svc.identify_email_column("users", {"columns": ["id", "E_Mail"]}, "owner")) is found
    by_dict = run(svc.identify_email_column("u2", {"columns": [{"name": "owner_email"}]}, "owner"))
    assert by_dict["email_column"] == "owner_email"
    missing = run(svc.identify_email_column("u3", {"columns": ["id"]}, "owner"))
    assert missing == {"email_column": None, "confidence": 0, "method": "failed"}


def test_default_model_name_from_env(monkeypatch):
    monkeypatch.setenv("LLM_MODEL_NAME", "gpt-test")
    assert SchemaMappingService().llm_model_name == "gpt-test"
