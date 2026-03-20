from __future__ import annotations

import logging

from ..models import User
from .middleware_base import BaseMiddlewareTools
from .middleware_crm import CRMMiddlewareTools
from .middleware_sql import SQLMiddlewareTools

logger = logging.getLogger("middleware_tools")

_SQL_CONNECTORS = {"postgresql", "mysql"}
_CRM_CONNECTORS = {"hubspot", "salesforce", "dynamics"}


def resolve_middleware_class(user_id: str):
    """Resolve the middleware strategy class for the user's organization connector."""
    try:
        user = User.query.get(user_id) if user_id else None
        connector_type = (getattr(getattr(user, "organization", None), "connector_type", None) or "").lower()
    except Exception as exc:
        logger.warning("Could not resolve middleware strategy for user %s: %s", user_id, exc)
        connector_type = ""

    if connector_type in _SQL_CONNECTORS:
        return SQLMiddlewareTools
    if connector_type in _CRM_CONNECTORS:
        return CRMMiddlewareTools
    return BaseMiddlewareTools
