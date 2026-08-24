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
final (non-tool-call) reply that claims an action it never took — decided
by an LLM judge (`build_narration_judge`), not by word patterns — the hook
re-invokes the model once with an explicit correction and lets that
response take over. If the model now makes a real handoff call, LangGraph's
own routing executes it exactly as if the model had called it on the first
try (see `post_model_hook_router` in `langgraph.prebuilt.chat_agent_executor`,
which sends any pending tool call straight to the tools node).

The judge replaced an earlier hand-written phrase regex: narration is
unbounded natural language ("escalated", then "transferred", then ...),
and Phase 12 adds Sinhala/Tamil where English patterns are useless. The
judge classifies meaning across three violation classes (claimed handoff,
promised action, claimed-but-absent content) in any language. Its verdict
parse is recall-biased (ambiguous counts as a violation: a false positive
only costs one corrective retry) and judge failures fail OPEN so a broken
judge never blocks a legitimate reply.

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
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
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

# Judge instructions: meaning-based classification of the supervisor's
# final reply, not word matching. Covers all three observed failure classes
# plus the legitimate reply shapes that must pass.
_JUDGE_SYSTEM_PROMPT = """You are a compliance checker for AgriPilot, an \
agricultural assistant for farmers. A triage supervisor may route farmer \
requests to specialist agents by making handoff tool calls. You will be \
given the farmer's latest message and the supervisor's FINAL reply to the \
farmer. That final reply was written WITHOUT any tool call.

Decide whether the reply VIOLATES any of these rules:

1. CLAIMED HANDOFF: It claims a delegation or transfer already happened \
("I have transferred your request", "handed over to our specialist", \
"escalated your case", "the support team has it now") when no such action \
was taken.
2. PROMISED ACTION: It promises an action is under way or information is \
coming ("let me check", "please hold on while I retrieve", "I'll get that \
for you", "someone is looking into it").
3. CLAIMED DELIVERY: It refers to information as already given ("as \
provided above", "the steps I shared", "see the details above") while \
that information does NOT actually appear anywhere in the reply text.

Reply FALSE (no violation) when the reply directly answers the farmer's \
question; asks a clarifying question about what is needed; honestly says \
something is unavailable or states what information is still missing; or \
truthfully reports work a specialist already did (the context tells you \
when a specialist was consulted).

The texts may be in any language (English, Sinhala, Tamil, ...). Judge \
meaning and intent, never specific words.

Answer with exactly one word: TRUE if the reply violates a rule, FALSE \
if it does not."""

_CORRECTION_MESSAGE = SystemMessage(
    content=(
        "Your previous reply described checking, escalating, transferring, "
        "retrieving, or having already provided something on the farmer's "
        "behalf, but you did not call any tool or specialist agent, and/or "
        "the promised information is not in your reply. This is not "
        "allowed: either make the real specialist/tool call right now, or "
        "answer the farmer directly with the actual information included in "
        "this reply — without claiming to have taken an action you have not "
        "taken."
    )
)


def _parse_judge_verdict(text: str) -> bool:
    """Interpret the judge's one-word answer as 'is a violation'.

    Recall-biased: anything ambiguous (empty, both words, unparseable)
    counts as a violation — a false positive only costs one corrective
    retry, a false negative ships a false claim to the farmer.
    """
    lowered = text.strip().lower()
    affirmative = "true" in lowered or "yes" in lowered
    negative = "false" in lowered or "no" in lowered
    if affirmative == negative:
        return True  # neither or both -> ambiguous -> violation
    return affirmative


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


def build_narration_judge(judge_model: LanguageModelLike):
    """Build a meaning-based violation detector from a chat model.

    :param judge_model: A cheap chat model (any provider — see
        `agents.model.get_judge_model`).
    :return: ``judge(farmer_text, reply_text, specialist_consulted) -> bool``
        where True means "this final reply claims an action or delivery it
        did not perform". Judge failures fail OPEN (False = no violation)
        so a broken judge never blocks a legitimate reply.
    """

    def judge(farmer_text: str, reply_text: str, specialist_consulted: bool) -> bool:
        context_note = (
            "Context: a specialist agent WAS consulted earlier in this turn.\n"
            if specialist_consulted
            else "Context: NO specialist agent was consulted in this turn.\n"
        )
        user_content = (
            f"{context_note}\n"
            f"Farmer's latest message:\n{farmer_text or '(none)'}\n\n"
            f"Supervisor's final reply:\n{reply_text}\n"
        )
        try:
            response = judge_model.invoke(
                [
                    SystemMessage(content=_JUDGE_SYSTEM_PROMPT),
                    HumanMessage(content=user_content),
                ]
            )
            content = response.content if isinstance(response.content, str) else str(response.content)
            return _parse_judge_verdict(content)
        except Exception:  # noqa: BLE001 - fail open on any judge failure
            log.exception("narration judge failed; failing OPEN (treating reply as clean)")
            return False

    return judge


def build_supervisor_post_model_hook(
    model: LanguageModelLike,
    extra_tools: list[BaseTool | Any],
    agent_names: list[str],
    judge: Any | None = None,
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
    :param judge: Optional narration judge from `build_narration_judge`;
        built lazily from `agents.model.get_judge_model()` when omitted.
    :return: A callable suitable for `create_supervisor(post_model_hook=...)`.
    """
    narrated_delegation_guard = build_narrated_delegation_guard(
        model=model, extra_tools=extra_tools, agent_names=agent_names, judge=judge
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
    judge: Any | None = None,
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
    :param judge: A callable from `build_narration_judge`. When None, one
        is built lazily on first use from `agents.model.get_judge_model()`
        — lazy so stub-model unit tests never need API credentials.
    :return: A callable suitable for `create_supervisor(post_model_hook=...)`.
    """
    handoff_tools = [create_handoff_tool(agent_name=name) for name in agent_names]
    retry_model = model.bind_tools(list(extra_tools) + handoff_tools)

    holder = {"judge": judge}

    def _get_judge():
        if holder["judge"] is None:
            from agents.model import get_judge_model

            log.info("building default narration judge model")
            holder["judge"] = build_narration_judge(get_judge_model())
        return holder["judge"]

    def guard(state: dict) -> dict:
        messages = state.get("messages") or []
        if not messages:
            return {}

        last = messages[-1]
        if not isinstance(last, AIMessage) or last.tool_calls:
            # Either not the supervisor's turn, or it already made a real
            # tool/handoff call — nothing to correct.
            return {}

        farmer_text = ""
        for message in reversed(messages[:-1]):
            if isinstance(message, HumanMessage):
                farmer_text = _message_text(message)
                break

        # Fail-open around ANY judge (built-in or injected): a broken judge
        # must never block a legitimate reply.
        try:
            violation = _get_judge()(farmer_text, _message_text(last), bool(_handoff_counts(messages)))
        except Exception:  # noqa: BLE001 - fail open on any judge failure
            log.exception("narration judge failed; failing OPEN (treating reply as clean)")
            return {}
        if not violation:
            return {}

        retry_response = retry_model.invoke(messages + [_CORRECTION_MESSAGE])
        return {"messages": [_CORRECTION_MESSAGE, retry_response]}

    return guard
