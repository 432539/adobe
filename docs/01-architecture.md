# 01 · 系统架构

## 设计原则
- **三进程解耦**：Web 面板 / 生成 worker / ARP 采集器彼此独立，可分机部署、独立伸缩。
- **稀缺资源池化**：上游账号、ARP 都是稀缺且短命资源，全部池化 + 租约 + 水位管理。
- **提交与浏览器解耦**：出图靠纯 HTTP（curl_cffi），浏览器只用于铸票，不为每个任务开浏览器。
- **计费强一致**：生成成功才扣费，扣费与流水同事务。

## 组件图

```
                         ┌───────────────────────────────────────────────┐
        浏览器/SPA  ────► │  Web 面板 (FastAPI)                             │
        API KEY 调用 ───► │  api/(用户+管理员)  admin-api/(内网)            │
                         │  ├─ auth / 计费 / 配置 / 日志                    │
                         │  ├─ 生成入口：入队 job                          │
                         │  └─ ARP 池 (Redis)  ◄── admin-api/adobe/arp     │
                         └───────┬───────────────────────────▲────────────┘
                                 │ enqueue                    │ push ARP
                        ┌────────▼─────────┐         ┌────────┴───────────┐
                        │ 生成 Worker (Celery)│         │ 采集器 harvester    │
                        │  curl_cffi 提交    │         │ fp-chromium 148    │
                        │  ├ checkout 账号   │         │ 住宅 sticky 出口    │
                        │  ├ checkout ARP    │         │ SherlockSdk 铸票   │
                        │  ├ 提交/轮询/下载  │         └────────────────────┘
                        │  └ 扣费/落库/回调  │
                        └────────┬───────────┘
                    PostgreSQL ◄─┘   Redis(队列/锁/缓存/ARP池)   对象存储(结果)
```

## 数据流（一次出图）
1. 用户在创作中心提交 prompt / 模型 / 尺寸 → 后端校验余额、幂等键 → 写 `generation_job(queued)` → 入队。
2. Worker 取 job → `checkout` 一个空闲 HARD 账号（Redis 租约）。
3. **按模型选身份**（`identity_lane`）：
   - **默认 FF-iOS**（香蕉 / Image 2 / 视频）：现换移动端 AT，住宅代理提交，**不** checkout ARP。
   - **仅 2.5**：Cookie 现换网页 clio AT + checkout ARP bundle，提交出口和 UA/CH 必须与铸票一致。
4. curl_cffi 打 `generate-async`，轮询后直连 CDN 下载。
5. 结果分支：
   - `200` → 取 `presignedUrl` → **直连 CDN** 下载 → 存对象存储。
   - 网页 2.5 的 `408` → invalidate 该 ARP，换票/换号重试。
   - `401` → 现换 AT 重试；连续鉴权失败标 `dead`；`429`/`451` → 不罚号、退避重试。
6. 成功：扣费（同事务写 `consume_record` + 余额）、更新 `generation_job(succeeded)`、落 `request_log`（脱敏）、回调/推送前端。

## 部署拓扑（建议）
- **面板 + DB + Redis**：主服务器（公网入口 + 内网 admin-api）。
- **生成 worker**：可多实例横向扩，出口走住宅代理（提交），本机 IP 走轮询/下载。
- **采集器**：部署在住宅出口机器（或绑定住宅 sticky 代理），与业务库零耦合。
- admin-api 仅内网可达；面板对外走 HTTPS + 反代。

## 目录结构（后端）
```
backend/app/
├── main.py            # FastAPI app 装配
├── core/              # config, db(async engine/session), redis, security, logging
├── models/            # SQLAlchemy ORM
├── schemas/           # Pydantic DTO
├── api/               # 面板路由：auth, user/*, admin/*
├── admin_api/         # 内网口：adobe/arp（采集器）
├── services/          # 业务：billing, users, keys, config, stats, logs, generation
├── arp/               # ARP 池：store(redis), checkout/invalidate, health
├── adobe/             # 提交链路：client(curl_cffi), payloads, auth(cookie→token), arp_session
└── workers/           # Celery tasks：generate_image, generate_video
```
