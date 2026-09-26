# 03 · 数据模型

PostgreSQL。金额/积分一律 `BIGINT` 最小单位（分 / 积分），禁 float。时间 `TIMESTAMPTZ`。敏感字段加密存储。

## 实体总览
```
users ─1:N─ api_keys
users ─1:N─ generation_jobs ─1:1─ consume_records
users ─1:N─ recharge_records
users ─1:N─ balance_ledger        (余额流水，充值/消费/退款统一记账)
upstream_accounts (账号池)         request_logs (审计)
arp_pool (Redis 为主，PG 可选快照)  system_configs (KV 配置)
```

## users — 用户
| 字段 | 类型 | 说明 |
|---|---|---|
| id | BIGINT PK | |
| username / email | text unique | 登录标识 |
| password_hash | text | argon2/bcrypt |
| role | enum(`user`,`admin`) | 权限 |
| balance | BIGINT | 当前**可用**余额（最小单位）；预扣即时扣减，与 ledger 对账 |
| status | enum(`active`,`disabled`) | disabled 的用户预扣直接失败 |
| rate_limit / concurrency_limit | int nullable | 为空取系统配置 `default_rate_limit` / `user_concurrency_default` |
| created_at / last_login_at | timestamptz | |
- 密码哈希：`scrypt`（stdlib，n=2^14），格式 `scrypt$n$r$p$salt$hash`。
- **新建用户自动创建一把名为 `default` 的 KEY**，明文随创建响应返回一次。

## api_keys — 用户 KEY
| id | key_prefix (text, `sk-xxxx` 前几位，用于展示) | key_hash (text, HMAC-SHA256(APP_SECRET_KEY, key)) | user_id FK | name | status(`active`/`revoked`) | rate_limit(每分钟) | last_used_at | created_at / revoked_at |
- 明文 KEY 仅创建时返回一次；校验按 hash 查表 + 常量时间比较，用户 `disabled` 或 KEY `revoked` 均拒绝。

## 计费模型（三段式，防透支）
```
submit ──hold(−cost)──▶ queued ──▶ running ──▶ succeeded : settle（consume_record → settled，余额不动）
   │ 余额不足 → 402，不建任务                 └──▶ failed/rejected : refund(+cost)（ledger refund，consume_record → refunded）
```
- 预扣是 `UPDATE users SET balance = balance - :c WHERE id = :u AND balance >= :c AND status = 'active'`，影响 0 行即拒绝；并发下永不为负。
- `balance_ledger (job_id, type)` 唯一：同一任务 hold / refund 各只可能发生一次。
- `generation_jobs (user_id, idempotency_key)` 唯一：重复提交返回原任务，不重复预扣。

## generation_jobs — 生成任务
| 字段 | 说明 |
|---|---|
| id / idempotency_key(unique) | 幂等键防重复扣费 |
| user_id FK / api_key_id FK(nullable) | 面板或 API 来源 |
| kind | enum(`image`,`video`) |
| model | 面板 id，见 [13-models](./13-models.md)：`nano-banana` / `gpt-image-2` / `seedance-2.0` 等 |
| prompt / negative_prompt | text |
| params | jsonb（aspect_ratio, resolution, duration, seeds, reference_blob_ids...） |
| status | enum(`queued`,`running`,`succeeded`,`failed`,`rejected`) |
| cost | BIGINT 提交时按计费表锁定的预扣金额；失败退回后 `refunded_at` 非空 |
| source | enum(`panel`,`openai`,`gemini`) 入口来源 |
| result_urls | jsonb（对象存储路径 / 签名 URL） |
| error_code / error_message | 失败/拒绝原因（脱敏） |
| retry_count | 上游重试次数 |
| created_at / started_at / finished_at | 面板「耗时」= `finished_at − created_at`（生成中用 now）；与单次上游 `request_logs.latency_ms` 无关 |

## consume_records — 消费记录
| id | user_id FK | job_id FK(unique) | amount(BIGINT) | model | status(`pending`/`settled`/`refunded`) | created_at / settled_at |
- 预扣时与 ledger 同事务写入 `pending`；成功 `settled`，退回 `refunded`。

## recharge_records — 充值记录
| id | user_id FK | amount(BIGINT) | method(enum:manual/card/...) | operator_id(管理员,nullable) | remark | status | created_at |

## balance_ledger — 余额流水（对账真源）
| id | user_id FK | delta(BIGINT,正负) | balance_after | type(enum:`recharge`,`consume`,`refund`,`adjust`) | job_id(nullable) | ref_id / remark | created_at |
- 任何余额变动都在此留痕；`users.balance` 为缓存视图，以 ledger 为准做对账（`SUM(delta) == balance`）。
- 唯一约束 `(job_id, type)`（job_id 非空时）防止同一任务重复预扣 / 重复退回。

## upstream_accounts — 上游账号池（敏感，加密）
| 字段 | 说明 |
|---|---|
| id | |
| email | 账号标识（展示脱敏） |
| cookie_enc | **加密存储** Cookie Header，绝不明文。Access Token 每次请求用 Cookie 现换，不入库 |
| plan_cap | enum(`HARD`,`FREE`)，只用 HARD 出图 |
| group | 历史字段，调度不再使用。身份按模型分流（2.5 网页 / 其它 FF-iOS） |
| credits_remaining / credits_total | 额度快照 |
| status | enum(`active`,`parked`,`ratelimited`,`dead`) |
| parked_until | timestamptz（408 后临时冷却） |
| last_used_at / updated_at | |
- checkout 用 Redis 租约锁。移动端 408 → 阶梯 `parked` + `parked_until`（5m / 10m / 30m，成功清零），**看门狗到期拉回可用**，无 until 的 park 不自动恢复；**不因 408 标 dead**。**429 / 451 不得 park、不得 dead，任务继续重试。** 到期后仍受配置约束：观察期单号 1 路、有 408 计数不领敏感模型、坏窗口暂停换号连打。401 → 用 Cookie 现换 AT；Cookie 失效 → `dead`。

## request_logs — 请求日志（审计，脱敏）
| id | job_id FK(nullable) | account_hash | egress_id | endpoint | status_code | latency_ms | retry_count | arp_id | outcome(`ok`/`408`/`403`/...) | trace(json，每步上游响应，已脱敏) | created_at |
- **绝不**记录 token/cookie/代理密码明文。用于成功率(按 egress 累积)、单次上游耗时、审计。详情页展示 `trace` 逐步原始响应。面板任务「耗时」取 job 墙钟，不取本表 `latency_ms`。

## system_configs — 系统配置（KV）
| key(text PK) | value(jsonb) | updated_by | updated_at |
- 例：模型开关与定价、默认 impersonate、池水位阈值、限流阈值、公告等。热点走 Redis 缓存 + 主动失效。

## arp_pool — ARP 池
主存 **Redis**（低延迟、TTL 天然过期）：`arp:{id}` 存 bundle（见 [02-arp-core §3](./02-arp-core.md)），`arp:ready`(zset by expires) 供 checkout。PG 可选留快照仅用于监控统计，**不存明文代理密码**（或加密）。
