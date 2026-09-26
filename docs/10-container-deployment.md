# 10 · 容器部署方案

## 服务拆分

| 服务 | 镜像/职责 | 是否可水平扩展 |
|---|---|---|
| `gateway` | Nginx/Caddy：TLS、静态前端、限流、路由 | 是 |
| `api` | FastAPI 面板、OpenAI/Gemini adapter、admin-api | 是（无状态） |
| `worker-image` | 图片生成/编辑任务 | 是 |
| `worker-video` | 视频任务，独立低并发队列 | 是 |
| `worker-media` | 上传、下载、转存、缩略图 | 是 |
| `postgres` | 业务数据 | 主从/托管优先 |
| `redis` | 队列、ARP 池、锁、缓存、事件 | Sentinel/托管优先 |
| `minio` | 本地对象存储；生产可换 S3 | 是 |
| `harvester` | Chrome 148 铸 ARP | 按住宅出口扩展 |

## Compose 拓扑

- 开发环境用 `compose.yml` + `compose.dev.yml`；生产用 `compose.prod.yml` 覆盖资源、健康检查、secret、replicas。
- `api/worker` 共用同一后端镜像，不同 command；镜像多阶段构建、非 root、只包含运行时依赖。
- 前端多阶段构建后由 gateway 提供静态文件，不在生产启动 Vite dev server。
- 数据卷：`pg_data`、`redis_data`（AOF）、`minio_data`；应用容器只读根文件系统，临时目录用 tmpfs。

## Harvester 容器化的现实约束

fingerprint-chromium 是特殊浏览器，不保证所有 Linux 容器都能保持与 Windows Chrome 148 相同的指纹。优先顺序：

1. **推荐**：harvester 跑在 Windows/住宅宿主机，其他组件容器化；通过内网 HTTPS 向 admin-api 发布 ARP。
2. 浏览器提供 Linux 构建时才做独立 harvester 镜像：安装运行库、`shm_size: 1gb`、Xvfb（有头模式）、只读挂载浏览器二进制。
3. 禁止为省事长期使用 `--no-sandbox`；若确需容器沙箱，配置 seccomp/user namespace/capabilities 后验收。
4. 容器内、宿主机提交前分别检测出口 IP，确保 sticky egress 一致。

## Secret 与测试 Cookie

- 生产使用 Docker secrets / Kubernetes Secret：数据库密码、JWT key、字段加密 key、ARP internal token、代理凭据。
- 测试 Cookie 文件只在本机调试时只读挂载：
  `/path/to/cookies.txt:/run/secrets/test_cookies:ro`
- 不通过 `COPY` 写入镜像，不放 `.env`，不输出文件内容。生产环境不挂载该测试文件。

## 网络隔离

- `public` 网络：仅 gateway。
- `app` 网络：gateway ↔ api；api ↔ worker/Redis/PostgreSQL/MinIO。
- `internal` 网络：harvester ↔ admin-api；`/admin-api/*` 在公网 gateway 明确拒绝。
- PostgreSQL、Redis、MinIO 管理端口不映射公网；容器间用服务名通信。

## 健康检查与启动顺序

- `api /health/live`：进程存活；`/health/ready`：DB/Redis/迁移完成。
- worker：Celery ping + 最近心跳；harvester：最近铸票时间、ARP ready 水位。
- gateway 仅把流量发给 ready 的 API。数据库迁移使用一次性 `migrate` job，不在每个副本启动时抢跑。
- `restart: unless-stopped` 只处理崩溃；业务级故障靠告警与熔断，避免无限重启掩盖问题。

## 资源与伸缩基线

- API：0.5–1 CPU / 512MB–1GB；按请求与同步等待连接数扩容。
- 图片 worker：1–2 CPU / 1–2GB；并发受账号/ARP 约束，不盲目调大。
- 视频 worker：独立队列，按账号容量设置低并发。
- harvester：每浏览器预留 1 CPU / 512MB–1GB，`/dev/shm` 至少 1GB。
- PostgreSQL/Redis 设置连接上限与内存淘汰策略；Redis ARP/锁库禁止使用会淘汰关键键的策略。

## 发布与回滚

- 镜像用 commit SHA 标签；先跑迁移兼容性检查，再滚动 API，最后 worker。
- 新旧 worker 需能共同处理任务 schema；schema 变更采用 expand → migrate → contract。
- 优雅停机：API 停接新请求；worker 等当前任务完成/重新入队；同步调用返回 task_id 供继续查询。
- 每次发布验证：health、ARP 水位、Cookie→token、测试图、OpenAI/Gemini 契约、日志无敏感数据。
