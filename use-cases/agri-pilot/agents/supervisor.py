"""Triage/supervisor agent for AgriPilot.

This agent is the entry point for every farmer message. In later increments
it routes to specialist agents (vision, knowledge, resource, market). For
now it is a placeholder that confirms the scaffold is wired correctly.
"""

from langgraph.prebuilt import create_react_agent

from agents.model import get_chat_model

model = get_chat_model()

TRIAGE_INSTRUCTIONS = """
You are the triage agent for AgriPilot, an agricultural assistant for
smallholder farmers. For now you have no specialist agents or tools
available yet. Greet the farmer and briefly explain that you will soon be
able to help diagnose crop problems, give irrigation and weather advice,
and check market prices.
"""

triage_agent = create_react_agent(
    name="triage",
    tools=[],
    model=model,
    prompt=TRIAGE_INSTRUCTIONS,
)
