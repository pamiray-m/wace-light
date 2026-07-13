import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// WACE Light dev server proxies API calls to the backend on :8000.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/voundry": "http://127.0.0.1:8000",
      "/health": "http://127.0.0.1:8000",
    },
  },
});
