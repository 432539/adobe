# firefly-gen · 生图 / 生视频 多用户中转平台

企业级 SaaS 后台风格（左右布局、蓝色科技感）的 AIGC 中转平台。用户在统一面板登录、在创作中心提交文生图 / 图生图 / 文生视频 / 图生视频，平台调度上游 Adobe Firefly，并做多用户计费、Key 管理与高并发调度。对外提供 OpenAI 与 Gemini 官方格式的同步/异步接口。

## 部分开源 · 完整源码须授权领取

本仓库**不完全开源**。`git clone` / 公开历史里只有后端面板与文档骨架；**`frontend/`、`harvester/` 整目录，以及 FF-iOS / ARP 出图核心**均不公开，**无法从本仓库拉取全部源码**。

**完整实现须经授权：加入技术支持 QQ 群 19302577，由群主发放。未经授权不得索取、转载或二次分发。**

清单见 [`PRIVATE.md`](./PRIVATE.md)。

## 技术支持

**QQ 群：19302577**（必加。完整源码、接入、部署、出图问题都在群里）

> 面向开发者的完整设计见 [`docs/`](./docs)。

## 界面预览

| 登录 | 创作中心 | 管理后台 |
|---|---|---|
| ![登录](docs/screenshots/login.png) | ![创作中心](docs/screenshots/create.png) | ![系统总览](docs/screenshots/dashboard.png) |

## 技术栈

| 层 | 选型 |
|---|---|
| 后端 | Python 3.11 · FastAPI · SQLAlchemy 2.0 (async) · PostgreSQL · Redis · Celery |
| 出图链路 | **默认 FF-iOS**（curl_cffi + 住宅代理，无 ARP）；仅 GPT Image 2.5 走网页 clio + ARP |
| 采集器 | [fingerprint-chromium](https://github.com/adryfish/fingerprint-chromium) 148 + Playwright（只服务 2.5 网页票） |
| 前端 | React 18 · TypeScript · Ant Design (Pro Layout) · Vite |

## 出图身份（按模型分流，账号不分池）

同一 HARD 号能跑全部正式模型。**默认走 FF-iOS 移动端**，只有 GPT Image 2.5 才用网页 ARP。

| 模型 | 身份 | 要不要 ARP |
|---|---|---|
| `nano-banana` / `nano-banana-pro` / `gpt-image-2` | **FF-iOS** | 否 |
| `gemini-omni-flash` / `seedance-2.0` / `seedance-2.0-fast` | **FF-iOS** | 否 |
| `gpt-image-2.5-flare` / `gpt-image-2.5-sunburst` | 网页 clio | 要（整套 bundle） |

### 默认：FF-iOS 出图

Nano Banana、GPT Image 2、视频都走这条。不铸网页票、不带 `x-arp-session-id`、不用 Chrome UA/CH。

```
HARD 账号 Cookie
   └─ 静默授权得到加密 device_token / device_id（入库）
       └─ 每次任务现换 FF-iOS access_token（不入库）
           └─ curl_cffi + 住宅 sticky 代理
               ├─ x-api-key / x-ims-clientid = FF-iOS
               ├─ UA = Firefly iOS
               ├─ POST generate-async → 轮询 → 直连 CDN
               └─ 429 / 451 不罚号，继续重试
```

### 例外：2.5 网页 ARP

2.5 没有 FF-iOS 接口。必须网页 clio（`creative_production`）+ 铸票出口自洽，否则 408/403。详见 [`docs/02-arp-core.md`](./docs/02-arp-core.md)、[`docs/13-models.md`](./docs/13-models.md)。

```
[采集器 fingerprint-chromium 148 · 住宅出口]
   └─ 铸 {sid,ark,bfp,ftr} + UA/CH → ARP 池
[生成 worker]
   └─ Cookie 现换 clio AT + checkout ARP
       ├─ 提交出口 == 铸票 sticky，UA/CH == 铸票浏览器
       ├─ x-api-key = clio-playground-web，带 x-arp-session-id
       └─ 408 → 作废该票，换票/换号重试
```

## 目录结构

```
firefly-gen/
├── docs/              # 设计文档骨架（部分实现文档进群领取）
├── backend/           # FastAPI 后端骨架（出图核心进群领取）
├── frontend/          # 非开源，仅占位 README，进群领取
└── harvester/         # 非开源，仅占位 README，进群领取
```

## 快速开始（开发）

参见 [`docs/07-dev-setup.md`](./docs/07-dev-setup.md)。最小路径：

```bash
docker compose up -d --build   # API :18000 + PostgreSQL + Redis + MinIO

# 或直接运行后端
cp .env.example .env      # 填 DATABASE_URL / REDIS_URL / ARP_INTERNAL_TOKEN
# 后端
cd backend && pip install -e ".[dev]" && uvicorn app.main:app --reload
# 前端与采集器不在本仓库，加入 QQ 群 19302577 经授权领取后再跑
```

## 合规声明

本项目为技术研究与内部工程实现。上游账号、代理凭据、Cookie 等敏感数据一律加密存储、绝不入库明文、绝不提交仓库。
