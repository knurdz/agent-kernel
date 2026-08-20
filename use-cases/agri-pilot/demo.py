"""CLI entry point for AgriPilot (Phase 0-11)."""

from dotenv import load_dotenv

load_dotenv(".env.local")

from agentkernel.cli import CLI
from agentkernel.langgraph import LangGraphModule

from agents.supervisor import triage_agent

LangGraphModule([triage_agent])


if __name__ == "__main__":
    CLI.main()
