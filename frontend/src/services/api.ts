import { http, USE_MOCK } from "@/services/http";
import { mock } from "@/services/mock";
import type {
  AccountListPage, AdminUser, ApiKey, ConsumeRecord, CreateImageRequest, CreateVideoRequest,
  CleanupScope, EgressScore, GenerationJob, JobListFilters, LedgerEntry, LoginResponse, LogListFilters, ModelInfo, Page,
  CreateUserRequest, CreateUserResponse, PatchUserRequest,
  Profile, ProxyConfig, ProxyTestResult, R2Account, R2TestResult, R2UsageResponse, RechargeRecord, RequestLog,
  StatsOverview, SystemConfig, TimeseriesPoint, UpstreamAccount, ArpStatus,
} from "@/types/api";

export interface AccountListFilters {
  q?: string;
  status?: string;
  credits_lt?: number;
}

export interface PatchAccountRequest {
  status?: string;
  group?: "normal" | "alpha";
  cookie?: string;
}

const data = async <T,>(promise: Promise<{ data: T }>): Promise<T> => (await promise).data;

export const api = {
  login: (username: string, password: string): Promise<LoginResponse> =>
    USE_MOCK ? mock.login(username) : data(http.post("/auth/login", { username, password })),
  me: (): Promise<Profile> => USE_MOCK ? mock.me() : data(http.get("/auth/me")),
  models: (): Promise<ModelInfo[]> => USE_MOCK ? mock.models() : data(http.get("/gen/models")),
  jobs: (page = 1, pageSize = 10, filters: JobListFilters = {}): Promise<Page<GenerationJob>> =>
    USE_MOCK ? mock.listJobs(page, pageSize, filters) : data(http.get("/jobs", { params: { page, page_size: pageSize, ...filters } })),
  job: (id: string): Promise<GenerationJob> => USE_MOCK ? mock.getJob(id) : data(http.get(`/jobs/${id}`)),
  clearJobs: (scope: CleanupScope): Promise<{ deleted: number }> =>
    USE_MOCK ? mock.clearJobs(scope) : data(http.delete("/jobs", { params: { scope } })),
  createImage: (req: CreateImageRequest, files?: File[]): Promise<GenerationJob> => {
    if (USE_MOCK) return mock.createImage(req);
    if (!files?.length) return data(http.post("/gen/image", req));
    const body = new FormData();
    body.append("model", req.model);
    body.append("prompt", req.prompt);
    body.append("aspect_ratio", req.aspect_ratio);
    body.append("resolution", req.resolution);
    body.append("idempotency_key", req.idempotency_key);
    for (const file of files) body.append("images", file);
    return data(http.post("/gen/image", body, { timeout: 120_000 }));
  },
  createVideo: (req: CreateVideoRequest, files?: File[]): Promise<GenerationJob> => {
    if (USE_MOCK) return mock.createVideo(req);
    if (!files?.length) return data(http.post("/gen/video", req));
    const body = new FormData();
    body.append("model", req.model);
    body.append("prompt", req.prompt);
    body.append("aspect_ratio", req.aspect_ratio);
    body.append("resolution", req.resolution);
    body.append("duration", String(req.duration ?? 5));
    body.append("idempotency_key", req.idempotency_key);
    for (const file of files) body.append("images", file);
    return data(http.post("/gen/video", body, { timeout: 120_000 }));
  },
  keys: (): Promise<ApiKey[]> => USE_MOCK ? mock.listKeys() : data(http.get("/keys")),
  createKey: (name: string): Promise<ApiKey> => USE_MOCK ? mock.createKey(name) : data(http.post("/keys", { name })),
  revokeKey: (id: number): Promise<void> => USE_MOCK ? mock.revokeKey(id) : data(http.delete(`/keys/${id}`)),
  ledger: (page = 1, pageSize = 10): Promise<Page<LedgerEntry>> =>
    USE_MOCK ? mock.ledger(page, pageSize) : data(http.get("/ledger", { params: { page, page_size: pageSize } })),
  announcement: (): Promise<{ announcement: string }> =>
    USE_MOCK ? mock.announcement() : data(http.get("/announcement")),
  users: (page = 1, pageSize = 10): Promise<Page<AdminUser>> =>
    USE_MOCK ? mock.users(page, pageSize) : data(http.get("/admin/users", { params: { page, page_size: pageSize } })),
  createUser: (req: CreateUserRequest): Promise<CreateUserResponse> =>
    USE_MOCK ? mock.createUser(req) : data(http.post("/admin/users", req)),
  patchUser: (id: number, patch: PatchUserRequest): Promise<AdminUser> =>
    USE_MOCK ? mock.patchUser(id, patch) : data(http.patch(`/admin/users/${id}`, patch)),
  rechargeUser: (id: number, amount: number, remark: string): Promise<AdminUser> =>
    USE_MOCK ? mock.rechargeUser(id, amount) : data(http.post(`/admin/users/${id}/recharge`, { amount, remark })),
  adjustUser: (id: number, delta: number, remark: string): Promise<AdminUser> =>
    USE_MOCK ? mock.rechargeUser(id, delta) : data(http.post(`/admin/users/${id}/adjust`, { delta, remark })),
  recharges: (page = 1, pageSize = 10): Promise<Page<RechargeRecord>> =>
    USE_MOCK ? mock.recharges(page, pageSize) : data(http.get("/admin/records/recharge", { params: { page, page_size: pageSize } })),
  consumes: (page = 1, pageSize = 10): Promise<Page<ConsumeRecord>> =>
    USE_MOCK ? mock.consumes(page, pageSize) : data(http.get("/admin/records/consume", { params: { page, page_size: pageSize } })),
  logs: (page = 1, pageSize = 10, filters: LogListFilters = {}): Promise<Page<RequestLog>> =>
    USE_MOCK ? mock.logs(page, pageSize, filters) : data(http.get("/admin/logs", { params: { page, page_size: pageSize, ...filters } })),
  logDetail: (jobId: string): Promise<RequestLog> =>
    USE_MOCK ? mock.logDetail(jobId) : data(http.get(`/admin/logs/${jobId}`)),
  clearLogs: (scope: CleanupScope): Promise<{ deleted: number }> =>
    USE_MOCK ? mock.clearLogs(scope) : data(http.delete("/admin/logs", { params: { scope } })),
  accounts: (page = 1, pageSize = 10, filters: AccountListFilters = {}): Promise<AccountListPage> =>
    USE_MOCK ? mock.accounts(page, pageSize, filters) : data(http.get("/admin/accounts", { params: { page, page_size: pageSize, ...filters } })),
  importAccounts: (text: string): Promise<{ created: number; skipped: number; total: number; verifying: number }> =>
    USE_MOCK
      ? Promise.resolve({ created: 0, skipped: 0, total: 0, verifying: 0 })
      : data(http.post("/admin/accounts/import", { text })),
  exportAccounts: (filters: AccountListFilters = {}): Promise<{ text: string; count: number }> =>
    USE_MOCK ? mock.exportAccounts(filters) : data(http.get("/admin/accounts/export", { params: filters })),
  deleteAccounts: (ids: number[]): Promise<{ deleted: number }> =>
    USE_MOCK ? mock.deleteAccounts(ids) : data(http.delete("/admin/accounts", { data: { ids } })),
  patchAccount: (id: number, patch: PatchAccountRequest): Promise<UpstreamAccount> =>
    USE_MOCK ? mock.patchAccount(id, patch) : data(http.patch(`/admin/accounts/${id}`, patch)),
  refreshAccount: (id: number): Promise<UpstreamAccount> =>
    USE_MOCK ? mock.refreshAccount(id) : data(http.post(`/admin/accounts/${id}/refresh`, undefined, { timeout: 90_000 })),
  overview: (): Promise<StatsOverview> => USE_MOCK ? mock.overview() : data(http.get("/admin/stats/overview")),
  timeseries: (): Promise<TimeseriesPoint[]> => USE_MOCK ? mock.timeseries() : data(http.get("/admin/stats/timeseries")),
  egress: (): Promise<EgressScore[]> => USE_MOCK ? mock.egress() : data(http.get("/admin/stats/egress")),
  arpStatus: (): Promise<ArpStatus> => USE_MOCK ? mock.arpStatus() : data(http.get("/admin/arp")),
  config: (): Promise<SystemConfig> => USE_MOCK ? mock.config() : data(http.get("/admin/config")),
  saveConfig: (config: SystemConfig): Promise<SystemConfig> => USE_MOCK ? mock.saveConfig(config) : data(http.put("/admin/config", config)),
  testProxy: (proxy: ProxyConfig): Promise<ProxyTestResult> => USE_MOCK ? mock.testProxy(proxy) : data(http.post("/admin/config/proxy/test", proxy)),
  /** 已保存账号传 id；弹窗里未保存的草稿传 draft（可含明文密钥，仅用于本次测试） */
  testR2: (payload: { id?: string; draft?: R2Account }): Promise<R2TestResult> =>
    USE_MOCK ? mock.testR2(payload) : data(http.post("/admin/config/r2/test", payload)),
  r2Usage: (refresh = false): Promise<R2UsageResponse> =>
    USE_MOCK ? mock.r2Usage() : data(http.get("/admin/config/r2/usage", { params: refresh ? { refresh: 1 } : undefined, timeout: 60_000 })),
};
