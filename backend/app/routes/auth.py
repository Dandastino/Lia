from flask import Blueprint, jsonify, request
from flask_jwt_extended import create_access_token
from sqlalchemy.exc import SQLAlchemyError

from ..models import DatabaseDriver, User
from ..tools.authorization import verify_user_by_email


auth_bp = Blueprint("auth", __name__)


db_driver = DatabaseDriver()


# NOTE: User registration is only available via CLI/development tools
# Accounts must be created by the development team


@auth_bp.route("/login", methods=["POST"])
def login():
    """
    Authenticate user and issue JWT token.
    
    Request body:
    {
        "email": "user@organization.com",
        "password": "secure_password"
    }
    
    Returns JWT token with user_id (UUID) in claims.
    Token can be used for all subsequent requests.
    """
    try:
        data = request.get_json() or {}

        # Normalize email: lowercase and strip whitespace
        email = (data.get("email") or "").strip().lower()
        password = data.get("password") or ""

        if not email or not password:
            return jsonify({"error": "Missing email or password"}), 400

        # Look up user by email
        # Email is globally unique across all organizations
        user = verify_user_by_email(email)

        if not user:
            return jsonify({"error": "Email does not exist"}), 401

        if not user.check_password(password):
            return jsonify({"error": "Invalid password"}), 401

        # Verify user is properly associated with organization
        if not user.org_id:
            return jsonify({
                "error": "User is not associated with any organization"
            }), 401

        # JWT token contains user_id (UUID), not email
        # This ensures all subsequent requests can identify exact user
        access_token = create_access_token(identity=str(user.id))

        return jsonify(
            {
                "message": "Login successful",
                "access_token": access_token,
                "user": {
                    "id": str(user.id),              # UUID for endpoint calls
                    "email": user.email,            # Display email
                    "org_id": str(user.org_id),     # Organization UUID
                    "org_name": user.organization.name,  # Organization name for display
                    "role": user.role,
                },
            }
        ), 200

    except SQLAlchemyError as e:
        return jsonify({"error": "Database error while logging in"}), 500
    except Exception as e:
        return jsonify({"error": "Server error while logging in"}), 500
