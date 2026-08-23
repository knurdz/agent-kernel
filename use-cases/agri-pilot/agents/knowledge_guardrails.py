"""Post-model guardrail for the AgriPilot knowledge specialist.

KNOWLEDGE_INSTRUCTIONS (agents/knowledge_agent.py) tell the knowledge LLM
to run every candidate chemical treatment through `validate_treatment`
before stating it. Prompts reduce unsafe replies but cannot guarantee
them: the model can still emit a final reply that names a chemical with a
dosage it never validated — exactly the hallucinated-dosage case the
deterministic safety tool exists to prevent (architecture doc, "Safety and
Treatment Validation").

This module adds a code-level backstop using an `after_model` middleware
hook, which `langchain.agents.create_agent` runs after every knowledge-agent
LLM turn. It cannot change what the model *wrote* after the fact, but it
can inspect the turn before it reaches the farmer: if the last message is
a final (non-tool-call) reply that states a known chemical together with a
dosage figure, and this turn's history does not contain an `allow`
verdict from `validate_treatment` for that chemical, the hook re-invokes
the model once with an explicit correction and lets that response take
over. If the retry makes a real `validate_treatment` call, LangGraph's own
routing executes it exactly as if the model had called it on the first try.

The check is fail-closed: a chemical whose validation verdict was `reject`
or `escalate` is treated as unvalidated, because neither verdict permits
stating a dosage. A reply that only gives non-chemical advice, or the exact
"I cannot safely recommend this" rejection wording, passes untouched.

This is a single-retry backstop, not a loop: the hook itself is not
recursive, so a still-bad retry simply proceeds to the farmer rather than
looping forever.
"""

from __future__ import annotations

import ast
import json
import re
from typing import Any, Optional

from langchain.agents.middleware import AgentMiddleware
from langchain_core.language_models import LanguageModelLike
from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool

from tools.safety_tool import known_chemical_names, known_dosage_units, resolve_chemical

VALIDATE_TOOL_NAME = "validate_treatment"

_CORRECTION_MESSAGE = SystemMessage(
    content=(
        "Your previous reply stated a chemical treatment with a dosage that "
        "was not validated this turn. This is not allowed: before any "
        "chemical name and dosage reaches the farmer you must call "
        "validate_treatment with that exact candidate first. If its verdict "
        'is "allow", include the treatment in your reply. If it is '
        '"reject", reply exactly "I cannot safely recommend this" instead '
        'of the candidate text. If it is "escalate", do not state the '
        "chemical or dosage; say it needs review by an agricultural officer."
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


def _tool_result_verdict(message: ToolMessage) -> Optional[str]:
    """Extract the "verdict" value from a validate_treatment ToolMessage."""
    raw = message.content
    if isinstance(raw, list):
        raw = " ".join(block.get("text", "") for block in raw if isinstance(block, dict))
    if not isinstance(raw, str):
        return None
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        try:
            data = ast.literal_eval(raw)
        except (ValueError, SyntaxError):
            return None
    if isinstance(data, dict):
        verdict = data.get("verdict")
        return verdict if isinstance(verdict, str) else None
    return None


def _validated_chemicals(messages: list) -> set[str]:
    """Return canonical names of chemicals validated to "allow" this turn.

    Pairs each `validate_treatment` tool call with its ToolMessage result
    by tool_call id. Calls with no result yet, or with a reject/escalate
    verdict, contribute nothing (fail-closed).
    """
    pending: dict[str, Any] = {}
    allowed: set[str] = set()
    for message in messages:
        if isinstance(message, AIMessage):
            for call in message.tool_calls or []:
                if call.get("name") == VALIDATE_TOOL_NAME:
                    pending[call["id"]] = call.get("args", {})
        elif isinstance(message, ToolMessage) and message.tool_call_id in pending:
            args = pending.pop(message.tool_call_id)
            if _tool_result_verdict(message) == "allow":
                canonical = resolve_chemical(str(args.get("chemical", "")))
                if canonical:
                    allowed.add(canonical)
    return allowed


class SafetyValidationMiddleware(AgentMiddleware):
    """`after_model` middleware enforcing validate-before-state on the knowledge agent.

    Runs after every knowledge-agent LLM turn. When the turn produced a
    final (non-tool-call) reply stating a known chemical together with a
    dosage figure that was never allowed by `validate_treatment`, it
    re-invokes the model once with an explicit correction and lets that
    response take over. If the retry makes a real `validate_treatment`
    call, LangGraph's own routing executes it exactly as if the model had
    called it on the first try.
    """

    def __init__(self, retry_model: LanguageModelLike, dosage_pattern: re.Pattern, chemical_names: frozenset):
        self.retry_model = retry_model
        self.dosage_pattern = dosage_pattern
        self.chemical_names = chemical_names

    def after_model(self, state: dict, runtime) -> dict:  # noqa: ANN001 - runtime is unused
        messages = state.get("messages") or []
        if not messages:
            return {}

        last = messages[-1]
        if not isinstance(last, AIMessage) or last.tool_calls:
            # Either not the agent's final reply, or it is mid-loop making
            # real tool calls — nothing to correct.
            return {}

        text = _message_text(last).lower()
        if not self.dosage_pattern.search(text):
            # No dosage figure stated at all (plain advice, the exact
            # rejection wording, escalation offers) — nothing to guard.
            return {}

        allowed = _validated_chemicals(messages)
        violating = any(
            re.search(rf"\b{re.escape(name)}\b", text) and (resolve_chemical(name) or name) not in allowed
            for name in self.chemical_names
        )
        if not violating:
            return {}

        retry_response = self.retry_model.invoke(messages + [_CORRECTION_MESSAGE])
        return {"messages": [_CORRECTION_MESSAGE, retry_response]}


def build_safety_validation_guard(
    model: LanguageModelLike,
    extra_tools: list[BaseTool | Any],
    chemical_names: Optional[set[str]] = None,
    dosage_units: Optional[set[str]] = None,
) -> SafetyValidationMiddleware:
    """Build the `after_model` middleware for the knowledge agent.

    :param model: The same (unbound) chat model the knowledge agent uses.
        The agent's full tool set (`extra_tools`, which must include
        `validate_treatment`) is bound to it here, so the retry call can
        make the real validation call exactly as the agent itself could.
    :param extra_tools: The knowledge agent's bound tools.
    :param chemical_names: Chemical names/aliases the detector recognizes;
        defaults to everything in `data/safety_rules.json`.
    :param dosage_units: Dosage units the detector recognizes; defaults to
        every unit used by the rules file.
    :return: A middleware instance suitable for `create_agent(middleware=...)`.
    """
    names = frozenset(chemical_names if chemical_names is not None else known_chemical_names())
    units = sorted(dosage_units if dosage_units is not None else known_dosage_units())
    dosage_pattern = re.compile(
        r"\d+(?:\.\d+)?\s*(?:" + "|".join(re.escape(unit) for unit in units) + r")",
        re.IGNORECASE,
    )
    retry_model = model.bind_tools(list(extra_tools))

    return SafetyValidationMiddleware(retry_model=retry_model, dosage_pattern=dosage_pattern, chemical_names=names)
