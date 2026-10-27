/**
 * 02 コンテンツのテスト仕様（docs/db/02-content/test-spec.md）の E のケース。
 *
 * 移した講座・レッスン・テスト・課題・アンケート・ライブ・コースを、新アプリの API から確かめる。
 * 期待する ID は e2e/.personas.json の content（移行先の値）。旧との突き合わせは verify が受け持つ。
 */
import { expect, test } from "@playwright/test";
import { CONTENT, ENROLLMENT, apiLogin, getJson, listOf, persona, tenantHeaders } from "./helpers";

const TYPES = new Set(["video", "live", "text", "survey"]);

function need(name: string) {
  const p = persona(name);
  test.skip(!p, `役 ${name} の会員を用意していない`);
  return p!;
}

function facts() {
  test.skip(!CONTENT, "e2e/.personas.json に content が無い（prepare_e2e_users.py apply を流し直す）");
  return CONTENT!;
}

test.describe("02 コンテンツ", () => {
  test("C-06・P-03 受講者の探す画面に移したコースが出て、詳細を開ける", async ({ request }) => {
    const f = facts();
    test.skip(f.paths.length === 0, "公開中のコースが無い");
    const token = await apiLogin(request, need("learner"));
    const found = listOf<{ id: string }>(await getJson(request, "/api/v1/learning-paths/search?limit=100", token));
    const expected = new Set(f.paths);
    expect(found.some((p) => expected.has(p.id)), "移したコースが探す画面に出ない").toBe(true);
    const detail = await request.get(`/api/v1/learning-paths/${f.paths[0]}`, { headers: tenantHeaders(token) });
    expect(detail.status()).toBe(200);
  });

  test("C-07 運営が移した講座を開いて、何も変えずに保存できる", async ({ request }) => {
    const f = facts();
    test.skip(!f.course, "公開中の講座が無い");
    const token = await apiLogin(request, need("admin"));
    const course = await getJson(request, `/api/v1/courses/${f.course!.id}`, token);
    const resp = await request.patch(`/api/v1/courses/${f.course!.id}`, {
      headers: tenantHeaders(token),
      data: { title: course.title, status: course.status },
    });
    expect(resp.status(), await resp.text()).toBe(200);
  });

  test("L-06 講座のレッスンが新の 4 種で、公開中のものが出る", async ({ request }) => {
    const f = facts();
    test.skip(!f.course, "公開中の講座が無い");
    const token = await apiLogin(request, need("admin"));
    const lessons = listOf<{ type: string }>(await getJson(request, `/api/v1/courses/${f.course!.id}/lessons`, token));
    expect(lessons.length).toBeGreaterThan(0);
    expect(lessons.every((l) => TYPES.has(l.type)), "新が扱えない種別のレッスンがある").toBe(true);
  });

  test("L-07 運営が移したレッスン（旧のテストのユニット）を、画面と同じ項目で保存できる", async ({ request }) => {
    const f = facts();
    test.skip(!f.text_lesson, "旧のテストのユニットが無い");
    const token = await apiLogin(request, need("admin"));
    const lessons = listOf<{ id: string; title: string; type: string; status: string; sort_order: number; drip_delay_days?: number }>(
      await getJson(request, `/api/v1/courses/${f.text_lesson!.course_id}/lessons`, token),
    );
    const lesson = lessons.find((l) => l.id === f.text_lesson!.id)!;
    const resp = await request.patch(`/api/v1/courses/${f.text_lesson!.course_id}/lessons/${lesson.id}`, {
      headers: tenantHeaders(token),
      data: {
        title: lesson.title,
        type: lesson.type,
        status: lesson.status,
        sort_order: lesson.sort_order,
        drip_delay_days: lesson.drip_delay_days ?? 0,
      },
    });
    expect(resp.status(), await resp.text()).toBe(200);
  });

  test("Q-05 受講者がテストを開いて提出でき、採点される", async ({ request }) => {
    const f = facts();
    test.skip(!f.quiz_lesson, "受講登録のある講座のテストが無い");
    const token = await apiLogin(request, need("content_learner"));
    const quiz = await getJson(request, `/api/v1/lessons/${f.quiz_lesson!.id}/quiz`, token);
    const questions = (quiz.questions ?? []) as Array<{ id: string; type: string; options: Array<{ id: string }> }>;
    expect(questions.length).toBeGreaterThan(0);
    const answers = questions.map((q) =>
      q.type === "free_text"
        ? { question_id: q.id, text_answer: "回答" }
        : { question_id: q.id, selected_option_ids: q.options.slice(0, 1).map((o) => o.id) },
    );
    const resp = await request.post(`/api/v1/quizzes/${quiz.quiz.id}/submit`, { headers: tenantHeaders(token), data: { answers } });
    expect(resp.ok(), await resp.text()).toBe(true); // 201 Created
    const result = await resp.json();
    expect(typeof result.passed).toBe("boolean");
  });

  test("A-02 受講者が講座の課題の一覧で移した課題を見られる", async ({ request }) => {
    const f = facts();
    test.skip(!f.assignment_course, "受講登録のある講座の課題が無い");
    const token = await apiLogin(request, need("content_learner"));
    const items = listOf(await getJson(request, `/api/v1/courses/${f.assignment_course!.course_id}/learner-assignments`, token));
    expect(items.length).toBeGreaterThan(0);
  });

  test("S-03 受講者がアンケートのレッスンを開ける（削除済みの設問は出ない）", async ({ request }) => {
    const f = facts();
    // テストのある講座の受講者にアンケートが無ければ、アンケートに回答した受講者（区分 03）で開く
    const fallback = ENROLLMENT?.survey_open ? { lesson: ENROLLMENT.survey_open.lesson_id, who: "survey_responder" } : null;
    const target = f.survey_lesson ? { lesson: f.survey_lesson.id, who: "content_learner" } : fallback;
    test.skip(!target, "受講登録のある講座のアンケートが無い");
    const token = await apiLogin(request, need(target!.who));
    const survey = await getJson(request, `/api/v1/lessons/${target!.lesson}/learner-survey`, token);
    expect(Array.isArray(survey.questions)).toBe(true);
    expect(survey.questions.length).toBeGreaterThan(0);
  });

  test("Q-06 運営が移したテストと設問を開いて、何も変えずに保存できる（選択肢は送らない）", async ({ request }) => {
    const f = facts();
    test.skip(!f.quiz_lessons?.length, "移したテストが無い");
    test.setTimeout(300_000);
    const token = await apiLogin(request, need("admin"));
    const failures: string[] = [];
    for (const lessonId of f.quiz_lessons!) {
      const detail = await getJson(request, `/api/v1/quizzes/by-lesson/${lessonId}`, token);
      const q = detail.quiz;
      const resp = await request.patch(`/api/v1/quizzes/${q.id}`, {
        headers: tenantHeaders(token),
        data: { title: q.title, description: q.description, passing_score: q.passing_score, time_limit_sec: q.time_limit_sec },
      });
      if (!resp.ok()) failures.push(`テスト ${q.id}: ${resp.status()} ${(await resp.text()).slice(0, 120)}`);
      for (const x of detail.questions as Array<Record<string, unknown>>) {
        const r = await request.patch(`/api/v1/quizzes/questions/${x.id}`, {
          headers: tenantHeaders(token),
          data: { body: x.body, type: x.type, points: x.points, sort_order: x.sort_order, explanation: x.explanation,
                  category_id: x.category_id, skill_name: x.skill_name },
        });
        if (!r.ok()) failures.push(`設問 ${x.id}: ${r.status()} ${(await r.text()).slice(0, 120)}`);
      }
    }
    expect(failures, failures.slice(0, 10).join("\n")).toEqual([]);
  });

  test("LV-05・LV-06 カレンダーが開け、運営がライブのレッスンを保存しても開催回が残る", async ({ request }) => {
    const f = facts();
    const learner = await apiLogin(request, need("learner"));
    expect((await request.get("/api/v1/live/calendar", { headers: tenantHeaders(learner) })).status()).toBe(200);
    test.skip(!f.live_lesson, "開催回のあるライブが無い");
    const token = await apiLogin(request, need("admin"));
    const url = `/api/v1/live/lessons/${f.live_lesson!.id}/occurrences?include_canceled=true`;
    const before = listOf(await getJson(request, url, token)).length;
    const lessons = listOf<{ id: string; title: string }>(
      await getJson(request, `/api/v1/courses/${f.live_lesson!.course_id}/lessons`, token),
    );
    const lesson = lessons.find((l) => l.id === f.live_lesson!.id)!;
    const resp = await request.patch(`/api/v1/courses/${f.live_lesson!.course_id}/lessons/${lesson.id}`, {
      headers: tenantHeaders(token),
      data: { title: lesson.title },
    });
    expect(resp.status(), await resp.text()).toBe(200);
    expect(listOf(await getJson(request, url, token)).length).toBe(before);
  });

  test.fixme("V-03 受講者が動画のレッスンを再生できる（p-movie の URL の規則が決まるまで保留）", async () => {});
});
