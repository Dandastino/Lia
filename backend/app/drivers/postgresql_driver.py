from __future__ import annotations

from typing import Any, Dict, List, Optional
from datetime import datetime
from contextlib import contextmanager
import logging
from sqlalchemy import create_engine, Column, String, Text, DateTime, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import QueuePool
from sqlalchemy.dialects.postgresql import UUID as JSONB
import uuid

from .base import BaseDriver
from .sql_driver_common import (
    add_owner_constraint_to_sql,
    apply_owner_scope_to_params,
    build_required_alias_hints,
    find_missing_required_columns,
    get_entity_mapping,
    get_owner_scope,
    resolve_foreign_key_values,
    resolve_required_columns,
    split_limit_and_query_filters,
)
from ..schema.inspector import BaseSQLSchemaInspector
from ..schema.query_builder import DynamicQueryBuilder
from ..utils import MeetingFormatter

logger = logging.getLogger("postgresql_driver")


def _compact_db_error(error: Exception) -> str:
    """Compress verbose DB exceptions into one actionable line for logs."""
    text = str(error).strip()
    if not text:
        return "unknown database error"

    first_line = next((line.strip() for line in text.splitlines() if line.strip()), text)
    lower = text.lower()
    if "connection refused" in lower:
        return f"connection refused ({first_line})"
    return first_line

Base = declarative_base()


class PostgreSQLSchemaInspector(BaseSQLSchemaInspector):
    """PostgreSQL schema introspector using shared SQL logic."""
    pass


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
        self.connect_timeout = int(self.config.get("connect_timeout", 5))

        if not all([self.host, self.database, self.user, self.password]):
            raise ValueError("PostgreSQL credentials (host, database, user, password) are required")

        # Build connection URI
        db_uri = f"postgresql+psycopg2://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"
        
        # SSL configuration - try to use SSL but allow fallback if not available
        ssl_mode = self.config.get("sslmode", "prefer")  # prefer, require, or disable
        
        # Create engine with connection pooling optimized for concurrent users
        self.engine = create_engine(
            db_uri,
            poolclass=QueuePool,
            pool_size=20,              # Base number of connections to maintain
            max_overflow=10,           # Allow up to 10 additional temporary connections
            pool_pre_ping=True,        # Verify connections are alive before using
            pool_recycle=3600,         # Recycle connections every hour to avoid stale connections
            echo=False,
            connect_args={
                "sslmode": ssl_mode,
                "connect_timeout": self.connect_timeout,
            }  # Enable SSL encryption and fail fast on unreachable hosts
        )
        self.SessionLocal = sessionmaker(bind=self.engine)

        # NOTE: Lia connects to EXISTING external databases.
        # We do NOT create tables in the client's database.
        # Schema discovery happens via introspection only (read-only).
        # For legacy meeting support, ensure 'lia_meetings' table exists manually in client DB.

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
                session.flush()

                return MeetingFormatter.format_meeting_response(
                    meeting_id=meeting.id,
                    title=meeting.title,
                    summary=meeting.summary,
                    participants=meeting.participants,
                    metadata=meeting.meeting_metadata,
                    created_at=meeting.created_at,
                    source="external_postgresql",
                )
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

                    owned_entity_ids = filters.get("owned_entity_ids") or []
                    if owned_entity_ids:
                        query = query.filter(ExternalMeeting.id.in_([str(entity_id) for entity_id in owned_entity_ids]))

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

    # ===== Generic CRUD methods (multi-entity support) =====

    async def get_schema_info(self) -> Dict[str, Any]:
        """Return raw database schema for LLM semantic analysis."""
        try:
            inspector = PostgreSQLSchemaInspector(self.engine)
            tables = await inspector.introspect_tables()
            logger.info(f"Introspected {len(tables)} tables from PostgreSQL")
            return {"tables": tables}
        except Exception as e:
            logger.error("Failed to introspect PostgreSQL schema: %s", _compact_db_error(e))
            raise

    async def create_entity(
        self,
        entity_type: str,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Create an entity using dynamic query builder based on schema mapping."""
        try:
            mapping = get_entity_mapping(self.config, entity_type)
            
            builder = DynamicQueryBuilder(mapping)
            sql, params = builder.build_insert(payload)
            logger.debug("Create %s initial mapped params=%s", entity_type, sorted(list(params.keys())))

            owner_col, owner_id = get_owner_scope(self)
            if apply_owner_scope_to_params(params, owner_col, owner_id):
                logger.info("Owner FK auto-stamped on create: %s=%s", owner_col, owner_id)

            # Validate and enrich insert for required DB columns before execution.
            # This avoids late IntegrityError when auto-mapping misses required fields
            # (e.g., patient tables with separate nome/cognome columns).
            table_name = builder.table_name
            inspector = inspect(self.engine)
            required_columns = resolve_required_columns(inspector, mapping, table_name, builder.id_column)
            missing_required = find_missing_required_columns(required_columns, params)

            # Attempt FK hydration from payload hints before failing for missing required fields.
            unresolved_fk_columns = resolve_foreign_key_values(
                inspector=inspector,
                table_name=table_name,
                params=params,
                payload=payload,
                session_factory=self.get_session,
                cast_as="TEXT",
                logger=logger,
                config=self.config,
                owner_scope=(owner_col, owner_id),
            )
            logger.debug("Create %s params after FK resolution=%s", entity_type, sorted(list(params.keys())))

            # If relationship hints were provided but could not be resolved, fail fast
            # instead of silently creating rows with NULL foreign keys.
            if unresolved_fk_columns:
                raise ValueError(
                    f"Cannot create {entity_type}: unresolved relationship hints for foreign key columns {sorted(set(unresolved_fk_columns))}. "
                    "Provide exact related entity IDs or names that uniquely match referenced records."
                )

            # Fail early with clear context when required columns are still missing.
            missing_required = find_missing_required_columns(required_columns, params)
            if missing_required:
                alias_hints = build_required_alias_hints(builder, missing_required)
                raise ValueError(
                    f"Cannot create {entity_type}: missing required columns {missing_required} for table {table_name}. "
                    f"Mapped aliases: {alias_hints}. "
                    "Ask the user for the missing values, then retry create."
                )

            # Rebuild SQL in case params were enriched.
            columns_str = ", ".join(params.keys())
            placeholders = ", ".join([f":{k}" for k in params.keys()])
            sql = f"INSERT INTO {table_name} ({columns_str}) VALUES ({placeholders}) RETURNING *"
            
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

    async def read_entities(
        self,
        entity_type: str,
        user_id: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Read entities using dynamic queries based on schema mapping."""
        try:
            mapping = get_entity_mapping(self.config, entity_type)
            
            builder = DynamicQueryBuilder(mapping)
            
            owner_col, owner_id = get_owner_scope(self)
            limit, query_filters = split_limit_and_query_filters(filters, user_id, builder, owner_col, owner_id)
            
            sql, params = builder.build_select(filters=query_filters if query_filters else None, limit=limit)
            
            with self.get_session() as session:
                result = session.execute(text(sql), params)
                rows = [dict(row._mapping) if hasattr(row, '_mapping') else dict(zip(result.keys(), row)) for row in result.fetchall()]
                return [builder.normalize_row(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to read {entity_type}: {e}")
            raise

    async def update_entity(
        self,
        entity_type: str,
        entity_id: str,
        updates: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Update an entity using dynamic queries."""
        try:
            mapping = get_entity_mapping(self.config, entity_type)
            
            builder = DynamicQueryBuilder(mapping)
            sql, params = builder.build_update(entity_id, updates)

            owner_col, owner_id = get_owner_scope(self)
            sql, owner_params = add_owner_constraint_to_sql(sql, owner_col, owner_id)
            params.update(owner_params)
            
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

    async def delete_entity(
        self,
        entity_type: str,
        entity_id: str,
    ) -> bool:
        """Delete an entity using dynamic queries."""
        try:
            mapping = get_entity_mapping(self.config, entity_type)
            
            builder = DynamicQueryBuilder(mapping)
            sql, params = builder.build_delete(entity_id)

            owner_col, owner_id = get_owner_scope(self)
            sql, owner_params = add_owner_constraint_to_sql(sql, owner_col, owner_id)
            params.update(owner_params)
            
            with self.get_session() as session:
                result = session.execute(text(sql), params)
                return result.rowcount > 0
        except Exception as e:
            logger.error(f"Failed to delete {entity_type}: {e}")
            raise
