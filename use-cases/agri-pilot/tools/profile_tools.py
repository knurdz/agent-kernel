"""Farmer profile tools for AgriPilot agents (Phase 7.2).

These are the tool functions the triage and specialist agents call to read
the durable farmer profile (standing facts + case history) and to record a
completed diagnosis/advice episode. They deliberately follow the un-guarded
`context_tools.py` pattern: they read local session state, not external
services, so per-session call limits and timeouts do not apply. See
architecture doc memory-update section.
"""

from __future__ import annotations

from typing import Any, Optional

from state.farmer_profile import current_farmer_profile, record_current_case


def get_farmer_profile() -> dict[str, Any]:
    """Return the farmer's durable profile: standing facts plus case history.

    Call this before asking the farmer about past problems — the profile
    records every completed diagnosis/advice episode with crop, disease,
    severity, advice given, date, and follow-up status. Use it to resolve
    references like "it" or "the same problem" to an earlier case instead
    of asking the farmer to repeat themselves.
    """
    return current_farmer_profile().to_dict()


def record_case_outcome(
    crop: str,
    disease: Optional[str] = None,
    severity: Optional[str] = None,
    advice_summary: Optional[str] = None,
    follow_up_status: Optional[str] = None,
) -> dict[str, Any]:
    """Record one completed diagnosis/advice episode in the case history.

    Call this after a successful diagnosis-and-advice interaction. The
    vision specialist passes the crop and diagnosed disease; the knowledge
    specialist adds a short advice summary of the validated recommendation.
    Only pass fields you have a real value for; `disease` must be an actual
    diagnosis, never a guess. If the latest open case is for the same crop,
    it is updated in place; otherwise a new dated case is appended. Mark
    `follow_up_status` "resolved" only when the farmer confirms the problem
    is dealt with.
    """
    updated = record_current_case(
        crop=crop,
        disease=disease,
        severity=severity,
        advice_summary=advice_summary,
        follow_up_status=follow_up_status,
    )
    return updated.to_dict()
