from __future__ import annotations

from typing import Any, Dict, List, Optional
import requests
import logging
import re
from .base import BaseDriver
from .sql_driver_common import get_entity_mapping

logger = logging.getLogger("salesforce_driver")

_API_VERSION = "v60.0"
_SKIP_PAYLOAD_KEYS = {"related_entities", "metadata", "participants"}


class SalesforceDriver(BaseDriver):
    """Salesforce API connector.
    
    Security: All API calls use HTTPS with SSL/TLS encryption.
    SSL certificate verification is enabled by default via requests library.
    """

    def __init__(self, connector_config: Optional[Dict[str, Any]] = None):
        super().__init__(connector_config)
        self.instance_url = self.config.get("instance_url")
        self.client_id = self.config.get("client_id")
        self.client_secret = self.config.get("client_secret")
        self.username = self.config.get("username")
        self.password = self.config.get("password")
        
        # SSL verification enabled by default, can be disabled for testing (not recommended)
        self.verify_ssl = self.config.get("verify_ssl", True)
        try:
            self.request_timeout_seconds = max(1.0, float(self.config.get("request_timeout_seconds", 20)))
        except (TypeError, ValueError):
            self.request_timeout_seconds = 20.0

        if not all([self.instance_url, self.client_id, self.client_secret, self.username, self.password]):
            raise ValueError(
                "Salesforce credentials (instance_url, client_id, client_secret, username, password) are required"
            )

        self.access_token: Optional[str] = None
        self._refresh_token()

    def _refresh_token(self) -> None:
        token_url = f"{self.instance_url}/services/oauth2/token"

        payload = {
            "grant_type": "password",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "username": self.username,
            "password": self.password,
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
                raise ValueError("Salesforce OAuth token response did not include access_token")
            logger.info("Salesforce access token refreshed")
        except requests.exceptions.RequestException as e:
            raise Exception(f"Failed to obtain Salesforce access token: {str(e)}")

    def _get_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    def _request(self, method: str, path: str, retry_on_401: bool = True, **kwargs: Any) -> requests.Response:
        url = path if path.startswith("http") else f"{self.instance_url}{path}"
        kwargs.setdefault("headers", self._get_headers())
        kwargs.setdefault("verify", self.verify_ssl)
        kwargs.setdefault("timeout", self.request_timeout_seconds)

        response = requests.request(method.upper(), url, **kwargs)
        if response.status_code == 401 and retry_on_401:
            logger.warning("Salesforce request unauthorized, refreshing token and retrying once")
            self._refresh_token()
            kwargs["headers"] = self._get_headers()
            response = requests.request(method.upper(), url, **kwargs)

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

    def _collect_mapped_fields(
        self,
        payload: Dict[str, Any],
        column_mapping: Dict[str, Any],
        table_columns: set,
    ) -> Dict[str, Any]:
        sf_data: Dict[str, Any] = {}

        for norm_field, sf_field in column_mapping.items():
            if norm_field in payload and payload[norm_field] is not None and isinstance(sf_field, str):
                sf_data[sf_field] = payload[norm_field]

        for payload_key, payload_value in payload.items():
            if payload_value is None:
                continue
            if payload_key in _SKIP_PAYLOAD_KEYS:
                continue
            if payload_key in table_columns:
                sf_data[payload_key] = payload_value

        return sf_data

    @staticmethod
    def _is_safe_identifier(value: str) -> bool:
        return bool(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value or ""))

    @staticmethod
    def _escape_soql_string(value: str) -> str:
        return value.replace("\\", "\\\\").replace("'", "\\'")

    def save_meeting(self, user_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Save meeting to Salesforce as Task record.
        
        Args:
            user_id: User identifier (not used by Salesforce, kept for interface consistency)
            payload: Meeting data
        """
        task_data = {
            "Subject": payload.get("title", "Meeting"),
            "Description": payload.get("summary", ""),
            "Status": "Completed",
            "Priority": "Normal",
        }

        try:
            logger.info("[Salesforce] save_meeting user=%s", user_id)
            response = self._request(
                "POST",
                f"/services/data/{_API_VERSION}/sobjects/Task",
                json=task_data,
            )
            result = response.json()

            return {
                "id": result.get("id"),
                "title": payload.get("title"),
                "summary": payload.get("summary"),
                "participants": payload.get("participants"),
                "metadata": payload.get("metadata", {"salesforce_id": result.get("id")}),
                "source": "salesforce",
            }
        except requests.exceptions.RequestException as e:
            detail = self._compact_http_error(e)
            raise Exception(f"Failed to save meeting to Salesforce: {detail}")

    def get_meeting_history(self, user_id: str, filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        try:
            limit = self._normalize_limit((filters or {}).get("limit", 20))
            query = f"SELECT Id, Subject, Description, Status, CreatedDate FROM Task ORDER BY CreatedDate DESC LIMIT {limit}"

            response = self._request(
                "GET",
                f"/services/data/{_API_VERSION}/query",
                params={"q": query},
            )
            records = response.json().get("records", [])
            owned_entity_ids = filters.get("owned_entity_ids", []) if filters else []
            if owned_entity_ids:
                allowed_ids = {str(entity_id) for entity_id in owned_entity_ids}
                records = [r for r in records if str(r.get("Id")) in allowed_ids]

            return [
                {
                    "id": record.get("Id"),
                    "title": record.get("Subject"),
                    "summary": record.get("Description", ""),
                    "participants": [],
                    "metadata": {"salesforce_id": record.get("Id")},
                    "created_at": record.get("CreatedDate"),
                    "source": "salesforce",
                }
                for record in records
            ]
        except requests.exceptions.RequestException as e:
            detail = self._compact_http_error(e)
            raise Exception(f"Failed to retrieve meeting history from Salesforce: {detail}")

    async def get_schema_info(self) -> Dict[str, Any]:
        try:
            response = self._request("GET", f"/services/data/{_API_VERSION}/sobjects")
            sobjects = response.json().get("sobjects", [])
            max_objects = self._normalize_limit(self.config.get("schema_max_objects", 200), default=200)
            if max_objects > 0:
                sobjects = sobjects[:max_objects]
            
            tables = []
            for sobject in sobjects:
                obj_name = sobject.get("name")
                if not isinstance(obj_name, str) or not self._is_safe_identifier(obj_name):
                    continue
                try:
                    describe_resp = self._request("GET", f"/services/data/{_API_VERSION}/sobjects/{obj_name}/describe")
                    obj_data = describe_resp.json()
                    fields = obj_data.get("fields", [])
                    tables.append({
                        "name": obj_name,
                        "columns": [f.get("name") for f in fields],
                        "column_types": {f.get("name"): f.get("type") for f in fields}
                    })
                except Exception as exc:
                    logger.warning("[Salesforce] schema describe skipped object=%s error=%s", obj_name, exc)
            
            logger.info(f"Introspected {len(tables)} Salesforce objects")
            return {"tables": tables}
        except Exception as e:
            logger.error(f"Failed to introspect Salesforce schema: {e}")
            raise

    async def create_entity(self, entity_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            mapping = get_entity_mapping(self.config, entity_type)

            sobject_name = mapping.get("table_name")
            if not isinstance(sobject_name, str) or not self._is_safe_identifier(sobject_name):
                raise ValueError(f"Unsafe Salesforce object name: {sobject_name}")
            column_mapping = mapping.get("column_mapping", {})
            table_columns = set(mapping.get("table_columns") or [])

            sf_data = self._collect_mapped_fields(payload, column_mapping, table_columns)
            if not sf_data:
                raise ValueError(f"No writable Salesforce fields found in payload for '{entity_type}'")

            logger.info("[Salesforce] create_entity type=%s object=%s keys=%s", entity_type, sobject_name, sorted(sf_data.keys()))
            response = self._request(
                "POST",
                f"/services/data/{_API_VERSION}/sobjects/{sobject_name}",
                json=sf_data,
            )
            result = response.json()
            
            return {
                "id": result.get("id"),
                **payload,
                "source": "salesforce"
            }
        except Exception as e:
            logger.error(f"Failed to create {entity_type}: {e}")
            raise

    async def read_entities(self, entity_type: str, user_id: Optional[str] = None, filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        try:
            mapping = get_entity_mapping(self.config, entity_type)

            sobject_name = mapping.get("table_name")
            if not isinstance(sobject_name, str) or not self._is_safe_identifier(sobject_name):
                raise ValueError(f"Unsafe Salesforce object name: {sobject_name}")
            column_mapping = mapping.get("column_mapping", {})
            created_col = column_mapping.get("created_at")

            safe_fields = [
                field for field in column_mapping.values() if isinstance(field, str) and self._is_safe_identifier(field)
            ]
            fields = ", ".join(["Id"] + safe_fields) if safe_fields else "Id"
            limit = self._normalize_limit((filters or {}).get("limit", 20))
            
            # Data isolation: filter by owned entity IDs at query level (SOQL WHERE clause)
            owned_entity_ids = filters.get("owned_entity_ids", []) if filters else []
            where_clause = ""
            if owned_entity_ids:
                id_list = ", ".join([f"'{self._escape_soql_string(str(entity_id))}'" for entity_id in owned_entity_ids])
                where_clause = f" WHERE Id IN ({id_list})"

            order_clause = ""
            if isinstance(created_col, str) and self._is_safe_identifier(created_col):
                order_clause = f" ORDER BY {created_col} DESC"

            query = f"SELECT {fields} FROM {sobject_name}{where_clause}{order_clause} LIMIT {limit}"

            logger.info("[Salesforce] read_entities type=%s object=%s limit=%s", entity_type, sobject_name, limit)
            response = self._request(
                "GET",
                f"/services/data/{_API_VERSION}/query",
                params={"q": query},
            )
            records = response.json().get("records", [])
            
            return [
                {
                    "id": r.get("Id"),
                    **{norm_field: r.get(sf_field) for norm_field, sf_field in column_mapping.items()},
                    "source": "salesforce"
                }
                for r in records
            ]
        except Exception as e:
            logger.error(f"Failed to read {entity_type}: {e}")
            raise

    async def update_entity(self, entity_type: str, entity_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        try:
            mapping = get_entity_mapping(self.config, entity_type)

            sobject_name = mapping.get("table_name")
            if not isinstance(sobject_name, str) or not self._is_safe_identifier(sobject_name):
                raise ValueError(f"Unsafe Salesforce object name: {sobject_name}")
            column_mapping = mapping.get("column_mapping", {})
            table_columns = set(mapping.get("table_columns") or [])

            sf_data = self._collect_mapped_fields(updates, column_mapping, table_columns)
            if not sf_data:
                raise ValueError(f"No writable Salesforce fields found in update payload for '{entity_type}'")

            logger.info("[Salesforce] update_entity type=%s object=%s id=%s keys=%s", entity_type, sobject_name, entity_id, sorted(sf_data.keys()))
            self._request(
                "PATCH",
                f"/services/data/{_API_VERSION}/sobjects/{sobject_name}/{entity_id}",
                json=sf_data,
            )

            return {
                "id": entity_id,
                **updates,
                "source": "salesforce"
            }
        except Exception as e:
            logger.error(f"Failed to update {entity_type}: {e}")
            raise

    async def delete_entity(self, entity_type: str, entity_id: str) -> bool:
        try:
            mapping = get_entity_mapping(self.config, entity_type)

            sobject_name = mapping.get("table_name")
            if not isinstance(sobject_name, str) or not self._is_safe_identifier(sobject_name):
                raise ValueError(f"Unsafe Salesforce object name: {sobject_name}")

            logger.info("[Salesforce] delete_entity type=%s object=%s id=%s", entity_type, sobject_name, entity_id)
            response = self._request("DELETE", f"/services/data/{_API_VERSION}/sobjects/{sobject_name}/{entity_id}")
            return response.status_code == 204
        except Exception as e:
            logger.error(f"Failed to delete {entity_type}: {e}")
            raise