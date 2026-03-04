"""Dynamic query builder for generic CRUD operations across mapped schemas."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy import text, insert, select, update, delete
from sqlalchemy.orm import Session

logger = logging.getLogger("dynamic_query_builder")


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
        """
        self.mapping = mapping
        self.entity_type = mapping.get("entity_type")
        self.table_name = mapping.get("table_name")
        self.id_column = mapping.get("id_column", "id")
        self.column_mapping = mapping.get("column_mapping", {})
        
        # Reverse mapping for output normalization
        self.reverse_mapping = {v: k for k, v in self.column_mapping.items()}

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
                db_columns[db_column] = payload[norm_field]
        
        if not db_columns:
            logger.warning(f"No mapped columns found for insert: {payload}")
            raise ValueError(f"Cannot map payload fields to table columns")
        
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
    ) -> Tuple[str, Dict[str, Any]]:
        """Build SELECT SQL with optional filtering.
        
        Args:
            filters: {"user_id": "123", "created_at_gte": "2024-01-01", ...}
            limit: Max rows to return
            
        Returns:
            (sql_string, param_dict) ready for execution
        """
        where_clauses = []
        params = {}
        
        if filters:
            for filter_key, filter_value in filters.items():
                # Map filter key to DB column
                db_column = self.column_mapping.get(filter_key, filter_key)
                
                # Handle range queries
                if filter_key.endswith("_gte"):
                    base_key = filter_key[:-4]
                    db_column = self.column_mapping.get(base_key, base_key)
                    where_clauses.append(f"{db_column} >= :{filter_key}")
                    params[filter_key] = filter_value
                elif filter_key.endswith("_lte"):
                    base_key = filter_key[:-4]
                    db_column = self.column_mapping.get(base_key, base_key)
                    where_clauses.append(f"{db_column} <= :{filter_key}")
                    params[filter_key] = filter_value
                else:
                    where_clauses.append(f"{db_column} = :{filter_key}")
                    params[filter_key] = filter_value
        
        where_str = " AND ".join(where_clauses) if where_clauses else "1=1"
        sql = f"SELECT * FROM {self.table_name} WHERE {where_str} ORDER BY {self.id_column} DESC LIMIT {limit}"
        
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
            db_column = self.column_mapping.get(norm_field, norm_field)
            db_updates[db_column] = new_value
        
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
        if "id_column" not in normalized and self.id_column in row:
            normalized["id"] = row[self.id_column]
        
        return normalized

    def normalize_rows(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Normalize multiple rows."""
        return [self.normalize_row(row) for row in rows]
