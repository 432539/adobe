"""Balance mutations. Every path here is atomic and leaves a ledger row.

The hold is a *conditional* UPDATE (``balance >= cost AND status = 'active'``) so it is
correct under concurrency on any SQL engine without relying on row locks: N parallel
submits against a balance that covers K of them succeed exactly K times.

Callers own the transaction (``async with session.begin()`` or explicit commit); every
function here only flushes so it composes with job creation in the same transaction.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models import BalanceLedger, ConsumeRecord, GenerationJob, RechargeRecord, User


class InsufficientBalance(AppError):
    def __init__(self, need: int, have: int) -> None:
        super().__init__(
            code="insufficient_balance",
            message=f"余额不足：需要 {need / 100:.2f}，当前 {have / 100:.2f}",
            http_status=402,
            detail={"need": need, "have": have},
        )


class UserNotActive(AppError):
    def __init__(self) -> None:
        super().__init__(code="user_disabled", message="账号已禁用", http_status=403)


class DuplicateBillingEvent(AppError):
    def __init__(self, job_id: str, kind: str) -> None:
        super().__init__(
            code="duplicate_billing_event",
            message=f"任务 {job_id} 已存在 {kind} 记录",
            http_status=409,
        )


def _check_amount(amount: int) -> None:
    if not isinstance(amount, int) or isinstance(amount, bool) or amount <= 0:
        raise AppError(code="invalid_amount", message="金额必须为正整数（分）", http_status=422)


async def _conditional_debit(session: AsyncSession, user_id: int, amount: int) -> int:
    """Debit only if affordable and active. Returns new balance or raises."""
    result = await session.execute(
        update(User)
        .where(User.id == user_id, User.status == "active", User.balance >= amount)
        .values(balance=User.balance - amount)
        .returning(User.balance)
    )
    row = result.first()
    if row is not None:
        return int(row[0])
    # Distinguish the failure so the caller gets an honest error. Re-read columns instead
    # of ``session.get`` so a User already in the identity map cannot report a stale balance.
    state = (
        await session.execute(select(User.status, User.balance).where(User.id == user_id))
    ).first()
    if state is None:
        raise AppError(code="user_not_found", message="用户不存在", http_status=404)
    status, have = state
    if status != "active":
        raise UserNotActive()
    raise InsufficientBalance(need=amount, have=int(have))


async def _credit(session: AsyncSession, user_id: int, amount: int) -> int:
    result = await session.execute(
        update(User)
        .where(User.id == user_id)
        .values(balance=User.balance + amount)
        .returning(User.balance)
    )
    row = result.first()
    if row is None:
        raise AppError(code="user_not_found", message="用户不存在", http_status=404)
    return int(row[0])


# --------------------------------------------------------------------------- job lifecycle
async def hold(
    session: AsyncSession, *, user_id: int, job_id: str, amount: int, model: str
) -> BalanceLedger:
    """Pre-charge at submit. Raises 402 when the user cannot afford it; nothing is written."""
    _check_amount(amount)
    balance_after = await _conditional_debit(session, user_id, amount)
    ledger = BalanceLedger(
        user_id=user_id,
        delta=-amount,
        balance_after=balance_after,
        type="consume",
        job_id=job_id,
        remark=f"生成预扣 {model}",
    )
    session.add(ledger)
    session.add(
        ConsumeRecord(user_id=user_id, job_id=job_id, model=model, amount=amount, status="pending")
    )
    try:
        await session.flush()
    except IntegrityError as exc:
        raise DuplicateBillingEvent(job_id, "hold") from exc
    return ledger


async def settle(session: AsyncSession, job: GenerationJob) -> None:
    """Confirm the hold after success. Balance is untouched; the pending record becomes final."""
    result = await session.execute(
        update(ConsumeRecord)
        .where(ConsumeRecord.job_id == job.id, ConsumeRecord.status == "pending")
        .values(status="settled", settled_at=datetime.now(UTC))
        .returning(ConsumeRecord.id)
    )
    if result.first() is None:
        existing = await session.scalar(
            select(ConsumeRecord.status).where(ConsumeRecord.job_id == job.id)
        )
        if existing != "settled":
            raise DuplicateBillingEvent(job.id, f"settle(state={existing})")


async def refund(session: AsyncSession, job: GenerationJob, *, reason: str) -> BalanceLedger | None:
    """Return the hold after failure/rejection. Idempotent: a second call is a no-op."""
    already = await session.scalar(
        select(BalanceLedger).where(BalanceLedger.job_id == job.id, BalanceLedger.type == "refund")
    )
    if already is not None:
        return None
    if job.cost <= 0:
        return None
    balance_after = await _credit(session, job.user_id, job.cost)
    ledger = BalanceLedger(
        user_id=job.user_id,
        delta=job.cost,
        balance_after=balance_after,
        type="refund",
        job_id=job.id,
        remark=f"生成失败退回：{reason}"[:255],
    )
    session.add(ledger)
    await session.execute(
        update(ConsumeRecord)
        .where(ConsumeRecord.job_id == job.id, ConsumeRecord.status == "pending")
        .values(status="refunded", settled_at=datetime.now(UTC))
    )
    job.refunded_at = datetime.now(UTC)
    try:
        await session.flush()
    except IntegrityError as exc:  # lost a race with a parallel refund
        raise DuplicateBillingEvent(job.id, "refund") from exc
    return ledger


# --------------------------------------------------------------------------- admin money
async def recharge(
    session: AsyncSession,
    *,
    user_id: int,
    amount: int,
    operator_id: int | None,
    method: str = "manual",
    remark: str = "",
) -> RechargeRecord:
    _check_amount(amount)
    balance_after = await _credit(session, user_id, amount)
    record = RechargeRecord(
        user_id=user_id,
        amount=amount,
        method=method,
        operator_id=operator_id,
        remark=remark,
        status="success",
    )
    session.add(record)
    await session.flush()
    session.add(
        BalanceLedger(
            user_id=user_id,
            delta=amount,
            balance_after=balance_after,
            type="recharge",
            ref_id=str(record.id),
            remark=remark or f"充值（{method}）",
        )
    )
    await session.flush()
    return record


async def adjust(
    session: AsyncSession, *, user_id: int, delta: int, operator_id: int | None, remark: str
) -> BalanceLedger:
    """Manual correction. Negative adjustments can never push balance below zero."""
    if not isinstance(delta, int) or delta == 0:
        raise AppError(
            code="invalid_amount", message="调账金额必须为非零整数（分）", http_status=422
        )
    if not remark.strip():
        raise AppError(code="remark_required", message="调账必须填写备注", http_status=422)
    if delta > 0:
        balance_after = await _credit(session, user_id, delta)
    else:
        result = await session.execute(
            update(User)
            .where(User.id == user_id, User.balance >= -delta)
            .values(balance=User.balance + delta)
            .returning(User.balance)
        )
        row = result.first()
        if row is None:
            user = await session.get(User, user_id)
            if user is None:
                raise AppError(code="user_not_found", message="用户不存在", http_status=404)
            raise InsufficientBalance(need=-delta, have=user.balance)
        balance_after = int(row[0])
    record = RechargeRecord(
        user_id=user_id,
        amount=delta,
        method="adjust",
        operator_id=operator_id,
        remark=remark,
        status="success",
    )
    session.add(record)
    await session.flush()
    ledger = BalanceLedger(
        user_id=user_id,
        delta=delta,
        balance_after=balance_after,
        type="adjust",
        ref_id=str(record.id),
        remark=remark,
    )
    session.add(ledger)
    await session.flush()
    return ledger


# --------------------------------------------------------------------------- audit
async def reconcile(session: AsyncSession, user_id: int) -> tuple[int, int]:
    """(cached balance, ledger sum). They must be equal; a mismatch is a bug."""
    balance = await session.scalar(select(User.balance).where(User.id == user_id))
    ledger_sum = await session.scalar(
        select(func.coalesce(func.sum(BalanceLedger.delta), 0)).where(
            BalanceLedger.user_id == user_id
        )
    )
    return int(balance or 0), int(ledger_sum or 0)
