"""End-to-end panel flow: bootstrap admin → create user (gets initial KEY) → user generates
with balance enforcement → admin recharge → API-key auth for the public surface."""

from __future__ import annotations

import base64
from collections.abc import Iterator
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from app.api.deps import ApiKeyDep
from app.core.config import Settings
from app.main import create_app

probe = APIRouter()


@probe.get("/v1/whoami")
async def whoami(principal: ApiKeyDep) -> dict[str, int]:
    return {"user_id": principal.user_id, "api_key_id": principal.api_key_id}


@pytest.fixture
def app(tmp_path: Path) -> FastAPI:
    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'panel.db'}",
        redis_url="redis://127.0.0.1:1/0",
        field_encryption_key=Fernet.generate_key().decode(),
        app_secret_key="test-secret-key-with-thirty-two-bytes!!",
        admin_username="root",
        admin_password="root-password-1",
        config_cache_seconds=0,
        gen_worker_enabled=False,
        media_dir=str(tmp_path / "media"),
    )
    application = create_app(settings)
    application.include_router(probe)
    return application


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c


def _login(client: TestClient, username: str, password: str) -> dict[str, str]:
    res = client.post("/api/auth/login", json={"username": username, "password": password})
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['token']}"}


def _create_user(
    client: TestClient, admin: dict[str, str], balance: int
) -> tuple[dict[str, str], str, int]:
    res = client.post(
        "/api/admin/users",
        headers=admin,
        json={
            "username": "bob",
            "email": "bob@example.com",
            "password": "bob-password-1",
            "initial_balance": balance,
        },
    )
    assert res.status_code == 201, res.text
    body = res.json()
    return _login(client, "bob", "bob-password-1"), body["initial_key"]["plain"], body["user"]["id"]


def test_bootstrap_admin_and_user_creation_with_initial_key(client: TestClient) -> None:
    admin = _login(client, "root", "root-password-1")
    me = client.get("/api/auth/me", headers=admin).json()
    assert me["role"] == "admin"

    res = client.post(
        "/api/admin/users",
        headers=admin,
        json={
            "username": "bob",
            "email": "bob@example.com",
            "password": "bob-password-1",
            "initial_balance": 500,
        },
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["user"]["balance"] == 500
    key = body["initial_key"]
    assert key["name"] == "default" and key["plain"].startswith("sk-") and len(key["plain"]) > 30
    assert key["key_prefix"] == key["plain"][:10]

    # Plaintext never comes back again.
    user = _login(client, "bob", "bob-password-1")
    keys = client.get("/api/keys", headers=user).json()
    assert (
        len(keys) == 1 and keys[0]["plain"] is None and keys[0]["key_prefix"] == key["key_prefix"]
    )

    # The opening balance is a real recharge in the ledger, attributed to the operator.
    ledger = client.get("/api/ledger", headers=user).json()
    assert (
        ledger["total"] == 1
        and ledger["items"][0]["type"] == "recharge"
        and ledger["items"][0]["delta"] == 500
    )
    recs = client.get("/api/admin/records/recharge", headers=admin).json()
    assert recs["items"][0]["operator"] == "root"

    dup = client.post(
        "/api/admin/users",
        headers=admin,
        json={"username": "bob", "email": "other@example.com", "password": "bob-password-1"},
    )
    assert dup.status_code == 409


def test_generation_is_gated_by_balance(client: TestClient) -> None:
    admin = _login(client, "root", "root-password-1")
    user, _, uid = _create_user(client, admin, balance=25)  # nano-banana-pro 1K = 10
    # Lift the per-user concurrency cap so this test exercises the money guard only.
    assert (
        client.patch(
            f"/api/admin/users/{uid}", headers=admin, json={"concurrency_limit": 10}
        ).status_code
        == 200
    )

    def gen(key: str) -> object:
        return client.post(
            "/api/gen/image",
            headers=user,
            json={
                "model": "nano-banana-pro",
                "prompt": "cat",
                "resolution": "1K",
                "idempotency_key": key,
            },
        )

    first = gen("idem-0001")
    second = gen("idem-0002")
    third = gen("idem-0003")
    assert first.status_code == 202 and second.status_code == 202  # type: ignore[attr-defined]
    assert third.status_code == 402 and third.json()["code"] == "insufficient_balance"  # type: ignore[attr-defined]

    me = client.get("/api/auth/me", headers=user).json()
    assert me["balance"] == 5
    jobs = client.get("/api/jobs", headers=user).json()
    assert jobs["total"] == 2 and all(
        j["status"] == "queued" and j["cost"] == 10 for j in jobs["items"]
    )

    # Replay with the same idempotency key: 200, same job, no new charge.
    replay = gen("idem-0001")
    assert replay.status_code == 200 and replay.json()["id"] == first.json()["id"]  # type: ignore[attr-defined]
    assert client.get("/api/auth/me", headers=user).json()["balance"] == 5

    # Admin tops up, then the third job goes through.
    top = client.post(
        f"/api/admin/users/{uid}/recharge", headers=admin, json={"amount": 100, "remark": "test"}
    )
    assert top.status_code == 200 and top.json()["balance"] == 105
    assert gen("idem-0003").status_code == 202  # type: ignore[attr-defined]
    rec = client.get(f"/api/admin/users/{uid}/reconcile", headers=admin).json()
    assert rec["consistent"] is True and rec["balance"] == 95

    # Consume records are visible to the user and the admin.
    mine = client.get("/api/records/consume", headers=user).json()
    assert mine["total"] == 3 and all(r["status"] == "pending" for r in mine["items"])
    assert client.get("/api/admin/records/consume", headers=admin).json()["total"] == 3


def test_unknown_model_and_bad_input_are_rejected(client: TestClient) -> None:
    admin = _login(client, "root", "root-password-1")
    user, _, _ = _create_user(client, admin, balance=1000)
    res = client.post(
        "/api/gen/image",
        headers=user,
        json={"model": "does-not-exist", "prompt": "x", "idempotency_key": "idem-0001"},
    )
    assert res.status_code == 422 and res.json()["code"] == "model_unsupported"
    res = client.post(
        "/api/gen/video",
        headers=user,
        json={
            "model": "seedance-2.0",
            "prompt": "x",
            "duration": 0,
            "idempotency_key": "idem-0002",
        },
    )
    assert res.status_code == 422  # pydantic: duration >= 1
    res = client.post(
        "/api/gen/video",
        headers=user,
        json={
            "model": "seedance-2.0-fast",
            "prompt": "x",
            "resolution": "1080p",
            "duration": 5,
            "idempotency_key": "idem-fast-1080",
        },
    )
    assert res.status_code == 422 and res.json()["code"] == "resolution_unsupported"
    assert client.get("/api/auth/me", headers=user).json()["balance"] == 1000


def test_role_isolation_and_disable(client: TestClient) -> None:
    admin = _login(client, "root", "root-password-1")
    user, _, uid = _create_user(client, admin, balance=0)
    assert client.get("/api/admin/users", headers=user).status_code == 403
    assert client.get("/api/admin/config", headers=user).status_code == 403

    # Users only ever see their own jobs.
    assert client.get("/api/jobs/not-mine", headers=user).status_code == 404

    disabled = client.patch(f"/api/admin/users/{uid}", headers=admin, json={"status": "disabled"})
    assert disabled.status_code == 200 and disabled.json()["status"] == "disabled"
    # Existing JWT is now useless; login is refused too.
    assert client.get("/api/auth/me", headers=user).status_code == 403
    assert (
        client.post(
            "/api/auth/login", json={"username": "bob", "password": "bob-password-1"}
        ).status_code
        == 403
    )


def test_api_key_auth_for_public_surface(client: TestClient) -> None:
    admin = _login(client, "root", "root-password-1")
    user, plain, uid = _create_user(client, admin, balance=0)

    ok = client.get("/v1/whoami", headers={"Authorization": f"Bearer {plain}"})
    assert ok.status_code == 200 and ok.json()["user_id"] == uid
    ok2 = client.get("/v1/whoami", headers={"x-goog-api-key": plain})
    assert ok2.status_code == 200

    assert (
        client.get(
            "/v1/whoami", headers={"Authorization": "Bearer sk-definitely-not-a-real-key-0000"}
        ).status_code
        == 401
    )
    assert client.get("/v1/whoami").status_code == 401

    # Revoke → immediately rejected; a new key works.
    key_id = client.get("/api/keys", headers=user).json()[0]["id"]
    assert client.delete(f"/api/keys/{key_id}", headers=user).json()["status"] == "revoked"
    assert client.get("/v1/whoami", headers={"Authorization": f"Bearer {plain}"}).status_code == 401
    new = client.post("/api/keys", headers=user, json={"name": "second"}).json()
    assert new["plain"].startswith("sk-")
    assert (
        client.get("/v1/whoami", headers={"Authorization": f"Bearer {new['plain']}"}).status_code
        == 200
    )


def test_models_come_from_pricing_table(client: TestClient) -> None:
    admin = _login(client, "root", "root-password-1")
    models = client.get("/api/gen/models", headers=admin).json()
    ids = {m["id"] for m in models}
    assert ids == {
        "nano-banana",
        "nano-banana-pro",
        "gpt-image-2",
        "gpt-image-2.5-flare",
        "gpt-image-2.5-sunburst",
        "gemini-omni-flash",
        "seedance-2.0",
        "seedance-2.0-fast",
    }
    pro = next(m for m in models if m["id"] == "nano-banana-pro")
    assert pro["billing"] == "per_tier" and pro["tiers"][0]["price"] == 10
    assert pro["submit_ready"] is True
    assert "t2i" in pro["modes"] and pro["max_reference_images"] == 8
    assert all(not m["id"].startswith("veo-") for m in models)
    omni = next(m for m in models if m["id"] == "gemini-omni-flash")
    assert omni["modes"] == ["t2v", "i2v"]
    seedance = next(m for m in models if m["id"] == "seedance-2.0")
    assert seedance["modes"] == ["t2v", "i2v"]
    seedance_fast = next(m for m in models if m["id"] == "seedance-2.0-fast")
    assert seedance_fast["modes"] == ["t2v", "i2v"]
    assert seedance_fast["resolutions"] == ["720p"]
    assert seedance["resolutions"] == ["720p", "1080p"]


_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def test_panel_multipart_image_is_staged_not_base64(client: TestClient, tmp_path: Path) -> None:
    admin = _login(client, "root", "root-password-1")
    user, _, _ = _create_user(client, admin, balance=1000)
    res = client.post(
        "/api/gen/image",
        headers=user,
        data={
            "model": "nano-banana",
            "prompt": "keep the icon as a studio product render",
            "aspect_ratio": "1:1",
            "resolution": "1K",
            "idempotency_key": "idem-file-01",
        },
        files={"images": ("logo.png", _PNG, "image/png")},
    )
    assert res.status_code == 202, res.text
    refs = res.json()["params"]["reference_blob_ids"]
    assert len(refs) == 1 and refs[0].startswith("file:refs/")
    assert (tmp_path / "media" / refs[0][5:]).is_file()


def test_create_image_commits_before_enqueue() -> None:
    import inspect

    from app.api import gen

    src = inspect.getsource(gen.create_image)
    commit_at = src.find("await session.commit()")
    enqueue_at = src.find("await _enqueue_job(")
    assert commit_at != -1 and enqueue_at != -1
    assert commit_at < enqueue_at
    assert "BackgroundTasks" not in src
