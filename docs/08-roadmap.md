# 08 · 里程碑 / 开发阶段

按"先打通链路、再做面板、后做优化"推进。每阶段有可验收产物。

## 阶段 0 · 骨架（本阶段产物：规则 + 文档 + 目录）
- [x] 设计文档 `docs/`、`.env.example`、目录骨架。
- [x] FastAPI 配置/日志/错误/健康检查、pytest/ruff/mypy 基线。
- [x] PostgreSQL + Redis + MinIO + API 开发 Compose。
- [x] 测试 Cookie 安全加载与脱敏验证（4 条，均含 `ims_sid`）。

## 阶段 1 · 出图链路打通（最高优先）
- [x] `harvester`：fingerprint-chromium 148 + 住宅 sticky 铸 `sid/ark/bfp/ftr`，抓 UA/CH，POST 入池。
- [x] `arp` 池（Redis）：四项 + `ftr` 含 `v2_tt` + Chrome 148 校验，原子 publish / checkout / invalidate / health，内网鉴权。
- [x] 安全读取本机测试 Cookie（4 行）→ clio token；全链路日志脱敏。
- [x] `gpt-image-2` 首次真实闭环：curl_cffi + Chrome 148 UA/CH、同出口提交/轮询、CDN 直连下载。
- [ ] Cookie/token 入库加密与账号池 token 缓存。
- [ ] 通用 `adobe` 客户端：重试/账号调度/MinIO 内容寻址缓存。
- [x] 五家图片 `generate-async` 请求体（nano / gpt-image-2 / gpt-image-2.5 flare+prism）。目录真源 [13-models](./13-models.md)。
- [ ] 图生图：把 `reference_blob_ids` 写入 `referenceBlobs`（须本环境 HAR）。
- [ ] 六家视频 `generate-async` 请求体（gemini-omni / seedance / veo）。未核实前不编字段。
- [ ] 验收：付费 HARD 号 → 200 出图；换 SID → 408；内容拒绝 451 不罚号。

## 阶段 2 · 后端平台
- [ ] 数据模型 + Alembic 迁移（users/keys/jobs/records/ledger/accounts/logs/config）。
- [ ] 面板鉴权(JWT) + 用户/管理员 API；生成入队(Celery) + 幂等 + 计费(原子扣减+ledger)。
- [ ] OpenAI + Gemini 官方格式；同步/异步、Operation/Task、图片编辑接口；KEY 鉴权 + 限流。
- [ ] 容器化：API/三类 worker/PostgreSQL/Redis/MinIO/前端；harvester 支持宿主机优先或独立容器。

## 阶段 3 · 前端 SaaS 后台
- [ ] ProLayout 左右布局 + 蓝色主题；角色分区路由与菜单。
- [ ] 用户：创作中心(WS 进度)/生成历史/KEY/调用说明/余额明细/个人设置。
- [ ] 管理员：数据统计(图表+池水位)/用户管理/充值·消费记录/系统配置/请求日志。

## 阶段 4 · 高并发与优化
- [ ] 账号池租约调度 + park/换号骑好窗口 + egress 评分。
- [ ] 分层限流、缓存、连接池调优、日志分区。
- [ ] 可观测（指标 + 告警）+ 自愈（采集器/worker/账号 token）。
- [ ] 横向扩展（面板/worker/采集器多实例，DB 读写分离/分区）。

## 阶段 5 · 加固
- [ ] 敏感数据加密(KMS/Fernet)、密钥轮换、越权(IDOR)审计。
- [ ] 压测、混沌演练（池空/账号大面积 dead 的降级）。
