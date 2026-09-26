"""Admin operational views: stats, request logs, ARP pool health. All sourced from DB/Redis."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Query
from sqlalchemy import delete as sql_delete
from sqlalchemy import func, select

from app.api.deps import AdminDep, ConfigStoreDep, ResourcesDep, SessionDep, SettingsDep
from app.arp.store import ArpStore
from app.core.errors import AppError
from app.models import ConsumeRecord, GenerationJob, User
from app.models.account import RequestLog, UpstreamAccount
from app.services.config.schema import SystemConfig

router = APIRouter(prefix="/api/admin", tags=["admin-ops"])

_CHANNEL = {"panel": "面板", "openai": "OpenAI", "gemini": "Gemini"}
_CAPACITY_LOG_OUTCOMES = frozenset({"no_account", "arp_empty"})
_SECRET_PARAM_KEYS = frozenset(
    {
        "cookie",
        "access_token",
        "password",
        "proxy_url",
        "token",
        "authorization",
        "upstream_urls",
        "trace",
    }
)
_SHORT_MODEL_NAMES = {
    "nano-banana": "Nano Banana",
    "nano-banana-pro": "Nano Banana Pro",
    "gpt-image-2": "GPT Image 2",
    "gpt-image-2.5-flare": "GPT Image 2.5 Flare",
    "gpt-image-2.5-sunburst": "GPT Image 2.5 Sunburst",
    "gemini-omni-flash": "Gemini Omni Flash",
    "seedance-2.0": "Seedance 2.0",
    "seedance-2.0-fast": "Seedance 2.0 Fast",
    "veo-3.1": "Veo 3.1",
    "veo-3.1-ref": "Veo 3.1 Ref",
    "veo-3.1-fast": "Veo 3.1 Fast",
}


def _arp(resources: ResourcesDep, settings: SettingsDep, cfg_ttl: int, cfg_uses: int) -> ArpStore:
    return ArpStore(
        resources.redis,
        key_prefix=settings.arp_key_prefix,
        ttl_seconds=cfg_ttl,
        max_uses=cfg_uses,
    )


@router.get("/stats/overview")
async def overview(
    _admin: AdminDep,
    session: SessionDep,
    resources: ResourcesDep,
    settings: SettingsDep,
    store: ConfigStoreDep,
) -> dict[str, object]:
    cfg = await store.load()
    now = datetime.now(UTC)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    users_total = int(await session.scalar(select(func.count()).select_from(User)) or 0)
    jobs_today = int(
        await session.scalar(
            select(func.count()).select_from(GenerationJob).where(GenerationJob.created_at >= today)
        )
        or 0
    )
    jobs_total = int(await session.scalar(select(func.count()).select_from(GenerationJob)) or 0)
    done_today = int(
        await session.scalar(
            select(func.count())
            .select_from(GenerationJob)
            .where(GenerationJob.created_at >= today, GenerationJob.status == "succeeded")
        )
        or 0
    )
    revenue = int(
        await session.scalar(
            select(func.coalesce(func.sum(ConsumeRecord.amount), 0)).where(
                ConsumeRecord.status == "settled", ConsumeRecord.created_at >= today
            )
        )
        or 0
    )
    revenue_total = int(
        await session.scalar(
            select(func.coalesce(func.sum(ConsumeRecord.amount), 0)).where(
                ConsumeRecord.status == "settled"
            )
        )
        or 0
    )
    accounts_active = int(
        await session.scalar(
            select(func.count())
            .select_from(UpstreamAccount)
            .where(UpstreamAccount.status == "active")
        )
        or 0
    )
    accounts_total = int(
        await session.scalar(select(func.count()).select_from(UpstreamAccount)) or 0
    )
    credits_available = int(
        await session.scalar(
            select(func.coalesce(func.sum(UpstreamAccount.credits_remaining), 0)).where(
                UpstreamAccount.status.in_(("active", "parked"))
            )
        )
        or 0
    )
    credits_total = int(
        await session.scalar(
            select(func.coalesce(func.sum(UpstreamAccount.credits_total), 0)).where(
                UpstreamAccount.status.in_(("active", "parked"))
            )
        )
        or 0
    )
    queue_depth = int(
        await session.scalar(
            select(func.count())
            .select_from(GenerationJob)
            .where(GenerationJob.status.in_(("queued", "running")))
        )
        or 0
    )
    arp_ready = 0
    arp_age = 0
    try:
        health = await _arp(resources, settings, cfg.arp_ttl_seconds, cfg.arp_max_uses).health()
        arp_ready = int(health.get("ready") or 0)
        arp_age = int(health.get("oldest_age_sec") or 0)
    except Exception:  # noqa: BLE001
        pass
    rate = (done_today / jobs_today) if jobs_today else 0.0
    return {
        "users_total": users_total,
        "users_active_today": users_total,
        "jobs_today": jobs_today,
        "jobs_total": jobs_total,
        "jobs_success_rate": round(rate, 4),
        "revenue_today": revenue,
        "revenue_total": revenue_total,
        "arp_ready": arp_ready,
        "arp_oldest_age_sec": arp_age,
        "accounts_active": accounts_active,
        "accounts_total": accounts_total,
        "credits_available": credits_available,
        "credits_total": credits_total,
        "queue_depth": queue_depth,
        "p95_latency_ms": 0,
    }


@router.get("/arp")
async def arp_status(
    _admin: AdminDep,
    resources: ResourcesDep,
    settings: SettingsDep,
    store: ConfigStoreDep,
) -> dict[str, object]:
    cfg = await store.load()
    arp = _arp(resources, settings, cfg.arp_ttl_seconds, cfg.arp_max_uses)
    snap = await arp.snapshot()
    seen = await arp.harvester_seen_at()
    password = store.proxy_password(cfg)
    return {
        **snap,
        "arp_ttl_seconds": cfg.arp_ttl_seconds,
        "arp_min_ready": cfg.arp_min_ready,
        "arp_pool_target": cfg.arp_pool_target,
        "arp_mint_batch": cfg.arp_mint_batch,
        "arp_max_uses": cfg.arp_max_uses,
        "mint_browser_count": cfg.mint_browser_count,
        "mint_interval_seconds": cfg.mint_interval_seconds,
        "proxy_ready": bool(cfg.proxy.host and cfg.proxy.username and password),
        "harvester_online": seen is not None,
        "harvester_seen_at": ArpStore._iso(seen) if seen is not None else None,
    }


@router.get("/stats/timeseries")
async def timeseries(_admin: AdminDep, session: SessionDep) -> list[dict[str, object]]:
    now = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    points: list[dict[str, object]] = []
    for i in range(23, -1, -1):
        start = now - timedelta(hours=i)
        end = start + timedelta(hours=1)
        n = int(
            await session.scalar(
                select(func.count())
                .select_from(GenerationJob)
                .where(GenerationJob.created_at >= start, GenerationJob.created_at < end)
            )
            or 0
        )
        ok = int(
            await session.scalar(
                select(func.count())
                .select_from(GenerationJob)
                .where(
                    GenerationJob.created_at >= start,
                    GenerationJob.created_at < end,
                    GenerationJob.status == "succeeded",
                )
            )
            or 0
        )
        points.append(
            {
                "ts": start.isoformat(),
                "jobs": n,
                "success_rate": (ok / n) if n else 0,
                "p95_ms": 0,
            }
        )
    return points


@router.get("/stats/egress")
async def egress(_admin: AdminDep, session: SessionDep) -> list[dict[str, object]]:
    rows = await session.execute(
        select(
            RequestLog.egress_id,
            RequestLog.outcome,
            func.count(),
            func.max(RequestLog.created_at),
        ).group_by(RequestLog.egress_id, RequestLog.outcome)
    )
    by_id: dict[str, dict[str, object]] = {}
    for egress_id, outcome, n, last_at in rows:
        bucket = by_id.setdefault(str(egress_id), {"success": 0, "failed": 0, "last_at": ""})
        if outcome == "ok":
            bucket["success"] = int(bucket["success"]) + int(n)
        else:
            bucket["failed"] = int(bucket["failed"]) + int(n)
        if last_at is not None:
            iso = last_at.isoformat()
            if iso > str(bucket["last_at"]):
                bucket["last_at"] = iso
    return sorted(
        [{"egress_id": k, **v} for k, v in by_id.items() if k],
        key=lambda row: str(row.get("last_at") or ""),
        reverse=True,
    )


def _model_names(cfg: SystemConfig) -> dict[str, str]:
    names = {t.model_id: t.model_name for t in cfg.image_pricing}
    names.update({t.model_id: t.model_name for t in cfg.video_pricing})
    return names


def _safe_params(params: object) -> dict[str, object]:
    if not isinstance(params, dict):
        return {}
    return {
        str(k): v
        for k, v in params.items()
        if str(k).lower() not in _SECRET_PARAM_KEYS
    }


def _short_model_name(model_id: str, names: dict[str, str]) -> str:
    if model_id in _SHORT_MODEL_NAMES:
        return _SHORT_MODEL_NAMES[model_id]
    raw = names.get(model_id, model_id)
    raw = raw.removeprefix("普通模型 ").removeprefix("Pro 模型 ")
    if raw.endswith(" / V2"):
        raw = raw[: -len(" / V2")]
    return raw.strip() or model_id


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _job_duration_ms(job: GenerationJob | None) -> int:
    """Wall clock from job create to finish (or now if still generating)."""
    if job is None or job.created_at is None:
        return 0
    start = _aware(job.created_at)
    end = _aware(job.finished_at) if job.finished_at is not None else datetime.now(UTC)
    return max(0, int((end - start).total_seconds() * 1000))


def _job_ui_status(job: GenerationJob | None, outcome: str) -> str:
    if job is None:
        return "succeeded" if outcome == "ok" else "failed"
    if job.status in {"queued", "running"}:
        return "generating"
    if job.status == "succeeded":
        return "succeeded"
    return "failed"


def log_view(
    row: RequestLog | None,
    job: GenerationJob | None,
    names: dict[str, str],
    *,
    username: str = "",
    attempt_count: int = 1,
) -> dict[str, object]:
    """Admin log row joined with the generation job. Never includes cookies/tokens."""
    raw_params = job.params if job and isinstance(job.params, dict) else {}
    stored_upstream = raw_params.get("upstream_urls")
    upstream_urls = (
        [str(u) for u in stored_upstream if u]
        if isinstance(stored_upstream, list)
        else []
    )
    params = _safe_params(raw_params)
    resolution = str(params.get("resolution") or "").strip()
    aspect_ratio = str(params.get("aspect_ratio") or "").strip()
    model_id = job.model if job else ""
    model_name = _short_model_name(model_id, names) if model_id else ""
    bits = [model_name]
    if resolution:
        bits.append(resolution)
    if aspect_ratio and aspect_ratio.lower() != "auto":
        bits.append(aspect_ratio)
    model_label = " ".join(bit for bit in bits if bit)
    channel = _CHANNEL.get(job.source, job.source) if job else ""
    result_urls = list(job.result_urls or []) if job else []
    if not upstream_urls:
        upstream_urls = list(result_urls)
    outcome = row.outcome if row is not None else ""
    job_status = _job_ui_status(job, outcome)
    created = (
        job.created_at.isoformat()
        if job is not None and job.created_at is not None
        else (row.created_at.isoformat() if row is not None else "")
    )
    return {
        "id": row.id if row is not None else 0,
        "job_id": (row.job_id if row is not None else None) or (job.id if job else ""),
        "account_hash": row.account_hash if row is not None else "",
        "egress_id": row.egress_id if row is not None else "",
        "endpoint": row.endpoint if row is not None else "generate",
        "status_code": row.status_code if row is not None else 0,
        "latency_ms": (
            _job_duration_ms(job)
            if job is not None
            else (row.latency_ms if row is not None else 0)
        ),
        "attempt_latency_ms": row.latency_ms if row is not None else 0,
        "retry_count": row.retry_count if row is not None else 0,
        "arp_id": row.arp_id if row is not None else None,
        "outcome": outcome or "pending",
        "created_at": created,
        "model": model_id,
        "model_label": model_label,
        "resolution": resolution,
        "aspect_ratio": aspect_ratio,
        "channel": channel,
        "prompt": job.prompt if job else "",
        "params": params,
        "result_urls": result_urls,
        "upstream_urls": upstream_urls,
        "trace": list(getattr(row, "trace", None) or []) if row is not None else [],
        "kind": job.kind if job else "",
        "username": username,
        "job_status": job_status,
        "attempt_count": attempt_count,
    }


def _latest_logs_by_job():
    return (
        select(func.max(RequestLog.id).label("id"), RequestLog.job_id)
        .where(RequestLog.job_id.is_not(None))
        .group_by(RequestLog.job_id)
        .subquery()
    )


def _apply_log_filters(stmt, latest, *, kind: str | None, status: str | None, q: str | None):
    if kind in {"image", "video"}:
        stmt = stmt.where(GenerationJob.kind == kind)
    if q and q.strip():
        stmt = stmt.where(User.username.ilike(f"%{q.strip()}%"))
    has_log = latest.c.id.is_not(None)
    if status == "succeeded":
        stmt = stmt.where(GenerationJob.status == "succeeded", has_log)
    elif status == "generating":
        stmt = stmt.where(GenerationJob.status.in_(("queued", "running")))
    elif status == "failed":
        stmt = stmt.where(GenerationJob.status.in_(("failed", "rejected")), has_log)
    else:
        stmt = stmt.where(GenerationJob.status.in_(("queued", "running")) | has_log)
    return stmt


@router.get("/logs")
async def logs(
    _admin: AdminDep,
    session: SessionDep,
    store: ConfigStoreDep,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    kind: str | None = Query(default=None, max_length=8),
    status: str | None = Query(default=None, max_length=16),
    q: str | None = Query(default=None, max_length=64),
    grouped: bool = Query(default=True),
) -> dict[str, object]:
    cfg = await store.load()
    names = _model_names(cfg)
    if grouped:
        latest = _latest_logs_by_job()
        stmt = (
            select(GenerationJob, User, RequestLog)
            .outerjoin(User, User.id == GenerationJob.user_id)
            .outerjoin(latest, latest.c.job_id == GenerationJob.id)
            .outerjoin(RequestLog, RequestLog.id == latest.c.id)
        )
        stmt = _apply_log_filters(stmt, latest, kind=kind, status=status, q=q)
        total = await session.scalar(
            select(func.count()).select_from(
                stmt.with_only_columns(GenerationJob.id).order_by(None).subquery()
            )
        )
        result = await session.execute(
            stmt.order_by(GenerationJob.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        triples = result.all()
        job_ids = [job.id for job, _, _ in triples]
        attempt_counts: dict[str, int] = {}
        if job_ids:
            counted = await session.execute(
                select(RequestLog.job_id, func.count())
                .where(
                    RequestLog.job_id.in_(job_ids),
                    RequestLog.outcome.notin_(tuple(_CAPACITY_LOG_OUTCOMES)),
                )
                .group_by(RequestLog.job_id)
            )
            attempt_counts = {str(jid): int(n) for jid, n in counted.all() if jid}
        items = [
            log_view(
                row,
                job,
                names,
                username=user.username if user is not None else "",
                attempt_count=attempt_counts.get(str(job.id), 0),
            )
            for job, user, row in triples
        ]
        return {"items": items, "total": int(total or 0), "page": page, "page_size": page_size}

    stmt = (
        select(RequestLog, GenerationJob, User)
        .outerjoin(GenerationJob, GenerationJob.id == RequestLog.job_id)
        .outerjoin(User, User.id == GenerationJob.user_id)
    )
    if kind in {"image", "video"}:
        stmt = stmt.where(GenerationJob.kind == kind)
    if status == "succeeded":
        stmt = stmt.where(GenerationJob.status == "succeeded")
    elif status == "generating":
        stmt = stmt.where(GenerationJob.status.in_(("queued", "running")))
    elif status == "failed":
        stmt = stmt.where(
            (GenerationJob.status.in_(("failed", "rejected")))
            | ((GenerationJob.id.is_(None)) & (RequestLog.outcome != "ok"))
        )
    if q and q.strip():
        stmt = stmt.where(User.username.ilike(f"%{q.strip()}%"))
    total = await session.scalar(select(func.count()).select_from(stmt.subquery()))
    result = await session.execute(
        stmt.order_by(RequestLog.id.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    pairs = result.all()
    job_ids = [row.job_id for row, _, _ in pairs if row.job_id]
    attempt_counts = {}
    if job_ids:
        counted = await session.execute(
            select(RequestLog.job_id, func.count())
            .where(
                RequestLog.job_id.in_(job_ids),
                RequestLog.outcome.notin_(tuple(_CAPACITY_LOG_OUTCOMES)),
            )
            .group_by(RequestLog.job_id)
        )
        attempt_counts = {str(jid): int(n) for jid, n in counted.all() if jid}
    items = [
        log_view(
            row,
            job,
            names,
            username=user.username if user is not None else "",
            attempt_count=attempt_counts.get(str(row.job_id or ""), 1),
        )
        for row, job, user in pairs
    ]
    return {"items": items, "total": int(total or 0), "page": page, "page_size": page_size}


@router.get("/logs/{job_id}")
async def log_detail(
    job_id: str,
    _admin: AdminDep,
    session: SessionDep,
    store: ConfigStoreDep,
) -> dict[str, object]:
    cfg = await store.load()
    names = _model_names(cfg)
    rows = (
        await session.execute(
            select(RequestLog, GenerationJob, User)
            .outerjoin(GenerationJob, GenerationJob.id == RequestLog.job_id)
            .outerjoin(User, User.id == GenerationJob.user_id)
            .where(RequestLog.job_id == job_id)
            .order_by(RequestLog.id.asc())
        )
    ).all()
    if not rows:
        job = await session.scalar(select(GenerationJob).where(GenerationJob.id == job_id))
        if job is None:
            raise AppError(code="log_not_found", message="日志不存在", http_status=404)
        user = await session.get(User, job.user_id)
        view = log_view(
            None,
            job,
            names,
            username=user.username if user is not None else "",
            attempt_count=0,
        )
        view["attempts"] = []
        return view
    last_row, job, user = rows[-1]
    attempts = [
        item
        for item in rows
        if item[0].outcome not in _CAPACITY_LOG_OUTCOMES
    ]
    view = log_view(
        last_row,
        job,
        names,
        username=user.username if user is not None else "",
        attempt_count=len(attempts),
    )
    view["attempts"] = [
        log_view(
            item,
            job_row,
            names,
            username=owner.username if owner is not None else "",
            attempt_count=len(attempts),
        )
        for item, job_row, owner in attempts
    ]
    return view


@router.delete("/logs")
async def clear_logs(
    _admin: AdminDep,
    session: SessionDep,
    scope: str = Query(default="failed", max_length=16),
) -> dict[str, int]:
    now = datetime.now(UTC)
    stmt = sql_delete(RequestLog)
    if scope == "failed":
        failed_jobs = select(GenerationJob.id).where(
            GenerationJob.status.in_(("failed", "rejected"))
        )
        stmt = stmt.where(
            (RequestLog.job_id.in_(failed_jobs)) | (RequestLog.outcome != "ok")
        )
    elif scope == "older_3d":
        stmt = stmt.where(RequestLog.created_at < now - timedelta(days=3))
    elif scope == "all":
        pass
    else:
        raise AppError(code="invalid_scope", message="清理范围无效", http_status=422)
    result = await session.execute(stmt)
    await session.commit()
    return {"deleted": int(result.rowcount or 0)}
