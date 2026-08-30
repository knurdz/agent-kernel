"""Unit + wiring tests for Phase 7.2 (farmer profile storage).

State-layer tests run against a plain in-memory `Session`, mirroring
tests/test_farmer_context.py. Wiring tests assert that the durable-profile
tools are bound to the agents that must record case outcomes and that the
prompts say when — the same pattern as tests/treatment_workflow_test.py.
"""

import pytest
from agentkernel.core.base import Session

from state.farmer_context import get_farmer_context, set_farmer_context
from state.farmer_profile import (
    CASE_OPEN,
    CASE_RESOLVED,
    CaseRecord,
    FarmerProfile,
    get_farmer_profile,
    record_case,
)


def _session() -> Session:
    return Session(id="test-session")


def test_default_profile_is_empty_and_created_once():
    session = _session()
    first = get_farmer_profile(session)
    second = get_farmer_profile(session)
    assert first is second
    assert first == FarmerProfile()
    assert first.cases == []


def test_record_case_appends_dated_open_case():
    session = _session()
    profile = record_case(session, crop="tomato", disease="early blight", severity="moderate")

    assert len(profile.cases) == 1
    case = profile.cases[0]
    assert isinstance(case, CaseRecord)
    assert case.crop == "tomato"
    assert case.disease == "early blight"
    assert case.severity == "moderate"
    assert case.follow_up_status == CASE_OPEN
    assert case.date  # ISO date of the interaction is recorded


def test_record_case_updates_latest_open_case_for_same_crop():
    """Vision records the diagnosis; knowledge later adds advice to the SAME case."""
    session = _session()
    record_case(session, crop="tomato", disease="early blight")
    profile = record_case(session, crop="tomato", advice_summary="Remove affected leaves; spray copper fungicide")

    assert len(profile.cases) == 1
    case = profile.cases[0]
    assert case.disease == "early blight"
    assert "copper" in case.advice_summary


def test_record_case_appends_new_case_for_different_crop():
    session = _session()
    record_case(session, crop="tomato", disease="early blight")
    profile = record_case(session, crop="chili", disease="leaf curl")

    assert [case.crop for case in profile.cases] == ["tomato", "chili"]


def test_resolved_case_then_new_episode_appends_fresh():
    session = _session()
    record_case(session, crop="tomato", disease="early blight")
    record_case(session, crop="tomato", follow_up_status=CASE_RESOLVED)
    profile = record_case(session, crop="tomato", disease="late blight")

    assert len(profile.cases) == 2
    assert profile.latest_open_case() is profile.cases[1]
    assert profile.cases[0].follow_up_status == CASE_RESOLVED


def test_latest_helpers():
    profile = FarmerProfile(
        cases=[
            CaseRecord(crop="tomato", follow_up_status=CASE_RESOLVED),
            CaseRecord(crop="chili"),
        ]
    )
    assert profile.latest_case().crop == "chili"
    assert profile.latest_open_case().crop == "chili"
    empty = FarmerProfile()
    assert empty.latest_case() is None
    assert empty.latest_open_case() is None


def test_record_case_rejects_invalid_status():
    with pytest.raises(ValueError):
        record_case(_session(), crop="tomato", follow_up_status="done")


def test_standing_facts_mirror_farmer_context():
    session = _session()
    set_farmer_context(session, get_farmer_context(session).update(location="Kandy", growth_stage="flowering"))
    profile = record_case(session, crop="tomato")

    assert (profile.location, profile.crop, profile.growth_stage) == ("Kandy", "tomato", "flowering")
    assert profile.updated_at


# --- wiring: the tools are bound where recording must happen ---


def test_vision_binds_and_mentions_recording():
    from agents.vision_agent import VISION_INSTRUCTIONS
    from agents.vision_agent import tools as vision_tools

    names = {getattr(t, "name", t) for t in vision_tools}
    assert "record_case_outcome" in names
    assert "record_case_outcome" in VISION_INSTRUCTIONS


def test_knowledge_binds_and_mentions_recording():
    from agents.knowledge_agent import KNOWLEDGE_INSTRUCTIONS
    from agents.knowledge_agent import tools as knowledge_tools

    names = {getattr(t, "name", t) for t in knowledge_tools}
    assert "record_case_outcome" in names
    assert "get_crop_guide" in names
    assert "record_case_outcome" in KNOWLEDGE_INSTRUCTIONS
    assert "advice_summary" in KNOWLEDGE_INSTRUCTIONS
    assert "get_crop_guide" in KNOWLEDGE_INSTRUCTIONS


def test_supervisor_binds_profile_tools():
    from agents.supervisor import tools as supervisor_tools

    names = {getattr(t, "name", t) for t in supervisor_tools}
    assert {"get_farmer_profile", "record_case_outcome"} <= names
