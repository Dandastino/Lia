from __future__ import annotations

from typing import Any, Dict, List, Optional
import requests
import logging
from .base import BaseDriver

logger = logging.getLogger(__name__)


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

        if not all([self.instance_url, self.client_id, self.client_secret, self.username, self.password]):
            raise ValueError(
                "Salesforce credentials (instance_url, client_id, client_secret, username, password) are required"
            )

        self.access_token = None
        self._refresh_token()

    def _refresh_token(self):
        token_url = f"{self.instance_url}/services/oauth2/token"

        payload = {
            "grant_type": "password",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "username": self.username,
            "password": self.password,
        }

        try:
            response = requests.post(token_url, data=payload, verify=self.verify_ssl)
            response.raise_for_status()
            self.access_token = response.json().get("access_token")
        except requests.exceptions.RequestException as e:
            raise Exception(f"Failed to obtain Salesforce access token: {str(e)}")

    def _get_headers(self):
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    def save_meeting(self, user_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        headers = self._get_headers()
        task_data = {
            "Subject": payload.get("title", "Meeting"),
            "Description": payload.get("summary", ""),
            "Status": "Completed",
            "Priority": "Normal",
        }

        try:
            response = requests.post(
                f"{self.instance_url}/services/data/v60.0/sobjects/Task",
                headers=headers,
                json=task_data,
                verify=self.verify_ssl,
            )
            response.raise_for_status()
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
            raise Exception(f"Failed to save meeting to Salesforce: {str(e)}")

    def get_meeting_history(self, user_id: str, filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        headers = self._get_headers()

        try:
            limit = int(filters.get("limit", 20)) if filters else 20
            query = f"SELECT Id, Subject, Description, Status, CreatedDate FROM Task ORDER BY CreatedDate DESC LIMIT {limit}"

            response = requests.get(
                f"{self.instance_url}/services/data/v60.0/query",
                headers=headers,
                params={"q": query},
                verify=self.verify_ssl,
            )
            response.raise_for_status()
            records = response.json().get("records", [])

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
            raise Exception(f"Failed to retrieve meeting history from Salesforce: {str(e)}")

    async def get_schema_info(self) -> Dict[str, Any]:
        try:
            headers = self._get_headers()
            response = requests.get(
                f"{self.instance_url}/services/data/v60.0/sobjects",
                headers=headers,
                verify=self.verify_ssl,
            )
            response.raise_for_status()
            sobjects = response.json().get("sobjects", [])
            
            tables = []
            for sobject in sobjects[:50]:
                obj_name = sobject.get("name")
                describe_resp = requests.get(
                    f"{self.instance_url}/services/data/v60.0/sobjects/{obj_name}/describe",
                    headers=headers,
                    verify=self.verify_ssl,
                )
                if describe_resp.status_code == 200:
                    obj_data = describe_resp.json()
                    fields = obj_data.get("fields", [])
                    tables.append({
                        "name": obj_name,
                        "columns": [f.get("name") for f in fields],
                        "column_types": {f.get("name"): f.get("type") for f in fields}
                    })
            
            logger.info(f"Introspected {len(tables)} Salesforce objects")
            return {"tables": tables}
        except Exception as e:
            logger.error(f"Failed to introspect Salesforce schema: {e}")
            raise

    async def create_entity(self, entity_type: str, user_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            mapping = self.config.get("schema_mappings", {}).get(entity_type)
            if not mapping:
                raise ValueError(f"No schema mapping for entity type: {entity_type}")
            
            headers = self._get_headers()
            sobject_name = mapping.get("table_name")
            column_mapping = mapping.get("column_mapping", {})
            
            sf_data = {}
            for norm_field, sf_field in column_mapping.items():
                if norm_field in payload and payload[norm_field] is not None:
                    sf_data[sf_field] = payload[norm_field]
            
            response = requests.post(
                f"{self.instance_url}/services/data/v60.0/sobjects/{sobject_name}",
                headers=headers,
                json=sf_data,
                verify=self.verify_ssl,
            )
            response.raise_for_status()
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
            mapping = self.config.get("schema_mappings", {}).get(entity_type)
            if not mapping:
                raise ValueError(f"No schema mapping for entity type: {entity_type}")
            
            headers = self._get_headers()
            sobject_name = mapping.get("table_name")
            column_mapping = mapping.get("column_mapping", {})
            
            fields = ", ".join(column_mapping.values())
            limit = filters.get("limit", 20) if filters else 20
            query = f"SELECT {fields} FROM {sobject_name} ORDER BY CreatedDate DESC LIMIT {limit}"
            
            response = requests.get(
                f"{self.instance_url}/services/data/v60.0/query",
                headers=headers,
                params={"q": query},
                verify=self.verify_ssl,
            )
            response.raise_for_status()
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

    async def update_entity(self, entity_type: str, entity_id: str, updates: Dict[str, Any], user_id: str) -> Dict[str, Any]:
        try:
            mapping = self.config.get("schema_mappings", {}).get(entity_type)
            if not mapping:
                raise ValueError(f"No schema mapping for entity type: {entity_type}")
            
            headers = self._get_headers()
            sobject_name = mapping.get("table_name")
            column_mapping = mapping.get("column_mapping", {})
            
            sf_data = {}
            for norm_field, sf_field in column_mapping.items():
                if norm_field in updates and updates[norm_field] is not None:
                    sf_data[sf_field] = updates[norm_field]
            
            response = requests.patch(
                f"{self.instance_url}/services/data/v60.0/sobjects/{sobject_name}/{entity_id}",
                headers=headers,
                json=sf_data,
                verify=self.verify_ssl,
            )
            response.raise_for_status()
            
            return {
                "id": entity_id,
                **updates,
                "source": "salesforce"
            }
        except Exception as e:
            logger.error(f"Failed to update {entity_type}: {e}")
            raise

    async def delete_entity(self, entity_type: str, entity_id: str, user_id: str) -> bool:
        try:
            mapping = self.config.get("schema_mappings", {}).get(entity_type)
            if not mapping:
                raise ValueError(f"No schema mapping for entity type: {entity_type}")
            
            headers = self._get_headers()
            sobject_name = mapping.get("table_name")
            
            response = requests.delete(
                f"{self.instance_url}/services/data/v60.0/sobjects/{sobject_name}/{entity_id}",
                headers=headers,
                verify=self.verify_ssl,
            )
            return response.status_code == 204
        except Exception as e:
            logger.error(f"Failed to delete {entity_type}: {e}")
            raise