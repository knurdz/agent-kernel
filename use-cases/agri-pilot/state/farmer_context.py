"""Farmer context state model for AgriPilot.

Every specialist agent and tool reads and writes a single `FarmerContext`
per session. It captures what the system currently knows about the farmer
and the current conversation, so the triage agent can decide what is
missing before calling a specialist (see architecture doc section 13,
"Information Sufficiency Check").

The context is stored in the Agent Kernel `Session` key-value store under
`SESSION_KEY`, so it survives across turns within the same session.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields, replace
from typing import Any, Optional

from agentkernel.core.base import Session
from agentkernel.core.tool import ToolContext

SESSION_KEY = "farmer_context"


@dataclass
class FarmerContext:
    """What AgriPilot currently knows about the farmer and the conversation.

    :ivar language: Farmer's preferred language (e.g. "en", "si", "ta").
        None until detected or set by the farmer.
    :ivar location: Farmer's location, used for weather lookups.
    :ivar crop: The crop under discussion (e.g. "tomato").
    :ivar disease: The diagnosed disease for that crop (e.g. "early blight"),
        recorded only by the vision specialist after a confident diagnosis,
        so the knowledge specialist can run a disease-specific retrieval
        without asking the farmer again.
    :ivar growth_stage: Growth stage of that crop (e.g. "flowering").
    :ivar previous_case: Short summary of the last resolved case, so a
        follow-up message like "it is getting worse" can be resolved
        without re-asking the farmer.
    :ivar input_type: Modality of the current message ("text", "image",
        "text+image", "voice").
    :ivar intent: The classified intent for the current message (see
        Increment 1.2 intent categories), or None if not yet classified.
    """

    language: Optional[str] = None
    location: Optional[str] = None
    crop: Optional[str] = None
    disease: Optional[str] = None
    growth_stage: Optional[str] = None
    previous_case: Optional[str] = None
    input_type: Optional[str] = None
    intent: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Return the context as a plain, JSON-serializable dict."""
        return asdict(self)

    def update(self, **changes: Any) -> "FarmerContext":
        """Return a copy of this context with the given fields overwritten.

        :param changes: Field name/value pairs to overwrite.
        :return: A new `FarmerContext`; the original is left untouched.
        :raises TypeError: If `changes` contains a field name that does not
            exist on `FarmerContext` (catches typos instead of silently
            creating an unused field).
        """
        valid = {f.name for f in fields(self)}
        unknown = set(changes) - valid
        if unknown:
            raise TypeError(f"Unknown FarmerContext field(s): {sorted(unknown)}")
        return replace(self, **changes)


def get_farmer_context(session: Session) -> FarmerContext:
    """Get the `FarmerContext` for a session, creating an empty one if absent.

    :param session: The Agent Kernel session to read from.
    :return: The session's `FarmerContext`.
    """
    stored = session.get(SESSION_KEY)
    if stored is None:
        stored = FarmerContext()
        session.set(SESSION_KEY, stored)
    return stored


def set_farmer_context(session: Session, context: FarmerContext) -> FarmerContext:
    """Store a `FarmerContext` on a session, replacing any existing one.

    :param session: The Agent Kernel session to write to.
    :param context: The context to store.
    :return: The stored context.
    """
    return session.set(SESSION_KEY, context)


def current_farmer_context() -> FarmerContext:
    """Get the `FarmerContext` for the currently executing tool call.

    Must be called from within a tool function running inside an agent,
    i.e. where `ToolContext.get()` succeeds.

    :return: The current session's `FarmerContext`.
    """
    return get_farmer_context(ToolContext.get().session)


def update_current_farmer_context(**changes: Any) -> FarmerContext:
    """Update and persist the `FarmerContext` for the currently executing tool call.

    :param changes: Field name/value pairs to overwrite.
    :return: The updated, persisted context.
    """
    session = ToolContext.get().session
    updated = get_farmer_context(session).update(**changes)
    return set_farmer_context(session, updated)
