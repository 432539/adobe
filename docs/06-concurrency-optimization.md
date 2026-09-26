# 06 · 高并发与系统优化

前提：**上游账号、ARP 都是稀缺 + 短命资源**，成功率成簇（好/坏窗口）。系统吞吐由"可用账号数 × 可用 ARP 数 × 好窗口命中"决定，不是简单加机器就能线性扩。

## 1. 分层限流（从外到内）
1. **入口**：Nginx/反代 连接数 + 面板/`/v1` 按用户与 KEY 令牌桶（Redis）。
2. **队列**：生成请求全部先持久化并入队；同步接口只是等待同一任务的 Redis 终态事件，不在 API 进程执行生成。
3. **worker 并发**：`worker_concurrency`（配置中心，默认 32，最高 200）与账号池容量取小；单号并发看 `account_concurrency_normal`。
4. **上游**：408 用 `parked_until` 退避；429 / 451 不 park 账号，任务退避重试。
- `image`、`video`、`media` 分队列与 worker，防止分钟级视频任务阻塞图片；队列设最大深度，超限返回 429/503 + `Retry-After`。

## 2. 资源池化与调度
- **账号池**：Redis 租约锁 `SET account:{id}:lease NX PX <ttl>`；只挑 `status=active & plan=HARD`；408 → `parked`+冷却，跨号重试骑好窗口；每次请求用 Cookie 现换 AT，不入库；Cookie 失效标 `dead`。
- **ARP 池**：常备 4–20 枚未过期票。`checkout` **round-robin** 把并发摊到多枚上（禁止总拿最新那张）；账号无关、请求无关，寿命内可复用。`uses<max_uses` 才留在 ready；408/身份失败 `invalidate` 后下次重试换票。`ready < arp_min_ready` 采集器跳过空闲加速铸；`ready >= arp_pool_target` 停铸。20 并发靠池里几枚新鲜票 + 住宅出口，不靠 20 个浏览器。
- **egress 评分**：按 egress 累积成功/失败（`egress_scores`），优先调度高分出口；单样本不下结论。

## 3. 数据一致性与幂等
- 生成幂等键唯一约束：重复提交返回已有 job，杜绝重复扣费。
- 扣费：Redis 原子预扣（Lua：查余额→扣→返回）+ 落库对账，或 PG `SELECT FOR UPDATE`；成功才 `consume`，失败/拒绝退款写 `refund`。金额全整数。
- 状态机严格迁移，避免并发把 job 从终态改回。

## 4. IO 与连接
- 全 async（FastAPI/asyncpg/redis.asyncio）；curl_cffi 同步提交放线程池 / Celery，绝不阻塞事件循环。
- PG 连接池匹配 worker 数；curl_cffi session 每请求新建（绑该次 proxy/fp）用完释放；下载与轮询走本机 IP，只提交走代理。
- 大文件（视频结果）流式落对象存储，避免全量进内存。
- 同步等待用 Redis Pub/Sub/Stream + 最多 180s timeout，不做高频数据库轮询；客户端断开不取消已入队任务。
- curl_cffi 的提交 session 不跨不同 ARP/代理复用；轮询/下载可用独立连接池，避免连接状态串污染。

## 5. 缓存
- 热点只读：系统配置、`key_hash→user_id`、模型定价、账号池/ARP 池快照 → Redis + 短 TTL + 主动失效。
- 生成结果元数据缓存，产物走对象存储 + CDN；预签名 URL 有访问控制与过期。

## 6. 可观测与自愈
- 指标（Prometheus/自研）：池水位、按 egress 成功率、队列深度、P50/P95 出图耗时、408 率、账号健康分布。
- 每次提交落 `request_log`（脱敏）；异常告警（池空、成功率跌破阈值、账号大面积 dead）。
- 自愈：采集器崩溃自拉起；账号 token 到期自动刷；ARP 过期自动清；worker 幂等可重启不丢单。

## 7. 横向扩展
- 面板无状态（JWT + Redis 会话黑名单）→ 多副本 + 负载均衡。
- worker 无状态 → 按住宅出口分组多实例；采集器按出口分布多实例，合并入同一池（跨多 IP 攒 Arkose 信任）。
- DB 读写分离 / 分区（`request_logs`、`generation_jobs` 按时间分区）应对日志量增长。

## 8. 成本与容量估算要点
- 采集器：1-2 浏览器常驻 ~0.5-1GB；铸票 75s/张，池维持 3-10 条。
- 出图并发上限 ≈ min(未过期 ARP 数, 可用 HARD 账号数, worker 并发)。要更高并发 → 加出口/账号/采集器，而不是让出图进程自己铸票。
- 压测必须拆开测：入口吞吐、同步长连接、队列吞吐、上游有效并发、对象下载带宽；不能用单一 QPS 代表系统容量。

## 9. 住宅代理流量优化（ARP 质量优先）

- **必须代理**：Firefly 页面、Sherlock/Arkose/Forter、`generate-async` 提交；出口必须与 ARP bundle 一致。
- **代理流量很小，可先保留**：IMS token 交换和任务轮询 JSON，避免在链路未验证前改变身份路径。
- **必须直连**：生成结果 presigned CDN 下载、MinIO/S3 上传、缩略图处理。图片/视频大流量不得穿住宅代理。
- 结果转存对象存储后，用户下载只访问平台 CDN；按内容 hash 去重，重复访问不再请求上游。
- Harvester 支持 `HARVESTER_BLOCK_RESOURCE_TYPES`，但默认空。禁止直接默认屏蔽 `script/xhr/fetch`；图片、字体也可能参与风控信号。
- 优化按 A/B 推进：同一批出口先采集基线成功率/每票流量，再分别测试 `media`、`image`；成功率、408率、票 TTL 任一变差即回滚。
- 浏览器缓存/复用会降低“新鲜指纹”强信号，第一阶段不启用。只有数据证明同出口短周期复用不降成功率时，才考虑每浏览器复用 2–3 次。
