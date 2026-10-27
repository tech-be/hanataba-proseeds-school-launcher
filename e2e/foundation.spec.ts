/**
 * 01 基盤のテスト仕様（docs/db/01-foundation/test-spec.md）の E のケース。
 *
 * 移したデータを、新アプリの API と画面から確かめる。画面の不具合は見ない（データが
 * 読めて、旧と同じ値が出ること・運営が保存し直せることを見る）。
 * 期待する値は e2e/.personas.json（移行先の値）。旧との突き合わせは verify が受け持つ。
 */
import { expect, test } from "@playwright/test";
import {
  MAILPIT,
  NEW_PASSWORD,
  PASSWORD,
  TENANT,
  acceptCookieConsent,
  apiLogin,
  getJson,
  identifier,
  loginRequest,
  persona,
  tenantHeaders,
  uiLogin,
  waitForResetToken,
} from "./helpers";

const UNAVAILABLE = "このアカウントは現在利用できません";

function need(name: string) {
  const p = persona(name);
  test.skip(!p, `役 ${name} の会員を用意していない`);
  return p!;
}

test.describe("01 基盤", () => {
  test("F-02 recademy のブランディングに旧のテナント名が出る", async ({ request }) => {
    const body = await getJson(request, "/api/v1/branding");
    expect(body.tenant_name).toBe(TENANT.name);
  });

  test("F-17 受講者がログインすると /change-password に移り、変えるとホームに着く", async ({ page }) => {
    const p = need("learner_change");
    await uiLogin(page, identifier(p));
    await expect(page).toHaveURL(/\/change-password/, { timeout: 15_000 });
    await page.getByLabel("現在のパスワード").fill(PASSWORD);
    await page.getByLabel("新しいパスワード", { exact: true }).fill(NEW_PASSWORD);
    await page.getByLabel("新しいパスワード（確認）").fill(NEW_PASSWORD);
    await page.getByRole("button", { name: "パスワードを変更する" }).click();
    await expect(page).not.toHaveURL(/\/(change-password|login)/, { timeout: 15_000 });
  });

  test("F-18 ログイン ID しか持たない会員が、ログイン ID でログインできる", async ({ request }) => {
    const p = need("login_id_only");
    expect(p.email).toBeNull();
    const resp = await loginRequest(request, p.login_id!);
    expect(resp.status()).toBe(200);
  });

  test("F-19 無効の会員・削除済みの会員は、正しいパスワードでもログインできない", async ({ request }) => {
    const inactive = persona("inactive");
    const deleted = persona("deleted");
    test.skip(!inactive && !deleted, "役 inactive・deleted の会員を用意していない");
    if (inactive) {
      const resp = await loginRequest(request, identifier(inactive));
      expect(resp.status()).toBe(401);
      expect((await resp.json()).message).toContain(UNAVAILABLE);
    }
    if (deleted) {
      expect(deleted.email).toBeNull();
      expect(deleted.login_id).toBeNull();
      for (const legacy of [deleted.legacy_login_id, deleted.legacy_email]) {
        if (!legacy) continue;
        const resp = await loginRequest(request, legacy);
        expect(resp.status(), "旧のログイン ID・メールではログインできない").toBe(401);
      }
    }
  });

  test("F-20 メールを持つ会員が、パスワードの再設定でログインできる", async ({ page, request }) => {
    const p = need("reset");
    // **新は再設定のメールを 1 人 24 時間に 3 通までしか送らない。** 何度も流すときは
    // e2e/users.json の reset を別の会員に変える（届かずに 30 秒で落ちる）
    const since = Date.now() - 5_000;
    const resp = await request.post("/api/v1/auth/forgot-password", {
      headers: tenantHeaders(),
      data: { email: p.email },
    });
    expect(resp.status()).toBe(200);
    const token = await waitForResetToken(request, p.email!, since);
    await acceptCookieConsent(page);
    await page.goto(`/reset-password?token=${token}`);
    await page.fill("#new-password", NEW_PASSWORD);
    await page.fill("#confirm-password", NEW_PASSWORD);
    await page.getByRole("button", { name: "パスワードをリセット" }).click();
    await expect(page.getByText("パスワードをリセットしました")).toBeVisible();
    expect((await loginRequest(request, p.email!, NEW_PASSWORD)).status()).toBe(200);
  });

  test("F-23 削除済みの会員が使っていたメールは、登録に使える", async ({ request }) => {
    const p = need("deleted");
    test.skip(!p.legacy_email, "削除済みの会員に旧のメールが無い");
    const body = await getJson(
      request,
      `/api/v1/auth/check-email?email=${encodeURIComponent(p.legacy_email!)}`,
    );
    expect(body.available).toBe(true);
  });

  test("F-32 運営の会員の一覧に、移した会員の数が出る", async ({ page, request }) => {
    const admin = need("admin");
    const token = await apiLogin(request, admin);
    const { total } = await getJson(request, "/api/v1/tenant/users?limit=1", token);
    expect(total).toBeGreaterThan(0);
    await uiLogin(page, identifier(admin));
    await page.goto("/admin/users");
    await expect(page.getByRole("heading", { name: "ユーザー管理" })).toBeVisible();
    await expect(page.getByText(`${total} 名`, { exact: true })).toBeVisible();
  });

  test("F-33 会員の詳細に、ログイン ID・住所・独自項目・個別番号が出る", async ({ page, request }) => {
    const admin = need("admin");
    const p = need("learner");
    const token = await apiLogin(request, admin);
    const detail = await getJson(request, `/api/v1/tenant/users/${p.id}`, token);
    expect(detail.login_id ?? null).toBe(p.login_id);
    // 新の API はメールの NULL を "" で返す
    expect(detail.email || null).toBe(p.email);
    const values = await getJson(request, `/api/v1/tenant/users/${p.id}/profile-values`, token);
    const scout = await getJson(request, `/api/v1/tenant/users/${p.id}/scout-display`, token);
    expect(scout.personal_no).toBe(p.personal_no);

    await uiLogin(page, identifier(admin));
    await page.goto(`/admin/users/${p.id}`);
    await expect(page.getByRole("heading", { name: "住所" }).or(page.getByText("住所").first())).toBeVisible();
    await expect(page.getByRole("heading", { name: "スクール独自の項目" })).toBeVisible();
    // 独自項目の値は入力欄に出る（受講者の設定と同じ部品）
    const filled = (values.items as Array<{ item_id: string; value: string; label: string; multiline: boolean }>).find(
      (i) => i.value,
    );
    if (filled) {
      const field = filled.multiline ? page.locator(`#pv-${filled.item_id}`) : page.getByLabel(filled.label).first();
      await expect(field).toHaveValue(filled.value);
    }
  });

  test("F-34 運営が移した会員のステータスを変えて元に戻せる", async ({ request }) => {
    const admin = need("admin");
    const token = await apiLogin(request, admin);
    const used = new Set(["learner", "learner_change", "reset", "login_id_only", "admin"].map((n) => persona(n)?.id));
    const list = await getJson(request, "/api/v1/tenant/users?limit=100&status=active&role=learner", token);
    const target = (list.data as Array<{ id: string }>).find((u) => !used.has(u.id));
    test.skip(!target, "変えてよい active の受講者がいない");
    for (const status of ["inactive", "active"]) {
      const resp = await request.patch(`/api/v1/tenant/users/${target!.id}/status`, {
        headers: tenantHeaders(token),
        data: { status },
      });
      expect(resp.status(), `status を ${status} に`).toBe(200);
    }
    const after = await getJson(request, `/api/v1/tenant/users/${target!.id}`, token);
    expect(after.status).toBe("active");
  });

  test("F-45 運営が入力項目を何も変えずに保存できる", async ({ request }) => {
    const token = await apiLogin(request, need("admin"));
    const current = await getJson(request, "/api/v1/tenant/profile-fields", token);
    const resp = await request.put("/api/v1/tenant/profile-fields", {
      headers: tenantHeaders(token),
      data: {
        fields: current.fields.map((f: Record<string, unknown>) => ({
          key: f.key,
          enabled: f.enabled,
          required: f.required,
          at_signup: f.at_signup,
        })),
        custom_items: current.custom_items,
      },
    });
    expect(resp.status(), await resp.text()).toBe(200);
  });

  test("F-46 受講者の設定に旧で入力した独自項目の値が出て、保存できる", async ({ page, request }) => {
    const p = need("learner");
    const token = await apiLogin(request, p);
    const { items } = await getJson(request, "/api/v1/profile-values", token);
    const values: Record<string, string> = {};
    for (const i of items as Array<{ item_id: string; value: string; editable: boolean }>) {
      if (i.editable) values[i.item_id] = i.value ?? "";
    }
    const resp = await request.put("/api/v1/profile-values", { headers: tenantHeaders(token), data: { values } });
    expect(resp.status(), await resp.text()).toBe(200);

    const filled = (items as Array<{ item_id: string; value: string; label: string; multiline: boolean }>).find(
      (i) => i.value,
    );
    test.skip(!filled, "独自項目の値を持たない受講者");
    await uiLogin(page, identifier(p));
    await page.goto("/settings");
    const field = filled!.multiline ? page.locator(`#pv-${filled!.item_id}`) : page.getByLabel(filled!.label).first();
    await expect(field).toHaveValue(filled!.value);
  });

  test("F-52 受講者の通知の受け取り設定が、移した受け取り設定と一致する", async ({ request }) => {
    const p = need("learner");
    const token = await apiLogin(request, p);
    const { items } = await getJson(request, "/api/v1/notification-preferences", token);
    const shown = new Set((items as Array<{ kind: string }>).map((i) => i.kind));
    const off = (items as Array<{ kind: string; enabled: boolean }>).filter((i) => !i.enabled).map((i) => i.kind);
    expect(off.sort()).toEqual(p.disabled_kinds.filter((k) => shown.has(k)).sort());
  });

  test("F-54 会員の詳細に「現在の番号」が旧の番号で出る", async ({ page }) => {
    const admin = need("admin");
    const p = need("learner");
    test.skip(!p.personal_no, "個別番号が無い");
    await uiLogin(page, identifier(admin));
    await page.goto(`/admin/users/${p.id}`);
    await expect(page.getByText(`現在の番号: ${p.personal_no}`)).toBeVisible();
  });

  test("F-56 運営が LINE の設定を何も変えずに保存できる", async ({ request }) => {
    const token = await apiLogin(request, need("admin"));
    const s = await getJson(request, "/api/v1/tenant/line-settings", token);
    const resp = await request.put("/api/v1/tenant/line-settings", {
      headers: tenantHeaders(token),
      data: {
        enabled: s.enabled,
        official_account_id: s.official_account_id,
        add_friend_message: s.add_friend_message,
        notification_kinds: s.notification_kinds,
        channel_secret: "",
        channel_access_token: "",
        login_channel_id: s.login_channel_id,
        login_channel_secret: "",
      },
    });
    expect(resp.status(), await resp.text()).toBe(200);
  });

  test("F-57 LINE ログインの可否が設定どおりで、ボタンの出方が合う", async ({ page, request }) => {
    const { available } = await getJson(request, "/api/v1/auth/line/status");
    await acceptCookieConsent(page);
    await page.goto("/login");
    await expect(page.locator("#email")).toBeVisible();
    await expect(page.getByText("LINEでログイン")).toHaveCount(available ? 1 : 0);
  });

  test("F-63 旧の属性がタグとして出て、受講者にその会員のタグが付いている", async ({ page, request }) => {
    const admin = need("admin");
    const p = need("learner");
    const token = await apiLogin(request, admin);
    const tags = (await getJson(request, "/api/v1/tenant/tags", token)) as Array<{ name: string }>;
    expect(tags.length).toBeGreaterThan(0);
    const mine = (await getJson(request, `/api/v1/tenant/users/${p.id}/tags`, token)) as Array<{ tag_name: string }>;
    expect(mine.map((t) => t.tag_name).sort()).toEqual([...p.tags].sort());

    await uiLogin(page, identifier(admin));
    await page.goto("/admin/tags");
    await expect(page.getByText(tags[0].name, { exact: true }).first()).toBeVisible();
  });
});

test.afterAll(() => {
  // パスワードを変えた会員がいるので、流し直す前に prepare_e2e_users.py apply し直す
  console.log(`mailpit: ${MAILPIT} / 流し直す前に scripts/prepare_e2e_users.py apply を流す`);
});
