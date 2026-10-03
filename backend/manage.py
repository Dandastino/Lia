#!/usr/bin/env python3
"""
Development management script for creating users and organizations.
This script allows developers to manage users and organizations via CLI.

Usage:
  python manage.py org create "Company Name" --industry "Tech" --connector internal
  python manage.py user create user@example.com --password SecurePass123 --org-id <org-id> --role owner
  python manage.py org list
  python manage.py user list
"""

import argparse
import getpass
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

# Add current directory to path for app imports
sys.path.insert(0, str(Path(__file__).parent))


import bcrypt
from sqlalchemy.orm.attributes import flag_modified

from app import create_app
from app.extensions import db
from app.models import DatabaseDriver, Organization, SyncLog, User
from app.security import ALLOWED_ROLES, is_valid_email, normalize_email, validate_password

app = create_app()


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def create_organization(name: str, industry: str = None, connector_type: str = "internal"):
    """Create a new organization."""
    with app.app_context():
        try:
            org = Organization(
                name=name,
                industry=industry,
                connector_type=connector_type,
                connector_config={},
            )
            db.session.add(org)
            db.session.commit()
            print("✓ Organization created successfully")
            print(f"  ID: {org.id}")
            print(f"  Name: {org.name}")
            return org
        except Exception as e:
            print(f"✗ Failed to create organization: {e}")
            db.session.rollback()
            return None


def create_user(email: str, password: str, org_id: str, role: str = "user"):
    """Create a new user."""
    email = normalize_email(email)
    if not is_valid_email(email):
        print("✗ Invalid email address")
        return None
    if validate_password(password):
        print("✗ Password does not meet the policy (8 to 72 bytes)")
        return None
    if role not in ALLOWED_ROLES:
        print(f"✗ Invalid role. Choose one of: {', '.join(sorted(ALLOWED_ROLES))}")
        return None

    with app.app_context():
        try:
            # Verify organization exists
            org = Organization.query.get(org_id)
            if not org:
                print(f"✗ Organization not found: {org_id}")
                return None

            # Check if user already exists
            existing = User.query.filter_by(email=email).first()
            if existing:
                print(f"✗ User already exists: {email}")
                return None

            user = User(email=email, org_id=org_id, role=role)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()

            print("✓ User created successfully")
            print(f"  ID: {user.id}")
            print(f"  Email: {user.email}")
            print(f"  Organization: {org.name}")
            print(f"  Role: {user.role}")
            return user
        except Exception as e:
            print(f"✗ Failed to create user: {e}")
            db.session.rollback()
            return None


def encrypt_connectors():
    """Encrypt connector_config of every organization (requires CONNECTOR_ENCRYPTION_KEY)."""
    from app.crypto import _get_fernet

    if _get_fernet() is None:
        print("✗ CONNECTOR_ENCRYPTION_KEY is not set")
        return
    with app.app_context():
        count = 0
        for org in Organization.query.all():
            if org.connector_config is not None:
                # Force a rewrite so the column type encrypts the value.
                flag_modified(org, "connector_config")
                count += 1
        db.session.commit()
        print(f"✓ Re-saved connector_config for {count} organization(s)")


def purge_sync_logs(days: int):
    """Delete sync logs older than ``days`` days (data retention)."""
    cutoff = datetime.now(UTC) - timedelta(days=days)
    with app.app_context():
        deleted = SyncLog.query.filter(SyncLog.created_at < cutoff).delete()
        db.session.commit()
        print(f"✓ Deleted {deleted} sync log(s) older than {days} days")


def list_organizations():
    """List all organizations."""
    with app.app_context():
        try:
            orgs = Organization.query.all()
            if not orgs:
                print("No organizations found")
                return

            print(f"\n{'ID':<40} {'Name':<30} {'Industry':<20} {'Connector':<15}")
            print("-" * 105)
            for org in orgs:
                print(f"{str(org.id):<40} {org.name:<30} {(org.industry or 'N/A'):<20} {org.connector_type:<15}")
        except Exception as e:
            print(f"✗ Failed to list organizations: {e}")


def list_users():
    """List all users."""
    with app.app_context():
        try:
            users = User.query.all()
            if not users:
                print("No users found")
                return

            print(f"\n{'ID':<40} {'Email':<30} {'Organization':<30} {'Role':<10}")
            print("-" * 110)
            for user in users:
                org_name = user.organization.name if user.organization else "N/A"
                print(f"{str(user.id):<40} {user.email:<30} {org_name:<30} {user.role:<10}")
        except Exception as e:
            print(f"✗ Failed to list users: {e}")


def delete_user(email: str):
    """Delete a user by email."""
    with app.app_context():
        try:
            user = User.query.filter_by(email=email).first()
            if not user:
                print(f"✗ User not found: {email}")
                return

            db.session.delete(user)
            db.session.commit()
            print(f"✓ User deleted: {email}")
        except Exception as e:
            print(f"✗ Failed to delete user: {e}")
            db.session.rollback()


def delete_organization(org_id: str):
    """Delete an organization."""
    with app.app_context():
        try:
            org = Organization.query.get(org_id)
            if not org:
                print(f"✗ Organization not found: {org_id}")
                return

            db.session.delete(org)
            db.session.commit()
            print(f"✓ Organization deleted: {org.name}")
        except Exception as e:
            print(f"✗ Failed to delete organization: {e}")
            db.session.rollback()


def assign_entity_to_user(email: str, entity_type: str, entity_id: str):
    """Assign an external entity (e.g., patient) to a user (e.g., doctor)."""
    with app.app_context():
        try:
            user = User.query.filter_by(email=email).first()
            if not user:
                print(f"✗ User not found: {email}")
                return

            db_driver = DatabaseDriver()
            ownership = db_driver.assign_entity_to_user(
                user_id=user.id,
                org_id=user.org_id,
                entity_type=entity_type,
                external_entity_id=entity_id,
            )

            if ownership:
                print(f"✓ Assigned {entity_type} '{entity_id}' to {email}")
            else:
                print(f"✗ Failed to assign {entity_type} '{entity_id}' (duplicate?)")
        except Exception as e:
            print(f"✗ Failed to assign entity: {e}")
            db.session.rollback()


def list_user_entities(email: str, entity_type: str):
    """List all entities owned by a user."""
    with app.app_context():
        try:
            user = User.query.filter_by(email=email).first()
            if not user:
                print(f"✗ User not found: {email}")
                return

            db_driver = DatabaseDriver()
            ownerships = db_driver.get_user_owned_entities_safe(user.id, entity_type)

            if not ownerships:
                print(f"No {entity_type} entities owned by {email}")
                return

            print(f"\nEntities owned by {email} ({entity_type}):")
            print(f"{'Entity ID':<40} {'Created':<30}")
            print("-" * 70)
            for ownership in ownerships:
                created = ownership.get("created_at", "N/A")
                print(f"{ownership.get('external_entity_id', 'N/A'):<40} {created:<30}")
        except Exception as e:
            print(f"✗ Failed to list entities: {e}")


def remove_entity_from_user(email: str, entity_type: str, entity_id: str):
    """Remove entity ownership from a user."""
    with app.app_context():
        try:
            user = User.query.filter_by(email=email).first()
            if not user:
                print(f"✗ User not found: {email}")
                return

            db_driver = DatabaseDriver()
            removed = db_driver.remove_entity_from_user_safe(user.id, entity_type, entity_id)

            if removed:
                print(f"✓ Removed {entity_type} '{entity_id}' from {email}")
            else:
                print(f"✗ Entity '{entity_id}' not owned by {email} or could not be removed")
        except Exception as e:
            print(f"✗ Failed to remove entity: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Lia Assistant - Development Management CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Create an organization
  python manage.py org create "Acme Corp" --industry "Technology" --connector salesforce

  # Create a user
  python manage.py user create admin@acme.com --org-id <uuid> --role owner   # prompts for the password

  # List all organizations
  python manage.py org list

  # List all users
  python manage.py user list

  # Delete a user
  python manage.py user delete admin@acme.com

  # Delete an organization
  python manage.py org delete <uuid>

  # Assign a patient to a doctor
  python manage.py entity assign-to-user doctor@clinic.com patient 12345

  # List patients owned by a doctor
  python manage.py entity list-owned doctor@clinic.com patient

  # Remove patient from doctor
  python manage.py entity remove-from-user doctor@clinic.com patient 12345
        """,
    )

    subparsers = parser.add_subparsers(dest="resource", help="Resource type")

    # Organization commands
    org_parser = subparsers.add_parser("org", help="Organization management")
    org_subparsers = org_parser.add_subparsers(dest="action", help="Action")

    org_create = org_subparsers.add_parser("create", help="Create organization")
    org_create.add_argument("name", help="Organization name")
    org_create.add_argument("--industry", help="Industry", default=None)
    org_create.add_argument("--connector", help="Connector type", default="internal")

    org_subparsers.add_parser("list", help="List all organizations")

    org_delete = org_subparsers.add_parser("delete", help="Delete organization")
    org_delete.add_argument("org_id", help="Organization ID")

    # User commands
    user_parser = subparsers.add_parser("user", help="User management")
    user_subparsers = user_parser.add_subparsers(dest="action", help="Action")

    user_create = user_subparsers.add_parser("create", help="Create user")
    user_create.add_argument("email", help="User email")
    user_create.add_argument("--password", help="User password (prompted when omitted, recommended)")
    user_create.add_argument("--org-id", required=True, help="Organization ID")
    user_create.add_argument("--role", default="user", help="User role (user, admin, owner)")

    user_subparsers.add_parser("list", help="List all users")

    user_delete = user_subparsers.add_parser("delete", help="Delete user")
    user_delete.add_argument("email", help="User email")

    # Maintenance commands
    subparsers.add_parser("encrypt-connectors", help="Encrypt stored connector credentials")
    purge_parser = subparsers.add_parser("purge-sync-logs", help="Delete old sync logs (retention)")
    purge_parser.add_argument("--days", type=int, default=90, help="Keep logs newer than this many days")

    # Entity ownership commands
    entity_parser = subparsers.add_parser("entity", help="Entity ownership management (patient assignments, etc.)")
    entity_subparsers = entity_parser.add_subparsers(dest="action", help="Action")

    entity_assign = entity_subparsers.add_parser("assign-to-user", help="Assign entity to user")
    entity_assign.add_argument("email", help="User email (e.g., doctor)")
    entity_assign.add_argument("entity_type", help="Entity type (e.g., patient, contact, deal)")
    entity_assign.add_argument("entity_id", help="External entity ID from CRM")

    entity_list = entity_subparsers.add_parser("list-owned", help="List entities owned by user")
    entity_list.add_argument("email", help="User email")
    entity_list.add_argument("entity_type", help="Entity type (e.g., patient, contact, deal)")

    entity_remove = entity_subparsers.add_parser("remove-from-user", help="Remove entity from user")
    entity_remove.add_argument("email", help="User email")
    entity_remove.add_argument("entity_type", help="Entity type (e.g., patient, contact, deal)")
    entity_remove.add_argument("entity_id", help="External entity ID from CRM")

    args = parser.parse_args()

    if not args.resource:
        parser.print_help()
        return

    # Execute commands
    if args.resource == "org":
        if args.action == "create":
            create_organization(args.name, args.industry, args.connector)
        elif args.action == "list":
            list_organizations()
        elif args.action == "delete":
            delete_organization(args.org_id)
        else:
            org_parser.print_help()

    elif args.resource == "user":
        if args.action == "create":
            password = args.password or getpass.getpass("Password: ")
            create_user(args.email, password, args.org_id, args.role)
        elif args.action == "list":
            list_users()
        elif args.action == "delete":
            delete_user(args.email)
        else:
            user_parser.print_help()

    elif args.resource == "encrypt-connectors":
        encrypt_connectors()

    elif args.resource == "purge-sync-logs":
        purge_sync_logs(args.days)

    elif args.resource == "entity":
        if args.action == "assign-to-user":
            assign_entity_to_user(args.email, args.entity_type, args.entity_id)
        elif args.action == "list-owned":
            list_user_entities(args.email, args.entity_type)
        elif args.action == "remove-from-user":
            remove_entity_from_user(args.email, args.entity_type, args.entity_id)
        else:
            entity_parser.print_help()


if __name__ == "__main__":
    main()
