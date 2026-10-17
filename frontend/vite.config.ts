import react from "@vitejs/plugin-react";
import path from "node:path";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "src") },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": { target: process.env.VITE_PROXY_TARGET ?? "http://127.0.0.1:18000", changeOrigin: true },
      "/v1": { target: process.env.VITE_PROXY_TARGET ?? "http://127.0.0.1:18000", changeOrigin: true },
    },
  },
  build: {
    target: "es2020",
    sourcemap: false,
    // ProLayout/Ant Design shared runtime; route-level feature chunks remain small.
    chunkSizeWarningLimit: 1100,
  },
});
