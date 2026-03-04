from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..extensions import db
from ..models import Organization, User, UserEntityOwnership, ExternalUserMapping, DatabaseDriver
from ..services.crm_mapper import CRMEntityMapper

admin_bp = Blueprint("admin", __name__)


def check_admin(user):
    """Check if user has admin role."""
    if user.role not in ("admin", "owner"):
        return False
    return True


@admin_bp.route("/admin/dashboard", methods=["GET"])
@jwt_required()
def admin_dashboard():
    """Get admin dashboard with statistics."""
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)

        if not user or not check_admin(user):
            return jsonify({"error": "Unauthorized"}), 403

        total_organizations = Organization.query.count()
        total_users = User.query.count()
        organizations = Organization.query.all()
        users = User.query.all()

        return jsonify(
            {
                "stats": {
                    "total_organizations": total_organizations,
                    "total_users": total_users,
                },
                "organizations": [
                    {
                        "id": str(org.id),
                        "name": org.name,
                        "industry": org.industry,
                        "connector_type": org.connector_type,
                        "user_count": len(org.users),
                    }
                    for org in organizations
                ],
                "users": [
                    {
                        "id": str(user.id),
                        "email": user.email,
                        "role": user.role,
                        "org_id": str(user.org_id) if user.org_id else None,
                        "org_name": user.organization.name if user.organization else None,
                        "created_at": user.created_at.isoformat() if user.created_at else None,
                    }
                    for user in users
                ],
            }
        ), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@admin_bp.route("/admin/organizations", methods=["POST"])
@jwt_required()
def admin_create_organization():
    """Create a new organization (admin only)."""
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)

        if not user or not check_admin(user):
            return jsonify({"error": "Unauthorized"}), 403

        data = request.get_json() or {}

        if not data or "name" not in data:
            return jsonify({"error": "Missing required field: name"}), 400

        org = Organization(
            name=data["name"],
            industry=data.get("industry"),
            connector_type=data.get("connector_type", "internal"),
            connector_config=data.get("connector_config", {}),
        )
        db.session.add(org)
        db.session.commit()

        return jsonify(
            {
                "message": "Organization created successfully",
                "organization": {
                    "id": str(org.id),
                    "name": org.name,
                    "industry": org.industry,
                    "connector_type": org.connector_type,
                },
            }
        ), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@admin_bp.route("/admin/users", methods=["POST"])
@jwt_required()
def admin_create_user():
    """Create a new user (admin only)."""
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)

        if not user or not check_admin(user):
            return jsonify({"error": "Unauthorized"}), 403

        data = request.get_json() or {}

        if not all(k in data for k in ["email", "password"]):
            return jsonify({"error": "Missing required fields: email, password"}), 400

        # Check if user already exists
        existing_user = User.query.filter_by(email=data["email"]).first()
        if existing_user:
            return jsonify({"error": "Email already registered"}), 409

        org_id = data.get("org_id")
        if org_id:
            org = Organization.query.get(org_id)
            if not org:
                return jsonify({"error": "Organization not found"}), 404
        else:
            return jsonify({"error": "org_id is required"}), 400

        new_user = User(
            email=data["email"],
            org_id=org_id,
            role=data.get("role", "user"),
        )
        new_user.set_password(data["password"])
        db.session.add(new_user)
        db.session.commit()

        return jsonify(
            {
                "message": "User created successfully",
                "user": {
                    "id": str(new_user.id),
                    "email": new_user.email,
                    "org_id": str(new_user.org_id),
                    "role": new_user.role,
                },
            }
        ), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@admin_bp.route("/admin/users/<user_id>", methods=["PUT"])
@jwt_required()
def admin_update_user(user_id):
    """Update user details (admin only)."""
    try:
        admin_id = get_jwt_identity()
        admin = User.query.get(admin_id)

        if not admin or not check_admin(admin):
            return jsonify({"error": "Unauthorized"}), 403

        target_user = User.query.get(user_id)
        if not target_user:
            return jsonify({"error": "User not found"}), 404

        data = request.get_json() or {}

        # Update email if provided
        if "email" in data:
            # Check if email already exists
            existing_user = User.query.filter_by(email=data["email"]).first()
            if existing_user and existing_user.id != target_user.id:
                return jsonify({"error": "Email already registered"}), 409
            target_user.email = data["email"]

        # Update organization if provided
        if "org_id" in data:
            if data["org_id"]:  # Only validate if org_id is not null
                org = Organization.query.get(data["org_id"])
                if not org:
                    return jsonify({"error": "Organization not found"}), 404
                target_user.org_id = data["org_id"]
            else:
                target_user.org_id = None

        # Update role if provided
        if "role" in data:
            target_user.role = data["role"]

        db.session.add(target_user)
        db.session.commit()

        return jsonify(
            {
                "message": "User updated successfully",
                "user": {
                    "id": str(target_user.id),
                    "email": target_user.email,
                    "org_id": str(target_user.org_id) if target_user.org_id else None,
                    "role": target_user.role,
                },
            }
        ), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@admin_bp.route("/admin/organizations/<org_id>", methods=["PUT"])
@jwt_required()
def admin_update_organization(org_id):
    """Update organization details (admin only)."""
    try:
        admin_id = get_jwt_identity()
        admin = User.query.get(admin_id)

        if not admin or not check_admin(admin):
            return jsonify({"error": "Unauthorized"}), 403

        org = Organization.query.get(org_id)
        if not org:
            return jsonify({"error": "Organization not found"}), 404

        data = request.get_json() or {}

        # Update name if provided
        if "name" in data:
            org.name = data["name"]

        # Update industry if provided
        if "industry" in data:
            org.industry = data["industry"]

        # Update connector type if provided
        if "connector_type" in data:
            org.connector_type = data["connector_type"]

        # Update connector config if provided
        if "connector_config" in data:
            org.connector_config = data["connector_config"] or {}

        db.session.add(org)
        db.session.commit()

        return jsonify(
            {
                "message": "Organization updated successfully",
                "organization": {
                    "id": str(org.id),
                    "name": org.name,
                    "industry": org.industry,
                    "connector_type": org.connector_type,
                    "connector_config": org.connector_config,
                },
            }
        ), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@admin_bp.route("/admin/users/<user_id>", methods=["DELETE"])
@jwt_required()
def admin_delete_user(user_id):
    """Delete a user (admin only)."""
    try:
        admin_id = get_jwt_identity()
        admin = User.query.get(admin_id)

        if not admin or not check_admin(admin):
            return jsonify({"error": "Unauthorized"}), 403

        target_user = User.query.get(user_id)
        if not target_user:
            return jsonify({"error": "User not found"}), 404

        email = target_user.email
        db.session.delete(target_user)
        db.session.commit()

        return jsonify(
            {"message": f"User deleted successfully: {email}"}
        ), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@admin_bp.route("/admin/organizations/<org_id>", methods=["DELETE"])
@jwt_required()
def admin_delete_organization(org_id):
    """Delete an organization (admin only)."""
    try:
        admin_id = get_jwt_identity()
        admin = User.query.get(admin_id)

        if not admin or not check_admin(admin):
            return jsonify({"error": "Unauthorized"}), 403

        org = Organization.query.get(org_id)
        if not org:
            return jsonify({"error": "Organization not found"}), 404

        org_name = org.name
        db.session.delete(org)
        db.session.commit()

        return jsonify(
            {"message": f"Organization deleted successfully: {org_name}"}
        ), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@admin_bp.route("/admin/users/<user_id>/reset-password", methods=["PUT"])
@jwt_required()
def admin_reset_user_password(user_id):
    """Reset a user's password (admin only)."""
    try:
        from werkzeug.security import generate_password_hash

        admin_id = get_jwt_identity()
        admin = User.query.get(admin_id)

        if not admin or not check_admin(admin):
            return jsonify({"error": "Unauthorized"}), 403

        target_user = User.query.get(user_id)
        if not target_user:
            return jsonify({"error": "User not found"}), 404

        data = request.get_json() or {}
        new_password = data.get("password")

        if not new_password:
            return jsonify({"error": "Password is required"}), 400

        if len(new_password) < 6:
            return jsonify({"error": "Password must be at least 6 characters"}), 400

        target_user.password_hash = generate_password_hash(new_password)
        db.session.add(target_user)
        db.session.commit()

        return jsonify(
            {
                "message": f"Password reset successfully for {target_user.email}",
                "user_id": str(target_user.id),
            }
        ), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

# ===== Entity Ownership Management (Data Isolation) =====


@admin_bp.route("/admin/users/<user_id>/entity-ownership", methods=["GET"])
@jwt_required()
def admin_get_user_entity_ownership(user_id):
    """Get all entities owned by a user (admin only)."""
    try:
        admin_id = get_jwt_identity()
        admin = User.query.get(admin_id)

        if not admin or not check_admin(admin):
            return jsonify({"error": "Unauthorized"}), 403

        user = User.query.get(user_id)
        if not user:
            return jsonify({"error": "User not found"}), 404

        entity_type = request.args.get("entity_type")

        db_driver = DatabaseDriver()
        ownerships = db_driver.get_user_owned_entities_safe(user.id, entity_type)

        return jsonify(
            {
                "user_id": str(user.id),
                "user_email": user.email,
                "entity_type_filter": entity_type,
                "total_entities": len(ownerships),
                "entities": ownerships,
            }
        ), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@admin_bp.route("/admin/users/<user_id>/entity-ownership", methods=["POST"])
@jwt_required()
def admin_assign_entity_to_user(user_id):
    """Assign an entity to a user (admin only)."""
    try:
        admin_id = get_jwt_identity()
        admin = User.query.get(admin_id)

        if not admin or not check_admin(admin):
            return jsonify({"error": "Unauthorized"}), 403

        user = User.query.get(user_id)
        if not user:
            return jsonify({"error": "User not found"}), 404

        data = request.get_json() or {}

        if not data.get("entity_type") or not data.get("external_entity_id"):
            return jsonify(
                {"error": "Missing required fields: entity_type, external_entity_id"}
            ), 400

        db_driver = DatabaseDriver()
        ownership = db_driver.assign_entity_to_user(
            user_id=user.id,
            org_id=user.org_id,
            entity_type=data["entity_type"],
            external_entity_id=str(data["external_entity_id"]),
        )

        if not ownership:
            return jsonify(
                {"error": f"Entity already assigned to user or database error"}
            ), 400

        return jsonify(
            {
                "message": "Entity assigned successfully",
                "ownership": {
                    "id": str(ownership.id),
                    "user_id": str(ownership.user_id),
                    "entity_type": ownership.entity_type,
                    "external_entity_id": ownership.external_entity_id,
                    "created_at": ownership.created_at.isoformat() if ownership.created_at else None,
                },
            }
        ), 201

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@admin_bp.route("/admin/users/<user_id>/entity-ownership/<entity_type>/<external_entity_id>", methods=["DELETE"])
@jwt_required()
def admin_remove_entity_from_user(user_id, entity_type, external_entity_id):
    """Remove entity assignment from a user (admin only)."""
    try:
        admin_id = get_jwt_identity()
        admin = User.query.get(admin_id)

        if not admin or not check_admin(admin):
            return jsonify({"error": "Unauthorized"}), 403

        user = User.query.get(user_id)
        if not user:
            return jsonify({"error": "User not found"}), 404

        db_driver = DatabaseDriver()
        removed = db_driver.remove_entity_from_user_safe(user.id, entity_type, external_entity_id)
        
        if not removed:
            return jsonify({"error": "Entity ownership not found or could not be removed"}), 404

        return jsonify(
            {
                "message": "Entity ownership removed successfully",
                "user_id": str(user.id),
                "entity_type": entity_type,
                "external_entity_id": external_entity_id,
            }
        ), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@admin_bp.route("/admin/entity-ownership/bulk", methods=["POST"])
@jwt_required()
def admin_bulk_assign_entities():
    """Bulk assign entities to users (admin only).
    
    Useful for importing large numbers of doctor-patient relationships.
    
    Request body:
    {
        "assignments": [
            {
                "user_id": "user-uuid",
                "entity_type": "patient",
                "external_entity_id": "123"
            },
            ...
        ]
    }
    """
    try:
        admin_id = get_jwt_identity()
        admin = User.query.get(admin_id)

        if not admin or not check_admin(admin):
            return jsonify({"error": "Unauthorized"}), 403

        data = request.get_json() or {}
        assignments = data.get("assignments", [])

        if not isinstance(assignments, list) or not assignments:
            return jsonify({"error": "assignments must be a non-empty list"}), 400

        db_driver = DatabaseDriver()
        successful = 0
        failed = 0
        errors = []

        for assignment in assignments:
            try:
                user_id = assignment.get("user_id")
                entity_type = assignment.get("entity_type")
                external_entity_id = assignment.get("external_entity_id")

                if not all([user_id, entity_type, external_entity_id]):
                    errors.append(f"Skipped assignment: missing required fields")
                    failed += 1
                    continue

                user = User.query.get(user_id)
                if not user:
                    errors.append(f"Skipped {entity_type}/{external_entity_id}: user not found")
                    failed += 1
                    continue

                ownership = db_driver.assign_entity_to_user(
                    user_id=user.id,
                    org_id=user.org_id,
                    entity_type=entity_type,
                    external_entity_id=str(external_entity_id),
                )

                if ownership:
                    successful += 1
                else:
                    errors.append(f"Failed {entity_type}/{external_entity_id}: duplicate or error")
                    failed += 1

            except Exception as e:
                errors.append(f"Error processing assignment: {str(e)}")
                failed += 1

        return jsonify(
            {
                "message": f"Bulk assignment complete: {successful} succeeded, {failed} failed",
                "successful": successful,
                "failed": failed,
                "errors": errors if errors else None,
            }
        ), 200 if failed == 0 else 207

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ============= External User Mapping Management =============

@admin_bp.route("/admin/external-user-mapping", methods=["POST"])
@jwt_required()
def create_external_user_mapping():
    """
    Create or update a mapping between a LIA user and their external CRM identity.
    
    Request body:
    {
        "user_id": "abc-123",  # LIA user UUID
        "org_id": "org-456",   # Organization UUID
        "crm_type": "salesforce",  # Type of CRM
        "external_user_id": "SF-999",  # Doctor's ID in that CRM
        "external_email": "andrea@test.com"  # Optional
    }
    """
    try:
        admin_id = get_jwt_identity()
        admin = User.query.get(admin_id)
        
        if not admin or not check_admin(admin):
            return jsonify({"error": "Unauthorized"}), 403
        
        data = request.get_json() or {}
        user_id = data.get("user_id")
        org_id = data.get("org_id")
        crm_type = data.get("crm_type")
        external_user_id = data.get("external_user_id")
        external_email = data.get("external_email")
        
        if not all([user_id, org_id, crm_type, external_user_id]):
            return jsonify({
                "error": "Missing required fields: user_id, org_id, crm_type, external_user_id"
            }), 400
        
        # Verify user exists and belongs to the org
        user = User.query.get(user_id)
        if not user or str(user.org_id) != str(org_id):
            return jsonify({"error": "User not found in organization"}), 404
        
        # Create mapping
        mapper = CRMEntityMapper()
        success = mapper.register_doctor_to_crm(
            user_id=user_id,
            org_id=org_id,
            crm_type=crm_type.lower(),
            external_user_id=external_user_id,
            external_email=external_email,
        )
        
        if success:
            return jsonify({
                "message": "External user mapping created successfully",
                "user_id": str(user_id),
                "crm_type": crm_type.lower(),
                "external_user_id": str(external_user_id),
            }), 201
        else:
            return jsonify({"error": "Failed to create mapping"}), 500
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@admin_bp.route("/admin/external-user-mapping/<user_id>", methods=["GET"])
@jwt_required()
def get_external_user_mappings(user_id):
    """
    Get all external CRM mappings for a specific user.
    
    Returns a dictionary like:
    {
        "salesforce": "SF-999",
        "hubspot": "HS-555",
        "dynamics": "DYN-111"
    }
    """
    try:
        admin_id = get_jwt_identity()
        admin = User.query.get(admin_id)
        
        if not admin or not check_admin(admin):
            return jsonify({"error": "Unauthorized"}), 403
        
        user = User.query.get(user_id)
        if not user:
            return jsonify({"error": "User not found"}), 404
        
        mapper = CRMEntityMapper()
        crm_profile = mapper.get_doctor_crm_profile(user_id)
        
        return jsonify({
            "user_id": str(user_id),
            "user_email": user.email,
            "org_id": str(user.org_id),
            "crm_mappings": crm_profile,
            "mapping_count": len(crm_profile),
        }), 200
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@admin_bp.route("/admin/external-user-mapping/<user_id>/<crm_type>", methods=["DELETE"])
@jwt_required()
def delete_external_user_mapping(user_id, crm_type):
    """
    Delete an external user mapping for a specific CRM system.
    """
    try:
        admin_id = get_jwt_identity()
        admin = User.query.get(admin_id)
        
        if not admin or not check_admin(admin):
            return jsonify({"error": "Unauthorized"}), 403
        
        user = User.query.get(user_id)
        if not user:
            return jsonify({"error": "User not found"}), 404
        
        mapping = ExternalUserMapping.query.filter_by(
            user_id=user_id,
            crm_type=crm_type.lower()
        ).first()
        
        if not mapping:
            return jsonify({"error": "Mapping not found"}), 404
        
        db.session.delete(mapping)
        db.session.commit()
        
        return jsonify({
            "message": f"Mapping for {crm_type} deleted successfully"
        }), 200
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@admin_bp.route("/admin/crm-users/<org_id>/<crm_type>", methods=["GET"])
@jwt_required()
def list_crm_users_in_org(org_id, crm_type):
    """
    List all CRM user mappings in an organization for a specific CRM system.
    
    Useful for admin dashboards to see which doctors have been mapped to which CRM.
    """
    try:
        admin_id = get_jwt_identity()
        admin = User.query.get(admin_id)
        
        if not admin or not check_admin(admin):
            return jsonify({"error": "Unauthorized"}), 403
        
        # Verify org exists
        org = Organization.query.get(org_id)
        if not org:
            return jsonify({"error": "Organization not found"}), 404
        
        # Get all mappings for this org and CRM type
        mappings = ExternalUserMapping.query.filter_by(
            org_id=org_id,
            crm_type=crm_type.lower()
        ).all()
        
        return jsonify({
            "org_id": str(org_id),
            "crm_type": crm_type.lower(),
            "total_mappings": len(mappings),
            "mappings": [
                {
                    "user_id": str(m.user_id),
                    "user_email": m.user.email,
                    "external_user_id": m.external_user_id,
                    "external_email": m.external_email,
                    "last_synced_at": m.last_synced_at.isoformat() if m.last_synced_at else None,
                }
                for m in mappings
            ]
        }), 200
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@admin_bp.route("/admin/external-user-mapping/bulk", methods=["POST"])
@jwt_required()
def bulk_create_external_user_mappings():
    """
    Bulk create external user mappings from CSV data.
    
    Request body:
    {
        "org_id": "org-456",
        "crm_type": "salesforce",
        "mappings": [
            {
                "lIA_user_email": "andrea@test.com",
                "external_user_id": "SF-999",
                "external_email": "andrea@test.com"
            },
            {
                "lia_user_email": "giuseppe@test.com",
                "external_user_id": "SF-888",
                "external_email": "giuseppe@test.com"
            }
        ]
    }
    """
    try:
        admin_id = get_jwt_identity()
        admin = User.query.get(admin_id)
        
        if not admin or not check_admin(admin):
            return jsonify({"error": "Unauthorized"}), 403
        
        data = request.get_json() or {}
        org_id = data.get("org_id")
        crm_type = data.get("crm_type")
        mappings = data.get("mappings", [])
        
        if not all([org_id, crm_type, mappings]):
            return jsonify({
                "error": "Missing required fields: org_id, crm_type, mappings"
            }), 400
        
        # Verify org exists
        org = Organization.query.get(org_id)
        if not org:
            return jsonify({"error": "Organization not found"}), 404
        
        db_driver = DatabaseDriver()
        mapper = CRMEntityMapper()
        successful = 0
        failed = 0
        errors = []
        
        for mapping_data in mappings:
            try:
                lia_user_email = (mapping_data.get("lia_user_email") or "").strip().lower()
                external_user_id = mapping_data.get("external_user_id")
                external_email = mapping_data.get("external_email")
                
                if not lia_user_email or not external_user_id:
                    errors.append("Missing lia_user_email or external_user_id")
                    failed += 1
                    continue
                
                # Find LIA user by email
                user = User.query.filter_by(email=lia_user_email).first()
                if not user or str(user.org_id) != str(org_id):
                    errors.append(f"LIA user {lia_user_email} not found in organization")
                    failed += 1
                    continue
                
                # Create mapping
                success = mapper.register_doctor_to_crm(
                    user_id=str(user.id),
                    org_id=org_id,
                    crm_type=crm_type.lower(),
                    external_user_id=external_user_id,
                    external_email=external_email,
                )
                
                if success:
                    successful += 1
                else:
                    errors.append(f"Failed to map {lia_user_email}")
                    failed += 1
            
            except Exception as e:
                errors.append(f"Error mapping {lia_user_email}: {str(e)}")
                failed += 1
        
        return jsonify({
            "message": f"Bulk mapping complete: {successful} succeeded, {failed} failed",
            "successful": successful,
            "failed": failed,
            "errors": errors if errors else None,
        }), 200 if failed == 0 else 207
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500