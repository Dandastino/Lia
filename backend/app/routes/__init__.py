from flask import Flask

from .auth import auth_bp
from .health import health_bp
from .livekit import livekit_bp
from .meetings import meetings_bp
from .organizations import organizations_bp
from .root import root_bp
from .admin import admin_bp


def register_blueprints(app: Flask) -> None:
    app.register_blueprint(root_bp)
    app.register_blueprint(health_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(organizations_bp)
    app.register_blueprint(meetings_bp)
    app.register_blueprint(livekit_bp)
    app.register_blueprint(admin_bp)
