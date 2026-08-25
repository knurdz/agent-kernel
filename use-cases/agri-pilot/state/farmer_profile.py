"""Durable farmer profile and case history for AgriPilot (Phase 7.2).

Where `FarmerContext` is the working state of the current conversation,
`FarmerProfile` is the durable record: standing facts (location, crop,
growth stage) plus a case history — crop, disease, severity, previous
advice, date, and follow-up status for every completed diagnosis/advice
episode (architecture doc memory-update section). It is stored in the
Agent Kernel `Session` key-value store under `PROFILE_SESSION_KEY`, so with
the Redis session store (Phase 7.1) it survives restarts and lets later
messages resolve references like "it is getting worse" to an earlier case
(Phase 7.3) without asking the farmer to repeat anything.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from agentkernel.core.base import Session
from agentkernel.core.tool import ToolContext

from state.farmer_context import get_farmer_context

PROFILE_SESSION_KEY = "farmer_profile"

CASE_OPEN = "open"
CASE_RESOLVED = "resolved"
_VALID_FOLLOW_UP = {CASE_OPEN, CASE_RESOLVED}


def _today() -> str:
    """Today's date as an ISO string (the interaction date on a CaseRecord)."""
    return datetime.now(timezone.utc).date().isoformat()


def _now() -> str:
    """Current UTC timestamp as an ISO string (the profile's updated_at)."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class CaseRecord:
    """One recorded crop-problem episode.

    :ivar crop: The crop under treatment (e.g. "tomato").
    :ivar disease: The diagnosed disease, only ever a name that was actually
        diagnosed by the vision specialist or stated by the farmer.
    :ivar severity: Severity when known ("mild", "moderate", "severe"),
        as stated by the farmer or reported by a specialist.
    :ivar advice_summary: One-or-two sentence summary of the validated
        advice given, so follow-ups can build on it without re-retrieval.
    :ivar date: ISO date of the interaction that produced this record.
    :ivar follow_up_status: "open" while the problem is being worked on,
        "resolved" once the farmer confirms it is dealt with.
    """

    crop: str
    disease: Optional[str] = None
    severity: Optional[str] = None
    advice_summary: Optional[str] = None
    date: str = ""
    follow_up_status: str = CASE_OPEN


@dataclass
class FarmerProfile:
    """Durable per-session farmer profile.

    :ivar location: Standing fact mirrored from FarmerContext at write time.
    :ivar crop: Current crop of interest (standing fact).
    :ivar growth_stage: Growth stage of that crop, when known.
    :ivar cases: Chronological case history; the last entry is the most recent.
    :ivar updated_at: UTC timestamp of the last profile write.
    """

    location: Optional[str] = None
    crop: Optional[str] = None
    growth_stage: Optional[str] = None
    cases: list[CaseRecord] = field(default_factory=list)
    updated_at: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Return the profile as a plain, JSON-serializable dict."""
        return asdict(self)

    def latest_case(self) -> Optional[CaseRecord]:
        """The most recent case record, or None when history is empty."""
        return self.cases[-1] if self.cases else None

    def latest_open_case(self) -> Optional[CaseRecord]:
        """The most recent case still marked open, or None."""
        for case in reversed(self.cases):
            if case.follow_up_status == CASE_OPEN:
                return case
        return None


def get_farmer_profile(session: Session) -> FarmerProfile:
    """Get the `FarmerProfile` for a session, creating an empty one if absent.

    :param session: The Agent Kernel session to read from.
    :return: The session's `FarmerProfile`.
    """
    stored = session.get(PROFILE_SESSION_KEY)
    if stored is None:
        stored = FarmerProfile()
        session.set(PROFILE_SESSION_KEY, stored)
    return stored


def set_farmer_profile(session: Session, profile: FarmerProfile) -> FarmerProfile:
    """Store a `FarmerProfile` on a session, replacing any existing one.

    :param session: The Agent Kernel session to write to.
    :param profile: The profile to store.
    :return: The stored profile.
    """
    return session.set(PROFILE_SESSION_KEY, profile)


def current_farmer_profile() -> FarmerProfile:
    """Get the `FarmerProfile` for the currently executing tool call.

    Must be called from within a tool function running inside an agent,
    i.e. where `ToolContext.get()` succeeds.

    :return: The current session's `FarmerProfile`.
    """
    return get_farmer_profile(ToolContext.get().session)


def record_case(
    session: Session,
    crop: str,
    disease: Optional[str] = None,
    severity: Optional[str] = None,
    advice_summary: Optional[str] = None,
    follow_up_status: Optional[str] = None,
) -> FarmerProfile:
    """Append to, or update, the session's case history and store it.

    Mirrors the standing facts (location, crop, growth stage) from the
    session's `FarmerContext`, then targets the latest OPEN case for the
    same crop: one is updated in place with any provided fields, otherwise
    a new `CaseRecord` dated today is appended. This lets the vision and
    knowledge specialists each contribute their part of one episode
    (diagnosis first, validated advice second) without creating duplicates.

    :param session: The Agent Kernel session to write to.
    :param crop: Crop under treatment (required).
    :param disease: Diagnosed disease name, when newly diagnosed.
    :param severity: Severity, when stated or judged.
    :param advice_summary: Short summary of validated advice given.
    :param follow_up_status: New status; must be "open" or "resolved".
    :return: The stored, updated `FarmerProfile`.
    :raises ValueError: If `follow_up_status` is not a valid status.
    """
    if follow_up_status is not None and follow_up_status not in _VALID_FOLLOW_UP:
        raise ValueError(f"follow_up_status must be one of {sorted(_VALID_FOLLOW_UP)}, got {follow_up_status!r}")

    profile = get_farmer_profile(session)

    # Mirror standing facts from the conversation context so the profile
    # stays consistent with what the agents already recorded there.
    ctx = get_farmer_context(session)
    if ctx.location:
        profile.location = ctx.location
    if ctx.growth_stage:
        profile.growth_stage = ctx.growth_stage
    profile.crop = crop

    target: Optional[CaseRecord] = None
    for case in reversed(profile.cases):
        if case.follow_up_status == CASE_OPEN and case.crop.strip().lower() == crop.strip().lower():
            target = case
            break

    if target is None:
        target = CaseRecord(crop=crop, date=_today())
        profile.cases.append(target)
    if disease is not None:
        target.disease = disease
    if severity is not None:
        target.severity = severity
    if advice_summary is not None:
        target.advice_summary = advice_summary
    if follow_up_status is not None:
        target.follow_up_status = follow_up_status
    profile.updated_at = _now()

    return set_farmer_profile(session, profile)


def record_current_case(
    crop: str,
    disease: Optional[str] = None,
    severity: Optional[str] = None,
    advice_summary: Optional[str] = None,
    follow_up_status: Optional[str] = None,
) -> FarmerProfile:
    """Record a case outcome for the currently executing tool call's session.

    Must be called from within a tool function running inside an agent,
    i.e. where `ToolContext.get()` succeeds.

    :param crop: Crop under treatment (required).
    :param disease: Diagnosed disease name, when newly diagnosed.
    :param severity: Severity, when stated or judged.
    :param advice_summary: Short summary of validated advice given.
    :param follow_up_status: New status; must be "open" or "resolved".
    :return: The stored, updated `FarmerProfile`.
    """
    session = ToolContext.get().session
    return record_case(
        session,
        crop=crop,
        disease=disease,
        severity=severity,
        advice_summary=advice_summary,
        follow_up_status=follow_up_status,
    )
