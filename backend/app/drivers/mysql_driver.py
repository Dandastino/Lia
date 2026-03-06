from __future__ import annotations

from typing import Any, Dict, List, Optional
from datetime import datetime
from contextlib import contextmanager
import logging
from sqlalchemy import create_engine, Column, String, Text, DateTime, text
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import QueuePool
from sqlalchemy.types import JSON
import uuid

from .base import BaseDriver
from ..schema.inspector import BaseSQLSchemaInspector
from ..schema.query_builder import DynamicQueryBuilder
from ..utils import MeetingFormatter, QueryFilterBuilder

logger = logging.getLogger("mysql_driver")

Base = declarative_base()


class MySQLSchemaInspector(BaseSQLSchemaInspector):
    """MySQL schema introspector using shared SQL logic."""
    pass


class ExternalMeeting(Base):
    __tablename__ = "lia_meetings"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String(255), nullable=True)
    summary = Column(Text, nullable=False)
    participants = Column(JSON)
    meeting_metadata = Column(JSON, name="metadata")
    created_at = Column(DateTime, default=datetime.utcnow)


class MySQLDriver(BaseDriver):

    def __init__(self, connector_config: Optional[Dict[str, Any]] = None):
        super().__init__(connector_config)
        self.host = self.config.get("host")
        self.port = self.config.get("port", 3306)
        self.database = self.config.get("database")
        self.user = self.config.get("user")
        self.password = self.config.get("password")

        if not all([self.host, self.database, self.user, self.password]):
            raise ValueError("MySQL credentials (host, database, user, password) are required")

        db_uri = f"mysql+pymysql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"
        
        # SSL configuration - try to use SSL but allow fallback if not available
        ssl_config = {}
        if self.config.get("ssl", True):  # Enable SSL by default
            ssl_mode = self.config.get("ssl_mode", "PREFERRED")  # PREFERRED, REQUIRED, or DISABLED
            if ssl_mode != "DISABLED":
                ssl_config["ssl"] = {"ssl_mode": ssl_mode}
        
        self.engine = create_engine(
            db_uri,
            poolclass=QueuePool,
            pool_size=20,
            max_overflow=10,
            pool_pre_ping=True,
            pool_recycle=3600,
            echo=False,
            connect_args=ssl_config  # Enable SSL encryption
        )
        self.SessionLocal = sessionmaker(bind=self.engine)

        # NOTE: Lia connects to EXISTING external databases.
        # We do NOT create tables in the client's database.
        # Schema discovery happens via introspection only (read-only).
        # For legacy meeting support, ensure 'lia_meetings' table exists manually in client DB.

    @contextmanager
    def get_session(self):
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def save_meeting(self, user_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            with self.get_session() as session:
                meeting = ExternalMeeting(
                    title=payload.get("title"),
                    summary=payload.get("summary", ""),
                    participants=payload.get("participants"),
                    meeting_metadata=payload.get("metadata", {}),
                )
                session.add(meeting)
                session.flush()

                return MeetingFormatter.format_meeting_response(
                    meeting_id=meeting.id,
                    title=meeting.title,
                    summary=meeting.summary,
                    participants=meeting.participants,
                    metadata=meeting.meeting_metadata,
                    created_at=meeting.created_at,
                    source="external_mysql",
                )
        except Exception as e:
            raise Exception(f"Failed to save meeting to external MySQL: {str(e)}")

    def get_meeting_history(
        self,
        user_id: str,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        try:
            with self.get_session() as session:
                query = session.query(ExternalMeeting)

                if filters:
                    if filters.get("start_date"):
                        query = query.filter(ExternalMeeting.created_at >= filters["start_date"])
                    if filters.get("end_date"):
                        query = query.filter(ExternalMeeting.created_at <= filters["end_date"])

                limit = int(filters.get("limit", 20)) if filters else 20
                meetings = query.order_by(ExternalMeeting.created_at.desc()).limit(limit).all()

                return [
                    {
                        "id": m.id,
                        "title": m.title,
                        "summary": m.summary,
                        "participants": m.participants,
                        "metadata": m.meeting_metadata,
                        "created_at": m.created_at.isoformat() if m.created_at else None,
                        "source": "external_mysql",
                    }
                    for m in meetings
                ]
        except Exception as e:
            raise Exception(f"Failed to retrieve meeting history from external MySQL: {str(e)}")

    async def get_schema_info(self) -> Dict[str, Any]:
        try:
            inspector = MySQLSchemaInspector(self.engine)
            tables = await inspector.introspect_tables()
            logger.info(f"Introspected {len(tables)} tables from MySQL")
            return {"tables": tables}
        except Exception as e:
            logger.error(f"Failed to introspect MySQL schema: {e}")
            raise

    async def create_entity(self, entity_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            mapping = self.config.get("schema_mappings", {}).get(entity_type)
            if not mapping:
                raise ValueError(f"No schema mapping for entity type: {entity_type}")
            
            builder = DynamicQueryBuilder(mapping)
            sql, params = builder.build_insert(payload)
            
            with self.get_session() as session:
                result = session.execute(text(sql), params)
                row = result.fetchone()
                
                if not row:
                    raise Exception(f"Failed to insert {entity_type}")
                
                row_dict = dict(row._mapping) if hasattr(row, '_mapping') else dict(zip(result.keys(), row))
                return builder.normalize_row(row_dict)
        except Exception as e:
            logger.error(f"Failed to create {entity_type}: {e}")
            raise

    async def read_entities(self, entity_type: str, user_id: Optional[str] = None, filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        try:
            mapping = self.config.get("schema_mappings", {}).get(entity_type)
            if not mapping:
                raise ValueError(f"No schema mapping for entity type: {entity_type}")
            
            builder = DynamicQueryBuilder(mapping)
            
            if user_id and "user_id" in builder.column_mapping:
                if not filters:
                    filters = {}
                filters["user_id"] = user_id
            
            sql, params = builder.build_select(filters=filters, limit=filters.get("limit", 20) if filters else 20)
            
            with self.get_session() as session:
                result = session.execute(text(sql), params)
                rows = [dict(row._mapping) if hasattr(row, '_mapping') else dict(zip(result.keys(), row)) for row in result.fetchall()]
                return [builder.normalize_row(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to read {entity_type}: {e}")
            raise

    async def update_entity(self, entity_type: str, entity_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        try:
            mapping = self.config.get("schema_mappings", {}).get(entity_type)
            if not mapping:
                raise ValueError(f"No schema mapping for entity type: {entity_type}")
            
            builder = DynamicQueryBuilder(mapping)
            sql, params = builder.build_update(entity_id, updates)
            
            with self.get_session() as session:
                result = session.execute(text(sql), params)
                row = result.fetchone()
                
                if not row:
                    raise ValueError(f"{entity_type} not found: {entity_id}")
                
                row_dict = dict(row._mapping) if hasattr(row, '_mapping') else dict(zip(result.keys(), row))
                return builder.normalize_row(row_dict)
        except Exception as e:
            logger.error(f"Failed to update {entity_type}: {e}")
            raise

    async def delete_entity(self, entity_type: str, entity_id: str) -> bool:
        try:
            mapping = self.config.get("schema_mappings", {}).get(entity_type)
            if not mapping:
                raise ValueError(f"No schema mapping for entity type: {entity_type}")
            
            builder = DynamicQueryBuilder(mapping)
            sql, params = builder.build_delete(entity_id)
            
            with self.get_session() as session:
                result = session.execute(text(sql), params)
                return result.rowcount > 0
        except Exception as e:
            logger.error(f"Failed to delete {entity_type}: {e}")
            raise