"""区分 02 の見直し（docs/db/02-content/migration-spec.md 0-3）のテスト。"""

from __future__ import annotations

import json
import unittest
from datetime import datetime

from migrator.steps.content import lessons
from tests.test_new_receptacles import make_ctx, unit


def lecture(unit_id, *, pmovie=0, token="", path=None):
    return {"lecture_id": unit_id * 10, "unit_id": unit_id, "pmovie_chk": pmovie, "pmovie_token": token,
            "_path": {"pc_path": path} if path is not None else None}


class LessonTypeTest(unittest.TestCase):
    def test_types_fit_the_four_new_kinds(self) -> None:
        """**新が扱える 4 種に収める**（Q2）。旧の種別は settings に残す。"""
        self.assertEqual(lessons.new_type("quiz", False), "text")
        self.assertEqual(lessons.new_type("assignment", False), "text")
        self.assertEqual(lessons.new_type("document", False), "text")
        self.assertEqual(lessons.new_type("survey", False), "survey")
        self.assertEqual(lessons.new_type("video", True), "video")
        # 再生できない講義（旧サーバーの教材・PDF など）は text（Q6）
        self.assertEqual(lessons.new_type("video", False), "text")

    def test_playable_only_pmovie_youtube_vimeo(self) -> None:
        self.assertTrue(lessons.is_playable(lecture(1, pmovie=1, token="a" * 40)))
        self.assertTrue(lessons.is_playable(lecture(1, path="https://youtu.be/abc")))
        self.assertFalse(lessons.is_playable(lecture(1, path="https://rome.learning-ware.jp/lesson/1/index.html")))
        self.assertFalse(lessons.is_playable(lecture(1, path="./contents/10/lesson/a.pdf")))
        self.assertFalse(lessons.is_playable(lecture(1, path="")))


class LessonsStepTest(unittest.TestCase):
    def transform(self, rows, lectures):
        ctx = make_ctx({"unit": rows, "lecture": lectures})
        step = lessons.LessonsStep()
        for row in rows:  # extract の代わり（偽物の旧 DB は join を解かないので、講義を直接付ける）
            row["_lecture"] = next((lec for lec in lectures if lec["unit_id"] == row["unit_id"]), None)
        return {r.values["unit_id"]: r.values for r in step.transform(ctx, rows)}

    def test_quiz_unit_is_text_with_legacy_type(self) -> None:
        out = self.transform([unit(1, 1, type_id=2)], [])
        self.assertEqual(out[1]["type"], "text")
        self.assertEqual(json.loads(out[1]["settings"])["legacy_unit_type"], "quiz")

    def test_non_playable_lecture_carries_url_in_body(self) -> None:
        """**再生できない講義の配信先は本文に載せる**（Q6）。動画の行は作らない。"""
        row = {**unit(2, 1), "detail": "説明"}
        out = self.transform([row], [lecture(2, path="https://rome.learning-ware.jp/lesson/9/a.html")])
        self.assertEqual(out[2]["type"], "text")
        self.assertEqual(out[2]["description"], "説明\n\nhttps://rome.learning-ware.jp/lesson/9/a.html")

    def test_order_is_renumbered_without_ties(self) -> None:
        """**`sort_no` が重なっても旧の並び（`unit_id` 順）の通し番号**（Q4）。"""
        out = self.transform([unit(3, 5), unit(2, 5), unit(1, 9)], [])
        self.assertEqual([out[k]["sort_order"] for k in (2, 3, 1)], [1, 2, 3])

    def test_free_unit_is_preview(self) -> None:
        """旧は有料でないユニットを購入の権限なしで開けた（Q17）。"""
        out = self.transform([{**unit(1, 1, type_id=2), "payment_unit": 0},
                              {**unit(2, 2, type_id=2), "payment_unit": 1}], [])
        self.assertEqual((out[1]["is_preview"], out[2]["is_preview"]), (True, False))


class VideoLessonsTest(unittest.TestCase):
    def test_only_playable_lectures_get_video_rows(self) -> None:
        ctx = make_ctx({"lecture": [lecture(1, pmovie=1, token="a" * 40), lecture(2, path="./x.pdf")],
                        "lecture_path": []})
        rows = lessons.VideoLessonsStep().extract(ctx)
        self.assertEqual([r["unit_id"] for r in rows], [1])



from migrator.steps.content import quizzes as qz  # noqa: E402


def q(qid, *, cate=1, level=None, type_id=1, num=3, answer="1", deleted=0):
    return {"question_id": qid, "question_cate_id": cate, "question_level_id": level, "question_type_id": type_id,
            "selection_num": num, "answer": answer, "del_chk": deleted}


def sub(sid, test_id, sub_type, n=0, sort=1, cate=None, level=None):
    return {"test_sub_id": sid, "test_id": test_id, "test_sub_type_id": sub_type, "set_question_no": n,
            "sort_no": sort, "question_cate_id": cate, "question_level_id": level, "score_per_question": 5}


def link(lid, sid, qid, sort):
    return {"test_sub_question_id": lid, "test_sub_id": sid, "question_id": qid, "sort_no": sort}


class PlanQuestionsTest(unittest.TestCase):
    QUESTIONS = {i: q(i) for i in range(1, 7)}

    def test_fixed_order_takes_first_n(self) -> None:
        """**固定出題は旧どおり先頭の N 問だけ**（Q10）。後ろは一覧に出す。"""
        plan, dropped = qz.plan_questions([sub(1, 10, 0, n=2)], [link(101, 1, 3, 3), link(102, 1, 1, 1), link(103, 1, 2, 2)],
                                          self.QUESTIONS)
        self.assertEqual([r["question_id"] for r in plan[10]], [1, 2])
        self.assertEqual([d[1] for d in dropped], ["101"])

    def test_random_from_fixed_takes_all(self) -> None:
        plan, _ = qz.plan_questions([sub(1, 10, 1, n=1)], [link(101, 1, 1, 1), link(102, 1, 2, 2)], self.QUESTIONS)
        self.assertEqual(len(plan[10]), 2)

    def test_category_range_is_expanded(self) -> None:
        """**カテゴリからのランダム出題は候補をすべて設問にする**（Q8）。削除済みの問題は除く。"""
        questions = {**self.QUESTIONS, 7: q(7, cate=2), 8: q(8, cate=2, deleted=1), 9: q(9, cate=3)}
        plan, _ = qz.plan_questions([sub(1, 10, 2, n=1, cate=2)], [], questions)
        self.assertEqual([r["question_id"] for r in plan[10]], [7])

    def test_unscorable_questions_are_listed(self) -> None:
        """**採点できない設問は移さない**（Q11）。選択肢 0 件・正解の番号が範囲外。"""
        questions = {1: q(1, num=0), 2: q(2, answer="5"), 3: q(3), 4: q(4, type_id=3, num=0, answer="はい")}
        plan, dropped = qz.plan_questions([sub(1, 10, 1)], [link(i, 1, i, i) for i in range(1, 5)], questions)
        self.assertEqual([r["question_id"] for r in plan[10]], [3, 4])
        self.assertEqual(sorted(d[1] for d in dropped), ["1", "2"])

    def test_order_is_continuous_across_subs(self) -> None:
        plan, _ = qz.plan_questions([sub(2, 10, 1, sort=2), sub(1, 10, 1, sort=1)],
                                    [link(201, 2, 3, 1), link(101, 1, 1, 1), link(102, 1, 2, 2)], self.QUESTIONS)
        self.assertEqual([(r["question_id"], r["_sort"]) for r in plan[10]], [(1, 1), (2, 2), (3, 3)])

    def test_deleted_subs_and_links_are_not_asked(self) -> None:
        """**削除済みの出題条件・設問は旧で出ない**ので入れない（一覧に出す）。"""
        deleted_sub = {**sub(2, 10, 1, sort=2), "del_chk": 1}
        links = [link(101, 1, 1, 1), {**link(102, 1, 2, 2), "del_chk": 1}, link(201, 2, 3, 1)]
        plan, dropped = qz.plan_questions([sub(1, 10, 1), deleted_sub], links, self.QUESTIONS)
        self.assertEqual([r["question_id"] for r in plan[10]], [1])
        self.assertEqual(sorted(d[1] for d in dropped), ["102", "201"])


class QuizzesStepTest(unittest.TestCase):
    def test_tests_without_questions_or_on_other_units_are_listed(self) -> None:
        """**設問が 1 件も無いテスト・テスト以外のユニットのテストは移さない**（Q8）。"""
        tables = {
            "unit": [unit(1, 1, type_id=2), unit(2, 2, type_id=2), unit(3, 3, type_id=3)],
            "test": [{"test_id": 10, "unit_id": 1}, {"test_id": 20, "unit_id": 2}, {"test_id": 30, "unit_id": 3}],
            "test_sub": [sub(1, 10, 1), sub(2, 30, 1)],
            "test_sub_question": [link(101, 1, 1, 1), link(201, 2, 1, 1)],
            "question": [q(1)],
        }
        ctx = make_ctx(tables)
        step = qz.QuizzesStep()
        kept = step.extract(ctx)
        self.assertEqual([r["test_id"] for r in kept], [10])
        self.assertEqual(sorted(v.key for v in step._take_dropped()), ["20", "30"])

    def test_title_is_the_unit_title(self) -> None:
        """**テストの題はユニット名**（02 の Q-06）。旧 `test` に題が無く、空だと新で運営が保存できない。"""
        tables = {
            "unit": [{**unit(1, 1, type_id=2), "title": " 確認テスト "}],
            "test": [{"test_id": 10, "unit_id": 1}],
            "test_sub": [sub(1, 10, 1)],
            "test_sub_question": [link(101, 1, 1, 1)],
            "question": [q(1)],
        }
        ctx = make_ctx(tables)
        step = qz.QuizzesStep()
        [rec] = step.transform(ctx, step.extract(ctx))
        self.assertEqual(rec.values["title"], "確認テスト")


class SurveyOrderTest(unittest.TestCase):
    def test_questions_are_numbered_across_pages(self) -> None:
        """**設問の並びはページをまたいだ通し番号**（Q13）。新はページを読まない。"""
        from migrator.steps.content import surveys

        tables = {
            "unit": [{"unit_id": 1, "lesson_id": 100, "unit_type_id": 3, "enquete_id": 7, "del_chk": 0}],
            "enquete": [{"enquete_id": 7, "del_chk": 0}],
            "enquete_page": [{"enquete_page_id": 2, "enquete_id": 7}, {"enquete_page_id": 1, "enquete_id": 7}],
            "enquete_question": [
                {"enquete_question_id": 11, "enquete_page_id": 2, "sort_no": 1},
                {"enquete_question_id": 12, "enquete_page_id": 1, "sort_no": 2},
                {"enquete_question_id": 13, "enquete_page_id": 1, "sort_no": 1},
            ],
        }
        rows = surveys.SurveyQuestionsStep().extract(make_ctx(tables))
        self.assertEqual([(r["enquete_question_id"], r["_order"]) for r in rows], [(13, 1), (12, 2), (11, 3)])


class OccurrenceTest(unittest.TestCase):
    def test_deleted_occurrences_are_listed_not_migrated(self) -> None:
        """**削除済みの開催回は移さない**（Q14）。新は開催回の deleted_at を読まない。"""
        from migrator.steps.content import live_lessons as lv

        dates = [{"live_lesson_date_id": 1, "live_lesson_id": 5, "del_chk": 0},
                 {"live_lesson_date_id": 2, "live_lesson_id": 5, "del_chk": 1}]
        ctx = make_ctx({"live_lesson_date": dates, "live_lesson": [{"live_lesson_id": 5}]})
        step = lv.OccurrencesStep()
        rows = step.extract(ctx)
        self.assertEqual([r["live_lesson_date_id"] for r in rows], [1])
        self.assertEqual([v.key for v in step._take_dropped()], ["2"])


class SurveyDeletedTest(unittest.TestCase):
    def test_deleted_questions_and_pages_get_deleted_at(self) -> None:
        """**削除済みの設問・ページも移し、deleted_at で表す**（2026-10-26。新はこれで除く）。"""
        from migrator.steps.content import surveys

        tables = {
            "unit": [{"unit_id": 1, "lesson_id": 100, "unit_type_id": 3, "enquete_id": 7, "del_chk": 0}],
            "enquete": [{"enquete_id": 7, "del_chk": 0}],
            "enquete_page": [
                {"enquete_page_id": 1, "enquete_id": 7, "del_chk": 0},
                {"enquete_page_id": 2, "enquete_id": 7, "del_chk": 1, "update_date": datetime(2021, 1, 1)},
            ],
            "enquete_question": [
                {"enquete_question_id": 11, "enquete_page_id": 1, "sort_no": 1, "question_type": 3, "del_chk": 0},
                {"enquete_question_id": 12, "enquete_page_id": 1, "sort_no": 2, "question_type": 3, "del_chk": 1,
                 "update_date": datetime(2022, 1, 1)},
                {"enquete_question_id": 13, "enquete_page_id": 2, "sort_no": 1, "question_type": 3, "del_chk": 0},
            ],
        }
        ctx = make_ctx(tables)
        step = surveys.SurveyQuestionsStep()
        out = {r.source_key: r.values["deleted_at"] for r in step.transform(ctx, step.extract(ctx))}
        self.assertIsNone(out[11])
        self.assertIsNotNone(out[12])
        self.assertIsNotNone(out[13])  # 削除済みのページの設問


if __name__ == "__main__":
    unittest.main()
