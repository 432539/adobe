import dayjs from "dayjs";

/** 后端金额/积分为最小单位整数；前端仅做展示换算（100 = 1.00） */
export const fmtCredits = (v: number | undefined | null): string => {
  if (v === undefined || v === null) return "-";
  const sign = v < 0 ? "-" : "";
  const abs = Math.abs(v);
  return `${sign}${(abs / 100).toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
};

export const fmtTime = (v?: string): string => (v ? dayjs(v).format("YYYY-MM-DD HH:mm:ss") : "-");
export const fmtShortTime = (v?: string): string => (v ? dayjs(v).format("MM-DD HH:mm") : "-");
export const fmtHourLabel = (v?: string): string => {
  if (!v) return "";
  const parsed = dayjs(v);
  return parsed.isValid() ? parsed.format("HH:mm") : v;
};
export const fmtPercent = (v: number, digits = 1): string => `${(v * 100).toFixed(digits)}%`;
export const fmtMs = (v: number): string => (v >= 1000 ? `${(v / 1000).toFixed(1)}s` : `${v}ms`);

const MODEL_SHORT: Record<string, string> = {
  "nano-banana": "Nano Banana",
  "nano-banana-pro": "Nano Banana Pro",
  "gpt-image-2": "GPT Image 2",
  "gpt-image-2.5-flare": "GPT Image 2.5 Flare",
  "gpt-image-2.5-sunburst": "GPT Image 2.5 Sunburst",
  "gemini-omni-flash": "Gemini Omni Flash",
  "seedance-2.0": "Seedance 2.0",
  "seedance-2.0-fast": "Seedance 2.0 Fast",
  "veo-3.1": "Veo 3.1",
  "veo-3.1-ref": "Veo 3.1 Ref",
  "veo-3.1-fast": "Veo 3.1 Fast",
};

export const fmtModelLabel = (
  model?: string,
  resolution?: string,
  aspectRatio?: string,
): string => {
  if (!model) return "—";
  const name = MODEL_SHORT[model] || model;
  const parts = [name];
  const res = (resolution || "").trim();
  const ratio = (aspectRatio || "").trim();
  if (res && !name.toUpperCase().includes(res.toUpperCase())) parts.push(res);
  if (ratio && ratio.toLowerCase() !== "auto" && !parts.includes(ratio)) parts.push(ratio);
  return parts.join(" ");
};

export const durationMs = (start?: string, end?: string): number | null => {
  if (!start) return null;
  const from = dayjs(start);
  const to = end ? dayjs(end) : dayjs();
  if (!from.isValid() || !to.isValid()) return null;
  const ms = to.diff(from);
  return ms < 0 ? 0 : ms;
};

const FAIL_BY_CODE: Record<string, string> = {
  content_rejected: "451 违禁词",
  arp_rejected: "408 异常",
  rate_limited: "429 频繁",
  no_account: "暂无可用账号",
  arp_empty: "票据不足，请稍后重试",
  auth_failed: "账号鉴权失败",
  identity_rejected: "账号被拒绝",
  bad_request: "请求参数无效",
  resolution_unsupported: "该分辨率不受支持",
  proxy_tls: "连接异常",
  poll_timeout: "生成超时",
  job_failed: "生成失败",
  download_failed: "结果下载失败",
  upstream_error: "生成失败",
};

export function formatJobError(code?: string, message?: string): string {
  const mapped = FAIL_BY_CODE[code || ""];
  if (code === "content_rejected") return "451 违禁词";
  if (code === "arp_rejected") return "408 异常";
  if (code === "rate_limited") return "429 频繁";
  const raw = (message || "").replace(/adobe|firefly|ims|gemini-flash|firefly-3p|bks-epo/gi, "").replace(/\s{2,}/g, " ").trim();
  if (mapped && (!raw || /adobe|firefly/i.test(message || ""))) return mapped;
  return raw || mapped || "生成失败";
}

export const newIdempotencyKey = (): string =>
  typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
