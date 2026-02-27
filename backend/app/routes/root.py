from flask import Blueprint, jsonify

root_bp = Blueprint("root", __name__)


@root_bp.route("/", methods=["GET"])
def index():
    return jsonify(
        {
            "name": "Lia Assistant API",
            "version": "1.0.0",
            "description": "Multi-tenant backend API for Lia",
            "endpoints": {
                "auth": {"register": "POST /register", "login": "POST /login"},
                "organizations": {"update_connector": "PATCH /organizations/<id>/connector"},
                "meetings": {"list": "GET /meetings", "create": "POST /meetings"},
                "livekit": {"token": "GET /getToken"},
                "health": "GET /health",
            },
        }
    ), 200
