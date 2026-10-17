import type { ProxyConfig } from "@/types/api";

/** 解析结果：能识别多少就填多少，其余交给用户补 */
export type ParsedProxy = Partial<Pick<ProxyConfig, "scheme" | "host" | "port" | "username" | "password" | "country" | "sticky_minutes" | "sid_length">>;

const USER_TEMPLATE = /^(.+?)-region-([A-Za-z]{2,3})-sid-([A-Za-z0-9]+)-t-(\d+)$/i;

/**
 * 解析供应商代理串，支持：
 * - `user:pass@host:port`
 * - `http://user:pass@host:port` / `socks5://...`
 * - `host:port:user:pass`
 * 账号若符合 `{u}-region-{CC}-sid-{SID}-t-{N}` 模板，会进一步拆出国家/时长/sid 位数。
 */
export function parseProxyLine(input: string): ParsedProxy | null {
  let raw = input.trim();
  if (!raw) return null;
  const out: ParsedProxy = {};

  const schemeMatch = raw.match(/^(https?|socks5h?):\/\//i);
  if (schemeMatch) {
    out.scheme = schemeMatch[0].toLowerCase().startsWith("socks") ? "socks5" : "http";
    raw = raw.slice(schemeMatch[0].length);
  }

  let username = "";
  let password = "";
  let host = "";
  let portText = "";

  const at = raw.lastIndexOf("@");
  if (at > 0) {
    const cred = raw.slice(0, at);
    const addr = raw.slice(at + 1);
    const c = cred.indexOf(":");
    if (c <= 0) return null;
    username = cred.slice(0, c);
    password = cred.slice(c + 1);
    const p = addr.lastIndexOf(":");
    if (p <= 0) return null;
    host = addr.slice(0, p);
    portText = addr.slice(p + 1);
  } else {
    // host:port:user:pass
    const parts = raw.split(":");
    if (parts.length < 4) return null;
    host = parts[0] ?? "";
    portText = parts[1] ?? "";
    username = parts[2] ?? "";
    password = parts.slice(3).join(":");
  }

  const port = Number(portText);
  if (!host || !Number.isInteger(port) || port < 1 || port > 65535 || !username) return null;

  out.host = host;
  out.port = port;
  out.password = password || undefined;

  const m = USER_TEMPLATE.exec(username);
  if (m && m[1] && m[2] && m[3] && m[4]) {
    out.username = m[1];
    out.country = m[2].toUpperCase();
    out.sid_length = m[3].length;
    out.sticky_minutes = Number(m[4]);
  } else {
    out.username = username;
  }
  return out;
}

const SID_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz23456789";

export function randomSid(length = 8): string {
  const bytes = new Uint8Array(length);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => SID_CHARS[b % SID_CHARS.length]).join("");
}

/** 按模板拼出一次会话用的完整账号名 */
export function buildProxyUsername(p: Pick<ProxyConfig, "username" | "country" | "sticky_minutes" | "sid_length">, sid = randomSid(p.sid_length)): string {
  return `${p.username}-region-${p.country}-sid-${sid}-t-${p.sticky_minutes}`;
}

/** 密码脱敏后的预览串，用于界面展示 */
export function previewProxyUrl(p: Pick<ProxyConfig, "scheme" | "host" | "port" | "username" | "country" | "sticky_minutes" | "sid_length">, sid?: string): string {
  const scheme = p.scheme === "socks5" ? "socks5h" : p.scheme;
  return `${scheme}://${buildProxyUsername(p, sid)}:••••@${p.host}:${p.port}`;
}
