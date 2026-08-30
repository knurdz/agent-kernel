"""API entry point for AgriPilot (Phase 8+).

Runs the agent behind an Agent Kernel REST server with WhatsApp Cloud API and
Telegram Bot API webhook support. Mobile chat uses JWT-authenticated thread routes.
"""

from dotenv import load_dotenv

load_dotenv(".env.local")

from agentkernel.api import RESTAPI
from agentkernel.langgraph import LangGraphModule

from agents.supervisor import triage_agent
from marketplace.database import run_migrations
from marketplace.routers.auth import router as auth_router
from marketplace.routers.buyer import router as buyer_router
from marketplace.routers.config import router as config_router
from marketplace.routers.devices import router as devices_router
from marketplace.routers.farmer import router as farmer_router
from marketplace.routers.plants import router as plants_router
from mobile_api.authenticated_chat_handler import AuthenticatedMobileChatHandler
from telegram_handler import GatedTelegramHandler
from whatsapp_handler import FastAckWhatsAppHandler

# Apply pending Alembic migrations before serving (single schema authority).
run_migrations()

LangGraphModule([triage_agent])

RESTAPI.add(auth_router)
RESTAPI.add(farmer_router)
RESTAPI.add(plants_router)
RESTAPI.add(buyer_router)
RESTAPI.add(config_router)
RESTAPI.add(devices_router)


if __name__ == "__main__":
    RESTAPI.run([AuthenticatedMobileChatHandler(), FastAckWhatsAppHandler(), GatedTelegramHandler()])
