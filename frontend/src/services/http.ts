import axios, { AxiosError } from "axios";
import { useAuth } from "@/store/auth";
import { feedback } from "@/utils/feedback";

interface Envelope<T> {
  code: number;
  message: string;
  data: T;
}

export const http = axios.create({ baseURL: "/api", timeout: 30_000 });

http.interceptors.request.use((config) => {
  const token = useAuth.getState().token;
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

http.interceptors.response.use(
  (res) => {
    const body = res.data as Envelope<unknown> | undefined;
    if (body && typeof body === "object" && "code" in body) {
      if (body.code !== 0) {
        const err = new Error(body.message || "请求失败");
        (err as Error & { code?: number }).code = body.code;
        return Promise.reject(err);
      }
      res.data = body.data;
    }
    return res;
  },
  (error: AxiosError<Envelope<unknown>>) => {
    const status = error.response?.status;
    if (status === 401) {
      useAuth.getState().logout();
      if (!location.pathname.startsWith("/login")) location.assign("/login");
      return Promise.reject(new Error("登录已过期，请重新登录"));
    }
    const payload = error.response?.data as (Envelope<unknown> & { detail?: unknown }) | undefined;
    let msg = (typeof payload?.message === "string" && payload.message) || "";
    if (!msg && Array.isArray(payload?.detail) && payload.detail[0] && typeof payload.detail[0] === "object") {
      const first = payload.detail[0] as { msg?: string };
      const raw = first.msg || "";
      msg = raw.startsWith("Value error, ") ? raw.slice("Value error, ".length) : raw;
    }
    if (!msg) msg = error.message || "网络错误";
    if (status !== 401) feedback.error(msg);
    return Promise.reject(new Error(msg));
  },
);

export const USE_MOCK = import.meta.env.VITE_USE_MOCK !== "0";
