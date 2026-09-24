"""オンデマンドのフェーズ4〜8（テスト・アンケート・課題・実績・教材）の変換テスト。

**DB を立てずに transform だけを通す。** ここで固定するのは、
**取り違えると気づかないまま誤データになるもの**に絞る。

- 採番キー（同じ ULID になると、どちらの行も移らない）
- 単位換算（分 → 秒）
- 正解・回答のパイプ区切り
- NULL と False の区別（「記録が無い」と「不正解だった」）
"""

from __future__ import annotations

import json
import logging
import unittest
from datetime import datetime

from migrator.config import Config, TenantConfig
from migrator.context import build_context
from migrator.db.target import TargetDatabase
from migrator.errors import MappingError
from migrator.steps.content import assignments as od_assignments
from migrator.steps.content import quizzes as od_quizzes
from migrator.steps.enrollment import results as od_results
from migrator.steps.content import surveys as od_surveys
from tests.fakes import FakeSource

CONFIG = Config(
    tenant=TenantConfig(legacy_id=12, slug="recademy", name="ReCADemy"),
    ulid_namespace="lw2-test",
    mappings={"role": {"values": {7: "learner"}}, "prefecture": {"values": {}}},
)


def make_ctx(tables: dict | None = None):
    ctx = build_context(
        CONFIG,
        FakeSource(tables or {}),
        TargetDatabase(None, dry_run=True),
        logging.getLogger("test"),
    )
    ctx.tenant_id.resolve("01ARZ3NDEKTSV4RRFFQ69G5FAV")
    return ctx


class QuizQuestionKeyTest(unittest.TestCase):
    """**採番キーに大問を含める。** 含めないと同じテスト内で衝突する。"""

    def test_same_question_in_two_sections_gets_two_ids(self) -> None:
        ctx = make_ctx()
        first = od_quizzes._question_ulid(ctx, sub_id=10, question_id=1, sort_no=1)
        second = od_quizzes._question_ulid(ctx, sub_id=11, question_id=1, sort_no=1)
        self.assertNotEqual(first, second)

    def test_same_row_is_stable_across_runs(self) -> None:
        """冪等性。**再実行で ID が変わると二重に入る。**"""
        a = od_quizzes._question_ulid(make_ctx(), sub_id=10, question_id=1, sort_no=1)
        b = od_quizzes._question_ulid(make_ctx(), sub_id=10, question_id=1, sort_no=1)
        self.assertEqual(a, b)


class QuizConversionTest(unittest.TestCase):
    def test_time_limit_is_minutes_to_seconds(self) -> None:
        """**旧は分、新は秒。** 換算を落とすと制限時間が 1/60 になる。"""
        self.assertEqual(od_quizzes._minutes_to_sec(30), 1800)

    def test_zero_time_limit_means_unlimited(self) -> None:
        self.assertIsNone(od_quizzes._minutes_to_sec(0))

    def test_correct_answers_are_pipe_separated(self) -> None:
        """単一選択は `"2"`、複数選択は `"2|5"`。"""
        self.assertEqual(od_quizzes._correct_numbers("2"), {2})
        self.assertEqual(od_quizzes._correct_numbers("2|5"), {2, 5})

    def test_free_text_answer_yields_no_option_numbers(self) -> None:
        """記述式の `answer` は期待する文字列そのもの。**番号として読まない。**"""
        self.assertEqual(od_quizzes._correct_numbers("/etc/passwd"), set())

    def test_unknown_question_type_stops(self) -> None:
        """**対応表に無い種別は止める。** 黙って単一選択に倒すと採点が変わる。"""
        with self.assertRaises(MappingError):
            od_quizzes._check_type({"question_type_id": 9, "question_id": 1})

    def test_options_are_expanded_up_to_selection_num(self) -> None:
        """**有効な数は `selection_num`。** 21列目以降は見ない。"""
        ctx = make_ctx()
        question = {
            "question_id": 1,
            "question_type_id": 2,
            "selection_num": 3,
            "answer": "1|3",
            "selection1": "あ",
            "selection2": "い",
            "selection3": "う",
            "selection4": "え",  # selection_num の外。展開しない
        }
        rows = [{"_sub": {"test_sub_id": 10, "test_id": 1}, "_question": question,
                 "question_id": 1, "sort_no": 1}]
        records = od_quizzes.QuizOptionsStep().transform(ctx, rows)
        self.assertEqual([r.values["body"] for r in records], ["あ", "い", "う"])
        self.assertEqual([r.values["is_correct"] for r in records], [True, False, True])

    def test_choice_question_without_options_is_skipped(self) -> None:
        """`selection_num = 0` は旧データの時点で選べない問題。選択肢を作らない。"""
        ctx = make_ctx()
        question = {"question_id": 1, "question_type_id": 1, "selection_num": 0, "answer": ""}
        rows = [{"_sub": {"test_sub_id": 10, "test_id": 1}, "_question": question,
                 "question_id": 1, "sort_no": 1}]
        self.assertEqual(od_quizzes.QuizOptionsStep().transform(ctx, rows), [])

    def test_rules_keep_category_only_for_ranged_questions(self) -> None:
        """**条件で引くのは `test_sub_type_id = 2` だけ。**

        固定出題（0 / 1）にカテゴリを持たせると、「カテゴリから引く条件」と区別が付かない。
        """
        ctx = make_ctx()
        rows = [
            {"test_sub_id": 1, "test_id": 1, "test_sub_type_id": 0, "question_cate_id": 5,
             "question_level_id": 2, "set_question_no": 3},
            {"test_sub_id": 2, "test_id": 1, "test_sub_type_id": 2, "question_cate_id": 5,
             "question_level_id": 2, "set_question_no": 3},
        ]
        fixed, ranged = od_quizzes.QuizQuestionRulesStep().transform(ctx, rows)
        self.assertIsNone(fixed.values["category_id"])
        self.assertIsNone(fixed.values["level"])
        self.assertIsNotNone(ranged.values["category_id"])
        self.assertEqual(ranged.values["level"], 2)


class SurveyCopyTest(unittest.TestCase):
    """**アンケートはユニットごとに複製する。** 同じ定義を複数ユニットが参照するため。"""

    def test_pages_differ_per_lesson(self) -> None:
        ctx = make_ctx()
        first = od_surveys.page_ulid(ctx, unit_id=100, page_id=7)
        second = od_surveys.page_ulid(ctx, unit_id=200, page_id=7)
        self.assertNotEqual(first, second)

    def test_unknown_question_kind_stops(self) -> None:
        with self.assertRaises(MappingError):
            od_surveys._kind({"question_type": 9, "enquete_question_id": 1})

    def test_free_text_question_has_no_options(self) -> None:
        ctx = make_ctx()
        rows = [{
            "_unit_id": 100,
            "enquete_question_id": 1,
            "enquete_page_id": 7,
            "question_type": 3,  # 記述
            "selection_num": 2,
            "selection1": "あ",
            "selection2": "い",
        }]
        self.assertEqual(od_surveys.SurveyQuestionOptionsStep().transform(ctx, rows), [])

    def test_long_page_title_becomes_null_not_truncated(self) -> None:
        """**切り捨てない。** 中途半端な文が残るより、空のほうが害が小さい。"""
        self.assertIsNone(od_surveys._fit("あ" * 201, 200))
        self.assertEqual(od_surveys._fit("あ" * 200, 200), "あ" * 200)


class AssignmentTest(unittest.TestCase):
    def test_allowed_types_fits_the_column(self) -> None:
        """`assignments.allowed_types` は varchar(100)。**桁拡大は要らない。**"""
        self.assertLessEqual(len(od_assignments.ALLOWED_TYPES), 100)

    def test_materials_are_renumbered_without_gaps(self) -> None:
        """**空いた枠を詰める。** `UNIQUE (assignment_id, sort_order)` があるため。"""
        ctx = make_ctx()
        row = {
            "report_id": 1,
            "report_save_file_name1": "a.pdf",
            "report_save_file_name2": None,   # 空き
            "report_save_file_name3": "c.pdf",
            "report_save_file_name4": None,
            "report_save_file_name5": None,
            "report_disp_file_name1": "資料A",
            "report_disp_file_name3": None,   # 表示名が無い
        }
        records = od_assignments.AssignmentMaterialsStep().transform(ctx, [row])
        self.assertEqual([r.values["sort_order"] for r in records], [1, 2])
        # 表示名が無ければ実ファイル名を出す（画面で名無しにしない）
        self.assertEqual([r.values["file_name"] for r in records], ["資料A", "c.pdf"])

    def test_video_url_only_when_pmovie_is_on(self) -> None:
        self.assertIsNone(
            od_assignments._video_url({"report_pmovie_chk": 0, "report_pmovie_token": "t"})
        )
        self.assertEqual(
            od_assignments._video_url({"report_pmovie_chk": 1, "report_pmovie_token": "t"}), "t"
        )


class ResultsTest(unittest.TestCase):
    def test_missing_grade_stays_null(self) -> None:
        """**NULL は「記録が無い」。** False に倒すと「不正解だった」になる。"""
        self.assertIsNone(od_results._flag(None))
        self.assertIs(od_results._flag(0), False)
        self.assertIs(od_results._flag(1), True)

    def test_scores_use_raw_not_percentage(self) -> None:
        """`sum_score` = 獲得点、`total_score` = 満点。**`test_score`（百分率）は使わない。**"""
        ctx = make_ctx()
        row = {
            "user_learning_test_id": 1,
            "_user_id": 101,
            "_test_id": 5,
            "sum_score": 8,
            "total_score": 10,
            "test_score": 80,
            "test_pass": 1,
            "finished_chk": 1,
            "test_time": 120,
            "test_start_time": None,
            "test_end_time": None,
        }
        record = od_results.QuizAttemptsStep().transform(ctx, [row])[0]
        self.assertEqual(record.values["score"], 8)
        self.assertEqual(record.values["max_score"], 10)
        self.assertEqual(record.values["passed"], True)

    def test_completion_comes_from_the_end_time_not_finished_chk(self) -> None:
        """**`finished_chk` は使わない。**

        同名の列は `user_learning_test_update`（中断・再開）のもので、lw2 は
        `user_learning_test` 側を一度も更新しない。ステージングでは全件 `0` のまま
        終了時刻と点数が入っており、**これを見ると全受験が「中断」になる**。
        """
        ctx = make_ctx()
        base = {
            "user_learning_test_id": 1, "_user_id": 101, "_test_id": 5,
            "sum_score": 8, "total_score": 10, "test_pass": 1, "finished_chk": 0,
            "test_time": None, "test_start_time": None,
        }
        done = od_results.QuizAttemptsStep().transform(
            ctx, [{**base, "test_end_time": datetime(2024, 1, 1, 9, 0)}]
        )[0]
        self.assertEqual(done.values["status"], "completed")
        self.assertIsNotNone(done.values["completed_at"])

        stopped = od_results.QuizAttemptsStep().transform(ctx, [{**base, "test_end_time": None}])[0]
        self.assertEqual(stopped.values["status"], "abandoned")
        self.assertIsNone(stopped.values["completed_at"])

    def test_selected_options_are_pipe_separated(self) -> None:
        self.assertEqual(od_results._numbers("2|5"), [2, 5])
        self.assertEqual(od_results._numbers("3"), [3])
        self.assertEqual(od_results._numbers(None), [])

    def test_unknown_reviewer_falls_back_to_proxy(self) -> None:
        """**添削者が分からない添削も移す。** 倒さないと本文と点数ごと落ちる（暫定対応）。"""
        ctx = make_ctx()
        proxy = ctx.ulid.for_row("user", od_results.PROXY_KEY)
        self.assertEqual(od_results._feedback_reviewer(ctx, {"evaluate_user_id": None}), proxy)
        self.assertEqual(od_results._feedback_reviewer(ctx, {"evaluate_user_id": 0}), proxy)
        self.assertNotEqual(od_results._feedback_reviewer(ctx, {"evaluate_user_id": 7}), proxy)

    def test_submission_reviewer_stays_null_when_unknown(self) -> None:
        """**提出側は NULL 可。** こちらは倒さない（倒す必要が無い）。"""
        self.assertIsNone(od_results._reviewer(make_ctx(), {"evaluate_user_id": None}))

    def test_question_comments_are_wrapped_as_json(self) -> None:
        raw = od_results._question_comments({"report_question_comment": "よくできました"})
        self.assertEqual(json.loads(raw), {"raw": "よくできました"})
        self.assertIsNone(od_results._question_comments({"report_question_comment": "  "}))


if __name__ == "__main__":
    unittest.main()
