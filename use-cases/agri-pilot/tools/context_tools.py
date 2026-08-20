"""Farmer context tools for AgriPilot agents.

These are the tool functions the triage (and later specialist) agents call
to read what is already known about the farmer before asking a question
they don't need to ask, and to record new facts as the farmer provides
them. See architecture doc section 13, "Information Sufficiency Check".
"""

from __future__ import annotations

from typing import Any, Optional

from state.farmer_context import current_farmer_context, update_current_farmer_context


def get_farmer_context() -> dict[str, Any]:
    """Return everything currently known about the farmer and this conversation.

    Call this before asking the farmer for information (language, location,
    crop, growth_stage, previous_case, input_type, intent) to check whether
    it is already known, so you don't ask redundant questions.
    """
    return current_farmer_context().to_dict()


def update_farmer_context(
    language: Optional[str] = None,
    location: Optional[str] = None,
    crop: Optional[str] = None,
    growth_stage: Optional[str] = None,
    previous_case: Optional[str] = None,
    input_type: Optional[str] = None,
    intent: Optional[str] = None,
) -> dict[str, Any]:
    """Record new facts about the farmer or the current conversation.

    Call this whenever the farmer states or implies a fact for one of these
    fields (e.g. names a crop, states their language, or the intent has
    been classified). Only pass the fields you have a new value for; omitted
    fields keep their previously stored value.
    """
    changes = {
        "language": language,
        "location": location,
        "crop": crop,
        "growth_stage": growth_stage,
        "previous_case": previous_case,
        "input_type": input_type,
        "intent": intent,
    }
    changes = {key: value for key, value in changes.items() if value is not None}
    return update_current_farmer_context(**changes).to_dict()
