import type { MessageInstance } from "antd/es/message/interface";

/**
 * 全局统一提示出口。组件内使用 `App.useApp().message`；
 * 非组件代码（如 HTTP 拦截器）通过这里转发，保证提示样式与主题一致。
 */
let instance: MessageInstance | null = null;

export const feedback = {
  bind(message: MessageInstance) {
    instance = message;
  },
  success(content: string) {
    instance?.success(content);
  },
  error(content: string) {
    instance?.error(content);
  },
  warning(content: string) {
    instance?.warning(content);
  },
};
