"""Skip-if-no-Redis integration tests for Phase 7.1 (durable memory).

Covers, against a real Redis on localhost:6379 (start one with
`docker compose up -d redis`; the whole module skips otherwise):

1. Config selection: with AK_SESSION__TYPE=redis, SessionStoreBuilder
   yields a RedisSessionStore.
2. Session durability: FarmerContext and ActivePlan written through one
   RedisSessionStore load intact from a freshly built store, simulating an
   app restart (two stores, no shared cache).
3. Attachment durability: AttachmentStorageManager under
   multimodal.storage_type=redis saves a photo binary that a fresh manager
   instance (post-restart) retrieves intact.

Every key is written under a unique per-run prefix and carries the
configured TTL, so test data expires without cleanup and never collides
with sessions from a running app.
"""

import base64
import time
import uuid

import pytest

redis_lib = pytest.importorskip("redis")

REDIS_URL = "redis://localhost:6379"


def _redis_reachable() -> bool:
    try:
        client = redis_lib.Redis.from_url(REDIS_URL, socket_connect_timeout=1)
        return bool(client.ping())
    except Exception:  # noqa: BLE001 - unreachable Redis must skip, not error
        return False


pytestmark = pytest.mark.skipif(not _redis_reachable(), reason="Redis not reachable on localhost:6379")


@pytest.fixture()
def redis_config(monkeypatch):
    """Point AKConfig at the real Redis under a unique per-run prefix.

    monkeypatch restores every env var afterwards; AKConfig._reset() before
    and after makes the config singleton reload from config.yaml for the
    next test, so no AK_* state leaks into the rest of the suite.
    """
    from agentkernel.core.config import AKConfig

    run_id = uuid.uuid4().hex[:8]
    monkeypatch.setenv("AK_SESSION__TYPE", "redis")
    monkeypatch.setenv("AK_SESSION__REDIS__URL", REDIS_URL)
    monkeypatch.setenv("AK_SESSION__REDIS__PREFIX", f"ak:agripilot:test:{run_id}:")
    monkeypatch.setenv("AK_MULTIMODAL__STORAGE_TYPE", "redis")
    monkeypatch.setenv("AK_MULTIMODAL__REDIS__URL", REDIS_URL)
    monkeypatch.setenv("AK_MULTIMODAL__REDIS__PREFIX", f"ak:attachments:test:{run_id}:")
    AKConfig._reset()
    yield
    AKConfig._reset()


def _fresh_session_store():
    """A RedisSessionStore with no in-memory cache, like a new process."""
    from agentkernel.core.session.redis import RedisSessionStore

    return RedisSessionStore(cache=None)


def test_session_store_builder_selects_redis(redis_config):
    from agentkernel.core.builder import SessionStoreBuilder
    from agentkernel.core.session.redis import RedisSessionStore

    assert isinstance(SessionStoreBuilder.build(), RedisSessionStore)


def test_farmer_context_and_plan_survive_store_recreation(redis_config):
    from state.farmer_context import get_farmer_context, set_farmer_context
    from state.plan import (
        PLAN_SESSION_KEY,
        STEP_DONE,
        STEP_PENDING,
        ActivePlan,
        PlanStep,
        get_active_plan,
        set_active_plan,
    )

    session_id = f"pytest-{uuid.uuid4().hex}"

    store_a = _fresh_session_store()
    session = store_a.new(session_id)
    set_farmer_context(
        session, get_farmer_context(session).update(crop="tomato", disease="early blight", location="Kandy")
    )
    set_active_plan(
        session,
        ActivePlan(
            goal="diagnose crop problem and give treatment advice",
            steps=[
                PlanStep(description="Diagnose from the photo", status=STEP_DONE),
                PlanStep(description="Advise treatment", status=STEP_PENDING),
            ],
        ),
    )
    store_a.store(session)

    # Simulated restart: brand-new store instance loading straight from Redis.
    reloaded = _fresh_session_store().load(session_id)

    ctx = get_farmer_context(reloaded)
    assert (ctx.crop, ctx.disease, ctx.location) == ("tomato", "early blight", "Kandy")

    plan = get_active_plan(reloaded)
    assert isinstance(plan, ActivePlan)
    assert plan.goal == "diagnose crop problem and give treatment advice"
    assert [step.status for step in plan.steps] == [STEP_DONE, STEP_PENDING]
    assert reloaded.id == session_id


def test_attachment_survives_manager_recreation(redis_config):
    from agentkernel.core.multimodal.storage.storage_manager import AttachmentStorageManager

    session_id = f"pytest-{uuid.uuid4().hex}"
    jpeg_bytes = base64.b64encode(b"\xff\xd8\xff\xe0fake-jpeg-bytes").decode()

    manager_a = AttachmentStorageManager(session_id)
    attachment_id = manager_a.save_attachment(
        data=jpeg_bytes,
        attachment_type="image",
        name="leaf.jpg",
        mime_type="image/jpeg",
        description="close-up of tomato leaf",
        max_attachments=5,
    )

    # Simulated restart: a fresh manager builds a fresh driver.
    results = AttachmentStorageManager(session_id).get_attachment_data([attachment_id])
    assert len(results) == 1
    restored = results[0]
    assert restored.name == "leaf.jpg"
    assert restored.mime_type == "image/jpeg"
    assert restored.data == jpeg_bytes
