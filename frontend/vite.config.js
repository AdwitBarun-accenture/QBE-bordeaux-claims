import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In dev, /api is proxied to the FastAPI backend on :8000.
// In production the built files are served by nginx, which proxies /api the same way.
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { "/api": "http://localhost:8000" } },
  preview: { proxy: { "/api": "http://localhost:8000" } },
});
