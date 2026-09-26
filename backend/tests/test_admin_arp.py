import base64
import json
from pathlib import Path
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from redis import Redis

from app.core.config import Settings
from app.main import create_app


def publish_payload() -> dict[str, object]:
    token = base64.b64encode(
        json.dumps(
            {"sid": "sid", "ark": "ark", "bfp": "bfp", "ftr": "id_ts__UDF43-xx=-3-v2_tt"}
        ).encode()
    ).decode()
    return {
        "tokens": [
            {
                "t": token,
                "proxy_url": "socks5h://user:password@proxy.example:1080",
                "egress_id": "residential-1",
                "ua": "Mozilla/5.0 Chrome/148.0.0.0 Safari/537.36",
                "ch": {
                    "platform": "Windows",
                    "platformVersion": "15.0.0",
                    "fullVersionList": [{"brand": "Google Chrome", "version": "148.0.0.0"}],
                    "architecture": "x86",
                    "bitness": "64",
                },
            }
        ]
    }


def _settings(tmp_path: Path, prefix: str) -> Settings:
    return Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'arp.db'}",
        redis_url="redis://127.0.0.1:6379/15",
        arp_key_prefix=prefix,
        arp_internal_token="test-internal-token",
        field_encryption_key=Fernet.generate_key().decode(),
        app_secret_key="test-secret-key-with-thirty-two-bytes!!",
        admin_username="root",
        admin_password="root-password-1",
        gen_worker_enabled=False,
        config_cache_seconds=0,
    )


def test_admin_arp_rejects_missing_internal_token() -> None:
    with TestClient(create_app(Settings(gen_worker_enabled=False))) as client:
        response = client.get("/admin-api/adobe/arp")

    assert response.status_code == 401
    assert response.json()["code"] == "internal_auth_failed"


def test_admin_arp_publish_and_health(tmp_path: Path) -> None:
    redis = Redis.from_url("redis://127.0.0.1:6379/15", decode_responses=True)
    try:
        redis.ping()
    except Exception:
        pytest.skip("Redis is not available")

    prefix = f"test:admin-arp:{uuid4().hex}"
    headers = {"X-Internal-Token": "test-internal-token"}
    try:
        with TestClient(create_app(_settings(tmp_path, prefix))) as client:
            published = client.post(
                "/admin-api/adobe/arp",
                headers=headers,
                json=publish_payload(),
            )
            health = client.get("/admin-api/adobe/arp", headers=headers)
    finally:
        keys = list(redis.scan_iter(f"{prefix}:*"))
        if keys:
            redis.delete(*keys)
        redis.close()

    assert published.status_code == 200
    assert published.json()["published"] == 1
    assert health.status_code == 200
    assert health.json()["ready"] == 1
    assert "proxy_url" not in health.text


def test_publish_ttl_follows_panel_config(tmp_path: Path) -> None:
    redis = Redis.from_url("redis://127.0.0.1:6379/15", decode_responses=True)
    try:
        redis.ping()
    except Exception:
        pytest.skip("Redis is not available")

    prefix = f"test:admin-arp-ttl:{uuid4().hex}"
    internal = {"X-Internal-Token": "test-internal-token"}
    try:
        with TestClient(create_app(_settings(tmp_path, prefix))) as client:
            login = client.post(
                "/api/auth/login", json={"username": "root", "password": "root-password-1"}
            )
            assert login.status_code == 200, login.text
            admin = {"Authorization": f"Bearer {login.json()['token']}"}
            cfg = client.get("/api/admin/config", headers=admin).json()
            cfg["arp_ttl_seconds"] = 45
            cfg["mint_interval_seconds"] = 20
            cfg["proxy"].update(
                host="us.arxlabs.io",
                username="p9mx",
                password="pw-secret",
                country="SG",
                sticky_minutes=10,
            )
            saved = client.put("/api/admin/config", headers=admin, json=cfg)
            assert saved.status_code == 200, saved.text
            published = client.post(
                "/admin-api/adobe/arp", headers=internal, json=publish_payload()
            )
            assert published.status_code == 200, published.text
            raw = redis.get(f"{prefix}:item:{published.json()['ids'][0]}")
            assert raw is not None
            item = json.loads(raw)
            assert item["expires_at"] - item["minted_at"] == 45
    finally:
        keys = list(redis.scan_iter(f"{prefix}:*"))
        if keys:
            redis.delete(*keys)
        redis.close()


def test_panel_arp_status_is_real_and_redacted(tmp_path: Path) -> None:
    redis = Redis.from_url("redis://127.0.0.1:6379/15", decode_responses=True)
    try:
        redis.ping()
    except Exception:
        pytest.skip("Redis is not available")

    prefix = f"test:admin-arp-panel:{uuid4().hex}"
    internal = {"X-Internal-Token": "test-internal-token"}
    try:
        with TestClient(create_app(_settings(tmp_path, prefix))) as client:
            login = client.post(
                "/api/auth/login", json={"username": "root", "password": "root-password-1"}
            )
            admin = {"Authorization": f"Bearer {login.json()['token']}"}
            published = client.post(
                "/admin-api/adobe/arp", headers=internal, json=publish_payload()
            )
            assert published.status_code == 200, published.text
            res = client.get("/api/admin/arp", headers=admin)
            assert res.status_code == 200, res.text
            body = res.json()
            assert body["ready"] == 1
            assert body["tickets"][0]["egress_id"] == "residential-1"
            assert body["tickets"][0]["max_uses"] == 10
            assert body["events"][0]["type"] == "published"
            assert body["harvester_online"] is False
            assert body["harvester_seen_at"] is None
            assert "password" not in res.text
            assert "proxy_url" not in res.text
            assert "socks5h://" not in res.text
    finally:
        keys = list(redis.scan_iter(f"{prefix}:*"))
        if keys:
            redis.delete(*keys)
        redis.close()


def test_harvester_online_follows_bootstrap_heartbeat(tmp_path: Path) -> None:
    redis = Redis.from_url("redis://127.0.0.1:6379/15", decode_responses=True)
    try:
        redis.ping()
    except Exception:
        pytest.skip("Redis is not available")

    prefix = f"test:admin-arp-hb:{uuid4().hex}"
    internal = {"X-Internal-Token": "test-internal-token"}
    try:
        with TestClient(create_app(_settings(tmp_path, prefix))) as client:
            login = client.post(
                "/api/auth/login", json={"username": "root", "password": "root-password-1"}
            )
            admin = {"Authorization": f"Bearer {login.json()['token']}"}
            before = client.get("/api/admin/arp", headers=admin)
            assert before.status_code == 200, before.text
            assert before.json()["harvester_online"] is False
            assert before.json()["ready"] == 0
            boot = client.get("/admin-api/adobe/harvester/bootstrap", headers=internal)
            assert boot.status_code == 200, boot.text
            after = client.get("/api/admin/arp", headers=admin)
            assert after.status_code == 200, after.text
            body = after.json()
            assert body["harvester_online"] is True
            assert body["harvester_seen_at"]
            assert body["ready"] == 0
            assert redis.get(f"{prefix}:harvester:heartbeat") is not None
    finally:
        keys = list(redis.scan_iter(f"{prefix}:*"))
        if keys:
            redis.delete(*keys)
        redis.close()


def test_publish_rejects_ftr_without_v2_tt(tmp_path: Path) -> None:
    redis = Redis.from_url("redis://127.0.0.1:6379/15", decode_responses=True)
    try:
        redis.ping()
    except Exception:
        pytest.skip("Redis is not available")

    prefix = f"test:admin-arp-ftr:{uuid4().hex}"
    headers = {"X-Internal-Token": "test-internal-token"}
    body = publish_payload()
    token = base64.b64encode(
        json.dumps({"sid": "sid", "ark": "ark", "bfp": "bfp", "ftr": "id_ts__UDF43-xx"}).encode()
    ).decode()
    body["tokens"][0]["t"] = token
    try:
        with TestClient(create_app(_settings(tmp_path, prefix))) as client:
            rejected = client.post("/admin-api/adobe/arp", headers=headers, json=body)
            health = client.get("/admin-api/adobe/arp", headers=headers)
    finally:
        keys = list(redis.scan_iter(f"{prefix}:*"))
        if keys:
            redis.delete(*keys)
        redis.close()

    assert rejected.status_code == 422
    payload = rejected.json()
    assert payload["code"] == "validation_error"
    assert "v2_tt" in payload["message"]
    assert token not in rejected.text
    assert health.status_code == 200
    assert health.json()["ready"] == 0
