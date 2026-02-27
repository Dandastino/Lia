from __future__ import annotations

from typing import Any, Dict, List, Optional

from livekit.agents import llm

from ..services.data_manager import DataManager


class MiddlewareTools:
    """Industry-agnostic tools that the agent can call."""

    def __init__(self, user_id: str):
        self.user_id = user_id

        self.save_meeting_tool = llm.function_tool(
            description="Save a summary of the current meeting, including participants and key details.",
        )(self._save_meeting)

        self.get_history_tool = llm.function_tool(
            description="Get previous meetings for this user, for additional context.",
        )(self._get_history)

    def get_tools(self):
        return [self.save_meeting_tool, self.get_history_tool]

    async def _save_meeting(
        self,
        summary: str,
        title: Optional[str] = None,
        participants: Optional[List[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        dm = DataManager.from_user_id(self.user_id)
        payload: Dict[str, Any] = {
            "title": title,
            "summary": summary,
            "participants": participants or [],
            "metadata": metadata or {},
        }
        return dm.save_meeting(user_id=self.user_id, payload=payload)

    async def _get_history(
        self,
        limit: int = 10,
        user_only: bool = True,
    ) -> List[Dict[str, Any]]:
        dm = DataManager.from_user_id(self.user_id)
        filters: Dict[str, Any] = {
            "limit": max(1, min(limit, 50)),
            "user_only": user_only,
        }
        return dm.get_meeting_history(user_id=self.user_id, filters=filters)
