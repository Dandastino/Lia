from __future__ import annotations

from typing import Any, Dict, List, Optional
import requests
from .base import BaseDriver


class SalesforceDriver(BaseDriver):
    """Salesforce CRM connector using REST API."""

    def __init__(self, connector_config: Optional[Dict[str, Any]] = None):
        super().__init__(connector_config)
        self.instance_url = self.config.get("instance_url")
        self.client_id = self.config.get("client_id")
        self.client_secret = self.config.get("client_secret")
        self.username = self.config.get("username")
        self.password = self.config.get("password")

        if not all([self.instance_url, self.client_id, self.client_secret, self.username, self.password]):
            raise ValueError(
                "Salesforce credentials (instance_url, client_id, client_secret, username, password) are required"
            )

        self.access_token = None
        self._refresh_token()

    def _refresh_token(self):
        """Get a fresh OAuth access token from Salesforce."""
        token_url = f"{self.instance_url}/services/oauth2/token"

        payload = {
            "grant_type": "password",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "username": self.username,
            "password": self.password,
        }

        try:
            response = requests.post(token_url, data=payload)
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
        """Save a meeting to Salesforce as a task."""
        headers = self._get_headers()

        # Map Lia meeting to Salesforce Task
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

    def get_meeting_history(
        self,
        user_id: str,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve meeting history from Salesforce."""
        headers = self._get_headers()

        try:
            limit = int(filters.get("limit", 20)) if filters else 20
            # Query tasks ordered by created date
            query = f"SELECT Id, Subject, Description, Status, CreatedDate FROM Task ORDER BY CreatedDate DESC LIMIT {limit}"

            response = requests.get(
                f"{self.instance_url}/services/data/v60.0/query",
                headers=headers,
                params={"q": query},
            )
            response.raise_for_status()
            records = response.json().get("records", [])

            meetings = []
            for record in records:
                meetings.append(
                    {
                        "id": record.get("Id"),
                        "title": record.get("Subject"),
                        "summary": record.get("Description", ""),
                        "participants": [],
                        "metadata": {"salesforce_id": record.get("Id")},
                        "created_at": record.get("CreatedDate"),
                        "source": "salesforce",
                    }
                )

            return meetings
        except requests.exceptions.RequestException as e:
            raise Exception(f"Failed to retrieve meeting history from Salesforce: {str(e)}")
