from __future__ import annotations

from typing import Optional, List
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
        try:
            if not self.password_hash:
                return False
            return bcrypt.checkpw(password.encode("utf-8"), self.password_hash.encode("utf-8"))
        except (ValueError, TypeError):
            return False


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


class UserEntityOwnership(db.Model):
    """Maps external CRM entities (patients, contacts, etc.) to their owning user (doctor).
    
    This enables data isolation so that doctors only see records they own.
    Example: Doctor "Andrea" owns patients with external_entity_ids [123, 456, 789]
    """

    __tablename__ = "user_entity_ownership"

    id = db.Column(PG_UUID(as_uuid=True), primary_key=True, server_default=_uuid_server_default())
    user_id = db.Column(PG_UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    org_id = db.Column(PG_UUID(as_uuid=True), db.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    entity_type = db.Column(db.String(50), nullable=False)  # e.g., "patient", "contact", "client"
    external_entity_id = db.Column(db.String(255), nullable=False)  # The actual ID from CRM database
    created_at = db.Column(db.DateTime(timezone=True), server_default=db.func.now())
    
    # Composite unique constraint: same user can't own same entity twice
    __table_args__ = (
        db.UniqueConstraint('user_id', 'entity_type', 'external_entity_id', name='uq_user_entity'),
        db.Index('idx_user_entity_lookup', 'user_id', 'entity_type', 'org_id'),
    )

    user = db.relationship("User", backref=db.backref("owned_entities", cascade="all, delete-orphan"))
    organization = db.relationship("Organization", backref=db.backref("entity_ownerships", lazy=True))


class ExternalUserMapping(db.Model):
    """Maps LIA internal users to their external CRM identities.
    
    Example:
    - LIA user_id: "abc-123" (Andrea)
    - Salesforce: external_user_id = "SF-999"
    - HubSpot: external_user_id = "HS-555"
    
    When Andrea logs in, LIA knows to query Salesforce with SF-999
    to get only her patients/records.
    """

    __tablename__ = "external_user_mapping"

    id = db.Column(PG_UUID(as_uuid=True), primary_key=True, server_default=_uuid_server_default())
    user_id = db.Column(PG_UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    org_id = db.Column(PG_UUID(as_uuid=True), db.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    crm_type = db.Column(db.String(50), nullable=False)  # e.g., "salesforce", "hubspot", "dynamics", "postgresql"
    external_user_id = db.Column(db.String(255), nullable=False)  # The actual user ID in that CRM
    external_email = db.Column(db.String(255))  # The email in that CRM system (for verification)
    last_synced_at = db.Column(db.DateTime(timezone=True), server_default=db.func.now())
    
    # Composite unique: same user can't have two mappings for same CRM
    __table_args__ = (
        db.UniqueConstraint('user_id', 'crm_type', name='uq_user_crm_mapping'),
        db.Index('idx_external_user_lookup', 'org_id', 'crm_type', 'external_user_id'),
    )

    user = db.relationship("User", backref=db.backref("external_mappings", cascade="all, delete-orphan"))
    organization = db.relationship("Organization", backref=db.backref("external_user_mappings", lazy=True))


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
    def assign_entity_to_user(
        self,
        user_id,
        org_id,
        entity_type: str,
        external_entity_id: str,
    ) -> Optional[UserEntityOwnership]:
        """Assign an external CRM entity (e.g., patient) to a user (e.g., doctor)."""
        try:
            ownership = UserEntityOwnership(
                user_id=self._uuid_any(user_id),
                org_id=self._uuid_any(org_id),
                entity_type=entity_type,
                external_entity_id=str(external_entity_id),
            )
            db.session.add(ownership)
            db.session.commit()
            return ownership
        except Exception:
            db.session.rollback()
            return None

    def table_exists(self, table_name: str) -> bool:
        """Check if a table exists in the database."""
        try:
            db.session.execute(db.text(f"SELECT 1 FROM {table_name} LIMIT 1"))
            return True
        except Exception:
            # Table doesn't exist or access failed
            return False

    def get_user_entity_ids(
        self,
        user_id,
        entity_type: str,
    ) -> List[str]:
        """Get all external entity IDs owned by a user for a given entity type.
        
        SECURITY: Validates table existence before querying (AI-enforced).
        Returns empty list if table doesn't exist or user owns no entities.
        """
        # IMPORTANT: Validate that user_entity_ownership table exists (multitenant safety)
        if not self.table_exists('user_entity_ownership'):
            logger.warning(
                f"user_entity_ownership table does not exist for user {user_id}. "
                "Database may not be properly initialized. Returning empty entity list."
            )
            return []  # No data can be retrieved safely
        
        try:
            ownerships = UserEntityOwnership.query.filter_by(
                user_id=self._uuid_any(user_id),
                entity_type=entity_type,
            ).all()
            return [str(o.external_entity_id) for o in ownerships]
        except Exception as e:
            logger.error(
                f"Failed to query user_entity_ownership for user {user_id}, "
                f"entity_type {entity_type}: {e}"
            )
            return []  # Return empty list rather than crashing

    def user_owns_entity(
        self,
        user_id,
        entity_type: str,
        external_entity_id: str,
    ) -> bool:
        """Check if a user owns a specific external entity.
        
        SECURITY: Validates table existence before querying (AI-enforced).
        Returns False if table doesn't exist (safe default).
        """
        # IMPORTANT: Validate that user_entity_ownership table exists (multitenant safety)
        if not self.table_exists('user_entity_ownership'):
            logger.warning(
                f"user_entity_ownership table does not exist. "
                "Database may not be properly initialized."
            )
            return False  # Default to deny access if table missing
        
        try:
            ownership = UserEntityOwnership.query.filter_by(
                user_id=self._uuid_any(user_id),
                entity_type=entity_type,
                external_entity_id=str(external_entity_id),
            ).first()
            return ownership is not None
        except Exception as e:
            logger.error(
                f"Failed to check entity ownership: {e}"
            )
            return False  # Default to deny access on error

    # ============= External User Mapping Methods =============

    def create_external_user_mapping(
        self,
        user_id,
        org_id,
        crm_type: str,
        external_user_id: str,
        external_email: Optional[str] = None,
    ) -> Optional[ExternalUserMapping]:
        """Create a mapping between a LIA user and their external CRM identity.
        
        Args:
            user_id: LIA user's UUID
            org_id: Organization UUID
            crm_type: Type of CRM ("salesforce", "hubspot", "dynamics", "postgresql", etc.)
            external_user_id: The user's ID in that external system
            external_email: The user's email in that external system
        
        Returns:
            ExternalUserMapping object or None if failed
        """
        try:
            # Delete old mapping if exists (in case user was reassigned)
            ExternalUserMapping.query.filter_by(
                user_id=self._uuid_any(user_id),
                crm_type=crm_type
            ).delete()

            mapping = ExternalUserMapping(
                user_id=self._uuid_any(user_id),
                org_id=self._uuid_any(org_id),
                crm_type=crm_type,
                external_user_id=str(external_user_id),
                external_email=external_email,
            )
            db.session.add(mapping)
            db.session.commit()
            return mapping
        except Exception:
            db.session.rollback()
            return None

    def get_external_user_id(
        self,
        user_id,
        crm_type: str,
    ) -> Optional[str]:
        """Get the external user ID for a specific CRM system.
        
        Args:
            user_id: LIA user's UUID
            crm_type: Type of CRM ("salesforce", "hubspot", "dynamics", etc.)
        
        Returns:
            The external user ID or None if no mapping exists
        """
        mapping = ExternalUserMapping.query.filter_by(
            user_id=self._uuid_any(user_id),
            crm_type=crm_type,
        ).first()
        return str(mapping.external_user_id) if mapping else None

    def get_external_user_mapping(
        self,
        user_id,
        crm_type: str,
    ) -> Optional[ExternalUserMapping]:
        """Get the full external user mapping record.
        
        Args:
            user_id: LIA user's UUID
            crm_type: Type of CRM
        
        Returns:
            Full ExternalUserMapping object or None
        """
        return ExternalUserMapping.query.filter_by(
            user_id=self._uuid_any(user_id),
            crm_type=crm_type,
        ).first()

    def get_all_external_mappings(
        self,
        user_id,
    ) -> List[ExternalUserMapping]:
        """Get all external CRM mappings for a user.
        
        Useful for admin dashboards showing which systems the user is connected to.
        """
        return ExternalUserMapping.query.filter_by(
            user_id=self._uuid_any(user_id),
        ).all()

    def find_user_by_external_id(
        self,
        org_id,
        crm_type: str,
        external_user_id: str,
    ) -> Optional[User]:
        """Find a LIA user based on their external CRM ID.
        
        Useful when syncing data from external CRM - you get CRM's user ID
        and need to find the corresponding LIA user.
        
        Args:
            org_id: Organization UUID
            crm_type: Type of CRM
            external_user_id: The user's ID in the external system
        
        Returns:
            User object or None if not found
        """
        mapping = ExternalUserMapping.query.filter_by(
            org_id=self._uuid_any(org_id),
            crm_type=crm_type,
            external_user_id=str(external_user_id),
        ).first()
        return mapping.user if mapping else None

    # ============= Safe Admin/Management Methods =============

    def get_user_owned_entities_safe(
        self,
        user_id,
        entity_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Get entities owned by a user - ADMIN SAFE (checks table existence first).
        
        Args:
            user_id: User UUID
            entity_type: Optional filter by entity type
            
        Returns:
            List of entity ownership records (empty if table missing)
        """
        if not self.table_exists('user_entity_ownership'):
            logger.warning(f"user_entity_ownership table not found - returning empty list")
            return []
        
        try:
            query = UserEntityOwnership.query.filter_by(user_id=self._uuid_any(user_id))
            if entity_type:
                query = query.filter_by(entity_type=entity_type)
            
            ownerships = query.all()
            return [
                {
                    "id": str(o.id),
                    "user_id": str(o.user_id),
                    "entity_type": o.entity_type,
                    "external_entity_id": o.external_entity_id,
                    "created_at": o.created_at.isoformat() if o.created_at else None,
                }
                for o in ownerships
            ]
        except Exception as e:
            logger.error(f"Failed to get user owned entities: {e}")
            return []

    def remove_entity_from_user_safe(
        self,
        user_id,
        entity_type: str,
        external_entity_id: str,
    ) -> bool:
        """Remove entity ownership from user - ADMIN SAFE (checks table existence first).
        
        Args:
            user_id: User UUID
            entity_type: Type of entity
            external_entity_id: External entity ID
            
        Returns:
            True if successfully removed, False otherwise
        """
        if not self.table_exists('user_entity_ownership'):
            logger.warning(f"user_entity_ownership table not found - cannot remove")
            return False
        
        try:
            ownership = UserEntityOwnership.query.filter_by(
                user_id=self._uuid_any(user_id),
                entity_type=entity_type,
                external_entity_id=str(external_entity_id),
            ).first()
            
            if not ownership:
                logger.warning(f"Entity ownership not found for user {user_id}")
                return False
            
            db.session.delete(ownership)
            db.session.commit()
            logger.info(f"Removed {entity_type} entity '{external_entity_id}' from user {user_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to remove entity from user: {e}")
            db.session.rollback()
            return False