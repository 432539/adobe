"""Build an ArpStore whose TTL / max_uses come from the live config document, not env."""

from __future__ import annotations

import logging

from fastapi import Request
from redis.exceptions import RedisError

from app.api.deps import get_config_store
from app.arp.store import ArpStore
from app.core.config import Settings
from app.core.resources import Resources
from app.services.config.schema import SystemConfig

logger = logging.getLogger(__name__)

# Covers a mint (default ARP_MINT_TIMEOUT=90s) after the last bootstrap/lease poll.
HEARTBEAT_GRACE_SECONDS = 180


def heartbeat_ttl(mint_interval_seconds: int) -> int:
    return max(int(mint_interval_seconds), 8) + HEARTBEAT_GRACE_SECONDS


async def pulse_harvester(store: ArpStore, mint_interval_seconds: int) -> None:
    try:
        await store.touch_harvester(heartbeat_ttl(mint_interval_seconds))
    except RedisError as exc:
        logger.warning("harvester heartbeat skipped error=%s", type(exc).__name__)


def arp_store_from(request: Request, cfg: SystemConfig) -> ArpStore:
    settings: Settings = request.app.state.settings
    resources: Resources = request.app.state.resources
    return ArpStore(
        resources.redis,
        key_prefix=settings.arp_key_prefix,
        ttl_seconds=cfg.arp_ttl_seconds,
        max_uses=cfg.arp_max_uses,
    )


async def arp_store_for(request: Request) -> ArpStore:
    cfg = await get_config_store(request).load()
    return arp_store_from(request, cfg)
