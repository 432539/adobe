"""Persistence for ``SystemConfig``.

* One JSON document under ``system_settings.key = 'system_config'`` so a save is atomic.
* Unknown / legacy fields are dropped by the schema; missing fields fall back to defaults,
  which is how new settings roll out without a migration.
* Every save bumps ``version`` and publishes it on a Redis channel so workers and the
  harvester can reload hot config without a restart.
* A short in-process cache keeps hot-path readers (billing, retry policy) off the DB.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from redis.asyncio import Redis
from sqlalchemy import select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm.attributes import flag_modified

from app.core.crypto import FieldCipher
from app.models.system_setting import SystemSetting
from app.services.config.schema import (
    SystemConfig,
    SystemConfigUpdate,
    SystemConfigView,
    apply_update,
    default_config,
    ensure_pricing_catalog,
    hydrate_stored_config,
    to_view,
)

logger = logging.getLogger(__name__)

CONFIG_KEY = "system_config"


@dataclass(slots=True)
class _Cached:
    config: SystemConfig
    version: int
    expires_at: float = field(default=0.0)


class ConfigStore:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        redis: Redis | None,
        cipher: FieldCipher,
        *,
        cache_seconds: float = 5.0,
        channel: str = "firefly:config:changed",
    ) -> None:
        self._sessions = sessions
        self._redis = redis
        self._cipher = cipher
        self._cache_seconds = cache_seconds
        self._channel = channel
        self._cache: _Cached | None = None

    # ------------------------------------------------------------------ read
    async def load(self, *, fresh: bool = False) -> SystemConfig:
        now = time.monotonic()
        if not fresh and self._cache and self._cache.expires_at > now:
            return self._cache.config
        async with self._sessions() as session:
            row = await session.get(SystemSetting, CONFIG_KEY)
        if row is None:
            cfg, version = default_config(), 0
        else:
            cfg = ensure_pricing_catalog(
                SystemConfig.model_validate(hydrate_stored_config(row.value))
            )
            version = row.version
        self._cache = _Cached(cfg, version, now + self._cache_seconds)
        return cfg

    async def version(self) -> int:
        await self.load()
        return self._cache.version if self._cache else 0

    async def view(self) -> SystemConfigView:
        return to_view(await self.load(fresh=True), self._cipher)

    # ------------------------------------------------------------------ write
    async def save(
        self, update: SystemConfigUpdate, *, session: AsyncSession | None = None
    ) -> SystemConfigView:
        """Persist. Pass the request's session so the write joins its transaction (the
        caller commits); without one, a private session is used and committed here."""
        current = await self.load(fresh=True)
        merged = apply_update(current, update, self._cipher)
        payload = merged.model_dump(mode="json")
        try:
            if session is not None:
                version = await self._write(session, payload)
                await session.flush()
            else:
                async with self._sessions() as own:
                    version = await self._write(own, payload)
                    await own.commit()
        except OperationalError as exc:
            err = str(exc).lower()
            if "lock timeout" in err or "canceling statement" in err:
                raise ValueError("配置正在被其他请求写入，请稍后重试") from exc
            raise
        self._cache = _Cached(merged, version, time.monotonic() + self._cache_seconds)
        await self._broadcast(version)
        logger.info("system config saved", extra={"version": version})
        return to_view(merged, self._cipher)

    @staticmethod
    async def _write(session: AsyncSession, payload: dict[str, Any]) -> int:
        bind = session.bind
        if bind is not None and getattr(bind.dialect, "name", "") == "postgresql":
            await session.execute(text("SET LOCAL lock_timeout = '3s'"))
        row = await session.get(SystemSetting, CONFIG_KEY, with_for_update=True)
        if row is None:
            row = SystemSetting(key=CONFIG_KEY, value=payload, version=1)
            session.add(row)
        else:
            row.value = payload
            flag_modified(row, "value")
            row.version += 1
        await session.flush()
        return row.version

    async def _broadcast(self, version: int) -> None:
        if self._redis is None:
            return
        try:
            await asyncio.wait_for(self._redis.publish(self._channel, str(version)), timeout=1.0)
        except Exception:  # noqa: BLE001 - broadcast is best-effort
            logger.warning("config change broadcast failed", extra={"version": version})

    # ------------------------------------------------------------------ secrets
    def proxy_password(self, cfg: SystemConfig) -> str | None:
        return self._cipher.decrypt(cfg.proxy.password_enc) if cfg.proxy.password_enc else None

    def r2_secret(self, cfg: SystemConfig, account_id: str) -> str | None:
        for acc in cfg.r2_accounts:
            if acc.id == account_id and acc.secret_key_enc:
                return self._cipher.decrypt(acc.secret_key_enc)
        return None

    def cloakbrowser_license(self, cfg: SystemConfig) -> str | None:
        enc = cfg.cloakbrowser_license_key_enc
        return self._cipher.decrypt(enc) if enc else None


async def list_settings(session: AsyncSession) -> list[SystemSetting]:
    result = await session.execute(select(SystemSetting).order_by(SystemSetting.key))
    return list(result.scalars())
