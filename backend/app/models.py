from __future__ import annotations

from typing import Optional
from uuid import UUID
import bcrypt
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB

from .extensions import db


def _uuid_server_default():
    return db.text("uuid_generate_v4()")


class Organization(db.Model):
    """Organization / tenant configuration, including connector metadata."""

    __tablename__ = "organizations"

    id = db.Column(PG_UUID(as_uuid=True), primary_key=True, server_default=_uuid_server_default())
    name = db.Column(db.String(255), nullable=False)
    industry = db.Column(db.String(100))
    connector_type = db.Column(db.String(50), nullable=False)
    connector_config = db.Column(JSONB)
    created_at = db.Column(db.DateTime(timezone=True), server_default=db.func.now())


class User(db.Model):
    """Authentication user linked to an organization (multi-tenant)."""

    __tablename__ = "users"

    id = db.Column(PG_UUID(as_uuid=True), primary_key=True, server_default=_uuid_server_default())
    org_id = db.Column(PG_UUID(as_uuid=True), db.ForeignKey("organizations.id", ondelete="CASCADE"))
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(50), default="user")
    created_at = db.Column(db.DateTime(timezone=True), server_default=db.func.now())

    organization = db.relationship("Organization", backref=db.backref("users", lazy=True))

    def set_password(self, password: str):
        self.password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode(
            "utf-8"
        )

    def check_password(self, password: str) -> bool:
        return bcrypt.checkpw(password.encode("utf-8"), self.password_hash.encode("utf-8"))


class SyncLog(db.Model):
    """Connector sync logs for debugging/audit."""

    __tablename__ = "sync_logs"

    id = db.Column(PG_UUID(as_uuid=True), primary_key=True, server_default=_uuid_server_default())
    org_id = db.Column(PG_UUID(as_uuid=True), db.ForeignKey("organizations.id", ondelete="CASCADE"))
    status = db.Column(db.String(50))
    target_system = db.Column(db.String(50))
    error_message = db.Column(db.Text)
    created_at = db.Column(db.DateTime(timezone=True), server_default=db.func.now())

    organization = db.relationship("Organization", backref=db.backref("sync_logs", lazy=True))


class DatabaseDriver:
    """Database driver for multi-tenant organizations, users, and logs."""

    def __init__(self, app=None):
        self.app = app

    def init_app(self, app):
        self.app = app
        db.init_app(app)
        with app.app_context():
            db.create_all()

    def _uuid_any(self, value):
        if value is None:
            return None
        return value if isinstance(value, UUID) else UUID(str(value))

    def create_user(self, email: str, password: str, org_id, role: str = "user") -> Optional[User]:
        if User.query.filter_by(email=email).first():
            return None

        org = Organization.query.get(org_id)
        if not org:
            return None

        user = User(email=email, org_id=org.id, role=role)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        return user

    def get_user_by_email(self, email: str) -> Optional[User]:
        return User.query.filter_by(email=email).first()

    def get_user_by_id(self, user_id) -> Optional[User]:
        return User.query.get(self._uuid_any(user_id))

    def create_sync_log(
        self,
        org_id,
        status: str,
        target_system: str,
        error_message: Optional[str] = None,
    ) -> SyncLog:
        log = SyncLog(
            org_id=self._uuid_any(org_id),
            status=status,
            target_system=target_system,
            error_message=error_message,
        )
        db.session.add(log)
        db.session.commit()
        return log
