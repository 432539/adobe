# 04 · API 规范

技术支持 QQ 群：**19302577**。

三类接口：**面板 API**（`/api`，JWT）、**对外生成 API**（`/v1`,`/v1beta`，KEY）、**内网 admin-api**（采集器，内网 token）。成功直接返回业务体；错误统一 `{code:"<snake_case>", message, detail?}` + 对应 HTTP 状态码。

## 通用
- 鉴权：面板 `Authorization: Bearer <JWT>`；对外 `Authorization: Bearer sk-...` 或 `x-goog-api-key: sk-...`；内网 `X-Internal-Token`。
- 分页：`?page=1&page_size=10`，返回 `{items, total, page, page_size}`。
- 时间 ISO8601 UTC；金额/积分为最小单位整数（分）。
- 面板 JWT 每次请求都回查 `users` 表：被禁用的用户即便 token 未过期也立即 403。

## 0. 计费门禁（所有生成入口共用）
所有生成请求（面板 / OpenAI / Gemini）都进 `services/generation/gate.submit_job()`，顺序固定：

| 步骤 | 失败响应 | 说明 |
|---|---|---|
| 报价 | 422 `pricing_missing` / `pricing_invalid` | 价格只来自系统配置计费表；无定价或 0 元直接拒绝 |
| 身份 | 403 `user_disabled` | 用户必须 active |
| 幂等 | 200 + 原任务 | `(user_id, idempotency_key)` 命中返回已有任务，不再预扣 |
| 并发 | 429 `concurrency_limit` | queued+running ≥ 用户并发上限（用户单独设置或系统默认） |
| 预扣 | 402 `insufficient_balance` `{need,have}` | 条件 UPDATE `balance>=cost`，失败则**没有任何写入** |
| 建任务 | 202 `JobOut` | 任务 + ledger(consume) + consume_record(pending) 同事务 |

生命周期：`succeeded` → `consume_record.settled`（余额不动）；`failed`/`rejected` → ledger `refund` +cost（同一任务最多退一次，由唯一约束保证）。

## 1. 认证（面板）— 已实现 `api/auth.py`
| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/auth/login` | `{username,password}` → `{token, role, profile}`；users 表校验（scrypt）。首次启动 users 为空时用 `ADMIN_USERNAME/ADMIN_PASSWORD` 落一条管理员 |
| GET | `/api/auth/me` | 当前用户 + 实时余额 |
| POST | `/api/auth/logout` | 规划：token 黑名单 |

## 2. 用户功能（面板；管理员亦可用）
### 创作中心 — 已实现 `api/gen.py`
| POST | `/api/gen/image` | JSON `{model,prompt,...}` 或 multipart（字段同上 + `images` 文件）。参考图：URL / data URI / 文件。worker 上传后再写入上游 `referenceBlobs` |
| POST | `/api/gen/video` | `{model,prompt,aspect_ratio,resolution,duration,reference_blob_ids?,idempotency_key}` → 202 `JobOut` |
| GET | `/api/gen/models` | 计费表 ∪ 目录：`{id,name,kind,price,billing,tiers,note,aspect_ratios,resolutions,durations,supports_edit,modes,max_reference_images,submit_ready}`。正式 8 个模型见 [13-models](./13-models.md) |
| GET | `/api/jobs` | 本人任务分页（`status`=`succeeded`/`generating`/`failed` 或原始状态，`prompt`/`model`/`kind` 筛选）；查询恒带 `user_id`。`JobOut` 含 `error_code`/`error_message`（用户提示词，不含上游改写词） |
| GET | `/api/jobs/{id}` | 本人任务；他人任务 404 |
| DELETE | `/api/jobs?scope=` | 本人清理：`failed` / `older_3d` / `all` |
| POST | `/api/gen/upload` | 规划：参考图上传 → `{blob_id}` |
### KEY 管理 — 已实现 `api/keys.py`
| GET | `/api/keys` | 列表（只有 `key_prefix`，永不回明文） |
| POST | `/api/keys` | `{name, rate_limit?}` → `ApiKeyOut` 含 `plain`（仅此一次）；每人最多 20 把有效 KEY |
| DELETE | `/api/keys/{id}` | 吊销，立即对 `/v1` 生效 |
### 平台公告 — 已实现 `api/account.py`
| GET | `/api/announcement` | 系统配置 `announcement`（≤160）。登录用户可读；不含其它配置。顶栏铃铛展示。 |
### 余额明细 — 已实现 `api/account.py`
| GET | `/api/ledger` | 本人 balance_ledger 分页 |
| GET | `/api/records/consume` | 本人消费记录（含 `status: pending/settled/refunded`） |
| GET | `/api/records/recharge` | 本人充值/调账记录 |
### 个人设置
| GET/PATCH | `/api/profile` | 昵称/密码/通知偏好 |

## 3. 管理员后台（`role=admin`，`require_admin`）
### 数据统计
| GET | `/api/admin/stats/overview` | 用户数、`jobs_today`/`jobs_total`、成功率、`revenue_today`/`revenue_total`、池水位、`credits_available`/`credits_total`、`accounts_total`/`accounts_active` |
| GET | `/api/admin/arp` | 铸票页：当前 Redis 票据（无 token/proxy）、入池事件、水位配置。`harvester_online` 看采集器 bootstrap/lease/health 心跳，不是池里有没有票。**不含代理 URL / ARP token。** |
| GET | `/api/admin/stats/timeseries` | 近 24 小时按小时生成量、成功率；`ts` 为 UTC ISO，面板用本地 `HH:mm` 展示 |
| GET | `/api/admin/stats/egress` | 按 `egress_id` 汇总成功/失败，按最近请求时间倒序 |
### 用户管理 — 已实现 `api/admin_users.py`
| GET | `/api/admin/users?q=` | 分页/搜索，附 `job_count`/`total_consumed`（只算 settled） |
| POST | `/api/admin/users` | `{username,email,password,role,initial_balance}` → 201 `{user, initial_key}`；**自动创建 `default` KEY，明文只在此响应出现一次**；初始余额走充值流水并记录操作员 |
| PATCH | `/api/admin/users/{id}` | `{status?,role?,rate_limit?,concurrency_limit?,password?}`；不能禁用/降级自己。**不能改余额** |
| POST | `/api/admin/users/{id}/recharge` | `{amount>0, remark}` → recharge_record + ledger `recharge` |
| POST | `/api/admin/users/{id}/adjust` | `{delta≠0, remark 必填}` → ledger `adjust`；负数不得使余额为负（402） |
| GET | `/api/admin/users/{id}/ledger` | 指定用户流水 |
| GET | `/api/admin/users/{id}/reconcile` | `{balance, ledger_sum, consistent}` 对账 |
### 充值/消费记录 — 已实现
| GET | `/api/admin/records/recharge` / `/consume` | 全量分页（含操作员用户名 / 消费状态） |
### 系统配置（已实现：`backend/app/api/admin_config.py`）
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/admin/config` | 脱敏视图：代理只回 `password_set`；License Key 回 `cb_••••xxxx`；R2 回 `endpoint_masked` + `key_suffix` |
| PUT | `/api/admin/config` | 全量保存。仅写字段 `proxy.password`、`cloakbrowser_license_key`、`r2_accounts[].endpoint/access_key_id/secret_access_key` **省略或回传掩码 = 保持原值**；R2 账号列表以提交为准（缺的即移除）；返回新脱敏视图。保存后后台给已启用 R2 桶写 1 天过期生命周期 |
| POST | `/api/admin/config/proxy/test` | body = `ProxyConfig`（可带 `password`，缺省用已存密码）。服务端拼 `{user}-region-{CC}-sid-{随机}-t-{min}` 走 curl_cffi 探测 → `{ok, proxy_masked, egress_ip, country, latency_ms, error}` |
| POST | `/api/admin/config/r2/test` | `{id}` 测已存账号，或 `{draft: R2Account}` 测弹窗里未保存的草稿（HeadBucket + List 1）；连通成功后顺带写入 1 天过期规则 |
| GET | `/api/admin/config/r2/usage?refresh=1` | 各账号 `used_bytes/object_count/over_quota`（ListObjectsV2 汇总，Redis 缓存 `R2_USAGE_CACHE_SECONDS`） |
| GET | `/api/admin/config/pricing/quote?model=&kind=image\|video&resolution=&duration=` | 按当前计费表报价（分） |

存储：`system_settings(key='system_config', value JSON, version)` 单文档原子保存；密钥字段 Fernet 加密（`FIELD_ENCRYPTION_KEY`），DB 永不落明文。每次保存 `version+1` 并 `PUBLISH firefly:config:changed <version>`，worker / harvester 订阅后热加载（`ConfigStore.load()` 带 5s 进程内缓存）。

字段语义（面板文案已对齐）：
- `sync_timeout_seconds` 同步接口最长等待；超时 504 + task_id，任务继续。
- `generation_timeout_seconds` worker 单任务上限（含排队等号/等票，从 `created_at`）；超过判失败并退款，停止重试。进程重启后看门狗仍会扫尾。
- `default_rate_limit` 用户默认限流（次/分钟，429）；`user_concurrency_default` 用户默认并发上限（同时运行任务数，1–200，超出排队）。
- 上游账号侧并发是 `account_concurrency_normal / _advanced`，与用户配额是两个维度。
- `proxy.upload_via_proxy`：参考图上传是否走住宅代理；默认关（直连）。生成结果下载始终直连。换 AT / 查额度 / 提交 / 轮询必须走代理。
### 请求日志
| GET | `/api/admin/logs` | 按任务归并。排队中/生成中即使还没打上游也会出现；已结束任务需有请求记录。筛选 `kind`/`status`/`q`。`latency_ms` 为任务墙钟（`created_at`→`finished_at`/now），`attempt_latency_ms` 为单次上游耗时。 |
| GET | `/api/admin/logs/{job_id}` | 同一任务的全部请求，`attempts[]` 按时间升序。任务「耗时」同上；每次请求旁标单次 `attempt_latency_ms`。 |
| DELETE | `/api/admin/logs?scope=` | 清理：`failed` / `older_3d` / `all` |
### 账号池（运营）
| GET | `/api/admin/accounts/export` | 按当前筛选导出，行格式与导入相同（`邮箱----Cookie` 或纯 Cookie）。管理员接口，明文 Cookie，不写日志。 |
| POST | `/api/admin/accounts/import` | body `{text, group?}`。`group` 忽略（调度不按组）。每行一个账号：`email----Cookie` 或纯 Cookie Header（须含 `ims_sid`）。只加密存 Cookie，不落 AT |
| GET | `/api/admin/accounts` | 列表。不含 AT/device token/device id；筛选 `q`（脱敏邮箱）、`status`、`credits_lt`。另返回全站汇总 `accounts_total` / `accounts_parked` / `accounts_hard` / `credits_available`（不受分页/筛选影响）。面板仅显示 Device 是否已初始化 |
| DELETE | `/api/admin/accounts` | body `{ids:[...]}` 批量删除所选账号；当前移动端/网页 canary 受保护，须先在系统设置取消 |
| PATCH | `/api/admin/accounts/{id}` | `{status?, group?, cookie?}`。`group` 不影响调度。Cookie 留空不改；写入时加密覆盖，指纹冲突 409 |
| POST | `/api/admin/accounts/{id}/refresh` | 验证凭据并查询积分。未配代理 422。`proxy_tls` 换新 sticky 出口最多重试 3 次；走网页 clio 查额度，短 AT 不入库 |

## 4. 对外生成 API（KEY 鉴权）

对外同时提供 **OpenAI 端点格式** 与 **Gemini 官方格式**，每个能力都有 **同步** 与 **异步** 两种调用方式。两套格式只是"协议适配层"，内部统一进同一条 `generation` 流水线（入队 → worker → 结果），计费/限流/日志一致。

### 4.0 同步 vs 异步（通用约定）
| 模式 | 行为 | 适用 |
|---|---|---|
| **同步** | 请求等待任务终态（默认 180s，可配置）。内部仍先持久化并入队，由 Redis 事件通知 API 进程 | 图片、短任务 |
| **异步** | 立即返回任务 ID/Operation，客户端轮询、SSE 或接收 webhook | 视频、长任务、批量并发 |

- OpenAI 端点可用 `?async=true` 或 `Prefer: respond-async`；Gemini 使用 `:predictLongRunning` / Operation 语义。
- 统一任务查询：`GET /v1/tasks/{task_id}`；产物：`GET /v1/tasks/{task_id}/content`。
- 可选 `callback_url`；终态回调使用 `X-Signature: sha256=<HMAC>`，失败指数退避且有最大次数。
- 同步等待超时返回 **504**（不是 408，避免与上游风控 408 混淆），错误 metadata 带 `task_id`；后台任务继续执行。
- `Idempotency-Key` 唯一约束；重复请求返回原任务，不重复生成和扣费。

### 4.1 OpenAI 端点格式（`/v1`，`Authorization: Bearer sk-...`）
| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/v1/images/generations` | 文生图：`{model,prompt,n,size,quality,response_format}`；默认同步，`?async=true` 转异步 |
| POST | `/v1/images/edits` | **图片编辑** multipart：`image`/`image[]`、可选 `mask`、`prompt`、`model`、`n`、`size`。先上传为 reference blob，再按模型映射 `general/subject/style/frame` |
| POST | `/v1/videos/generations` | 文生视频/图生视频；默认异步，可 `?wait=true` 同步等待 |
| GET | `/v1/videos/{task_id}` | 查询视频任务；`/content` 下载 |
| GET | `/v1/tasks/{task_id}` | 统一查询图片/视频异步任务 |
| GET | `/v1/models` | 模型、能力、尺寸、价格 |

同步图片响应兼容 `{created,data:[{url|b64_json,revised_prompt}]}`；异步响应为 `{id,object:"generation.task",status,created_at}`。错误采用 OpenAI `{error:{message,type,param,code}}`。

### 4.2 Gemini 官方格式（`/v1beta`，`x-goog-api-key` 或 Bearer KEY）
| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/v1beta/models/{model}:generateContent` | 同步生成；解析 `contents[].parts[]` 的 `text`、`inlineData`、`fileData` |
| POST | `/v1beta/models/{model}:streamGenerateContent` | SSE；先发状态事件，终态返回 Gemini `GenerateContentResponse` |
| POST | `/v1beta/models/{model}:predict` | Imagen 风格同步图片生成/编辑 |
| POST | `/v1beta/models/{model}:predictLongRunning` | 异步图片/视频，返回 `{name:"operations/{id}",done:false}` |
| GET | `/v1beta/operations/{id}` | 查询 Operation；完成后返回 `response` 或 `error` |
| POST | `/upload/v1beta/files` | 可选兼容文件上传，返回可在 `fileData.fileUri` 引用的资源 |

- 图片编辑通过 `contents.parts` 同时传文本和 `inlineData`/`fileData`；多图顺序保留，mask 通过扩展字段 `generationConfig.mask`。
- 返回图片放在 `candidates[].content.parts[].inlineData`（小图/b64）或 `fileData`（大图/视频 URL）。
- Gemini 风格错误采用 `{error:{code,message,status,details}}`；内部错误码映射到标准 HTTP/Google RPC status。
- 两套协议共用同一任务、幂等、计费、内容审核和资源归属校验，不维护两套业务逻辑。

## 5. 内网 admin-api（采集器 → ARP 池）
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/admin-api/adobe/harvester/bootstrap` | 铸票参数 + `proxy_ready`。License 字段保留兼容（开源 fingerprint-chromium 忽略）。采集器每轮拉取，`version` 变化即热加载；同时写 Redis 心跳（面板「采集器在线」）。**不返回代理密码。** |
| POST | `/admin-api/adobe/harvester/lease` | 按配置中心模板 `build_session` 发一枚全新 sticky SID：`{sid,egress_id,proxy_url,proxy_masked,sticky_minutes}`。采集器必须把 `proxy_url` 原样用于铸票并原样入池。 |
| POST | `/admin-api/adobe/arp` | body `{tokens:[{t,ua,ch,proxy_url,egress_id}...]}`；TTL / max_uses 取自配置中心（不是 env） |
| GET | `/admin-api/adobe/arp` | 池健康：`{present,ready,oldest_age_sec,egress}` |
| POST | `/admin-api/adobe/arp/invalidate` | `{id}` 作废（408 后）|

- 鉴权 `X-Internal-Token=ARP_INTERNAL_TOKEN` + IP 白名单，**绝不暴露公网**。
- 水位：`ready >= arp_pool_target` 时采集器停铸；`ready < arp_min_ready` 时跳过铸完后的空闲等待。提交 round-robin 取票。
- 看门狗：采集器 supervisor 每 3s 拉 bootstrap（心跳 + 热加载浏览器数）。worker 崩了自动拉起；浏览器 close 卡住杀进程树。TTL 到期 Redis 自动删票。
- `socks5` 在 `build_session` 落成 `socks5h://`（DNS 走代理）；铸票与提交共用这一条 URL。

## 错误码约定（节选）
| code | 含义 |
|---|---|
| 0 | ok |
| 1001 | 未登录/token 失效 |
| 1003 | 无权限 |
| 2001 | 余额不足 |
| 3001 | 无可用 ARP（排队重试）|
| 3002 | 上游临时不可用（408/5xx，已重试）|
| 3003 | 内容被拒绝（451）|
| 3004 | 账号额度耗尽/限速 |
