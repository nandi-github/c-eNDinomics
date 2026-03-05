// filename: ui/vite.config.ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react-swc";

export default defineConfig({
  plugins: [react()],
  root: ".",
  build: {
    outDir: "dist",
    emptyOutDir: true
  },
  server: {
    port: 5173,
    proxy: {
      // Proxy API calls to FastAPI running on localhost:8000
      "/health": "http://localhost:8000",
      "/profiles": "http://localhost:8000",
      "/profile-config": "http://localhost:8000",
      "/reports": "http://localhost:8000",
      "/artifact": "http://localhost:8000",
      "/run": "http://localhost:8000",
      "/help.html": "http://localhost:8000"
    }
  }
});

