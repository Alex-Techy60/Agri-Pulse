import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

// Dev: UI proxies /api to the backend (default: http://localhost:8000).
// Override by setting VITE_API_URL in frontend/.env.local, e.g.:
//   VITE_API_URL=https://kisaanmitra.onrender.com
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const apiTarget = env.VITE_API_URL || "http://localhost:8000";
  return {
    plugins: [react()],
    server: { host: true, port: 5173, proxy: { "/api": apiTarget } },
  };
});
