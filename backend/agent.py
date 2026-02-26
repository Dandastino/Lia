from __future__ import annotations
from livekit.agents import (
    AutoSubscribe,
    JobContext,
    WorkerOptions,
    cli,
    llm
)
from livekit.agents.voice import Agent, AgentSession
from livekit.plugins import openai
from dotenv import load_dotenv
from flask import Flask
from server import build_postgres_uri
from db_driver import db
from api import AssistantFnc, db_driver
from prompts import INSTRUCTIONS, WELCOME_MESSAGE, CONSULTATION_START
import os
import logging

load_dotenv()

logger = logging.getLogger("medical-agent")
logger.setLevel(logging.INFO)


def init_database():
    """
    Initialize SQLAlchemy for the agent process so assistant tools
    can talk to the same Postgres database as the Flask API.
    """
    app = Flask("lia-agent-db")
    app.config["SQLALCHEMY_DATABASE_URI"] = build_postgres_uri()
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db_driver.init_app(app)
    return app


async def entrypoint(ctx: JobContext):
    """Main entry point for the medical consultation agent"""
    app = init_database()
    # Ensure all DB operations in this job run within the Flask app context
    with app.app_context():
        await ctx.connect(auto_subscribe=AutoSubscribe.SUBSCRIBE_ALL)
        await ctx.wait_for_participant()
        
        # Derive doctor_id from job metadata or participant identity.
        metadata = ctx.job.metadata or {}
        doctor_id = metadata.get("doctor_id")
        
        # Fallback: parse doctor UUID from participant identity: "doctor_<doctorId>_<patientId>"
        if not doctor_id:
            for p in ctx.room.remote_participants.values():
                ident = getattr(p, "identity", "") or ""
                if ident.startswith("doctor_"):
                    parts = ident.split("_", 2)
                    if len(parts) >= 2:
                        doctor_id = parts[1]
                        break
        
        logger.info(f"Starting consultation session for doctor_id: {doctor_id}")
        
        # Initialize the AI model
        model = openai.realtime.RealtimeModel(
            voice="marin",
            temperature=0.8,
            modalities=["audio", "text"]
        )
        
        # Initialize assistant functions with doctor context
        assistant_fnc = AssistantFnc(doctor_id=doctor_id)
        
        # Create agent with medical instructions and tools
        agent = Agent(
            instructions=INSTRUCTIONS,
            llm=model,
            tools=assistant_fnc.get_tools()
        )
        
        # Create and start session
        session = AgentSession()
        await session.start(agent, room=ctx.room)
        
        # Session is now running; the model will respond to speech from the room
        logger.info("Medical consultation agent started successfully")


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))