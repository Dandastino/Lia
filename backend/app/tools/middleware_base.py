from __future__ import annotations

import logging
import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from livekit.agents import llm
from sqlalchemy import inspect as sqlalchemy_inspect

from ..drivers.sql_driver_common import resolve_required_columns
from ..services.data_manager import DataManager

logger = logging.getLogger("middleware_tools")
TOOLSET_VERSION = "middleware-v2026-03-11-contact-hint-improvements"


class BaseMiddlewareTools:
    """Industry-agnostic tools that the agent can call. Supports both legacy meeting-specific tools and new generic CRUD operations"""

    def __init__(self, user_id: str):
        self.user_id = user_id
        logger.info("Initializing %s version=%s", self.__class__.__name__, TOOLSET_VERSION)

        # ===== Legacy meeting-specific tools =====
        self.save_meeting_tool = llm.function_tool(
            name="save_meeting_tool",
            description="Save a summary of the current meeting, including participants and key details.",
        )(self._save_meeting)

        self.get_history_tool = llm.function_tool(
            name="get_history_tool",
            description="Get previous meetings for this user, for additional context.",
        )(self._get_history)

        # ===== Generic CRUD tools (new) =====
        self.save_entity_tool = llm.function_tool(
            name="save_entity_tool",
            description="Create a new record in an existing entity type (e.g., meeting, patient, contact, mail). Writes real table columns for that entity type; if required fields are missing, ask the user for them and retry.",
        )(self._save_entity)

        self.get_entities_tool = llm.function_tool(
            name="get_entities_tool",
            description="Retrieve records from an entity type (e.g., get all meetings, patients, contacts). Specify which entity_type to query.",
        )(self._get_entities)

        self.get_entity_requirements_tool = llm.function_tool(
            name="get_entity_requirements_tool",
            description="Return schema requirements for an entity type: required columns, mapped columns, and target table. Use this before asking the user for missing fields.",
        )(self._get_entity_requirements)

        self.update_entity_tool = llm.function_tool(
            name="update_entity_tool",
            description="Update an existing record within an entity type. Requires entity_type and entity_id, and updates only the requested fields mapped to real table columns.",
        )(self._update_entity)

        self.delete_entity_tool = llm.function_tool(
            name="delete_entity_tool",
            description="Delete a specific record from an entity type. Requires entity_type and entity_id of the record to delete.",
        )(self._delete_entity)

    def get_tools(self):
        """Return all available tools for the agent."""
        return [
            self.save_meeting_tool,
            self.get_history_tool,
            self.save_entity_tool,
            self.get_entities_tool,
            self.get_entity_requirements_tool,
            self.update_entity_tool,
            self.delete_entity_tool,
        ]

    def _has_user_context(self) -> bool:
        return bool(self.user_id)

    def _format_data_access_error(self, entity_type: str, error: Exception) -> str:
        """Return a concise, user-facing error for common connector failures."""
        error_text = str(error)
        lower_text = error_text.lower()

        if "connection refused" in lower_text or "operationalerror" in lower_text:
            return (
                f"External database unavailable for '{entity_type}'. "
                "Check connector host/port, firewall, pg_hba.conf, and that PostgreSQL is running."
            )

        return f"Failed to access '{entity_type}' records: {error_text}"

    def _merge_related_entities_into_payload(
        self,
        payload: Dict[str, Any],
        related_entities: Optional[Dict[str, Any]],
    ) -> None:
        """Connector-family hook to enrich payload with relationship hints."""
        if isinstance(related_entities, dict):
            payload["related_entities"] = related_entities

    def _merge_metadata_into_payload(
        self,
        payload: Dict[str, Any],
        metadata: Optional[Dict[str, Any]],
    ) -> None:
        """Connector-family hook to control metadata handling in CRUD payloads."""
        if metadata is None:
            return
        if isinstance(metadata, dict):
            payload.update(metadata)
            return
        payload["metadata"] = metadata

    def _use_live_required_column_resolution(self, dm: DataManager) -> bool:
        """Connector-family hook deciding whether requirements should use SQL introspection."""
        return False

    def _finalize_update_payload(self, dm: DataManager, update_payload: Dict[str, Any]) -> None:
        """Connector-family hook for last-mile update payload normalization."""
        return

    @staticmethod
    def _extract_missing_required_columns(error_text: str) -> List[str]:
        """Parse missing required columns from driver ValueError text."""
        match = re.search(r"missing required columns\s*\[([^\]]*)\]", error_text, flags=re.IGNORECASE)
        if not match:
            return []

        raw_items = [item.strip().strip("'\"") for item in match.group(1).split(",")]
        return [item for item in raw_items if item]

    @staticmethod
    def _json_safe(value: Any) -> Any:
        """Convert tool outputs into JSON-serializable values for LiveKit."""
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, Decimal):
            return float(value)
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        if isinstance(value, dict):
            return {str(k): BaseMiddlewareTools._json_safe(v) for k, v in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [BaseMiddlewareTools._json_safe(v) for v in value]
        return str(value)

    @staticmethod
    def _extract_contact_hints_from_participants(participants: Any) -> Dict[str, str]:
        """Build language-agnostic contact hints from participants payload."""
        if not isinstance(participants, list):
            return {}

        candidates: List[Dict[str, str]] = []

        for item in participants:
            email = ""
            name = ""

            if isinstance(item, dict):
                for key in ("email", "mail", "contact_email"):
                    raw = item.get(key)
                    if isinstance(raw, str) and raw.strip():
                        email = raw.strip()
                        break

                direct_name = item.get("name") or item.get("full_name") or item.get("display_name")
                if isinstance(direct_name, str) and direct_name.strip():
                    name = direct_name.strip()
                else:
                    first = str(item.get("first_name") or "").strip()
                    last = str(item.get("last_name") or "").strip()
                    name = " ".join(part for part in [first, last] if part).strip()

            elif isinstance(item, str):
                raw = item.strip()
                if not raw:
                    continue
                if re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", raw):
                    email = raw
                else:
                    name = raw

            if email or name:
                candidates.append({"contact_email": email, "contact_name": name})

        if not candidates:
            return {}

        # Prefer a coherent candidate from one participant (email+name together),
        # then email-only, then name-only. This avoids cross-participant mixing.
        best = next((c for c in candidates if c.get("contact_email") and c.get("contact_name")), None)
        if best is None:
            best = next((c for c in candidates if c.get("contact_email")), None)
        if best is None:
            best = next((c for c in candidates if c.get("contact_name")), None)
        if best is None:
            return {}

        hints: Dict[str, str] = {}
        if best.get("contact_email"):
            hints["contact_email"] = str(best["contact_email"])
        if best.get("contact_name"):
            hints["contact_name"] = str(best["contact_name"])
        return hints

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
        md = metadata if isinstance(metadata, dict) else {}
        payload: Dict[str, Any] = {
            "title": title,
            "summary": summary,
            "participants": participants or [],
            "metadata": md,
        }

        # Backward-compatible association hints for legacy meeting tool.
        # Example payloads often send IDs inside metadata (e.g. related_client_id).
        if isinstance(md, dict):
            nested_related = md.get("related_entities")
            if isinstance(nested_related, dict) and not isinstance(payload.get("related_entities"), dict):
                payload["related_entities"] = nested_related

            for key in ("contact_id", "related_contact_id", "related_client_id", "client_id"):
                if md.get(key) and not payload.get("contact_id"):
                    payload["contact_id"] = md.get(key)
                    break
            for key in ("company_id", "related_company_id", "account_id"):
                if md.get(key) and not payload.get("company_id"):
                    payload["company_id"] = md.get(key)
                    break
            if md.get("contact_email") and not payload.get("contact_email"):
                payload["contact_email"] = md.get("contact_email")
            if md.get("contact_name") and not payload.get("contact_name"):
                payload["contact_name"] = md.get("contact_name")
            if md.get("company_name") and not payload.get("company_name"):
                payload["company_name"] = md.get("company_name")

        # Use participants as secondary hint when metadata has no direct contact info.
        if not payload.get("contact_email") and not payload.get("contact_name"):
            payload.update(self._extract_contact_hints_from_participants(payload.get("participants")))

        return self._json_safe(dm.save_meeting(user_id=self.user_id, payload=payload))

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
        return self._json_safe(dm.get_meeting_history(user_id=self.user_id, filters=filters))

    # ===== Generic CRUD tools (new) =====

    async def _save_entity(
        self,
        entity_type: str,
        title: Optional[str] = None,
        summary: Optional[str] = None,
        participants: Optional[List[Dict[str, Any]]] = None,
        fields: Optional[Dict[str, Any]] = None,
        related_entities: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create a new record in an existing entity type."""
        if not self._has_user_context():
            return {"error": "Missing user context; cannot create record."}

        try:
            dm = DataManager.from_user_id(self.user_id)
            payload: Dict[str, Any] = {}
            if isinstance(fields, dict):
                # Highest priority: explicit external fields requested by the user.
                payload.update(fields)
            self._merge_related_entities_into_payload(payload, related_entities)
            if title is not None:
                payload["title"] = title
            if summary is not None:
                payload["summary"] = summary
            if participants is not None:
                payload["participants"] = participants
                if not payload.get("contact_email") and not payload.get("contact_name"):
                    payload.update(self._extract_contact_hints_from_participants(participants))
            self._merge_metadata_into_payload(payload, metadata)

            if not payload:
                requirements = await self._get_entity_requirements(entity_type)
                required_fields = requirements.get("required_fields", [])
                if required_fields:
                    return {
                        "error": f"Cannot create record: missing required columns {required_fields}",
                        "missing_required_fields": required_fields,
                        "action": "ask_user_for_missing_fields",
                        "table_name": requirements.get("table_name"),
                    }
                return {
                    "error": "No fields provided to create record.",
                    "action": "ask_user_for_fields",
                    "table_name": requirements.get("table_name"),
                    "available_fields": requirements.get("available_fields", []),
                }

            logger.debug(
                "save_entity payload prepared entity_type=%s payload_keys=%s related_keys=%s",
                entity_type,
                sorted(list(payload.keys())),
                sorted(list((payload.get("related_entities") or {}).keys())) if isinstance(payload.get("related_entities"), dict) else [],
            )

            result = await dm.create_entity(entity_type, payload)
            logger.info(f"Created record in {entity_type}: {result.get('id')}")
            return self._json_safe(result)
        except ValueError as e:
            # Handle authorization issues, missing tables, etc.
            logger.warning(f"Cannot create record in {entity_type}: {e}")
            error_text = str(e)
            missing_columns = self._extract_missing_required_columns(error_text)
            if missing_columns:
                return {
                    "error": f"Cannot create record: {error_text}",
                    "missing_required_fields": missing_columns,
                    "action": "ask_user_for_missing_fields",
                }
            return {"error": f"Cannot create record: {error_text}"}
        except Exception as e:
            msg = self._format_data_access_error(entity_type, e)
            logger.error(msg)
            return {"error": msg}

    async def _get_entity_requirements(self, entity_type: str) -> Dict[str, Any]:
        """Read required/available fields for an entity directly from mapped schema metadata."""
        if not self._has_user_context():
            return {"error": "Missing user context; cannot inspect entity requirements."}

        try:
            dm = DataManager.from_user_id(self.user_id)
            await dm.ensure_entity_mapping(entity_type)

            config = dm.driver.config or {}
            mapping = (config.get("schema_mappings") or {}).get(entity_type) or {}

            required_fields = mapping.get("required_columns") or []
            available_fields = mapping.get("table_columns") or []
            table_name = mapping.get("table_name")

            # For SQL connectors, derive required fields from live schema to avoid
            # stale cached metadata causing false "required" prompts.
            if table_name and self._use_live_required_column_resolution(dm):
                try:
                    inspector = sqlalchemy_inspect(dm.driver.engine)
                    required_fields = resolve_required_columns(
                        inspector=inspector,
                        mapping=mapping,
                        table_name=str(table_name),
                        id_column=str(mapping.get("id_column") or "id"),
                    )
                except Exception:  # noqa: S110 - best-effort, failure is expected and handled by the caller
                    # Fallback to mapping metadata when live inspection is unavailable.
                    pass

            if not isinstance(required_fields, list):
                required_fields = []
            if not isinstance(available_fields, list):
                available_fields = []

            # Build field constraints including enum values for better LLM guidance
            field_constraints = {}
            enum_values = mapping.get("enum_values") or {}
            if isinstance(enum_values, dict):
                for field_name, enum_list in enum_values.items():
                    if isinstance(enum_list, list) and enum_list:
                        field_constraints[field_name] = {
                            "type": "enum",
                            "values": enum_list,
                        }

            response = {
                "entity_type": entity_type,
                "table_name": table_name,
                "required_fields": required_fields,
                "available_fields": available_fields,
            }
            if field_constraints:
                response["field_constraints"] = field_constraints
            return response
        except Exception as e:
            logger.error(f"Failed to inspect requirements for {entity_type}: {e}")
            return {"error": f"Failed to inspect requirements: {str(e)}"}

    async def _get_entities(
        self,
        entity_type: str,
        limit: int = 20,
        user_only: bool = True,
    ) -> Dict[str, Any]:
        """Retrieve records from a specific entity type validation issues."""
        if not self._has_user_context():
            logger.warning(f"Missing user context; returning empty records for {entity_type}")
            return {
                "entity_type": entity_type,
                "records": [],
                "count": 0,
            }

        try:
            dm = DataManager.from_user_id(self.user_id)

            query_filters: Dict[str, Any] = {
                "limit": max(1, min(limit, 50)),
            }

            user_id = self.user_id if user_only else None
            records = await dm.read_entities(entity_type, user_id, query_filters)
            logger.info(f"Retrieved {len(records)} records from {entity_type}")
            return {
                "entity_type": entity_type,
                "records": self._json_safe(records),
                "count": len(records),
            }
        except ValueError as e:
            # Handle missing tables, authorization issues, etc.
            logger.warning(f"Cannot retrieve {entity_type} records: {e}")
            # Return empty list instead of crashing - graceful degradation for multitenant safety
            return {
                "entity_type": entity_type,
                "records": [],
                "count": 0,
                "error": str(e),
            }
        except Exception as e:
            logger.error(self._format_data_access_error(entity_type, e))
            # Return empty list instead of crashing - graceful degradation for multitenant safety
            return {
                "entity_type": entity_type,
                "records": [],
                "count": 0,
                "error": self._format_data_access_error(entity_type, e),
            }

    async def _update_entity(
        self,
        entity_type: str,
        entity_id: str,
        title: Optional[str] = None,
        summary: Optional[str] = None,
        fields: Optional[Dict[str, Any]] = None,
        related_entities: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Update an existing record in an entity."""
        if not self._has_user_context():
            return {"error": "Missing user context; cannot update record."}

        try:
            dm = DataManager.from_user_id(self.user_id)

            update_payload: Dict[str, Any] = {}
            if isinstance(fields, dict):
                # Highest priority: explicit external fields requested by the user.
                update_payload.update(fields)
            self._merge_related_entities_into_payload(update_payload, related_entities)
            if title is not None:
                update_payload["title"] = title
            if summary is not None:
                update_payload["summary"] = summary
            self._merge_metadata_into_payload(update_payload, metadata)

            if not update_payload:
                return {"error": "No fields provided to update record."}

            self._finalize_update_payload(dm, update_payload)

            result = await dm.update_entity(entity_type, entity_id, update_payload)
            logger.info(f"Updated record {entity_id} in {entity_type}")
            return self._json_safe(result)
        except ValueError as e:
            # Handle authorization issues, missing tables, etc.
            logger.warning(f"Cannot update record in {entity_type}: {e}")
            return {"error": f"Cannot update record: {str(e)}"}
        except Exception as e:
            msg = self._format_data_access_error(entity_type, e)
            logger.error(msg)
            return {"error": msg}

    async def _delete_entity(
        self,
        entity_type: str,
        entity_id: str,
    ) -> Dict[str, Any]:
        """Delete a specific record from an entity."""
        if not self._has_user_context():
            return {"deleted": False, "error": "Missing user context; cannot delete record."}

        try:
            dm = DataManager.from_user_id(self.user_id)
            deleted = await dm.delete_entity(entity_type, entity_id)
            logger.info(f"Deleted record {entity_id} from {entity_type}: {deleted}")
            return {"deleted": deleted}
        except ValueError as e:
            # Handle authorization issues, missing tables, etc.
            logger.warning(f"Cannot delete record in {entity_type}: {e}")
            return {"deleted": False, "error": f"Cannot delete record: {str(e)}"}
        except Exception as e:
            msg = self._format_data_access_error(entity_type, e)
            logger.error(msg)
            return {"deleted": False, "error": msg}
