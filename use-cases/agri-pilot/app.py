"""API entry point for AgriPilot (Phase 8+).

Runs the agent behind an Agent Kernel REST server with WhatsApp Cloud API
webhook support. Requires AK_WHATSAPP__ACCESS_TOKEN, AK_WHATSAPP__PHONE_NUMBER_ID
and AK_WHATSAPP__VERIFY_TOKEN to be set; startup fails fast otherwise.
"""

from dotenv import load_dotenv

load_dotenv(".env.local")

from agentkernel.api import RESTAPI
from agentkernel.langgraph import LangGraphModule
from agentkernel.whatsapp import AgentWhatsAppRequestHandler

from agents.supervisor import triage_agent

LangGraphModule([triage_agent])


if __name__ == "__main__":
    RESTAPI.run([AgentWhatsAppRequestHandler()])
