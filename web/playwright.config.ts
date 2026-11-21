import { defineConfig, devices } from "@playwright/test";

// Runs against a production build in recording mode, so it needs no backend.
// Build first: pnpm build && pnpm e2e
const PORT = 3200;

export default defineConfig({
  testDir: "e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    launchOptions: { args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"] },
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: `pnpm exec next start -H 127.0.0.1 -p ${PORT}`,
    url: `http://127.0.0.1:${PORT}`,
    reuseExistingServer: false,
    // Empty values win over .env.local, which forces the recording.
    env: { BACKDATE_API_URL: "", BACKDATE_TOKEN: "", BACKDATE_ALLOW_WRITES: "" },
  },
});
