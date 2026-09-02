import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import { loadEnv } from "vite";
import { resolve } from "node:path";

export default defineConfig(({ mode }) => {
  const rootEnv = loadEnv(mode, resolve(import.meta.dirname, "../.."), "");
  const defaultRagbotTarget = `http:${"/"}${"/"}127.0.0.1:${rootEnv.API_PORT || "8080"}`;
  const ragbotTarget = rootEnv.EVAL_API_DEV_PROXY
    || defaultRagbotTarget;
  const proxy = {
    target: ragbotTarget,
    changeOrigin: false,
  };
  return {
    base: "./",
    plugins: [react()],
    build: {
      sourcemap: false,
      assetsInlineLimit: 4096,
    },
    server: {
      strictPort: true,
      proxy: {
        "/api/login": proxy,
        "/api/v1/evaluation": proxy,
      },
    },
    test: {
      environment: "jsdom",
      setupFiles: "./src/test/setup.ts",
      css: true,
      restoreMocks: true,
    },
  };
});
