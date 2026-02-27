from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..models import Organization, User, DatabaseDriver
from ..drivers.base import BaseDriver
from ..drivers.postgresql_driver import PostgreSQLDriver
from ..drivers.mysql_driver import MySQLDriver
from ..drivers.hubspot_driver import HubSpotDriver
from ..drivers.salesforce_driver import SalesforceDriver
from ..drivers.dynamics_driver import DynamicsDriver


class DataManager:
    """Factory + strategy over connector drivers."""

    def __init__(self, org: Organization, driver: BaseDriver):
        self.org = org
        self.driver = driver
        self._db_driver = DatabaseDriver()

    @classmethod
    def from_user_id(cls, user_id: str) -> "DataManager":
        user = User.query.get(user_id)
        if not user:
            raise ValueError("User not found")

        if not user.org_id:
            raise ValueError("User is not associated with an organization")

        org = user.organization
        connector_type = (org.connector_type or "").lower()
        config = org.connector_config or {}

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

        return cls(org=org, driver=driver)

    def save_meeting(self, user_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            result = self.driver.save_meeting(user_id, payload)
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

    def get_meeting_history(
        self,
        user_id: str,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        return self.driver.get_meeting_history(user_id, filters=filters)
