"""The one and only way to create a generation job.

Order matters and is deliberate:

1. quote      – price comes from the live pricing table; unknown model → 422, never 0.
2. identity   – user must be active.
3. idempotency– same (user, idempotency_key) returns the existing job, no second hold.
4. concurrency– queued+running jobs below the user's limit (else 429).
5. hold       – conditional debit; 402 if unaffordable, and nothing has been written.
6. persist    – job + ledger + consume_record commit together.

Panel, OpenAI and Gemini adapters all build a ``GenerationCommand`` and call
:func:`submit_job`. Nothing else may insert into ``generation_jobs``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.adobe.payloads import catalog_for
from app.core.errors import AppError
from app.models import GenerationJob, User
from app.services import billing
from app.services.config import pricing
from app.services.config.schema import SystemConfig

Kind = Literal["image", "video"]
Source = Literal["panel", "openai", "gemini"]


@dataclass(slots=True)
class GenerationCommand:
    kind: Kind
    model: str
    prompt: str
    idempotency_key: str
    source: Source = "panel"
    api_key_id: int | None = None
    resolution: str = "1K"
    duration_seconds: int = 0
    params: dict[str, Any] = field(default_factory=dict)


def quote(cfg: SystemConfig, cmd: GenerationCommand) -> int:
    extra = catalog_for(cmd.model)
    if not extra.get("submit_ready"):
        raise AppError(
            code="model_unsupported", message=f"模型 {cmd.model} 暂未接入提交链路", http_status=422
        )
    allowed = [str(item) for item in extra.get("resolutions") or []]
    if allowed:
        if cmd.kind == "image":
            label = pricing.normalize_resolution(cmd.resolution)
            ok = label in allowed
        else:
            label = cmd.resolution.strip().lower()
            ok = label in {item.lower() for item in allowed}
        if not ok:
            raise AppError(
                code="resolution_unsupported",
                message=f"{cmd.model} 不支持分辨率 {cmd.resolution}",
                http_status=422,
            )
    if cmd.kind == "image":
        price = pricing.image_cost(cfg, cmd.model, cmd.resolution)
    else:
        price = pricing.video_cost(cfg, cmd.model, cmd.duration_seconds)
    if price <= 0:
        raise AppError(
            code="pricing_invalid", message=f"模型 {cmd.model} 计费为 0，已拒绝", http_status=422
        )
    return price


async def _active_jobs(session: AsyncSession, user_id: int) -> int:
    n = await session.scalar(
        select(func.count())
        .select_from(GenerationJob)
        .where(GenerationJob.user_id == user_id, GenerationJob.status.in_(("queued", "running")))
    )
    return int(n or 0)


async def submit_job(
    session: AsyncSession, *, user_id: int, cmd: GenerationCommand, cfg: SystemConfig
) -> tuple[GenerationJob, bool]:
    """Returns ``(job, created)``. ``created=False`` means the idempotency key matched."""
    if not cmd.prompt.strip() and not cmd.params.get("reference_blob_ids"):
        raise AppError(code="prompt_required", message="提示词不能为空", http_status=422)
    if not cmd.idempotency_key or len(cmd.idempotency_key) > 128:
        raise AppError(
            code="idempotency_key_invalid", message="idempotency_key 缺失或过长", http_status=422
        )

    cost = quote(cfg, cmd)

    user = await session.get(User, user_id)
    if user is None:
        raise AppError(code="user_not_found", message="用户不存在", http_status=404)
    if user.status != "active":
        raise billing.UserNotActive()

    existing = await session.scalar(
        select(GenerationJob).where(
            GenerationJob.user_id == user_id, GenerationJob.idempotency_key == cmd.idempotency_key
        )
    )
    if existing is not None:
        return existing, False

    limit = user.concurrency_limit or cfg.user_concurrency_default
    if await _active_jobs(session, user_id) >= limit:
        raise AppError(
            code="concurrency_limit",
            message=f"并发任务已达上限 {limit}，请等待现有任务完成",
            http_status=429,
        )

    job_id = str(uuid.uuid4())
    # Hold first: if it raises, nothing below runs and the transaction has no job row.
    await billing.hold(session, user_id=user_id, job_id=job_id, amount=cost, model=cmd.model)
    job = GenerationJob(
        id=job_id,
        user_id=user_id,
        api_key_id=cmd.api_key_id,
        source=cmd.source,
        idempotency_key=cmd.idempotency_key,
        kind=cmd.kind,
        model=cmd.model,
        prompt=cmd.prompt,
        params={
            **cmd.params,
            "resolution": cmd.resolution,
            **({"duration": cmd.duration_seconds} if cmd.kind == "video" else {}),
        },
        status="queued",
        cost=cost,
    )
    session.add(job)
    try:
        await session.flush()
    except IntegrityError:
        # Two identical submits raced past the SELECT; roll back ours and return the winner.
        await session.rollback()
        winner = await session.scalar(
            select(GenerationJob).where(
                GenerationJob.user_id == user_id,
                GenerationJob.idempotency_key == cmd.idempotency_key,
            )
        )
        if winner is None:  # pragma: no cover - defensive
            raise
        return winner, False
    return job, True
