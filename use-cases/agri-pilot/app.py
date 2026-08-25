"""API entry point for AgriPilot (Phase 8+).

Runs the agent behind an Agent Kernel REST server with WhatsApp Cloud API
webhook support. Requires AK_WHATSAPP__ACCESS_TOKEN, AK_WHATSAPP__PHONE_NUMBER_ID
and AK_WHATSAPP__VERIFY_TOKEN to be set; startup fails fast otherwise.
"""

from dotenv import load_dotenv

load_dotenv(".env.local")

from agentkernel.api import RESTAPI, AgentRESTRequestHandler
from agentkernel.langgraph import LangGraphModule

from agents.supervisor import triage_agent
from marketplace.database import run_migrations
from marketplace.routers.auth import router as auth_router
from marketplace.routers.buyer import router as buyer_router
from marketplace.routers.farmer import router as farmer_router
from whatsapp_handler import FastAckWhatsAppHandler

# Apply pending Alembic migrations before serving (single schema authority).
run_migrations()

LangGraphModule([triage_agent])

RESTAPI.add(auth_router)
RESTAPI.add(farmer_router)
RESTAPI.add(buyer_router)


if __name__ == "__main__":
    # AgentRESTRequestHandler mounts /api/v1/chat (+ /agents); without it the
    # explicit handler list would leave only the WhatsApp webhook routes.
    RESTAPI.run([AgentRESTRequestHandler(), FastAckWhatsAppHandler()])
