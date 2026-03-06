from flask import Blueprint, jsonify

root_bp = Blueprint("root", __name__)


@root_bp.route("/", methods=["GET"])
def index():
    return jsonify(
        {
            "name": "Lia Assistant API",
            "version": "1.0.0",
            "description": "Multi-tenant backend API for Lia with data isolation",
            "note": "User and organization management is available via Admin UI or CLI (python backend/manage.py)",
            "endpoints": {
                "auth": {
                    "login": "POST /login (email, password)",
                },
                "organizations": {
                    "list": "GET /organizations",
                    "get": "GET /organizations/<id> (requires auth)",
                    "update_connector": "PATCH /organizations/<id>/connector (requires auth, owner/admin)",
                },
                "admin": {
                    "dashboard": "GET /admin/dashboard (admin only)",
                    "create_org": "POST /admin/organizations (admin only)",
                    "create_user": "POST /admin/users (admin only)",
                    "update_user": "PUT /admin/users/<id> (admin only)",
                    "delete_user": "DELETE /admin/users/<id> (admin only)",
                    "delete_org": "DELETE /admin/organizations/<id> (admin only)",
                    "entity_ownership": {
                        "list": "GET /admin/users/<id>/entity-ownership (admin only, returns entities owned by user)",
                        "assign": "POST /admin/users/<id>/entity-ownership (admin only, assign entity to user)",
                        "remove": "DELETE /admin/users/<id>/entity-ownership/<entity_type>/<entity_id> (admin only)",
                        "bulk_assign": "POST /admin/entity-ownership/bulk (admin only, bulk assign entities)",
                    },
                },
                "health": "GET /health",
            },
        }
    ), 200
