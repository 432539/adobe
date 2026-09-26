import base64
import json
import os
import time
from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
import pytest_asyncio
from redis.asyncio import Redis

from app.arp.models import ArpPublishItem
from app.arp.store import ArpStore


def make_item() -> ArpPublishItem:
    token = base64.b64encode(
        json.dumps(
            {"sid": "sid", "ark": "ark", "bfp": "bfp", "ftr": "id_ts__UDF43-xx=-3-v2_tt"}
        ).encode()
    ).decode()
    return ArpPublishItem.model_validate(
        {
            "t": token,
            "proxy_url": "socks5h://user:password@proxy.example:1080",
            "egress_id": "residential-1",
            "ua": "Mozilla/5.0 Chrome/148.0.0.0 Safari/537.36",
            "ch": {
                "platform": "Windows",
                "platformVersion": "15.0.0",
                "fullVersionList": [{"brand": "Google Chrome", "version": "148.0.0.0"}],
                "architecture": "x86",
                "bitness": "64",
            },
        }
    )


@pytest_asyncio.fixture
async def store() -> AsyncIterator[ArpStore]:
    redis = Redis.from_url(
        os.getenv("REDIS_TEST_URL", "redis://127.0.0.1:6379/15"),
        decode_responses=True,
    )
    try:
        await redis.ping()
    except Exception:
        await redis.aclose()
        pytest.skip("Redis is not available")

    prefix = f"test:arp:{uuid4().hex}"
    instance = ArpStore(redis, key_prefix=prefix, ttl_seconds=30, max_uses=2)
    yield instance
    keys = [key async for key in redis.scan_iter(f"{prefix}:*")]
    if keys:
        await redis.delete(*keys)
    await redis.aclose()


@pytest.mark.asyncio
async def test_publish_checkout_and_max_uses_are_atomic(store: ArpStore) -> None:
    ids = await store.publish([make_item()])

    first = await store.checkout()
    second = await store.checkout()
    exhausted = await store.checkout()

    assert len(ids) == 1
    assert first is not None and first.id == ids[0] and first.uses == 1
    assert second is not None and second.id == ids[0] and second.uses == 2
    assert exhausted is None


@pytest.mark.asyncio
async def test_checkout_round_robins_across_ready_tickets(store: ArpStore) -> None:
    published = set(await store.publish([make_item(), make_item(), make_item()]))
    first_pass = [(await store.checkout()) for _ in range(3)]
    picked = {bundle.id for bundle in first_pass if bundle is not None}
    assert picked == published
    again = await store.checkout()
    assert again is not None and again.id == first_pass[0].id and again.uses == 2


@pytest.mark.asyncio
async def test_invalidate_removes_bundle_from_ready_pool(store: ArpStore) -> None:
    bundle_id = (await store.publish([make_item()]))[0]

    removed = await store.invalidate(bundle_id)

    assert removed is True
    assert await store.checkout() is None


@pytest.mark.asyncio
async def test_health_returns_only_non_sensitive_pool_metadata(store: ArpStore) -> None:
    await store.publish([make_item()])

    health = await store.health()

    assert health["present"] is True
    assert health["ready"] == 1
    assert health["egress"] == {"residential-1": 1}
    assert "proxy_url" not in health
    assert "token" not in health


@pytest.mark.asyncio
async def test_snapshot_is_public_and_records_mint_events(store: ArpStore) -> None:
    await store.publish([make_item()])
    snap = await store.snapshot()
    dumped = json.dumps(snap)
    assert "password" not in dumped
    assert "proxy_url" not in dumped
    assert snap["ready"] == 1
    assert snap["tickets"][0]["egress_id"] == "residential-1"
    assert snap["tickets"][0]["chrome_148"] is True
    assert snap["events"][0]["type"] == "published"
    assert snap["last_publish"]["egress_id"] == "residential-1"


@pytest.mark.asyncio
async def test_max_uses_is_capped_at_ten_on_publish_and_snapshot() -> None:
    redis = Redis.from_url(
        os.getenv("REDIS_TEST_URL", "redis://127.0.0.1:6379/15"),
        decode_responses=True,
    )
    try:
        await redis.ping()
    except Exception:
        await redis.aclose()
        pytest.skip("Redis is not available")
    prefix = f"test:arp-cap:{uuid4().hex}"
    store = ArpStore(redis, key_prefix=prefix, ttl_seconds=30, max_uses=20)
    try:
        ids = await store.publish([make_item()])
        raw = await redis.get(f"{prefix}:item:{ids[0]}")
        assert raw is not None
        assert json.loads(raw)["max_uses"] == 10
        snap = await store.snapshot()
        assert snap["tickets"][0]["max_uses"] == 10
    finally:
        keys = [key async for key in redis.scan_iter(f"{prefix}:*")]
        if keys:
            await redis.delete(*keys)
        await redis.aclose()


@pytest.mark.asyncio
async def test_harvester_heartbeat_is_independent_of_tickets(store: ArpStore) -> None:
    assert await store.harvester_seen_at() is None
    await store.touch_harvester(30)
    seen = await store.harvester_seen_at()
    assert seen is not None
    assert abs(seen - int(time.time())) < 3


@pytest.mark.asyncio
async def test_checkout_and_snapshot_drop_ftr_without_v2_tt(store: ArpStore) -> None:
    now = int(time.time())
    bad_id = "arp_short_ftr"
    token = base64.b64encode(
        json.dumps({"sid": "sid", "ark": "ark", "bfp": "bfp", "ftr": "id_ts__UDF43-xx"}).encode()
    ).decode()
    blob = {
        "id": bad_id,
        "token": token,
        "proxy_url": "socks5h://user:password@proxy.example:1080",
        "egress_id": "residential-1",
        "ua": "Mozilla/5.0 Chrome/148.0.0.0 Safari/537.36",
        "ch": {
            "platform": "Windows",
            "platformVersion": "15.0.0",
            "fullVersionList": [{"brand": "Google Chrome", "version": "148.0.0.0"}],
            "architecture": "x86",
            "bitness": "64",
        },
        "headers": {},
        "minted_at": now,
        "expires_at": now + 60,
        "uses": 0,
        "max_uses": 2,
    }
    await store._redis.set(store._item_key(bad_id), json.dumps(blob), ex=60)
    await store._redis.zadd(store._ready_key, {bad_id: now + 60})

    assert await store.checkout() is None
    snap = await store.snapshot()
    assert snap["ready"] == 0
    assert await store._redis.get(store._item_key(bad_id)) is None
