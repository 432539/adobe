# 09 · 出图链路开发方案

目标：先用测试 Cookie 打通 `harvester → ARP 池 → curl_cffi 提交 → 轮询 → 下载`，再接入多用户、OpenAI/Gemini 协议和生产级调度。每阶段均可独立验收。

## 0. 测试数据与安全边界

- 测试 Cookie：本机导出文件，每行 `邮箱----Cookie Header` 或纯 Cookie Header（须含 `ims_sid`）。
- 该文件只作为本机测试输入，通过 `TEST_COOKIE_FILE` 或面板导入；**不复制进项目、不打进镜像、不写日志、不提交 Git**。
- 导入器逐行解析，每行作为一个账号；入库只加密 Cookie，**不把 CK 换成 AT 存库**；出图时现换 AT。
- 进入数据库前用 `FIELD_ENCRYPTION_KEY` 加密；测试结束可一键删除测试账号。

## 1. 里程碑 A：最小闭环（单进程调试）

### A1. ARP 采集器
- 从现有 `adobe-arp-harvester` 迁移核心逻辑，但改为本项目接口。
- [fingerprint-chromium](https://github.com/adryfish/fingerprint-chromium) 148，随机 seed，住宅 sticky 代理。Playwright 只驱动该二进制。
- `SherlockSdk.initAsync()` 取得 `sid/ark/bfp/ftr`，抓 UA/高熵 CH，校验后发布完整 bundle。
- 采集器仅调用 HTTP admin-api，不连接 PostgreSQL/Redis。

### A2. ARP 池
- Redis Hash 存 bundle，ZSET 按 `expires_at` 管 ready 队列。
- 原子 Lua 实现 `publish / checkout / increment_use / invalidate / cleanup`。
- `/admin-api/adobe/arp/health` 返回 ready、即将过期数、铸票速率、按 egress 分布。

### A3. Cookie → clio token
- 读取测试 Cookie，调用 IMS `/ims/check/v6/token`。
- 校验 JWT `client_id=clio-playground-web`、`user_id/aa_id`、`creative_production`、非 `@GuestID`。
- 缓存 token 至 `exp-60s`；401 只刷新账号 token，不丢 ARP。

### A4. curl_cffi 提交
- 身份目标统一 Chrome 148；默认 TLS profile 用 curl_cffi 当前可用的 `chrome146`，UA/CH 严格覆盖为 bundle 的 148 身份。
- 若能导出准确的 Chrome 148 JA3/Akamai，再启用自定义 TLS；未验证前不伪造标签。
- 提交绑定 `bundle.proxy_url`，按模型构造 payload，处理 200/401/403/408/429/451/5xx。
- 200 后轮询，产物 CDN 直连流式下载；408 立即 invalidate 当前 ARP 并换票，最多 2–3 次。

### A5. 验收
1. health 显示至少 1 枚新鲜、四项齐全、带 egress + UA/CH 的 ARP。
2. Cookie 换出合格 clio token，日志无敏感信息。
3. HARD 账号出图 200；结果文件可打开，记录提交/轮询/下载耗时。
4. 故意换出口或 UA 能稳定复现 408/403，证明绑定校验有效。
5. 451 / 429 不罚号、退避重试，失败退费；408 换票重试；401 用 Cookie 现换 AT。

## 2. 里程碑 B：任务化与协议适配

- 建立内部统一命令 `GenerationCommand`：模型、prompt、输入媒体、输出规格、同步策略、调用者。
- OpenAI adapter：`images/generations`、`images/edits`、videos、tasks。
- Gemini adapter：`generateContent`、`predict`、`predictLongRunning`、operations。
- 两个 adapter 只做请求/响应映射；共同调用 `GenerationService`，禁止复制业务逻辑。
- 同步接口也先持久化任务并入队；API 进程通过 Redis 事件等待。超时返回 504 + task_id，任务继续。
- 图片编辑：multipart/inlineData → 安全校验 → 上传 Adobe blob → 按模型映射 reference usage。

## 3. 里程碑 C：多用户与高并发

- PostgreSQL：用户、KEY、任务、余额流水、账号池、请求日志、配置。
- Redis：队列、ARP 池、账号租约、限流、热点缓存、同步等待事件。
- worker 按 `image / video / upload-download` 分队列，避免长视频饿死短图片。
- 账号单提交并发 1；轮询与下载可高并发。ARP 与账号解耦，按 TTL/uses 管理。
- 计费：预授权/冻结 → 成功结算；失败释放。幂等键防重复提交与扣费。

## 4. 里程碑 D：企业后台 UI

- 先完成设计 token、ProLayout 壳、登录、角色菜单，再填业务页。
- 创作中心用三栏/两栏响应式工作台：模型和参数、画布/上传、结果与任务状态。
- 管理首页突出系统健康：ARP 水位、账号可用数、队列、成功率、P95，而不只是运营数字。
- 提供骨架屏、空状态、错误恢复、任务进度、暗色主题；桌面优先并兼容平板。
- 调用说明页面提供 OpenAI/Gemini × 同步/异步 × 生成/编辑的可复制示例。

## 5. 测试策略

- 单元：ARP bundle 校验、payload builder、错误映射、计费状态机、协议 adapter。
- 集成：真实 Redis/PostgreSQL；Mock Adobe 覆盖 200/401/403/408/429/451/5xx。
- 受控真实测试：只用本机 Cookie 文件和住宅出口，测试结果单独标记，CI 不运行。
- 压测：异步入口、同步长连接、任务查询、日志写入分别压；记录 P50/P95/P99 和资源占用。
- E2E：登录 → 创作 → 进度 → 下载 → 余额流水；管理员查看日志/池健康。

## 6. Definition of Done

- 容器一条命令启动 API、worker、PostgreSQL、Redis、MinIO、前端；harvester 可宿主机或独立容器。
- OpenAI/Gemini 同步、异步和图片编辑都有契约测试。
- 任何日志/响应/镜像层中都没有 Cookie、token、代理密码。
- ARP 空池、数据库/Redis 重启、worker 重启均有明确降级，不丢任务、不重复扣费。
- 核心链路有指标、追踪 ID、健康检查和可操作告警。
