import React, { useEffect } from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { App as AntApp, ConfigProvider, theme } from "antd";
import zhCN from "antd/locale/zh_CN";
import { BrowserRouter } from "react-router-dom";
import App from "@/App";
import { darkTheme, lightTheme } from "@/theme";
import { useUi } from "@/store/auth";
import { feedback } from "@/utils/feedback";
import "@/styles/global.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, refetchOnWindowFocus: false, staleTime: 15_000 },
    mutations: { retry: 0 },
  },
});

/** 把 antd App 的 message 实例绑定到全局出口，供拦截器等非组件代码使用 */
function FeedbackBinder() {
  const { message } = AntApp.useApp();
  useEffect(() => { feedback.bind(message); }, [message]);
  return null;
}

function Providers() {
  const dark = useUi((state) => state.dark);
  return (
    <ConfigProvider locale={zhCN} theme={{ ...(dark ? darkTheme : lightTheme), algorithm: dark ? theme.darkAlgorithm : theme.defaultAlgorithm }}>
      <AntApp message={{ maxCount: 3, duration: 2.5, top: 64 }} notification={{ placement: "topRight", maxCount: 3 }}>
        <FeedbackBinder />
        <QueryClientProvider client={queryClient}>
          <BrowserRouter>
            <App />
          </BrowserRouter>
        </QueryClientProvider>
      </AntApp>
    </ConfigProvider>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <Providers />
  </React.StrictMode>,
);
