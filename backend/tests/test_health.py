from collections.abc import Awaitable, Callable

from fastapi.testclient import TestClient

from app.api import health
from app.core.config import Settings
from app.core.resources import Resources
from app.main import create_app

HealthCheck = Callable[[Resources], Awaitable[None]]


def test_live_is_available_without_dependency_checks() -> None:
    with TestClient(create_app(Settings())) as client:
        response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_reports_dependencies(monkeypatch: object) -> None:
    async def passing_check(_resources: Resources) -> None:
        return None

    monkeypatch.setattr(health, "check_database", passing_check)  # type: ignore[attr-defined]
    monkeypatch.setattr(health, "check_redis", passing_check)  # type: ignore[attr-defined]

    with TestClient(create_app(Settings())) as client:
        response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json()["checks"] == {"database": True, "redis": True}


def test_ready_returns_503_when_dependency_fails(monkeypatch: object) -> None:
    async def passing_check(_resources: Resources) -> None:
        return None

    async def failing_check(_resources: Resources) -> None:
        raise ConnectionError("not available")

    monkeypatch.setattr(health, "check_database", passing_check)  # type: ignore[attr-defined]
    monkeypatch.setattr(health, "check_redis", failing_check)  # type: ignore[attr-defined]

    with TestClient(create_app(Settings())) as client:
        response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["checks"] == {"database": True, "redis": False}
