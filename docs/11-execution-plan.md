# 11 · 最优开发进度与执行方案

## 总策略

采用“**风险优先的垂直切片**”，而不是前端、后端、采集器同时全面铺开：

1. 先用一个 HARD 测试账号和一个图片模型证明真实链路稳定。
2. 再把链路任务化，接 OpenAI/Gemini 两个协议适配层。
3. 然后建设多用户、计费、管理后台和完整 UI。
4. 最后扩充视频/全部模型并做压测、容器生产化与安全加固。

任何阶段未通过验收闸门，不进入依赖它的下一阶段。

## 优先级

- **P0 关键路径**：配置与 Secret → Redis ARP 池 → harvester → Cookie 换 token → 单模型提交/轮询/下载。
- **P1 平台核心**：持久任务、同步/异步、OpenAI/Gemini、图片编辑、账号调度、幂等与计费。
- **P2 产品体验**：登录、创作中心、历史、Key、管理后台、统计和美观度。
- **P3 扩展与加固**：视频/更多模型、压测、监控、容器生产化、故障演练。

## Sprint 0 · 工程基础（第一批开发）

目标：让所有后续模块有统一、可测试、可容器运行的骨架。

### 实现
- 后端 FastAPI 工程：配置、日志脱敏、统一错误、健康检查、测试框架。
- PostgreSQL/Redis/MinIO 的开发 Compose；迁移容器与本地 `.env`。
- Redis ARP 数据结构与协议 DTO，但先使用 fake bundle 测试，不连接真实上游。
- Cookie 文件安全读取器：逐行加载、格式校验、hash 标识、绝不打印内容。
- 建立 CI 基线：ruff、mypy、pytest、前端 lint/typecheck。

### 闸门 G0
- `docker compose up` 后 API、PostgreSQL、Redis、MinIO 全部 ready。
- 测试 Cookie 文件能识别 4 个条目，日志只显示 hash/行号。
- 单元测试通过，仓库与镜像层扫描不到 Cookie/token。

## Sprint 1 · ARP 工厂与池

目标：稳定产出并消费不可拆的 ARP bundle。

### 实现
- Redis Lua：`publish / checkout / increment_use / invalidate / cleanup`。
- admin-api：发布、健康、作废；内网 token + IP 限制。
- 移植 harvester：Chrome 148、随机 seed、住宅 sticky、SherlockSdk、UA/CH。
- egress 一致性探针与池指标：ready、age、uses、egress 分布。

### 闸门 G1
- 连续运行至少多个铸票周期，无内存/浏览器进程泄漏。
- 每枚票能解出 `sid/ark/bfp/ftr`，且含 proxy/egress/UA/CH/TTL。
- 过期自动清理；并发 checkout/invalidate 无重复或脏状态。

## Sprint 2 · 首个真实出图闭环

目标：只支持一个模型（建议 `gpt-image-2`）和 URL 输出，先证明链路。

### 实现
- Cookie → clio token，校验 HARD/账号 ID/scope，安全缓存。
- curl_cffi：最新可用 TLS profile + bundle 的 Chrome 148 UA/CH。
- 提交、轮询、CDN 直连流式下载、MinIO 转存。
- 错误分类：401/403/408/429/451/5xx；408 换票/换号，429/451 不罚号并重试。
- 结构化请求日志与 trace_id，全程脱敏。

### 闸门 G2（最关键）
- 正常路径得到可打开的图片和稳定元数据。
- 故意换出口/身份能复现 408/403；恢复绑定后成功。
- 重试不会重复扣费或产生不可追踪的孤儿任务。
- 连续真实测试记录成功率、P50/P95、408 分布；不以单次成功作为完成。

> G2 未通过前，不开发完整 UI、计费后台和全部模型。

## Sprint 3 · 统一任务核心与协议

目标：一次业务实现，同时服务面板、OpenAI 和 Gemini。

### 实现
- `GenerationCommand`、任务状态机、幂等键、三队列（image/video/media）。
- 同步：任务入队后通过 Redis 事件等待；超时 504 + task_id。
- 异步：task/operation 查询、SSE、Webhook（签名与退避）。
- OpenAI：`images/generations`、`images/edits`、videos/tasks。
- Gemini：`generateContent`、`predict`、`predictLongRunning`、operations。
- 图片编辑：多图、mask、blob 上传、reference usage 映射。
- 两套协议契约测试；adapter 不包含上游业务逻辑。

### 闸门 G3
- 同一内部任务可分别通过 OpenAI/Gemini 发起并得到各自官方形状响应。
- 同步断开不取消任务；异步重复查询一致；同一幂等键不重复执行。
- 生成与编辑接口均有 mock + 至少一条受控真实测试。

## Sprint 4 · 多用户、账号池与计费

目标：从技术链路变成可运营平台。

### 实现
- 用户/JWT/API Key、角色与数据隔离。
- 上游账号加密存储、租约、健康评分、park/刷新/dead 状态。
- 余额账本：冻结 → 成功结算 / 失败释放；充值、消费、退款、管理员调整。
- Redis 限流、队列背压、配置缓存。
- 管理 API：用户、账号、记录、配置、请求日志、统计。

### 闸门 G4
- 并发生成下余额与账本严格一致；故障重放不重复扣费。
- 普通用户无法读取其他用户任务、文件、流水或管理员资源。
- 账号/ARP 空池有明确排队或 503，不发生无限重试。

## Sprint 5 · 企业级前端

目标：先完成完整工作流，再进行视觉精修。

### 实现顺序
1. Design tokens、ProLayout、登录、角色路由、错误边界。
2. 创作中心：生成/编辑/视频模式、上传、mask、任务进度、结果。
3. 历史、Key、调用说明（OpenAI/Gemini 示例）、余额、设置。
4. 管理仪表盘、用户、充值/消费、系统配置、日志、账号/ARP 健康。
5. 暗色主题、响应式、骨架屏、空状态、微交互与可访问性。

### 闸门 G5
- 用户从登录到生成、下载、查看扣费的完整 E2E 通过。
- 管理员能定位一次 408 的账号/egress/ARP/重试链路，但看不到敏感值。
- Lighthouse 生产构建性能/可访问性目标 ≥ 90；核心页面无明显布局跳动。

## Sprint 6 · 视频、模型扩充与生产化

目标：在稳定任务核心上逐个增加模型，不一次性并行接入。

### 顺序
1. 图片编辑与 Image 5。
2. AD 视频。
3. Veo/Luma/Sora。
4. Seedance（clio/scope/媒体引用路径单独验收）。
5. 每个模型建立能力矩阵、价格、payload fixture 和契约测试。

### 生产化
- Compose 生产覆盖、Secret、只读文件系统、资源限制、滚动升级。
- Prometheus/Grafana 或等价指标；日志、告警、trace。
- 入口/同步长连接/队列/真实上游/下载带宽分层压测。
- Redis/PostgreSQL/worker 重启、ARP 空池、账号池失效的故障演练。

### 闸门 G6
- 每个模型独立通过正常、内容拒绝、限速、超时、下载失败测试。
- 容器滚动升级不丢任务；数据库迁移可回滚或向前兼容。
- 容量基线、告警阈值和运维手册完整。

## 首次开发提交拆分

为了便于审查，第一阶段不做一个超大提交：

1. `chore/backend-skeleton`：FastAPI、配置、日志、健康、pytest。
2. `chore/dev-compose`：PostgreSQL、Redis、MinIO、migrate、healthcheck。
3. `feat/cookie-loader`：安全读取与脱敏测试。
4. `feat/arp-domain`：bundle schema、校验、Redis store/Lua、admin-api。
5. `feat/harvester`：Chrome 148 真铸票与 health。
6. `feat/ad-image-spike`：token、submit、poll、download，仅 gpt-image-2。

## 当前下一步

立即执行 **Sprint 0**。完成后先展示：
- 可启动的 Compose。
- FastAPI `/health/live` 与 `/health/ready`。
- Cookie loader 的脱敏测试结果。
- ARP bundle schema 与 Redis 原子操作测试。

确认 G0 后再接真实浏览器和上游，避免把外部不稳定因素混入基础工程问题。
