/**
 * 05 サポート（未実装だった移行の分）のテスト仕様（docs/db/05-support/test-spec.md）の E のケース。
 *
 * 移したお知らせ・クーポン・自動メールの文面・問い合わせ・講座のディスカッション・
 * career（就活プロフィール・面談）を、新アプリの API から確かめる。
 * 期待する ID は e2e/.personas.json の support（移行先の値）。旧との突き合わせは verify が受け持つ。
 */
import { expect, test } from "@playwright/test";
import { REMAINING, SUPPORT, apiLogin, getJson, listOf, persona, tenantHeaders } from "./helpers";

function need(name: string) {
  const p = persona(name);
  test.skip(!p, `役 ${name} の会員を用意していない`);
  return p!;
}

function facts() {
  test.skip(!SUPPORT, "e2e/.personas.json に support が無い（prepare_e2e_users.py apply を流し直す）");
  return SUPPORT!;
}

test.describe("05 サポート", () => {
  test("S-06 受講者に、自分に配信された移したお知らせだけが出て、開ける", async ({ request }) => {
    const f = facts();
    for (const name of ["news_reader", "learner"]) {
      const p = persona(name);
      if (!p || !f.announcements[name]) continue;
      const token = await apiLogin(request, p);
      const items = listOf<{ id: string }>(await getJson(request, "/api/v1/announcements?limit=100", token));
      const expected = new Set(f.announcements[name]);
      // 配信されたものだけが出る（対象外のお知らせは見えない）
      expect(items.every((i) => expected.has(i.id)), `${name} に配信外のお知らせが出ている`).toBe(true);
      expect(items.length).toBe(Math.min(expected.size, 100));
      if (items.length > 0) {
        const resp = await request.get(`/api/v1/announcements/${items[0].id}`, { headers: tenantHeaders(token) });
        expect(resp.status()).toBe(200);
      }
    }
  });

  test("S-07 運営が移したお知らせを何も変えずに保存でき、配信先が変わらない", async ({ request }) => {
    const f = facts();
    test.skip(!f.admin_announcement, "配信先のある公開中のお知らせが無い");
    const token = await apiLogin(request, need("admin"));
    const url = `/api/v1/tenant/announcements/${f.admin_announcement}`;
    const before = await getJson(request, url, token);
    const resp = await request.put(url, {
      headers: tenantHeaders(token),
      data: { title: before.title, body: before.body },
    });
    expect(resp.status(), await resp.text()).toBe(200);
    const after = await getJson(request, url, token);
    expect([...after.user_ids].sort()).toEqual([...before.user_ids].sort());
    expect(after.audience_type).toBe("specific_users");
  });

  test("S-15 受講者が移したクーポンのコードを確かめられる", async ({ request }) => {
    const f = facts();
    test.skip(f.coupons.length === 0, "移したクーポンが無い");
    const token = await apiLogin(request, need("learner"));
    let usable = 0;
    for (const coupon of f.coupons) {
      const resp = await request.post("/api/v1/coupons/validate", {
        headers: tenantHeaders(token),
        data: { code: coupon.code },
      });
      expect(resp.status(), coupon.code).toBe(200);
      const body = await resp.json();
      expect(typeof body.valid).toBe("boolean");
      if (!body.valid) expect(body.message, `${coupon.code} が使えない理由`).toBeTruthy();
      if (body.valid) usable++;
    }
    // 旧で有効なクーポン（期限なし）は新でも使える（2026-10-26 決定。旧のとおり有効で移す）
    expect(usable).toBeGreaterThan(0);
  });

  test("S-16 運営のクーポンの一覧に移したクーポンが出て、状態を切り替えて戻せる", async ({ request }) => {
    const f = facts();
    test.skip(f.coupons.length === 0, "移したクーポンが無い");
    const token = await apiLogin(request, need("admin"));
    const list = listOf<{ id: string; code: string; status: string; audience_type: string }>(
      await getJson(request, "/api/v1/tenant/coupons?limit=100", token),
    );
    const codes = new Set(list.map((c) => c.code.toUpperCase()));
    for (const coupon of f.coupons) expect(codes.has(coupon.code.toUpperCase()), coupon.code).toBe(true);
    const target = list.find((c) => c.status === "active");
    test.skip(!target, "有効なクーポンが無い");
    for (const status of ["inactive", "active"]) {
      const resp = await request.patch(`/api/v1/tenant/coupons/${target!.id}`, {
        headers: tenantHeaders(token),
        data: { status },
      });
      expect(resp.status(), `status を ${status} に`).toBe(200);
    }
    const after = listOf<{ id: string; audience_type: string }>(
      await getJson(request, "/api/v1/tenant/coupons?limit=100", token),
    ).find((c) => c.id === target!.id);
    expect(after?.audience_type).toBe(target!.audience_type);
  });

  test("S-23 運営の設定にメールの文面の一覧が出る（移した種別は変更済み）", async ({ request }) => {
    const token = await apiLogin(request, need("admin"));
    const body = await getJson(request, "/api/v1/tenant/email-templates", token);
    expect(listOf(body).length).toBeGreaterThan(0);
  });

  test("S-33 受講者の質問の履歴に、移した問い合わせと回答が出る", async ({ request }) => {
    const f = facts();
    const p = need("inquirer");
    test.skip(!f.inquiries?.length, "移した問い合わせを持つ会員がいない");
    const token = await apiLogin(request, p);
    const items = listOf<{ id: string; resolution?: string | null }>(
      await getJson(request, "/api/v1/inquiries?limit=50", token),
    );
    const ids = new Set(items.map((i) => i.id));
    for (const id of f.inquiries!) expect(ids.has(id), id).toBe(true);
    expect(items.some((i) => (i.resolution ?? "").length > 0)).toBe(true);
  });

  test("S-34・S-35 運営の問い合わせの一覧・詳細に移した問い合わせが出て、分類に other がある", async ({ request }) => {
    const f = facts();
    test.skip(!f.inquiries?.length, "移した問い合わせが無い");
    const token = await apiLogin(request, need("admin"));
    const items = listOf<{ id: string }>(
      await getJson(request, "/api/v1/tenant/inquiries?status=resolved&limit=100", token),
    );
    const ids = new Set(items.map((i) => i.id));
    expect(ids.has(f.inquiries![0])).toBe(true);
    const detail = await getJson(request, `/api/v1/tenant/inquiries/${f.inquiries![0]}`, token);
    expect((detail.resolution ?? "").length).toBeGreaterThan(0);
    const categories = listOf<{ code: string }>(await getJson(request, "/api/v1/tenant/inquiry-categories", token));
    expect(categories.map((c) => c.code)).toContain("other");
  });

  test("S-52 講座のユニットのディスカッションに移した投稿が出る", async ({ request }) => {
    const f = facts();
    const p = need("discussant");
    test.skip(!f.discussion_posts?.length, "移した投稿が無い");
    const token = await apiLogin(request, p);
    const post = f.discussion_posts![0];
    const items = listOf<{ id: string }>(
      await getJson(request, `/api/v1/lessons/${post.lesson_id}/discussions?limit=100`, token),
    );
    expect(items.map((i) => i.id)).toContain(post.id);
  });

  test("S-67 受講者が就活プロフィールを開き、何も変えずに保存できる", async ({ request }) => {
    const token = await apiLogin(request, need("career_user"));
    const profile = await getJson(request, "/career-api/v1/career-profile/me", token);
    const resp = await request.patch("/career-api/v1/career-profile/me", {
      headers: tenantHeaders(token),
      data: {
        education: profile.education ?? "",
        employment_status: profile.employment_status ?? "",
        job_category: profile.job_category ?? "",
        qualification: profile.qualification ?? "",
      },
    });
    expect(resp.status(), await resp.text()).toBe(200);
  });

  test("S-70・S-71 受講者と運営の面談の一覧に移した面談が出る", async ({ request }) => {
    const f = facts();
    const p = need("interviewee");
    test.skip(!f.interviews?.length, "移した面談が無い");
    const learner = await apiLogin(request, p);
    const mine = listOf<{ id: string }>(await getJson(request, "/career-api/v1/interviews", learner));
    expect(mine.map((i) => i.id)).toContain(f.interviews![0]);
    const admin = await apiLogin(request, need("admin"));
    const all = listOf<{ id: string }>(await getJson(request, "/career-api/v1/interviews/all?limit=100", admin));
    expect(all.map((i) => i.id)).toContain(f.interviews![0]);
  });
});

/** 05 の残り（docs/db/05-support/test-spec-remaining.md）。**読むだけ**（フォルダの保存・メモの追加はしない）。 */
test.describe("05 サポート（残り）", () => {
  function rest() {
    test.skip(!REMAINING, "e2e/.personas.json に remaining が無い（prepare_e2e_users.py apply を流し直す）");
    return REMAINING!;
  }

  test("N-04 LINE の紐付けのある受講者の連携の状態が「連携済み」", async ({ request }) => {
    const token = await apiLogin(request, need("line_linked"));
    const status = await getJson(request, "/api/v1/tenant/line/status", token);
    test.skip(!status.enabled, "テナントの LINE 連携が無効（linked は常に false）");
    expect(status.linked).toBe(true);
  });

  test("B-05 受講者のライブラリに、全員向けで公開中のフォルダが出る", async ({ request }) => {
    const f = rest();
    test.skip(!f.open_folders.length, "全員向けで公開中のフォルダが無い");
    const token = await apiLogin(request, need("learner"));
    const ids = new Set(listOf<{ id: string }>(await getJson(request, "/api/v1/library/folders", token)).map((x) => x.id));
    for (const id of f.open_folders) expect(ids.has(id), `フォルダ ${id} が出ない`).toBe(true);
  });

  test("B-06 運営が移したフォルダを開ける（保存はしない）", async ({ request }) => {
    const f = rest();
    test.skip(!f.folders.length, "フォルダが無い");
    const token = await apiLogin(request, need("admin"));
    for (const id of f.folders) {
      const resp = await request.get(`/api/v1/tenant/library/folders/${id}`, { headers: tenantHeaders(token) });
      expect(resp.status(), await resp.text()).toBe(200);
    }
  });

  test("M-03 運営が会員の学習状況の画面で、移したメモを見られる", async ({ request }) => {
    const f = rest();
    test.skip(!f.notes.length, "運営メモが無い");
    const token = await apiLogin(request, need("admin"));
    const note = f.notes[0];
    const body = await getJson(request, `/api/v1/tenant/analytics/learners/${note.user_id}`, token);
    expect((body.admin_notes as Array<{ id: string }>).map((n) => n.id)).toContain(note.id);
  });
});
