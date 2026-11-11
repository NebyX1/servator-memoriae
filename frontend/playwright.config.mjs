import { defineConfig } from '@playwright/test';
import { existsSync } from 'node:fs';
const windowsChrome = 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const executablePath = process.env.PLAYWRIGHT_EXECUTABLE_PATH || (process.platform === 'win32' && existsSync(windowsChrome) ? windowsChrome : undefined);
export default defineConfig({
  testDir: './e2e', testMatch: '*.spec.mjs', workers: 1, timeout: 60_000,
  use: { baseURL: 'http://127.0.0.1:18548', launchOptions: executablePath ? { executablePath } : {} },
});
