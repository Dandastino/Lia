from __future__ import annotations

import logging
import re
import uuid
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import Column, DateTime, String, Text, create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import QueuePool
from sqlalchemy.types import JSON

from ..schema.inspector import BaseSQLSchemaInspector
from ..schema.query_builder import DynamicQueryBuilder
from ..utils import MeetingFormatter
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

    @staticmethod
    def _is_safe_identifier(value: str) -> bool:
        return bool(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value or ""))

    def _fetch_row_by_id(
        self,
        session,
        table_name: str,
        id_column: str,
        entity_id: Any,
    ) -> Optional[Dict[str, Any]]:
        if not (self._is_safe_identifier(table_name) and self._is_safe_identifier(id_column)):
            return None
        query = text(f"SELECT * FROM {table_name} WHERE {id_column} = :entity_id LIMIT 1")
        result = session.execute(query, {"entity_id": entity_id})
        row = result.fetchone()
        if not row:
            return None
        return dict(row._mapping) if hasattr(row, "_mapping") else dict(zip(result.keys(), row, strict=False))

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
            raise Exception(f"Failed to save meeting to external MySQL: {str(e)}") from e

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
                        "source": "external_mysql",
                    }
                    for m in meetings
                ]
        except Exception as e:
            raise Exception(f"Failed to retrieve meeting history from external MySQL: {str(e)}") from e

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
            mapping = get_entity_mapping(self.config, entity_type)

            builder = DynamicQueryBuilder(mapping)
            sql, params = builder.build_insert(payload)
            sql = sql.replace(" RETURNING *", "")
            logger.debug("Create %s initial mapped params=%s", entity_type, sorted(list(params.keys())))

            owner_col, owner_id = get_owner_scope(self)
            if apply_owner_scope_to_params(params, owner_col, owner_id):
                logger.info("Owner FK auto-stamped on create: %s=%s", owner_col, owner_id)

            table_name = builder.table_name
            inspector = inspect(self.engine)
            required_columns = resolve_required_columns(inspector, mapping, table_name, builder.id_column)

            # Attempt FK hydration from payload hints before failing for missing required fields.
            unresolved_fk_columns = resolve_foreign_key_values(
                inspector=inspector,
                table_name=table_name,
                params=params,
                payload=payload,
                session_factory=self.get_session,
                cast_as="CHAR",
                logger=logger,
                config=self.config,
                owner_scope=(owner_col, owner_id),
            )
            logger.debug("Create %s params after FK resolution=%s", entity_type, sorted(list(params.keys())))

            if unresolved_fk_columns:
                raise ValueError(
                    f"Cannot create {entity_type}: unresolved relationship hints for foreign key columns {sorted(set(unresolved_fk_columns))}. "
                    "Provide exact related entity IDs or names that uniquely match referenced records."
                )

            missing_required = find_missing_required_columns(required_columns, params)
            if missing_required:
                alias_hints = build_required_alias_hints(builder, missing_required)
                raise ValueError(
                    f"Cannot create {entity_type}: missing required columns {missing_required} for table {table_name}. "
                    f"Mapped aliases: {alias_hints}. "
                    "Ask the user for the missing values, then retry create."
                )

            # Rebuild the INSERT: the owner stamp and resolved foreign keys were added to
            # params after the statement was first built (PostgreSQL does the same).
            columns_str = ", ".join(params.keys())
            placeholders = ", ".join([f":{k}" for k in params])
            sql = f"INSERT INTO {table_name} ({columns_str}) VALUES ({placeholders})"

            with self.get_session() as session:
                result = session.execute(text(sql), params)
                inserted_id = params.get(builder.id_column)
                if inserted_id is None:
                    inserted_id = getattr(result, "lastrowid", None)

                if inserted_id is None:
                    raise Exception(f"Failed to determine inserted id for {entity_type}")

                row_dict = self._fetch_row_by_id(session, builder.table_name, builder.id_column, inserted_id)
                if not row_dict:
                    raise Exception(f"Failed to fetch inserted {entity_type} row")
                return builder.normalize_row(row_dict)
        except Exception as e:
            logger.error(f"Failed to create {entity_type}: {e}")
            raise

    async def read_entities(self, entity_type: str, user_id: Optional[str] = None, filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        try:
            mapping = get_entity_mapping(self.config, entity_type)

            builder = DynamicQueryBuilder(mapping)

            owner_col, owner_id = get_owner_scope(self)
            limit, query_filters = split_limit_and_query_filters(filters, user_id, builder, owner_col, owner_id)
            sql, params = builder.build_select(
                filters=query_filters if query_filters else None,
                limit=limit,
                trusted_columns=[owner_col] if owner_col else [],
            )

            with self.get_session() as session:
                result = session.execute(text(sql), params)
                rows = [dict(row._mapping) if hasattr(row, '_mapping') else dict(zip(result.keys(), row, strict=False)) for row in result.fetchall()]
                return [builder.normalize_row(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to read {entity_type}: {e}")
            raise

    async def update_entity(self, entity_type: str, entity_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        try:
            mapping = get_entity_mapping(self.config, entity_type)

            builder = DynamicQueryBuilder(mapping)
            sql, params = builder.build_update(entity_id, updates)
            sql = sql.replace(" RETURNING *", "")

            owner_col, owner_id = get_owner_scope(self)
            sql, owner_params = add_owner_constraint_to_sql(sql, owner_col, owner_id)
            params.update(owner_params)

            with self.get_session() as session:
                result = session.execute(text(sql), params)
                if result.rowcount <= 0:
                    raise ValueError(f"{entity_type} not found: {entity_id}")

                row_dict = self._fetch_row_by_id(session, builder.table_name, builder.id_column, entity_id)
                if not row_dict:
                    raise ValueError(f"{entity_type} not found after update: {entity_id}")
                return builder.normalize_row(row_dict)
        except Exception as e:
            logger.error(f"Failed to update {entity_type}: {e}")
            raise

    async def delete_entity(self, entity_type: str, entity_id: str) -> bool:
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
