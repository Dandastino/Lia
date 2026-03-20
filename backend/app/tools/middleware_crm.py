from __future__ import annotations

from typing import Any, Dict, Optional

from .middleware_base import BaseMiddlewareTools


class CRMMiddlewareTools(BaseMiddlewareTools):
    """Middleware strategy for API CRM drivers (HubSpot/Salesforce/Dynamics)."""

    def _merge_related_entities_into_payload(
        self,
        payload: Dict[str, Any],
        related_entities: Optional[Dict[str, Any]],
    ) -> None:
        if isinstance(related_entities, dict):
            payload["related_entities"] = related_entities

    def _merge_metadata_into_payload(
        self,
        payload: Dict[str, Any],
        metadata: Optional[Dict[str, Any]],
    ) -> None:
        # CRM drivers may use metadata as nested association/context hints.
        if metadata is None:
            return
        payload["metadata"] = metadata
