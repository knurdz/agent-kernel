"""Unit tests for the market workflow (Increments 6.2, 6.3).

Wiring-level assertions only (mirroring tests/resource_workflow_test.py):
the market agent binds the price tools, its prompt carries the
never-invent / relay-and-stop / staleness / rank-two rules, and the
supervisor graph actually contains a `market` node and delegates MARKET
intents to it. Live-LLM behaviour is covered by tests/market_e2e_test.py
(marked `slow`).
"""

from agents.market_agent import MARKET_INSTRUCTIONS
from agents.market_agent import tools as market_tools
from agents.supervisor import TRIAGE_INSTRUCTIONS, triage_agent
from tools.market_tool import get_price


def test_market_agent_binds_price_and_context_tools():
    bound_names = {getattr(t, "name", t) for t in market_tools}
    assert {"get_price", "get_farmer_context", "update_farmer_context"} <= bound_names


def test_market_instructions_never_invent_prices():
    assert "Never state a price that did not come from get_price" in MARKET_INSTRUCTIONS
    assert "reliable" in MARKET_INSTRUCTIONS and "message" in MARKET_INSTRUCTIONS


def test_market_instructions_relay_and_stop_on_no_data():
    """Unknown crop / missing location: relay the limitation and stop —
    no guessing, no substitute crops."""
    flat = " ".join(MARKET_INSTRUCTIONS.split())
    assert "relay `message` plainly and stop" in flat
    assert "do not guess, estimate from memory, or substitute a different crop" in flat


def test_market_instructions_rank_at_least_two_markets_with_concrete_values():
    assert "AT LEAST TWO markets" in MARKET_INSTRUCTIONS
    assert "price_per_kg" in MARKET_INSTRUCTIONS and "estimated_revenue" in MARKET_INSTRUCTIONS


# ---------------------------------------------------------------------------
# Increment 6.3 — staleness handling rule in the prompt
# ---------------------------------------------------------------------------


def test_market_instructions_check_freshness_before_citing_prices():
    assert "data_freshness" in MARKET_INSTRUCTIONS
    assert "stale" in MARKET_INSTRUCTIONS
    assert "`as_of`" in MARKET_INSTRUCTIONS


def test_tool_registered_for_agent_use():
    """get_price must be importable and callable standalone."""
    result = get_price("tomato", "kandy")
    assert result["reliable"] is True
    assert len(result["options"]) >= 2


# ---------------------------------------------------------------------------
# Supervisor wiring
# ---------------------------------------------------------------------------


def test_supervisor_graph_contains_market_node():
    nodes = set(triage_agent.get_graph().nodes)
    assert {"vision", "knowledge", "resource", "market"} <= nodes


def test_supervisor_delegates_market_intents_to_market():
    assert "`market` agent" in TRIAGE_INSTRUCTIONS
    assert "MARKET" in TRIAGE_INSTRUCTIONS
    assert "selling recommendation" in TRIAGE_INSTRUCTIONS.lower() or "price" in TRIAGE_INSTRUCTIONS.lower()


def test_supervisor_no_longer_defers_market_to_later_phase():
    assert "no specialist exists yet" not in TRIAGE_INSTRUCTIONS
    assert "coming soon" not in TRIAGE_INSTRUCTIONS.lower()
