from __future__ import annotations
import json
from uuid import UUID
from livekit.agents import (
    AutoSubscribe,
    JobContext,
    WorkerOptions,
    cli,
)
from livekit.agents.voice import Agent, AgentSession
from livekit.plugins import openai
from dotenv import load_dotenv
from flask import Flask

from app.config import build_postgres_uri
from app.extensions import db
from app.models import User
from app.tools.middleware import MiddlewareTools
from app.prompts import build_system_prompt
import logging

load_dotenv()

logger = logging.getLogger("agent")
logger.setLevel(logging.INFO)


def init_database():
    """
    Initialize SQLAlchemy for the agent process so assistant tools
    can talk to the same Postgres database as the Flask API.
    """
    app = Flask("lia-agent-db")
    app.config["SQLALCHEMY_DATABASE_URI"] = build_postgres_uri()
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)
    return app


def normalize_user_id(raw_user_id: str | None) -> str | None:
    if not raw_user_id:
        return None

    candidate = raw_user_id
    if raw_user_id.startswith("User_"):
        candidate = raw_user_id.split("User_", 1)[1]

    try:
        return str(UUID(candidate))
    except ValueError:
        return None


async def entrypoint(ctx: JobContext):
    """Main entry point for the multi-tenant Lia agent."""
    app = init_database()
    # Ensure all DB operations in this job run within the Flask app context
    with app.app_context():
        await ctx.connect(auto_subscribe=AutoSubscribe.SUBSCRIBE_ALL)
        try:
            participant = await ctx.wait_for_participant()
        except RuntimeError as exc:
            if "room disconnected while waiting for participant" in str(exc).lower():
                logger.info("Room disconnected before participant joined; closing job gracefully")
                return
            raise

        # Derive user_id from job metadata, participant metadata, or participant identity.
        job_metadata = ctx.job.metadata or {}
        if isinstance(job_metadata, str):
            try:
                job_metadata = json.loads(job_metadata)
            except Exception:
                job_metadata = {}

        participant_metadata = getattr(participant, "metadata", None) or {}
        if isinstance(participant_metadata, str):
            try:
                participant_metadata = json.loads(participant_metadata)
            except Exception:
                participant_metadata = {}

        participant_identity = getattr(participant, "identity", None)
        raw_user_id = (
            job_metadata.get("user_id")
            or participant_metadata.get("user_id")
            or participant_identity
        )
        user_id = normalize_user_id(raw_user_id)

        logger.info(f"Starting voice session for raw_user_id={raw_user_id}, normalized_user_id={user_id}")

        # Resolve user + organization for multi-tenant configuration
        user = User.query.get(user_id) if user_id else None
        org = getattr(user, "organization", None) if user else None

        org_name = org.name if org and getattr(org, "name", None) else "your organization"
        org_industry = getattr(org, "industry", None) if org else None
        connector_config = getattr(org, "connector_config", None) if org else None
        prompt_overrides = (connector_config or {}).get("prompt_overrides") if connector_config else None

        instructions = build_system_prompt(
            org_name=org_name,
            org_industry=org_industry,
            extra_rules=prompt_overrides,
        )

        # Initialize the AI model
        model = openai.realtime.RealtimeModel(
            voice="marin",
            temperature=0.8,
            modalities=["audio", "text"],
            turn_detection={
                "type": "server_vad",
                "threshold": 0.8, # Valid range is <= 1.0; higher means less sensitivity to background noise
                "prefix_padding_ms": 500, # Capture 500ms of audio before speech starts
                "silence_duration_ms": 1500, # Consider speech ended after 1.5s of silence
            },
        )

        # Industry-agnostic tools: generic meeting + history only
        middleware_tools = MiddlewareTools(user_id)
        tools = middleware_tools.get_tools()

        # Create agent with dynamic, industry-aware instructions, tools, and STT
        agent = Agent(
            instructions=instructions,
            llm=model,
            tools=tools,
        )
        
        # Create and start session
        session = AgentSession()
        await session.start(agent, room=ctx.room)
        
        # Session is now running; the model will respond to speech from the room
        logger.info("Lia Start sucessfully")


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))