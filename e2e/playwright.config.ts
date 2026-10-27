import { defineConfig } from "@playwright/test";

/**
 * 移したデータを、確認用の DB を読む新アプリ（scripts/e2e-stack.sh up）で確かめる。
 *
 * - 先に scripts/prepare_e2e_users.py apply で、テスト用の会員を用意する
 * - パスワードの変更・再設定をするテストがあるので、流し直す前に apply し直す
 * - 1 本ずつ流す（同じ会員を複数のテストが使い、ログインの回数制限もある）
 */
export default defineConfig({
  testDir: ".",
  testMatch: /.*\.spec\.ts/,
  workers: 1,
  fullyParallel: false,
  retries: 0,
  timeout: 60_000,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://recademy.localhost:13000",
    locale: "ja-JP",
    timezoneId: "Asia/Tokyo",
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { browserName: "chromium" } }],
});
