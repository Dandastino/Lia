#!/usr/bin/env python3
"""
User Mapping Sync Script - Auto-match LIA users to external DB users by email.

This script automatically creates external_user_mapping entries by:
1. Reading all LIA users in the organization
2. Reading the users table in the external database
3. Matching by email address
4. Creating external_user_mapping for each match

This eliminates manual mapping when user emails are consistent across systems.

Usage:
  python sync_user_mapping.py --org-id <org-uuid> --user-entity-type doctor --email-field email
  python sync_user_mapping.py --org-id <org-uuid> --user-entity-type lawyer --email-field email --dry-run
"""

import sys
import argparse
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app import create_app
from app.models import Organization, User, DatabaseDriver
from app.drivers.postgresql_driver import PostgreSQLDriver, PostgreSQLSchemaInspector
from app.drivers.mysql_driver import MySQLDriver, MySQLSchemaInspector

from app.schema.mapper import SchemaMappingService
from sqlalchemy import text
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

app = create_app()


async def sync_user_mappings(
    org_id: str,
    user_entity_type: str,
    dry_run: bool = False,
):
    """
    Auto-create external_user_mapping by discovering DB structure and matching emails.
    
    Automatically:
    1. Introspects external database to discover tables and columns
    2. Uses LLM to identify which table holds users (semantically understanding "doctor", "lawyer", etc.)
    3. Discovers email and ID columns automatically
    4. Matches LIA users to external users by email
    
    Works with ANY database schema and naming conventions.
    
    Args:
        org_id: Organization UUID
        user_entity_type: User type to sync (e.g., "doctor", "lawyer", "employee", "merchant", "consultant")
        dry_run: If True, only show what would be done without committing
    """
    with app.app_context():
        # Get organization and connector
        org = Organization.query.get(org_id)
        if not org:
            logger.error(f"Organization {org_id} not found")
            return
        
        connector_type = (org.connector_type or "").lower()
        config = org.connector_config or {}
        
        logger.info(f"Syncing user mappings for org {org.name} ({connector_type})")
        logger.info(f"User type to discover: {user_entity_type}")
        
        # Initialize driver and inspector
        if connector_type == "postgresql":
            driver = PostgreSQLDriver(config)
            inspector = PostgreSQLSchemaInspector(driver.engine)
        elif connector_type == "mysql":
            driver = MySQLDriver(config)
            inspector = MySQLSchemaInspector(driver.engine)
        else:
            logger.error(f"Unsupported connector type: {connector_type}")
            return
        
        # Step 1: Introspect database schema
        logger.info("Introspecting external database schema...")
        try:
            schema_info = await inspector.introspect_tables()
            logger.info(f"Found {len(schema_info)} tables in external database")
            
            # Log table names for reference
            table_names = [t["name"] for t in schema_info]
            logger.debug(f"Tables: {table_names}")
        except Exception as e:
            logger.error(f"Failed to introspect database: {e}", exc_info=True)
            return
        
        # Step 2: Use LLM to find which table stores users
        logger.info(f"Using LLM to identify {user_entity_type} table...")
        try:
            schema_mapper = SchemaMappingService()
            mapping = await schema_mapper.auto_map_entity(
                entity_type=user_entity_type,
                schema_info={"tables": schema_info},
                connector_config=config,
            )
            
            table_name = mapping.get("table_name")
            column_mapping = mapping.get("column_mapping", {})
            confidence = mapping.get("confidence", 0)
            
            logger.info(f"Identified table: {table_name} (confidence: {confidence:.1%})")
            
            if confidence < 0.7:
                logger.warning(
                    f"Low confidence match ({confidence:.1%}). "
                    f"May need manual verification."
                )
            
        except Exception as e:
            logger.error(f"Failed to auto-map {user_entity_type}: {e}", exc_info=True)
            return
        
        # Step 3: Discover email column (DRY - reuse SchemaMappingService)
        logger.info("Discovering email column...")
        try:
            table_detail = await inspector.introspect_table(table_name)
            
            # Use LLM-based email column discovery (with pattern matching + caching)
            email_info = await schema_mapper.identify_email_column(
                table_name=table_name,
                table_schema=table_detail,
                user_type=user_entity_type,
            )
            
            email_column = email_info.get("email_column")
            if not email_column:
                logger.error(
                    f"Could not find email column in {table_name}. "
                    f"Available columns: {table_detail.get('columns', [])}"
                )
                return
            
            logger.info(f"Email column: {email_column}")
            
            # Discover ID column (primary key or "id")
            id_column = table_detail.get("primary_keys", ["id"])[0] if table_detail.get("primary_keys") else "id"
            logger.info(f"ID column: {id_column}")
            
        except Exception as e:
            logger.error(f"Failed to introspect table details: {e}", exc_info=True)
            return
        
        # Step 4: Match LIA users to external users by email
        logger.info("Matching LIA users to external database users...")
        try:
            sql = f"SELECT {id_column}, {email_column} FROM {table_name} WHERE {email_column} IS NOT NULL"
            
            with driver.get_session() as session:
                result = session.execute(text(sql))
                external_users = result.fetchall()
                
                logger.info(f"Found {len(external_users)} users in external database")
                
                # Get all LIA users for this organization
                lia_users = User.query.filter_by(org_id=org_id).all()
                logger.info(f"Found {len(lia_users)} users in LIA for this organization")
                
                # Create email → external_id mapping
                external_email_map = {}
                for row in external_users:
                    external_id = str(row[0])
                    external_email = str(row[1]).lower().strip()
                    external_email_map[external_email] = external_id
                
                # Match LIA users to external users by email (DRY - use DatabaseDriver consistently)
                db_driver = DatabaseDriver()
                matched_count = 0
                skipped_count = 0
                
                for lia_user in lia_users:
                    lia_email = lia_user.email.lower().strip()
                    
                    if lia_email not in external_email_map:
                        logger.debug(
                            f"Skipping LIA user {lia_user.email}: "
                            f"no matching email in external database"
                        )
                        skipped_count += 1
                        continue
                    
                    external_user_id = external_email_map[lia_email]
                    
                    if dry_run:
                        logger.info(
                            f"[DRY RUN] Would map LIA user {lia_user.email} → "
                            f"external ID {external_user_id}"
                        )
                        matched_count += 1
                    else:
                        # Create external user mapping using consistent DatabaseDriver API
                        try:
                            db_driver.create_external_user_mapping(
                                user_id=lia_user.id,
                                org_id=org_id,
                                crm_type=connector_type,
                                external_user_id=external_user_id,
                                external_email=lia_user.email,
                            )
                            logger.info(
                                f"Mapped LIA user {lia_user.email} → external ID {external_user_id}"
                            )
                            matched_count += 1
                        except Exception as e:
                            logger.warning(
                                f"Failed to map LIA user {lia_user.email}: {e}"
                            )
                            skipped_count += 1
                
                logger.info("=" * 60)
                logger.info(f"User mapping sync complete:")
                logger.info(f"  Total LIA users: {len(lia_users)}")
                logger.info(f"  Matched: {matched_count}")
                logger.info(f"  Skipped: {skipped_count}")
                if dry_run:
                    logger.info("  (DRY RUN - no changes committed)")
                
        except Exception as e:
            logger.error(f"Failed to sync user mappings: {e}", exc_info=True)


def main():
    parser = argparse.ArgumentParser(
        description="Auto-discover users in external DB and sync to LIA by matching emails",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Sync doctors (discovers schema, email column, matches users) - dry run first
  python sync_user_mapping.py --org-id abc-123 --user-type doctor --dry-run
  
  # Actually perform the sync
  python sync_user_mapping.py --org-id abc-123 --user-type doctor
  
  # Sync lawyers, merchants, consultants, or any other role
  python sync_user_mapping.py --org-id abc-123 --user-type lawyer
  python sync_user_mapping.py --org-id abc-123 --user-type merchant
  python sync_user_mapping.py --org-id abc-123 --user-type consultant
  
How it works:
  1. Introspects external database to discover all tables
  2. Uses AI (LLM) to semantically identify which table stores the user type
  3. Automatically discovers email and ID columns
  4. Matches LIA users to external users by email
  5. Creates external_user_mapping for each match
  
Prerequisites:
  1. Create LIA users with SAME emails as external DB users
  2. Organization must have external DB connection configured
  
After this step:
  1. Run sync_ownership.py to assign entity ownership based on these user mappings
        """,
    )
    
    parser.add_argument("--org-id", required=True, help="Organization UUID")
    parser.add_argument(
        "--user-type", 
        required=True, 
        help="User type to discover (e.g., doctor, lawyer, employee, merchant, consultant, specialist)"
    )
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without committing")
    
    args = parser.parse_args()
    
    asyncio.run(sync_user_mappings(
        org_id=args.org_id,
        user_entity_type=args.user_type,
        dry_run=args.dry_run,
    ))


if __name__ == "__main__":
    main()
