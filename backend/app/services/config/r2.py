"""Cloudflare R2 (S3-compatible) account checks and usage accounting.

boto3 is synchronous, so every call runs in a worker thread. Usage is a full
``ListObjectsV2`` walk (R2 has no cheap "bucket size" API without an account token);
results are cached in Redis so the panel can poll freely.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from pydantic import BaseModel
from redis.asyncio import Redis

from app.services.config.schema import R2Account

logger = logging.getLogger(__name__)

_MAX_PAGES = 200  # 200 × 1000 keys; enough for a 10GB / 1-day-TTL bucket
OBJECT_EXPIRE_DAYS = 1
LIFECYCLE_RULE_ID = "firefly-gen-expire-1d"


def lifecycle_configuration() -> dict[str, Any]:
    """Expire objects after one day; abort leftover multipart uploads the same window."""
    return {
        "Rules": [
            {
                "ID": LIFECYCLE_RULE_ID,
                "Status": "Enabled",
                "Filter": {"Prefix": ""},
                "Expiration": {"Days": OBJECT_EXPIRE_DAYS},
                "AbortIncompleteMultipartUpload": {
                    "DaysAfterInitiation": OBJECT_EXPIRE_DAYS,
                },
            }
        ]
    }


class R2TestResult(BaseModel):
    id: str
    ok: bool
    latency_ms: int
    error: str | None = None


class R2Usage(BaseModel):
    id: str
    used_bytes: int | None = None
    object_count: int | None = None
    over_quota: bool = False
    truncated: bool = False
    cached: bool = False
    fetched_at: float | None = None
    error: str | None = None


def _client(account: R2Account, secret: str) -> Any:
    import boto3
    from botocore.config import Config

    return boto3.client(
        "s3",
        endpoint_url=account.endpoint,
        aws_access_key_id=account.access_key_id,
        aws_secret_access_key=secret,
        region_name="auto",
        config=Config(
            signature_version="s3v4",
            connect_timeout=8,
            read_timeout=15,
            retries={"max_attempts": 2},
        ),
    )


def _safe_error(exc: Exception) -> str:
    text = str(exc)
    # botocore messages can include the request URL; keep only the class + code-ish part.
    return f"{type(exc).__name__}: {text[:140]}"


def _ensure_lifecycle_sync(account: R2Account, secret: str) -> None:
    client = _client(account, secret)
    client.put_bucket_lifecycle_configuration(
        Bucket=account.bucket,
        LifecycleConfiguration=lifecycle_configuration(),
    )


def _test_sync(account: R2Account, secret: str) -> R2TestResult:
    started = time.perf_counter()
    try:
        client = _client(account, secret)
        client.head_bucket(Bucket=account.bucket)
        client.list_objects_v2(Bucket=account.bucket, MaxKeys=1, Prefix=account.prefix or "")
        try:
            client.put_bucket_lifecycle_configuration(
                Bucket=account.bucket,
                LifecycleConfiguration=lifecycle_configuration(),
            )
        except Exception:  # noqa: BLE001 - connectivity succeeded; TTL rule is best-effort
            logger.warning("r2 lifecycle apply failed", extra={"r2_id": account.id}, exc_info=True)
        return R2TestResult(
            id=account.id, ok=True, latency_ms=int((time.perf_counter() - started) * 1000)
        )
    except Exception as exc:  # noqa: BLE001
        return R2TestResult(
            id=account.id,
            ok=False,
            latency_ms=int((time.perf_counter() - started) * 1000),
            error=_safe_error(exc),
        )


def _usage_sync(account: R2Account, secret: str) -> R2Usage:
    try:
        client = _client(account, secret)
        paginator = client.get_paginator("list_objects_v2")
        total = 0
        count = 0
        truncated = False
        for page_no, page in enumerate(
            paginator.paginate(Bucket=account.bucket, Prefix=account.prefix or ""), start=1
        ):
            for obj in page.get("Contents", []):
                total += int(obj.get("Size", 0))
                count += 1
            if page_no >= _MAX_PAGES and page.get("IsTruncated"):
                truncated = True
                break
        return R2Usage(
            id=account.id,
            used_bytes=total,
            object_count=count,
            over_quota=account.quota_bytes > 0 and total >= account.quota_bytes,
            truncated=truncated,
            fetched_at=time.time(),
        )
    except Exception as exc:  # noqa: BLE001
        return R2Usage(id=account.id, error=_safe_error(exc), fetched_at=time.time())


async def test_account(account: R2Account, secret: str | None) -> R2TestResult:
    if not account.access_key_id or not secret:
        return R2TestResult(
            id=account.id, ok=False, latency_ms=0, error="Access Key / Secret 未配置"
        )
    return await asyncio.to_thread(_test_sync, account, secret)


async def ensure_lifecycle(account: R2Account, secret: str) -> None:
    await asyncio.to_thread(_ensure_lifecycle_sync, account, secret)


def _put_sync(account: R2Account, secret: str, key: str, body: bytes, content_type: str) -> str:
    client = _client(account, secret)
    client.put_object(Bucket=account.bucket, Key=key, Body=body, ContentType=content_type)
    base = account.public_base_url.rstrip("/")
    if base:
        return f"{base}/{key}"
    return key


async def upload_object(
    account: R2Account, secret: str, *, key: str, body: bytes, content_type: str
) -> str:
    return await asyncio.to_thread(_put_sync, account, secret, key, body, content_type)


class R2UsageService:
    def __init__(
        self, redis: Redis | None, *, cache_seconds: int = 600, key_prefix: str = "firefly:r2:usage"
    ) -> None:
        self._redis = redis
        self._ttl = cache_seconds
        self._prefix = key_prefix

    def _key(self, account: R2Account) -> str:
        return f"{self._prefix}:{account.id}:{account.bucket}"

    async def _cached(self, account: R2Account) -> R2Usage | None:
        if self._redis is None or self._ttl <= 0:
            return None
        try:
            raw = await self._redis.get(self._key(account))
        except Exception:  # noqa: BLE001
            return None
        if not raw:
            return None
        usage = R2Usage.model_validate(json.loads(raw))
        usage.cached = True
        return usage

    async def _remember(self, account: R2Account, usage: R2Usage) -> None:
        if self._redis is None or self._ttl <= 0 or usage.error:
            return
        try:
            await self._redis.set(self._key(account), usage.model_dump_json(), ex=self._ttl)
        except Exception:  # noqa: BLE001
            logger.debug("r2 usage cache write failed", exc_info=True)

    async def usage(
        self, account: R2Account, secret: str | None, *, force: bool = False
    ) -> R2Usage:
        if not force and (hit := await self._cached(account)):
            return hit
        if not account.access_key_id or not secret:
            return R2Usage(id=account.id, error="Access Key / Secret 未配置")
        result = await asyncio.to_thread(_usage_sync, account, secret)
        await self._remember(account, result)
        return result

    async def usage_all(
        self, accounts: list[tuple[R2Account, str | None]], *, force: bool = False
    ) -> list[R2Usage]:
        return list(
            await asyncio.gather(
                *(self.usage(acc, secret, force=force) for acc, secret in accounts)
            )
        )
