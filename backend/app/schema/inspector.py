"""Base class for database schema introspection across different DB types."""
from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from functools import partial
from typing import Any, Dict, List, Optional

try:
    from sqlalchemy import inspect as sqlalchemy_inspect
except ImportError:
    sqlalchemy_inspect = None


class SchemaInspector(ABC):
    """Base for DB-specific schema introspection."""

    @abstractmethod
    async def introspect_tables(self) -> List[Dict[str, Any]]:
        """Return list of all tables with basic info."""
        pass

    @abstractmethod
    async def introspect_table(self, table_name: str) -> Dict[str, Any]:
        """Return detailed schema for one table."""
        pass

    @abstractmethod
    async def infer_id_column(self, table_name: str) -> Optional[str]:
        """Infer the primary key column name for a table."""
        pass


class BaseSQLSchemaInspector(SchemaInspector):
    """Base implementation for SQL database schema introspection using SQLAlchemy.
    
    Provides common logic for MySQL, PostgreSQL, and other SQL databases.
    Subclasses can override specific methods if needed for DB-specific behavior.
    """
    
    def __init__(self, engine):
        """Initialize with a SQLAlchemy engine."""
        if sqlalchemy_inspect is None:
            raise ImportError("SQLAlchemy is required for SQL schema inspection")
        self.engine = engine

    async def introspect_tables(self) -> List[Dict[str, Any]]:
        """Introspect all tables in the database using SQLAlchemy inspector.
        
        Executes blocking SQLAlchemy operations in thread pool to avoid blocking async event loop.
        """
        loop = asyncio.get_event_loop()
        
        # Run inspect() in thread pool (blocking operation)
        inspector = await loop.run_in_executor(
            None,
            partial(sqlalchemy_inspect, self.engine)
        )
        
        # Get table names in thread pool
        table_names = await loop.run_in_executor(
            None,
            inspector.get_table_names
        )
        
        tables = []
        for table_name in table_names:
            # Run get_columns in thread pool
            columns = await loop.run_in_executor(
                None,
                partial(inspector.get_columns, table_name)
            )
            
            column_names = [col["name"] for col in columns]
            column_types = {col["name"]: str(col["type"]) for col in columns}
            
            tables.append({
                "name": table_name,
                "columns": column_names,
                "column_types": column_types,
            })
        
        return tables

    async def introspect_table(self, table_name: str) -> Dict[str, Any]:
        """Introspect a specific table with full detail.
        
        Executes blocking SQLAlchemy operations in thread pool to avoid blocking async event loop.
        """
        loop = asyncio.get_event_loop()
        
        # Run inspect() in thread pool
        inspector = await loop.run_in_executor(
            None,
            partial(sqlalchemy_inspect, self.engine)
        )
        
        # Get all constraints in thread pool
        columns = await loop.run_in_executor(
            None,
            partial(inspector.get_columns, table_name)
        )
        pk = await loop.run_in_executor(
            None,
            partial(inspector.get_pk_constraint, table_name)
        )
        indexes = await loop.run_in_executor(
            None,
            partial(inspector.get_indexes, table_name)
        )
        fks = await loop.run_in_executor(
            None,
            partial(inspector.get_foreign_keys, table_name)
        )
        
        return {
            "name": table_name,
            "columns": [
                {
                    "name": col["name"],
                    "type": str(col["type"]),
                    "nullable": col.get("nullable", True),
                    "default": col.get("default"),
                }
                for col in columns
            ],
            "primary_keys": pk.get("constrained_columns", []) if pk else [],
            "indexes": indexes,
            "foreign_keys": fks,
        }

    async def infer_id_column(self, table_name: str) -> Optional[str]:
        """Infer the primary key column from table constraints.
        
        Executes blocking SQLAlchemy operations in thread pool to avoid blocking async event loop.
        """
        loop = asyncio.get_event_loop()
        
        # Run inspect() in thread pool
        inspector = await loop.run_in_executor(
            None,
            partial(sqlalchemy_inspect, self.engine)
        )
        
        # Get primary key constraint in thread pool
        pk = await loop.run_in_executor(
            None,
            partial(inspector.get_pk_constraint, table_name)
        )
        
        if pk and pk.get("constrained_columns"):
            return pk["constrained_columns"][0]
        return None
