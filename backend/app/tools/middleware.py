from __future__ import annotations

from typing import Any, Dict, List, Optional
import logging

from livekit.agents import llm

from ..services.data_manager import DataManager

logger = logging.getLogger("middleware_tools")


class MiddlewareTools:
    """Industry-agnostic tools that the agent can call.
    
    Supports both legacy meeting-specific tools and new generic CRUD for RECORDS:
    - save_entity() / get_entities() / update_entity() / delete_entity()
    
    These tools work with RECORDS within existing entity types (meetings, patients, contacts, deals, etc.).
    They do NOT create new entity types/tables - only add/modify/delete records within existing ones.
    """

    def __init__(self, user_id: str):
        self.user_id = user_id

        # ===== Legacy meeting-specific tools =====
        self.save_meeting_tool = llm.function_tool(
            description="Save a summary of the current meeting, including participants and key details.",
        )(self._save_meeting)

        self.get_history_tool = llm.function_tool(
            description="Get previous meetings for this user, for additional context.",
        )(self._get_history)

        # ===== Generic CRUD tools (new) =====
        self.save_entity_tool = llm.function_tool(
            description="Create a new record in an existing entity type (e.g., add a meeting, patient, contact, deal, etc.). The entity type must already exist in the system.",
        )(self._save_entity)

        self.get_entities_tool = llm.function_tool(
            description="Retrieve records from an entity type (e.g., get all meetings, patients, contacts). Specify which entity_type to query.",
        )(self._get_entities)

        self.update_entity_tool = llm.function_tool(
            description="Update an existing record within an entity type. Requires entity_type and entity_id of the record to update.",
        )(self._update_entity)

        self.delete_entity_tool = llm.function_tool(
            description="Delete a specific record from an entity type. Requires entity_type and entity_id of the record to delete.",
        )(self._delete_entity)

    def get_tools(self):
        """Return all available tools for the agent."""
        return [
            self.save_meeting_tool,
            self.get_history_tool,
            self.save_entity_tool,
            self.get_entities_tool,
            self.update_entity_tool,
            self.delete_entity_tool,
        ]

    def _has_user_context(self) -> bool:
        return bool(self.user_id)

    # ===== Legacy meeting-specific tools =====

    async def _save_meeting(
        self,
        summary: str,
        title: Optional[str] = None,
        participants: Optional[List[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if not self._has_user_context():
            return {"error": "Missing user context; cannot save meeting."}

        dm = DataManager.from_user_id(self.user_id)
        payload: Dict[str, Any] = {
            "title": title,
            "summary": summary,
            "participants": participants or [],
            "metadata": metadata or {},
        }
        return dm.save_meeting(user_id=self.user_id, payload=payload)

    async def _get_history(
        self,
        limit: int = 10,
        user_only: bool = True,
    ) -> List[Dict[str, Any]]:
        if not self._has_user_context():
            logger.warning("Missing user context; returning empty history")
            return []

        dm = DataManager.from_user_id(self.user_id)
        filters: Dict[str, Any] = {
            "limit": max(1, min(limit, 50)),
            "user_only": user_only,
        }
        return dm.get_meeting_history(user_id=self.user_id, filters=filters)

    # ===== Generic CRUD tools (new) =====

    async def _save_entity(
        self,
        entity_type: str,
        title: Optional[str] = None,
        summary: Optional[str] = None,
        participants: Optional[List[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create a new record in an existing entity type.
        
        Args:
            entity_type: The entity type to add a record to ("meeting", "patient", "contact", "deal", etc.)
            title: Record title/name
            summary: Record description/notes  
            participants: List of people involved
            metadata: Custom metadata
            
        Returns:
            Created record with ID and timestamps
        """
        if not self._has_user_context():
            return {"error": "Missing user context; cannot create record."}

        try:
            dm = DataManager.from_user_id(self.user_id)
            payload: Dict[str, Any] = {
                "title": title,
                "summary": summary,
                "participants": participants or [],
                "metadata": metadata or {},
            }
            
            result = await dm.create_entity(entity_type, self.user_id, payload)
            logger.info(f"Created record in {entity_type}: {result.get('id')}")
            return result
        except Exception as e:
            logger.error(f"Failed to create record in {entity_type}: {e}")
            raise

    async def _get_entities(
        self,
        entity_type: str,
        limit: int = 20,
        user_only: bool = True,
    ) -> List[Dict[str, Any]]:
        """Retrieve records from a specific entity type.
        
        Args:
            entity_type: Which entity type to query ("meeting", "patient", "contact", "deal", etc.)
            limit: Max number of records to return (1-50)
            user_only: Filter to only current user's records
            
        Returns:
            List of records in normalized format
        """
        if not self._has_user_context():
            logger.warning(f"Missing user context; returning empty records for {entity_type}")
            return []

        try:
            dm = DataManager.from_user_id(self.user_id)
            
            query_filters: Dict[str, Any] = {
                "limit": max(1, min(limit, 50)),
            }
            
            user_id = self.user_id if user_only else None
            result = await dm.read_entities(entity_type, user_id, query_filters)
            logger.info(f"Retrieved {len(result)} records from {entity_type}")
            return result
        except Exception as e:
            logger.error(f"Failed to get records from {entity_type}: {e}")
            raise

    async def _update_entity(
        self,
        entity_type: str,
        entity_id: str,
        title: Optional[str] = None,
        summary: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Update an existing record in an entity.
        
        Args:
            entity_type: Which entity type the record belongs to ("meeting", "patient", "contact", etc.)
            entity_id: ID of the specific record to update
            title: New title (if updating)
            summary: New summary/notes (if updating)
            metadata: New metadata (if updating)
            
        Returns:
            Updated record
        """
        if not self._has_user_context():
            return {"error": "Missing user context; cannot update record."}

        try:
            dm = DataManager.from_user_id(self.user_id)
            
            update_payload: Dict[str, Any] = {}
            if title is not None:
                update_payload["title"] = title
            if summary is not None:
                update_payload["summary"] = summary
            if metadata is not None:
                update_payload["metadata"] = metadata
            
            result = await dm.update_entity(entity_type, entity_id, update_payload, self.user_id)
            logger.info(f"Updated record {entity_id} in {entity_type}")
            return result
        except Exception as e:
            logger.error(f"Failed to update record {entity_id} in {entity_type}: {e}")
            raise

    async def _delete_entity(
        self,
        entity_type: str,
        entity_id: str,
    ) -> Dict[str, Any]:
        """Delete a specific record from an entity.
        
        Args:
            entity_type: Which entity type the record belongs to ("meeting", "patient", "contact", etc.)
            entity_id: ID of the specific record to delete
            
        Returns:
            {"deleted": True/False}
        """
        if not self._has_user_context():
            return {"deleted": False, "error": "Missing user context; cannot delete record."}

        try:
            dm = DataManager.from_user_id(self.user_id)
            deleted = await dm.delete_entity(entity_type, entity_id, self.user_id)
            logger.info(f"Deleted record {entity_id} from {entity_type}: {deleted}")
            return {"deleted": deleted}
        except Exception as e:
            logger.error(f"Failed to delete record {entity_id} from {entity_type}: {e}")
            raise
