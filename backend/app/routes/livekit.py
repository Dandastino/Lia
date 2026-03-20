import os
import uuid
from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from livekit import api

from ..models import User


livekit_bp = Blueprint("livekit", __name__)


def generate_room_name() -> str:
    return "room-" + str(uuid.uuid4())[:8]


@livekit_bp.route("/getToken", methods=["GET"])
@jwt_required()
def get_token():
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        if not user:
            return jsonify({"error": "User not found"}), 404

        name = request.args.get("name", user.email or str(user.id))
        room = request.args.get("room") or generate_room_name()

        token = (
            api.AccessToken(
                os.getenv("LIVEKIT_API_KEY"),
                os.getenv("LIVEKIT_API_SECRET"),
            )
            .with_identity(f"User_{user.id}")
            .with_name(name)
            .with_grants(
                api.VideoGrants(
                    room_join=True,
                    room=room,
                    can_publish=True,
                    can_subscribe=True,
                )
            )
        )

        return jsonify(
            {
                "token": token.to_jwt(),
                "room": room,
                "url": os.getenv("LIVEKIT_URL"),
            }
        ), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
