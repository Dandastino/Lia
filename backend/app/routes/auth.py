from flask import Blueprint, jsonify, request
from flask_jwt_extended import create_access_token
from sqlalchemy.exc import SQLAlchemyError

from ..models import DatabaseDriver


auth_bp = Blueprint("auth", __name__)


db_driver = DatabaseDriver()


# NOTE: User registration is only available via CLI/development tools
# Accounts must be created by the development team


@auth_bp.route("/login", methods=["POST"])
def login():
    try:
        data = request.get_json() or {}

        email = (data.get("email") or "").strip().lower()
        password = data.get("password") or ""

        if not email or not password:
            return jsonify({"error": "Missing email or password"}), 400

        user = db_driver.get_user_by_email(email)

        if not user:
            return jsonify({"error": "Email does not exist"}), 401

        if not user.check_password(password):
            return jsonify({"error": "Invalid password"}), 401

        access_token = create_access_token(identity=str(user.id))

        return jsonify(
            {
                "message": "Login successful",
                "access_token": access_token,
                "user": {
                    "id": str(user.id),
                    "email": user.email,
                    "org_id": str(user.org_id),
                    "role": user.role,
                },
            }
        ), 200

    except SQLAlchemyError:
        return jsonify({"error": "Database error while logging in"}), 500
    except Exception:
        return jsonify({"error": "Server error while logging in"}), 500
