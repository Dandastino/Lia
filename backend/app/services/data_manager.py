from __future__ import annotations

import copy
import logging
import re
from typing import Any, Dict, List, Optional, Callable

import requests
from sqlalchemy import inspect as sqlalchemy_inspect, text as sqlalchemy_text

from ..models import Organization, User, DatabaseDriver
from ..extensions import db
from ..drivers.base import BaseDriver
from ..drivers.postgresql_driver import PostgreSQLDriver
from ..drivers.mysql_driver import MySQLDriver
from ..drivers.hubspot_driver import HubSpotDriver
from ..drivers.salesforce_driver import SalesforceDriver
from ..drivers.dynamics_driver import DynamicsDriver
from ..schema.mapper import SchemaMappingService
from ..utils import normalize_user_id

logger = logging.getLogger("data_manager")


class DataManager:
    """Factory + strategy over connector drivers.
    
    Supports both legacy meeting-specific operations and
    new generic CRUD for managing records within existing entity types.
    """

    def __init__(self, org: Organization, driver: BaseDriver):
        self.org = org
        self.driver = driver
        self._db_driver = DatabaseDriver()
        self.schema_mapper = SchemaMappingService()

    @staticmethod
    def _compact_error(error: Exception) -> str:
        text = str(error).strip()
        if not text:
            return "unknown error"
        return next((line.strip() for line in text.splitlines() if line.strip()), text)

    def _log_sync_operation(self, operation: Callable, *args, **kwargs) -> Any:
        """Execute an operation with automatic sync logging."""
        try:
            result = operation(*args, **kwargs)
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

    def _sync_driver_config(self, config: Dict[str, Any]) -> None:
        """Keep the active driver in sync with freshly persisted connector config."""
        # Use a detached copy to avoid accidental cross-mutation between ORM JSON
        # state and per-request driver runtime state.
        self.driver.config = copy.deepcopy(config)

    def _resolve_owner_column(self, entity_type: str) -> Optional[str]:
        mapping = ((self.driver.config or {}).get("schema_mappings") or {}).get(entity_type) or {}
        column_mapping = mapping.get("column_mapping") or {}
        explicit_owner_column = mapping.get("owner_column")

        if isinstance(explicit_owner_column, str) and explicit_owner_column.strip():
            return explicit_owner_column.strip()

        if isinstance(column_mapping, dict):
            for mapping_key in ("owner_id", "user_id"):
                mapped_owner_col = column_mapping.get(mapping_key)
                if isinstance(mapped_owner_col, str) and mapped_owner_col.strip():
                    return mapped_owner_col.strip()

        # Generic fallback for legacy mappings created before owner fields were
        # consistently inferred by LLM; avoid domain-specific keywords.
        table_columns = mapping.get("table_columns") or []
        if not isinstance(table_columns, list):
            return None

        normalized = {
            str(col).strip().lower(): str(col).strip()
            for col in table_columns
            if isinstance(col, str) and col.strip()
        }

        generic_candidates = [
            "owner_id",
            "user_id",
            "assignee_id",
            "assigned_to_id",
            "created_by",
            "creator_id",
        ]
        for candidate in generic_candidates:
            if candidate in normalized:
                return normalized[candidate]
        return None

    @staticmethod
    def _is_safe_sql_identifier(value: str) -> bool:
        return bool(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value or ""))

    async def _resolve_external_owner_id(self, owner_column: Optional[str] = None) -> Optional[str]:
        """Resolve current user's external owner/user ID for connector scoping."""
        connector_type = (self.org.connector_type or "").lower()
        if not hasattr(self, "authorized_user_id"):
            return None

        from ..services.crm_mapper import CRMEntityMapper

        mapper = CRMEntityMapper()
        external_user_id = mapper.resolve_doctor_in_crm(
            user_id=str(self.authorized_user_id),
            crm_type=connector_type,
        )
        if external_user_id:
            return str(external_user_id)

        # HubSpot fallback: resolve owner by authenticated user's email,
        # then persist mapping for subsequent requests.
        if connector_type == "hubspot":
            user_email = getattr(getattr(self, "authorized_user", None), "email", None)
            api_key = (self.driver.config or {}).get("api_key") if hasattr(self.driver, "config") else None
            if user_email and api_key:
                try:
                    base_url = getattr(self.driver, "_base_url", "https://api.hubapi.com")
                    verify_ssl = bool((self.driver.config or {}).get("verify_ssl", True)) if hasattr(self.driver, "config") else True
                    timeout = float((self.driver.config or {}).get("request_timeout_seconds", 20)) if hasattr(self.driver, "config") else 20.0
                    timeout = max(1.0, timeout)

                    resp = requests.get(
                        f"{base_url}/crm/v3/owners/",
                        headers={
                            "Authorization": f"Bearer {api_key}",
                            "Content-Type": "application/json",
                        },
                        params={"email": user_email, "archived": "false"},
                        timeout=timeout,
                        verify=verify_ssl,
                    )
                    if resp.ok:
                        results = (resp.json() or {}).get("results") or []
                        # Prefer exact email match and active owner entries.
                        exact = [
                            row for row in results
                            if isinstance(row, dict)
                            and str(row.get("email") or "").strip().lower() == str(user_email).strip().lower()
                            and not bool(row.get("archived", False))
                        ]
                        pool = exact or [row for row in results if isinstance(row, dict)]
                        if pool:
                            resolved_id = str(pool[0].get("id") or "").strip()
                            if resolved_id and resolved_id.isdigit():
                                mapper.register_doctor_to_crm(
                                    user_id=str(self.authorized_user_id),
                                    org_id=str(self.org.id),
                                    crm_type=connector_type,
                                    external_user_id=resolved_id,
                                    external_email=user_email,
                                )
                                logger.info(
                                    "Auto-linked HubSpot owner id %s for user %s by email %s",
                                    resolved_id,
                                    self.authorized_user_id,
                                    user_email,
                                )
                                return resolved_id
                except Exception as exc:
                    logger.warning("HubSpot owner auto-resolution failed for user %s: %s", self.authorized_user_id, exc)

        # SQL fallback: try to find the current user in external owner/user tables by email.
        if connector_type not in ["postgresql", "mysql"] or not hasattr(self.driver, "engine"):
            return None

        user_email = getattr(getattr(self, "authorized_user", None), "email", None)
        if not user_email:
            return None

        inspector = sqlalchemy_inspect(self.driver.engine)
        table_names = inspector.get_table_names()

        schema_mappings = (self.driver.config or {}).get("schema_mappings") or {}
        mapped_tables = []
        preferred_tables = []

        for mapping in schema_mappings.values():
            if not isinstance(mapping, dict):
                continue
            table_name = mapping.get("table_name")
            if isinstance(table_name, str) and table_name in table_names:
                mapped_tables.append(table_name)
                if owner_column:
                    try:
                        foreign_keys = inspector.get_foreign_keys(table_name) or []
                        for fk in foreign_keys:
                            if not isinstance(fk, dict):
                                continue
                            constrained_columns = fk.get("constrained_columns") or []
                            if owner_column not in constrained_columns:
                                continue
                            referred_table = fk.get("referred_table")
                            if isinstance(referred_table, str) and referred_table in table_names:
                                preferred_tables.append(referred_table)
                    except Exception:
                        # Foreign key metadata is best-effort and may be unavailable.
                        pass

        preferred_tables = list(dict.fromkeys(preferred_tables + mapped_tables + list(table_names)))

        for table_name in preferred_tables:
            try:
                if not self._is_safe_sql_identifier(table_name):
                    continue

                pk_info = inspector.get_pk_constraint(table_name) or {}
                pk_cols = pk_info.get("constrained_columns") or []
                if not pk_cols:
                    continue
                pk_col = pk_cols[0]
                if not self._is_safe_sql_identifier(pk_col):
                    continue

                cols = inspector.get_columns(table_name)
                col_names = [c.get("name") for c in cols if isinstance(c, dict) and c.get("name")]
                table_schema = {
                    "columns": col_names,
                    "column_types": {
                        c.get("name"): str(c.get("type"))
                        for c in cols
                        if isinstance(c, dict) and c.get("name")
                    },
                }

                email_probe = await self.schema_mapper.identify_email_column(
                    table_name=table_name,
                    table_schema=table_schema,
                    user_type="owner",
                )
                email_col = email_probe.get("email_column") if isinstance(email_probe, dict) else None
                if not isinstance(email_col, str) or email_col not in col_names:
                    # Heuristic fallback when LLM/pattern inference cannot identify an email field.
                    email_col = next(
                        (
                            c
                            for c in col_names
                            if isinstance(c, str)
                            and any(token in c.lower() for token in ["email", "mail"]) 
                        ),
                        None,
                    )
                if not email_col:
                    continue
                if not self._is_safe_sql_identifier(email_col):
                    continue

                query = sqlalchemy_text(
                    f"SELECT {pk_col} FROM {table_name} "
                    f"WHERE LOWER(CAST({email_col} AS TEXT)) = LOWER(:user_email) LIMIT 2"
                )
                with self.driver.get_session() as session:
                    rows = session.execute(query, {"user_email": user_email}).fetchall()
                if not rows:
                    continue
                if len(rows) > 1:
                    logger.warning(
                        "Skipping owner auto-link for user %s: ambiguous email match in table %s",
                        self.authorized_user_id,
                        table_name,
                    )
                    continue

                resolved_id = str(rows[0][0])
                mapper.register_doctor_to_crm(
                    user_id=str(self.authorized_user_id),
                    org_id=str(self.org.id),
                    crm_type=connector_type,
                    external_user_id=resolved_id,
                    external_email=user_email,
                )
                logger.info(
                    "Auto-linked external owner id %s for user %s via table %s",
                    resolved_id,
                    self.authorized_user_id,
                    table_name,
                )
                return resolved_id
            except Exception:
                continue

        return None

    async def _set_driver_owner_context(self, entity_type: str) -> Dict[str, Optional[str]]:
        owner_column = self._resolve_owner_column(entity_type)
        owner_id = await self._resolve_external_owner_id(owner_column=owner_column)
        setattr(self.driver, "request_owner_column", owner_column)
        setattr(self.driver, "request_owner_id", owner_id)
        return {"owner_column": owner_column, "owner_id": owner_id}

    def _clear_driver_owner_context(self) -> None:
        setattr(self.driver, "request_owner_column", None)
        setattr(self.driver, "request_owner_id", None)

    async def _log_sync_operation_async(self, operation: Callable, *args, **kwargs) -> Any:
        """Async version of _log_sync_operation."""
        try:
            result = await operation(*args, **kwargs)
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

    @classmethod
    def from_user_id(cls, user_id: str) -> "DataManager":
        normalized_user_id = normalize_user_id(user_id)
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
        connector_type = (self.org.connector_type or "").lower()
        owner_user_id = getattr(self, "authorized_user_id", None) or normalize_user_id(user_id)

        # Legacy path parity: auto-resolve HubSpot owner context, so meetings are
        # visible in HubSpot owner-filtered views (e.g., "My activities").
        if connector_type == "hubspot" and owner_user_id:
            try:
                from ..services.crm_mapper import CRMEntityMapper

                mapper = CRMEntityMapper()
                resolved_owner_id = mapper.resolve_doctor_in_crm(
                    user_id=str(owner_user_id),
                    crm_type="hubspot",
                )

                if not resolved_owner_id:
                    user_email = getattr(getattr(self, "authorized_user", None), "email", None)
                    api_key = (self.driver.config or {}).get("api_key") if hasattr(self.driver, "config") else None
                    if user_email and api_key:
                        base_url = getattr(self.driver, "_base_url", "https://api.hubapi.com")
                        verify_ssl = bool((self.driver.config or {}).get("verify_ssl", True)) if hasattr(self.driver, "config") else True
                        timeout = float((self.driver.config or {}).get("request_timeout_seconds", 20)) if hasattr(self.driver, "config") else 20.0
                        timeout = max(1.0, timeout)
                        resp = requests.get(
                            f"{base_url}/crm/v3/owners/",
                            headers={
                                "Authorization": f"Bearer {api_key}",
                                "Content-Type": "application/json",
                            },
                            params={"email": user_email, "archived": "false"},
                            timeout=timeout,
                            verify=verify_ssl,
                        )
                        if resp.ok:
                            results = (resp.json() or {}).get("results") or []
                            exact = [
                                row for row in results
                                if isinstance(row, dict)
                                and str(row.get("email") or "").strip().lower() == str(user_email).strip().lower()
                                and not bool(row.get("archived", False))
                            ]
                            pool = exact or [row for row in results if isinstance(row, dict)]
                            if pool:
                                candidate = str(pool[0].get("id") or "").strip()
                                if candidate.isdigit():
                                    resolved_owner_id = candidate
                                    mapper.register_doctor_to_crm(
                                        user_id=str(owner_user_id),
                                        org_id=str(self.org.id),
                                        crm_type="hubspot",
                                        external_user_id=resolved_owner_id,
                                        external_email=user_email,
                                    )

                if resolved_owner_id:
                    setattr(self.driver, "request_owner_id", str(resolved_owner_id))
            except Exception as exc:
                logger.warning("Failed to resolve HubSpot owner for legacy save_meeting: %s", exc)

        try:
            result = self._log_sync_operation(
                self.driver.save_meeting,
                user_id,
                payload
            )
        finally:
            if connector_type == "hubspot":
                setattr(self.driver, "request_owner_id", None)

        # Keep legacy meeting flow aligned with generic CRUD ownership behavior.
        # Without this, user-scoped history/update paths can miss newly created meetings.
        meeting_id = result.get("id") if isinstance(result, dict) else None
        if meeting_id and owner_user_id:
            ownership = self._db_driver.assign_entity_to_user(
                user_id=owner_user_id,
                org_id=self.org.id,
                entity_type="meeting",
                external_entity_id=str(meeting_id),
            )
            if ownership:
                logger.info("Auto-assigned meeting '%s' to user %s", meeting_id, owner_user_id)

        return result

    def get_meeting_history(
        self,
        user_id: str,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        base_filters: Dict[str, Any] = dict(filters or {})
        user_only = bool(base_filters.get("user_only", True))
        owned_entity_ids: List[str] = []

        if user_only:
            # Enforce multi-tenant isolation through generic ownership links when
            # available, regardless of connector or business domain.
            ownership_user_id = getattr(self, "authorized_user_id", None) or normalize_user_id(user_id) or user_id
            owned_entity_ids = self._db_driver.get_user_entity_ids(
                user_id=ownership_user_id,
                entity_type="meeting",
                org_id=self.org.id,
            )
            if not owned_entity_ids and not bool(base_filters.get("allow_unowned_read", True)):
                return []

        scoped_filters = self.driver.prepare_meeting_history_filters(
            user_id=user_id,
            filters=base_filters,
            owned_entity_ids=owned_entity_ids if user_only else None,
        )
        return self.driver.get_meeting_history(user_id, filters=scoped_filters)

    # ===== Generic CRUD methods (multi-entity support) =====

    async def ensure_entity_mapping(self, entity_type: str) -> None:
        """Discover schema and create mapping for entity type if not already done.
        
        This is called once per entity_type per organization to auto-map
        the external schema to our normalized format.
        """
        # Use a detached copy so SQLAlchemy detects JSONB changes on reassignment.
        config = copy.deepcopy(self.org.connector_config or {})
        
        # Check if mapping already exists
        existing_mapping = config.get("schema_mappings", {}).get(entity_type)
        schema_info = None

        def _mapping_matches_schema(mapping: Dict[str, Any], current_schema: Dict[str, Any]) -> bool:
            table_name = mapping.get("table_name")
            tables = current_schema.get("tables", []) if isinstance(current_schema, dict) else []
            if not isinstance(table_name, str) or not table_name.strip() or not isinstance(tables, list):
                return False

            target = table_name.strip().lower()
            for table in tables:
                if not isinstance(table, dict):
                    continue
                candidate = table.get("table_name") or table.get("name")
                if isinstance(candidate, str) and candidate.strip().lower() == target:
                    return True
            return False

        if existing_mapping:
            schema_info = await self.driver.get_schema_info()
            if not _mapping_matches_schema(existing_mapping, schema_info):
                logger.warning(
                    "Existing mapping for %s points to unknown table/object '%s'; rebuilding mapping",
                    entity_type,
                    existing_mapping.get("table_name"),
                )
                config.get("schema_mappings", {}).pop(entity_type, None)
                existing_mapping = None

        if existing_mapping:
            # Backfill metadata for older mappings that were saved before
            # we started persisting table/required columns.
            has_table_metadata = bool(existing_mapping.get("table_columns")) and (
                existing_mapping.get("required_columns") is not None
            )
            has_type_metadata = isinstance(existing_mapping.get("column_types"), dict) and bool(
                existing_mapping.get("column_types")
            )
            if has_table_metadata and has_type_metadata:
                self._sync_driver_config(config)
                logger.info(f"Schema mapping for {entity_type} already exists")
                return

            if schema_info is None:
                schema_info = await self.driver.get_schema_info()
            self._enrich_mapping_with_table_metadata(existing_mapping, schema_info)
            self.schema_mapper.save_mapping_to_config(existing_mapping, config)
            self.org.connector_config = config
            db.session.add(self.org)
            db.session.commit()
            self._sync_driver_config(config)
            logger.info("Backfilled table metadata for existing mapping %s", entity_type)
            return
        
        try:
            # Get raw schema from driver
            if schema_info is None:
                schema_info = await self.driver.get_schema_info()
            logger.info(f"Introspected schema for {entity_type}: {len(schema_info.get('tables', []))} tables")
            
            # Use LLM to understand it
            mapping = await self.schema_mapper.auto_map_entity(
                entity_type=entity_type,
                schema_info=schema_info,
                connector_config=config,
            )
            
            # Save table metadata (columns + required columns) for runtime validation.
            self._enrich_mapping_with_table_metadata(mapping, schema_info)

            # Save mapping to org config
            self.schema_mapper.save_mapping_to_config(mapping, config)
            self.org.connector_config = config
            db.session.add(self.org)
            db.session.commit()  # Persist to DB
            self._sync_driver_config(config)
            
            logger.info(f"Created mapping for {entity_type}: {mapping.get('table_name')}")
        except Exception as e:
            logger.error("Failed to auto-map %s: %s", entity_type, self._compact_error(e))
            raise

    @staticmethod
    def _enrich_mapping_with_table_metadata(mapping: Dict[str, Any], schema_info: Dict[str, Any]) -> None:
        """Attach table metadata to a mapping for strict write validation.

        This metadata lets query building accept direct DB columns safely
        and provides required-column hints for missing-field prompts.
        """
        table_name = mapping.get("table_name")
        tables = schema_info.get("tables", []) if isinstance(schema_info, dict) else []
        if not table_name or not isinstance(tables, list):
            return

        matched = None
        target_table = str(table_name).strip().lower()
        for table in tables:
            if not isinstance(table, dict):
                continue
            candidate = table.get("table_name") or table.get("name")
            if isinstance(candidate, str) and candidate.strip().lower() == target_table:
                matched = table
                break

        if not matched:
            mapped_columns = mapping.get("column_mapping", {})
            if isinstance(mapped_columns, dict):
                mapping["table_columns"] = sorted(
                    {
                        str(col).strip()
                        for col in mapped_columns.values()
                        if isinstance(col, str) and col.strip()
                    }
                )
                mapping["required_columns"] = mapping.get("required_columns", [])
            return

        columns = matched.get("columns", [])
        table_columns: List[str] = []
        column_details: List[Dict[str, Any]] = []
        if isinstance(columns, list):
            if columns and isinstance(columns[0], dict):
                table_columns = [str(col.get("name")).strip() for col in columns if isinstance(col, dict) and col.get("name")]
                column_details = [col for col in columns if isinstance(col, dict)]
            else:
                table_columns = [str(col).strip() for col in columns if isinstance(col, str) and col.strip()]

        id_column = mapping.get("id_column")
        required_columns = []
        for col in column_details:
            if not isinstance(col, dict):
                continue

            col_name = col.get("name")
            if not col_name or col_name == id_column:
                continue

            if col.get("nullable", True):
                continue

            if col.get("default") is not None:
                continue

            if col.get("autoincrement"):
                continue

            required_columns.append(col_name)

        # Extract enum values from schema metadata for field constraints.
        # These are used by middleware to inform the LLM of valid enum options.
        enum_values = matched.get("enum_values", {})
        if isinstance(enum_values, dict) and enum_values:
            mapping["enum_values"] = enum_values

        # Preserve property types so drivers can normalize outbound payloads
        # (e.g., HubSpot date/datetime fields expect epoch milliseconds).
        column_types = matched.get("column_types", {})
        if isinstance(column_types, dict) and column_types:
            mapping["column_types"] = column_types

        # Always include mapped DB columns in table_columns even if schema payload was minimal.
        mapped_columns = mapping.get("column_mapping", {})
        mapped_values = []
        if isinstance(mapped_columns, dict):
            mapped_values = [str(col).strip() for col in mapped_columns.values() if isinstance(col, str) and col.strip()]

        mapping["table_columns"] = sorted(set(table_columns + mapped_values))
        mapping["required_columns"] = sorted(set(required_columns))

    async def create_entity(
        self,
        entity_type: str,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Create a new record in an existing entity type in the organization's external system.
        
        Automatically assigns ownership to the current user for data isolation.
        """
        # Ensure mapping exists
        await self.ensure_entity_mapping(entity_type)
        
        owner_scope = await self._set_driver_owner_context(entity_type)
        try:
            owner_column = owner_scope.get("owner_column")
            owner_id = owner_scope.get("owner_id")

            # Auto-stamp owner FK for scoped SQL tables when available.
            if owner_column and owner_id and owner_column not in payload:
                payload[owner_column] = owner_id

            # Delegate to driver with sync logging
            result = await self._log_sync_operation_async(
                self.driver.create_entity,
                entity_type,
                payload
            )
        finally:
            self._clear_driver_owner_context()
        
        # AUTO-ASSIGNMENT: Assign ownership to current user
        if result and result.get("id") and hasattr(self, 'authorized_user_id'):
            try:
                self._db_driver.assign_entity_to_user(
                    user_id=self.authorized_user_id,
                    org_id=self.org.id,
                    entity_type=entity_type,
                    external_entity_id=str(result["id"]),
                )
                logger.info(
                    f"Auto-assigned {entity_type} '{result['id']}' to user {self.authorized_user_id}"
                )
            except Exception as e:
                logger.warning(f"Failed to auto-assign ownership: {e}")
                # Don't fail the whole operation if assignment fails
        
        return result

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

            owner_scope = await self._set_driver_owner_context(entity_type)
            owner_column = owner_scope.get("owner_column")
            owner_id = owner_scope.get("owner_id")
            
            # Build a mutable filter bag.
            if not filters:
                filters = {}
            
            # Enforce owner scope when we can map both owner column and owner id.
            if owner_column and owner_id:
                filters[owner_column] = owner_id
                logger.info(
                    "Applying owner scope read filter %s=%s for entity %s",
                    owner_column,
                    owner_id,
                    entity_type,
                )

            # IMPORTANT: Data isolation/read mode settings.
            # - restrict_to_owned_entities=True: only linked rows are returned.
            # - restrict_to_owned_entities=False (default): return all accessible rows and
            #   bootstrap ownership links for pre-existing entities.
            owned_entity_ids = self._db_driver.get_user_entity_ids(
                user_id_to_use,
                entity_type,
                org_id=self.org.id,
            )
            allow_unowned_read = bool((self.org.connector_config or {}).get("allow_unowned_read", True))
            restrict_to_owned = bool((self.org.connector_config or {}).get("restrict_to_owned_entities", False))

            # If SQL owner scope is active, query directly with owner filter and skip
            # ownership table gating so users see exactly their DB-linked records.
            if owner_column and owner_id:
                result = await self.driver.read_entities(entity_type, user_id_to_use, filters)
                self._bootstrap_ownership_from_results(user_id_to_use, entity_type, result)
                self._clear_driver_owner_context()
                return result

            if restrict_to_owned and owned_entity_ids:
                filters["owned_entity_ids"] = owned_entity_ids
                result = await self.driver.read_entities(entity_type, user_id_to_use, filters)
                return result

            if restrict_to_owned and not owned_entity_ids:
                logger.info(
                    "restrict_to_owned_entities enabled and no ownership rows for user %s (%s)",
                    user_id_to_use,
                    entity_type,
                )
                return []

            if not allow_unowned_read:
                logger.info(
                    "User %s owns no %s entities in org %s and unowned fallback is disabled",
                    user_id_to_use,
                    entity_type,
                    self.org.id,
                )
                return []

            # Migration-friendly fallback: first read returns existing external rows,
            # then we persist ownership links so subsequent reads stay isolated.
            logger.info(
                "Reading external %s records without ownership restriction for user %s",
                entity_type,
                user_id_to_use,
            )
            result = await self.driver.read_entities(entity_type, user_id_to_use, filters)
            self._bootstrap_ownership_from_results(user_id_to_use, entity_type, result)
            self._clear_driver_owner_context()
            return result
        except Exception as e:
            logger.error(f"Failed to read {entity_type} for user {user_id}: {e}")
            raise
        finally:
            self._clear_driver_owner_context()

    def _bootstrap_ownership_from_results(
        self,
        user_id,
        entity_type: str,
        rows: List[Dict[str, Any]],
    ) -> None:
        """Create ownership links for externally pre-existing rows returned in fallback mode."""
        if not rows:
            return

        assigned = 0
        for row in rows:
            entity_id = row.get("id") if isinstance(row, dict) else None
            if not entity_id:
                continue

            ownership = self._db_driver.assign_entity_to_user(
                user_id=user_id,
                org_id=self.org.id,
                entity_type=entity_type,
                external_entity_id=str(entity_id),
            )
            if ownership:
                assigned += 1

        if assigned:
            logger.info(
                "Bootstrapped %s ownership rows for user %s (%s)",
                assigned,
                user_id,
                entity_type,
            )

    async def update_entity(
        self,
        entity_type: str,
        entity_id: str,
        updates: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Update an existing record in an entity type in the organization's external system."""
        # Ensure mapping exists
        await self.ensure_entity_mapping(entity_type)

        user_id_to_use = getattr(self, "authorized_user_id", None)
        if user_id_to_use and not self._db_driver.user_owns_entity(user_id_to_use, entity_type, str(entity_id)):
            raise ValueError(
                f"Unauthorized update: user does not own {entity_type} entity {entity_id}"
            )
        
        await self._set_driver_owner_context(entity_type)
        try:
            # Delegate to driver with sync logging
            return await self._log_sync_operation_async(
                self.driver.update_entity,
                entity_type,
                entity_id,
                updates
            )
        finally:
            self._clear_driver_owner_context()

    async def delete_entity(
        self,
        entity_type: str,
        entity_id: str,
    ) -> bool:
        """Delete a specific record from an entity type in the organization's external system."""
        # Ensure mapping exists
        await self.ensure_entity_mapping(entity_type)

        user_id_to_use = getattr(self, "authorized_user_id", None)
        if user_id_to_use and not self._db_driver.user_owns_entity(user_id_to_use, entity_type, str(entity_id)):
            raise ValueError(
                f"Unauthorized delete: user does not own {entity_type} entity {entity_id}"
            )
        
        await self._set_driver_owner_context(entity_type)
        try:
            # Delegate to driver with sync logging
            return await self._log_sync_operation_async(
                self.driver.delete_entity,
                entity_type,
                entity_id
            )
        finally:
            self._clear_driver_owner_context()

