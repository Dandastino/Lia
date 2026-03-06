from __future__ import annotations

from typing import Any, Dict, List, Optional
import requests
import logging
from .base import BaseDriver

logger = logging.getLogger(__name__)


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

        if not all([self.tenant_id, self.client_id, self.client_secret, self.dynamics_url]):
            raise ValueError(
                "Dynamics credentials (tenant_id, client_id, client_secret, dynamics_url) are required"
            )

        self.access_token = None
        self._refresh_token()

    def _refresh_token(self):
        token_url = f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"

        payload = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "scope": f"{self.dynamics_url}/.default",
            "grant_type": "client_credentials",
        }

        try:
            response = requests.post(token_url, data=payload, verify=self.verify_ssl)
            response.raise_for_status()
            self.access_token = response.json().get("access_token")
        except requests.exceptions.RequestException as e:
            raise Exception(f"Failed to obtain Dynamics access token: {str(e)}")

    def _get_headers(self):
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "OData-MaxVersion": "4.0",
            "OData-Version": "4.0",
        }

    def save_meeting(self, user_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Save meeting to Dynamics 365 as phone call activity.
        
        Args:
            user_id: User identifier (not used by Dynamics, kept for interface consistency)
            payload: Meeting data
        """
        headers = self._get_headers()
        activity_data = {
            "subject": payload.get("title", "Meeting"),
            "description": payload.get("summary", ""),
        }

        try:
            response = requests.post(
                f"{self.dynamics_url}/api/data/v9.2/phonecalls",
                headers=headers,
                json=activity_data,
                verify=self.verify_ssl,
            )
            response.raise_for_status()
            entity_id = response.headers.get("OData-EntityId", "").split("(")[-1].rstrip(")")

            return {
                "id": entity_id,
                "title": payload.get("title"),
                "summary": payload.get("summary"),
                "participants": payload.get("participants"),
                "metadata": payload.get("metadata", {"dynamics_id": entity_id}),
                "source": "dynamics",
            }
        except requests.exceptions.RequestException as e:
            raise Exception(f"Failed to save meeting to Dynamics: {str(e)}")

    def get_meeting_history(self, filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        headers = self._get_headers()

        try:
            limit = int(filters.get("limit", 20)) if filters else 20
            query = f"/api/data/v9.2/phonecalls?$select=phonecallid,subject,description,createdon&$top={limit}&$orderby=createdon desc"

            response = requests.get(f"{self.dynamics_url}{query}", headers=headers, verify=self.verify_ssl)
            response.raise_for_status()
            records = response.json().get("value", [])

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
            raise Exception(f"Failed to retrieve meeting history from Dynamics: {str(e)}")

    async def get_schema_info(self) -> Dict[str, Any]:
        try:
            headers = self._get_headers()
            response = requests.get(
                f"{self.dynamics_url}/api/data/v9.2/$metadata",
                headers=headers,
                verify=self.verify_ssl,
            )
            response.raise_for_status()
            
            entities_resp = requests.get(
                f"{self.dynamics_url}/api/data/v9.2/EntityDefinitions?$select=LogicalName",
                headers=headers,
                verify=self.verify_ssl,
            )
            entities_resp.raise_for_status()
            entities = entities_resp.json().get("value", [])
            
            tables = []
            for entity in entities[:50]:
                entity_name = entity.get("LogicalName")
                attr_resp = requests.get(
                    f"{self.dynamics_url}/api/data/v9.2/EntityDefinitions(LogicalName='{entity_name}')/Attributes?$select=LogicalName,AttributeType",
                    headers=headers,
                    verify=self.verify_ssl,
                )
                if attr_resp.status_code == 200:
                    attrs = attr_resp.json().get("value", [])
                    tables.append({
                        "name": entity_name,
                        "columns": [a.get("LogicalName") for a in attrs],
                        "column_types": {a.get("LogicalName"): a.get("AttributeType") for a in attrs}
                    })
            
            logger.info(f"Introspected {len(tables)} Dynamics entities")
            return {"tables": tables}
        except Exception as e:
            logger.error(f"Failed to introspect Dynamics schema: {e}")
            raise

    async def create_entity(self, entity_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            mapping = self.config.get("schema_mappings", {}).get(entity_type)
            if not mapping:
                raise ValueError(f"No schema mapping for entity type: {entity_type}")
            
            headers = self._get_headers()
            entity_name = mapping.get("table_name")
            column_mapping = mapping.get("column_mapping", {})
            
            dyn_data = {}
            for norm_field, dyn_field in column_mapping.items():
                if norm_field in payload and payload[norm_field] is not None:
                    dyn_data[dyn_field] = payload[norm_field]
            
            response = requests.post(
                f"{self.dynamics_url}/api/data/v9.2/{entity_name}",
                headers=headers,
                json=dyn_data,
                verify=self.verify_ssl,
            )
            response.raise_for_status()
            entity_id = response.headers.get("OData-EntityId", "").split("(")[-1].rstrip(")")
            
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
            mapping = self.config.get("schema_mappings", {}).get(entity_type)
            if not mapping:
                raise ValueError(f"No schema mapping for entity type: {entity_type}")
            
            headers = self._get_headers()
            entity_name = mapping.get("table_name")
            column_mapping = mapping.get("column_mapping", {})
            
            fields = ",".join(column_mapping.values())
            limit = filters.get("limit", 20) if filters else 20
            id_field = mapping.get("id_column", f"{entity_name}id")
            
            # Data isolation: filter by owned entity IDs at query level (OData $filter parameter)
            owned_entity_ids = filters.get("owned_entity_ids", []) if filters else []
            filter_clause = ""
            if owned_entity_ids:
                id_filters = " or ".join([f"{id_field} eq '{id}'" for id in owned_entity_ids])
                filter_clause = f"&$filter={id_filters}"
            
            query = f"/api/data/v9.2/{entity_name}?$select={fields},{id_field}&$top={limit}&$orderby=createdon desc{filter_clause}"
            
            response = requests.get(f"{self.dynamics_url}{query}", headers=headers, verify=self.verify_ssl)
            response.raise_for_status()
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
            mapping = self.config.get("schema_mappings", {}).get(entity_type)
            if not mapping:
                raise ValueError(f"No schema mapping for entity type: {entity_type}")
            
            headers = self._get_headers()
            entity_name = mapping.get("table_name")
            column_mapping = mapping.get("column_mapping", {})
            
            dyn_data = {}
            for norm_field, dyn_field in column_mapping.items():
                if norm_field in updates and updates[norm_field] is not None:
                    dyn_data[dyn_field] = updates[norm_field]
            
            response = requests.patch(
                f"{self.dynamics_url}/api/data/v9.2/{entity_name}({entity_id})",
                headers=headers,
                json=dyn_data,
                verify=self.verify_ssl,
            )
            response.raise_for_status()
            
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
            mapping = self.config.get("schema_mappings", {}).get(entity_type)
            if not mapping:
                raise ValueError(f"No schema mapping for entity type: {entity_type}")
            
            headers = self._get_headers()
            entity_name = mapping.get("table_name")
            
            response = requests.delete(
                f"{self.dynamics_url}/api/data/v9.2/{entity_name}({entity_id})",
                headers=headers,
                verify=self.verify_ssl,
            )
            return response.status_code == 204
        except Exception as e:
            logger.error(f"Failed to delete {entity_type}: {e}")
            raise