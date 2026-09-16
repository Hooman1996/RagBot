import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import { loadEnv } from "vite";

export default defineConfig(({ mode }) => {
  const localEnv = loadEnv(mode, import.meta.dirname, "");
  const evalApiTarget = localEnv.EVAL_API_DEV_PROXY
    || `http:${"/"}${"/"}127.0.0.1:8090`;
  const proxy = {
    target: evalApiTarget,
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
