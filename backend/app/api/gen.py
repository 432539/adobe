"""Panel generation entry + job queries. Billing happens inside ``gate.submit_job`` only."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, TypeVar

from fastapi import APIRouter, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from sqlalchemy import delete as sql_delete
from sqlalchemy import func, select
from starlette.datastructures import UploadFile

from app.adobe.payloads import IMAGE_MAX_REFS, VIDEO_MAX_REFS, catalog_for
from app.adobe.refs import MAX_IMAGE_BYTES, stage_reference_bytes
from app.api.deps import ConfigStoreDep, SessionDep, UserDep
from app.core.config import Settings
from app.core.errors import AppError
from app.models import GenerationJob
from app.schemas.panel import (
    CreateImageRequest,
    CreateVideoRequest,
    JobOut,
    ModelOut,
    Page,
    job_of,
)
from app.services.config.schema import SystemConfig
from app.services.generation.gate import GenerationCommand, submit_job
from app.services.generation.worker import enqueue

router = APIRouter(prefix="/api", tags=["generation"])
_T = TypeVar("_T", CreateImageRequest, CreateVideoRequest)
logger = logging.getLogger(__name__)


def models_from_pricing(cfg: SystemConfig) -> list[ModelOut]:
    out: list[ModelOut] = []
    for tier in cfg.image_pricing:
        extra = catalog_for(tier.model_id)
        out.append(
            ModelOut(
                id=tier.model_id,
                name=tier.model_name,
                kind="image",
                price=min((t.price for t in tier.tiers), default=0),
                billing="per_tier",
                tiers=[t.model_dump() for t in tier.tiers],
                note=tier.model_note or "",
                aspect_ratios=list(extra["aspect_ratios"]),
                resolutions=list(extra["resolutions"]),
                supports_edit=bool(extra.get("supports_edit")),
                modes=list(extra.get("modes") or []),
                max_reference_images=int(extra.get("max_reference_images") or 0),
                submit_ready=bool(extra.get("submit_ready")),
            )
        )
    for v in cfg.video_pricing:
        extra = catalog_for(v.model_id)
        if not extra.get("submit_ready"):
            continue
        durations = extra.get("durations")
        out.append(
            ModelOut(
                id=v.model_id,
                name=v.model_name,
                kind="video",
                price=v.price,
                billing=v.billing,
                note=v.note,
                aspect_ratios=list(extra["aspect_ratios"]),
                resolutions=list(extra["resolutions"]),
                durations=list(durations) if durations else None,
                modes=list(extra.get("modes") or []),
                max_reference_images=int(extra.get("max_reference_images") or 0),
                submit_ready=bool(extra.get("submit_ready")),
            )
        )
    return out


async def _enqueue_job(redis: Any, job_id: str) -> None:
    """Push after the request transaction has committed. BackgroundTasks can race commit."""
    try:
        await enqueue(redis, job_id)
    except Exception:  # noqa: BLE001
        logger.warning("job %s left queued: redis enqueue failed", job_id)


def _parse_model(model: type[_T], data: dict[str, Any]) -> _T:
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        raise RequestValidationError(exc.errors()) from exc


def _form_strings(form: Any, key: str) -> list[str]:
    values: list[str] = []
    for item in form.getlist(key):
        if isinstance(item, str) and item.strip():
            values.append(item.strip())
    return values


async def _read_image_request(
    request: Request,
) -> tuple[CreateImageRequest, list[tuple[bytes, str]]]:
    ctype = (request.headers.get("content-type") or "").lower()
    if ctype.startswith("multipart/form-data"):
        form = await request.form()
        payload = _parse_model(
            CreateImageRequest,
            {
                "model": str(form.get("model") or ""),
                "prompt": str(form.get("prompt") or ""),
                "aspect_ratio": str(form.get("aspect_ratio") or "1:1"),
                "resolution": str(form.get("resolution") or "1K"),
                "idempotency_key": str(form.get("idempotency_key") or ""),
                "reference_blob_ids": _form_strings(form, "reference_blob_ids"),
            },
        )
        buffers: list[tuple[bytes, str]] = []
        for item in form.getlist("images"):
            if not isinstance(item, UploadFile):
                continue
            buffers.append((await item.read(MAX_IMAGE_BYTES + 1), item.content_type or ""))
        return payload, buffers
    try:
        body = await request.json()
    except Exception as exc:
        raise AppError(code="invalid_request", message="请求体无效", http_status=422) from exc
    if not isinstance(body, dict):
        raise AppError(code="invalid_request", message="请求体无效", http_status=422)
    return _parse_model(CreateImageRequest, body), []


async def _read_video_request(
    request: Request,
) -> tuple[CreateVideoRequest, list[tuple[bytes, str]]]:
    ctype = (request.headers.get("content-type") or "").lower()
    if ctype.startswith("multipart/form-data"):
        form = await request.form()
        duration_raw = str(form.get("duration") or "5")
        try:
            duration = int(duration_raw)
        except ValueError:
            duration = 0
        payload = _parse_model(
            CreateVideoRequest,
            {
                "model": str(form.get("model") or ""),
                "prompt": str(form.get("prompt") or ""),
                "aspect_ratio": str(form.get("aspect_ratio") or "16:9"),
                "resolution": str(form.get("resolution") or "720p"),
                "duration": duration,
                "idempotency_key": str(form.get("idempotency_key") or ""),
                "reference_blob_ids": _form_strings(form, "reference_blob_ids"),
            },
        )
        buffers: list[tuple[bytes, str]] = []
        for item in form.getlist("images"):
            if not isinstance(item, UploadFile):
                continue
            buffers.append((await item.read(MAX_IMAGE_BYTES + 1), item.content_type or ""))
        return payload, buffers
    try:
        body = await request.json()
    except Exception as exc:
        raise AppError(code="invalid_request", message="请求体无效", http_status=422) from exc
    if not isinstance(body, dict):
        raise AppError(code="invalid_request", message="请求体无效", http_status=422)
    return _parse_model(CreateVideoRequest, body), []


def _stage_buffers(
    job: GenerationJob,
    buffers: list[tuple[bytes, str]],
    media_dir: str,
    *,
    max_refs: int,
) -> None:
    existing = [
        str(item).strip()
        for item in list(job.params.get("reference_blob_ids") or [])
        if str(item).strip()
    ]
    if len(existing) + len(buffers) > max_refs:
        raise AppError(code="invalid_request", message="参考图数量超出上限", http_status=422)
    staged = [
        stage_reference_bytes(Path(media_dir), job.id, len(existing) + index, data, declared)
        for index, (data, declared) in enumerate(buffers)
    ]
    job.params = {**dict(job.params or {}), "reference_blob_ids": existing + staged}


@router.get("/gen/models", response_model=list[ModelOut])
async def list_models(_user: UserDep, store: ConfigStoreDep) -> list[ModelOut]:
    return models_from_pricing(await store.load())


@router.post("/gen/image", response_model=JobOut, status_code=202)
async def create_image(
    user: UserDep,
    session: SessionDep,
    store: ConfigStoreDep,
    response: Response,
    request: Request,
) -> JobOut:
    payload, buffers = await _read_image_request(request)
    if len(payload.reference_blob_ids) + len(buffers) > IMAGE_MAX_REFS:
        raise AppError(code="invalid_request", message="参考图数量超出上限", http_status=422)
    cmd = GenerationCommand(
        kind="image",
        model=payload.model,
        prompt=payload.prompt,
        idempotency_key=payload.idempotency_key,
        source="panel",
        resolution=payload.resolution,
        params={
            "aspect_ratio": payload.aspect_ratio,
            "reference_blob_ids": payload.reference_blob_ids,
        },
    )
    job, created = await submit_job(session, user_id=user.id, cmd=cmd, cfg=await store.load())
    if not created:
        response.status_code = 200
        return job_of(job)
    if buffers:
        settings: Settings = request.app.state.settings
        _stage_buffers(job, buffers, settings.media_dir, max_refs=IMAGE_MAX_REFS)
    await session.commit()
    await _enqueue_job(request.app.state.resources.redis, job.id)
    return job_of(job)


@router.post("/gen/video", response_model=JobOut, status_code=202)
async def create_video(
    user: UserDep,
    session: SessionDep,
    store: ConfigStoreDep,
    response: Response,
    request: Request,
) -> JobOut:
    payload, buffers = await _read_video_request(request)
    if len(payload.reference_blob_ids) + len(buffers) > VIDEO_MAX_REFS:
        raise AppError(code="invalid_request", message="参考图数量超出上限", http_status=422)
    cmd = GenerationCommand(
        kind="video",
        model=payload.model,
        prompt=payload.prompt,
        idempotency_key=payload.idempotency_key,
        source="panel",
        resolution=payload.resolution,
        duration_seconds=payload.duration,
        params={
            "aspect_ratio": payload.aspect_ratio,
            "reference_blob_ids": payload.reference_blob_ids,
        },
    )
    job, created = await submit_job(session, user_id=user.id, cmd=cmd, cfg=await store.load())
    if not created:
        response.status_code = 200
        return job_of(job)
    if buffers:
        settings: Settings = request.app.state.settings
        _stage_buffers(job, buffers, settings.media_dir, max_refs=VIDEO_MAX_REFS)
    await session.commit()
    await _enqueue_job(request.app.state.resources.redis, job.id)
    return job_of(job)


def _jobs_owned(user_id: int):
    return select(GenerationJob).where(GenerationJob.user_id == user_id)


def _apply_job_filters(
    base,
    *,
    status: str | None,
    kind: str | None,
    prompt: str | None,
    model: str | None,
):
    if status == "generating":
        base = base.where(GenerationJob.status.in_(("queued", "running")))
    elif status == "failed":
        base = base.where(GenerationJob.status.in_(("failed", "rejected")))
    elif status:
        base = base.where(GenerationJob.status == status)
    if kind in {"image", "video"}:
        base = base.where(GenerationJob.kind == kind)
    if prompt and prompt.strip():
        base = base.where(GenerationJob.prompt.ilike(f"%{prompt.strip()}%"))
    if model and model.strip():
        base = base.where(GenerationJob.model.ilike(f"%{model.strip()}%"))
    return base


@router.get("/jobs", response_model=Page[JobOut])
async def list_jobs(
    user: UserDep,
    session: SessionDep,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    status: str | None = Query(default=None, max_length=16),
    kind: str | None = Query(default=None, max_length=8),
    prompt: str | None = Query(default=None, max_length=200),
    model: str | None = Query(default=None, max_length=64),
) -> Page[JobOut]:
    base = _apply_job_filters(
        _jobs_owned(user.id),
        status=status,
        kind=kind,
        prompt=prompt,
        model=model,
    )
    total = await session.scalar(select(func.count()).select_from(base.subquery()))
    rows = await session.scalars(
        base.order_by(GenerationJob.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return Page(
        items=[job_of(j) for j in rows], total=int(total or 0), page=page, page_size=page_size
    )


@router.delete("/jobs")
async def clear_jobs(
    user: UserDep,
    session: SessionDep,
    scope: str = Query(default="failed", max_length=16),
) -> dict[str, int]:
    now = datetime.now(UTC)
    stmt = sql_delete(GenerationJob).where(GenerationJob.user_id == user.id)
    if scope == "failed":
        stmt = stmt.where(GenerationJob.status.in_(("failed", "rejected")))
    elif scope == "older_3d":
        stmt = stmt.where(GenerationJob.created_at < now - timedelta(days=3))
    elif scope == "all":
        pass
    else:
        raise AppError(code="invalid_scope", message="清理范围无效", http_status=422)
    result = await session.execute(stmt)
    await session.commit()
    return {"deleted": int(result.rowcount or 0)}


@router.get("/jobs/{job_id}", response_model=JobOut)
async def get_job(job_id: str, user: UserDep, session: SessionDep) -> JobOut:
    job = await session.scalar(
        select(GenerationJob).where(GenerationJob.id == job_id, GenerationJob.user_id == user.id)
    )
    if job is None:
        raise AppError(code="job_not_found", message="任务不存在", http_status=404)
    return job_of(job)
