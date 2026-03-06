from __future__ import annotations

from typing import Any, Dict, List, Optional
import logging
import requests

from .base import BaseDriver
from ..schema.query_builder import DynamicQueryBuilder

logger = logging.getLogger("hubspot_driver")


class HubSpotDriver(BaseDriver):
    """HubSpot API connector.
    
    Security: All API calls use HTTPS with SSL/TLS encryption.
    SSL certificate verification is enabled by default via requests library.
    """

    def __init__(self, connector_config: Optional[Dict[str, Any]] = None):
        super().__init__(connector_config)
        self.api_key = self.config.get("api_key")
        self.base_url = "https://api.hubapi.com"
        
        # SSL verification enabled by default, can be disabled for testing (not recommended)
        self.verify_ssl = self.config.get("verify_ssl", True)

        if not self.api_key:
            raise ValueError("HubSpot API key is required in connector_config")

    def _get_headers(self):
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def save_meeting(self, user_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        headers = self._get_headers()
        hubspot_data = {
            "body": payload.get("summary", ""),
        }

        try:
            response = requests.post(
                f"{self.base_url}/crm/v3/objects/notes",
                headers=headers,
                json=hubspot_data,
                verify=self.verify_ssl,
            )
            response.raise_for_status()
            result = response.json()

            return {
                "id": result.get("id"),
                "title": payload.get("title"),
                "summary": payload.get("summary"),
                "participants": payload.get("participants"),
                "metadata": payload.get("metadata"),
                "source": "hubspot",
            }
        except requests.exceptions.RequestException as e:
            raise Exception(f"Failed to save meeting to HubSpot: {str(e)}")

    def get_meeting_history(self, user_id: str, filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        headers = self._get_headers()

        try:
            query_data = {
                "filterGroups": [{"filters": [{"propertyName": "ownerId", "operator": "EQ", "value": user_id}]}],
                "limit": int(filters.get("limit", 20)) if filters else 20,
                "sorts": [{"propertyName": "hs_createdate", "direction": "DESCENDING"}],
            }

            response = requests.post(
                f"{self.base_url}/crm/v3/objects/notes/search",
                headers=headers,
                json=query_data,
                verify=self.verify_ssl,
            )
            response.raise_for_status()
            results = response.json().get("results", [])

            return [
                {
                    "id": result.get("id"),
                    "title": result.get("properties", {}).get("hs_note_body", "")[:100],
                    "summary": result.get("properties", {}).get("hs_note_body", ""),
                    "participants": [],
                    "metadata": {"hubspot_id": result.get("id")},
                    "created_at": result.get("properties", {}).get("hs_createdate"),
                    "source": "hubspot",
                }
                for result in results
            ]
        except requests.exceptions.RequestException as e:
            raise Exception(f"Failed to retrieve meeting history from HubSpot: {str(e)}")

    async def get_schema_info(self) -> Dict[str, Any]:
        try:
            headers = self._get_headers()
            response = requests.get(f"{self.base_url}/crm/v3/schemas", headers=headers, verify=self.verify_ssl)
            response.raise_for_status()
            schemas = response.json().get("results", [])
            
            tables = []
            for schema in schemas:
                props = schema.get("properties", [])
                tables.append({
                    "name": schema.get("name"),
                    "columns": [p.get("name") for p in props],
                    "column_types": {p.get("name"): p.get("type") for p in props}
                })
            
            logger.info(f"Introspected {len(tables)} HubSpot objects")
            return {"tables": tables}
        except Exception as e:
            logger.error(f"Failed to introspect HubSpot schema: {e}")
            raise

    async def create_entity(self, entity_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            mapping = self.config.get("schema_mappings", {}).get(entity_type)
            if not mapping:
                raise ValueError(f"No schema mapping for entity type: {entity_type}")
            
            headers = self._get_headers()
            table_name = mapping.get("table_name")
            column_mapping = mapping.get("column_mapping", {})
            
            properties = {}
            for norm_field, hubspot_field in column_mapping.items():
                if norm_field in payload and payload[norm_field] is not None:
                    properties[hubspot_field] = payload[norm_field]
            
            response = requests.post(
                f"{self.base_url}/crm/v3/objects/{table_name}",
                headers=headers,
                json={"properties": properties},
                verify=self.verify_ssl,
            )
            response.raise_for_status()
            result = response.json()
            
            return {
                "id": result.get("id"),
                **{k: result.get("properties", {}).get(v) for k, v in column_mapping.items()},
                "source": "hubspot"
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
            table_name = mapping.get("table_name")
            column_mapping = mapping.get("column_mapping", {})
            
            query_data = {
                "limit": filters.get("limit", 20) if filters else 20,
                "sorts": [{"propertyName": "createdate", "direction": "DESCENDING"}]
            }
            
            response = requests.post(
                f"{self.base_url}/crm/v3/objects/{table_name}/search",
                headers=headers,
                json=query_data,
                verify=self.verify_ssl,
            )
            response.raise_for_status()
            results = response.json().get("results", [])
            
            # Data isolation: filter by owned entity IDs if provided
            owned_entity_ids = filters.get("owned_entity_ids", []) if filters else []
            if owned_entity_ids:
                results = [r for r in results if r.get("id") in owned_entity_ids]
            
            return [
                {
                    "id": r.get("id"),
                    **{k: r.get("properties", {}).get(v) for k, v in column_mapping.items()},
                    "source": "hubspot"
                }
                for r in results
            ]
        except Exception as e:
            logger.error(f"Failed to read {entity_type}: {e}")
            raise

    async def update_entity(self, entity_type: str, entity_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        try:
            mapping = self.config.get("schema_mappings", {}).get(entity_type)
            if not mapping:
                raise ValueError(f"No schema mapping for entity type: {entity_type}")
            
            headers = self._get_headers()
            table_name = mapping.get("table_name")
            column_mapping = mapping.get("column_mapping", {})
            
            properties = {}
            for norm_field, hubspot_field in column_mapping.items():
                if norm_field in updates and updates[norm_field] is not None:
                    properties[hubspot_field] = updates[norm_field]
            
            response = requests.patch(
                f"{self.base_url}/crm/v3/objects/{table_name}/{entity_id}",
                headers=headers,
                json={"properties": properties},
                verify=self.verify_ssl,
            )
            response.raise_for_status()
            result = response.json()
            
            return {
                "id": result.get("id"),
                **{k: result.get("properties", {}).get(v) for k, v in column_mapping.items()},
                "source": "hubspot"
            }
        except Exception as e:
            logger.error(f"Failed to update {entity_type}: {e}")
            raise

    async def delete_entity(self, entity_type: str, entity_id: str) -> bool:
        try:
            mapping = self.config.get("schema_mappings", {}).get(entity_type)
            if not mapping:
                raise ValueError(f"No schema mapping for entity type: {entity_type}")
            
            headers = self._get_headers()
            table_name = mapping.get("table_name")
            
            response = requests.delete(
                f"{self.base_url}/crm/v3/objects/{table_name}/{entity_id}",
                headers=headers,
                verify=self.verify_ssl,
            )
            return response.status_code == 204
        except Exception as e:
            logger.error(f"Failed to delete {entity_type}: {e}")
            raise