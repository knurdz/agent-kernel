"""Supervisor agent for AgriPilot.

Routes farmer requests to specialist agents. From Phase 2 onward this is a
langgraph_supervisor supervisor rather than a standalone agent. Phase 3
adds the knowledge specialist. More specialists join `agents=[...]` in
later phases (resource, market).
"""

from agentkernel.langgraph import LangGraphToolBuilder
from langgraph_supervisor import create_supervisor

from agents.knowledge_agent import knowledge_agent
from agents.model import get_chat_model
from agents.supervisor_guardrails import build_narrated_delegation_guard
from agents.vision_agent import vision_agent
from tools.context_tools import get_farmer_context, update_farmer_context

model = get_chat_model()

tools = LangGraphToolBuilder.bind([get_farmer_context, update_farmer_context])

# Code-level backstop for the "delegation is an action, not a narration"
# rule in TRIAGE_INSTRUCTIONS below (see agents/supervisor_guardrails.py).
# Catches the case where the supervisor LLM ignores that instruction and
# writes a reply that only claims to have delegated.
narrated_delegation_guard = build_narrated_delegation_guard(
    model=get_chat_model(),
    extra_tools=tools,
    agent_names=["vision", "knowledge"],
)

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
- If the intent is CROP_HEALTH and the farmer asks for treatment or
  prevention guidance for a disease that is already known (e.g. from a
  prior vision diagnosis, an earlier turn, or because the farmer stated
  the disease name directly in this message), delegate to the
  `knowledge` agent.
- Chain vision into knowledge in the SAME turn: after the `vision` agent
  returns a confident diagnosis, it records the crop and diagnosed
  disease in the farmer context — immediately delegate to `knowledge`
  next so the farmer gets one combined reply with the diagnosis AND a
  full treatment recommendation, not just a disease name. Do not reply
  in between the two handoffs.
- For all other intents, no specialist exists yet (they arrive in later
  phases). Answer directly, but say plainly if the request needs a
  capability you don't have yet (weather, market), and that it is coming
  soon.

Never state a chemical name or dosage yourself, even if you know one:
treatment recommendations only come from the `knowledge` agent, which
validates them against the safety rules before replying.

Do not ask for information you already have, and do not ask more
questions than necessary.

## Step 3a: Delegation is an action, never a narration

"Delegate" means actually invoking the `vision` or `knowledge` agent as a
handoff in this same turn — it is not something you describe in prose.

- Never write a reply that claims or implies delegation has happened, is
  happening, or will happen ("I have escalated this...", "Please hold
  on...", "let me check with...", "I'll get that for you...") unless you
  are simultaneously making the actual handoff call. A sentence about
  delegating is not a substitute for delegating.
- Never end your turn on a message that promises information is coming.
  If you decide a specialist is needed, invoke it now, in this turn, and
  only reply to the farmer after you have its result (see Step 4). If for
  any reason you cannot invoke it, do not pretend you did — instead say
  plainly what you still need or that the capability is unavailable.

## Step 4: Relay the specialist's answer

When a specialist agent (`vision`, `knowledge`) returns a response, your
final reply to the farmer must contain that response's actual content —
the diagnosis, treatment steps, etc. Never reply with a meta-summary like
"I have provided the steps" or "I have shared the information above"
without including the information itself. If the specialist's message is
already farmer-ready, relay it directly. Relay safety wording exactly as
given (including "I cannot safely recommend this") — never soften it,
and never add chemical names or dosages of your own.
"""

triage_agent = create_supervisor(
    model=model,
    agents=[vision_agent, knowledge_agent],
    tools=tools,
    prompt=TRIAGE_INSTRUCTIONS,
    post_model_hook=narrated_delegation_guard,
).compile(name="triage")
