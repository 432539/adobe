"""Request-log grouping / cleanup and generation-history filters."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.models import GenerationJob
from app.models.account import RequestLog


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'ui.db'}",
        redis_url="redis://127.0.0.1:1/0",
        field_encryption_key=Fernet.generate_key().decode(),
        app_secret_key="test-secret-key-with-thirty-two-bytes!!",
        admin_username="root",
        admin_password="root-password-1",
        config_cache_seconds=0,
        gen_worker_enabled=False,
        media_dir=str(tmp_path / "media"),
    )
    with TestClient(create_app(settings)) as c:
        yield c


def _admin(client: TestClient) -> dict[str, str]:
    res = client.post("/api/auth/login", json={"username": "root", "password": "root-password-1"})
    return {"Authorization": f"Bearer {res.json()['token']}"}


def _user(client: TestClient, admin: dict[str, str]) -> dict[str, str]:
    client.post(
        "/api/admin/users",
        headers=admin,
        json={
            "username": "carol",
            "email": "carol@example.com",
            "password": "carol-pass-1",
            "initial_balance": 1000,
        },
    )
    token = client.post(
        "/api/auth/login", json={"username": "carol", "password": "carol-pass-1"}
    ).json()["token"]
    return {"Authorization": f"Bearer {token}"}


def _submit(client: TestClient, headers: dict[str, str], prompt: str, key: str) -> dict:
    res = client.post(
        "/api/gen/image",
        headers=headers,
        json={
            "model": "nano-banana-pro",
            "prompt": prompt,
            "resolution": "1K",
            "idempotency_key": key,
        },
    )
    assert res.status_code == 202, res.text
    return res.json()


@pytest.mark.asyncio
async def test_logs_group_by_job_and_cleanup(client: TestClient) -> None:
    admin = _admin(client)
    headers = _user(client, admin)
    job = _submit(client, headers, "a red apple", "log-group-01")
    other = _submit(client, headers, "a blue sky", "log-group-02")

    async with client.app.state.resources.request_sessions() as session:
        session.add(
            RequestLog(
                job_id=job["id"],
                account_hash="h1",
                egress_id="e1",
                outcome="timeout",
                status_code=408,
                retry_count=0,
            )
        )
        session.add(
            RequestLog(
                job_id=job["id"],
                account_hash="h2",
                egress_id="e1",
                outcome="ok",
                status_code=200,
                retry_count=1,
            )
        )
        session.add(
            RequestLog(
                job_id=other["id"],
                account_hash="h3",
                egress_id="e2",
                outcome="ok",
                status_code=200,
            )
        )
        await session.commit()

    listed = client.get("/api/admin/logs", headers=admin).json()
    assert listed["total"] == 2
    grouped = next(item for item in listed["items"] if item["job_id"] == job["id"])
    assert grouped["attempt_count"] == 2
    assert grouped["username"] == "carol"
    assert grouped["job_status"] == "generating"
    assert grouped["kind"] == "image"
    assert grouped["latency_ms"] >= 0

    images = client.get("/api/admin/logs", headers=admin, params={"kind": "image"}).json()
    assert images["total"] == 2
    videos = client.get("/api/admin/logs", headers=admin, params={"kind": "video"}).json()
    assert videos["total"] == 0
    by_user = client.get("/api/admin/logs", headers=admin, params={"q": "car"}).json()
    assert by_user["total"] == 2
    missing = client.get("/api/admin/logs", headers=admin, params={"q": "nobody"}).json()
    assert missing["total"] == 0
    generating = client.get(
        "/api/admin/logs", headers=admin, params={"status": "generating"}
    ).json()
    assert generating["total"] == 2

    pending_id = str(uuid4())
    async with client.app.state.resources.request_sessions() as session:
        existing = await session.get(GenerationJob, job["id"])
        assert existing is not None
        session.add(
            GenerationJob(
                id=pending_id,
                user_id=existing.user_id,
                idempotency_key="log-group-pending",
                kind="image",
                model="nano-banana-pro",
                prompt="still queued",
                params={"resolution": "1K"},
                cost=1,
                source="panel",
                status="queued",
            )
        )
        await session.commit()
    pending = {"id": pending_id}
    before_attempt = client.get("/api/admin/logs", headers=admin).json()
    assert any(item["job_id"] == pending["id"] for item in before_attempt["items"])
    stub = next(item for item in before_attempt["items"] if item["job_id"] == pending["id"])
    assert stub["job_status"] == "generating"
    assert stub["attempt_count"] == 0
    pending_detail = client.get(f"/api/admin/logs/{pending['id']}", headers=admin).json()
    assert pending_detail["attempts"] == []
    assert pending_detail["job_status"] == "generating"

    detail = client.get(f"/api/admin/logs/{job['id']}", headers=admin).json()
    assert detail["attempt_count"] == 2
    assert len(detail["attempts"]) == 2
    assert [row["status_code"] for row in detail["attempts"]] == [408, 200]

    async with client.app.state.resources.request_sessions() as session:
        row = await session.get(GenerationJob, job["id"])
        assert row is not None
        row.status = "failed"
        row.error_code = "content_rejected"
        row.error_message = "sensitive content"
        await session.commit()

    failed = client.get("/api/admin/logs", headers=admin, params={"status": "failed"}).json()
    assert failed["total"] == 1
    cleared = client.delete("/api/admin/logs", headers=admin, params={"scope": "failed"}).json()
    assert cleared["deleted"] >= 2
    left = client.get("/api/admin/logs", headers=admin).json()
    left_ids = {item["job_id"] for item in left["items"]}
    assert other["id"] in left_ids
    assert pending["id"] in left_ids
    assert job["id"] not in left_ids


@pytest.mark.asyncio
async def test_jobs_filter_and_cleanup_are_user_scoped(client: TestClient) -> None:
    admin = _admin(client)
    headers = _user(client, admin)
    apple = _submit(client, headers, "a red apple", "hist-job-01")
    sky = _submit(client, headers, "a blue sky", "hist-job-02")

    async with client.app.state.resources.request_sessions() as session:
        row = await session.get(GenerationJob, apple["id"])
        assert row is not None
        row.status = "failed"
        row.error_code = "content_rejected"
        row.error_message = "sensitive content"
        await session.commit()

    failed = client.get("/api/jobs", headers=headers, params={"status": "failed"}).json()
    assert failed["total"] == 1
    assert failed["items"][0]["id"] == apple["id"]
    assert failed["items"][0]["error_code"] == "content_rejected"
    assert failed["items"][0]["error_message"] == "451 违禁词"
    assert failed["items"][0]["prompt"] == "a red apple"

    by_prompt = client.get("/api/jobs", headers=headers, params={"prompt": "blue"}).json()
    assert by_prompt["total"] == 1 and by_prompt["items"][0]["id"] == sky["id"]
    by_model = client.get("/api/jobs", headers=headers, params={"model": "nano-banana-pro"}).json()
    assert by_model["total"] == 2
    generating = client.get("/api/jobs", headers=headers, params={"status": "generating"}).json()
    assert generating["total"] == 1 and generating["items"][0]["id"] == sky["id"]

    assert client.delete("/api/jobs", headers=headers, params={"scope": "nope"}).status_code == 422
    cleared = client.delete("/api/jobs", headers=headers, params={"scope": "failed"}).json()
    assert cleared["deleted"] == 1
    left = client.get("/api/jobs", headers=headers).json()
    assert left["total"] == 1 and left["items"][0]["id"] == sky["id"]
    assert client.get(f"/api/jobs/{apple['id']}", headers=headers).status_code == 404


@pytest.mark.asyncio
async def test_log_latency_is_job_wall_clock_not_last_attempt(client: TestClient) -> None:
    admin = _admin(client)
    headers = _user(client, admin)
    job = _submit(client, headers, "wall clock duration", "log-duration-01")

    async with client.app.state.resources.request_sessions() as session:
        row = await session.get(GenerationJob, job["id"])
        assert row is not None
        row.status = "succeeded"
        row.finished_at = row.created_at + timedelta(seconds=32)
        session.add(
            RequestLog(
                job_id=job["id"],
                account_hash="h1",
                egress_id="e1",
                outcome="ok",
                status_code=200,
                latency_ms=12,
                retry_count=0,
            )
        )
        await session.commit()

    listed = client.get("/api/admin/logs", headers=admin).json()
    item = next(x for x in listed["items"] if x["job_id"] == job["id"])
    assert item["latency_ms"] == 32_000
    assert item["attempt_latency_ms"] == 12

    detail = client.get(f"/api/admin/logs/{job['id']}", headers=admin).json()
    assert detail["latency_ms"] == 32_000
    assert detail["attempts"][0]["attempt_latency_ms"] == 12
    assert detail["attempts"][0]["latency_ms"] == 32_000

    async with client.app.state.resources.request_sessions() as session:
        row = await session.get(GenerationJob, job["id"])
        assert row is not None
        row.status = "running"
        row.finished_at = None
        row.created_at = datetime.now(UTC) - timedelta(seconds=8)
        await session.commit()

    live = client.get("/api/admin/logs", headers=admin).json()
    generating = next(x for x in live["items"] if x["job_id"] == job["id"])
    assert generating["job_status"] == "generating"
    assert 5_000 <= generating["latency_ms"] <= 20_000


def test_public_fail_message_hides_upstream_brand() -> None:
    from app.services.generation.errors import public_fail_message

    assert public_fail_message("content_rejected", 451, "Adobe rejected") == "451 违禁词"
    assert public_fail_message("arp_rejected", 408, "x") == "408 异常"
    assert public_fail_message("rate_limited", 429, "x") == "429 频繁"
    assert "Adobe" not in public_fail_message("upstream_error", 500, "Adobe generation failed")

