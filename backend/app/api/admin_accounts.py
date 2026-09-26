"""Admin: upstream account pool. Cookies are encrypted at rest; admin list shows plaintext."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from app.accounts.cookie_loader import CookieFileError, parse_cookie_text
from app.adobe.client import AdobeGenerateError
from app.adobe.credits import DEFAULT_UA
from app.api.deps import AdminDep, ConfigStoreDep, ResourcesDep, SessionDep, SettingsDep
from app.core.config import Settings
from app.core.errors import AppError
from app.core.resources import Resources
from app.models.account import UpstreamAccount
from app.services import accounts as account_pool
from app.services.config.proxy import build_session
from app.services.config.store import ConfigStore

router = APIRouter(prefix="/api/admin/accounts", tags=["admin-accounts"])
logger = logging.getLogger(__name__)

_STATUSES = frozenset({"active", "parked", "ratelimited", "dead"})


def _accounts_stmt(
    *,
    q: str | None,
    status: str | None,
    credits_lt: int | None,
) -> Select[tuple[UpstreamAccount]]:
    stmt = select(UpstreamAccount)
    if q and q.strip():
        stmt = stmt.where(UpstreamAccount.email_masked.ilike(f"%{q.strip()}%"))
    if status:
        if status not in _STATUSES:
            raise AppError(code="invalid_status", message="状态无效", http_status=422)
        stmt = stmt.where(UpstreamAccount.status == status)
    if credits_lt is not None:
        stmt = stmt.where(UpstreamAccount.credits_remaining < credits_lt)
    return stmt


class ImportCookiesRequest(BaseModel):
    text: str = Field(min_length=10, max_length=2_000_000)
    group: str = Field(default="alpha", pattern="^(normal|alpha)$")


class PatchAccountRequest(BaseModel):
    status: str | None = None
    group: str | None = Field(default=None, pattern="^(normal|alpha)$")
    cookie: str | None = Field(default=None, max_length=2_000_000)


class DeleteAccountsRequest(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=1000)


async def lease_panel_proxy(store: ConfigStore) -> str:
    """Sticky URL from config center. Never log the return value."""
    cfg = await store.load()
    password = store.proxy_password(cfg)
    if not cfg.proxy.host or not cfg.proxy.username or not password:
        raise AppError(
            code="proxy_not_configured", message="请先在系统设置里配置代理", http_status=422
        )
    try:
        session = build_session(cfg.proxy, password, arp_ttl_seconds=cfg.arp_ttl_seconds)
    except ValueError as exc:
        raise AppError(code="proxy_invalid", message=str(exc), http_status=422) from exc
    return session.url


async def _verify_imported_accounts(
    session: AsyncSession,
    store: ConfigStore,
    resources: Resources,
    settings: Settings,
    ids: list[int],
) -> dict[str, int]:
    """Mint + credits for newly imported rows. Skip when proxy is not configured."""
    if not ids:
        return {"verified": 0, "hard": 0, "failed": 0}
    try:
        await lease_panel_proxy(store)
    except AppError as exc:
        if exc.code == "proxy_not_configured":
            return {"verified": 0, "hard": 0, "failed": 0}
        raise
    verified = 0
    hard = 0
    failed = 0
    for account_id in ids:
        row = await session.get(UpstreamAccount, account_id)
        if row is None:
            continue
        try:
            proxy_url = await lease_panel_proxy(store)
            row = await account_pool.refresh_credits(
                session,
                row,
                resources.cipher,
                proxy_url=proxy_url,
                user_agent=DEFAULT_UA,
                impersonate=settings.submit_impersonate,
            )
            verified += 1
            if row.plan_cap == "HARD":
                hard += 1
        except (AdobeGenerateError, AppError):
            failed += 1
    return {"verified": verified, "hard": hard, "failed": failed}


async def _verify_imported_later(
    resources: Resources,
    store: ConfigStore,
    settings: Settings,
    ids: list[int],
) -> None:
    if not ids:
        return
    try:
        async with resources.request_sessions() as session:
            stats = await _verify_imported_accounts(session, store, resources, settings, ids)
            await session.commit()
            logger.info(
                "import verify done count=%s verified=%s hard=%s failed=%s",
                len(ids),
                stats["verified"],
                stats["hard"],
                stats["failed"],
            )
    except Exception:
        logger.exception("import verify failed count=%s", len(ids))


def _schedule_import_verify(
    resources: Resources,
    store: ConfigStore,
    settings: Settings,
    ids: list[int],
) -> None:
    if not ids:
        return
    asyncio.create_task(
        _verify_imported_later(resources, store, settings, ids),
        name="import-verify",
    )


def _imported_ids(imported: dict[str, int | list[int]]) -> list[int]:
    raw = imported.get("ids", [])
    if not isinstance(raw, list):
        return []
    return [int(item) for item in raw if isinstance(item, int)]


@router.get("")
async def list_accounts(
    _admin: AdminDep,
    session: SessionDep,
    resources: ResourcesDep,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    q: str | None = Query(default=None, max_length=128),
    status: str | None = Query(default=None, max_length=16),
    credits_lt: int | None = Query(default=None, ge=0),
) -> dict[str, object]:
    await account_pool.release_expired_parks(session)
    stmt = _accounts_stmt(q=q, status=status, credits_lt=credits_lt)
    total = await session.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = await session.scalars(
        stmt.order_by(UpstreamAccount.id.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    stats = await account_pool.counts(session)
    return {
        "items": [account_pool.view_of(r, resources.cipher) for r in rows],
        "total": int(total or 0),
        "page": page,
        "page_size": page_size,
        "credits_available": stats["credits_available"],
        "accounts_total": stats["total"],
        "accounts_parked": stats["parked"],
        "accounts_hard": stats["hard"],
    }


@router.get("/export")
async def export_cookies(
    _admin: AdminDep,
    session: SessionDep,
    resources: ResourcesDep,
    q: str | None = Query(default=None, max_length=128),
    status: str | None = Query(default=None, max_length=16),
    credits_lt: int | None = Query(default=None, ge=0),
) -> dict[str, object]:
    """Plaintext Cookie dump for admins. Same line format as import. Never log the text."""
    stmt = _accounts_stmt(q=q, status=status, credits_lt=credits_lt)
    rows = await session.scalars(stmt.order_by(UpstreamAccount.id.desc()))
    lines: list[str] = []
    for row in rows:
        cookie = account_pool.cookie_of(row, resources.cipher)
        ident = (row.email_masked or "").strip()
        if ident and not ident.startswith("acct-"):
            lines.append(f"{ident}----{cookie}")
        else:
            lines.append(cookie)
    return {"text": "\n".join(lines), "count": len(lines)}


@router.post("/import")
async def import_cookies(
    payload: ImportCookiesRequest,
    _admin: AdminDep,
    session: SessionDep,
    resources: ResourcesDep,
    store: ConfigStoreDep,
    settings: SettingsDep,
) -> dict[str, int]:
    try:
        records = parse_cookie_text(payload.text)
    except CookieFileError as exc:
        raise AppError(code="cookie_invalid", message="Cookie 格式无效", http_status=422) from exc
    imported = await account_pool.import_records(
        session, resources.cipher, records, group=payload.group
    )
    ids = _imported_ids(imported)
    await session.commit()
    _schedule_import_verify(resources, store, settings, ids)
    return {
        "created": int(imported["created"]),
        "skipped": int(imported["skipped"]),
        "total": int(imported["total"]),
        "verifying": len(ids),
    }


@router.post("/import-file")
async def import_cookie_file(
    _admin: AdminDep,
    session: SessionDep,
    resources: ResourcesDep,
    settings: SettingsDep,
    store: ConfigStoreDep,
) -> dict[str, int]:
    if not settings.test_cookie_file:
        raise AppError(code="cookie_file_unset", message="未配置 TEST_COOKIE_FILE", http_status=422)
    try:
        imported = await account_pool.import_file(
            session, resources.cipher, settings.test_cookie_file, group="alpha"
        )
    except CookieFileError as exc:
        raise AppError(code="cookie_file_invalid", message=str(exc), http_status=422) from exc
    ids = _imported_ids(imported)
    await session.commit()
    _schedule_import_verify(resources, store, settings, ids)
    return {
        "created": int(imported["created"]),
        "skipped": int(imported["skipped"]),
        "total": int(imported["total"]),
        "verifying": len(ids),
    }


@router.delete("")
async def delete_accounts(
    payload: DeleteAccountsRequest,
    _admin: AdminDep,
    session: SessionDep,
    resources: ResourcesDep,
    store: ConfigStoreDep,
) -> dict[str, int]:
    ids = sorted({account_id for account_id in payload.ids if account_id > 0})
    if not ids:
        raise AppError(code="account_ids_empty", message="请选择要删除的账号", http_status=422)
    cfg = await store.load()
    protected = {
        account_id
        for account_id in (
            cfg.normal_canary_account_id,
            cfg.alpha_canary_account_id,
        )
        if account_id and account_id in ids
    }
    if protected:
        joined = ", ".join(str(account_id) for account_id in sorted(protected))
        raise AppError(
            code="account_canary_protected",
            message=f"账号 {joined} 正在作为灰度账号，请先在系统设置中取消",
            http_status=409,
        )
    existing = list(
        await session.scalars(select(UpstreamAccount.id).where(UpstreamAccount.id.in_(ids)))
    )
    if existing:
        await session.execute(delete(UpstreamAccount).where(UpstreamAccount.id.in_(existing)))
        keys = [
            key
            for account_id in existing
            for key in (
                f"{account_pool.LEASE_PREFIX}{account_id}:n",
                f"{account_pool.STREAK_PREFIX}{account_id}",
                f"{account_pool.OBSERVE_PREFIX}{account_id}",
            )
        ]
        try:
            await resources.redis.delete(*keys)
        except Exception:
            pass
    return {"deleted": len(existing)}


@router.patch("/{account_id}")
async def patch_account(
    account_id: int,
    payload: PatchAccountRequest,
    _admin: AdminDep,
    session: SessionDep,
    resources: ResourcesDep,
) -> dict[str, object]:
    row = await session.get(UpstreamAccount, account_id)
    if row is None:
        raise AppError(code="account_not_found", message="账号不存在", http_status=404)
    if payload.status:
        row = await account_pool.set_status(session, account_id, payload.status)
    if payload.group and payload.group != row.group:
        row = await account_pool.set_group(session, row, payload.group)
    if payload.cookie and payload.cookie.strip():
        try:
            records = parse_cookie_text(payload.cookie)
        except CookieFileError as exc:
            raise AppError(
                code="cookie_invalid", message="Cookie 格式无效", http_status=422
            ) from exc
        if len(records) != 1:
            raise AppError(
                code="cookie_invalid", message="编辑只接受一个账号的 Cookie", http_status=422
            )
        row = await account_pool.replace_cookie(session, row, resources.cipher, records[0])
    await session.flush()
    return account_pool.view_of(row, resources.cipher)


@router.post("/{account_id}/refresh")
async def refresh_account(
    account_id: int,
    _admin: AdminDep,
    session: SessionDep,
    resources: ResourcesDep,
    store: ConfigStoreDep,
    settings: SettingsDep,
) -> dict[str, object]:
    row = await session.get(UpstreamAccount, account_id)
    if row is None:
        raise AppError(code="account_not_found", message="账号不存在", http_status=404)
    for attempt in range(3):
        proxy_url = await lease_panel_proxy(store)
        try:
            row = await account_pool.refresh_credits(
                session,
                row,
                resources.cipher,
                proxy_url=proxy_url,
                user_agent=DEFAULT_UA,
                impersonate=settings.submit_impersonate,
            )
            return account_pool.view_of(row, resources.cipher)
        except AdobeGenerateError as exc:
            if exc.code == "proxy_tls" and attempt < 2:
                await asyncio.sleep(0.5 * (attempt + 1))
                continue
            await session.commit()
            raise AppError(
                code=f"account_{exc.code}",
                message="账号凭据或积分验证失败",
                http_status=exc.status_code,
            ) from exc
    raise AppError(code="account_proxy_tls", message="代理连接失败", http_status=502)
