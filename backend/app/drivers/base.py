from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class BaseDriver(ABC):
    """Connector driver interface for data operations.

    All drivers implement the same methods so that higher layers
    remain agnostic to the underlying storage / CRM.
    
    Supports both:
    - Meeting-specific methods (for backwards compatibility)
    - Generic CRUD for managing records within existing entity types
    
    Note: Drivers work with records (rows) in existing entity types (tables).
    They do NOT create new entity types/tables, only manage records within them.
    """

    def __init__(self, connector_config: Optional[Dict[str, Any]] = None):
        self.config = connector_config or {}

    # ===== Legacy Meeting-specific methods (keep for backward compatibility) =====
    
    @abstractmethod
    def save_meeting(self, user_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Persist a meeting record and return a canonical representation."""
        raise NotImplementedError

    @abstractmethod
    def get_meeting_history(
        self,
        user_id: str,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Return list of meetings for the user/organization."""
        raise NotImplementedError

    # ===== Generic CRUD methods (new multi-entity support) =====
    
    @abstractmethod
    async def create_entity(
        self,
        entity_type: str,
        user_id: str,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Create a new record in an existing entity type in the external system.
        
        Args:
            entity_type: The entity type to add a record to (\"meeting\", \"patient\", \"contact\", etc.)
            user_id: Creator/owner user ID
            payload: Normalized record data {title, summary, user_id, ...}
            
        Returns:
            Created record with id, timestamps, etc.
        """
        raise NotImplementedError

    @abstractmethod
    async def read_entities(
        self,
        entity_type: str,
        user_id: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve records from an existing entity type in the external system.
        
        Args:
            entity_type: The entity type to query ("meeting", "patient", "contact", etc.)
            user_id: Optionally filter by creator/owner
            filters: {user_id, created_at_gte, limit, ...}
            
        Returns:
            List of records in normalized format
        """
        raise NotImplementedError

    @abstractmethod
    async def update_entity(
        self,
        entity_type: str,
        entity_id: str,
        updates: Dict[str, Any],
        user_id: str,
    ) -> Dict[str, Any]:
        """Update an existing record in an entity type in the external system.
        
        Args:
            entity_type: The entity type containing the record ("meeting", "patient", etc.)
            entity_id: ID of the specific record to update
            updates: Normalized fields to update {title, summary, ...}
            user_id: User performing the update
            
        Returns:
            Updated record
        """
        raise NotImplementedError

    @abstractmethod
    async def delete_entity(
        self,
        entity_type: str,
        entity_id: str,
        user_id: str,
    ) -> bool:
        """Delete a specific record from an entity type in the external system.
        
        Args:
            entity_type: The entity type containing the record ("meeting", "patient", etc.)
            entity_id: ID of the specific record to delete
            user_id: User performing the delete
            
        Returns:
            True if deleted, False if not found
        """
        raise NotImplementedError

    @abstractmethod
    async def get_schema_info(self) -> Dict[str, Any]:
        """Return raw database schema for LLM analysis.
        
        Returns:
            {
                "tables": [
                    {
                        "name": "crm_calls",
                        "columns": ["id", "title", ...],
                        "column_types": {...}
                    },
                    ...
                ]
            }
        """
