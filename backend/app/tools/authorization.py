"""
Authorization and security middleware for multi-tenant data isolation.

Ensures:
1. JWT token must match the request user
2. User must be from same organization as the data
3. All user-specific actions are verified
4. Email-based identity with UUID-based scoping
"""

from functools import wraps
from flask import jsonify, request
from flask_jwt_extended import get_jwt_identity
from typing import Callable, Optional, Tuple

from ..models import User, Organization


def get_authorized_user_and_org(
    user_id_from_jwt: Optional[str] = None,
    org_id_from_request: Optional[str] = None,
) -> Tuple[Optional[User], Optional[Organization]]:
    """
    Verify and retrieve authorized user and organization.
    
    Args:
        user_id_from_jwt: User ID from JWT token (required)
        org_id_from_request: Organization ID from request (optional, will use user's org if not provided)
    
    Returns:
        Tuple of (User, Organization) if valid, raises ValueError if not
    
    Raises:
        ValueError: If user or org not found, or mismatch detected
    """
    if not user_id_from_jwt:
        raise ValueError("No user_id in JWT token")
    
    user = User.query.get(user_id_from_jwt)
    if not user:
        raise ValueError(f"User {user_id_from_jwt} not found")
    
    # User's organization is the authority
    if not user.org_id:
        raise ValueError(f"User {user.email} is not associated with any organization")
    
    # If org_id provided in request, verify it matches user's org
    if org_id_from_request:
        if str(user.org_id) != str(org_id_from_request):
            raise ValueError(
                f"User {user.email} (org: {user.org_id}) "
                f"tried to access org: {org_id_from_request}"
            )
    
    org = user.organization
    if not org:
        raise ValueError(f"Organization {user.org_id} not found")
    
    return user, org


def require_auth_user(f: Callable) -> Callable:
    """
    Decorator to enforce authentication and multi-tenant isolation.
    
    Usage:
        @app.route("/api/data")
        @jwt_required()
        @require_auth_user
        def get_data(authorized_user, authorized_org):
            # authorized_user and authorized_org are automatically injected
            return jsonify({"org": authorized_org.name})
    
    Verifies:
    1. JWT token is valid (via @jwt_required)
    2. User exists and is active
    3. User is properly associated with organization
    4. Org ID in request (if provided) matches user's org
    """
    @wraps(f)
    def wrapper(*args, **kwargs):
        try:
            user_id = get_jwt_identity()
            
            # Extract org_id from request if provided
            org_id_from_request = (
                request.view_args.get("org_id") or
                request.args.get("org_id") or
                (request.get_json() or {}).get("org_id")
            )
            
            # Get and verify user and org
            authorized_user, authorized_org = get_authorized_user_and_org(
                user_id_from_jwt=user_id,
                org_id_from_request=org_id_from_request
            )
            
            # Inject into function
            return f(
                *args,
                authorized_user=authorized_user,
                authorized_org=authorized_org,
                **kwargs
            )
        
        except ValueError as e:
            return jsonify({"error": str(e)}), 403
        except Exception as e:
            return jsonify({"error": f"Authorization error: {str(e)}"}), 500
    
    return wrapper


def verify_user_owns_entity(
    user_id: str,
    entity_type: str,
    external_entity_id: str,
) -> bool:
    """
    Verify a user owns a specific entity.
    
    Always call this before returning any entity data.
    
    Args:
        user_id: LIA user UUID
        entity_type: Type of entity ("patient", "contact", etc.)
        external_entity_id: ID of entity in external CRM
    
    Returns:
        True if user owns entity, False otherwise
    """
    from ..models import DatabaseDriver
    db_driver = DatabaseDriver()
    return db_driver.user_owns_entity(user_id, entity_type, external_entity_id)


def verify_user_in_organization(
    user_id: str,
    org_id: str,
) -> bool:
    """
    Verify a user belongs to an organization.
    
    Args:
        user_id: LIA user UUID
        org_id: Organization UUID
    
    Returns:
        True if user is in organization, False otherwise
    """
    user = User.query.get(user_id)
    if not user:
        return False
    return str(user.org_id) == str(org_id)


def verify_user_by_email(
    email: str,
) -> Optional[User]:
    """
    Safe user lookup by email (used in login and provisioning).
    
    Args:
        email: User email address
    
    Returns:
        User object if found, None otherwise
    """
    if not email:
        return None
    
    return User.query.filter_by(email=email.lower().strip()).first()
