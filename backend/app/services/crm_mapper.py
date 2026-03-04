"""
CRM Entity Mapper - Bridges LIA internal users to external CRM identities.

This module helps synchronize doctor/user identities across multiple systems:
- LIA database (our internal system)
- Salesforce, HubSpot, Dynamics, PostgreSQL (external CRM systems)

The mapper maintains bidirectional lookups to handle data isolation properly.
"""

from typing import Optional, Dict, List
from uuid import UUID
from ..models import db, User, ExternalUserMapping, DatabaseDriver


class CRMEntityMapper:
    """Manages mapping between LIA users and external CRM entity IDs."""

    def __init__(self):
        self.db_driver = DatabaseDriver()

    def register_doctor_to_crm(
        self,
        user_id: str,
        org_id: str,
        crm_type: str,
        external_user_id: str,
        external_email: Optional[str] = None,
    ) -> bool:
        """
        Register a doctor in LIA with their CRM identity.
        
        Example:
            mapper.register_doctor_to_crm(
                user_id="abc-123",  # Andrea's LIA ID
                org_id="org-456",
                crm_type="salesforce",
                external_user_id="SF-999",  # Andrea in Salesforce
                external_email="andrea@test.com"
            )
        
        Args:
            user_id: Doctor's LIA UUID
            org_id: Organization UUID
            crm_type: Name of CRM system (salesforce, hubspot, dynamics, postgresql, etc.)
            external_user_id: Doctor's ID in that CRM system
            external_email: Doctor's email in that CRM (optional)
        
        Returns:
            True if successful, False otherwise
        """
        mapping = self.db_driver.create_external_user_mapping(
            user_id=user_id,
            org_id=org_id,
            crm_type=crm_type,
            external_user_id=external_user_id,
            external_email=external_email,
        )
        return mapping is not None

    def resolve_doctor_in_crm(
        self,
        user_id: str,
        crm_type: str,
    ) -> Optional[str]:
        """
        Given a LIA user, find their ID in a specific CRM system.
        
        Example:
            # Andrea logs in, we need to query Salesforce with her SF ID
            sf_user_id = mapper.resolve_doctor_in_crm(
                user_id="abc-123",  # Andrea's LIA ID
                crm_type="salesforce"
            )
            # Returns: "SF-999"
            # Now we can query Salesforce: SELECT * FROM doctors WHERE id = 'SF-999'
        
        Args:
            user_id: LIA user UUID
            crm_type: CRM system name
        
        Returns:
            The external user ID, or None if no mapping exists
        """
        return self.db_driver.get_external_user_id(
            user_id=user_id,
            crm_type=crm_type,
        )

    def resolve_user_from_crm(
        self,
        org_id: str,
        crm_type: str,
        external_user_id: str,
    ) -> Optional[User]:
        """
        Given a CRM user ID, find their LIA user record.
        
        Useful when processing webhooks or syncing data from external CRM.
        
        Example:
            # Salesforce webhook: "Doctor SF-999 has new patient"
            user = mapper.resolve_user_from_crm(
                org_id="org-456",
                crm_type="salesforce",
                external_user_id="SF-999"
            )
            # Returns: User object for Andrea
            # Now we know Andrea owns this patient in LIA
        
        Args:
            org_id: Organization UUID
            crm_type: CRM system name
            external_user_id: User's ID in external CRM
        
        Returns:
            User object, or None if not found
        """
        return self.db_driver.find_user_by_external_id(
            org_id=org_id,
            crm_type=crm_type,
            external_user_id=external_user_id,
        )

    def get_doctor_crm_profile(
        self,
        user_id: str,
    ) -> Dict[str, str]:
        """
        Get all CRM identities for a doctor (multi-CRM support).
        
        Example:
            profile = mapper.get_doctor_crm_profile(user_id="abc-123")
            # Returns:
            # {
            #     "salesforce": "SF-999",
            #     "hubspot": "HS-555",
            #     "dynamics": "DYN-111"
            # }
        
        Args:
            user_id: LIA user UUID
        
        Returns:
            Dictionary mapping CRM names to external user IDs
        """
        mappings = self.db_driver.get_all_external_mappings(user_id)
        return {
            mapping.crm_type: str(mapping.external_user_id)
            for mapping in mappings
        }

    def validate_mapping_exists(
        self,
        user_id: str,
        crm_type: str,
    ) -> bool:
        """
        Check if a CRM mapping exists for a user.
        
        Args:
            user_id: LIA user UUID
            crm_type: CRM system name
        
        Returns:
            True if mapping exists, False otherwise
        """
        mapping = self.db_driver.get_external_user_mapping(
            user_id=user_id,
            crm_type=crm_type,
        )
        return mapping is not None
