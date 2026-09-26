from collections.abc import Iterator
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app

INTERNAL = {"X-Internal-Token": "test-internal-token"}


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'harvest.db'}",
        redis_url="redis://127.0.0.1:1/0",
        field_encryption_key=Fernet.generate_key().decode(),
        app_secret_key="test-secret-key-with-thirty-two-bytes!!",
        admin_username="root",
        admin_password="root-password-1",
        arp_internal_token="test-internal-token",
        config_cache_seconds=0,
        gen_worker_enabled=False,
    )
    with TestClient(create_app(settings)) as c:
        yield c


def _admin(client: TestClient) -> dict[str, str]:
    res = client.post("/api/auth/login", json={"username": "root", "password": "root-password-1"})
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['token']}"}


def _save_proxy(client: TestClient, **overrides: object) -> None:
    headers = _admin(client)
    cfg = client.get("/api/admin/config", headers=headers).json()
    cfg["proxy"].update(
        {
            "host": "us.arxlabs.io",
            "port": 3010,
            "username": "p9mx",
            "password": "pw-secret",
            "country": "SG",
            "sticky_minutes": 10,
            "sid_length": 8,
            "scheme": "http",
            **overrides,
        }
    )
    saved = client.put("/api/admin/config", headers=headers, json=cfg)
    assert saved.status_code == 200, saved.text


def test_harvester_requires_internal_token(client: TestClient) -> None:
    assert client.get("/admin-api/adobe/harvester/bootstrap").status_code == 401
    assert client.post("/admin-api/adobe/harvester/lease").status_code == 401


def test_bootstrap_reports_proxy_not_ready(client: TestClient) -> None:
    res = client.get("/admin-api/adobe/harvester/bootstrap", headers=INTERNAL)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["proxy_ready"] is False
    assert body["mint_browser_count"] >= 1
    assert body["arp_ttl_seconds"] == 120
    assert body["arp_pool_target"] >= body["arp_min_ready"]
    assert body["arp_mint_batch"] >= 1
    assert "password" not in res.text.lower() or "pw-secret" not in res.text


def test_lease_refuses_until_proxy_configured(client: TestClient) -> None:
    res = client.post("/admin-api/adobe/harvester/lease", headers=INTERNAL)
    assert res.status_code == 422
    assert res.json()["code"] == "proxy_not_configured"


def test_lease_issues_unique_sticky_sessions(client: TestClient) -> None:
    _save_proxy(client)
    first = client.post("/admin-api/adobe/harvester/lease", headers=INTERNAL)
    second = client.post("/admin-api/adobe/harvester/lease", headers=INTERNAL)
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    a, b = first.json(), second.json()
    assert a["sid"] != b["sid"]
    assert a["proxy_url"] != b["proxy_url"]
    assert a["egress_id"].startswith("sid-")
    assert f"p9mx-region-SG-sid-{a['sid']}-t-10" in a["proxy_url"]
    assert a["proxy_url"].startswith("http://")
    assert "pw-secret" not in a["proxy_masked"]
    assert "••••" in a["proxy_masked"]
    boot = client.get("/admin-api/adobe/harvester/bootstrap", headers=INTERNAL).json()
    assert boot["proxy_ready"] is True
    for secret in ("pw-secret",):
        assert secret not in str(boot)


def test_lease_socks5_is_socks5h(client: TestClient) -> None:
    _save_proxy(client, scheme="socks5")
    res = client.post("/admin-api/adobe/harvester/lease", headers=INTERNAL)
    assert res.status_code == 200, res.text
    assert res.json()["proxy_url"].startswith("socks5h://")
    assert res.json()["proxy_masked"].startswith("socks5h://")
