"""Harvester bootstrap + sticky-session lease. The collector never builds proxy URLs itself."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field

from app.admin_api.auth import require_internal_token
from app.admin_api.store import arp_store_from, pulse_harvester
from app.api.deps import ConfigStoreDep
from app.core.errors import AppError
from app.services.config.proxy import build_session

router = APIRouter(prefix="/admin-api/adobe/harvester", tags=["internal-harvester"])


class HarvesterBootstrap(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int
    mint_browser_count: int
    mint_interval_seconds: int
    arp_ttl_seconds: int
    arp_max_uses: int
    arp_min_ready: int
    arp_pool_target: int
    arp_mint_batch: int
    proxy_ready: bool
    cloakbrowser_license_key: str | None = None


class HarvesterLease(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sid: str
    egress_id: str
    proxy_url: str = Field(repr=False)
    proxy_masked: str
    sticky_minutes: int


@router.get("/bootstrap", response_model=HarvesterBootstrap)
async def bootstrap(
    request: Request,
    store: ConfigStoreDep,
    _auth: Annotated[None, Depends(require_internal_token)],
) -> HarvesterBootstrap:
    cfg = await store.load(fresh=True)
    password = store.proxy_password(cfg)
    proxy_ready = bool(cfg.proxy.host and cfg.proxy.username and password)
    await pulse_harvester(arp_store_from(request, cfg), cfg.mint_interval_seconds)
    return HarvesterBootstrap(
        version=await store.version(),
        mint_browser_count=cfg.mint_browser_count,
        mint_interval_seconds=cfg.mint_interval_seconds,
        arp_ttl_seconds=cfg.arp_ttl_seconds,
        arp_max_uses=cfg.arp_max_uses,
        arp_min_ready=cfg.arp_min_ready,
        arp_pool_target=cfg.arp_pool_target,
        arp_mint_batch=cfg.arp_mint_batch,
        proxy_ready=proxy_ready,
        cloakbrowser_license_key=store.cloakbrowser_license(cfg),
    )


@router.post("/lease", response_model=HarvesterLease)
async def lease(
    request: Request,
    store: ConfigStoreDep,
    _auth: Annotated[None, Depends(require_internal_token)],
) -> HarvesterLease:
    cfg = await store.load(fresh=True)
    await pulse_harvester(arp_store_from(request, cfg), cfg.mint_interval_seconds)
    password = store.proxy_password(cfg)
    if not cfg.proxy.host or not cfg.proxy.username or not password:
        raise AppError(
            code="proxy_not_configured",
            message="panel proxy is not configured",
            http_status=422,
        )
    try:
        session = build_session(cfg.proxy, password, arp_ttl_seconds=cfg.arp_ttl_seconds)
    except ValueError as exc:
        raise AppError(code="proxy_invalid", message=str(exc), http_status=422) from exc
    return HarvesterLease(
        sid=session.sid,
        egress_id=session.egress_id,
        proxy_url=session.url,
        proxy_masked=session.masked,
        sticky_minutes=cfg.proxy.sticky_minutes,
    )
