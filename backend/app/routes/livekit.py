import os
import uuid
from datetime import timedelta

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from livekit import api

from ..extensions import db
from ..models import User
from ..security import server_error

livekit_bp = Blueprint("livekit", __name__)

_MAX_DISPLAY_NAME = 64
_TOKEN_TTL = timedelta(hours=1)


def generate_room_name() -> str:
    # Full 128-bit random suffix: rooms must not be guessable, since anyone who
    # knows a room name and holds a valid token for it could join it.
    return "room-" + uuid.uuid4().hex


@livekit_bp.route("/getToken", methods=["GET"])
@jwt_required()
def get_token():
    try:
        user = db.session.get(User, get_jwt_identity())
        if not user:
            return jsonify({"error": "User not found"}), 404

        # The room is always chosen by the server; a client-supplied "room" is ignored so
        # that a user cannot obtain a token for someone else's room.
        name = (request.args.get("name") or user.email or str(user.id)).strip()[:_MAX_DISPLAY_NAME]
        room = generate_room_name()

        token = (
            api.AccessToken(
                os.getenv("LIVEKIT_API_KEY"),
                os.getenv("LIVEKIT_API_SECRET"),
            )
            .with_identity(f"User_{user.id}")
            .with_name(name)
            .with_ttl(_TOKEN_TTL)
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
        return server_error(e)
