import { mkdtempSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { defineConfig } from "@playwright/test"

// Real backend, throwaway data: the server runs against a temporary HOME and data
// root, never a rider's. E2E_PYTHON selects an interpreter with the server
// requirements installed (default: python).
const port = Number(process.env.E2E_PORT ?? 22488)
process.env.E2E_HOME ??= mkdtempSync(join(tmpdir(), "shepherd-e2e-"))
const home = process.env.E2E_HOME

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  workers: 1,
  fullyParallel: false,
  reporter: [["list"]],
  use: { baseURL: `http://127.0.0.1:${port}/v2/`, trace: "retain-on-failure" },
  webServer: {
    command: `${process.env.E2E_PYTHON ?? "python"} -m uvicorn app:app --host 127.0.0.1 --port ${port} --workers 1 --log-level warning`,
    cwd: "../src",
    url: `http://127.0.0.1:${port}/healthz`,
    reuseExistingServer: false,
    timeout: 120_000,
    env: {
      HOME: home,
      SHEPHERD_HOME: join(home, "data"),
      SHEPHERD_NO_NET: "1",
      ICU_ATHLETE_ID: "",
      ICU_API_KEY: "",
      ICU_ACCESS_TOKEN: "",
      PYTHONDONTWRITEBYTECODE: "1",
    },
  },
})
