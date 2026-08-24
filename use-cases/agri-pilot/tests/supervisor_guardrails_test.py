"""Unit tests for agents/supervisor_guardrails.py.

Covers the post_model_hook backstop that catches the supervisor narrating
an action ("I have escalated this...", "transferred your request",
"provided the steps above") without actually making the handoff call or
including the content, and forces a real decision via a corrective retry.

Detection is an LLM judge (`build_narration_judge`), not word patterns:
these tests inject a stub judge so they are fast, deterministic, and
isolated from provider credentials.
"""

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from agents.supervisor_guardrails import (
    _parse_judge_verdict,
    build_narrated_delegation_guard,
    build_narration_judge,
)


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


class _StubJudge:
    """Stand-in for the narration judge: preset verdict, records calls.

    `verdict` may be a bool or a callable(farmer_text, reply_text,
    specialist_consulted) -> bool.
    """

    def __init__(self, verdict=True):
        self.verdict = verdict
        self.calls = []

    def __call__(self, farmer_text, reply_text, specialist_consulted):
        self.calls.append((farmer_text, reply_text, specialist_consulted))
        if callable(self.verdict):
            return self.verdict(farmer_text, reply_text, specialist_consulted)
        return self.verdict


class _StubJudgeModel:
    """Stand-in for the judge's chat model: returns pre-set content."""

    def __init__(self, content):
        self.content = content
        self.invoke_calls = []

    def invoke(self, messages):
        self.invoke_calls.append(messages)
        return AIMessage(content=self.content)


def _make_guard(response, judge):
    model = _StubModel(response)
    guard = build_narrated_delegation_guard(
        model=model,
        extra_tools=["fake_get_farmer_context", "fake_update_farmer_context"],
        agent_names=["vision", "knowledge"],
        judge=judge,
    )
    return guard, model


# ---------------------------------------------------------------------------
# Guard flow: which turns reach the judge at all
# ---------------------------------------------------------------------------


def test_no_judge_call_when_last_message_has_a_real_tool_call():
    """A supervisor turn that already made a handoff call needs no correction."""
    judge = _StubJudge(True)
    guard, model = _make_guard(AIMessage(content="unused"), judge)

    last = AIMessage(
        content="",
        tool_calls=[{"name": "transfer_to_knowledge", "args": {}, "id": "call_1"}],
    )
    state = {"messages": [HumanMessage(content="my tomatoes have late blight"), last]}

    result = guard(state)

    assert result == {}
    assert judge.calls == []
    assert model.invoke_calls == []


def test_no_violation_when_reply_does_not_claim_an_action():
    """A direct, non-promissory answer should pass through untouched."""
    judge = _StubJudge(False)
    guard, model = _make_guard(AIMessage(content="unused"), judge)

    last = AIMessage(content="Tomatoes generally need full sun and consistent watering.")
    state = {"messages": [HumanMessage(content="how do I grow tomatoes?"), last]}

    result = guard(state)

    assert result == {}
    assert model.invoke_calls == []


def test_promise_like_wording_passes_when_judge_says_clean():
    """Regression for the regex removal: word matching is gone — a reply
    that merely contains promise-shaped words must NOT be corrected unless
    the meaning-based judge flags it."""
    judge = _StubJudge(False)
    guard, model = _make_guard(AIMessage(content="unused"), judge)

    last = AIMessage(content="Please wait here while I check — the gate opens at noon.")
    state = {"messages": [HumanMessage(content="is the farm gate open?"), last]}

    assert guard(state) == {}
    assert model.invoke_calls == []
    # The judge, not a pattern list, decided.
    assert judge.calls[-1][1] == last.content


def test_no_judge_call_on_empty_message_history():
    judge = _StubJudge(True)
    guard, model = _make_guard(AIMessage(content="unused"), judge)

    result = guard({"messages": []})

    assert result == {}
    assert judge.calls == []


def test_no_judge_call_when_last_message_is_not_from_the_model():
    judge = _StubJudge(True)
    guard, model = _make_guard(AIMessage(content="unused"), judge)

    state = {"messages": [HumanMessage(content="I have escalated this myself, thanks")]}

    result = guard(state)

    assert result == {}
    assert judge.calls == []


# ---------------------------------------------------------------------------
# Judge inputs: what the judge gets to see
# ---------------------------------------------------------------------------


def test_judge_receives_farmer_text_reply_and_specialist_flag():
    judge = _StubJudge(False)
    guard, _ = _make_guard(AIMessage(content="unused"), judge)

    state = {
        "messages": [
            HumanMessage(content="When should I irrigate my onions?"),
            AIMessage("", tool_calls=[{"name": "transfer_to_resource", "args": {}, "id": "c0"}]),
            AIMessage(content="Water them early tomorrow morning."),
        ]
    }
    guard(state)

    assert judge.calls[-1] == ("When should I irrigate my onions?", "Water them early tomorrow morning.", True)


def test_judge_sees_no_specialist_consulted_without_prior_handoff():
    judge = _StubJudge(False)
    guard, _ = _make_guard(AIMessage(content="unused"), judge)

    state = {
        "messages": [
            HumanMessage(content="When should I irrigate my onions?"),
            AIMessage(content="I did initiate a transfer to the resource specialist."),
        ]
    }
    guard(state)

    assert judge.calls[-1] == (
        "When should I irrigate my onions?",
        "I did initiate a transfer to the resource specialist.",
        False,
    )


# ---------------------------------------------------------------------------
# Violation path: corrective retry
# ---------------------------------------------------------------------------


def test_violation_detected_and_corrective_retry_is_invoked():
    """The classic bug: a promise with no tool call must trigger a retry."""
    retry_response = AIMessage(
        content="",
        tool_calls=[{"name": "transfer_to_knowledge", "args": {}, "id": "call_2"}],
    )
    judge = _StubJudge(True)
    guard, model = _make_guard(retry_response, judge)

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
    assert isinstance(result["messages"][0], SystemMessage)
    assert result["messages"][0].content  # non-empty correction present
    assert result["messages"][1] is retry_response

    # The retry call must have seen the full original history plus the
    # correction, so the model has context for its second decision.
    assert len(model.invoke_calls) == 1
    invoked_messages = model.invoke_calls[0]
    assert invoked_messages[0] is human
    assert invoked_messages[1] is bad_reply
    assert isinstance(invoked_messages[2], SystemMessage)


@pytest.mark.parametrize(
    "bad_text",
    [
        "I have escalated your request to our knowledge base.",
        "I did initiate a transfer to the resource specialist for your request.",
        "I’ve now transferred your request to the resource specialist. They’ll provide up-to-date advice.",
        "I have provided the steps above.",  # claimed delivery, nothing delivered
        "As shared above, apply 2 ml per litre.",  # same class, different words
    ],
)
def test_all_three_violation_classes_trigger_retry(bad_text):
    """Live-failure regressions across all three judge categories: claimed
    handoff (incl. 'transferred', seen on the resource path), promised action,
    and claimed-but-absent delivery."""
    retry_response = AIMessage(content="", tool_calls=[{"name": "transfer_to_resource", "args": {}, "id": "c3"}])
    judge = _StubJudge(True)
    guard, model = _make_guard(retry_response, judge)

    state = {"messages": [HumanMessage(content="When should I irrigate my onions?"), AIMessage(content=bad_text)]}
    result = guard(state)

    assert model.invoke_calls, f"not caught: {bad_text!r}"
    assert result["messages"][1] is retry_response


def test_correction_message_covers_both_arms():
    """The correction must offer BOTH fixes: make the real call, or include
    the actual information in the reply (the claimed-delivery arm)."""
    judge = _StubJudge(True)
    guard, model = _make_guard(AIMessage(content="ok"), judge)

    state = {"messages": [HumanMessage(content="hi"), AIMessage(content="Provided above.")]}
    guard(state)

    correction = model.invoke_calls[0][-1]
    assert "specialist" in correction.content.lower()
    assert "actual information" in correction.content.lower()


def test_handoff_and_extra_tools_are_bound_for_the_retry_model():
    """The retry call must have the same delegation power as the supervisor."""
    guard, model = _make_guard(AIMessage(content="ok"), _StubJudge(True))

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
    guard, model = _make_guard(still_bad, _StubJudge(True))

    bad_reply = AIMessage(content="Please wait while I look into this.")
    result = guard({"messages": [HumanMessage(content="hi"), bad_reply]})

    # Only one retry call is made by this single invocation of the guard.
    assert len(model.invoke_calls) == 1
    assert result["messages"][1] is still_bad


# ---------------------------------------------------------------------------
# Judge resilience: fail-open, ambiguous verdicts
# ---------------------------------------------------------------------------


def test_judge_exception_fails_open():
    """A broken judge must never block a legitimate reply path."""

    def boom(farmer_text, reply_text, specialist_consulted):
        raise ConnectionError("judge provider down")

    retry_response = AIMessage(content="unused")
    guard, model = _make_guard(retry_response, boom)

    state = {"messages": [HumanMessage(content="hi"), AIMessage(content="I transferred your request.")]}
    result = guard(state)

    assert result == {}
    assert model.invoke_calls == []


def test_unparseable_judge_answer_counts_as_violation():
    """Recall-biased parsing: garbage output triggers the retry rather than
    letting a possible false claim through."""
    assert _parse_judge_verdict("TRUE") is True
    assert _parse_judge_verdict("FALSE") is False
    assert _parse_judge_verdict("yes") is True
    assert _parse_judge_verdict("no.") is False
    assert _parse_judge_verdict("") is True
    assert _parse_judge_verdict("The reply seems problematic") is True
    assert _parse_judge_verdict("true... false... maybe?") is True  # both -> ambiguous


def test_build_narration_judge_parses_model_output_and_fails_open():
    judge = build_narration_judge(_StubJudgeModel("TRUE"))
    assert judge("hi", "I escalated this.", False) is True

    judge = build_narration_judge(_StubJudgeModel("FALSE"))
    assert judge("hi", "Tomatoes need sun.", False) is False

    class _Boom:
        def invoke(self, messages):
            raise TimeoutError("provider down")

    assert build_narration_judge(_Boom())("hi", "anything", False) is False
