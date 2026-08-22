"""Active-plan tools for the AgriPilot triage supervisor (Increment 7.2).

These let the supervisor record, inspect and advance a multi-step plan in
the session so an interrupted flow (e.g. "ask for a closer photo") resumes
where it left off instead of restarting from scratch.
"""

from __future__ import annotations

from typing import Any

from agentkernel.core.tool import ToolContext

from state.plan import (
    STEP_DONE,
    ActivePlan,
    PlanStep,
    clear_active_plan as clear_session_plan,
    get_active_plan as read_session_plan,
    set_active_plan as store_session_plan,
)


def get_active_plan() -> dict[str, Any]:
    """Return the current multi-step plan for this conversation, if any.

    Call this at the start of handling a request that may continue earlier
    work (especially crop-health requests after a photo was rejected). If
    `plan` is not None, resume from its next pending or awaiting_farmer
    step instead of starting over; if None there is nothing to resume.
    """
    session = ToolContext.get().session
    plan = read_session_plan(session)
    return {"plan": plan.to_dict() if plan else None}


def set_active_plan(goal: str, steps: list[str]) -> dict[str, Any]:
    """Record a new ordered plan for the current multi-step request.

    Call this when a request spans several dependent steps and one of them
    needs input from the farmer (e.g. a better photo), so later turns can
    resume instead of restarting. Pass the steps in execution order as
    short descriptions.

    :param goal: What the overall request is trying to achieve.
    :param steps: Ordered step descriptions.
    :return: The stored plan.
    """
    session = ToolContext.get().session
    plan = ActivePlan(goal=goal, steps=[PlanStep(description=step.strip()) for step in steps if step.strip()])
    store_session_plan(session, plan)
    return {"plan": plan.to_dict()}


def mark_plan_step(step_description: str, status: str = STEP_DONE) -> dict[str, Any]:
    """Update the status of one step of the active plan.

    Use status "done" once a step is completed, "awaiting_farmer" while
    waiting for something from the farmer (e.g. a closer photo), or
    "skipped" when it is no longer needed. When every step is finished the
    plan is cleared automatically.

    :param step_description: Exact description of the step to update.
    :param status: One of done / awaiting_farmer / skipped / pending.
    :return: The updated plan, plus `matched` so you can tell whether the
        description matched a recorded step.
    """
    session = ToolContext.get().session
    plan = read_session_plan(session)
    if plan is None:
        return {"plan": None, "matched": False}
    matched = plan.mark(step_description, status)
    if matched and plan.next_step() is None:
        clear_session_plan(session)
        return {"plan": None, "matched": True, "cleared": True}
    if matched:
        store_session_plan(session, plan)
    return {"plan": plan.to_dict(), "matched": matched}


def clear_active_plan_tool() -> dict[str, Any]:
    """Remove the active plan from this conversation.

    Call this when a plan is obsolete (e.g. the farmer changed topic to a
    completely different problem) rather than letting stale steps linger.
    """
    session = ToolContext.get().session
    clear_session_plan(session)
    return {"plan": None, "cleared": True}
