from __future__ import annotations

import json
from uuid import UUID
from typing import Any, Dict, List, Optional
from datetime import datetime


def normalize_user_id(raw_user_id: str | None) -> str | None:
    """Normalize user_id from various formats to UUID string.
    
    Handles:
    - None/empty values
    - "User_" prefixed IDs
    - Direct UUID strings
    
    Args:
        raw_user_id: Raw user ID in various formats
        
    Returns:
        Normalized UUID string or None if invalid
    """
    if not raw_user_id:
        return None

    candidate = raw_user_id
    if raw_user_id.startswith("User_"):
        candidate = raw_user_id.split("User_", 1)[1]

    try:
        return str(UUID(candidate))
    except ValueError:
        return None


def parse_json_metadata(metadata: Any) -> Dict[str, Any]:
    """Parse metadata that might be a JSON string or already a dict.
    
    Args:
        metadata: Either a JSON string or a dict
        
    Returns:
        Parsed dict, or empty dict if parsing fails
    """
    if isinstance(metadata, str):
        try:
            return json.loads(metadata)
        except Exception:
            return {}
    return metadata or {}


class MeetingFormatter:
    """Utility for formatting meeting responses consistently across all drivers."""
    
    @staticmethod
    def format_meeting_response(
        meeting_id: Any,
        title: str | None,
        summary: str,
        participants: Any,
        metadata: Dict[str, Any],
        created_at: Any,
        source: str,
    ) -> Dict[str, Any]:
        """Format a meeting record into standardized response format.
        
        Args:
            meeting_id: Meeting identifier
            title: Meeting title/subject
            summary: Meeting summary/notes
            participants: List of participants or participant data
            metadata: Additional metadata
            created_at: Creation timestamp (datetime or string)
            source: Source system identifier
            
        Returns:
            Standardized meeting dict
        """
        # Handle created_at formatting
        if isinstance(created_at, datetime):
            created_at_str = created_at.isoformat()
        elif created_at:
            created_at_str = str(created_at)
        else:
            created_at_str = None
        
        return {
            "id": str(meeting_id) if meeting_id else None,
            "title": title,
            "summary": summary,
            "participants": participants or [],
            "metadata": metadata or {},
            "created_at": created_at_str,
            "source": source,
        }


class QueryFilterBuilder:
    """Utility for building consistent query filters across drivers."""
    
    @staticmethod
    def parse_filters(filters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Parse and normalize filter parameters.
        
        Args:
            filters: Raw filter dict from user input
            
        Returns:
            Normalized filter dict with validated values
        """
        if not filters:
            return {
                "limit": 20,
                "start_date": None,
                "end_date": None,
                "user_only": True,
            }
        
        return {
            "limit": max(1, min(int(filters.get("limit", 20)), 50)),
            "start_date": filters.get("start_date"),
            "end_date": filters.get("end_date"),
            "user_only": filters.get("user_only", True),
            "owned_entity_ids": filters.get("owned_entity_ids"),
            "external_user_id": filters.get("external_user_id"),
        }
    
    @staticmethod
    def apply_date_filters(query: Any, filters: Dict[str, Any], date_column: Any) -> Any:
        """Apply date range filters to a SQLAlchemy query.
        
        Args:
            query: SQLAlchemy query object
            filters: Parsed filters dict
            date_column: The date column to filter on
            
        Returns:
            Modified query with date filters applied
        """
        if filters.get("start_date"):
            query = query.filter(date_column >= filters["start_date"])
        if filters.get("end_date"):
            query = query.filter(date_column <= filters["end_date"])
        return query
