import fs from "node:fs";
import path from "node:path";
import { chromium, defineConfig, devices } from "@playwright/test";

const PORT = 3100;
const BASE_URL = `http://127.0.0.1:${PORT}`;
const hasProductionBuild = fs.existsSync(
  path.join(__dirname, ".next", "BUILD_ID"),
);
const systemChromePath =
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const hasBundledChromium = (() => {
  try {
    return fs.existsSync(chromium.executablePath());
  } catch {
    return false;
  }
})();
const useSystemChrome =
  !process.env.CI &&
  process.platform === "darwin" &&
  !hasBundledChromium &&
  fs.existsSync(systemChromePath);

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 2 : undefined,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: BASE_URL,
    trace: "on-first-retry",
  },
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        ...(useSystemChrome ? { channel: "chrome" } : {}),
      },
    },
  ],
  webServer: {
    command: hasProductionBuild
      ? `./node_modules/.bin/next start --port ${PORT} --hostname 127.0.0.1`
      : `./node_modules/.bin/next dev --port ${PORT} --hostname 127.0.0.1`,
    url: `${BASE_URL}/projects`,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
    env: {
      NEXT_PUBLIC_API_URL: "http://localhost:8000",
    },
  },
});
