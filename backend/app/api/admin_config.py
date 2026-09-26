"""Admin → system configuration.

GET  /api/admin/config                 masked view
PUT  /api/admin/config                 full save (secrets optional; omitted = keep)
POST /api/admin/config/proxy/test      probe egress with a fresh sid
POST /api/admin/config/r2/test         connectivity check for one stored / draft account
GET  /api/admin/config/r2/usage        per-account used bytes (Redis cached; ?refresh=1)
GET  /api/admin/config/pricing/quote   what a request would cost (for the panel / docs)
"""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.api.deps import AdminDep, ConfigStoreDep, ResourcesDep, SessionDep, SettingsDep
from app.core.errors import AppError
from app.services.config import pricing
from app.services.config.proxy import ProxyTestResult, test_proxy
from app.services.config.r2 import (
    R2TestResult,
    R2Usage,
    R2UsageService,
    test_account,
)
from app.services.config.schema import (
    ProxyConfigUpdate,
    R2Account,
    R2AccountUpdate,
    SystemConfigUpdate,
    SystemConfigView,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/config", tags=["admin-config"])


@router.get("", response_model=SystemConfigView)
async def get_config(_admin: AdminDep, store: ConfigStoreDep) -> SystemConfigView:
    return await store.view()


@router.put("", response_model=SystemConfigView)
async def save_config(
    payload: SystemConfigUpdate,
    _admin: AdminDep,
    store: ConfigStoreDep,
    session: SessionDep,
) -> SystemConfigView:
    try:
        view = await store.save(payload, session=session)
    except ValueError as exc:
        raise AppError(code="config_invalid", message=str(exc), http_status=422) from exc
    return view


# --------------------------------------------------------------------------- proxy
@router.post("/proxy/test", response_model=ProxyTestResult)
async def proxy_test(
    payload: ProxyConfigUpdate,
    _admin: AdminDep,
    store: ConfigStoreDep,
    settings: SettingsDep,
) -> ProxyTestResult:
    """Uses the password from the request when provided, otherwise the stored one."""
    password = payload.password
    if not password or "••" in password:
        password = store.proxy_password(await store.load(fresh=True))
    if not password:
        raise AppError(code="proxy_password_missing", message="请先填写代理密码", http_status=422)
    if not payload.host or not payload.username:
        raise AppError(code="proxy_incomplete", message="请先填写代理地址与账号", http_status=422)
    return await test_proxy(
        payload,
        password,
        probe_url=settings.proxy_probe_url,
        timeout_seconds=settings.proxy_probe_timeout_seconds,
        impersonate=settings.submit_impersonate,
    )


# --------------------------------------------------------------------------- r2
class R2TestRequest(BaseModel):
    """Either an existing account id, or a draft account (with secret) not yet saved."""

    id: str | None = None
    draft: R2AccountUpdate | None = None


@router.post("/r2/test", response_model=R2TestResult)
async def r2_test(payload: R2TestRequest, _admin: AdminDep, store: ConfigStoreDep) -> R2TestResult:
    cfg = await store.load(fresh=True)
    if payload.draft is not None:
        d = payload.draft
        prev = next((a for a in cfg.r2_accounts if a.id == d.id), None) if d.id else None
        endpoint = (
            d.endpoint if d.endpoint and "…" not in d.endpoint else (prev.endpoint if prev else "")
        )
        access_key = d.access_key_id or (prev.access_key_id if prev else "")
        secret = (
            d.secret_access_key
            if d.secret_access_key and "••" not in d.secret_access_key
            else (store.r2_secret(cfg, prev.id) if prev else None)
        )
        if not endpoint:
            raise AppError(code="r2_incomplete", message="请填写 Endpoint", http_status=422)
        draft = R2Account(
            id=d.id or "draft",
            name=d.name,
            endpoint=endpoint,
            bucket=d.bucket,
            public_base_url=d.public_base_url,
            prefix=d.prefix,
            enabled=d.enabled,
            quota_bytes=d.quota_bytes,
            access_key_id=access_key,
        )
        return await test_account(draft, secret)

    stored = next((a for a in cfg.r2_accounts if a.id == payload.id), None)
    if stored is None:
        raise AppError(code="r2_not_found", message="R2 账号不存在", http_status=404)
    return await test_account(stored, store.r2_secret(cfg, stored.id))


class R2UsageResponse(BaseModel):
    accounts: list[R2Usage]
    total_used_bytes: int
    total_quota_bytes: int


@router.get("/r2/usage", response_model=R2UsageResponse)
async def r2_usage(
    _admin: AdminDep,
    store: ConfigStoreDep,
    resources: ResourcesDep,
    settings: SettingsDep,
    refresh: bool = Query(default=False),
) -> R2UsageResponse:
    cfg = await store.load(fresh=True)
    service = R2UsageService(resources.redis, cache_seconds=settings.r2_usage_cache_seconds)
    pairs = [(acc, store.r2_secret(cfg, acc.id)) for acc in cfg.r2_accounts]
    usages = await service.usage_all(pairs, force=refresh)
    return R2UsageResponse(
        accounts=usages,
        total_used_bytes=sum(u.used_bytes or 0 for u in usages),
        total_quota_bytes=sum(a.quota_bytes for a in cfg.r2_accounts if a.enabled),
    )


# --------------------------------------------------------------------------- pricing
class PriceQuote(BaseModel):
    model_id: str
    kind: Literal["image", "video"]
    price: int = Field(description="分")
    display: str


@router.get("/pricing/quote", response_model=PriceQuote)
async def pricing_quote(
    _admin: AdminDep,
    store: ConfigStoreDep,
    model: str = Query(min_length=1),
    kind: Literal["image", "video"] = Query(default="image"),
    resolution: str = Query(default="1K"),
    duration: int = Query(default=0, ge=0, le=600),
) -> PriceQuote:
    cfg = await store.load()
    price = (
        pricing.image_cost(cfg, model, resolution)
        if kind == "image"
        else pricing.video_cost(cfg, model, duration)
    )
    return PriceQuote(model_id=model, kind=kind, price=price, display=pricing.format_credits(price))
