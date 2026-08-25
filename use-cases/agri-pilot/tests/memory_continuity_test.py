"""Wiring/prompt tests for Phase 7.3 (continue previous case).

Asserts the pronoun/topic-resolution rules are actually wired: the triage
prompt carries the resolution step over the durable profile, and the
knowledge specialist can see previous advice. The live Day 1 -> Day 3
behaviour is covered by tests/memory_continuity_e2e_test.py (`slow`).
"""

from agents.knowledge_agent import KNOWLEDGE_INSTRUCTIONS
from agents.knowledge_agent import tools as knowledge_tools
from agents.supervisor import TRIAGE_INSTRUCTIONS
from agents.supervisor import tools as supervisor_tools


def test_triage_prompt_resolves_references_via_the_profile():
    assert "get_farmer_profile" in TRIAGE_INSTRUCTIONS
    for phrase in ("it is getting worse", "the same problem", "follow_up_status"):
        assert phrase in TRIAGE_INSTRUCTIONS, f"Resolution rule missing {phrase!r}"


def test_supervisor_binds_get_farmer_profile():
    names = {getattr(t, "name", t) for t in supervisor_tools}
    assert "get_farmer_profile" in names


def test_knowledge_binds_profile_and_mentions_previous_advice():
    names = {getattr(t, "name", t) for t in knowledge_tools}
    assert "get_farmer_profile" in names
    assert "advice_summary" in KNOWLEDGE_INSTRUCTIONS
