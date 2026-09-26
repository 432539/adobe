from dataclasses import dataclass
from typing import Any

from redis.asyncio import Redis
from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import Settings
from app.core.crypto import FieldCipher


@dataclass(slots=True)
class Resources:
    database: AsyncEngine
    sessions: async_sessionmaker[AsyncSession]
    # Same pool; request handlers that may write use this so SQLite takes the write lock
    # up front. On PostgreSQL it is identical to ``sessions``.
    request_sessions: async_sessionmaker[AsyncSession]
    redis: Redis
    cipher: FieldCipher

    async def close(self) -> None:
        await self.redis.aclose()
        await self.database.dispose()


SQLITE_WRITE_OPTION = "sqlite_write"


def _tune_sqlite(engine: AsyncEngine) -> None:
    """Dev/test only. SQLite has a single writer. Sessions flagged ``sqlite_write`` (the
    request-scoped one) start with ``BEGIN IMMEDIATE`` so concurrent submits queue on the
    busy timeout instead of deadlocking SHARED→RESERVED. Everything else (config reads,
    background lookups) stays DEFERRED and, thanks to WAL, never waits on a writer."""

    @event.listens_for(engine.sync_engine, "connect")
    def _on_connect(dbapi_conn: Any, _record: Any) -> None:
        dbapi_conn.isolation_level = None  # we emit BEGIN ourselves below
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()

    @event.listens_for(engine.sync_engine, "begin")
    def _on_begin(conn: Any) -> None:
        if conn.get_execution_options().get(SQLITE_WRITE_OPTION):
            conn.exec_driver_sql("BEGIN IMMEDIATE")
        else:
            conn.exec_driver_sql("BEGIN")


def create_resources(settings: Settings) -> Resources:
    if settings.database_url.startswith("sqlite"):
        database = create_async_engine(
            settings.database_url,
            pool_pre_ping=True,
            connect_args={"timeout": 30},
            pool_size=20,
            max_overflow=40,
        )
        _tune_sqlite(database)
    else:
        database = create_async_engine(
            settings.database_url,
            pool_pre_ping=True,
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
        )
    sessions = async_sessionmaker(database, expire_on_commit=False)
    write_engine = database.execution_options(**{SQLITE_WRITE_OPTION: True})
    request_sessions = async_sessionmaker(write_engine, expire_on_commit=False)
    redis = Redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_connect_timeout=1,
        socket_timeout=2,
    )
    return Resources(
        database=database,
        sessions=sessions,
        request_sessions=request_sessions,
        redis=redis,
        cipher=FieldCipher.from_settings(settings),
    )
