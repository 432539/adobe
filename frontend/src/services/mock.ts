/**
 * 内置 Mock 数据层：面板 API 未就绪时让界面完整可用。
 * 契约对齐 docs/04-api-spec.md，切换真实后端只需 VITE_USE_MOCK=0。
 */
import dayjs from "dayjs";
import type {
  AdminUser,
  ApiKey,
  ArpStatus,
  ConsumeRecord,
  CreateImageRequest,
  CreateUserRequest,
  CreateUserResponse,
  CreateVideoRequest,
  EgressScore,
  GenerationJob,
  LedgerEntry,
  LoginResponse,
  ModelInfo,
  ProxyConfig,
  ProxyTestResult,
  R2Account,
  R2TestResult,
  R2UsageResponse,
  Page,
  PatchUserRequest,
  Profile,
  RechargeRecord,
  RequestLog,
  StatsOverview,
  SystemConfig,
  TimeseriesPoint,
  AccountListPage,
  CleanupScope,
  UpstreamAccount,
  JobListFilters,
  LogListFilters,
} from "@/types/api";

const sleep = (ms = 220) => new Promise((r) => setTimeout(r, ms));
const rand = (min: number, max: number) => Math.floor(Math.random() * (max - min + 1)) + min;
const pick = <T,>(arr: readonly T[]): T => arr[rand(0, arr.length - 1)] as T;
const id = () => Math.random().toString(36).slice(2, 10);

const IMAGE_RATIOS = ["1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3", "5:4", "4:5", "21:9"];
const IMAGE_RES = ["1K", "2K", "4K"];
const VIDEO_RATIOS = ["16:9", "9:16"];
const VIDEO_RES = ["720p", "1080p"];
const VIDEO_DUR = [5, 8, 10];

const MODELS: ModelInfo[] = [
  { id: "nano-banana", name: "Nano Banana", kind: "image", price: 8, aspect_ratios: IMAGE_RATIOS, resolutions: IMAGE_RES, supports_edit: true, enabled: true, modes: ["t2i", "i2i"], max_reference_images: 8, submit_ready: true },
  { id: "nano-banana-pro", name: "Nano Banana Pro", kind: "image", price: 10, aspect_ratios: IMAGE_RATIOS, resolutions: IMAGE_RES, supports_edit: true, enabled: true, modes: ["t2i", "i2i"], max_reference_images: 8, submit_ready: true },
  { id: "gpt-image-2", name: "GPT Image 2", kind: "image", price: 8, aspect_ratios: IMAGE_RATIOS, resolutions: IMAGE_RES, supports_edit: true, enabled: true, modes: ["t2i", "i2i"], max_reference_images: 8, submit_ready: true },
  { id: "gpt-image-2.5-flare", name: "GPT Image 2.5 Flare", kind: "image", price: 8, aspect_ratios: IMAGE_RATIOS, resolutions: IMAGE_RES, supports_edit: true, enabled: true, modes: ["t2i", "i2i"], max_reference_images: 8, submit_ready: true },
  { id: "gpt-image-2.5-sunburst", name: "GPT Image 2.5 Sunburst", kind: "image", price: 8, aspect_ratios: IMAGE_RATIOS, resolutions: IMAGE_RES, supports_edit: true, enabled: true, modes: ["t2i", "i2i"], max_reference_images: 8, submit_ready: true },
  { id: "gemini-omni-flash", name: "Gemini Omni Flash", kind: "video", price: 10, aspect_ratios: VIDEO_RATIOS, resolutions: VIDEO_RES, durations: VIDEO_DUR, supports_edit: false, enabled: true, modes: ["t2v", "i2v"], max_reference_images: 4, submit_ready: true },
  { id: "seedance-2.0", name: "Seedance 2.0", kind: "video", price: 20, aspect_ratios: VIDEO_RATIOS, resolutions: VIDEO_RES, durations: VIDEO_DUR, supports_edit: false, enabled: true, modes: ["t2v", "i2v"], max_reference_images: 4, submit_ready: true },
  { id: "seedance-2.0-fast", name: "Seedance 2.0 Fast", kind: "video", price: 15, aspect_ratios: VIDEO_RATIOS, resolutions: ["720p"], durations: VIDEO_DUR, supports_edit: false, enabled: true, modes: ["t2v", "i2v"], max_reference_images: 4, submit_ready: true },
];

const USER: Profile = {
  id: 2, username: "创作者", email: "creator@example.com", role: "user",
  balance: 128_600, created_at: dayjs().subtract(90, "day").toISOString(),
  last_login_at: dayjs().subtract(5, "minute").toISOString(),
};
const ADMIN: Profile = { ...USER, id: 1, username: "系统管理员", email: "admin@example.com", role: "admin", balance: 999_999 };

let jobs: GenerationJob[] = Array.from({ length: 18 }, (_, i) => {
  const video = i % 4 === 0;
  const failed = i % 7 === 0;
  return {
    id: `job_${id()}`,
    kind: video ? "video" : "image",
    model: video ? "seedance-2.0" : "gpt-image-2",
    prompt: pick(["未来城市夜景，蓝色霓虹灯", "白色背景上的红苹果，摄影棚光效", "宇航员漫步在开满鲜花的月球", "极简科技产品展示"]),
    status: failed ? "failed" : "succeeded",
    progress: 100,
    cost: video ? 3000 : 800,
    result_urls: failed ? [] : video ? [`https://interactive-examples.mdn.mozilla.net/media/cc0-videos/flower.mp4`] : [`https://picsum.photos/seed/aigc${i}/800/800`],
    error_code: failed ? "content_rejected" : undefined,
    error_message: failed ? "内容触发安全策略，请修改提示词后重试" : undefined,
    created_at: dayjs().subtract(i * 3, "hour").toISOString(),
    finished_at: dayjs().subtract(i * 3, "hour").add(28, "second").toISOString(),
    params: { aspect_ratio: video ? "16:9" : "1:1", resolution: video ? "720p" : "1K" },
  };
});

let keys: ApiKey[] = [
  { id: 1, name: "生产环境", key_prefix: "sk-prod...8F2A", status: "active", rate_limit: 60, last_used_at: dayjs().subtract(3, "minute").toISOString(), created_at: dayjs().subtract(30, "day").toISOString() },
  { id: 2, name: "开发测试", key_prefix: "sk-dev...1C9B", status: "active", rate_limit: 20, last_used_at: dayjs().subtract(2, "day").toISOString(), created_at: dayjs().subtract(10, "day").toISOString() },
];

const adminUsers: AdminUser[] = Array.from({ length: 36 }, (_, i) => ({
  id: i + 2, username: `用户${String(i + 1).padStart(3, "0")}`, email: `user${i + 1}@example.com`,
  role: "user", balance: rand(1_000, 200_000), status: i % 11 === 0 ? "disabled" : "active",
  job_count: rand(0, 420), total_consumed: rand(0, 300_000),
  created_at: dayjs().subtract(rand(1, 240), "day").toISOString(),
  last_login_at: dayjs().subtract(rand(0, 30), "day").toISOString(),
}));

const ledger: LedgerEntry[] = Array.from({ length: 30 }, (_, i) => {
  const consume = i % 4 !== 0;
  const delta = consume ? -pick([400, 500, 800, 3000]) : pick([10_000, 50_000]);
  return { id: i + 1, delta, balance_after: 128_600 + i * 800, type: consume ? "consume" : "recharge", ref_id: `ref_${id()}`, remark: consume ? "生成任务消费" : "在线充值", created_at: dayjs().subtract(i * 7, "hour").toISOString() };
});

const requestLogs: RequestLog[] = Array.from({ length: 50 }, (_, i) => {
  const status = pick([200, 200, 200, 200, 408, 429, 451]);
  const video = i % 5 === 0;
  const resolution = video ? pick(["720p", "1080p"]) : pick(["1K", "2K", "4K"]);
  const model = video ? pick(["seedance-2.0", "seedance-2.0-fast"]) : pick(["gpt-image-2", "nano-banana-pro", "nano-banana"]);
  const names: Record<string, string> = {
    "gpt-image-2": "GPT Image 2",
    "nano-banana-pro": "Nano Banana Pro",
    "nano-banana": "Nano Banana",
    "seedance-2.0": "Seedance 2.0",
    "seedance-2.0-fast": "Seedance 2.0 Fast",
  };
  const ok = status === 200;
  return {
    id: i + 1,
    job_id: `job_${id()}`,
    account_hash: `sha256:${id()}***`,
    egress_id: `sid-${id().slice(0, 5)}`,
    endpoint: i % 3 ? "generate" : "poll",
    status_code: status,
    latency_ms: rand(120, 35_000),
    retry_count: ok ? 0 : rand(1, 2),
    arp_id: `arp_${id()}`,
    outcome: ok ? "ok" : String(status),
    created_at: dayjs().subtract(i * 11, "minute").toISOString(),
    model,
    model_label: `${names[model]} ${resolution} ${video ? "16:9" : "1:1"}`,
    resolution,
    aspect_ratio: video ? "16:9" : "1:1",
    channel: pick(["面板", "OpenAI", "Gemini"]),
    prompt: pick(["未来城市夜景，蓝色霓虹灯", "白色背景上的红苹果", "宇航员漫步在开满鲜花的月球"]),
    params: { aspect_ratio: video ? "16:9" : "1:1", resolution },
    result_urls: ok
      ? video
        ? ["https://interactive-examples.mdn.mozilla.net/media/cc0-videos/flower.mp4"]
        : [`https://picsum.photos/seed/log${i}/800/800`]
      : [],
    upstream_urls: ok
      ? video
        ? ["https://interactive-examples.mdn.mozilla.net/media/cc0-videos/flower.mp4"]
        : [`https://picsum.photos/seed/up${i}/800/800`]
      : [],
    trace: ok
      ? [
          { step: "auth", method: "POST", url: "https://upstream.example/token", status_code: 200, latency_ms: 420, body: { expires_in: 86400, access_token: "[REDACTED]" } },
          { step: "submit", method: "POST", url: video ? "https://upstream.example/v2/videos/generate-async" : "https://upstream.example/v2/images/generate-async", status_code: 200, latency_ms: 880, body: { status: "SUBMITTED" } },
          { step: "poll", method: "GET", url: "https://upstream.example/v2/jobs/result/demo", status_code: 200, latency_ms: 210, body: { status: "COMPLETED" } },
        ]
      : [{ step: "submit", method: "POST", status_code: status, error: String(status), body: { error_code: "timeout_error" } }],
    kind: video ? "video" : "image",
    username: pick(["carol", "admin", "创作者"]),
    job_status: ok ? "succeeded" : "failed",
    attempt_count: ok ? 1 : rand(2, 4),
  };
});

let accounts: UpstreamAccount[] = Array.from({ length: 24 }, (_, i) => {
  const status = pick(["active", "active", "active", "parked", "ratelimited", "dead"] as const);
  const total = pick([1000, 2000, 5000]);
  return {
    id: i + 1,
    email_masked: `acc***${String(i + 1).padStart(2, "0")}@****.com`,
    cookie: `ims_sid=mock-cookie-${i + 1}; locale=en_US`,
    plan_cap: i % 7 === 0 ? "FREE" : "HARD",
    group: i % 4 === 0 ? "alpha" : "normal",
    credential_status: "ready",
    ios_device_ready: i % 4 !== 0,
    credits_remaining: status === "dead" ? 0 : rand(0, total),
    credits_total: total,
    status,
    parked_until: status === "parked" ? dayjs().add(rand(5, 40), "minute").toISOString() : undefined,
    last_used_at: dayjs().subtract(rand(1, 180), "minute").toISOString(),
    updated_at: dayjs().subtract(rand(1, 60), "minute").toISOString(),
  };
});

const page = <T,>(items: T[], p = 1, ps = 20): Page<T> => ({ items: items.slice((p - 1) * ps, p * ps), total: items.length, page: p, page_size: ps });
const makeJob = (kind: "image" | "video", req: CreateImageRequest | CreateVideoRequest): GenerationJob => {
  const job: GenerationJob = { id: `job_${id()}`, kind, model: req.model, prompt: req.prompt, status: "running", progress: 25, cost: MODELS.find((m) => m.id === req.model)?.price ?? 0, result_urls: [], created_at: new Date().toISOString(), params: { ...req } };
  jobs = [job, ...jobs];
  setTimeout(() => { job.status = "succeeded"; job.progress = 100; job.finished_at = new Date().toISOString(); if (kind === "image") job.result_urls = [`https://picsum.photos/seed/${job.id}/1024/1024`]; }, 2500);
  return job;
};

export const mock = {
  async login(username: string): Promise<LoginResponse> { await sleep(450); const profile = username.toLowerCase().includes("admin") ? ADMIN : USER; return { token: `mock_${id()}`, role: profile.role, profile }; },
  async me(): Promise<Profile> { await sleep(); return USER; },
  async models(): Promise<ModelInfo[]> { await sleep(100); return MODELS; },
  async listJobs(p = 1, ps = 20, filters: JobListFilters = {}): Promise<Page<GenerationJob>> {
    await sleep();
    let rows = jobs;
    if (filters.prompt) rows = rows.filter((j) => j.prompt.includes(filters.prompt!));
    if (filters.model) rows = rows.filter((j) => j.model.includes(filters.model!));
    if (filters.status === "generating") rows = rows.filter((j) => j.status === "queued" || j.status === "running");
    else if (filters.status === "failed") rows = rows.filter((j) => j.status === "failed" || j.status === "rejected");
    else if (filters.status) rows = rows.filter((j) => j.status === filters.status);
    return page(rows, p, ps);
  },
  async getJob(jobId: string): Promise<GenerationJob> { await sleep(100); const job = jobs.find((j) => j.id === jobId); if (!job) throw new Error("任务不存在"); return job; },
  async clearJobs(scope: CleanupScope): Promise<{ deleted: number }> {
    await sleep();
    const before = jobs.length;
    const cutoff = dayjs().subtract(3, "day");
    jobs = jobs.filter((j) => {
      if (scope === "failed") return j.status !== "failed" && j.status !== "rejected";
      if (scope === "older_3d") return dayjs(j.created_at).isAfter(cutoff);
      return false;
    });
    return { deleted: before - jobs.length };
  },
  async createImage(req: CreateImageRequest): Promise<GenerationJob> { await sleep(300); return makeJob("image", req); },
  async createVideo(req: CreateVideoRequest): Promise<GenerationJob> { await sleep(300); return makeJob("video", req); },
  async listKeys(): Promise<ApiKey[]> { await sleep(); return keys; },
  async createKey(name: string): Promise<ApiKey> { await sleep(); const item: ApiKey = { id: Date.now(), name, key_prefix: `sk-${id()}...${id().slice(0, 4)}`, plain: `sk-${id()}${id()}${id()}${id()}`, status: "active", rate_limit: 60, created_at: new Date().toISOString() }; keys = [item, ...keys]; return item; },
  async revokeKey(keyId: number): Promise<void> { await sleep(); keys = keys.map((k) => k.id === keyId ? { ...k, status: "revoked" } : k); },
  async ledger(p = 1, ps = 20): Promise<Page<LedgerEntry>> { await sleep(); return page(ledger, p, ps); },
  async users(p = 1, ps = 20): Promise<Page<AdminUser>> { await sleep(); return page(adminUsers, p, ps); },
  async createUser(req: CreateUserRequest): Promise<CreateUserResponse> {
    await sleep(400);
    if (adminUsers.some((u) => u.username === req.username)) throw new Error("用户名或邮箱已存在");
    const user: AdminUser = { id: adminUsers.length + 100, username: req.username, email: req.email, role: req.role, balance: req.initial_balance, status: "active", job_count: 0, total_consumed: 0, created_at: new Date().toISOString() };
    adminUsers.unshift(user);
    const plain = `sk-${id()}${id()}${id()}`.slice(0, 43);
    return { user, initial_key: { id: rand(1000, 9999), name: "default", key_prefix: plain.slice(0, 10), status: "active", rate_limit: 60, created_at: user.created_at, plain } };
  },
  async patchUser(uid: number, patch: PatchUserRequest): Promise<AdminUser> {
    await sleep(300);
    const u = adminUsers.find((x) => x.id === uid); if (!u) throw new Error("用户不存在");
    Object.assign(u, patch.status ? { status: patch.status } : {}, patch.role ? { role: patch.role } : {}, patch.concurrency_limit ? { concurrency_limit: patch.concurrency_limit } : {}, patch.rate_limit ? { rate_limit: patch.rate_limit } : {});
    return { ...u };
  },
  async rechargeUser(uid: number, delta: number): Promise<AdminUser> {
    await sleep(300);
    const u = adminUsers.find((x) => x.id === uid); if (!u) throw new Error("用户不存在");
    if (u.balance + delta < 0) throw new Error("余额不足，调账后不能为负");
    u.balance += delta;
    return { ...u };
  },
  async recharges(p = 1, ps = 20): Promise<Page<RechargeRecord>> { await sleep(); return page(Array.from({ length: 30 }, (_, i) => ({ id: i + 1, user_id: i + 2, username: `用户${i + 1}`, amount: pick([10_000, 50_000, 100_000]), method: pick(["支付宝", "微信", "人工"]), operator: i % 3 === 0 ? "管理员" : undefined, status: "success" as const, created_at: dayjs().subtract(i, "day").toISOString() })), p, ps); },
  async consumes(p = 1, ps = 20): Promise<Page<ConsumeRecord>> { await sleep(); return page(jobs.map((j, i) => ({ id: i + 1, user_id: 2, username: "创作者", job_id: j.id, model: j.model, amount: j.cost, created_at: j.created_at })), p, ps); },
  async logs(p = 1, ps = 20, filters: LogListFilters = {}): Promise<Page<RequestLog>> {
    await sleep();
    let rows = requestLogs;
    if (filters.kind) rows = rows.filter((r) => r.kind === filters.kind);
    if (filters.status) rows = rows.filter((r) => r.job_status === filters.status);
    if (filters.q) rows = rows.filter((r) => (r.username || "").includes(filters.q!));
    return page(rows, p, ps);
  },
  async logDetail(jobId: string): Promise<RequestLog> {
    await sleep();
    const rows = requestLogs.filter((r) => r.job_id === jobId);
    if (!rows.length) throw new Error("日志不存在");
    const last = rows[rows.length - 1]!;
    return { ...last, attempts: rows, attempt_count: rows.length };
  },
  async clearLogs(scope: CleanupScope): Promise<{ deleted: number }> {
    await sleep();
    const before = requestLogs.length;
    const cutoff = dayjs().subtract(3, "day");
    const kept = requestLogs.filter((r) => {
      if (scope === "failed") return r.job_status !== "failed" && r.outcome === "ok";
      if (scope === "older_3d") return dayjs(r.created_at).isAfter(cutoff);
      return false;
    });
    requestLogs.splice(0, requestLogs.length, ...kept);
    return { deleted: before - requestLogs.length };
  },
  async accounts(p = 1, ps = 20, filters: { q?: string; status?: string; credits_lt?: number } = {}): Promise<AccountListPage> {
    await sleep();
    let rows = accounts;
    if (filters.q) {
      const q = filters.q.toLowerCase();
      rows = rows.filter((a) => a.email_masked.toLowerCase().includes(q));
    }
    if (filters.status) rows = rows.filter((a) => a.status === filters.status);
    if (typeof filters.credits_lt === "number") rows = rows.filter((a) => a.credits_remaining < filters.credits_lt!);
    const credits_available = accounts
      .filter((a) => a.status === "active")
      .reduce((sum, a) => sum + a.credits_remaining, 0);
    return {
      ...page(rows, p, ps),
      credits_available,
      accounts_total: accounts.length,
      accounts_parked: accounts.filter((a) => a.status === "parked").length,
      accounts_hard: accounts.filter((a) => a.plan_cap === "HARD").length,
    };
  },
  async exportAccounts(filters: { q?: string; status?: string; credits_lt?: number } = {}): Promise<{ text: string; count: number }> {
    const listed = await this.accounts(1, 1000, filters);
    const lines = listed.items.map((a) => (a.cookie ? `${a.email_masked}----${a.cookie}` : ""));
    const text = lines.filter(Boolean).join("\n");
    return { text, count: listed.items.length };
  },
  async deleteAccounts(ids: number[]): Promise<{ deleted: number }> {
    await sleep(200);
    const selected = new Set(ids);
    const before = accounts.length;
    accounts = accounts.filter((item) => !selected.has(item.id));
    return { deleted: before - accounts.length };
  },
  async patchAccount(accountId: number, patch: { status?: string; group?: "normal" | "alpha"; cookie?: string }): Promise<UpstreamAccount> {
    await sleep(200);
    const item = accounts.find((a) => a.id === accountId);
    if (!item) throw new Error("账号不存在");
    const next: UpstreamAccount = {
      ...item,
      status: (patch.status as UpstreamAccount["status"]) ?? item.status,
      group: patch.group ?? item.group,
      cookie: patch.cookie?.trim() || item.cookie,
      parked_until: patch.status === "active" ? undefined : item.parked_until,
      updated_at: new Date().toISOString(),
    };
    accounts = accounts.map((a) => a.id === accountId ? next : a);
    return next;
  },
  async refreshAccount(accountId: number): Promise<UpstreamAccount> {
    await sleep(400);
    const item = accounts.find((a) => a.id === accountId);
    if (!item) throw new Error("账号不存在");
    const next = { ...item, status: "active" as const, parked_until: undefined, updated_at: new Date().toISOString(), credits_remaining: Math.min(item.credits_total, item.credits_remaining + rand(50, 200)) };
    accounts = accounts.map((a) => a.id === accountId ? next : a);
    return next;
  },
  async overview(): Promise<StatsOverview> { await sleep(); return { users_total: 1286, users_active_today: 218, jobs_today: 3684, jobs_total: 10000, jobs_success_rate: 0.923, revenue_today: 286_400, revenue_total: 5_555_500, arp_ready: 5, arp_oldest_age_sec: 38, accounts_active: 12, accounts_total: 12, credits_available: 10860, credits_total: 20000, queue_depth: 7, p95_latency_ms: 31_800 }; },
  async timeseries(): Promise<TimeseriesPoint[]> { await sleep(); return Array.from({ length: 24 }, (_, i) => ({ ts: dayjs().subtract(23 - i, "hour").format("HH:00"), jobs: rand(80, 220), success_rate: rand(86, 98) / 100, p95_ms: rand(22_000, 42_000) })); },
  async egress(): Promise<EgressScore[]> { await sleep(); return Array.from({ length: 5 }, (_, i) => ({ egress_id: `sid-${id().slice(0, 5)}`, success: rand(80, 180), failed: rand(3, 22) + i })); },
  async arpStatus(): Promise<ArpStatus> {
    await sleep();
    return {
      present: false,
      ready: 0,
      oldest_age_sec: null,
      egress: {},
      tickets: [],
      events: [],
      last_publish: null,
      arp_ttl_seconds: 120,
      arp_min_ready: 3,
      arp_pool_target: 8,
      arp_mint_batch: 8,
      arp_max_uses: 10,
      mint_browser_count: 2,
      mint_interval_seconds: 10,
      proxy_ready: false,
      harvester_online: false,
      harvester_seen_at: null,
    };
  },
  async announcement(): Promise<{ announcement: string }> {
    await sleep();
    const cfg = await this.config();
    return { announcement: cfg.announcement };
  },
  async config(): Promise<SystemConfig> {
    await sleep();
    return {
      announcement: "平台运行正常，Chrome 148 ARP 池已启用。",
      sync_timeout_seconds: 180,
      generation_timeout_seconds: 300,
      default_rate_limit: 60,
      user_concurrency_default: 2,
      proxy: { scheme: "http", host: "us.arxlabs.io", port: 3010, username: "p9mx1124350", password_set: true, country: "SG", sticky_minutes: 10, sid_length: 8, upload_via_proxy: false },
      mint_browser_count: 2,
      mint_interval_seconds: 10,
      arp_ttl_seconds: 120,
      arp_max_uses: 10,
      arp_min_ready: 3,
      arp_pool_target: 8,
      arp_mint_batch: 8,
      cloakbrowser_license_key_masked: "cb_••••••••••••••••",
      retry_max_attempts: 10,
      retry_backoff_base_seconds: 0.1,
      adobe_dual_identity_enabled: true,
      normal_canary_account_id: 0,
      alpha_canary_account_id: 0,
      alpha_retry_max_attempts: 6,
      alpha_retry_delay_seconds: 1.2,
      account_park_seconds: 300,
      account_park_second_seconds: 600,
      account_park_disable_seconds: 1800,
      account_park_disable_after: 3,
      account_408_observe_seconds: 1800,
      account_408_block_models: "gpt-image-2.5-flare,gpt-image-2.5-sunburst",
      account_408_block_after: 1,
      arp_bad_window_count: 3,
      arp_bad_window_seconds: 60,
      arp_bad_window_pause_seconds: 120,
      worker_concurrency: 32,
      token_rotation: "random",
      account_concurrency_normal: 1,
      account_daily_image_limit: 5,
      account_concurrency_advanced: 1,
      disabled_auto_enable_waterline: 2,
      retryable_status_codes: "429,451,500,502,503,422",
      retryable_error_types: "UpstreamTemporaryError",
      storage_backend: "r2",
      gemini_image_response_format: "url",
      r2_accounts: Array.from({ length: 10 }, (_, i) => ({
        id: `cf${i + 1}`,
        name: `cf${i + 1}`,
        endpoint_masked: `${["ffa7964b", "b6ca0e4a", "dec57717", "a321384c", "22402cd9", "a88a20f4", "11361ba4", "aaf613c7", "7a835c81", "3c0a76a1"][i]}…arestorage.com`,
        bucket: "pic2api-media",
        public_base_url: `https://pub-${["23429673f166443c831c00f1c46e2a05", "6045ce4fffcc43c89fc25529d6ac405e", "c128659c78d447228955192d59e3aeff", "73fd3cbd4a3742278d6fab4b97e17abf", "791cdad1202540ca87e3f1cf7646c32e", "bf072aa571b1426e8b420156f51b97bb", "a7290bdda416409b9a23d6b8acc0b272", "fe152da0437642a1ae94d98ef9eb0fc2", "a6d0f51807e84bb782ef544f89c035ec", "4487c40156bb4065b2070d468c1c0d80"][i]}.r2.dev`,
        enabled: true,
        used_bytes: rand(1_200_000_000, 4_800_000_000),
        quota_bytes: 10 * 1024 * 1024 * 1024,
        key_suffix: ["ee82", "eb58", "9e39", "60d2", "3a11", "41c5", "6d94", "63fb", "6a19", "c4b4"][i]!,
      })),
      image_pricing: [
        { model_id: "nano-banana", model_name: "普通模型 Nano Banana / V2", tiers: [
          { resolution: "1K", pixels: "1024px", price: 8 },
          { resolution: "2K", pixels: "2048px", price: 12 },
          { resolution: "4K", pixels: "4096px", price: 15 },
        ] },
        { model_id: "nano-banana-pro", model_name: "Pro 模型 Nano Banana Pro", tiers: [
          { resolution: "1K", pixels: "1024px", price: 10 },
          { resolution: "2K", pixels: "2048px", price: 15 },
          { resolution: "4K", pixels: "4096px", price: 20 },
        ] },
        { model_id: "gpt-image-2", model_name: "GPT IMAGE 2", model_note: "gpt-image-2", tiers: [
          { resolution: "1K", pixels: "~1Mpx", price: 8 },
          { resolution: "2K", pixels: "~4Mpx", price: 12 },
          { resolution: "4K", pixels: "~8Mpx", price: 20 },
        ] },
        { model_id: "gpt-image-2.5-flare", model_name: "GPT IMAGE 2.5 Flare", model_note: "gpt-image-2.5-flare", tiers: [
          { resolution: "1K", pixels: "~1Mpx", price: 8 },
          { resolution: "2K", pixels: "~4Mpx", price: 12 },
          { resolution: "4K", pixels: "~8Mpx", price: 20 },
        ] },
        { model_id: "gpt-image-2.5-sunburst", model_name: "GPT IMAGE 2.5 Sunburst", model_note: "gpt-image-2.5-sunburst", tiers: [
          { resolution: "1K", pixels: "~1Mpx", price: 8 },
          { resolution: "2K", pixels: "~4Mpx", price: 12 },
          { resolution: "4K", pixels: "~8Mpx", price: 20 },
        ] },
      ],
      video_pricing: [
        { model_id: "gemini-omni-flash", model_name: "Gemini Omni Flash", billing: "per_second", note: "按秒计费", price: 10 },
        { model_id: "seedance-2.0", model_name: "Seedance 2.0", billing: "per_second", note: "按秒计费，支持参考图", price: 20 },
        { model_id: "seedance-2.0-fast", model_name: "Seedance 2.0 Fast", billing: "per_second", note: "按秒计费，支持参考图", price: 15 },
      ],
    };
  },
  async saveConfig(config: SystemConfig): Promise<SystemConfig> {
    await sleep(400);
    // 密钥只写不回显：模拟后端脱敏
    const { password, ...proxy } = config.proxy;
    const { cloakbrowser_license_key, ...rest } = config;
    return {
      ...rest,
      cloakbrowser_license_key_masked: cloakbrowser_license_key ? `${cloakbrowser_license_key.slice(0, 3)}••••${cloakbrowser_license_key.slice(-4)}` : rest.cloakbrowser_license_key_masked,
      proxy: { ...proxy, password_set: proxy.password_set || Boolean(password) },
      r2_accounts: config.r2_accounts.map((a) => {
        const { endpoint, access_key_id, secret_access_key, ...view } = a;
        return {
          ...view,
          id: a.id ?? `r2_${id().slice(0, 8)}`,
          endpoint_masked: endpoint ? `${endpoint.replace(/^https?:\/\//, "").slice(0, 10)}…${endpoint.slice(-11)}` : a.endpoint_masked,
          key_suffix: access_key_id ? access_key_id.slice(-4) : a.key_suffix,
          used_bytes: a.used_bytes ?? (secret_access_key ? 0 : undefined),
        };
      }),
    };
  },
  async testR2(payload: { id?: string; draft?: R2Account }): Promise<R2TestResult> {
    await sleep(700);
    const d = payload.draft;
    if (d && !d.id && !(d.access_key_id && d.secret_access_key)) return { id: "draft", ok: false, latency_ms: 0, error: "Access Key / Secret 未配置" };
    return { id: payload.id ?? d?.id ?? "draft", ok: true, latency_ms: rand(120, 480) };
  },
  async r2Usage(): Promise<R2UsageResponse> {
    await sleep(600);
    const cfg = await this.config();
    const accounts = cfg.r2_accounts.map((a) => ({ id: a.id!, used_bytes: a.used_bytes, object_count: rand(800, 4200), over_quota: false, truncated: false, cached: true, fetched_at: Date.now() / 1000 }));
    return { accounts, total_used_bytes: accounts.reduce((s, a) => s + (a.used_bytes ?? 0), 0), total_quota_bytes: cfg.r2_accounts.reduce((s, a) => s + a.quota_bytes, 0) };
  },
  async testProxy(proxy: ProxyConfig): Promise<ProxyTestResult> {
    await sleep(900);
    const sid = id().slice(0, proxy.sid_length || 8);
    const user = `${proxy.username}-region-${proxy.country}-sid-${sid}-t-${proxy.sticky_minutes}`;
    return { ok: true, proxy_masked: `${proxy.scheme}://${user}:••••@${proxy.host}:${proxy.port}`, egress_ip: `103.${rand(10, 250)}.${rand(1, 250)}.${rand(1, 250)}`, country: proxy.country, latency_ms: rand(320, 780) };
  },
};