"""Unit tests for state/farmer_context.py (Increment 1.1)."""

import pytest
from agentkernel.core.base import Session

from state.farmer_context import FarmerContext, get_farmer_context, set_farmer_context


def test_default_context_is_empty():
    session = Session(id="test-session")
    assert get_farmer_context(session) == FarmerContext()


def test_get_farmer_context_creates_once_and_persists():
    session = Session(id="test-session")
    first = get_farmer_context(session)
    second = get_farmer_context(session)
    assert first is second


@pytest.mark.parametrize(
    "field, value",
    [
        ("language", "si"),
        ("location", "Kandy"),
        ("crop", "tomato"),
        ("growth_stage", "flowering"),
        ("previous_case", "early blight, moderate"),
        ("input_type", "text+image"),
        ("intent", "CROP_HEALTH"),
    ],
)
def test_set_and_read_each_field(field, value):
    session = Session(id="test-session")
    updated = get_farmer_context(session).update(**{field: value})
    set_farmer_context(session, updated)

    assert getattr(get_farmer_context(session), field) == value


def test_update_rejects_unknown_field():
    with pytest.raises(TypeError):
        FarmerContext().update(unknown_field="x")
