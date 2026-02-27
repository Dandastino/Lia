from __future__ import annotations

from typing import Any, Dict, List, Optional
import requests
from .base import BaseDriver


class HubSpotDriver(BaseDriver):
    """HubSpot CRM connector using REST API."""

    def __init__(self, connector_config: Optional[Dict[str, Any]] = None):
        super().__init__(connector_config)
        self.api_key = self.config.get("api_key")
        self.base_url = "https://api.hubapi.com"

        if not self.api_key:
            raise ValueError("HubSpot API key is required in connector_config")

    def _get_headers(self):
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def save_meeting(self, user_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Save a meeting to HubSpot as a note or engagement."""
        headers = self._get_headers()

        # Map Lia meeting to HubSpot note
        hubspot_data = {
            "body": payload.get("summary", ""),
            "ownerId": user_id,
        }

        try:
            response = requests.post(
                f"{self.base_url}/crm/v3/objects/notes",
                headers=headers,
                json=hubspot_data,
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

    def get_meeting_history(
        self,
        user_id: str,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve meeting history from HubSpot."""
        headers = self._get_headers()

        try:
            # Query notes associated with the user
            query_data = {
                "filterGroups": [
                    {
                        "filters": [
                            {
                                "propertyName": "ownerId",
                                "operator": "EQ",
                                "value": user_id,
                            }
                        ]
                    }
                ],
                "limit": int(filters.get("limit", 20)) if filters else 20,
                "sorts": [{"propertyName": "hs_createdate", "direction": "DESCENDING"}],
            }

            response = requests.post(
                f"{self.base_url}/crm/v3/objects/notes/search",
                headers=headers,
                json=query_data,
            )
            response.raise_for_status()
            results = response.json().get("results", [])

            meetings = []
            for result in results:
                properties = result.get("properties", {})
                meetings.append(
                    {
                        "id": result.get("id"),
                        "title": properties.get("hs_note_body", "")[:100],
                        "summary": properties.get("hs_note_body", ""),
                        "participants": [],
                        "metadata": {"hubspot_id": result.get("id")},
                        "created_at": properties.get("hs_createdate"),
                        "source": "hubspot",
                    }
                )

            return meetings
        except requests.exceptions.RequestException as e:
            raise Exception(f"Failed to retrieve meeting history from HubSpot: {str(e)}")
