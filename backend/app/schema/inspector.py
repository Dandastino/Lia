"""Base class for database schema introspection across different DB types."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class SchemaInspector(ABC):
    """Base for DB-specific schema introspection.
    
    Each driver subclasses this to expose database structure:
    tables, columns, types, relationships, indexes.
    """

    @abstractmethod
    async def introspect_tables(self) -> List[Dict[str, Any]]:
        """Return list of all tables with basic info.
        
        Returns:
            [
                {
                    "name": "crm_calls",
                    "columns": ["id", "title", "summary", ...],
                    "column_types": {"id": "UUID", "title": "VARCHAR(255)", ...}
                },
                ...
            ]
        """
        pass

    @abstractmethod
    async def introspect_table(self, table_name: str) -> Dict[str, Any]:
        """Return detailed schema for one table.
        
        Returns:
            {
                "name": "crm_calls",
                "columns": [
                    {"name": "id", "type": "UUID", "nullable": False, "primary_key": True},
                    {"name": "title", "type": "VARCHAR(255)", "nullable": True},
                    {"name": "created_at", "type": "TIMESTAMP", "nullable": False, "default": "now()"},
                    ...
                ],
                "primary_keys": ["id"],
                "indexes": [...],
                "foreign_keys": [...]
            }
        """
        pass

    @abstractmethod
    async def infer_id_column(self, table_name: str) -> Optional[str]:
        """Infer the primary key column name for a table.
        
        Most tables have 'id', but some might be 'pk', 'user_id', etc.
        """
        pass
