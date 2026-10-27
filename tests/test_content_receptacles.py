"""school-launcher が 2026-10 に足した、コンテンツの受け皿への変換テスト（2026-10-22）。

**DB を立てずに extract / transform だけを通す。** 固定するのは、取り違えると気づかないまま
誤データになるもの。

- 販売停止の講座が `archived` になること（新は講座の下書きをやめた）
- 削除済みのレッスンに `deleted_at` が入ること（新アプリは `deleted_at IS NULL` で絞る）
- 動画の置き場所の種類（p-movie・YouTube・Vimeo・それ以外）
- ライブの予約・キャンセルの期限（キャンセルを日数で表せないときは NULL）
- コース（旧の講座の販売商品）の期間・状態・一覧への表示と、削除済みの結び付きを入れないこと
"""

from __future__ import annotations

import json
import logging
import unittest
from datetime import datetime

from migrator.config import Config, TenantConfig
from migrator.context import build_context
from migrator.db.target import TargetDatabase
from migrator.steps.content import courses, learning_paths, lessons, live_lessons
from tests.fakes import FakeSource

CONFIG = Config(
    tenant=TenantConfig(legacy_id=12, slug="recademy", name="ReCADemy"),
    ulid_namespace="lw2-test",
    mappings={"role": {"values": {7: "learner"}}, "prefecture": {"values": {}}},
)


def make_ctx(tables: dict | None = None):
    ctx = build_context(
        CONFIG, FakeSource(tables or {}), TargetDatabase(None, dry_run=True), logging.getLogger("test")
    )
    ctx.tenant_id.resolve("01ARZ3NDEKTSV4RRFFQ69G5FAV")
    return ctx


class CourseStatusTest(unittest.TestCase):
    def test_stopped_sale_is_archived(self) -> None:
        """**`draft` にしない。** 新は講座を画面から公開にできないので、運営が戻せなくなる。"""
        self.assertEqual(courses._status_of({"sales_status": 0, "del_chk": 0}), "archived")
        self.assertEqual(courses._status_of({"sales_status": 1, "del_chk": 0}), "published")
        # 削除済みも `archived`（2026-10-26 決定。`deleted` は新で受講者に見え、編集も 400）
        self.assertEqual(courses._status_of({"sales_status": 0, "del_chk": 1}), "archived")

    def test_sales_status_is_kept_in_settings(self) -> None:
        self.assertEqual(json.loads(courses._settings({"sales_status": 0}))["sales_status"], 0)


class TenantCourseCategoryTest(unittest.TestCase):
    def test_deleted_category_is_deprecated(self) -> None:
        ctx = make_ctx()
        rows = [
            {"lesson_cate_id": 1, "lesson_cate_name": "CAD", "sort_no": 2, "del_chk": 0},
            {"lesson_cate_id": 2, "lesson_cate_name": "BIM", "sort_no": 3, "del_chk": 1,
             "update_date": datetime(2024, 1, 1)},
        ]
        alive, deleted = (r.values for r in courses.TenantCourseCategoriesStep().transform(ctx, rows))
        self.assertIsNone(alive["deprecated_at"])
        self.assertIsNotNone(deleted["deprecated_at"])
        self.assertEqual(alive["id"], ctx.ulid.for_row("tenant_course_category", 1))

    def test_link_points_at_the_tenant_category(self) -> None:
        ctx = make_ctx()
        (link,) = courses.CourseCategoryLinksStep().transform(ctx, [{"lesson_id": 5, "lesson_cate_id": 1}])
        self.assertEqual(link.values["category_id"], ctx.ulid.for_row("tenant_course_category", 1))
        self.assertEqual(link.values["course_id"], ctx.ulid.for_row("lesson", 5))


class LessonDeletedAtTest(unittest.TestCase):
    def _unit(self, **over):
        row = {"unit_id": 1, "lesson_id": 9, "unit_type_id": 1, "sort_no": 1, "title": "動画",
               "del_chk": 0, "update_date": datetime(2024, 5, 1), "regist_date": datetime(2020, 1, 1)}
        row.update(over)
        return row

    def test_deleted_unit_has_deleted_at(self) -> None:
        """**status='deleted' だけでは新の画面に出る。**"""
        ctx = make_ctx()
        alive, deleted = lessons.LessonsStep().transform(ctx, [self._unit(), self._unit(unit_id=2, del_chk=1)])
        self.assertIsNone(alive.values["deleted_at"])
        self.assertIsNotNone(deleted.values["deleted_at"])
        self.assertEqual(deleted.values["status"], "deleted")


class VideoSourceTest(unittest.TestCase):
    def source(self, pmovie=0, token=None, path=None):
        return lessons._video_source({"pmovie_chk": pmovie, "pmovie_token": token, "_path": {"pc_path": path}})

    def test_pmovie_token_is_pmovie(self) -> None:
        self.assertEqual(self.source(pmovie=1, token="7384a5c2dbe6"), "pmovie")

    def test_embed_hosts(self) -> None:
        self.assertEqual(self.source(path="https://youtu.be/abcdefghijk"), "youtube")
        self.assertEqual(self.source(path="https://www.youtube.com/watch?v=abcdefghijk"), "youtube")
        self.assertEqual(self.source(path="https://vimeo.com/123"), "vimeo")

    def test_everything_else_stays_storage(self) -> None:
        """旧の自前サーバーの URL や、パスだけの値は既定のまま。"""
        self.assertEqual(self.source(path="https://rome.learning-ware.jp/a.mp4"), "storage")
        self.assertEqual(self.source(path="yougo/a.mp4"), "storage")
        self.assertEqual(self.source(pmovie=1, token="", path=None), "storage")


class ReservationPolicyTest(unittest.TestCase):
    def test_days_are_copied(self) -> None:
        ctx = make_ctx()
        row = {"live_lesson_id": 3, "reserve_start_day": 60, "reserve_end_day": 3, "reserve_end_time": 0,
               "_cancel": {"ticket_cancel_chk": 1, "ticket_cancel_day": 1, "ticket_cancel_time": 0}}
        (policy,) = live_lessons.ReservationPoliciesStep().transform(ctx, [row])
        self.assertEqual(policy.values["lesson_id"], ctx.ulid.for_row("live_lesson", 3))
        self.assertEqual(
            (policy.values["reserve_open_days_before"], policy.values["reserve_close_days_before"],
             policy.values["reserve_close_hours_before"], policy.values["cancel_days_before"]),
            (60, 3, 0, 1),
        )

    def test_cancel_that_days_cannot_express_is_null(self) -> None:
        """時間つきの期限と、キャンセル不可は日数で表せない。**0 に倒さない**（0 は「開始まで可」）。"""
        self.assertIsNone(live_lessons.cancel_days_before(
            {"ticket_cancel_chk": 1, "ticket_cancel_day": 1, "ticket_cancel_time": 3}))
        self.assertIsNone(live_lessons.cancel_days_before({"ticket_cancel_chk": 0}))
        self.assertIsNone(live_lessons.cancel_days_before({}))


class LearningPathTest(unittest.TestCase):
    def test_access_period_units(self) -> None:
        """週は 7 日、年は 12 ヶ月に直す。期限なしと自動継続（種類が NULL）は無期限。"""
        period = learning_paths.access_period
        self.assertEqual(period({"manual_term": 30, "manual_term_type": 0}), (30, "day"))
        self.assertEqual(period({"manual_term": 2, "manual_term_type": 1}), (14, "day"))
        self.assertEqual(period({"manual_term": 6, "manual_term_type": 2}), (6, "month"))
        self.assertEqual(period({"manual_term": 1, "manual_term_type": 3}), (12, "month"))
        self.assertEqual(period({"manual_term": 1, "manual_term_type": 4}), (None, None))
        self.assertEqual(period({"manual_term": 100, "manual_term_type": 3, "no_limit_chk": 1}), (None, None))
        self.assertEqual(period({"manual_term": None, "manual_term_type": None}), (None, None))

    def test_missing_term_is_not_filled_in(self) -> None:
        """数が無いのに種類があるものは作り替えない（CHECK に当たって一覧に出る）。"""
        self.assertEqual(learning_paths.access_period({"manual_term": 0, "manual_term_type": 2}), (None, "month"))

    def test_status_and_listing(self) -> None:
        ctx = make_ctx()
        rows = [
            {"item_id": 1, "item_name": "A", "price": 1000, "valid_chk": 1, "display_chk": 1, "del_chk": 0,
             "remote_chk": 1, "extension_price": 500},
            {"item_id": 2, "item_name": "B", "price": 0, "valid_chk": 0, "display_chk": 0, "del_chk": 0},
            {"item_id": 3, "item_name": "C", "price": 0, "valid_chk": 1, "display_chk": 2, "del_chk": 1},
        ]
        a, b, c = (r.values for r in learning_paths.LearningPathsStep().transform(ctx, rows))
        self.assertEqual((a["status"], a["listed"], a["remote_pc_enabled"], a["extension_fee"]),
                         ("published", True, True, 500))
        self.assertEqual((b["status"], b["listed"], b["extension_fee"]), ("archived", False, None))
        self.assertEqual((c["status"], c["listed"]), ("archived", False))

    def test_deleted_links_are_listed_not_loaded(self) -> None:
        """**削除済みの結び付きは入れない**（移行対象外）。新も外した結び付きは物理削除で持たない。"""
        ctx = make_ctx({
            "payment_item": [{"item_id": 1, "item_type": 0}],
            "payment_item_lesson": [
                {"item_set_lesson_id": 10, "item_id": 1, "lesson_id": 5, "del_chk": 0},
                {"item_set_lesson_id": 11, "item_id": 1, "lesson_id": 6, "del_chk": 1},
                {"item_set_lesson_id": 12, "item_id": 1, "lesson_id": 99, "del_chk": 0},
            ],
            "lesson": [{"lesson_id": 5}, {"lesson_id": 6}],
        })
        step = learning_paths.LearningPathCoursesStep()
        rows = step.extract(ctx)
        self.assertEqual([(r["item_id"], r["lesson_id"]) for r in rows], [(1, 5)])
        dropped = {(v.key, v.reason) for v in step._take_dropped()}
        self.assertEqual(dropped, {("1:6", "移行対象外"), ("1:99", "旧データの不整合")})
        (link,) = step.transform(ctx, rows)
        self.assertEqual(link.values["learning_path_id"], ctx.ulid.for_row("learning_path", 1))


if __name__ == "__main__":
    unittest.main()
