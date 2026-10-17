export type Role = "admin" | "user";

export interface Profile {
  id: number;
  username: string;
  email: string;
  role: Role;
  /** 余额，最小单位（积分） */
  balance: number;
  created_at: string;
  last_login_at?: string;
}

export interface LoginResponse {
  token: string;
  role: Role;
  profile: Profile;
}

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

/** 号池列表：分页数据 + 全站汇总（不受分页/筛选影响） */
export interface AccountListPage extends Page<UpstreamAccount> {
  credits_available: number;
  accounts_total: number;
  accounts_parked: number;
  accounts_hard: number;
}

export type JobKind = "image" | "video";
export type JobStatus = "queued" | "running" | "succeeded" | "failed" | "rejected";

export interface GenerationJob {
  id: string;
  kind: JobKind;
  model: string;
  prompt: string;
  status: JobStatus;
  progress: number;
  cost: number;
  result_urls: string[];
  error_code?: string;
  error_message?: string;
  created_at: string;
  finished_at?: string;
  params: Record<string, unknown>;
}

export interface ModelInfo {
  id: string;
  name: string;
  kind: JobKind;
  /** 单价，最小单位 */
  price: number;
  aspect_ratios: string[];
  resolutions: string[];
  durations?: number[];
  supports_edit: boolean;
  enabled: boolean;
  /** t2i / i2i / t2v / i2v */
  modes: string[];
  max_reference_images: number;
  submit_ready: boolean;
}

export interface ApiKey {
  id: number;
  name: string;
  key_prefix: string;
  status: "active" | "revoked";
  rate_limit: number;
  last_used_at?: string;
  created_at: string;
  /** 仅创建时返回一次 */
  plain?: string;
}

export interface LedgerEntry {
  id: number;
  delta: number;
  balance_after: number;
  type: "recharge" | "consume" | "refund" | "adjust";
  ref_id?: string;
  remark?: string;
  created_at: string;
}

export interface RechargeRecord {
  id: number;
  user_id: number;
  username: string;
  amount: number;
  method: string;
  operator?: string;
  remark?: string;
  status: "success" | "pending" | "failed";
  created_at: string;
}

export interface ConsumeRecord {
  id: number;
  user_id: number;
  username: string;
  job_id: string;
  model: string;
  amount: number;
  created_at: string;
}

export interface AdminUser extends Profile {
  status: "active" | "disabled";
  job_count: number;
  total_consumed: number;
  /** 为空取系统配置默认值 */
  rate_limit?: number | null;
  concurrency_limit?: number | null;
}

export interface CreateUserRequest {
  username: string;
  email: string;
  password: string;
  role: Role;
  /** 开户初始余额（分），走充值流水 */
  initial_balance: number;
}

/** 初始 KEY 明文只在此响应里出现一次 */
export interface CreateUserResponse {
  user: AdminUser;
  initial_key: ApiKey;
}

export interface PatchUserRequest {
  status?: "active" | "disabled";
  role?: Role;
  rate_limit?: number;
  concurrency_limit?: number;
  password?: string;
}

/** 上游账号池：管理员列表明文回显 Cookie；AT 永不回显 */
export interface UpstreamAccount {
  id: number;
  email_masked: string;
  plan_cap: "UNKNOWN" | "HARD" | "FREE";
  group: "normal" | "alpha";
  credential_status: "unverified" | "ready" | "invalid" | "transient";
  credential_error?: string;
  last_verified_at?: string;
  ios_device_ready: boolean;
  cookie: string;
  credits_remaining: number;
  credits_total: number;
  status: "active" | "parked" | "ratelimited" | "dead";
  parked_until?: string;
  last_used_at?: string;
  updated_at: string;
}

export interface RequestLog {
  id: number;
  job_id?: string;
  account_hash: string;
  egress_id: string;
  endpoint: string;
  status_code: number;
  latency_ms: number;
  attempt_latency_ms?: number;
  retry_count: number;
  arp_id?: string;
  outcome: string;
  created_at: string;
  model?: string;
  model_label?: string;
  resolution?: string;
  aspect_ratio?: string;
  channel?: string;
  prompt?: string;
  params?: Record<string, unknown>;
  result_urls?: string[];
  upstream_urls?: string[];
  trace?: Array<{
    step?: string;
    method?: string;
    url?: string;
    status_code?: number;
    latency_ms?: number;
    body?: unknown;
    error?: string;
    note?: string;
  }>;
  kind?: string;
  username?: string;
  job_status?: "succeeded" | "generating" | "failed";
  attempt_count?: number;
  attempts?: RequestLog[];
}

export type CleanupScope = "failed" | "older_3d" | "all";

export interface JobListFilters {
  prompt?: string;
  model?: string;
  status?: string;
}

export interface LogListFilters {
  kind?: string;
  status?: string;
  q?: string;
}

export interface StatsOverview {
  users_total: number;
  users_active_today: number;
  jobs_today: number;
  jobs_total: number;
  jobs_success_rate: number;
  revenue_today: number;
  revenue_total: number;
  arp_ready: number;
  arp_oldest_age_sec: number;
  accounts_active: number;
  accounts_total: number;
  credits_available: number;
  credits_total: number;
  queue_depth: number;
  p95_latency_ms: number;
}

export interface TimeseriesPoint {
  ts: string;
  jobs: number;
  success_rate: number;
  p95_ms: number;
}

export interface EgressScore {
  egress_id: string;
  success: number;
  failed: number;
  last_at?: string;
}

export interface ArpTicket {
  id: string;
  egress_id: string;
  minted_at: string;
  expires_at: string;
  age_sec: number;
  ttl_left_sec: number;
  uses: number;
  max_uses: number;
  chrome_148: boolean;
}

export interface ArpEvent {
  ts: string;
  type: string;
  id: string;
  egress_id: string;
}

export interface ArpStatus {
  present: boolean;
  ready: number;
  oldest_age_sec: number | null;
  egress: Record<string, number>;
  tickets: ArpTicket[];
  events: ArpEvent[];
  last_publish: { ts: string; id: string; egress_id: string } | null;
  arp_ttl_seconds: number;
  arp_min_ready: number;
  arp_pool_target: number;
  arp_mint_batch: number;
  arp_max_uses: number;
  mint_browser_count: number;
  mint_interval_seconds: number;
  proxy_ready: boolean;
  harvester_online: boolean;
  harvester_seen_at: string | null;
}

export interface SystemConfig {
  announcement: string;
  /** 同步接口最长等待；超时返回 504 + task_id，任务继续 */
  sync_timeout_seconds: number;
  /** worker 侧单任务上限；超过判失败并进入容错重试 */
  generation_timeout_seconds: number;
  /** 用户默认限流（次/分钟） */
  default_rate_limit: number;
  /** 用户默认并发上限（同时运行任务数） */
  user_concurrency_default: number;
  worker_concurrency: number;

  /** 代理（住宅 sticky 出口） */
  proxy: ProxyConfig;

  /** 铸币工厂 */
  mint_browser_count: number;
  mint_interval_seconds: number;
  arp_ttl_seconds: number;
  arp_max_uses: number;
  arp_min_ready: number;
  arp_pool_target: number;
  arp_mint_batch: number;
  cloakbrowser_license_key_masked: string;
  /** 仅写：留空保持不变 */
  cloakbrowser_license_key?: string;

  /** 重试与容错 */
  retry_max_attempts: number;
  retry_backoff_base_seconds: number;
  adobe_dual_identity_enabled: boolean;
  normal_canary_account_id: number;
  alpha_canary_account_id: number;
  alpha_retry_max_attempts: number;
  alpha_retry_delay_seconds: number;
  account_park_seconds: number;
  account_park_second_seconds: number;
  account_park_disable_seconds: number;
  account_park_disable_after: number;
  account_408_observe_seconds: number;
  account_408_block_models: string;
  account_408_block_after: number;
  arp_bad_window_count: number;
  arp_bad_window_seconds: number;
  arp_bad_window_pause_seconds: number;
  token_rotation: "random" | "round_robin" | "least_used";
  account_concurrency_normal: number;
  account_daily_image_limit: number;
  account_concurrency_advanced: number;
  disabled_auto_enable_waterline: number;
  retryable_status_codes: string;
  retryable_error_types: string;

  /** 存储 */
  storage_backend: "r2" | "s3" | "minio";
  gemini_image_response_format: "url" | "inline";
  r2_accounts: R2Account[];

  /** 计费（最小单位：分，100=1.00 积分） */
  image_pricing: ImagePricingTier[];
  video_pricing: VideoPricingTier[];
}

/**
 * 住宅代理配置。账号按供应商模板拼接：
 * `{username}-region-{country}-sid-{sid}-t-{sticky_minutes}`，其中 sid 每次铸票随机生成。
 * 密码后端加密存储，不回显；`password_set` 表示已配置。
 */
export interface ProxyConfig {
  scheme: "http" | "socks5";
  host: string;
  port: number;
  /** 账号前缀，如 p9mx1124350 */
  username: string;
  /** 仅写：留空表示不修改 */
  password?: string;
  password_set: boolean;
  /** 出口国家/地区代码，如 SG */
  country: string;
  /** 粘性会话时长（分钟），对应 `-t-N` */
  sticky_minutes: number;
  /** 会话 ID 位数，对应 `-sid-XXXXXXXX` */
  sid_length: number;
  /** 参考图上传是否走住宅代理；关闭则直连。生成结果下载始终直连 */
  upload_via_proxy: boolean;
}

export interface ProxyTestResult {
  ok: boolean;
  /** 本次测试实际使用的代理串（密码脱敏） */
  proxy_masked: string;
  egress_ip?: string;
  country?: string;
  latency_ms?: number;
  error?: string;
}

/** R2 账号。读取时 endpoint / key 均脱敏；新增或改密钥时填写仅写字段，留空保持不变。 */
export interface R2Account {
  /** 新增时为空，由后端分配 */
  id?: string;
  name: string;
  endpoint_masked?: string;
  /** 仅写：完整 endpoint（新增必填） */
  endpoint?: string;
  bucket: string;
  public_base_url: string;
  prefix?: string;
  enabled: boolean;
  used_bytes?: number;
  quota_bytes: number;
  key_suffix?: string;
  /** 仅写 */
  access_key_id?: string;
  /** 仅写 */
  secret_access_key?: string;
}

export interface R2TestResult {
  id: string;
  ok: boolean;
  latency_ms: number;
  error?: string;
}

export interface R2Usage {
  id: string;
  used_bytes?: number;
  object_count?: number;
  over_quota: boolean;
  truncated: boolean;
  cached: boolean;
  fetched_at?: number;
  error?: string;
}

export interface R2UsageResponse {
  accounts: R2Usage[];
  total_used_bytes: number;
  total_quota_bytes: number;
}

export interface ImagePricingTier {
  model_id: string;
  model_name: string;
  model_note?: string;
  tiers: { resolution: string; pixels: string; price: number }[];
}

export interface VideoPricingTier {
  model_id: string;
  model_name: string;
  billing: "per_second" | "per_call";
  note: string;
  price: number;
}

export interface CreateImageRequest {
  model: string;
  prompt: string;
  aspect_ratio: string;
  resolution: string;
  reference_blob_ids?: string[];
  idempotency_key: string;
}

export interface CreateVideoRequest {
  model: string;
  prompt: string;
  aspect_ratio: string;
  resolution: string;
  duration: number;
  reference_blob_ids?: string[];
  idempotency_key: string;
}
