"""Unit + integration tests for Increment 4.3 (treatment workflow).

Covers three things:
1. Wiring: the knowledge agent binds `validate_treatment` and its prompt
   carries the validate-before-reply rule and the exact reject wording; the
   vision prompt records a diagnosed disease; the supervisor prompt chains
   vision-into-knowledge in the same turn.
2. The `agents/knowledge_guardrails.py` backstop with a stub model (no API
   key): detects replies that state a chemical+dosage without a prior
   allow verdict, and ignores safe cases.
3. A compiled-graph smoke test proving the hook's retry call is really
   executed by the tools node in langgraph 1.0.6, then pass-throughs once
   validated.

The guard unit tests use a stub model (records its tool bindings and
invocation history) so they are fast and isolated from provider
credentials, mirroring tests/supervisor_guardrules_test.py.
"""

import json

import pytest
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent

from agents.knowledge_agent import KNOWLEDGE_INSTRUCTIONS
from agents.knowledge_agent import tools as knowledge_tools
from agents.knowledge_guardrails import build_safety_validation_guard
from agents.supervisor import TRIAGE_INSTRUCTIONS
from agents.vision_agent import VISION_INSTRUCTIONS
from tools.safety_tool import validate_treatment

KNOWN_CHEMICALS = {
    "copper hydroxide",
    "copper-based fungicide",
    "copper fungicide",
    "copper oxychloride",
    "chlorothalonil",
    "mancozeb",
}
KNOWN_UNITS = {"g/l"}


class _StubModel:
    """Minimal stand-in for a LangChain chat model.

    Records the tools it was bound with and the messages it was invoked
    with; always returns a pre-set response from `.invoke`. Matches the
    pattern used in tests/supervisor_guardrails_test.py.
    """

    def __init__(self, response):
        self._response = response
        self.bound_tools = None
        self.invoke_calls = []

    def bind_tools(self, tools):
        self.bound_tools = list(tools)
        return self

    def invoke(self, messages):
        self.invoke_calls.append(messages)
        return self._response


def _tool_call_msg(name, args, call_id):
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id}])


def _tool_result_msg(call_id, verdict):
    return ToolMessage(content=json.dumps({"verdict": verdict, "reason": "checked"}), tool_call_id=call_id)


def _guard(response=None):
    """Build a guard backed by a stub model and real rules + validate_treatment."""
    model = _StubModel(response if response is not None else AIMessage(content="ok"))
    guard = build_safety_validation_guard(
        model=model,
        extra_tools=[validate_treatment],
        chemical_names=KNOWN_CHEMICALS,
        dosage_units=KNOWN_UNITS,
    )
    return guard, model


# ---------------------------------------------------------------------------
# 1. Wiring tests
# ---------------------------------------------------------------------------


def test_knowledge_agent_binds_validate_treatment():
    bound_names = {getattr(t, "name", t) for t in knowledge_tools}
    assert "validate_treatment" in bound_names


def test_knowledge_instructions_mandate_validation_and_exact_reject_phrase():
    assert "validate_treatment" in KNOWLEDGE_INSTRUCTIONS
    assert "I cannot safely recommend this" in KNOWLEDGE_INSTRUCTIONS
    assert "allow" in KNOWLEDGE_INSTRUCTIONS and "reject" in KNOWLEDGE_INSTRUCTIONS


def test_vision_instructions_record_disease():
    assert "disease" in VISION_INSTRUCTIONS and "update_farmer_context" in VISION_INSTRUCTIONS


def test_supervisor_chains_vision_into_knowledge_same_turn():
    assert "knowledge" in TRIAGE_INSTRUCTIONS
    assert "diagnosis" in TRIAGE_INSTRUCTIONS.lower()


# ---------------------------------------------------------------------------
# 2. Guard unit tests
# ---------------------------------------------------------------------------


def test_unvalidated_chemical_plus_dosage_triggers_correction():
    guard, model = _guard(response=AIMessage(content="retry text"))
    bad_reply = AIMessage(content="Apply copper hydroxide at 3 g/L at the first sign of disease.")
    state = {"messages": [HumanMessage(content="what should I spray?"), bad_reply]}

    result = guard(state)

    assert len(model.invoke_calls) == 1
    correction, retry = result["messages"]
    assert isinstance(correction, SystemMessage)
    assert retry is model._response
    # The retry saw the full original history plus the correction.
    assert model.invoke_calls[0][0] is state["messages"][0]
    assert model.invoke_calls[0][1] is bad_reply
    assert model.invoke_calls[0][2] is correction


def test_invalidated_by_alias_too():
    """An alias for a known chemical is caught just like the canonical name."""
    guard, model = _guard(response=AIMessage(content="ok"))
    bad_reply = AIMessage(content="Use a copper-based fungicide at 3 g/L.")
    result = guard({"messages": [HumanMessage(content="x"), bad_reply]})
    assert len(model.invoke_calls) == 1
    assert isinstance(result["messages"][0], SystemMessage)


def test_allow_verdict_this_turn_passes_through():
    guard, model = _guard()
    history = [
        HumanMessage(content="what should I do for early blight?"),
        _tool_call_msg("validate_treatment", {"chemical": "copper hydroxide", "dosage": 3.0, "unit": "g/L"}, "c1"),
        _tool_result_msg("c1", "allow"),
        AIMessage(content="Apply copper hydroxide at 3 g/L."),
    ]
    result = guard({"messages": history})
    assert result == {}
    assert model.invoke_calls == []


def test_reject_verdict_with_dosage_still_stated_is_corrected():
    """Fail-closed: a reject verdict does NOT permit restating the dosage —
    the chemical+dosage pair must go through the guard just like an unknown."""
    guard, model = _guard(response=AIMessage(content="retry"))
    history = [
        HumanMessage(content="x"),
        _tool_call_msg("validate_treatment", {"chemical": "mancozeb", "dosage": 9.0, "unit": "g/L"}, "c1"),
        _tool_result_msg("c1", "reject"),
        AIMessage(content="Apply mancozeb at 9 g/L."),
    ]
    result = guard({"messages": history})
    assert len(model.invoke_calls) == 1
    assert isinstance(result["messages"][0], SystemMessage)


def test_escalate_verdict_is_fail_closed():
    """An escalate verdict (chemical not on allow-list) also forbids stating
    a dosage, so restating it is corrected."""
    guard, model = _guard(response=AIMessage(content="retry"))
    history = [
        HumanMessage(content="x"),
        _tool_call_msg("validate_treatment", {"chemical": "mancozeb", "dosage": 1.0, "unit": "g/L"}, "c1"),
        _tool_result_msg("c1", "escalate"),
        AIMessage(content="Apply mancozeb at 1 g/L pending an officer review."),
    ]
    result = guard({"messages": history})
    assert len(model.invoke_calls) == 1
    assert isinstance(result["messages"][0], SystemMessage)


def test_dosage_without_known_chemical_passes_through():
    """'apply 3 g/L' alone (no named chemical) is outside this guard's scope."""
    guard, model = _guard()
    bad_reply = AIMessage(content="Apply 3 g/L of the protectant.")
    result = guard({"messages": [HumanMessage(content="x"), bad_reply]})
    assert result == {}
    assert model.invoke_calls == []


def test_exact_reject_phrase_is_not_flagged():
    guard, model = _guard()
    reply = AIMessage(content="I cannot safely recommend this.")
    result = guard({"messages": [HumanMessage(content="x"), reply]})
    assert result == {}
    assert model.invoke_calls == []


def test_mid_loop_tool_call_message_passes_through():
    guard, model = _guard()
    last = AIMessage(content="", tool_calls=[{"name": "validate_treatment", "args": {}, "id": "call_1"}])
    result = guard({"messages": [HumanMessage(content="x"), last]})
    assert result == {}
    assert model.invoke_calls == []


def test_empty_history_passes_through():
    guard, model = _guard()
    assert guard({"messages": []}) == {}
    assert model.invoke_calls == []


def test_non_final_message_is_not_the_last_is_not_corrected():
    """Only an AIMessage as the final message is a candidate for correction."""
    guard, model = _guard()
    result = guard({"messages": [HumanMessage(content="I have escalated this myself")]})
    assert result == {}


def test_single_shot_no_recursion_on_still_bad_retry():
    """The hook is single-shot: if its own retry is also bad, the hook does
    not correct again — it returns the retry response as-is."""
    still_bad = AIMessage(content="Still apply copper hydroxide at 3 g/L")
    guard, model = _guard(response=still_bad)

    bad_reply = AIMessage(content="Apply copper hydroxide at 3 g/L.")
    result = guard({"messages": [HumanMessage(content="x"), bad_reply]})

    assert len(model.invoke_calls) == 1
    # returned the retry verbatim, did not loop
    assert result["messages"][1] is still_bad


# ---------------------------------------------------------------------------
# 3. Compiled-graph smoke test (proves retry tool call really executes)
# ---------------------------------------------------------------------------


class _BindableFake(FakeMessagesListChatModel):
    """FakeMessagesListChatModel that also supports bind_tools (cycling)."""

    def bind_tools(self, tools):
        object.__setattr__(self, "bound_tools", list(tools))
        return self


@tool
def _fake_validate(chemical: str, dosage: float, unit: str) -> dict:
    """Fake validate_treatment for the graph smoke test."""
    return {"verdict": "allow", "reason": "ok"}


def test_hook_retry_tool_call_executes_then_passes_through():
    """Full micro-cycle: violation -> correction+retry -> tool exec -> pass."""
    main = _BindableFake(
        responses=[
            AIMessage(content="Apply copper hydroxide at 3 g/L at first sign."),
            AIMessage(content="Validated: apply copper hydroxide at 3 g/L."),
        ]
    )
    retry = _BindableFake(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "_fake_validate",
                        "args": {"chemical": "copper hydroxide", "dosage": 3.0, "unit": "g/L"},
                        "id": "call_9",
                    }
                ],
            )
        ]
    )

    guard = build_safety_validation_guard(
        model=retry, extra_tools=[_fake_validate], chemical_names=KNOWN_CHEMICALS, dosage_units=KNOWN_UNITS
    )
    agent = create_react_agent(model=main, tools=[_fake_validate], prompt="be a knowledge agent", post_model_hook=guard)
    result = agent.invoke({"messages": [HumanMessage(content="what should I spray?")]})

    # The guard's corrective retry happened (correction message present).
    assert any(isinstance(m, SystemMessage) for m in result["messages"])
    # The validate tool was actually executed by the tools node (ToolMessage present).
    assert any(isinstance(m, ToolMessage) for m in result["messages"])
    # And the run terminated cleanly: a final plain AIMessage with no tool_calls.
    final = [m for m in result["messages"] if isinstance(m, AIMessage) and not m.tool_calls]
    assert final
    assert "3 g/L" in final[-1].content


def test_guard_can_be_built_from_real_rules():
    """Smoke: the real rules file yields names and units usable by the guard."""
    from tools.safety_tool import known_chemical_names, known_dosage_units

    names = known_chemical_names()
    units = known_dosage_units()
    assert "copper hydroxide" in names
    assert "g/l" in units
