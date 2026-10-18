import { resolve } from "node:path"
import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vitest/config"

// https://vite.dev/config/
export default defineConfig({
  base: "/v2/",
  test: { environment: "jsdom", globals: false, setupFiles: ["./src/test-setup.ts"], exclude: ["e2e/**", "node_modules/**"] },
  // Dev container: proxy the backend routes to the API container (see docker-compose.dev.yml).
  server: process.env.API_TARGET
    ? {
        host: true,
        proxy: Object.fromEntries(
          ["/api", "/healthz", "/oauth", "/login", "/logout", "/profile", "/setup"].map((p) => [
            p,
            process.env.API_TARGET as string,
          ])
        ),
      }
    : undefined,
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": resolve(import.meta.dirname, "./src"),
    },
  },
})
