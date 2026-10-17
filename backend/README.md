# backend

**开源地址：https://github.com/432539/adobe**  
**技术支持 QQ 群：1109037692**

FastAPI 后端。当前 Sprint 0 已提供：

- `app.main:create_app` 应用工厂。
- `/health/live` 与检查 PostgreSQL/Redis 的 `/health/ready`。
- 环境变量配置、统一领域错误、日志敏感信息脱敏。
- 安全 Cookie 文件加载器 `app.accounts.cookie_loader`。
- pytest、ruff、mypy 严格检查基线。

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]"
.\.venv\Scripts\python -m pytest
.\.venv\Scripts\python -m ruff check app tests
.\.venv\Scripts\python -m mypy app
```

目录规划见 [`../docs/01-architecture.md`](../docs/01-architecture.md)。默认出图是 AD 移动端，仅 2.5 走网页 ARP。
