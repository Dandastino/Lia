from __future__ import annotations

from flask import Flask
from flask_cors import CORS

from .config import Config
from .extensions import db, jwt
from .routes import register_blueprints


def create_app() -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config())

    CORS(
        app,
        resources={r"/*": {"origins": app.config.get("CORS_ORIGINS", "*")}},
        supports_credentials=True,
        allow_headers=["Content-Type", "Authorization"],
        expose_headers=["Content-Type", "Authorization"],
    )

    db.init_app(app)
    jwt.init_app(app)

    register_blueprints(app)

    with app.app_context():
        db.create_all()

    return app
