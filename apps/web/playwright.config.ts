import { defineConfig, devices } from "@playwright/test";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

const state = process.env.PILOT_TEST_STATE_DIR ?? mkdtempSync(join(tmpdir(), "klave-pilot-"));
process.env.PILOT_TEST_STATE_DIR = state;
const quote = (value: string) => "'" + value.replaceAll("'", "'\\''") + "'";

export default defineConfig({
  testDir: "./e2e",
  workers: 1,
  fullyParallel: false,
  timeout: 120_000,
  expect: { timeout: 15_000 },
  reporter: [["list"]],
  use: {
    baseURL: "http://127.0.0.1:13000",
    trace: "off",
    video: "off",
    screenshot: "off",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: [
      quote(resolve("../../.venv/bin/python")),
      quote(resolve("../../scripts/pilot_test_env.py")),
      "serve --state-dir", quote(state),
    ].join(" "),
    url: "http://127.0.0.1:13000/bienvenida",
    reuseExistingServer: false,
    timeout: 120_000,
    gracefulShutdown: { signal: "SIGTERM", timeout: 15_000 },
    stdout: "ignore",
    stderr: "pipe",
  },
});
