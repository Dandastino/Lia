from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..services.data_manager import DataManager
from ..tools.authorization import require_auth_user


meetings_bp = Blueprint("meetings", __name__)


@meetings_bp.route("/meetings", methods=["GET"])
@jwt_required()
@require_auth_user
def list_meetings(authorized_user, authorized_org):
    """
    Get meeting history for the authenticated user.
    
    Returns only meetings created by or assigned to this user.
    Data is automatically filtered by user ownership and organization.
    """
    try:
        user_id = str(authorized_user.id)
        limit = int(request.args.get("limit", 20))

        dm = DataManager.from_user_id(user_id)
        meetings = dm.get_meeting_history(
            user_id=user_id,
            filters={"limit": limit},
        )
        return jsonify({
            "meetings": meetings,
            "org": authorized_org.name,
            "user_email": authorized_user.email,
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@meetings_bp.route("/meetings", methods=["POST"])
@jwt_required()
@require_auth_user
def create_meeting(authorized_user, authorized_org):
    """
    Create a new meeting for the authenticated user.
    
    Request body:
    {
        "title": "Meeting title",
        "summary": "Meeting summary",
        "participants": ["email1@org.com", "email2@org.com"],
        "metadata": {}
    }
    """
    try:
        user_id = str(authorized_user.id)
        data = request.get_json() or {}

        summary = data.get("summary")
        if not summary:
            return jsonify({"error": "summary is required"}), 400

        payload = {
            "title": data.get("title") or "Meeting",
            "summary": summary,
            "participants": data.get("participants") or [],
            "metadata": data.get("metadata") or {},
        }

        dm = DataManager.from_user_id(user_id)
        meeting = dm.save_meeting(user_id=user_id, payload=payload)
        
        return jsonify({
            "message": "Meeting created successfully",
            "meeting": meeting,
            "org": authorized_org.name,
        }), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500
