from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..extensions import db
from ..models import Organization, User


organizations_bp = Blueprint("organizations", __name__)


@organizations_bp.route("/organizations", methods=["GET"])
def list_organizations():
    """List all available organizations."""
    try:
        orgs = Organization.query.all()
        return jsonify(
            {
                "message": "Organizations retrieved successfully",
                "organizations": [
                    {
                        "id": str(org.id),
                        "name": org.name,
                        "industry": org.industry,
                        "connector_type": org.connector_type,
                    }
                    for org in orgs
                ],
            }
        ), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@organizations_bp.route("/organizations/<org_id>", methods=["GET"])
@jwt_required()
def get_organization(org_id):
    """Get organization details (authenticated users only)."""
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        if not user:
            return jsonify({"error": "User not found"}), 404

        org = Organization.query.get(org_id)
        if not org:
            return jsonify({"error": "Organization not found"}), 404

        return jsonify(
            {
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
        return jsonify({"error": str(e)}), 500


@organizations_bp.route("/organizations/<org_id>/connector", methods=["PATCH"])
@jwt_required()
def update_connector(org_id):
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        if not user:
            return jsonify({"error": "User not found"}), 404

        if str(user.org_id) != str(org_id):
            return jsonify({"error": "You can only modify your own organization"}), 403
        if user.role not in ("admin", "owner"):
            return jsonify({"error": "Insufficient permissions"}), 403

        data = request.get_json() or {}
        connector_type = data.get("connector_type")
        connector_config = data.get("connector_config")

        if not connector_type:
            return jsonify({"error": "connector_type is required"}), 400

        org = Organization.query.get(org_id)
        if not org:
            return jsonify({"error": "Organization not found"}), 404

        org.connector_type = connector_type
        org.connector_config = connector_config or {}
        db.session.add(org)
        db.session.commit()

        return jsonify(
            {
                "message": "Connector updated successfully",
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
        return jsonify({"error": str(e)}), 500
