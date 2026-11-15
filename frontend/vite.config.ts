/// <reference types="vitest" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Node's process.env, declared here to avoid adding @types/node for one variable.
declare const process: { env: Record<string, string | undefined> };

// The backend port defaults to 8000. Set EARTHSIGNAL_API_PORT to point the dev proxy elsewhere
// (e.g. to run a second copy side by side for review).
const apiPort = process.env.EARTHSIGNAL_API_PORT ?? "8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": `http://127.0.0.1:${apiPort}` },
  },
  test: { environment: "node", include: ["src/**/*.test.ts"] },
});
