"""Unit tests for agents/supervisor_guardrails.py.

Covers the post_model_hook backstop that catches the supervisor narrating
a delegation ("I have escalated this...") without actually making the
handoff tool call, and forces a real decision via a corrective retry.

Uses a stub chat model (no real LLM/API key needed) so these tests are
fast, deterministic, and isolated from provider credentials.
"""

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from agents.supervisor_guardrails import build_narrated_delegation_guard


class _StubModel:
    """Minimal stand-in for a LangChain chat model.

    Records the tools it was bound with and the messages it was invoked
    with, and always returns a pre-set response to `.invoke`.
    """

    def __init__(self, response):
        self._response = response
        self.bound_tools = None
        self.invoke_calls = []

    def bind_tools(self, tools):
        self.bound_tools = tools
        return self

    def invoke(self, messages):
        self.invoke_calls.append(messages)
        return self._response


def _make_guard(response):
    model = _StubModel(response)
    guard = build_narrated_delegation_guard(
        model=model,
        extra_tools=["fake_get_farmer_context", "fake_update_farmer_context"],
        agent_names=["vision", "knowledge"],
    )
    return guard, model


def test_no_violation_when_last_message_has_a_real_tool_call():
    """A supervisor turn that already made a handoff call needs no correction."""
    retry_response = AIMessage(content="unused")
    guard, model = _make_guard(retry_response)

    last = AIMessage(
        content="",
        tool_calls=[{"name": "transfer_to_knowledge", "args": {}, "id": "call_1"}],
    )
    state = {"messages": [HumanMessage(content="my tomatoes have late blight"), last]}

    result = guard(state)

    assert result == {}
    assert model.invoke_calls == []


def test_no_violation_when_reply_does_not_claim_an_action():
    """A direct, non-promissory answer should pass through untouched."""
    retry_response = AIMessage(content="unused")
    guard, model = _make_guard(retry_response)

    last = AIMessage(content="Tomatoes generally need full sun and consistent watering.")
    state = {"messages": [HumanMessage(content="how do I grow tomatoes?"), last]}

    result = guard(state)

    assert result == {}
    assert model.invoke_calls == []


def test_no_violation_on_empty_message_history():
    guard, model = _make_guard(AIMessage(content="unused"))

    result = guard({"messages": []})

    assert result == {}
    assert model.invoke_calls == []


def test_no_violation_when_last_message_is_not_from_the_model():
    guard, model = _make_guard(AIMessage(content="unused"))

    state = {"messages": [HumanMessage(content="I have escalated this myself, thanks")]}

    result = guard(state)

    assert result == {}
    assert model.invoke_calls == []


def test_violation_detected_and_corrective_retry_is_invoked():
    """The classic bug: a promise with no tool call must trigger a retry."""
    retry_response = AIMessage(
        content="",
        tool_calls=[{"name": "transfer_to_knowledge", "args": {}, "id": "call_2"}],
    )
    guard, model = _make_guard(retry_response)

    human = HumanMessage(content="My tomatoes have late blight, what should I do?")
    bad_reply = AIMessage(
        content=(
            "I understand you are dealing with late blight. I have escalated "
            "your request to our knowledge base. Please hold on while I "
            "retrieve the best practices for treating late blight for you."
        )
    )
    state = {"messages": [human, bad_reply]}

    result = guard(state)

    # A correction message plus the retry response are returned for the
    # graph's `add_messages` reducer to append to state.
    assert result["messages"][0].content  # non-empty correction present
    assert isinstance(result["messages"][0], SystemMessage)
    assert result["messages"][1] is retry_response

    # The retry call must have seen the full original history plus the
    # correction, so the model has context for its second decision.
    assert len(model.invoke_calls) == 1
    invoked_messages = model.invoke_calls[0]
    assert invoked_messages[0] is human
    assert invoked_messages[1] is bad_reply
    assert isinstance(invoked_messages[2], SystemMessage)


def test_case_insensitive_and_alternate_phrasing_is_caught():
    retry_response = AIMessage(content="ok")
    guard, model = _make_guard(retry_response)

    bad_reply = AIMessage(content="CHECKING WITH our specialist agent now, one moment.")
    state = {"messages": [HumanMessage(content="hi"), bad_reply]}

    result = guard(state)

    assert len(model.invoke_calls) == 1
    assert result["messages"][1] is retry_response


def test_transfer_narration_is_caught():
    """Regression: 'transferred/initiated a transfer' phrasing (seen live on
    the market path) must trigger the correction retry like escalation does."""
    retry_response = AIMessage(
        content="",
        tool_calls=[{"name": "transfer_to_market", "args": {}, "id": "call_3"}],
    )
    guard, model = _make_guard(retry_response)

    for bad_text in (
        "I did initiate a transfer to the market specialist for your request.",
        "I’ve now transferred your request to the market specialist. " "They’ll provide you with up-to-date prices.",
    ):
        state = {"messages": [HumanMessage(content="Where should I sell my onions?"), AIMessage(content=bad_text)]}
        result = guard(state)
        assert len(model.invoke_calls) == 2 or model.invoke_calls, f"not caught: {bad_text!r}"
        assert result["messages"][1] is retry_response
        model.invoke_calls.clear()


def test_handoff_and_extra_tools_are_bound_for_the_retry_model():
    """The retry call must have the same delegation power as the supervisor."""
    guard, model = _make_guard(AIMessage(content="ok"))

    bad_reply = AIMessage(content="Let me check on that for you.")
    guard({"messages": [HumanMessage(content="hi"), bad_reply]})

    bound_names = {getattr(t, "name", t) for t in model.bound_tools}
    assert "transfer_to_vision" in bound_names
    assert "transfer_to_knowledge" in bound_names
    assert "fake_get_farmer_context" in bound_names
    assert "fake_update_farmer_context" in bound_names


def test_second_bad_reply_after_retry_is_not_looped():
    """The hook is a single-shot backstop: if the retry is itself a bad
    promise, the hook does not recurse to correct it again (that message
    would only be caught if `guard` runs again on a later graph turn)."""
    still_bad = AIMessage(content="I am checking with the specialist now.")
    guard, model = _make_guard(still_bad)

    bad_reply = AIMessage(content="Please wait while I look into this.")
    result = guard({"messages": [HumanMessage(content="hi"), bad_reply]})

    # Only one retry call is made by this single invocation of the guard.
    assert len(model.invoke_calls) == 1
    assert result["messages"][1] is still_bad
