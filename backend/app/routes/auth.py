from flask import Blueprint, jsonify, request
from flask_jwt_extended import create_access_token

from ..models import DatabaseDriver


auth_bp = Blueprint("auth", __name__)


db_driver = DatabaseDriver()


@auth_bp.route("/register", methods=["POST"])
def register():
    try:
        data = request.get_json() or {}

        org_id = data.get("org_id")
        if not data or not all(k in data for k in ["email", "password", "org_id"]):
            return jsonify({"error": "Missing required fields (email, password, org_id)"}), 400

        existing_user = db_driver.get_user_by_email(data["email"])
        if existing_user:
            return jsonify({"error": "Email already registered"}), 409

        user = db_driver.create_user(
            email=data["email"],
            password=data["password"],
            org_id=org_id,
            role=data.get("role", "user"),
        )

        if not user:
            return jsonify({"error": "Failed to create user account"}), 500

        access_token = create_access_token(identity=str(user.id))

        return jsonify(
            {
                "message": "User registered successfully",
                "access_token": access_token,
                "user": {
                    "id": str(user.id),
                    "email": user.email,
                    "org_id": str(user.org_id),
                    "role": user.role,
                },
            }
        ), 201

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@auth_bp.route("/login", methods=["POST"])
def login():
    try:
        data = request.get_json() or {}

        if not data or not all(k in data for k in ["email", "password"]):
            return jsonify({"error": "Missing email or password"}), 400

        user = db_driver.get_user_by_email(data["email"])

        if not user or not user.check_password(data["password"]):
            return jsonify({"error": "Invalid email or password"}), 401

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

    except Exception as e:
        return jsonify({"error": str(e)}), 500
