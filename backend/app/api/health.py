import asyncio
from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.config import Settings
from app.core.resources import Resources

router = APIRouter(prefix="/health", tags=["health"])
HealthCheck = Callable[[Resources], Awaitable[None]]


async def check_database(resources: Resources) -> None:
    async with resources.database.connect() as connection:
        await connection.execute(text("SELECT 1"))


async def check_redis(resources: Resources) -> None:
    await resources.redis.ping()


async def _bounded_check(check: HealthCheck, resources: Resources, timeout_seconds: float) -> bool:
    try:
        async with asyncio.timeout(timeout_seconds):
            await check(resources)
    except Exception:
        return False
    return True


@router.get("/live")
async def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
async def ready(request: Request) -> JSONResponse:
    resources: Resources = request.app.state.resources
    settings: Settings = request.app.state.settings
    database_ok, redis_ok = await asyncio.gather(
        _bounded_check(check_database, resources, settings.health_timeout_seconds),
        _bounded_check(check_redis, resources, settings.health_timeout_seconds),
    )
    ready_now = database_ok and redis_ok
    return JSONResponse(
        status_code=200 if ready_now else 503,
        content={
            "status": "ready" if ready_now else "not_ready",
            "checks": {"database": database_ok, "redis": redis_ok},
        },
    )
