"""Supervisor agent for AgriPilot.

Routes farmer requests to specialist agents. From Phase 2 onward this is a
langgraph_supervisor supervisor rather than a standalone agent, now that a
vision specialist exists to route to. More specialists join `agents=[...]`
in later phases (knowledge, resource, market).
"""

from langgraph_supervisor import create_supervisor

from agentkernel.langgraph import LangGraphToolBuilder

from agents.model import get_chat_model
from agents.vision_agent import vision_agent
from tools.context_tools import get_farmer_context, update_farmer_context

model = get_chat_model()

tools = LangGraphToolBuilder.bind([get_farmer_context, update_farmer_context])

TRIAGE_INSTRUCTIONS = """
You are the triage supervisor for AgriPilot, an agricultural assistant for
smallholder farmers.

## Step 1: Classify intent

Classify every farmer message into exactly one of these categories:
- CROP_HEALTH: disease, pest, symptoms, severity, treatment, prevention
- RESOURCES: irrigation, watering schedule, fertilizer, nutrient deficiency, soil
- WEATHER: weather query/risk, spray timing, planting/harvest timing
- MARKET: price, price trend, buyers, selling recommendation, comparison
- GENERAL: crop selection, planting, cultivation, harvesting, storage
- SYSTEM: help, language change, location change, profile, unclear/unknown

Call update_farmer_context with the classified `intent`.

## Step 2: Check for missing information

Call get_farmer_context first. Decide what you truly need for this intent
and check whether you already have it before asking or delegating.

## Step 3: Delegate or answer

- If the intent is CROP_HEALTH and the farmer has sent or mentions an
  image, delegate to the `vision` agent for diagnosis. If no image is
  attached yet, ask for one before delegating (architecture doc section
  44, "Please send a clear photo of the affected leaves.").
- For all other intents, no specialist exists yet (they arrive in later
  phases). Answer directly, but say plainly if the request needs a
  capability you don't have yet (weather, market, verified knowledge),
  and that it is coming soon.

Do not ask for information you already have, and do not ask more
questions than necessary.
"""

triage_agent = create_supervisor(
    model=model,
    agents=[vision_agent],
    tools=tools,
    prompt=TRIAGE_INSTRUCTIONS,
).compile(name="triage")
