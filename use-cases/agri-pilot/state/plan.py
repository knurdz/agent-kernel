"""Active multi-step plan state for AgriPilot (Increment 7.2).

When a request spans several dependent steps (e.g. diagnose from photo ->
treatment advice), the triage supervisor records an `ActivePlan` in the
session key-value store under `PLAN_SESSION_KEY`. If one step fails in a
recoverable way (a blurry photo), the plan records that it is waiting for
the farmer instead of being abandoned, so the original flow resumes on the
farmer's next message rather than restarting from scratch.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from agentkernel.core.base import Session

PLAN_SESSION_KEY = "active_plan"

STEP_PENDING = "pending"
STEP_DONE = "done"
STEP_AWAITING_FARMER = "awaiting_farmer"
STEP_SKIPPED = "skipped"
_VALID_STATUSES = {STEP_PENDING, STEP_DONE, STEP_AWAITING_FARMER, STEP_SKIPPED}


@dataclass
class PlanStep:
    """One ordered step of an active plan.

    :ivar description: What needs to happen, phrased for the agent's own
        bookkeeping (not shown to the farmer verbatim).
    :ivar status: One of pending / done / awaiting_farmer / skipped.
    """

    description: str
    status: str = STEP_PENDING


@dataclass
class ActivePlan:
    """An ordered, resumable plan for the current multi-step request.

    :ivar goal: Short statement of what the overall request is trying to
        achieve (e.g. "diagnose crop problem and give treatment advice").
    :ivar steps: The ordered steps; at least one must be actionable.
    """

    goal: str
    steps: list[PlanStep] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Return the plan as a plain, JSON-serializable dict."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ActivePlan":
        """Rebuild an `ActivePlan` from `to_dict` output."""
        return cls(
            goal=data.get("goal", ""),
            steps=[PlanStep(**step) for step in data.get("steps", [])],
        )

    def next_step(self) -> Optional[PlanStep]:
        """Return the first step still awaiting action, or None if finished."""
        for step in self.steps:
            if step.status in (STEP_PENDING, STEP_AWAITING_FARMER):
                return step
        return None

    def mark(self, description: str, status: str) -> bool:
        """Set the status of the step whose description matches exactly.

        :param description: Exact description of the step to update.
        :param status: New status (one of the STEP_* values).
        :return: True when a matching step was updated, False otherwise.
        :raises ValueError: If `status` is not a known status value.
        """
        if status not in _VALID_STATUSES:
            raise ValueError(f"Unknown plan step status: {status}")
        for step in self.steps:
            if step.description == description:
                step.status = status
                return True
        return False


def get_active_plan(session: Session) -> Optional[ActivePlan]:
    """Get the session's active plan, or None when no plan is recorded.

    :param session: The Agent Kernel session to read from.
    """
    stored = session.get(PLAN_SESSION_KEY)
    if stored is None:
        return None
    if isinstance(stored, ActivePlan):
        return stored
    return ActivePlan.from_dict(stored)


def set_active_plan(session: Session, plan: ActivePlan) -> ActivePlan:
    """Store an active plan on a session, replacing any existing one.

    :param session: The Agent Kernel session to write to.
    :param plan: The plan to store.
    :return: The stored plan.
    """
    return session.set(PLAN_SESSION_KEY, plan)


def clear_active_plan(session: Session) -> None:
    """Remove any active plan from a session.

    :param session: The Agent Kernel session to clear.
    """
    session.set(PLAN_SESSION_KEY, None)
