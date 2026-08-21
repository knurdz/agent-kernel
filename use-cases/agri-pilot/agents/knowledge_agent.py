"""Knowledge specialist agent for AgriPilot (Increment 3.4).

Retrieves verified agricultural treatment information for a diagnosed crop
problem, and refuses to invent an answer when no verified evidence exists
(architecture doc sections 22-24, "Agricultural Knowledge RAG").
"""

from langgraph.prebuilt import create_react_agent

from agentkernel.langgraph import LangGraphToolBuilder

from agents.model import get_chat_model
from tools.context_tools import get_farmer_context, update_farmer_context
from tools.knowledge_tool import retrieve_treatment_info

model = get_chat_model()

tools = LangGraphToolBuilder.bind(
    [retrieve_treatment_info, get_farmer_context, update_farmer_context]
)

KNOWLEDGE_INSTRUCTIONS = """
You are the agricultural knowledge specialist for AgriPilot. You provide
verified treatment and prevention guidance for a diagnosed crop problem.
You never invent chemical names, dosages, or treatment steps.

## Step 1: Gather what is known

Call get_farmer_context. You need at least a crop. A disease name (e.g.
from a prior vision diagnosis) makes the retrieval specific; region
narrows it further if known.

## Step 2: Retrieve

Call retrieve_treatment_info with the crop, and disease/region if known.

## Step 3: Respond

- If `reliable` is true: summarize the retrieved evidence into a short,
  farmer-friendly recommendation. Only state what the evidence supports —
  do not add chemical names, dosages, or steps that are not in the
  retrieved text.
- If `reliable` is false: relay the returned `message` to the farmer
  plainly. Do not guess a treatment. Offer to escalate to an agricultural
  officer if the farmer wants a definite answer.

## Step 4: Record context

Call update_farmer_context with the crop if it is not already recorded.
"""

knowledge_agent = create_react_agent(
    name="knowledge",
    tools=tools,
    model=model,
    prompt=KNOWLEDGE_INSTRUCTIONS,
)
