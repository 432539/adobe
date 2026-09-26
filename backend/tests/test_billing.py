"""Service-level billing invariants. Runs on SQLite; every guard used is a conditional
UPDATE / unique constraint, so the same guarantees hold on PostgreSQL."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.errors import AppError
from app.models import BalanceLedger, Base, ConsumeRecord, GenerationJob
from app.services import billing
from app.services import users as users_service
from app.services.config.schema import default_config
from app.services.generation import lifecycle
from app.services.generation.gate import GenerationCommand, submit_job

PEPPER = "unit-test-pepper-with-32-bytes-len!!"


@pytest.fixture
async def sessions(tmp_path: Path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'billing.db'}", connect_args={"timeout": 30}
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def _user(sessions: async_sessionmaker[AsyncSession], balance: int) -> int:
    async with sessions() as s:
        created = await users_service.create_user(
            s,
            username="alice",
            email="a@x.io",
            password="password123",
            pepper=PEPPER,
            initial_balance=balance,
        )
        await s.commit()
        return created.user.id


def _cmd(key: str, model: str = "nano-banana-pro", resolution: str = "1K") -> GenerationCommand:
    return GenerationCommand(
        kind="image", model=model, prompt="a cat", idempotency_key=key, resolution=resolution
    )


async def _submit(
    sessions: async_sessionmaker[AsyncSession], user_id: int, key: str
) -> GenerationJob | AppError:
    cfg = default_config()
    async with sessions() as s:
        try:
            job, _ = await submit_job(s, user_id=user_id, cmd=_cmd(key), cfg=cfg)
            await s.commit()
            return job
        except AppError as exc:
            await s.rollback()
            return exc


async def _balance(sessions: async_sessionmaker[AsyncSession], user_id: int) -> tuple[int, int]:
    async with sessions() as s:
        return await billing.reconcile(s, user_id)


# --------------------------------------------------------------------------- the big one
async def test_parallel_submits_never_overspend(sessions: async_sessionmaker[AsyncSession]) -> None:
    # nano-banana-pro 1K costs 10; balance covers exactly 3 jobs.
    uid = await _user(sessions, balance=30)
    cfg = default_config()
    cfg.user_concurrency_default = 64  # concurrency guard must not mask the money guard here

    async def one(i: int) -> GenerationJob | AppError:
        async with sessions() as s:
            try:
                job, _ = await submit_job(s, user_id=uid, cmd=_cmd(f"k-{i}"), cfg=cfg)
                await s.commit()
                return job
            except AppError as exc:
                await s.rollback()
                return exc

    results = await asyncio.gather(*(one(i) for i in range(12)))
    jobs = [r for r in results if isinstance(r, GenerationJob)]
    errors = [r for r in results if isinstance(r, AppError)]

    assert len(jobs) == 3
    assert len(errors) == 9 and all(e.code == "insufficient_balance" for e in errors)

    balance, ledger_sum = await _balance(sessions, uid)
    assert balance == 0 and ledger_sum == 0
    async with sessions() as s:
        assert await s.scalar(select(func.count()).select_from(GenerationJob)) == 3
        assert await s.scalar(select(func.count()).select_from(ConsumeRecord)) == 3


async def test_insufficient_balance_writes_nothing(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    uid = await _user(sessions, balance=5)
    res = await _submit(sessions, uid, "k1")
    assert isinstance(res, AppError) and res.http_status == 402
    async with sessions() as s:
        assert await s.scalar(select(func.count()).select_from(GenerationJob)) == 0
        assert await s.scalar(select(func.count()).select_from(ConsumeRecord)) == 0
        # only the opening recharge in the ledger
        assert await s.scalar(select(func.count()).select_from(BalanceLedger)) == 1
    assert await _balance(sessions, uid) == (5, 5)


async def test_failure_refunds_exactly_once(sessions: async_sessionmaker[AsyncSession]) -> None:
    uid = await _user(sessions, balance=100)
    job = await _submit(sessions, uid, "k1")
    assert isinstance(job, GenerationJob) and job.cost == 10
    assert (await _balance(sessions, uid))[0] == 90

    async with sessions() as s:
        j = await s.get(GenerationJob, job.id)
        assert j is not None
        await lifecycle.mark_running(s, j)
        await lifecycle.mark_failed(s, j, code="upstream_408", message="parked")
        await s.commit()
    assert await _balance(sessions, uid) == (100, 100)

    # Second refund attempt (e.g. worker retry) is a no-op, and no further transition is legal.
    async with sessions() as s:
        j = await s.get(GenerationJob, job.id)
        assert j is not None and j.status == "failed" and j.refunded_at is not None
        assert await billing.refund(s, j, reason="again") is None
        with pytest.raises(AppError) as exc:
            await lifecycle.mark_succeeded(s, j, result_urls=["x"])
        assert exc.value.code == "invalid_transition"
        record = await s.scalar(select(ConsumeRecord).where(ConsumeRecord.job_id == job.id))
        assert record is not None and record.status == "refunded"
    assert await _balance(sessions, uid) == (100, 100)


async def test_success_settles_and_cannot_be_refunded_later(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    uid = await _user(sessions, balance=100)
    job = await _submit(sessions, uid, "k1")
    assert isinstance(job, GenerationJob)
    async with sessions() as s:
        j = await s.get(GenerationJob, job.id)
        assert j is not None
        await lifecycle.mark_running(s, j)
        await lifecycle.mark_succeeded(s, j, result_urls=["https://cdn/x.png"])
        await s.commit()
    async with sessions() as s:
        j = await s.get(GenerationJob, job.id)
        assert j is not None and j.status == "succeeded"
        with pytest.raises(AppError):
            await lifecycle.mark_failed(s, j, code="late", message="nope")
        record = await s.scalar(select(ConsumeRecord).where(ConsumeRecord.job_id == job.id))
        assert record is not None and record.status == "settled"
    assert await _balance(sessions, uid) == (90, 90)


async def test_idempotency_key_returns_same_job_without_second_hold(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    uid = await _user(sessions, balance=100)
    first = await _submit(sessions, uid, "same")
    second = await _submit(sessions, uid, "same")
    assert isinstance(first, GenerationJob) and isinstance(second, GenerationJob)
    assert first.id == second.id
    assert await _balance(sessions, uid) == (90, 90)


async def test_unpriced_model_is_rejected_before_any_write(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    uid = await _user(sessions, balance=100)
    cfg = default_config().model_copy(update={"image_pricing": []})
    async with sessions() as s:
        with pytest.raises(AppError) as exc:
            await submit_job(s, user_id=uid, cmd=_cmd("k", model="nano-banana-pro"), cfg=cfg)
        assert exc.value.code == "pricing_missing"
    assert await _balance(sessions, uid) == (100, 100)


async def test_disabled_user_cannot_submit(sessions: async_sessionmaker[AsyncSession]) -> None:
    uid = await _user(sessions, balance=100)
    async with sessions() as s:
        from app.models import User

        u = await s.get(User, uid)
        assert u is not None
        u.status = "disabled"
        await s.commit()
    res = await _submit(sessions, uid, "k")
    assert isinstance(res, AppError) and res.code == "user_disabled"


async def test_concurrency_limit(sessions: async_sessionmaker[AsyncSession]) -> None:
    uid = await _user(sessions, balance=1000)
    cfg = default_config()
    cfg.user_concurrency_default = 2
    async with sessions() as s:
        await submit_job(s, user_id=uid, cmd=_cmd("a"), cfg=cfg)
        await submit_job(s, user_id=uid, cmd=_cmd("b"), cfg=cfg)
        with pytest.raises(AppError) as exc:
            await submit_job(s, user_id=uid, cmd=_cmd("c"), cfg=cfg)
        assert exc.value.http_status == 429
        await s.commit()
    assert (await _balance(sessions, uid))[0] == 980


async def test_adjust_cannot_go_negative(sessions: async_sessionmaker[AsyncSession]) -> None:
    uid = await _user(sessions, balance=50)
    async with sessions() as s:
        with pytest.raises(billing.InsufficientBalance):
            await billing.adjust(s, user_id=uid, delta=-60, operator_id=None, remark="oops")
        await billing.adjust(s, user_id=uid, delta=-50, operator_id=None, remark="clawback")
        await s.commit()
    assert await _balance(sessions, uid) == (0, 0)


async def test_amounts_must_be_positive_ints(sessions: async_sessionmaker[AsyncSession]) -> None:
    uid = await _user(sessions, balance=0)
    async with sessions() as s:
        for bad in (0, -1, True):
            with pytest.raises(AppError):
                await billing.recharge(s, user_id=uid, amount=bad, operator_id=None)  # type: ignore[arg-type]
