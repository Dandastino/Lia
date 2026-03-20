from __future__ import annotations

import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()


def build_postgres_uri() -> str:
    user = os.getenv("DB_USER")
    password = os.getenv("DB_PASSWORD")
    host = os.getenv("DB_HOST")
    port = os.getenv("DB_PORT")
    dbname = os.getenv("DB_NAME")
    missing = [
        k
        for k, v in [
            ("DB_USER", user),
            ("DB_PASSWORD", password),
            ("DB_HOST", host),
            ("DB_PORT", port),
            ("DB_NAME", dbname),
        ]
        if not v
    ]
    if missing:
        raise RuntimeError(
            f"Missing required environment variables for DB config: {', '.join(missing)}"
        )
    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{dbname}"


class Config:
    SQLALCHEMY_DATABASE_URI = build_postgres_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=24)
    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*")
    DEBUG = os.getenv("DEBUG", "False").lower() == "true"
    ENV = os.getenv("ENV", "development")
