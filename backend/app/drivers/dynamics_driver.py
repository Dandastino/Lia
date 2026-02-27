from __future__ import annotations

from typing import Any, Dict, List, Optional
import requests
from .base import BaseDriver


class DynamicsDriver(BaseDriver):
    """Microsoft Dynamics 365 CRM connector using REST API."""

    def __init__(self, connector_config: Optional[Dict[str, Any]] = None):
        super().__init__(connector_config)
        self.tenant_id = self.config.get("tenant_id")
        self.client_id = self.config.get("client_id")
        self.client_secret = self.config.get("client_secret")
        self.dynamics_url = self.config.get("dynamics_url")

        if not all([self.tenant_id, self.client_id, self.client_secret, self.dynamics_url]):
            raise ValueError(
                "Dynamics credentials (tenant_id, client_id, client_secret, dynamics_url) are required"
            )

        self.access_token = None
        self._refresh_token()

    def _refresh_token(self):
        """Get a fresh OAuth access token from Azure AD."""
        token_url = f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"

        payload = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "scope": f"{self.dynamics_url}/.default",
            "grant_type": "client_credentials",
        }

        try:
            response = requests.post(token_url, data=payload)
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
        """Save a meeting to Dynamics as an activity/phonecall."""
        headers = self._get_headers()

        # Map Lia meeting to Dynamics phonecall
        activity_data = {
            "subject": payload.get("title", "Meeting"),
            "description": payload.get("summary", ""),
        }

        try:
            response = requests.post(
                f"{self.dynamics_url}/api/data/v9.2/phonecalls",
                headers=headers,
                json=activity_data,
            )
            response.raise_for_status()

            # Extract ID from response header
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

    def get_meeting_history(
        self,
        user_id: str,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve meeting history from Dynamics."""
        headers = self._get_headers()

        try:
            limit = int(filters.get("limit", 20)) if filters else 20
            # Query phonecalls (activities in Dynamics)
            query = f"/api/data/v9.2/phonecalls?$select=phonecallid,subject,description,createdon&$top={limit}&$orderby=createdon desc"

            response = requests.get(
                f"{self.dynamics_url}{query}",
                headers=headers,
            )
            response.raise_for_status()
            records = response.json().get("value", [])

            meetings = []
            for record in records:
                meetings.append(
                    {
                        "id": record.get("phonecallid"),
                        "title": record.get("subject"),
                        "summary": record.get("description", ""),
                        "participants": [],
                        "metadata": {"dynamics_id": record.get("phonecallid")},
                        "created_at": record.get("createdon"),
                        "source": "dynamics",
                    }
                )

            return meetings
        except requests.exceptions.RequestException as e:
            raise Exception(f"Failed to retrieve meeting history from Dynamics: {str(e)}")
