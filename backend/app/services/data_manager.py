from __future__ import annotations

import logging
from uuid import UUID
from typing import Any, Dict, List, Optional

from ..models import Organization, User, DatabaseDriver
from ..drivers.base import BaseDriver
from ..drivers.postgresql_driver import PostgreSQLDriver
from ..drivers.mysql_driver import MySQLDriver
from ..drivers.hubspot_driver import HubSpotDriver
from ..drivers.salesforce_driver import SalesforceDriver
from ..drivers.dynamics_driver import DynamicsDriver
from ..schema.mapper import SchemaMappingService

logger = logging.getLogger("data_manager")


class DataManager:
    """Factory + strategy over connector drivers.
    
    Supports both legacy meeting-specific operations and
    new generic CRUD for managing records within existing entity types.
    
    Note: This does NOT create new entity types/tables. It only manages
    records (add/read/update/delete) within pre-existing entity types like
    meetings, patients, contacts, deals, etc.
    """

    def __init__(self, org: Organization, driver: BaseDriver):
        self.org = org
        self.driver = driver
        self._db_driver = DatabaseDriver()
        self.schema_mapper = SchemaMappingService()

    @staticmethod
    def normalize_user_id(raw_user_id: str | None) -> str | None:
        if not raw_user_id:
            return None

        candidate = raw_user_id
        if raw_user_id.startswith("User_"):
            candidate = raw_user_id.split("User_", 1)[1]

        try:
            return str(UUID(candidate))
        except ValueError:
            return None

    @classmethod
    def from_user_id(cls, user_id: str) -> "DataManager":
        normalized_user_id = cls.normalize_user_id(user_id)
        if not normalized_user_id:
            raise ValueError("Missing or invalid user_id in agent context")

        user = User.query.get(normalized_user_id)
        if not user:
            raise ValueError("User not found")

        if not user.org_id:
            raise ValueError("User is not associated with an organization")

        org = user.organization
        connector_type = (org.connector_type or "").lower()
        config = org.connector_config or {}

        if connector_type == "postgresql":
            driver: BaseDriver = PostgreSQLDriver(config)
        elif connector_type == "mysql":
            driver = MySQLDriver(config)
        elif connector_type == "hubspot":
            driver = HubSpotDriver(config)
        elif connector_type == "salesforce":
            driver = SalesforceDriver(config)
        elif connector_type == "dynamics":
            driver = DynamicsDriver(config)
        else:
            raise ValueError(f"Unsupported connector_type: {connector_type}")

        return cls(org=org, driver=driver)

    # ===== Legacy Meeting-specific methods =====
    
    def save_meeting(self, user_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            result = self.driver.save_meeting(user_id, payload)
            self._db_driver.create_sync_log(
                org_id=self.org.id,
                status="success",
                target_system=self.org.connector_type or "unknown",
                error_message=None,
            )
            return result
        except Exception as e:
            self._db_driver.create_sync_log(
                org_id=self.org.id,
                status="failed",
                target_system=self.org.connector_type or "unknown",
                error_message=str(e),
            )
            raise

    def get_meeting_history(
        self,
        user_id: str,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        return self.driver.get_meeting_history(user_id, filters=filters)

    # ===== Generic CRUD methods (multi-entity support) =====

    async def ensure_entity_mapping(self, entity_type: str) -> None:
        """Discover schema and create mapping for entity type if not already done.
        
        This is called once per entity_type per organization to auto-map
        the external schema to our normalized format.
        """
        config = self.org.connector_config or {}
        
        # Check if mapping already exists
        if config.get("schema_mappings", {}).get(entity_type):
            logger.info(f"Schema mapping for {entity_type} already exists")
            return
        
        try:
            # Get raw schema from driver
            schema_info = await self.driver.get_schema_info()
            logger.info(f"Introspected schema for {entity_type}: {len(schema_info.get('tables', []))} tables")
            
            # Use LLM to understand it
            mapping = await self.schema_mapper.auto_map_entity(
                entity_type=entity_type,
                schema_info=schema_info,
                connector_config=config,
            )
            
            # Save mapping to org config
            self.schema_mapper.save_mapping_to_config(mapping, config)
            self.org.connector_config = config
            self.org.save()  # Persist to DB
            
            logger.info(f"Created mapping for {entity_type}: {mapping.get('table_name')}")
        except Exception as e:
            logger.error(f"Failed to auto-map {entity_type}: {e}")
            raise

    async def create_entity(
        self,
        entity_type: str,
        user_id: str,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Create a new record in an existing entity type in the organization's external system.
        
        Args:
            entity_type: The entity type to add a record to (e.g., "meeting", "patient", "contact")
            user_id: User creating the record
            payload: Record data
            
        Returns:
            Created record with ID and timestamps
        """
        try:
            # Ensure mapping exists
            await self.ensure_entity_mapping(entity_type)
            
            # Delegate to driver
            result = await self.driver.create_entity(entity_type, user_id, payload)
            
            self._db_driver.create_sync_log(
                org_id=self.org.id,
                status="success",
                target_system=self.org.connector_type or "unknown",
                error_message=None,
            )
            return result
        except Exception as e:
            self._db_driver.create_sync_log(
                org_id=self.org.id,
                status="failed",
                target_system=self.org.connector_type or "unknown",
                error_message=str(e),
            )
            raise

    async def read_entities(
        self,
        entity_type: str,
        user_id: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Read records from an existing entity type in the organization's external system.
        
        Args:
            entity_type: The entity type to query (e.g., "meeting", "patient", "contact")
            user_id: Optional user filter
            filters: Additional query filters
            
        Returns:
            List of records from the entity type
        """
        try:
            # Ensure mapping exists
            await self.ensure_entity_mapping(entity_type)
            
            # Delegate to driver
            return await self.driver.read_entities(entity_type, user_id, filters)
        except Exception as e:
            logger.error(f"Failed to read {entity_type}: {e}")
            raise

    async def update_entity(
        self,
        entity_type: str,
        entity_id: str,
        updates: Dict[str, Any],
        user_id: str,
    ) -> Dict[str, Any]:
        """Update an existing record in an entity type in the organization's external system.
        
        Args:
            entity_type: The entity type containing the record (e.g., "meeting", "patient")
            entity_id: ID of the specific record to update
            updates: Fields to update
            user_id: User performing the update
            
        Returns:
            Updated record
        """
        try:
            # Ensure mapping exists
            await self.ensure_entity_mapping(entity_type)
            
            # Delegate to driver
            result = await self.driver.update_entity(entity_type, entity_id, updates, user_id)
            
            self._db_driver.create_sync_log(
                org_id=self.org.id,
                status="success",
                target_system=self.org.connector_type or "unknown",
                error_message=None,
            )
            return result
        except Exception as e:
            self._db_driver.create_sync_log(
                org_id=self.org.id,
                status="failed",
                target_system=self.org.connector_type or "unknown",
                error_message=str(e),
            )
            raise

    async def delete_entity(
        self,
        entity_type: str,
        entity_id: str,
        user_id: str,
    ) -> bool:
        """Delete a specific record from an entity type in the organization's external system.
        
        Args:
            entity_type: The entity type containing the record (e.g., "meeting", "patient")
            entity_id: ID of the specific record to delete
            user_id: User performing the deletion
            
        Returns:
            True if successfully deleted, False otherwise
        """
        try:
            # Ensure mapping exists
            await self.ensure_entity_mapping(entity_type)
            
            # Delegate to driver
            result = await self.driver.delete_entity(entity_type, entity_id, user_id)
            
            self._db_driver.create_sync_log(
                org_id=self.org.id,
                status="success",
                target_system=self.org.connector_type or "unknown",
                error_message=None,
            )
            return result
        except Exception as e:
            self._db_driver.create_sync_log(
                org_id=self.org.id,
                status="failed",
                target_system=self.org.connector_type or "unknown",
                error_message=str(e),
            )
            raise

