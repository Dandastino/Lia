from __future__ import annotations

from .middleware_factory import resolve_middleware_class


class MiddlewareTools:
    """Compatibility facade that selects SQL or CRM middleware strategy per connector."""

    def __new__(cls, user_id: str):
        strategy_cls = resolve_middleware_class(user_id)
        return strategy_cls(user_id)
