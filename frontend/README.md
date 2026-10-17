# frontend

AD小怪兽控制台。登录页、侧栏、调用说明和个人设置会展示开源地址与技术支持 QQ 群。

- 开源地址：https://github.com/432539/adobe
- QQ 群：1109037692

```bash
pnpm install
pnpm dev
```

开发期 Vite 把 `/api`、`/v1` 代理到 `VITE_PROXY_TARGET`（默认 `http://127.0.0.1:18000`）。复制 `.env.example` 为 `.env`，不要提交 `.env`。
