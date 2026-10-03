import bcrypt
from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import create_access_token, get_jwt_identity, jwt_required

from ..extensions import db, limiter
from ..models import User
from ..security import normalize_email, server_error, validate_password
from ..tools.authorization import verify_user_by_email

auth_bp = Blueprint("auth", __name__)

# NOTE: User registration is only available via CLI/development tools or the admin API.

# Used to spend the same CPU time when the email is unknown, so that response
# timing does not reveal which emails exist.
_DUMMY_HASH = bcrypt.hashpw(b"timing-equalizer", bcrypt.gensalt()).decode("utf-8")

_INVALID_CREDENTIALS = {"error": "Invalid email or password"}


def _login_limit() -> str:
    return current_app.config.get("LOGIN_RATE_LIMIT", "5 per minute;30 per hour")


@auth_bp.route("/login", methods=["POST"])
@limiter.limit(_login_limit)
def login():
    """
    Authenticate user and issue JWT token.

    Request body: {"email": "...", "password": "..."}
    Returns a JWT whose identity is the user UUID.
    """
    try:
        data = request.get_json(silent=True) or {}
        if not isinstance(data, dict):
            return jsonify({"error": "Invalid request body"}), 400

        email = normalize_email(data.get("email"))
        password = data.get("password")
        if not email or not isinstance(password, str) or not password:
            return jsonify({"error": "Missing email or password"}), 400

        user = verify_user_by_email(email)
        if user is None:
            bcrypt.checkpw(password.encode("utf-8")[:72], _DUMMY_HASH.encode("utf-8"))
            return jsonify(_INVALID_CREDENTIALS), 401

        if not user.check_password(password):
            return jsonify(_INVALID_CREDENTIALS), 401

        if not user.org_id:
            return jsonify({"error": "User is not associated with any organization"}), 403

        access_token = create_access_token(identity=str(user.id))

        return jsonify(
            {
                "message": "Login successful",
                "access_token": access_token,
                "user": {
                    "id": str(user.id),
                    "email": user.email,
                    "org_id": str(user.org_id),
                    "org_name": user.organization.name,
                    "role": user.role,
                },
            }
        ), 200
    except Exception as e:
        return server_error(e, "Server error while logging in")


@auth_bp.route("/me/export", methods=["GET"])
@jwt_required()
def export_my_data():
    """GDPR Art. 15/20: export the personal data Lia stores about the current user."""
    try:
        from ..models import ExternalUserMapping, UserEntityOwnership

        user = db.session.get(User, get_jwt_identity())
        if not user:
            return jsonify({"error": "User not found"}), 404

        ownerships = UserEntityOwnership.query.filter_by(user_id=user.id).all()
        mappings = ExternalUserMapping.query.filter_by(user_id=user.id).all()
        return jsonify(
            {
                "user": {
                    "id": str(user.id),
                    "email": user.email,
                    "role": user.role,
                    "org_id": str(user.org_id) if user.org_id else None,
                    "created_at": user.created_at.isoformat() if user.created_at else None,
                },
                "entity_ownership": [
                    {
                        "entity_type": o.entity_type,
                        "external_entity_id": o.external_entity_id,
                        "created_at": o.created_at.isoformat() if o.created_at else None,
                    }
                    for o in ownerships
                ],
                "external_user_mappings": [
                    {
                        "crm_type": m.crm_type,
                        "external_user_id": m.external_user_id,
                        "external_email": m.external_email,
                    }
                    for m in mappings
                ],
                "note": (
                    "Business records (meetings, contacts, ...) live in your organization's own "
                    "system and must be requested from your organization."
                ),
            }
        ), 200
    except Exception as e:
        return server_error(e)


@auth_bp.route("/me", methods=["DELETE"])
@jwt_required()
def delete_my_account():
    """GDPR Art. 17: delete the current user's account (requires password confirmation)."""
    try:
        user = db.session.get(User, get_jwt_identity())
        if not user:
            return jsonify({"error": "User not found"}), 404

        data = request.get_json(silent=True) or {}
        password = data.get("password")
        if not isinstance(password, str) or not user.check_password(password):
            return jsonify({"error": "Password confirmation failed"}), 403

        db.session.delete(user)
        db.session.commit()
        return jsonify({"message": "Account deleted"}), 200
    except Exception as e:
        db.session.rollback()
        return server_error(e)


@auth_bp.route("/me/password", methods=["PUT"])
@jwt_required()
def change_my_password():
    """Let a user change their own password (current password required)."""
    try:
        user = db.session.get(User, get_jwt_identity())
        if not user:
            return jsonify({"error": "User not found"}), 404

        data = request.get_json(silent=True) or {}
        if not user.check_password(data.get("current_password") or ""):
            return jsonify({"error": "Current password is incorrect"}), 403

        error = validate_password(data.get("new_password"))
        if error:
            return jsonify({"error": error}), 400

        user.set_password(data["new_password"])
        db.session.commit()
        return jsonify({"message": "Password updated"}), 200
    except Exception as e:
        db.session.rollback()
        return server_error(e)
