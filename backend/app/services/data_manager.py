from __future__ import annotations

import logging
from uuid import UUID
from typing import Any, Dict, List, Optional

from ..models import Organization, User, DatabaseDriver
from ..extensions import db
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
        
        # Verify user is active (not deleted/disabled)
        if not user.email:
            raise ValueError("User email is missing")

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

        dm = cls(org=org, driver=driver)
        # Store normalized user_id and org_id for security checks
        dm.authorized_user_id = normalized_user_id
        dm.authorized_user = user
        return dm

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
            db.session.add(self.org)
            db.session.commit()  # Persist to DB
            
            logger.info(f"Created mapping for {entity_type}: {mapping.get('table_name')}")
        except Exception as e:
            logger.error(f"Failed to auto-map {entity_type}: {e}")
            raise

    async def create_entity(
        self,
        entity_type: str,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Create a new record in an existing entity type in the organization's external system.
        
        Args:
            entity_type: The entity type to add a record to (e.g., "meeting", "patient", "contact")
            payload: Record data
            
        Returns:
            Created record with ID and timestamps
        """
        try:
            # Ensure mapping exists
            await self.ensure_entity_mapping(entity_type)
            
            # Delegate to driver
            result = await self.driver.create_entity(entity_type, payload)
            
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
        
        Automatically filters to entities owned by the user for data isolation.
        SECURITY: Verifies user ownership before returning any data.
        Uses AI-validated schema before querying any tables.
        
        Args:
            entity_type: The entity type to query (e.g., "meeting", "patient", "contact")
            user_id: The user making the request (used for ownership filtering)
            filters: Additional query filters
            
        Returns:
            List of records owned by the user (empty list if none found or table missing)
            
        Raises:
            ValueError: If user is not authorized or org mismatch
        """
        try:
            # SECURITY: Verify the user making the request is authorized
            user_id_to_use = user_id or getattr(self, 'authorized_user_id', None)
            if not user_id_to_use:
                raise ValueError("No user_id provided or authorized user not set")
            
            # Additional safety check - ensure this user is from the same org as the driver
            if hasattr(self, 'authorized_user'):
                if str(self.authorized_user.org_id) != str(self.org.id):
                    raise ValueError("User organization mismatch")
            
            # Ensure mapping exists for external entity type
            await self.ensure_entity_mapping(entity_type)
            
            # IMPORTANT: Data isolation - only return entities the user owns
            # Get the list of entity IDs this user owns (AI-validated table access)
            # Note: This now gracefully returns [] if user_entity_ownership table doesn't exist
            owned_entity_ids = self._db_driver.get_user_entity_ids(user_id_to_use, entity_type)
            
            if not owned_entity_ids:
                # User owns no entities of this type - return empty list
                logger.info(f"User {user_id_to_use} owns no {entity_type} entities in org {self.org.id}")
                return []
            
            # Add ID filter to the query
            if not filters:
                filters = {}
            
            # Pass owned IDs to driver for filtering
            filters["owned_entity_ids"] = owned_entity_ids
            
            # For external CRM drivers, resolve user's external ID
            connector_type = (self.org.connector_type or "").lower()
            if connector_type in ["salesforce", "hubspot", "dynamics"]:
                # Get user's external CRM ID
                from ..services.crm_mapper import CRMEntityMapper
                mapper = CRMEntityMapper()
                external_user_id = mapper.resolve_doctor_in_crm(
                    user_id=str(user_id_to_use),
                    crm_type=connector_type
                )
                if external_user_id:
                    filters["external_user_id"] = external_user_id
            
            # Delegate to driver with ownership filter
            return await self.driver.read_entities(entity_type, user_id_to_use, filters)
        except Exception as e:
            logger.error(f"Failed to read {entity_type} for user {user_id}: {e}")
            raise

    async def update_entity(
        self,
        entity_type: str,
        entity_id: str,
        updates: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Update an existing record in an entity type in the organization's external system.
        
        Args:
            entity_type: The entity type containing the record (e.g., "meeting", "patient")
            entity_id: ID of the specific record to update
            updates: Fields to update
            
        Returns:
            Updated record
        """
        try:
            # Ensure mapping exists
            await self.ensure_entity_mapping(entity_type)
            
            # Delegate to driver
            result = await self.driver.update_entity(entity_type, entity_id, updates)
            
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
    ) -> bool:
        """Delete a specific record from an entity type in the organization's external system.
        
        Args:
            entity_type: The entity type containing the record (e.g., "meeting", "patient")
            entity_id: ID of the specific record to delete
            
        Returns:
            True if successfully deleted, False otherwise
        """
        try:
            # Ensure mapping exists
            await self.ensure_entity_mapping(entity_type)
            
            # Delegate to driver
            result = await self.driver.delete_entity(entity_type, entity_id)
            
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

