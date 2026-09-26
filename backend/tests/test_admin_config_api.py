from collections.abc import Iterator
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from app.api import admin_config
from app.core.config import Settings
from app.main import create_app
from app.services.config.proxy import ProxyTestResult


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'panel.db'}",
        redis_url="redis://127.0.0.1:1/0",  # unreachable on purpose: broadcast must be best-effort
        field_encryption_key=Fernet.generate_key().decode(),
        app_secret_key="test-secret-key-with-thirty-two-bytes!!",
        admin_username="root",
        admin_password="root-password-1",
        config_cache_seconds=0,
        gen_worker_enabled=False,
    )
    with TestClient(create_app(settings)) as c:
        yield c


def _login(client: TestClient) -> dict[str, str]:
    res = client.post("/api/auth/login", json={"username": "root", "password": "root-password-1"})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["role"] == "admin"
    return {"Authorization": f"Bearer {body['token']}"}


def test_login_rejects_bad_password(client: TestClient) -> None:
    res = client.post("/api/auth/login", json={"username": "root", "password": "nope-nope-nope"})
    assert res.status_code == 401
    assert res.json()["code"] == "bad_credentials"


def test_config_requires_admin_token(client: TestClient) -> None:
    assert client.get("/api/admin/config").status_code == 401
    assert (
        client.get("/api/admin/config", headers={"Authorization": "Bearer junk"}).status_code == 401
    )


def test_config_roundtrip_keeps_secrets_server_side(client: TestClient) -> None:
    headers = _login(client)

    initial = client.get("/api/admin/config", headers=headers)
    assert initial.status_code == 200
    cfg = initial.json()
    assert cfg["proxy"]["password_set"] is False
    assert cfg["proxy"]["upload_via_proxy"] is False
    assert cfg["generation_timeout_seconds"] == 300
    assert cfg["user_concurrency_default"] == 2

    cfg["proxy"].update(
        host="us.arxlabs.io",
        port=3010,
        username="p9mx",
        password="pw-secret",
        country="sg",
        sticky_minutes=10,
        sid_length=8,
        upload_via_proxy=True,
    )
    cfg["cloakbrowser_license_key"] = "cb_licence_plain"
    cfg["r2_accounts"] = [
        {
            "name": "cf1",
            "endpoint": "https://ffa7964b824a013739abcdef.r2.cloudflarestorage.com",
            "bucket": "media",
            "public_base_url": "https://pub-x.r2.dev",
            "enabled": True,
            "quota_bytes": 10 * 1024**3,
            "access_key_id": "AKIAXXXXXXXXXXXXee82",
            "secret_access_key": "SK-plain",
        }
    ]
    cfg["sync_timeout_seconds"] = 200
    saved = client.put("/api/admin/config", headers=headers, json=cfg)
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["proxy"]["password_set"] is True
    assert body["proxy"]["country"] == "SG"
    assert body["proxy"]["upload_via_proxy"] is True
    assert body["sync_timeout_seconds"] == 200
    assert body["r2_accounts"][0]["key_suffix"] == "ee82"
    assert body["r2_accounts"][0]["id"]
    for secret in ("pw-secret", "SK-plain", "cb_licence_plain", "AKIAXXXX"):
        assert secret not in saved.text

    # Echo the masked view back untouched → secrets must survive.
    again = client.put("/api/admin/config", headers=headers, json=body)
    assert again.status_code == 200, again.text
    assert again.json()["proxy"]["password_set"] is True
    assert (
        again.json()["cloakbrowser_license_key_masked"] == body["cloakbrowser_license_key_masked"]
    )

    reread = client.get("/api/admin/config", headers=headers).json()
    assert reread["proxy"]["password_set"] is True
    assert reread["r2_accounts"][0]["key_suffix"] == "ee82"


def test_proxy_test_uses_stored_password_and_fresh_sid(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = _login(client)
    cfg = client.get("/api/admin/config", headers=headers).json()
    cfg["proxy"].update(host="us.arxlabs.io", username="p9mx", password="pw-secret", country="SG")
    client.put("/api/admin/config", headers=headers, json=cfg)

    seen: dict[str, object] = {}

    async def fake_test_proxy(cfg_in: object, password: str, **kwargs: object) -> ProxyTestResult:
        seen["password"] = password
        seen["kwargs"] = kwargs
        return ProxyTestResult(
            ok=True, proxy_masked="http://masked", egress_ip="1.2.3.4", country="SG", latency_ms=321
        )

    monkeypatch.setattr(admin_config, "test_proxy", fake_test_proxy)

    payload = {**cfg["proxy"], "password": None, "password_set": True}
    res = client.post("/api/admin/config/proxy/test", headers=headers, json=payload)
    assert res.status_code == 200, res.text
    assert res.json()["egress_ip"] == "1.2.3.4"
    assert seen["password"] == "pw-secret"

    # Without host the endpoint refuses instead of probing.
    bad = client.post("/api/admin/config/proxy/test", headers=headers, json={**payload, "host": ""})
    assert bad.status_code == 422


def test_r2_test_without_secret_reports_cleanly(client: TestClient) -> None:
    headers = _login(client)
    res = client.post(
        "/api/admin/config/r2/test",
        headers=headers,
        json={
            "draft": {
                "name": "cf1",
                "endpoint": "https://x.r2.cloudflarestorage.com",
                "bucket": "b",
            }
        },
    )
    assert res.status_code == 200
    assert res.json()["ok"] is False
    assert "未配置" in res.json()["error"]

    missing = client.post("/api/admin/config/r2/test", headers=headers, json={"id": "nope"})
    assert missing.status_code == 404


def test_pricing_quote(client: TestClient) -> None:
    headers = _login(client)
    image = client.get(
        "/api/admin/config/pricing/quote",
        headers=headers,
        params={"model": "nano-banana-pro", "resolution": "2K"},
    )
    assert image.json()["price"] == 15 and image.json()["display"] == "0.15"
    video = client.get(
        "/api/admin/config/pricing/quote",
        headers=headers,
        params={"model": "seedance-2.0", "kind": "video", "duration": 5},
    )
    assert video.json()["price"] == 100 and video.json()["display"] == "1.00"


def test_announcement_is_readable_by_logged_in_users(client: TestClient) -> None:
    assert client.get("/api/announcement").status_code == 401

    admin = _login(client)
    empty = client.get("/api/announcement", headers=admin)
    assert empty.status_code == 200
    assert empty.json() == {"announcement": ""}

    cfg = client.get("/api/admin/config", headers=admin).json()
    cfg["announcement"] = "维护窗口今晚 02:00"
    saved = client.put("/api/admin/config", headers=admin, json=cfg)
    assert saved.status_code == 200, saved.text

    created = client.post(
        "/api/admin/users",
        headers=admin,
        json={
            "username": "bob",
            "email": "bob@example.com",
            "password": "bob-password-1",
            "initial_balance": 0,
        },
    )
    assert created.status_code == 201, created.text
    login = client.post("/api/auth/login", json={"username": "bob", "password": "bob-password-1"})
    user = {"Authorization": f"Bearer {login.json()['token']}"}

    note = client.get("/api/announcement", headers=user)
    assert note.status_code == 200
    assert note.json() == {"announcement": "维护窗口今晚 02:00"}
    assert "proxy" not in note.json()
    assert client.get("/api/admin/config", headers=user).status_code == 403


def test_five_minute_ttl_lifts_five_minute_sticky(client: TestClient) -> None:
    headers = _login(client)
    cfg = client.get("/api/admin/config", headers=headers).json()
    cfg["proxy"].update(
        host="us.arxlabs.io",
        username="p9mx",
        password="pw-secret",
        country="SG",
        sticky_minutes=5,
    )
    cfg["arp_ttl_seconds"] = 300
    saved = client.put("/api/admin/config", headers=headers, json=cfg)
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["arp_ttl_seconds"] == 300
    assert body["proxy"]["sticky_minutes"] == 6
