from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class BaseDriver(ABC):
    """Connector driver interface for data operations.

    All drivers implement the same methods so that higher layers
    remain agnostic to the underlying storage / CRM.
    """

    def __init__(self, connector_config: Optional[Dict[str, Any]] = None):
        self.config = connector_config or {}

    @abstractmethod
    def save_meeting(self, doctor_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Persist a meeting record and return a canonical representation."""
        raise NotImplementedError

    @abstractmethod
    def get_meeting_history(
        self,
        doctor_id: str,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Return list of meetings for the doctor/organization."""
        raise NotImplementedError

