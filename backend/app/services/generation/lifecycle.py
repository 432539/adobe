"""Job state machine. Transitions are the only place settle/refund get called.

Workers must go through these helpers so the money side cannot drift from the status:
``succeeded`` ⇒ settled, ``failed``/``rejected`` ⇒ refunded, always and exactly once.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models import JOB_TRANSITIONS, GenerationJob
from app.services import billing


def _transition(job: GenerationJob, to: str) -> None:
    allowed = JOB_TRANSITIONS[job.status]
    if to not in allowed:
        raise AppError(
            code="invalid_transition",
            message=f"任务 {job.id} 不能从 {job.status} 迁移到 {to}",
            http_status=409,
        )
    job.status = to


async def mark_running(session: AsyncSession, job: GenerationJob) -> None:
    _transition(job, "running")
    if job.started_at is None:
        job.started_at = datetime.now(UTC)
    await session.flush()


async def mark_queued(session: AsyncSession, job: GenerationJob) -> None:
    """Park a running job back on the queue (no account / empty ARP). No money movement."""
    if job.status == "queued":
        await session.flush()
        return
    _transition(job, "queued")
    await session.flush()


async def mark_succeeded(
    session: AsyncSession, job: GenerationJob, *, result_urls: list[str]
) -> None:
    if not result_urls:
        raise AppError(code="empty_result", message="成功任务必须有产物", http_status=422)
    _transition(job, "succeeded")
    job.result_urls = result_urls
    job.progress = 100
    job.finished_at = datetime.now(UTC)
    await billing.settle(session, job)
    await session.flush()


async def mark_failed(
    session: AsyncSession, job: GenerationJob, *, code: str, message: str, rejected: bool = False
) -> None:
    _transition(job, "rejected" if rejected else "failed")
    job.error_code = code
    job.error_message = message[:2000]
    job.finished_at = datetime.now(UTC)
    await billing.refund(session, job, reason=code)
    await session.flush()
