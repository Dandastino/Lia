"""Dynamic query builder for generic CRUD operations across mapped schemas."""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .common import is_usable_column_name

logger = logging.getLogger("dynamic_query_builder")

# Table/column names end up inside SQL text (they cannot be bound as parameters), so only
# plain (optionally schema-qualified) identifiers are accepted. Names can come from an
# LLM-generated mapping or from LLM-supplied filter keys, so they are never trusted.
_IDENTIFIER_RE = re.compile(r"^[^\W\d]\w*(\.[^\W\d]\w*)?$")
MAX_LIMIT = 200


def is_safe_identifier(value: Any) -> bool:
    return isinstance(value, str) and bool(_IDENTIFIER_RE.match(value.strip()))

class DynamicQueryBuilder:
    """Builds dynamic SQL/ORM queries based on entity-to-table mappings.

    Instead of hardcoded models, uses the mapping to translate:
    - Normalized entity fields (title, summary, participants)
    - To real DB columns (call_subject, call_notes, attendees_json)
    """

    def __init__(self, mapping: Dict[str, Any]):
        """
        Args:
            mapping: Result from SchemaMappingService.auto_map_entity()
                {
                    "entity_type": "meeting",
                    "table_name": "crm_calls",
                    "id_column": "call_id",
                    "column_mapping": {...},
                    "confidence": 0.95
                }

        Raises:
            ValueError: If table_name, id_column, or column_mapping is missing or invalid.
        """
        self.mapping = mapping
        self.entity_type = mapping.get("entity_type")
        self.table_name = mapping.get("table_name")
        self.id_column = mapping.get("id_column", "id")

        # Validate required fields
        if not self.table_name:
            raise ValueError(f"Mapping missing required field 'table_name': {mapping}")
        if not self.id_column:
            raise ValueError(f"Mapping missing required field 'id_column': {mapping}")
        if not is_safe_identifier(self.table_name):
            raise ValueError("Invalid table_name in mapping: not a plain SQL identifier")
        if not is_safe_identifier(self.id_column):
            raise ValueError("Invalid id_column in mapping: not a plain SQL identifier")
        self.table_name = self.table_name.strip()
        self.id_column = self.id_column.strip()

        raw_column_mapping = mapping.get("column_mapping", {})

        if not isinstance(raw_column_mapping, dict):
            raise ValueError(
                f"Invalid column_mapping: must be dict, got {type(raw_column_mapping).__name__}"
            )

        # Build column mapping. Optional normalized fields may be absent in external schemas.
        self.column_mapping = {}
        optional_fields = {"summary", "participants", "created_at", "user_id", "owner_id", "external_id"}
        invalid_required = {}
        invalid_optional = {}

        for normalized_field, db_column in raw_column_mapping.items():
            if db_column is None:
                if normalized_field in optional_fields:
                    invalid_optional[normalized_field] = None
                else:
                    invalid_required[normalized_field] = None
            elif isinstance(db_column, str):
                if is_usable_column_name(db_column) and is_safe_identifier(db_column):
                    self.column_mapping[normalized_field] = db_column.strip()
                else:
                    if normalized_field in optional_fields:
                        invalid_optional[normalized_field] = db_column
                    else:
                        invalid_required[normalized_field] = db_column
            else:
                if normalized_field in optional_fields:
                    invalid_optional[normalized_field] = db_column
                else:
                    invalid_required[normalized_field] = db_column

        # Keep strict validation for required fields.
        if invalid_required:
            raise ValueError(
                f"Invalid column_mapping for {self.entity_type}: contains None or empty values. "
                f"Invalid required fields: {invalid_required}. "
                f"Ensure required normalized fields map to actual DB columns. "
                f"Full mapping: {raw_column_mapping}"
            )

        if invalid_optional:
            logger.info(
                "Ignoring unmapped optional fields for %s: %s",
                self.entity_type,
                ", ".join(sorted(invalid_optional.keys())),
            )

        if not self.column_mapping:
            raise ValueError(
                f"Invalid column_mapping for {self.entity_type}: no usable mapped columns after sanitization. "
                f"Full mapping: {raw_column_mapping}"
            )

        # Reverse mapping for output normalization
        self.reverse_mapping = {v: k for k, v in self.column_mapping.items()}
        raw_table_columns = mapping.get("table_columns", [])
        self.table_columns = {
            col.strip()
            for col in raw_table_columns
            if isinstance(col, str) and is_safe_identifier(col)
        }
        owner_column = mapping.get("owner_column")
        self.owner_column = owner_column.strip() if is_safe_identifier(owner_column) else None

    @staticmethod
    def _coerce_limit(value: Any, default: int = 20) -> int:
        try:
            return max(1, min(int(value), MAX_LIMIT))
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _coerce_offset(value: Any) -> int:
        try:
            return max(0, min(int(value), 1_000_000))
        except (TypeError, ValueError):
            return 0

    def _resolve_filter_column(self, key: str, trusted_columns: Iterable[str]) -> Optional[str]:
        """Map a filter key to a DB column, accepting only known columns."""
        if key in self.column_mapping:
            return self.column_mapping[key]
        known = (
            set(self.reverse_mapping)
            | self.table_columns
            | {self.id_column}
            | ({self.owner_column} if self.owner_column else set())
            | {c for c in trusted_columns if is_safe_identifier(c)}
        )
        return key if key in known else None

    @staticmethod
    def _coerce_param_value(value: Any) -> Any:
        """Convert complex Python values into DB-safe parameter values."""
        if isinstance(value, (dict, list)):
            return json.dumps(value)
        return value

    def build_insert(self, payload: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        """Build INSERT SQL from normalized payload.

        Args:
            payload: {"title": "...", "summary": "...", "participants": [...], ...}

        Returns:
            (sql_string, param_dict) ready for execution
        """
        # Map normalized fields to DB columns
        db_columns = {}
        for norm_field, db_column in self.column_mapping.items():
            if norm_field in payload and payload[norm_field] is not None:
                db_columns[db_column] = self._coerce_param_value(payload[norm_field])

        # Allow direct DB column writes only for known table columns.
        # This supports real-field writes like email/gmail columns even when
        # they are not part of the normalized mapping.
        for payload_key, payload_value in payload.items():
            if payload_key in self.column_mapping:
                continue
            if payload_key in self.table_columns and payload_value is not None:
                db_columns[payload_key] = self._coerce_param_value(payload_value)

        if not db_columns:
            logger.warning(f"No mapped columns found for insert: {payload}")
            raise ValueError("Cannot map payload fields to table columns")

        # Build raw SQL insert
        columns_str = ", ".join(db_columns.keys())
        placeholders = ", ".join([f":{k}" for k in db_columns.keys()])
        sql = f"INSERT INTO {self.table_name} ({columns_str}) VALUES ({placeholders}) RETURNING *"

        logger.debug(f"Insert SQL: {sql}")
        return sql, db_columns

    def build_select(
        self,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 20,
        trusted_columns: Iterable[str] = (),
    ) -> Tuple[str, Dict[str, Any]]:
        """Build SELECT SQL with optional filtering.

        Args:
            filters: {
                "user_id": "123",
                "created_at_gte": "2024-01-01",
                "owned_entity_ids": ["id1", "id2", "id3"],  # IN clause for data isolation
                "offset": 40,
                ...
            }
            limit: Max rows to return (clamped to MAX_LIMIT)
            trusted_columns: server-side column names (e.g. the owner column) that may be
                filtered even if absent from the mapping. Never pass client/LLM input here.

        Returns:
            (sql_string, param_dict) ready for execution

        Raises:
            ValueError: if a filter refers to a column that is not part of the mapping.
        """
        filters = dict(filters or {})
        limit = self._coerce_limit(filters.pop("limit", limit))
        offset = self._coerce_offset(filters.pop("offset", 0))

        where_clauses = []
        params: Dict[str, Any] = {}

        for index, (filter_key, filter_value) in enumerate(filters.items()):
            # Special handling for ownership filter (data isolation)
            if filter_key == "owned_entity_ids":
                if isinstance(filter_value, list) and filter_value:
                    placeholders = []
                    for idx, entity_id in enumerate(filter_value):
                        name = f"owned_id_{idx}"
                        placeholders.append(f":{name}")
                        params[name] = entity_id
                    where_clauses.append(f"{self.id_column} IN ({', '.join(placeholders)})")
                continue

            operator = "="
            base_key = filter_key
            if filter_key.endswith("_gte"):
                operator, base_key = ">=", filter_key[:-4]
            elif filter_key.endswith("_lte"):
                operator, base_key = "<=", filter_key[:-4]

            db_column = self._resolve_filter_column(base_key, trusted_columns)
            if db_column is None:
                raise ValueError(f"Unknown filter column: {base_key!r}")

            param_name = f"filter_{index}"
            where_clauses.append(f"{db_column} {operator} :{param_name}")
            params[param_name] = filter_value

        where_str = " AND ".join(where_clauses) if where_clauses else "1=1"
        sql = (
            f"SELECT * FROM {self.table_name} WHERE {where_str} "
            f"ORDER BY {self.id_column} DESC LIMIT {limit}"
        )
        if offset:
            sql += f" OFFSET {offset}"

        logger.debug(f"Select SQL: {sql}")
        return sql, params

    def build_update(self, entity_id: str, updates: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        """Build UPDATE SQL.

        Args:
            entity_id: Value of the ID column
            updates: Normalized updates {"title": "new title", ...}

        Returns:
            (sql_string, param_dict) ready for execution
        """
        # Map normalized fields to DB columns
        db_updates = {}
        for norm_field, new_value in updates.items():
            if norm_field in self.column_mapping:
                db_column = self.column_mapping[norm_field]
            elif norm_field in self.table_columns:
                db_column = norm_field
            else:
                logger.debug(f"Skipping update field {norm_field}: not mapped and not a known table column")
                continue
            if not isinstance(db_column, str) or not db_column.strip():
                logger.debug(f"Skipping update field {norm_field}: no mapped column")
                continue
            db_updates[db_column] = self._coerce_param_value(new_value)

        if not db_updates:
            raise ValueError("No fields to update")

        set_clauses = ", ".join([f"{k} = :{k}" for k in db_updates.keys()])
        sql = f"UPDATE {self.table_name} SET {set_clauses} WHERE {self.id_column} = :entity_id RETURNING *"

        params = {**db_updates, "entity_id": entity_id}
        logger.debug(f"Update SQL: {sql}")
        return sql, params

    def build_delete(self, entity_id: str) -> Tuple[str, Dict[str, Any]]:
        """Build DELETE SQL.

        Args:
            entity_id: Value of the ID column

        Returns:
            (sql_string, param_dict) ready for execution
        """
        sql = f"DELETE FROM {self.table_name} WHERE {self.id_column} = :entity_id"
        params = {"entity_id": entity_id}
        logger.debug(f"Delete SQL: {sql}")
        return sql, params

    def normalize_row(self, row: Dict[str, Any]) -> Dict[str, Any]:
        """Convert DB row back to normalized format.

        Reverse-maps DB columns to normalized field names.
        """
        normalized = {}
        for db_col, value in row.items():
            norm_field = self.reverse_mapping.get(db_col, db_col)
            normalized[norm_field] = value

        # Always include id and created_at at top level
        if "id" not in normalized and self.id_column in row:
            normalized["id"] = row[self.id_column]

        return normalized

    def normalize_rows(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Normalize multiple rows."""
        return [self.normalize_row(row) for row in rows]
