"""ライブ区分の変換テスト。**取り違えると気づかないまま誤データになるもの**に絞る。"""

from __future__ import annotations

import logging
import unittest
from datetime import datetime

from migrator.config import Config, TenantConfig
from migrator.context import build_context
from migrator.db.target import TargetDatabase
from migrator.steps.content import live_courses as lv_courses
from migrator.steps.content import live_lessons as lv_lessons
from migrator.steps.billing import tickets as lv_tickets
from tests.fakes import FakeSource

CONFIG = Config(
    tenant=TenantConfig(legacy_id=12, slug="recademy", name="ReCADemy"),
    ulid_namespace="lw2-test",
    mappings={"role": {"values": {7: "learner"}}, "prefecture": {"values": {}}},
)


def make_ctx():
    ctx = build_context(CONFIG, FakeSource({}), TargetDatabase(None, dry_run=True),
                        logging.getLogger("test"))
    ctx.tenant_id.resolve("01ARZ3NDEKTSV4RRFFQ69G5FAV")
    return ctx


class PlacementTest(unittest.TestCase):
    """**商品で制限しているライブは実在の講座へ、無いものは受け皿講座へ。**"""

    def test_restricted_live_goes_to_the_real_course(self) -> None:
        ctx = make_ctx()
        real = lv_courses.course_for(ctx, 2100029735)
        self.assertEqual(real, ctx.ulid.for_row("lesson", 2100029735))

    def test_unrestricted_live_goes_to_the_host_course(self) -> None:
        ctx = make_ctx()
        self.assertEqual(lv_courses.course_for(ctx, None), lv_courses.host_course_id(ctx))

    def test_host_course_is_not_a_real_course(self) -> None:
        """**受け皿講座に旧 ID を持たせない。** 実在の講座と見分けが付かなくなる。"""
        ctx = make_ctx()
        rows = [{"live_lesson_id": 1, "lesson_instructor_id": 243, "del_chk": 0}]
        record = lv_courses.HostCourseStep().transform(ctx, rows)[0]
        self.assertIsNone(record.values["legacy_id"])

    def test_representative_instructor_is_the_busiest(self) -> None:
        """同数なら旧 ID の小さい順。**実行のたびに変わらないこと。**"""
        ctx = make_ctx()
        rows = [
            {"live_lesson_id": 1, "lesson_instructor_id": 9, "del_chk": 0},
            {"live_lesson_id": 2, "lesson_instructor_id": 5, "del_chk": 0},
            {"live_lesson_id": 3, "lesson_instructor_id": 5, "del_chk": 0},
        ]
        record = lv_courses.HostCourseStep().transform(ctx, rows)[0]
        self.assertEqual(record.values["instructor_id"], ctx.ulid.for_row("user", 5))

    def test_enrollment_source_is_a_real_lookup_value(self) -> None:
        """`enrollment_sources` に `manual` は無い。**`admin`（管理者付与）が正。**"""
        ctx = make_ctx()
        record = lv_courses.HostCourseEnrollmentsStep().transform(ctx, [{"user_id": 1}])[0]
        self.assertEqual(record.values["source"], "admin")


class ScheduledAtTest(unittest.TestCase):
    """代表日時は**直近の開催予定日、無ければ最後の回**。"""

    def _dates(self, *pairs):
        return [{"live_lesson_date_from": d, "del_chk": c} for d, c in pairs]

    def test_picks_the_next_upcoming(self) -> None:
        now = datetime(2026, 6, 1)
        rows = self._dates((datetime(2026, 1, 1), 0), (datetime(2026, 7, 1), 0),
                           (datetime(2026, 9, 1), 0))
        self.assertEqual(lv_lessons._representative_starts_at(rows, now), datetime(2026, 7, 1))

    def test_falls_back_to_the_last_one_when_all_past(self) -> None:
        now = datetime(2026, 6, 1)
        rows = self._dates((datetime(2026, 1, 1), 0), (datetime(2026, 3, 1), 0))
        self.assertEqual(lv_lessons._representative_starts_at(rows, now), datetime(2026, 3, 1))

    def test_deleted_occurrences_are_not_preferred(self) -> None:
        """削除済みしか無ければ使うが、生きている回があればそちらを選ぶ。"""
        now = datetime(2026, 6, 1)
        rows = self._dates((datetime(2026, 7, 1), 1), (datetime(2026, 8, 1), 0))
        self.assertEqual(lv_lessons._representative_starts_at(rows, now), datetime(2026, 8, 1))


class OccurrenceTest(unittest.TestCase):
    def test_zero_capacity_becomes_null(self) -> None:
        """`chk_llo_capacity` は `>= 1`。**`0` は「定員なし」として NULL に倒す。**"""
        self.assertIsNone(lv_lessons._capacity({"capacity": 0}, {"capacity": 0}))

    def test_occurrence_capacity_wins_over_the_lesson_default(self) -> None:
        self.assertEqual(lv_lessons._capacity({"capacity": 5}, {"capacity": 9}), 5)
        self.assertEqual(lv_lessons._capacity({"capacity": None}, {"capacity": 9}), 9)

    def test_status_of_the_live_prefers_deleted(self) -> None:
        """**`del_chk` を `valid_chk` より優先する。**"""
        self.assertEqual(lv_lessons._status({"del_chk": 1, "valid_chk": 1}), "deleted")
        self.assertEqual(lv_lessons._status({"del_chk": 0, "valid_chk": 1}), "published")
        self.assertEqual(lv_lessons._status({"del_chk": 0, "valid_chk": 0}), "draft")


class ReservationStatusTest(unittest.TestCase):
    """**3フラグを畳む。** 開催中止と受講者キャンセルを混ぜない。"""

    def _status(self, starts_past: bool, **flags):
        now = datetime(2026, 6, 1)
        starts = datetime(2026, 1, 1) if starts_past else datetime(2026, 12, 1)
        row = {"cancel_chk": 0, "attendance_chk": 0, "stop_chk": 0, **flags}
        return lv_tickets._status(row, starts, now)

    def test_host_cancel_is_not_a_learner_cancel(self) -> None:
        self.assertEqual(self._status(True, stop_chk=1), "host_canceled")

    def test_learner_cancel(self) -> None:
        self.assertEqual(self._status(True, cancel_chk=1), "canceled")

    def test_attended(self) -> None:
        self.assertEqual(self._status(True, attendance_chk=1), "attended")

    def test_past_without_attendance_is_no_show(self) -> None:
        self.assertEqual(self._status(True), "no_show")

    def test_future_stays_reserved(self) -> None:
        self.assertEqual(self._status(False), "reserved")

    def test_no_show_still_holds_the_ticket(self) -> None:
        """**欠席でもチケットは消費済み。** lw2 は予約時に引き、来なくても戻さない。

        `live_reservation_statuses.occupies_seat` と揃える（no_show は 1）。
        """
        self.assertIn("no_show", lv_tickets.HOLDS_SEAT)
        self.assertNotIn("canceled", lv_tickets.HOLDS_SEAT)
        self.assertNotIn("host_canceled", lv_tickets.HOLDS_SEAT)


class TicketTest(unittest.TestCase):
    def test_balance_goes_to_both_columns(self) -> None:
        """**残高1行 = 付与1行。** 旧は「何枚配ったか」を持たない。"""
        ctx = make_ctx()
        row = {"user_id": 1, "ticket_id": 2, "ticket_num": 3, "authority_id": None,
               "ticket_start_date": None, "ticket_end_date": None, "regist_date": None}
        record = lv_tickets.TicketGrantsStep().transform(ctx, [row])[0]
        self.assertEqual(record.values["quantity"], 3)
        self.assertEqual(record.values["remaining_quantity"], 3)

    def test_consumption_is_negative(self) -> None:
        """台帳の `quantity_delta` は**消費なので負**。返却時に -delta で数える。"""
        ctx = make_ctx()
        row = {
            "live_lesson_reserve_id": 7, "user_id": 1, "reserve_date": None,
            "_cost": 3,
            "_grant": {"user_id": 1, "ticket_id": 2, "authority_id": None},
        }
        record = lv_tickets.TicketLedgerStep().transform(ctx, [row])[0]
        self.assertEqual(record.values["quantity_delta"], -3)
        self.assertEqual(record.values["kind"], "consumed")


if __name__ == "__main__":
    unittest.main()
