import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev: UI on :5173 proxies /api to the FastAPI server on :8000 (no CORS pain).
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { "/api": "http://localhost:8000" } },
});
