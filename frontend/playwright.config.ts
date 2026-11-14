import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "tests/browser",
  testMatch: "*.spec.ts",
  fullyParallel: true,
  workers: 2,
  timeout: 60_000,
  use: {
    baseURL: "http://127.0.0.1:3102",
    viewport: { width: 1280, height: 900 },
    screenshot: "only-on-failure",
    launchOptions: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH ? {
      executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH,
      args: ["--no-sandbox"]
    } : undefined
  },
  webServer: {
    command: "npm run dev -- --hostname 127.0.0.1 --port 3102",
    env: { TODOIST_NEXT_DIST_DIR: ".next-e2e" },
    url: "http://127.0.0.1:3102/control-panel",
    reuseExistingServer: false,
    timeout: 120000
  }
});
