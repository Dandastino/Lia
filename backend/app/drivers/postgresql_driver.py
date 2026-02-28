from __future__ import annotations

from typing import Any, Dict, List, Optional
from datetime import datetime
from contextlib import contextmanager
from sqlalchemy import create_engine, Column, String, Text, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import QueuePool
from sqlalchemy.dialects.postgresql import UUID as JSONB
import uuid

from .base import BaseDriver

Base = declarative_base()


class ExternalMeeting(Base):
    """Generic meeting model for external database connections."""
    __tablename__ = "lia_meetings"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String(255), nullable=True)
    summary = Column(Text, nullable=False)
    participants = Column(JSONB)
    meeting_metadata = Column(JSONB)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class PostgreSQLDriver(BaseDriver):
    """External PostgreSQL database connector using SQLAlchemy ORM.
    
    Optimized for concurrent users with connection pooling:
    - Pool size: 20 base connections
    - Max overflow: 10 additional temporary connections
    - Connection health checks enabled
    - Automatic connection recycling every hour
    """

    def __init__(self, connector_config: Optional[Dict[str, Any]] = None):
        super().__init__(connector_config)
        self.host = self.config.get("host")
        self.port = self.config.get("port", 5432)
        self.database = self.config.get("database")
        self.user = self.config.get("user")
        self.password = self.config.get("password")

        if not all([self.host, self.database, self.user, self.password]):
            raise ValueError("PostgreSQL credentials (host, database, user, password) are required")

        # Build connection URI
        db_uri = f"postgresql+psycopg2://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"
        
        # Create engine with connection pooling optimized for concurrent users
        self.engine = create_engine(
            db_uri,
            poolclass=QueuePool,
            pool_size=20,              # Base number of connections to maintain
            max_overflow=10,           # Allow up to 10 additional temporary connections
            pool_pre_ping=True,        # Verify connections are alive before using
            pool_recycle=3600,         # Recycle connections every hour to avoid stale connections
            echo=False
        )
        self.SessionLocal = sessionmaker(bind=self.engine)

        # Create tables if they don't exist
        Base.metadata.create_all(self.engine)

    @contextmanager
    def get_session(self):
        """Context manager for safe session handling.
        
        Ensures session is properly committed/rolled back and closed,
        even if an exception occurs. Prevents connection leaks and ensures
        connections are returned to the pool.
        """
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
        """Save a meeting to external PostgreSQL database."""
        try:
            with self.get_session() as session:
                meeting = ExternalMeeting(
                    title=payload.get("title"),
                    summary=payload.get("summary", ""),
                    participants=payload.get("participants"),
                    meeting_metadata=payload.get("metadata", {}),
                )
                session.add(meeting)
                
                # Flush to get the ID before commit
                session.flush()

                return {
                    "id": meeting.id,
                    "title": meeting.title,
                    "summary": meeting.summary,
                    "participants": meeting.participants,
                    "metadata": meeting.meeting_metadata,
                    "created_at": meeting.created_at.isoformat() if meeting.created_at else None,
                    "source": "external_postgresql",
                }
        except Exception as e:
            raise Exception(f"Failed to save meeting to external PostgreSQL: {str(e)}")

    def get_meeting_history(
        self,
        user_id: str,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve meeting history from external PostgreSQL database."""
        try:
            with self.get_session() as session:
                query = session.query(ExternalMeeting)

                # Apply optional filters
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
                        "source": "external_postgresql",
                    }
                    for m in meetings
                ]
        except Exception as e:
            raise Exception(f"Failed to retrieve meeting history from external PostgreSQL: {str(e)}")