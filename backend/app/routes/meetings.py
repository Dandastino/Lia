from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..services.data_manager import DataManager


meetings_bp = Blueprint("meetings", __name__)


@meetings_bp.route("/meetings", methods=["GET"])
@jwt_required()
def list_meetings():
    try:
        user_id = get_jwt_identity()
        limit = int(request.args.get("limit", 20))

        dm = DataManager.from_user_id(user_id)
        meetings = dm.get_meeting_history(
            user_id=user_id,
            filters={"limit": limit, "user_only": False},
        )
        return jsonify({"meetings": meetings}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@meetings_bp.route("/meetings", methods=["POST"])
@jwt_required()
def create_meeting():
    try:
        user_id = get_jwt_identity()
        data = request.get_json() or {}

        summary = data.get("summary")
        if not summary:
            return jsonify({"error": "summary is required"}), 400

        payload = {
            "title": data.get("title"),
            "summary": summary,
            "participants": data.get("participants") or [],
            "metadata": data.get("metadata") or {},
        }

        dm = DataManager.from_user_id(user_id)
        meeting = dm.save_meeting(user_id=user_id, payload=payload)
        return jsonify({"meeting": meeting}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500
