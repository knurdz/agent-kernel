"""Unit tests for the resource workflow (Increments 5.2, 5.3).

Wiring-level assertions only (mirroring tests/treatment_workflow_test.py):
the resource agent binds the weather/treatment tools, its prompt carries
the never-invent / cached-labeling / verdict-mapping rules, and the
supervisor graph actually contains a `resource` node and delegates
RESOURCES/WEATHER intents to it. Live-LLM behaviour is covered by
tests/weather_e2e_test.py (marked `slow`).
"""

from agents.resource_agent import RESOURCE_INSTRUCTIONS
from agents.resource_agent import tools as resource_tools
from agents.supervisor import TRIAGE_INSTRUCTIONS, triage_agent
from tools.weather_tool import assess_spray_conditions, get_forecast


def test_resource_agent_binds_weather_and_treatment_tools():
    bound_names = {getattr(t, "name", t) for t in resource_tools}
    assert {"get_forecast", "assess_spray_conditions", "get_farmer_context", "update_farmer_context"} <= bound_names


def test_resource_instructions_never_invent_numbers():
    assert "Never state a number that did not come from get_forecast" in RESOURCE_INSTRUCTIONS
    assert "reliable" in RESOURCE_INSTRUCTIONS and "message" in RESOURCE_INSTRUCTIONS


def test_resource_instructions_relay_cached_label_and_cite_values():
    assert "cached" in RESOURCE_INSTRUCTIONS and "as_of" in RESOURCE_INSTRUCTIONS
    assert "Cite at least one concrete forecast value" in RESOURCE_INSTRUCTIONS


def test_resource_instructions_map_spray_verdicts():
    for verdict in ("suitable", "not suitable", "cannot determine"):
        assert verdict in RESOURCE_INSTRUCTIONS
    assert "assess_spray_conditions" in RESOURCE_INSTRUCTIONS


def test_resource_instructions_forbid_chemical_dosage_statements():
    """Resource advice must not restate chemical+dosage; that is the
    knowledge specialist's safety-validated job."""
    assert "Never state a chemical name together with a dosage" in RESOURCE_INSTRUCTIONS


def test_supervisor_graph_contains_resource_node():
    nodes = set(triage_agent.get_graph().nodes)
    assert {"vision", "knowledge", "resource"} <= nodes


def test_supervisor_delegates_resources_and_weather_to_resource():
    assert "`resource` agent" in TRIAGE_INSTRUCTIONS
    assert "irrigation" in TRIAGE_INSTRUCTIONS.lower()
    assert "spray timing" in TRIAGE_INSTRUCTIONS.lower()


def test_supervisor_keeps_fertilizer_dosages_with_knowledge():
    assert "fertilizer" in TRIAGE_INSTRUCTIONS.lower()
    assert "`knowledge` agent" in TRIAGE_INSTRUCTIONS


def test_spray_tool_registered_for_agent_use():
    """assess_spray_conditions must be importable and callable standalone."""
    result = assess_spray_conditions("kandy", days_ahead=0)
    assert result["verdict"] in ("suitable", "not suitable", "cannot determine")
    assert result["reason"]
