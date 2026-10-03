from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..extensions import db
from ..models import Organization, User
from ..security import (
    mask_connector_config,
    merge_connector_config,
    server_error,
    validate_connector_config,
)

organizations_bp = Blueprint("organizations", __name__)

_PRIVILEGED_ROLES = ("admin", "owner")


def _org_payload(org: Organization, include_config: bool = False) -> dict:
    payload = {
        "id": str(org.id),
        "name": org.name,
        "industry": org.industry,
        "connector_type": org.connector_type,
    }
    if include_config:
        # Secrets are never returned to clients; they are masked.
        payload["connector_config"] = mask_connector_config(org.connector_config)
    return payload


@organizations_bp.route("/organizations", methods=["GET"])
@jwt_required()
def list_organizations():
    """List organizations visible to the caller (admins: all, others: their own)."""
    try:
        user = db.session.get(User, get_jwt_identity())
        if not user:
            return jsonify({"error": "User not found"}), 404

        if user.role in _PRIVILEGED_ROLES:
            orgs = Organization.query.all()
        else:
            orgs = [user.organization] if user.organization else []

        return jsonify(
            {
                "message": "Organizations retrieved successfully",
                "organizations": [_org_payload(org) for org in orgs],
            }
        ), 200
    except Exception as e:
        return server_error(e)


@organizations_bp.route("/organizations/<org_id>", methods=["GET"])
@jwt_required()
def get_organization(org_id):
    """Get organization details (members of that organization and admins only)."""
    try:
        user = db.session.get(User, get_jwt_identity())
        if not user:
            return jsonify({"error": "User not found"}), 404

        is_member = str(user.org_id) == str(org_id)
        if not is_member and user.role not in _PRIVILEGED_ROLES:
            # Same response as a missing org: do not reveal which IDs exist.
            return jsonify({"error": "Organization not found"}), 404

        org = Organization.query.get(org_id)
        if not org:
            return jsonify({"error": "Organization not found"}), 404

        # Plain members never see connector configuration, not even masked.
        include_config = user.role in _PRIVILEGED_ROLES
        return jsonify({"organization": _org_payload(org, include_config)}), 200
    except Exception as e:
        return server_error(e)


@organizations_bp.route("/organizations/<org_id>/connector", methods=["PATCH"])
@jwt_required()
def update_connector(org_id):
    try:
        user = db.session.get(User, get_jwt_identity())
        if not user:
            return jsonify({"error": "User not found"}), 404

        if str(user.org_id) != str(org_id):
            return jsonify({"error": "You can only modify your own organization"}), 403
        if user.role not in _PRIVILEGED_ROLES:
            return jsonify({"error": "Insufficient permissions"}), 403

        data = request.get_json(silent=True) or {}
        connector_type = data.get("connector_type")
        connector_config = data.get("connector_config")

        if not connector_type:
            return jsonify({"error": "connector_type is required"}), 400

        error = validate_connector_config(
            connector_type,
            connector_config,
            block_private_hosts=current_app.config.get("BLOCK_PRIVATE_CONNECTOR_HOSTS", False),
        )
        if error:
            return jsonify({"error": error}), 400

        org = Organization.query.get(org_id)
        if not org:
            return jsonify({"error": "Organization not found"}), 404

        org.connector_type = connector_type.lower()
        # Fields echoed back as "********" keep their stored value.
        org.connector_config = merge_connector_config(org.connector_config, connector_config or {})
        db.session.add(org)
        db.session.commit()

        return jsonify(
            {
                "message": "Connector updated successfully",
                "organization": _org_payload(org, include_config=True),
            }
        ), 200
    except Exception as e:
        db.session.rollback()
        return server_error(e)
