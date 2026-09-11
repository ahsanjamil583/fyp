import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import process from "node:process";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const proxy = {
    "/api": "http://127.0.0.1:8000",
    "/uploads": "http://127.0.0.1:8000",
    "/whatsapp-bridge": { target: env.WHATSAPP_BRIDGE_URL || "http://127.0.0.1:3005", rewrite: (path) => path.replace(/^\/whatsapp-bridge/, ""), headers: { "X-Forwarded-Prefix": "/whatsapp-bridge" } },
  };
  const allowedHosts = (env.NGROK_HOST || "").split(",").map((host) => host.trim().replace(/^https?:\/\//, "").replace(/\/$/, "")).filter(Boolean);
  return {
  plugins: [react()],
  server: {
    port: 5173,
    allowedHosts,
    proxy,
  },
  preview: { allowedHosts, proxy },
  build: {
    chunkSizeWarningLimit: 1200,
    rollupOptions: {
      output: {
        manualChunks: {
          vendor: ["react", "react-dom", "react-router-dom"],
          query: ["@tanstack/react-query"],
          icons: ["lucide-react"],
        },
      },
    },
  },
  };
});
