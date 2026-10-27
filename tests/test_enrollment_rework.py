"""受講（区分 03）の見直しのテスト（docs/db/03-enrollment/migration-spec.md 0-2、rework-gap.md G1〜G9）。"""

from __future__ import annotations

import unittest
from datetime import date, datetime

from migrator.steps.enrollment import certificates as en_certificates
from migrator.steps.enrollment import learning_paths as en_paths
from migrator.steps.enrollment import progress as en_progress
from migrator.steps.enrollment import results as en_results
from migrator.steps.enrollment import rights as en_rights
from tests.test_enrollment import authority, make_ctx, unit_row


class CompletionTest(unittest.TestCase):
    """G1: 受講登録の修了日は旧の講座の修了日（Q1）。"""

    def test_time_is_the_last_unit_completion_of_that_day(self) -> None:
        rows = [
            {"user_id": 100, "lesson_id": 200, "lesson_complete_date": date(2021, 5, 1),
             "complete_date": datetime(2021, 5, 1, 9, 0)},
            {"user_id": 100, "lesson_id": 200, "lesson_complete_date": date(2021, 5, 1),
             "complete_date": datetime(2021, 5, 1, 18, 30)},
        ]
        # JST 18:30 → UTC 09:30
        self.assertEqual(en_rights.completions(rows), {(100, 200): datetime(2021, 5, 1, 9, 30)})

    def test_midnight_jst_without_a_unit_completion(self) -> None:
        rows = [{"user_id": 100, "lesson_id": 200, "lesson_complete_date": date(2021, 5, 1), "complete_date": None}]
        self.assertEqual(en_rights.completions(rows), {(100, 200): datetime(2021, 4, 30, 15, 0)})

    def test_latest_completion_wins(self) -> None:
        rows = [
            {"user_id": 100, "lesson_id": 200, "lesson_complete_date": date(2020, 1, 1), "complete_date": None},
            {"user_id": 100, "lesson_id": 200, "lesson_complete_date": date(2021, 1, 1), "complete_date": None},
        ]
        self.assertEqual(en_rights.completions(rows)[(100, 200)].date(), date(2020, 12, 31))

    def test_enrollment_gets_the_completion(self) -> None:
        ctx = make_ctx({
            "payment_item_lesson_authority": [authority()],
            "user_learning_lesson": [{"user_id": 100, "lesson_id": 200,
                                      "lesson_complete_date": date(2019, 6, 1), "complete_date": None}],
        })
        step = en_rights.EnrollmentRightsStep()
        [rec] = step.transform(ctx, step.extract(ctx))
        # 受講開始（2020-01-01）より前でも作り替えない（Q2）
        self.assertEqual(rec.values["completed_at"], datetime(2019, 5, 31, 15, 0))

    def test_no_completion_stays_null(self) -> None:
        ctx = make_ctx({"payment_item_lesson_authority": [authority()]})
        step = en_rights.EnrollmentRightsStep()
        [rec] = step.transform(ctx, step.extract(ctx))
        self.assertIsNone(rec.values["completed_at"])


class DirectGrantTest(unittest.TestCase):
    """G2: 直接付与もある組は、コースの取り消しで直接付与の状態に戻る（Q3）。"""

    def _records(self, rows, direct):
        ctx = make_ctx({"payment_item_lesson_authority": direct})
        step = en_paths.LearningPathEnrollmentCoursesStep()
        step._direct = en_paths.direct_grants(direct)
        return step.transform(ctx, rows)

    def test_prev_is_recorded_with_the_direct_grant(self) -> None:
        direct = [authority(authority_id=2, authority_key="", item_id=None,
                            authority_end_date=date(2030, 1, 1))]
        [rec] = self._records([authority()], direct)
        self.assertTrue(rec.values["prev_recorded"])
        self.assertEqual(rec.values["prev_status"], "active")
        self.assertEqual(rec.values["prev_expires_at"], datetime(2030, 1, 1, 14, 59, 59))

    def test_no_direct_grant_keeps_defaults(self) -> None:
        [rec] = self._records([authority()], [])
        self.assertFalse(rec.values["prev_recorded"])
        self.assertIsNone(rec.values["prev_status"])

    def test_deleted_direct_grant_is_not_a_fallback(self) -> None:
        direct = [authority(authority_id=2, authority_key="", item_id=None, del_chk=1)]
        [rec] = self._records([authority()], direct)
        self.assertFalse(rec.values["prev_recorded"])


class ProgressReworkTest(unittest.TestCase):
    """G3〜G5: 学習の記録。"""

    def _extract(self, units, lessons, answers=(), unit_defs=None):
        ctx = make_ctx({
            "user_learning_unit": units,
            "user_learning_lesson": lessons,
            "unit": unit_defs or [{"unit_id": 300, "unit_type_id": 2, "update_date": datetime(2023, 3, 3)}],
            "enquete_answer": list(answers),
        })
        step = en_progress.LessonProgressStep()
        rows = step.extract(ctx)
        return step, ctx, rows

    def test_updated_at_is_the_later_of_update_and_completion(self) -> None:
        step, ctx, rows = self._extract(
            [unit_row(update_date=datetime(2021, 5, 1, 9), complete_date=datetime(2021, 6, 1, 9))],
            [{"user_learning_lesson_id": 10, "user_id": 100, "del_chk": 0}])
        [rec] = step.transform(ctx, rows)
        self.assertEqual(rec.values["updated_at"], datetime(2021, 6, 1, 0, 0))

    def test_rows_under_a_removed_learning_record_are_listed(self) -> None:
        """**管理者が削除した受講の記録の下の行は移さない**（新で完了に数えられる。Q5）。"""
        step, ctx, rows = self._extract(
            [unit_row()], [{"user_learning_lesson_id": 10, "user_id": 100, "del_chk": 1}])
        self.assertEqual(rows, [])
        [dropped] = step._take_dropped()
        self.assertEqual((dropped.table, dropped.reason), ("lesson_progress", "受け皿なし"))

    def test_answered_survey_rows_are_kept(self) -> None:
        """アンケートに回答した記録は残す（Q12）。"""
        _, _, rows = self._extract(
            [unit_row()], [{"user_learning_lesson_id": 10, "user_id": 100, "del_chk": 1}],
            answers=[{"entity_type_id": 2, "entity_id": 1, "del_chk": 0}])
        self.assertEqual(len(rows), 1)

    def test_live_learning_record_wins_a_duplicate(self) -> None:
        step, ctx, rows = self._extract(
            [unit_row(user_learning_unit_id=1, user_learning_lesson_id=10, progress_status=1,
                      update_date=datetime(2020, 1, 1)),
             unit_row(user_learning_unit_id=2, user_learning_lesson_id=11, progress_status=3,
                      update_date=datetime(2022, 1, 1))],
            [{"user_learning_lesson_id": 10, "user_id": 100, "del_chk": 0},
             {"user_learning_lesson_id": 11, "user_id": 100, "del_chk": 1}],
            answers=[{"entity_type_id": 2, "entity_id": 2, "del_chk": 0}])
        [rec] = step.transform(ctx, rows)
        self.assertEqual(rec.values["progress_status"], "quiz:1")

    def test_deleted_unit_uses_the_unit_deletion_time(self) -> None:
        step, ctx, rows = self._extract(
            [unit_row(del_chk=1, update_date=datetime(2021, 5, 1, 12))],
            [{"user_learning_lesson_id": 10, "user_id": 100, "del_chk": 0}])
        [rec] = step.transform(ctx, rows)
        self.assertEqual(rec.values["deleted_at"], datetime(2023, 3, 2, 15, 0))


class CertificateSerialTest(unittest.TestCase):
    """G6: 修了証の番号の文字列（Q7）。"""

    def test_serial_text_is_no_date_number(self) -> None:
        self.assertEqual(en_certificates.serial_text(6, datetime(2025, 11, 10, 23, 30)), "No.202511106")

    def test_settings_use_the_date_prefixed_format(self) -> None:
        ctx = make_ctx({"config_certificate": [], "certificate_no": [
            {"tenant_id": 12, "certificate_no": 7, "regist_date": datetime(2025, 1, 1)}]})
        step = en_certificates.CertificateSettingsStep()
        [rec] = step.transform(ctx, step.extract(ctx))
        self.assertEqual(rec.values["serial_format"], "date_prefixed")


def report(**over):
    row = {"user_learning_report_id": 1, "user_learning_unit_id": 50, "submit_date": datetime(2022, 1, 1),
           "evaluate_date": None, "_latest": True, "_progress_status": 2, "_learning_status": 0}
    row.update(over)
    return row


class SubmissionStatusTest(unittest.TestCase):
    """G7・G8: 提出の状態と添削の結果（Q10）。"""

    def test_latest_submission_follows_the_unit_status(self) -> None:
        cases = {2: "submitted", 3: "graded", 4: "returned", 5: "under_review"}
        for legacy, expected in cases.items():
            self.assertEqual(en_results.submission_status(report(_progress_status=legacy)), expected)

    def test_evaluated_but_waiting_is_graded(self) -> None:
        """評価した日時があるのに評価待のまま（旧データ）は採点待ちに戻さない（A-02）。"""
        row = report(evaluate_date=datetime(2017, 9, 8), _learning_status=1)
        self.assertEqual(en_results.submission_status(row), "graded")
        self.assertEqual(en_results.feedback_result(row), "pass")

    def test_older_evaluated_submission_is_returned(self) -> None:
        old = report(_latest=False, evaluate_date=datetime(2022, 1, 2))
        self.assertEqual(en_results.submission_status(old), "returned")
        self.assertEqual(en_results.feedback_result(old), "needs_resubmission")

    def test_feedback_result_follows_the_learning_status(self) -> None:
        graded = dict(_progress_status=3, evaluate_date=datetime(2022, 1, 2))
        self.assertEqual(en_results.feedback_result(report(**graded, _learning_status=1)), "pass")
        self.assertEqual(en_results.feedback_result(report(**graded, _learning_status=0)), "fail")
        self.assertEqual(en_results.feedback_result(report(_progress_status=4)), "needs_resubmission")


if __name__ == "__main__":
    unittest.main()
