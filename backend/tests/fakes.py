"""In-memory test doubles shared by the service, middleware and route tests."""
from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional

from app.drivers.base import BaseDriver

MEETING_MAPPING = {
    "entity_type": "meeting",
    "table_name": "meetings",
    "id_column": "id",
    "column_mapping": {"title": "title", "summary": "summary"},
    "table_columns": ["id", "title", "summary", "owner_id"],
    "column_types": {"id": "INTEGER", "title": "TEXT", "summary": "TEXT"},
    "required_columns": ["title"],
}

SCHEMA = {"tables": [{"table_name": "meetings", "columns": ["id", "title", "summary", "owner_id"]}]}


class FakeDriver(BaseDriver):
    """Records every call; stores rows in memory and honours the owner-scope attributes."""

    def __init__(self, connector_config: Optional[Dict[str, Any]] = None):
        super().__init__(connector_config)
        self.rows: List[Dict[str, Any]] = []
        self.calls: List[tuple] = []
        self.request_owner_column = None
        self.request_owner_id = None
        self.fail_with: Optional[Exception] = None
        self._next_id = 1

    def _maybe_fail(self):
        if self.fail_with is not None:
            raise self.fail_with

    def prepare_meeting_history_filters(self, user_id, filters=None, owned_entity_ids=None):
        scoped = super().prepare_meeting_history_filters(user_id, filters, owned_entity_ids)
        self.calls.append(("prepare", scoped))
        return scoped

    def save_meeting(self, user_id, payload):
        self._maybe_fail()
        self.calls.append(("save_meeting", payload))
        row = {"id": str(self._next_id), **payload}
        self._next_id += 1
        self.rows.append(row)
        return {"id": row["id"], "title": payload.get("title")}

    def get_meeting_history(self, user_id, filters=None):
        self._maybe_fail()
        self.calls.append(("history", filters))
        return list(self.rows)

    async def create_entity(self, entity_type, payload):
        self._maybe_fail()
        self.calls.append(("create", entity_type, copy.deepcopy(payload), self.request_owner_column, self.request_owner_id))
        row = {"id": str(self._next_id), **payload}
        self._next_id += 1
        self.rows.append(row)
        return dict(row)

    async def read_entities(self, entity_type, user_id=None, filters=None):
        self._maybe_fail()
        self.calls.append(("read", entity_type, user_id, copy.deepcopy(filters), self.request_owner_column, self.request_owner_id))
        rows = list(self.rows)
        owned = (filters or {}).get("owned_entity_ids")
        if owned:
            rows = [r for r in rows if r["id"] in owned]
        return rows

    async def update_entity(self, entity_type, entity_id, updates):
        self._maybe_fail()
        self.calls.append(("update", entity_type, entity_id, updates))
        for row in self.rows:
            if row["id"] == str(entity_id):
                row.update(updates)
                return dict(row)
        raise ValueError(f"{entity_type} not found: {entity_id}")

    async def delete_entity(self, entity_type, entity_id):
        self._maybe_fail()
        self.calls.append(("delete", entity_type, entity_id))
        before = len(self.rows)
        self.rows = [r for r in self.rows if r["id"] != str(entity_id)]
        return len(self.rows) < before

    async def get_schema_info(self):
        self._maybe_fail()
        return copy.deepcopy(SCHEMA)
