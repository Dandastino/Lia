#!/usr/bin/env python3
"""
Ownership Sync Script - Sync existing external DB records to user_entity_ownership.

This script automatically discovers which external records belong to which LIA users by:
1. Reading the external database schema
2. Using LLM to identify owner/assignment columns (e.g., owner_id, assigned_to, user_id)
3. Mapping external user IDs to LIA user IDs via external_user_mapping
4. Populating user_entity_ownership for data isolation

Usage:
  python sync_ownership.py --org-id <org-uuid> --entity-type patient
  python sync_ownership.py --org-id <org-uuid> --entity-type contact --dry-run

Prerequisites:
  1. Create external_user_mapping entries first (map LIA users to external DB user IDs)
  2. Ensure schema_mappings exist for the entity_type (run Lia once to auto-map)
"""

import sys
import asyncio
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app import create_app
from app.models import Organization, User, DatabaseDriver
from app.drivers.postgresql_driver import PostgreSQLDriver
from app.drivers.mysql_driver import MySQLDriver
from app.schema.inspector import PostgreSQLSchemaInspector, MySQLSchemaInspector
from app.schema.mapper import SchemaMappingService
from sqlalchemy import text
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

app = create_app()


async def sync_ownership_for_entity(
    org_id: str,
    entity_type: str,
    dry_run: bool = False,
):
    """
    Sync ownership for an entity type by reading external DB.
    
    Automatically identifies the owner column using LLM (no manual parameters needed).
    
    Args:
        org_id: Organization UUID
        entity_type: Entity type to sync (e.g., "patient", "contact")
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
        
        logger.info(f"Syncing ownership for {entity_type} in org {org.name} ({connector_type})")
        
        # Get schema mapping for entity type
        schema_mappings = config.get("schema_mappings", {})
        mapping = schema_mappings.get(entity_type)
        
        if not mapping:
            logger.error(f"No schema mapping found for {entity_type}. Run Lia once to auto-map schema first.")
            return
        
        table_name = mapping.get("table_name")
        id_column = mapping.get("id_column", "id")
        
        if not table_name:
            logger.error(f"No table_name in mapping for {entity_type}")
            return
        
        logger.info(f"External table: {table_name}")
        logger.info(f"ID column (DB): {id_column}")
        
        # Initialize driver to access external DB
        if connector_type == "postgresql":
            driver = PostgreSQLDriver(config)
            inspector = PostgreSQLSchemaInspector(driver.engine)
        elif connector_type == "mysql":
            driver = MySQLDriver(config)
            inspector = MySQLSchemaInspector(driver.engine)
        else:
            logger.error(f"Unsupported connector type: {connector_type}")
            return
        
        # Introspect table schema
        try:
            table_schema = await inspector.introspect_table(table_name)
            logger.info(f"Introspected table {table_name}: {len(table_schema.get('columns', []))} columns")
        except Exception as e:
            logger.error(f"Failed to introspect table {table_name}: {e}")
            return
        
        # Use LLM to identify owner column (DRY - reuse SchemaMappingService)
        schema_mapper = SchemaMappingService()
        try:
            owner_info = await schema_mapper.identify_owner_column(
                table_name=table_name,
                table_schema=table_schema,
                entity_type=entity_type,
            )
            owner_column = owner_info.get("owner_column")
            owner_confidence = owner_info.get("confidence", 0)
            owner_type = owner_info.get("owner_type", "unknown")
            
            if owner_confidence < 0.7:
                logger.warning(
                    f"Low confidence ({owner_confidence:.1%}) identifying owner column. "
                    f"Owner type: {owner_type}. Suggest manual verification."
                )
            
            logger.info(f"Identified owner column: {owner_column} ({owner_type}, {owner_confidence:.1%} confidence)")
        except Exception as e:
            logger.error(f"Failed to identify owner column for {entity_type}: {e}")
            return
        
        # Read all records from external table
        sql = f"SELECT {id_column}, {owner_column} FROM {table_name} WHERE {owner_column} IS NOT NULL"
        
        try:
            with driver.get_session() as session:
                result = session.execute(text(sql))
                records = result.fetchall()
                
                logger.info(f"Found {len(records)} records with owner assignments")
                
                db_driver = DatabaseDriver()
                assigned_count = 0
                skipped_count = 0
                
                for row in records:
                    record_id = str(row[0])
                    external_owner_id = str(row[1])
                    
                    # Find LIA user by external ID mapping
                    lia_user = db_driver.find_user_by_external_id(
                        org_id=org_id,
                        crm_type=connector_type,
                        external_user_id=external_owner_id,
                    )
                    
                    if not lia_user:
                        logger.debug(
                            f"Skipping {entity_type} {record_id}: "
                            f"no LIA user mapped to external ID {external_owner_id}"
                        )
                        skipped_count += 1
                        continue
                    
                    if dry_run:
                        logger.info(
                            f"[DRY RUN] Would assign {entity_type} {record_id} to {lia_user.email}"
                        )
                        assigned_count += 1
                    else:
                        # Assign ownership
                        ownership = db_driver.assign_entity_to_user(
                            user_id=lia_user.id,
                            org_id=org_id,
                            entity_type=entity_type,
                            external_entity_id=record_id,
                        )
                        logger.debug(f"Assigned {entity_type} {record_id} to {lia_user.email}")
                        assigned_count += 1
                
                logger.info("=" * 60)
                logger.info(f"Sync complete:")
                logger.info(f"  Total records: {len(records)}")
                logger.info(f"  Assigned: {assigned_count}")
                logger.info(f"  Skipped: {skipped_count}")
                if dry_run:
                    logger.info("  (DRY RUN - no changes committed)")
                
        except Exception as e:
            logger.error(f"Failed to sync ownership: {e}", exc_info=True)


def main():
    parser = argparse.ArgumentParser(
        description="Sync external DB record ownership to LIA user_entity_ownership table (auto-detects owner column)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Sync patients owned by doctors (dry run first to check)
  python sync_ownership.py --org-id abc-123 --entity-type patient --dry-run
  
  # Actually perform the sync
  python sync_ownership.py --org-id abc-123 --entity-type patient
  
  # Sync contacts (auto-detects assignee column)
  python sync_ownership.py --org-id abc-123 --entity-type contact
  
Prerequisites:
  1. Create external_user_mapping entries first (map LIA users to external DB user IDs)
  2. Ensure schema_mappings exist for the entity_type (run Lia once to auto-map)
  3. LLM will auto-detect owner/assignment column (no manual specification needed)
        """,
    )
    
    parser.add_argument("--org-id", required=True, help="Organization UUID")
    parser.add_argument("--entity-type", required=True, help="Entity type to sync (e.g., patient, contact, deal)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without committing")
    
    args = parser.parse_args()
    
    asyncio.run(sync_ownership_for_entity(
        org_id=args.org_id,
        entity_type=args.entity_type,
        dry_run=args.dry_run,
    ))


if __name__ == "__main__":
    main()
