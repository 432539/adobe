import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI

from app.admin_api.arp import router as arp_admin_router
from app.admin_api.harvester import router as harvester_admin_router
from app.api.account import router as account_router
from app.api.admin_accounts import router as admin_accounts_router
from app.api.admin_config import router as admin_config_router
from app.api.admin_ops import router as admin_ops_router
from app.api.admin_users import router as admin_users_router
from app.api.auth import router as auth_router
from app.api.gen import router as gen_router
from app.api.health import router as health_router
from app.api.keys import router as keys_router
from app.api.media import router as media_router
from app.core.config import Settings, get_settings
from app.core.errors import install_error_handlers
from app.core.logging import configure_logging
from app.core.resources import Resources, create_resources
from app.models import Base
from app.services import accounts as account_pool
from app.services import users as users_service
from app.core.support import SUPPORT_QQ_LABEL
from app.services.generation.worker import timeout_watchdog_loop, worker_loop

logger = logging.getLogger(__name__)


def _ensure_request_log_trace(sync_conn: Any) -> None:
    from sqlalchemy import inspect, text

    inspector = inspect(sync_conn)
    if "request_logs" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("request_logs")}
    if "trace" in columns:
        return
    sync_conn.execute(text("ALTER TABLE request_logs ADD COLUMN trace JSON"))


def _ensure_account_identity_columns(sync_conn: Any) -> None:
    """Dev/test convenience only. Production applies ``migrations/*.sql`` explicitly."""
    from sqlalchemy import inspect, text

    inspector = inspect(sync_conn)
    if "upstream_accounts" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("upstream_accounts")}
    additions = {
        "ios_device_token_enc": "TEXT",
        "ios_device_id_enc": "TEXT",
        "credential_status": "VARCHAR(16) NOT NULL DEFAULT 'unverified'",
        "credential_error": "VARCHAR(255)",
        "last_verified_at": "TIMESTAMP",
    }
    for name, ddl in additions.items():
        if name not in columns:
            sync_conn.execute(text(f"ALTER TABLE upstream_accounts ADD COLUMN {name} {ddl}"))


async def _prepare_database(settings: Settings, resources: Resources) -> None:
    """Dev convenience: create tables and seed the bootstrap admin. Prod runs migrations."""
    try:
        async with resources.database.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.run_sync(_ensure_request_log_trace)
            await conn.run_sync(_ensure_account_identity_columns)
        async with resources.sessions() as session:
            await users_service.ensure_bootstrap_admin(
                session,
                username=settings.admin_username,
                password=settings.admin_password,
                pepper=settings.app_secret_key,
            )
            await session.commit()
    except Exception:  # noqa: BLE001 - /health/ready surfaces DB outages
        logger.warning("database prepare skipped: database unavailable", exc_info=True)


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()
    configure_logging(resolved_settings.log_level)
    Path(resolved_settings.media_dir).mkdir(parents=True, exist_ok=True)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        import asyncio

        app.state.settings = resolved_settings
        app.state.resources = create_resources(resolved_settings)
        if resolved_settings.db_auto_create:
            await _prepare_database(resolved_settings, app.state.resources)
        worker = asyncio.create_task(worker_loop(app), name="generation-worker")
        parks = asyncio.create_task(
            account_pool.watchdog_loop(app.state.resources), name="account-park-watchdog"
        )
        timeouts = asyncio.create_task(
            timeout_watchdog_loop(app), name="generation-timeout-watchdog"
        )
        try:
            yield
        finally:
            worker.cancel()
            parks.cancel()
            timeouts.cancel()
            for task in (worker, parks, timeouts):
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            await app.state.resources.close()

    app = FastAPI(
        title="aigc-hub",
        version="0.1.0",
        description=SUPPORT_QQ_LABEL,
        lifespan=lifespan,
    )
    install_error_handlers(app)
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(gen_router)
    app.include_router(keys_router)
    app.include_router(account_router)
    app.include_router(media_router)
    app.include_router(admin_users_router)
    app.include_router(admin_accounts_router)
    app.include_router(admin_ops_router)
    app.include_router(admin_config_router)
    app.include_router(arp_admin_router)
    app.include_router(harvester_admin_router)
    return app


app = create_app()
