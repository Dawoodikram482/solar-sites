import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Vite builds the React app into dist/ (served by FastAPI in production).
// During development (`npm run dev`, port 5173) the proxy forwards /api
// calls to the Python backend on port 8000, so the browser still sees one
// origin and the session cookie works the same way as in production.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: { "/api": "http://localhost:8000" },
  },
});
