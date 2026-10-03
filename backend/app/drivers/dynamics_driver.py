from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import requests

from ..security import validate_dynamics_config
from .base import BaseDriver
from .sql_driver_common import get_entity_mapping

logger = logging.getLogger("dynamics_driver")

_API_BASE = "/api/data/v9.2"
_SKIP_PAYLOAD_KEYS = {"related_entities", "metadata", "participants"}


class DynamicsDriver(BaseDriver):
    """Microsoft Dynamics 365 API connector.

    Security: All API calls use HTTPS with SSL/TLS encryption.
    SSL certificate verification is enabled by default via requests library.
    """

    def __init__(self, connector_config: Optional[Dict[str, Any]] = None):
        super().__init__(connector_config)
        self.tenant_id = self.config.get("tenant_id")
        self.client_id = self.config.get("client_id")
        self.client_secret = self.config.get("client_secret")
        self.dynamics_url = self.config.get("dynamics_url")

        # SSL verification enabled by default, can be disabled for testing (not recommended)
        self.verify_ssl = self.config.get("verify_ssl", True)
        try:
            self.request_timeout_seconds = max(1.0, float(self.config.get("request_timeout_seconds", 20)))
        except (TypeError, ValueError):
            self.request_timeout_seconds = 20.0

        if not all([self.tenant_id, self.client_id, self.client_secret, self.dynamics_url]):
            raise ValueError(
                "Dynamics credentials (tenant_id, client_id, client_secret, dynamics_url) are required"
            )

        config_error = validate_dynamics_config(self.tenant_id, self.dynamics_url)
        if config_error:
            raise ValueError(config_error)

        self.access_token: Optional[str] = None
        self._refresh_token()

    def _refresh_token(self) -> None:
        token_url = f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"

        payload = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "scope": f"{self.dynamics_url}/.default",
            "grant_type": "client_credentials",
        }

        try:
            response = requests.post(
                token_url,
                data=payload,
                verify=self.verify_ssl,
                timeout=self.request_timeout_seconds,
            )
            response.raise_for_status()
            self.access_token = response.json().get("access_token")
            if not self.access_token:
                raise ValueError("Dynamics OAuth token response did not include access_token")
            logger.info("Dynamics access token refreshed")
        except requests.exceptions.RequestException as e:
            raise Exception(f"Failed to obtain Dynamics access token: {str(e)}") from e

    def _get_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "OData-MaxVersion": "4.0",
            "OData-Version": "4.0",
        }

    def _request(self, method: str, path: str, retry_on_401: bool = True, **kwargs: Any) -> requests.Response:
        url = path if path.startswith("http") else f"{self.dynamics_url}{path}"
        kwargs.setdefault("headers", self._get_headers())
        kwargs.setdefault("verify", self.verify_ssl)
        kwargs.setdefault("timeout", self.request_timeout_seconds)

        response = requests.request(method.upper(), url, **kwargs)  # noqa: S113 - timeout is set through kwargs.setdefault above
        if response.status_code == 401 and retry_on_401:
            logger.warning("Dynamics request unauthorized, refreshing token and retrying once")
            self._refresh_token()
            kwargs["headers"] = self._get_headers()
            response = requests.request(method.upper(), url, **kwargs)  # noqa: S113 - timeout is set through kwargs.setdefault above

        response.raise_for_status()
        return response

    @staticmethod
    def _normalize_limit(value: Any, default: int = 20) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return default
        return max(1, min(parsed, 200))

    @staticmethod
    def _compact_http_error(error: Exception) -> str:
        response = getattr(error, "response", None)
        if response is not None:
            text = (response.text or "").strip().replace("\n", " ")
            return f"HTTP {response.status_code}: {text[:400]}"
        return str(error)

    @staticmethod
    def _extract_entity_id(response: requests.Response) -> str:
        entity_header = str(response.headers.get("OData-EntityId", "") or "").strip()
        if not entity_header:
            return ""
        if "(" in entity_header and entity_header.endswith(")"):
            return entity_header.split("(")[-1].rstrip(")")
        return entity_header

    def _collect_mapped_fields(
        self,
        payload: Dict[str, Any],
        column_mapping: Dict[str, Any],
        table_columns: set,
    ) -> Dict[str, Any]:
        dyn_data: Dict[str, Any] = {}

        for norm_field, dyn_field in column_mapping.items():
            if norm_field in payload and payload[norm_field] is not None and isinstance(dyn_field, str):
                dyn_data[dyn_field] = payload[norm_field]

        for payload_key, payload_value in payload.items():
            if payload_value is None:
                continue
            if payload_key in _SKIP_PAYLOAD_KEYS:
                continue
            if payload_key in table_columns:
                dyn_data[payload_key] = payload_value

        return dyn_data

    @staticmethod
    def _is_safe_identifier(value: str) -> bool:
        return bool(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value or ""))

    @staticmethod
    def _escape_odata_string(value: str) -> str:
        return value.replace("'", "''")

    def save_meeting(self, user_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Save meeting to Dynamics 365 as phone call activity.

        Args:
            user_id: User identifier (not used by Dynamics, kept for interface consistency)
            payload: Meeting data
        """
        activity_data = {
            "subject": payload.get("title", "Meeting"),
            "description": payload.get("summary", ""),
        }

        try:
            logger.info("[Dynamics] save_meeting user=%s", user_id)
            response = self._request(
                "POST",
                f"{_API_BASE}/phonecalls",
                json=activity_data,
            )
            entity_id = self._extract_entity_id(response)

            return {
                "id": entity_id,
                "title": payload.get("title"),
                "summary": payload.get("summary"),
                "participants": payload.get("participants"),
                "metadata": payload.get("metadata", {"dynamics_id": entity_id}),
                "source": "dynamics",
            }
        except requests.exceptions.RequestException as e:
            detail = self._compact_http_error(e)
            raise Exception(f"Failed to save meeting to Dynamics: {detail}") from e

    def get_meeting_history(self, user_id: str, filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        try:
            limit = self._normalize_limit((filters or {}).get("limit", 20))
            query = f"{_API_BASE}/phonecalls?$select=phonecallid,subject,description,createdon&$top={limit}&$orderby=createdon desc"

            response = self._request("GET", query)
            records = response.json().get("value", [])
            owned_entity_ids = filters.get("owned_entity_ids", []) if filters else []
            if owned_entity_ids:
                allowed_ids = {str(entity_id) for entity_id in owned_entity_ids}
                records = [r for r in records if str(r.get("phonecallid")) in allowed_ids]

            return [
                {
                    "id": record.get("phonecallid"),
                    "title": record.get("subject"),
                    "summary": record.get("description", ""),
                    "participants": [],
                    "metadata": {"dynamics_id": record.get("phonecallid")},
                    "created_at": record.get("createdon"),
                    "source": "dynamics",
                }
                for record in records
            ]
        except requests.exceptions.RequestException as e:
            detail = self._compact_http_error(e)
            raise Exception(f"Failed to retrieve meeting history from Dynamics: {detail}") from e

    async def get_schema_info(self) -> Dict[str, Any]:
        try:
            self._request("GET", f"{_API_BASE}/$metadata")

            max_objects = self._normalize_limit(self.config.get("schema_max_objects", 200), default=200)
            entities: List[Dict[str, Any]] = []
            next_url = f"{_API_BASE}/EntityDefinitions?$select=LogicalName"
            while next_url and (max_objects <= 0 or len(entities) < max_objects):
                entities_resp = self._request("GET", next_url)
                payload = entities_resp.json() if isinstance(entities_resp.json(), dict) else {}
                batch = payload.get("value", []) if isinstance(payload.get("value", []), list) else []
                entities.extend(batch)
                next_url = payload.get("@odata.nextLink")

            if max_objects > 0:
                entities = entities[:max_objects]

            tables = []
            for entity in entities:
                entity_name = entity.get("LogicalName")
                if not isinstance(entity_name, str) or not self._is_safe_identifier(entity_name):
                    continue
                try:
                    attr_resp = self._request(
                        "GET",
                        f"{_API_BASE}/EntityDefinitions(LogicalName='{entity_name}')/Attributes?$select=LogicalName,AttributeType",
                    )
                    attrs = attr_resp.json().get("value", [])
                    tables.append({
                        "name": entity_name,
                        "columns": [a.get("LogicalName") for a in attrs],
                        "column_types": {a.get("LogicalName"): a.get("AttributeType") for a in attrs}
                    })
                except Exception as exc:
                    logger.warning("[Dynamics] schema attributes skipped entity=%s error=%s", entity_name, exc)

            logger.info(f"Introspected {len(tables)} Dynamics entities")
            return {"tables": tables}
        except Exception as e:
            logger.error(f"Failed to introspect Dynamics schema: {e}")
            raise

    async def create_entity(self, entity_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            mapping = get_entity_mapping(self.config, entity_type)

            entity_name = mapping.get("table_name")
            if not isinstance(entity_name, str) or not self._is_safe_identifier(entity_name):
                raise ValueError(f"Unsafe Dynamics entity name: {entity_name}")
            column_mapping = mapping.get("column_mapping", {})
            table_columns = set(mapping.get("table_columns") or [])

            dyn_data = self._collect_mapped_fields(payload, column_mapping, table_columns)
            if not dyn_data:
                raise ValueError(f"No writable Dynamics fields found in payload for '{entity_type}'")

            logger.info("[Dynamics] create_entity type=%s object=%s keys=%s", entity_type, entity_name, sorted(dyn_data.keys()))
            response = self._request(
                "POST",
                f"{_API_BASE}/{entity_name}",
                json=dyn_data,
            )
            entity_id = self._extract_entity_id(response)

            return {
                "id": entity_id,
                **payload,
                "source": "dynamics"
            }
        except Exception as e:
            logger.error(f"Failed to create {entity_type}: {e}")
            raise

    async def read_entities(self, entity_type: str, user_id: Optional[str] = None, filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        try:
            mapping = get_entity_mapping(self.config, entity_type)

            entity_name = mapping.get("table_name")
            if not isinstance(entity_name, str) or not self._is_safe_identifier(entity_name):
                raise ValueError(f"Unsafe Dynamics entity name: {entity_name}")
            column_mapping = mapping.get("column_mapping", {})
            created_col = column_mapping.get("created_at")

            safe_fields = [
                field for field in column_mapping.values() if isinstance(field, str) and self._is_safe_identifier(field)
            ]
            limit = self._normalize_limit((filters or {}).get("limit", 20))
            id_field = mapping.get("id_column", f"{entity_name}id")
            if not isinstance(id_field, str) or not self._is_safe_identifier(id_field):
                raise ValueError(f"Unsafe Dynamics id column: {id_field}")

            # Data isolation: filter by owned entity IDs at query level (OData $filter parameter)
            owned_entity_ids = filters.get("owned_entity_ids", []) if filters else []
            filter_clause = ""
            if owned_entity_ids:
                id_filters = " or ".join(
                    [
                        # percent-encode so '&', '#' or '+' inside an id cannot forge extra query options
                        f"{id_field} eq '{quote(self._escape_odata_string(str(entity_id)), safe=chr(39))}'"
                        for entity_id in owned_entity_ids
                    ]
                )
                filter_clause = f"&$filter={id_filters}"

            select_fields = [id_field] + safe_fields
            order_clause = ""
            if isinstance(created_col, str) and self._is_safe_identifier(created_col):
                order_clause = f"&$orderby={created_col} desc"
            query = (
                f"{_API_BASE}/{entity_name}?$select={','.join(select_fields)}"
                f"&$top={limit}{order_clause}{filter_clause}"
            )

            logger.info("[Dynamics] read_entities type=%s object=%s limit=%s", entity_type, entity_name, limit)
            response = self._request("GET", query)
            records = response.json().get("value", [])

            return [
                {
                    "id": r.get(id_field),
                    **{norm_field: r.get(dyn_field) for norm_field, dyn_field in column_mapping.items()},
                    "source": "dynamics"
                }
                for r in records
            ]
        except Exception as e:
            logger.error(f"Failed to read {entity_type}: {e}")
            raise

    async def update_entity(self, entity_type: str, entity_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        try:
            mapping = get_entity_mapping(self.config, entity_type)

            entity_name = mapping.get("table_name")
            if not isinstance(entity_name, str) or not self._is_safe_identifier(entity_name):
                raise ValueError(f"Unsafe Dynamics entity name: {entity_name}")
            column_mapping = mapping.get("column_mapping", {})
            table_columns = set(mapping.get("table_columns") or [])

            dyn_data = self._collect_mapped_fields(updates, column_mapping, table_columns)
            if not dyn_data:
                raise ValueError(f"No writable Dynamics fields found in update payload for '{entity_type}'")

            logger.info("[Dynamics] update_entity type=%s object=%s id=%s keys=%s", entity_type, entity_name, entity_id, sorted(dyn_data.keys()))
            self._request(
                "PATCH",
                f"{_API_BASE}/{entity_name}({quote(str(entity_id), safe='')})",
                json=dyn_data,
            )

            return {
                "id": entity_id,
                **updates,
                "source": "dynamics"
            }
        except Exception as e:
            logger.error(f"Failed to update {entity_type}: {e}")
            raise

    async def delete_entity(self, entity_type: str, entity_id: str) -> bool:
        try:
            mapping = get_entity_mapping(self.config, entity_type)

            entity_name = mapping.get("table_name")
            if not isinstance(entity_name, str) or not self._is_safe_identifier(entity_name):
                raise ValueError(f"Unsafe Dynamics entity name: {entity_name}")

            logger.info("[Dynamics] delete_entity type=%s object=%s id=%s", entity_type, entity_name, entity_id)
            response = self._request("DELETE", f"{_API_BASE}/{entity_name}({quote(str(entity_id), safe='')})")
            return response.status_code == 204
        except Exception as e:
            logger.error(f"Failed to delete {entity_type}: {e}")
            raise
