/**
 * 04 課金のテスト仕様（docs/db/04-billing/test-spec.md）の E のケース。
 *
 * 移したチケット・予約・決済・領収書・自動割当を、新アプリの API から確かめる。
 * 期待する値は e2e/.personas.json の billing（移行先の値）。旧との突き合わせは verify が受け持つ。
 * **読むだけ**（返金・領収書の発行・ルールの保存・予約のキャンセルなど、移したデータを書き換える操作はしない）。
 */
import { expect, test } from "@playwright/test";
import { BILLING, apiLogin, getJson, listOf, persona, tenantHeaders } from "./helpers";

function need(name: string) {
  const p = persona(name);
  test.skip(!p, `役 ${name} の会員を用意していない`);
  return p!;
}

function facts() {
  test.skip(!BILLING, "e2e/.personas.json に billing が無い（prepare_e2e_users.py apply を流し直す）");
  return BILLING!;
}

type Balance = { ticket_type_id: string; ticket_type_name: string; grants: Array<{ id: string }> };

test.describe("04 課金", () => {
  test("T-08 受講者と運営の画面に、移したチケットの残高が種別名つきで出る", async ({ request }) => {
    const f = facts();
    test.skip(!f.grants?.length, "チケットの残高のある会員がいない");
    const holder = need("ticket_holder");
    const token = await apiLogin(request, holder);
    const mine = listOf<Balance>(await getJson(request, "/api/v1/my-tickets", token));
    const ids = new Set(mine.flatMap((b) => b.grants.map((g) => g.id)));
    for (const g of f.grants!) expect(ids.has(g.id), `付与 ${g.id} が /my-tickets に出ない`).toBe(true);
    expect(mine.every((b) => b.ticket_type_name), "種別名が空").toBe(true);
    const admin = await apiLogin(request, need("admin"));
    const theirs = listOf<Balance>(await getJson(request, `/api/v1/tenant/users/${holder.id}/ticket-grants`, admin));
    expect(theirs.flatMap((b) => b.grants).length).toBe(f.grants!.length);
  });

  test("V-03 受講者の自分の予約に、移した予約が出る", async ({ request }) => {
    const f = facts();
    test.skip(!f.reservations?.length, "予約のある会員がいない");
    const token = await apiLogin(request, need("reserver"));
    const mine = listOf<{ id: string; status: string }>(await getJson(request, "/api/v1/live/my-reservations", token));
    const ids = new Set(mine.map((r) => r.id));
    for (const id of f.reservations!) expect(ids.has(id), `予約 ${id} が出ない`).toBe(true);
    expect(mine.every((r) => r.status !== "host_canceled")).toBe(true);
  });

  test("P-07 運営の収益の画面に移した決済が出る（返金は押さない）", async ({ request }) => {
    const f = facts();
    test.skip(!f.payments.length, "移した決済が無い");
    const token = await apiLogin(request, need("admin"));
    const list = listOf<{ id: string; status: string }>(await getJson(request, "/api/v1/tenant/payments?limit=100", token));
    const ids = new Set(list.map((p) => p.id));
    expect(f.payments.some((id) => ids.has(id)), "移した決済が一覧に出ない").toBe(true);
    expect(list.every((p) => p.status !== "pending" || !f.payments.includes(p.id)), "移した決済に pending がある").toBe(true);
  });

  test("R-03 受講者が移した領収書を開いて PDF を取れる（発行はしない）", async ({ request }) => {
    const f = facts();
    test.skip(!f.receipts?.length, "領収書のある会員がいない");
    const token = await apiLogin(request, need("receipt_holder"));
    const mine = listOf<{ id: string }>(await getJson(request, "/api/v1/my-receipts", token));
    const ids = new Set(mine.map((r) => r.id));
    for (const id of f.receipts!) expect(ids.has(id), `領収書 ${id} が出ない`).toBe(true);
    const pdf = await request.get(`/api/v1/my-receipts/${f.receipts![0]}/pdf`, { headers: tenantHeaders(token) });
    expect(pdf.status(), await pdf.text().catch(() => "")).toBe(200);
  });

  test("A-05 運営が自動割当の一覧で移したルールを開ける（保存はしない）", async ({ request }) => {
    const f = facts();
    test.skip(!f.rules.length, "自動割当のルールが無い");
    const token = await apiLogin(request, need("admin"));
    const rules = listOf<{ id: string }>(await getJson(request, "/api/v1/tenant/tag-auto-assign-rules", token));
    const ids = new Set(rules.map((r) => r.id));
    for (const id of f.rules) expect(ids.has(id), `ルール ${id} が出ない`).toBe(true);
  });
});
