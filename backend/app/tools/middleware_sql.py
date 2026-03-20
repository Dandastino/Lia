from __future__ import annotations

import re
from typing import Any, Dict, Optional

from ..services.data_manager import DataManager
from .middleware_base import BaseMiddlewareTools


class SQLMiddlewareTools(BaseMiddlewareTools):
    """Middleware strategy for SQL-family drivers (PostgreSQL/MySQL)."""

    def _merge_related_entities_into_payload(
        self,
        payload: Dict[str, Any],
        related_entities: Optional[Dict[str, Any]],
    ) -> None:
        if not isinstance(related_entities, dict):
            return

        payload["related_entities"] = related_entities

        # Normalize common FK hints so SQL drivers can resolve relationships.
        for rel_key, rel_value in related_entities.items():
            target_fk_key = rel_key if isinstance(rel_key, str) and rel_key.endswith("_id") else f"{rel_key}_id"

            if isinstance(rel_value, dict) and rel_value.get("id"):
                payload[target_fk_key] = rel_value.get("id")
                continue

            if isinstance(rel_value, (int, float)):
                payload[target_fk_key] = rel_value
                continue

            if isinstance(rel_value, str):
                rel_value_stripped = rel_value.strip()
                if rel_value_stripped.isdigit() or re.fullmatch(r"[0-9a-fA-F-]{8,}", rel_value_stripped):
                    payload[target_fk_key] = rel_value_stripped
                    continue

            if isinstance(rel_key, str) and rel_key.endswith("_id") and rel_value is not None:
                payload[rel_key] = rel_value

    def _merge_metadata_into_payload(
        self,
        payload: Dict[str, Any],
        metadata: Optional[Dict[str, Any]],
    ) -> None:
        # SQL CRUD treats metadata dict as explicit field overrides.
        if metadata is None:
            return
        if isinstance(metadata, dict):
            payload.update(metadata)
            return
        payload["metadata"] = metadata

    def _use_live_required_column_resolution(self, dm: DataManager) -> bool:
        return hasattr(dm.driver, "engine")

    def _finalize_update_payload(self, dm: DataManager, update_payload: Dict[str, Any]) -> None:
        # SQL drivers cannot PATCH relationship helpers directly.
        if hasattr(dm.driver, "engine"):
            update_payload.pop("related_entities", None)
