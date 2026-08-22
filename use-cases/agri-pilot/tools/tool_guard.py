"""Per-session call limits, timeouts and debug hooks for AgriPilot tools.

Increment 7.4: every data-fetching tool is wrapped with `guarded`, which

- counts invocations per tool per Agent Kernel session and, past
  `AGRIPILOT_TOOL_MAX_CALLS` (default 8), stops executing the tool and
  returns a farmer-ready limitation message instead — so a confused agent
  can never retry the same lookup forever;
- runs the wrapped call under `AGRIPILOT_TOOL_TIMEOUT_SECONDS` (default
  180 s; generous because the first vision call loads the classifier) and
  reports a timeout with its own limitation message;
- logs each call's duration (used for the Increment 7.1 parallelism
  timing check);
- honors two debug switches so failure/latency scenarios are repeatable
  from the CLI without automated tests:
    AGRIPILOT_DEBUG_FORCE_TOOL_FAILURE=<comma-separated tool names>
        makes the named tools raise on every call (the count above still
        applies, so the agent sees failures until the limit kicks in);
    AGRIPILOT_DEBUG_TOOL_DELAY_SECONDS=<float>
        sleeps that long before every guarded call, making parallel vs
        serial execution observable in the timing logs.

Counting uses the session key-value store when running inside an agent
(ToolContext available) and degrades to a no-op pass-through otherwise,
so direct calls (scripts, tests) behave exactly as before.
"""

from __future__ import annotations

import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from functools import wraps
from typing import Any, Callable

from agentkernel.core.tool import ToolContext

log = logging.getLogger("agripilot.tool_guard")

SESSION_KEY = "tool_call_counts"

DEFAULT_MAX_CALLS = int(os.environ.get("AGRIPILOT_TOOL_MAX_CALLS", "8"))
DEFAULT_TIMEOUT_SECONDS = float(os.environ.get("AGRIPILOT_TOOL_TIMEOUT_SECONDS", "180"))

LIMIT_REACHED_MESSAGE = (
    "This check has been attempted too many times without success, so I have "
    "stopped trying. Please rephrase your request or try again later."
)

TIMEOUT_MESSAGE = (
    "This check took too long to complete, so I had to give up on it. " "Please try again in a little while."
)

_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="agripilot-tool")


def _forced_failure_tools() -> set[str]:
    """Parse AGRIPILOT_DEBUG_FORCE_TOOL_FAILURE into a set of tool names."""
    raw = os.environ.get("AGRIPILOT_DEBUG_FORCE_TOOL_FAILURE", "")
    return {name.strip() for name in raw.split(",") if name.strip()}


def _debug_delay_seconds() -> float:
    """Return the configured artificial delay for guarded calls (0 if none)."""
    raw = os.environ.get("AGRIPILOT_DEBUG_TOOL_DELAY_SECONDS", "").strip()
    try:
        return max(0.0, float(raw)) if raw else 0.0
    except ValueError:
        return 0.0


def _increment_count(tool_name: str) -> int | None:
    """Increment and return this session's invocation count for one tool.

    Returns None when there is no active session context: direct calls
    (scripts, tests) are not counted or limited, matching pre-guard
    behavior exactly.
    """
    try:
        session = ToolContext.get().session
    except Exception:  # noqa: BLE001 - no active tool context: no limiting
        return None

    counts = session.get(SESSION_KEY)
    if not isinstance(counts, dict):
        counts = {}
    counts[tool_name] = counts.get(tool_name, 0) + 1
    session.set(SESSION_KEY, counts)
    return counts[tool_name]


def _run_with_timeout(func: Callable[..., Any], args: tuple, kwargs: dict) -> Any:
    """Run one tool call, giving up after DEFAULT_TIMEOUT_SECONDS."""
    future = _executor.submit(func, *args, **kwargs)
    return future.result(timeout=DEFAULT_TIMEOUT_SECONDS)


def guarded(func: Callable[..., Any]) -> Callable[..., Any]:
    """Wrap a tool function with call limits, timeout, timing and debug hooks.

    :param func: The tool function to wrap. Its signature and docstring are
        preserved (`functools.wraps`), so tool schema generation is unaffected.
    :return: The guarded callable, suitable as a drop-in replacement.
    """

    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        delay = _debug_delay_seconds()
        if delay:
            log.info("tool %s: artificial delay %.2fs", func.__name__, delay)
            time.sleep(delay)

        count = _increment_count(func.__name__)
        if count is not None and count > DEFAULT_MAX_CALLS:
            log.warning(
                "tool %s blocked: %d calls exceed the per-session limit of %d",
                func.__name__,
                count,
                DEFAULT_MAX_CALLS,
            )
            return {"limited": True, "message": LIMIT_REACHED_MESSAGE}

        if func.__name__ in _forced_failure_tools():
            log.warning("tool %s: forced failure via AGRIPILOT_DEBUG_FORCE_TOOL_FAILURE", func.__name__)
            raise RuntimeError(f"{func.__name__}: simulated failure for manual testing")

        started = time.perf_counter()
        try:
            result = _run_with_timeout(func, args, kwargs)
        except FutureTimeoutError:
            log.warning("tool %s timed out after %.0fs", func.__name__, DEFAULT_TIMEOUT_SECONDS)
            return {"limited": True, "message": TIMEOUT_MESSAGE}
        duration = time.perf_counter() - started
        log.info("tool %s completed in %.2fs", func.__name__, duration)
        return result

    return wrapper
