# 07 · 本地开发与部署

运营参数（代理、TTL、铸票间隔、计费）在**系统配置面板**，不在 `.env`。见 [12-minting-and-config](./12-minting-and-config.md)。

**开源地址：https://github.com/432539/adobe**  
**技术支持 QQ 群：1109037692**

## 依赖
- Python 3.11+、Node 18+（pnpm）、PostgreSQL 15+、Redis 7+。
- 采集器另需 [fingerprint-chromium](https://github.com/adryfish/fingerprint-chromium) 148（`vendor/fingerprint-chromium/chrome.exe`）与住宅 sticky 代理。

## 环境变量
```bash
cp .env.example .env
# 必填：APP_SECRET_KEY, FIELD_ENCRYPTION_KEY, DATABASE_URL, REDIS_URL, ARP_INTERNAL_TOKEN
```

本机真实链路测试可设置：
```text
TEST_COOKIE_FILE=/path/to/cookies.txt
```
该文件仅运行时读取，不复制进仓库/镜像，不输出内容；测试账号入库前必须加密。

## 后端
```bash
docker compose up -d --build  # API: http://127.0.0.1:18000

# 或不使用容器直接运行
cd backend
python -m venv .venv && . .venv/Scripts/activate   # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8000
# worker（另开终端）
celery -A app.workers.celery_app worker -l info -c 32
```
当前依赖声明在 `backend/pyproject.toml`；Alembic/Celery/curl_cffi 将在对应 Sprint 接入后加入。

## 前端 / 采集器

```bash
cd frontend
pnpm install
pnpm dev    # http://localhost:5173/ ，代理到 API :18000
```

采集器实现按去过敏策略不在公开仓库。问题进 QQ 群 **1109037692**。

## 冒烟校验（对齐 [02 §10](./02-arp-core.md)）
1. 铸出可解码 `sid+ark+bfp+ftr`。
2. checkout 后提交代理与铸票一致（抓出口 IP）。
3. 付费 HARD 号打一次 → 200 出图；故意换 SID → 408。
4. 内容拒绝(451) 如实返回、不罚号。

## 部署（生产）
- 面板 + DB + Redis 在主机（HTTPS 反代，`admin-api` 仅内网 + IP 白名单）。
- worker 多实例，出口绑住宅代理；采集器部署在住宅出口机器，按出口分布多实例合并入同一池。
- 进程守护用 systemd / pm2 / supervisor；日志集中收集并脱敏。
- 容器化拓扑、harvester 容器限制、Secret/网络/回滚见 [`10-container-deployment.md`](./10-container-deployment.md)。
