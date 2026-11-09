import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In dev, proxy /api to the services (run them locally on 8001/8002 or use docker compose).
export default defineConfig({
  plugins: [react()],
  build: { sourcemap: false },
  server: {
    proxy: {
      "/api/auth": "http://localhost:8001",
      "/api": "http://localhost:8002",
    },
  },
});
