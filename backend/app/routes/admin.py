from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..extensions import db
from ..models import Organization, User

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
