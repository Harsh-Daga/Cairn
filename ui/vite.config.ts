import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "path";

const staticIife = process.env.CAIRN_STATIC_IIFE === "1";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "src"),
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    exclude: ["**/node_modules/**", "**/e2e/**"],
    coverage: {
      provider: "v8",
      reporter: ["text", "json", "json-summary", "lcov"],
      reportsDirectory: "./coverage",
      include: ["src/**/*.{ts,tsx}"],
      exclude: ["src/lib/generated/**", "src/test/**", "src/main.tsx", "src/vite-env.d.ts"],
      all: true,
    },
  },
  build: {
    outDir: staticIife ? "../server/static_file" : "../server/static",
    emptyOutDir: true,
    modulePreload: false,
    // file:// snapshots intentionally inline every lazy route into one IIFE. The release gate
    // enforces a tighter gzip budget for that artifact; the default uncompressed warning is not
    // comparable to route-split HTTP output.
    chunkSizeWarningLimit: staticIife ? 700 : 650,
    rollupOptions: staticIife
      ? {
          output: {
            format: "iife",
            inlineDynamicImports: true,
            name: "CairnApp",
          },
        }
      : {
          output: {
            chunkFileNames: "assets/[name]-[hash].js",
          },
        },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8787",
    },
  },
});
