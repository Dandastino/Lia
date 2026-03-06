"""Generic CRUD routes for managing entities across different external systems.

Supports reading, creating, updating, and deleting records in external databases
while maintaining multi-tenant isolation via user_entity_ownership table.
"""

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
import logging

from ..models import Organization, User, DatabaseDriver
from ..services.data_manager import DataManager

logger = logging.getLogger(__name__)

entities_bp = Blueprint("entities", __name__)


def get_authorized_context():
    """Extract and validate JWT claims for multi-tenant operations."""
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    
    if not user:
        return None, None, {"error": "User not found"}, 401
    
    org = Organization.query.get(user.org_id)
    if not org:
        return None, None, {"error": "Organization not found"}, 401
    
    return user, org, None, None


@entities_bp.route("/entities/<entity_type>", methods=["GET"])
@jwt_required()
def list_entities(entity_type: str):
    """List all entities of a given type owned by the current user.
    
    Query parameters:
    - limit: Number of records to return (default: 20)
    - offset: For pagination (default: 0)
    
    Returns:
        List of entities owned by the user
    """
    user, org, error, status = get_authorized_context()
    if error:
        return jsonify(error), status
    
    try:
        # Create DataManager for the organization
        dm = DataManager.from_user_id(user_id=str(user.id))
        
        # Get limit and offset from query params
        limit = min(int(request.args.get("limit", 20)), 100)  # Max 100
        offset = int(request.args.get("offset", 0))
        
        # Get user's owned entity IDs for this entity type
        db_driver = DatabaseDriver()
        ownerships = db_driver.get_user_owned_entities_safe(
            user_id=user.id,
            entity_type=entity_type
        )
        
        # Extract IDs
        owned_ids = [o["external_entity_id"] for o in ownerships]
        
        if not owned_ids:
            return jsonify([]), 200
        
        # Read entities from external system with ownership filter
        import asyncio
        entities = asyncio.run(dm.driver.read_entities(
            entity_type=entity_type,
            filters={"owned_entity_ids": owned_ids, "limit": limit, "offset": offset}
        ))
        
        return jsonify(entities), 200
    
    except Exception as e:
        logger.error(f"Failed to list {entity_type}: {e}")
        return jsonify({"error": str(e)}), 500


@entities_bp.route("/entities/<entity_type>", methods=["POST"])
@jwt_required()
def create_entity(entity_type: str):
    """Create a new entity in the organization's external system.
    
    The created entity is automatically assigned to the current user.
    
    Request body:
        - title: Entity title/name
        - summary: Entity description/summary
        - participants: People/attendees
        - Any other fields supported by the external system
    
    Returns:
        Created entity with ID
    """
    user, org, error, status = get_authorized_context()
    if error:
        return jsonify(error), status
    
    try:
        payload = request.get_json()
        if not payload:
            return jsonify({"error": "Request body is empty"}), 400
        
        # Create DataManager for the organization
        dm = DataManager.from_user_id(user_id=str(user.id))
        
        # Create entity (auto-assigns ownership to user)
        import asyncio
        result = asyncio.run(dm.create_entity(
            entity_type=entity_type,
            payload=payload
        ))
        
        logger.info(f"Created {entity_type} {result.get('id')} for user {user.email}")
        return jsonify(result), 201
    
    except ValueError as e:
        logger.error(f"Validation error creating {entity_type}: {e}")
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error(f"Failed to create {entity_type}: {e}")
        return jsonify({"error": str(e)}), 500


@entities_bp.route("/entities/<entity_type>/<entity_id>", methods=["GET"])
@jwt_required()
def get_entity(entity_type: str, entity_id: str):
    """Get a single entity (must be owned by the current user).
    
    Returns 403 if user doesn't own the entity.
    """
    user, org, error, status = get_authorized_context()
    if error:
        return jsonify(error), status
    
    try:
        # Verify user owns this entity
        db_driver = DatabaseDriver()
        ownership = db_driver.get_user_owned_entities_safe(
            user_id=user.id,
            entity_type=entity_type
        )
        
        entity_ids = [o["external_entity_id"] for o in ownership]
        if entity_id not in entity_ids:
            return jsonify({"error": "Access denied - you don't own this entity"}), 403
        
        # Create DataManager and read single entity
        dm = DataManager.from_user_id(user_id=str(user.id))
        
        import asyncio
        entities = asyncio.run(dm.driver.read_entities(
            entity_type=entity_type,
            filters={"owned_entity_ids": [entity_id], "limit": 1}
        ))
        
        if not entities:
            return jsonify({"error": "Entity not found"}), 404
        
        return jsonify(entities[0]), 200
    
    except Exception as e:
        logger.error(f"Failed to get {entity_type} {entity_id}: {e}")
        return jsonify({"error": str(e)}), 500


@entities_bp.route("/entities/<entity_type>/<entity_id>", methods=["PUT"])
@jwt_required()
def update_entity(entity_type: str, entity_id: str):
    """Update an entity (must be owned by the current user).
    
    Returns 403 if user doesn't own the entity.
    """
    user, org, error, status = get_authorized_context()
    if error:
        return jsonify(error), status
    
    try:
        # Verify user owns this entity
        db_driver = DatabaseDriver()
        ownership = db_driver.get_user_owned_entities_safe(
            user_id=user.id,
            entity_type=entity_type
        )
        
        entity_ids = [o["external_entity_id"] for o in ownership]
        if entity_id not in entity_ids:
            return jsonify({"error": "Access denied - you don't own this entity"}), 403
        
        payload = request.get_json()
        if not payload:
            return jsonify({"error": "Request body is empty"}), 400
        
        # Create DataManager and update entity
        dm = DataManager.from_user_id(user_id=str(user.id))
        
        import asyncio
        result = asyncio.run(dm.driver.update_entity(
            entity_type=entity_type,
            entity_id=entity_id,
            updates=payload
        ))
        
        logger.info(f"Updated {entity_type} {entity_id} for user {user.email}")
        return jsonify(result), 200
    
    except Exception as e:
        logger.error(f"Failed to update {entity_type} {entity_id}: {e}")
        return jsonify({"error": str(e)}), 500


@entities_bp.route("/entities/<entity_type>/<entity_id>", methods=["DELETE"])
@jwt_required()
def delete_entity(entity_type: str, entity_id: str):
    """Delete an entity (must be owned by the current user).
    
    Returns 403 if user doesn't own the entity.
    """
    user, org, error, status = get_authorized_context()
    if error:
        return jsonify(error), status
    
    try:
        # Verify user owns this entity
        db_driver = DatabaseDriver()
        ownership = db_driver.get_user_owned_entities_safe(
            user_id=user.id,
            entity_type=entity_type
        )
        
        entity_ids = [o["external_entity_id"] for o in ownership]
        if entity_id not in entity_ids:
            return jsonify({"error": "Access denied - you don't own this entity"}), 403
        
        # Create DataManager and delete entity
        dm = DataManager.from_user_id(user_id=str(user.id))
        
        import asyncio
        success = asyncio.run(dm.driver.delete_entity(
            entity_type=entity_type,
            entity_id=entity_id
        ))
        
        if success:
            # Also remove ownership record
            db_driver.remove_entity_from_user_safe(
                user_id=user.id,
                entity_type=entity_type,
                external_entity_id=entity_id
            )
            logger.info(f"Deleted {entity_type} {entity_id} for user {user.email}")
            return jsonify({"success": True}), 200
        else:
            return jsonify({"error": "Failed to delete entity"}), 500
    
    except Exception as e:
        logger.error(f"Failed to delete {entity_type} {entity_id}: {e}")
        return jsonify({"error": str(e)}), 500
