"""Delivery specialist agent — read-only order/dispatch explanations."""

from agentkernel.langgraph import LangGraphToolBuilder
from langchain.agents import create_agent

from agents.model import get_chat_model
from tools.delivery_tools import (
    my_orders_tool,
    nearby_delivery_jobs_tool,
    order_status_tool,
    rider_active_job_tool,
)

DELIVERY_INSTRUCTIONS = """
You are the delivery specialist for AgriPilot marketplace logistics.

You help farmers, buyers, and riders understand order and delivery status.
You NEVER create orders, assign riders, accept jobs, or change delivery state —
those actions happen only in the mobile app via REST APIs.

Always call the appropriate tool before answering:
- my_orders_tool — list the user's orders or rider delivery history
- order_status_tool — detailed tracking for a specific order_id
- rider_active_job_tool — rider's current active delivery
- nearby_delivery_jobs_tool — available jobs for online riders (weight/distance only)

Relay tool results clearly: crop, quantity, status, ETA hints from route_duration_s,
and whether rider location is stale. Never invent order IDs, ETAs, or phone numbers.
If a tool returns an error, explain it plainly.
"""

model = get_chat_model()
tools = LangGraphToolBuilder.bind(
    [my_orders_tool, order_status_tool, rider_active_job_tool, nearby_delivery_jobs_tool]
)

delivery_agent = create_agent(
    model=model,
    tools=tools,
    name="delivery",
    system_prompt=DELIVERY_INSTRUCTIONS,
)
