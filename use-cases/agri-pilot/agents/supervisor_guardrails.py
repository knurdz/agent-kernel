"""Post-model guardrail for the AgriPilot triage supervisor.

TRIAGE_INSTRUCTIONS (agents/supervisor.py) tells the supervisor LLM that
delegation must be a real handoff call, never prose describing one. Prompts
reduce this failure but cannot guarantee it: the supervisor can still emit a
final, tool-call-free reply that claims to be "escalating", "checking", or
"retrieving" something it never actually requested. That reply would go
straight to the farmer with no specialist ever having run.

This module adds a code-level backstop using `post_model_hook`, a node
`langgraph_supervisor.create_supervisor` runs after every supervisor LLM
turn. It cannot change what the model *wrote* after the fact, but it can
inspect the turn before it reaches the farmer: if the last message is a
final (non-tool-call) reply that matches a "promised an action, took none"
pattern, the hook re-invokes the model once with an explicit correction and
lets that response take over. If the model now makes a real handoff call,
LangGraph's own routing executes it exactly as if the model had called it
on the first try (see `post_model_hook_router` in
`langgraph.prebuilt.chat_agent_executor`, which sends any pending tool call
straight to the tools node).

This is a single-retry backstop, not a loop: the hook itself is not
recursive, so a still-bad retry simply proceeds to the farmer rather than
looping forever.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

from langchain_core.language_models import LanguageModelLike
from langchain_core.messages import AIMessage, SystemMessage
from langchain_core.tools import BaseTool
from langgraph_supervisor.handoff import create_handoff_tool

log = logging.getLogger("agripilot.supervisor_guardrails")

# Increment 7.4: how many times one specialist may be handed off to within
# a single supervisor run before routing is declared a loop.
DEFAULT_HANDOFF_LIMIT = int(os.environ.get("AGRIPILOT_HANDOFF_LIMIT", "3"))

# langgraph_supervisor names its handoff tools transfer_to_<agent>.
_HANDOFF_TOOL_PATTERN = re.compile(r"^transfer_to_(.+)$")

LOOP_CORRECTION_MESSAGE_TEMPLATE = (
    "You have delegated to the '{agent}' specialist {count} times in this "
    "turn without completing the request. This is a routing loop: do NOT "
    "delegate again. Give the farmer a clear, honest final reply now — say "
    "what you could not complete and why, and suggest what they can do next."
)

_loop_retry_model: LanguageModelLike | None = None

# Phrases that describe taking an action ("I'll check", "escalated",
# "transferred your request") without a tool call attached. Matching this
# alone isn't proof of a violation — that's decided by pairing it with "no
# tool_calls" in `build_narrated_delegation_guard` — but it's a good-enough
# signal that a reply is narrating rather than answering.
_PROMISE_WITHOUT_ACTION_PATTERN = re.compile(
    r"\b("
    r"hold on|please wait|"
    r"let me (?:check|get|retrieve|look|confirm)|"
    r"i(?:'|’)?ll (?:get|check|retrieve|look)|"
    r"i have escalated|escalat(?:ed|ing) (?:this|your)|"
    r"(?:initiated?|made)?\s*transfer(?:red|ring)?(?:\s+\w+){0,3}|"
    r"handed? (?:this|your|it)(?: \w+)? to|handing? (?:this|your|it)(?: \w+)? to|"
    r"forwarded (?:this|your)|pass(?:ed|ing) (?:this|your) (?:request|question) (?:to|on)|"
    r"checking with|"
    r"retrieving the (?:best|latest)|"
    r"i am (?:checking|retrieving)"
    r")\b",
    re.IGNORECASE,
)

_CORRECTION_MESSAGE = SystemMessage(
    content=(
        "Your previous reply described checking, escalating, transferring, "
        "or retrieving information on the farmer's behalf, but you did not "
        "call any tool or specialist agent. This is not allowed: either "
        "call the appropriate specialist agent right now, or answer the "
        "farmer directly without claiming to take an action you have not "
        "taken."
    )
)


def _message_text(message: AIMessage) -> str:
    """Flatten an AIMessage's content into plain text for pattern matching."""
    content = message.content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(block.get("text", "") for block in content if isinstance(block, dict))
    return str(content)


def _handoff_counts(messages: list) -> dict[str, int]:
    """Count handoff tool calls per specialist in the CURRENT turn only.

    The Agent Kernel session replays earlier turns into the message list,
    so counting the whole history would flag legitimate re-delegations on
    later farmer messages as loops. Only AIMessages after the most recent
    HumanMessage (i.e. this turn's supervisor steps) are counted.
    """
    current_turn_start = 0
    for index, message in enumerate(messages):
        if type(message).__name__ == "HumanMessage":
            current_turn_start = index + 1
    counts: dict[str, int] = {}
    for message in messages[current_turn_start:]:
        if not isinstance(message, AIMessage):
            continue
        for tool_call in message.tool_calls or []:
            match = _HANDOFF_TOOL_PATTERN.match(tool_call.get("name", ""))
            if match:
                agent = match.group(1)
                counts[agent] = counts.get(agent, 0) + 1
    return counts


def build_supervisor_post_model_hook(
    model: LanguageModelLike,
    extra_tools: list[BaseTool | Any],
    agent_names: list[str],
):
    """Build the combined `post_model_hook` for the triage supervisor.

    Runs two checks after every supervisor LLM turn, in order:

    1. Loop detection (Increment 7.4): if one specialist has been handed
       off to `DEFAULT_HANDOFF_LIMIT` times or more within this run, the
       supervisor is re-invoked once with a plain-tools-only model (no
       handoff tools, so it physically cannot delegate again) and an
       instruction to give a clear limitation reply instead.
    2. Narrated-delegation correction (see `build_narrated_delegation_guard`).

    :param model: The same (unbound) chat model the supervisor uses.
    :param extra_tools: The supervisor's own non-handoff tools.
    :param agent_names: Names of the specialist agents the supervisor can
        hand off to.
    :return: A callable suitable for `create_supervisor(post_model_hook=...)`.
    """
    narrated_delegation_guard = build_narrated_delegation_guard(
        model=model, extra_tools=extra_tools, agent_names=agent_names
    )

    global _loop_retry_model
    if _loop_retry_model is None:
        # Deliberately WITHOUT handoff tools: the loop-correction reply can
        # use plain tools but cannot start another delegation.
        _loop_retry_model = model.bind_tools(list(extra_tools))

    def combined_hook(state: dict) -> dict:
        messages = state.get("messages") or []
        counts = _handoff_counts(messages)
        for agent, count in counts.items():
            if count >= DEFAULT_HANDOFF_LIMIT:
                log.warning("handoff loop detected: %s delegated %d times", agent, count)
                correction = SystemMessage(content=LOOP_CORRECTION_MESSAGE_TEMPLATE.format(agent=agent, count=count))
                response = _loop_retry_model.invoke(messages + [correction])
                return {"messages": [correction, response]}
        return narrated_delegation_guard(state)

    return combined_hook


def build_narrated_delegation_guard(
    model: LanguageModelLike,
    extra_tools: list[BaseTool | Any],
    agent_names: list[str],
):
    """Build the `post_model_hook` callable for the triage supervisor.

    :param model: The same (unbound) chat model the supervisor uses. A
        fresh copy of the supervisor's own tools plus handoff tools for
        `agent_names` is bound to it here, so the retry call can make a
        real handoff exactly as the supervisor itself could.
    :param extra_tools: The supervisor's own non-handoff tools (e.g.
        get_farmer_context, update_farmer_context).
    :param agent_names: Names of the specialist agents the supervisor can
        hand off to (e.g. ["vision", "knowledge"]).
    :return: A callable suitable for `create_supervisor(post_model_hook=...)`.
    """
    handoff_tools = [create_handoff_tool(agent_name=name) for name in agent_names]
    retry_model = model.bind_tools(list(extra_tools) + handoff_tools)

    def guard(state: dict) -> dict:
        messages = state.get("messages") or []
        if not messages:
            return {}

        last = messages[-1]
        if not isinstance(last, AIMessage) or last.tool_calls:
            # Either not the supervisor's turn, or it already made a real
            # tool/handoff call — nothing to correct.
            return {}

        if not _PROMISE_WITHOUT_ACTION_PATTERN.search(_message_text(last)):
            return {}

        retry_response = retry_model.invoke(messages + [_CORRECTION_MESSAGE])
        return {"messages": [_CORRECTION_MESSAGE, retry_response]}

    return guard
