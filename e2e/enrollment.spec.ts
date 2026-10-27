/**
 * 03 受講のテスト仕様（docs/db/03-enrollment/test-spec.md）の E のケース。
 *
 * 移した受講登録・学習の記録・修了証・受験・提出・アンケートの回答を、新アプリの API から確かめる。
 * 期待する値は e2e/.personas.json の enrollment（移行先の値）。旧との突き合わせは verify が受け持つ。
 * **読むだけ**（採点し直す・予約するなど、移したデータを書き換える操作はしない）。
 */
import { type APIRequestContext, expect, test } from "@playwright/test";
import { BILLING, ENROLLMENT, apiLogin, getJson, listOf, persona, tenantHeaders } from "./helpers";

function need(name: string) {
  const p = persona(name);
  test.skip(!p, `役 ${name} の会員を用意していない`);
  return p!;
}

function facts() {
  test.skip(!ENROLLMENT, "e2e/.personas.json に enrollment が無い（prepare_e2e_users.py apply を流し直す）");
  return ENROLLMENT!;
}

type Detail = { enrollment: { course_id: string; status: string }; progress: { is_completed: boolean } };

/** マイ講座の一覧を最後のページまで読む（1 回 50 件まで）。 */
async function allDetails(request: APIRequestContext, token: string): Promise<Detail[]> {
  const out: Detail[] = [];
  for (let offset = 0; ; offset += 50) {
    const body = await getJson(request, `/api/v1/enrollments/details?limit=50&offset=${offset}`, token);
    const page = listOf<Detail>(body);
    out.push(...page);
    if (page.length < 50 || out.length >= Number(body.total ?? 0)) return out;
  }
}

test.describe("03 受講", () => {
  test("E-06 マイ講座に受講中の講座が出て開ける。期限切れの講座は受講中にならない", async ({ request }) => {
    const f = facts();
    test.skip(!f.completer, "修了した有効な受講登録のある会員がいない");
    const token = await apiLogin(request, need("completer"));
    const details = await allDetails(request, token);
    const active = new Set(details.filter((d) => d.enrollment.status === "active").map((d) => d.enrollment.course_id));
    for (const id of f.completer!.active) {
      expect(active.has(id), `受講中の講座 ${id} がマイ講座に出ない`).toBe(true);
    }
    for (const id of f.completer!.expired) {
      expect(active.has(id), `期限切れの講座 ${id} が受講中で出る`).toBe(false);
    }
    const course = f.completer!.completed?.course_id ?? f.completer!.active[0];
    const lessons = await request.get(`/api/v1/courses/${course}/lessons`, { headers: tenantHeaders(token) });
    expect(lessons.status()).toBe(200);
  });

  test("R-04 修了した講座の進捗に、旧の完了の記録が出る", async ({ request }) => {
    const f = facts();
    test.skip(!f.completer?.completed, "修了した有効な受講登録のある会員がいない");
    const token = await apiLogin(request, need("completer"));
    const progress = await getJson(request, `/api/v1/progress/${f.completer!.completed!.course_id}`, token);
    expect(progress.completed_lessons, "完了したレッスンが 0 件").toBeGreaterThan(0);
    // 資料のレッスンは新では進捗の分母に入る（02 の Q3）ので、100% とは限らない
    const done = (progress.lesson_progresses as Array<{ completed: boolean; updated_at: string | null }>).filter((p) => p.completed);
    expect(done.every((p) => p.updated_at), "完了の記録に最終学習日時が無い").toBe(true);
  });

  test("P-02 コースの受講者のマイ講座に、コースの講座が受講中で出る", async ({ request }) => {
    test.skip(!BILLING?.path_courses?.length, "有効なコースの受講のある会員がいない（billing を流していない）");
    const token = await apiLogin(request, need("path_learner"));
    const details = await allDetails(request, token);
    const active = new Set(details.filter((d) => d.enrollment.status === "active").map((d) => d.enrollment.course_id));
    for (const id of BILLING!.path_courses!) {
      expect(active.has(id), `コースの講座 ${id} が受講中で出ない`).toBe(true);
    }
  });

  test("P-03 運営が会員のコースの割り当て一覧を開ける", async ({ request }) => {
    const f = facts();
    test.skip(!f.path_member, "コースの受講が 0 件（billing を流していない）");
    const token = await apiLogin(request, need("admin"));
    const body = await getJson(request, `/api/v1/tenant/users/${f.path_member!.id}/learning-paths`, token);
    expect(body.enrollments.length).toBeGreaterThan(0);
  });

  test("C-04 受講者の修了証の一覧に、旧で発行した修了証が旧の番号で出る", async ({ request }) => {
    const f = facts();
    test.skip(!f.certificates?.length, "修了証のある会員がいない");
    const token = await apiLogin(request, need("certificate_holder"));
    const mine = listOf<{ serial_no: number; serial_text: string }>(await getJson(request, "/api/v1/certificates", token));
    for (const cert of f.certificates!) {
      expect(mine.some((m) => m.serial_no === cert.serial_no && m.serial_text === cert.serial_text),
        `修了証 ${cert.serial_text} が出ない`).toBe(true);
    }
  });

  test("C-05 運営の修了証の台帳に旧の番号で出て、次の番号が重ならない", async ({ request }) => {
    const f = facts();
    test.skip(!f.settings, "修了証の設定が無い");
    const token = await apiLogin(request, need("admin"));
    const settings = await getJson(request, "/api/v1/tenant/certificates/settings", token);
    expect(settings.serial_format).toBe("date_prefixed");
    expect(settings.serial_next).toBeGreaterThan(f.settings!.max_serial ?? 0);
    const ledger = listOf<{ serial_text: string }>(await getJson(request, "/api/v1/tenant/certificates?limit=100", token));
    for (const cert of f.certificates ?? []) {
      expect(ledger.some((l) => l.serial_text === cert.serial_text), `台帳に ${cert.serial_text} が無い`).toBe(true);
    }
  });

  test("Q-03 受講者のテストの受験の履歴に、旧の受験が出る", async ({ request }) => {
    const f = facts();
    test.skip(!f.quiz, "受験した会員がいない");
    const token = await apiLogin(request, need("quiz_taker"));
    const attempts = listOf<{ score: number; max_score: number }>(
      await getJson(request, `/api/v1/quizzes/${f.quiz!.quiz_id}/attempts`, token));
    expect(attempts.length).toBe(Number(f.quiz!.attempts));
    expect(attempts.every((a) => a.score <= a.max_score)).toBe(true);
  });

  test("A-03 受講者が自分の提出と添削を見られる", async ({ request }) => {
    const f = facts();
    test.skip(!f.submission, "添削された提出のある会員がいない");
    const token = await apiLogin(request, need("submitter"));
    const body = await getJson(request, `/api/v1/submissions/${f.submission!.id}`, token);
    expect(body.submission.status).toBe(f.submission!.status);
    expect(body.feedback?.result).toBe(f.submission!.result);
  });

  test("A-04 運営が移した提出を採点の画面で開ける", async ({ request }) => {
    const f = facts();
    test.skip(!f.submission, "添削された提出が無い");
    const token = await apiLogin(request, need("admin"));
    const resp = await request.get(`/api/v1/assignments/submissions/${f.submission!.id}`, { headers: tenantHeaders(token) });
    expect(resp.status(), await resp.text()).toBe(200);
    const body = await resp.json();
    expect(body.feedback?.result).toBe(f.submission!.result);
  });

  test("S-04 回答済みの受講者がアンケートを開くと回答済みになる", async ({ request }) => {
    const f = facts();
    test.skip(!f.survey, "アンケートに回答した会員がいない");
    const token = await apiLogin(request, need("survey_responder"));
    const resp = await request.get(`/api/v1/lessons/${f.survey!.lesson_id}/learner-survey`, { headers: tenantHeaders(token) });
    expect(resp.status(), await resp.text()).toBe(200);
    expect((await resp.json()).already_submitted).toBe(true);
  });
});
