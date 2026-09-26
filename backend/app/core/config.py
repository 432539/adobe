from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: str = "dev"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_secret_key: str = Field(default="dev-only-change-me", min_length=16)
    field_encryption_key: str = ""

    database_url: str = "postgresql+asyncpg://firefly:firefly@127.0.0.1:5432/firefly_gen"
    db_pool_size: int = Field(default=20, ge=1)
    db_max_overflow: int = Field(default=10, ge=0)
    redis_url: str = "redis://127.0.0.1:6379/0"
    arp_internal_token: str = "change-me-internal-token"
    arp_ttl_seconds: int = Field(default=120, ge=30, le=240)
    arp_max_uses: int = Field(default=10, ge=1, le=10)
    arp_key_prefix: str = "firefly:arp"
    submit_impersonate: str = "chrome146"
    poll_timeout_seconds: int = Field(default=120, ge=30, le=600)

    test_cookie_file: str | None = None
    gen_worker_enabled: bool = True
    media_dir: str = "outputs"
    log_level: str = "INFO"
    health_timeout_seconds: float = Field(default=2.0, gt=0, le=10)

    # ---- 面板鉴权 ----
    jwt_algorithm: str = "HS256"
    jwt_ttl_hours: int = Field(default=24, ge=1, le=24 * 30)
    # 引导管理员：用户表落地前的唯一管理员；生产必须改掉默认密码
    admin_username: str = "admin"
    admin_password: str = Field(default="change-me-admin-password", min_length=8)

    # ---- 系统配置服务 ----
    # 开发期自动建表；生产走迁移脚本
    db_auto_create: bool = True
    config_cache_seconds: float = Field(default=5.0, ge=0, le=60)
    config_channel: str = "firefly:config:changed"
    # 代理探测目标：返回 {ip, country} 的 JSON 端点
    proxy_probe_url: str = "https://ipinfo.io/json"
    proxy_probe_timeout_seconds: float = Field(default=12.0, gt=0, le=60)
    r2_usage_cache_seconds: int = Field(default=600, ge=0)


@lru_cache
def get_settings() -> Settings:
    return Settings()
