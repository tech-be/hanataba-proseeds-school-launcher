"""support.2 クーポン（docs/db/05-support/migration-spec.md 0-2・0-9）のテスト。"""

from __future__ import annotations

import unittest
from datetime import date, datetime

from migrator.steps.support import coupons as cp
from tests.test_support_announcements import ctx_with

BASE = {
    "coupon_id": 4, "coupon_name": "200円引き", "coupon_code": "abcdefghijklmnopq", "valid_chk": 1,
    "coupon_start_date": None, "coupon_end_date": None, "valid_term_day": None, "coupon_type": 2,
    "discount_amount": 200, "discount_rate": None, "target_type": 0, "timing_chk": 0,
    "regist_date": datetime(2023, 1, 1), "update_date": datetime(2023, 1, 1), "del_chk": 0,
}
FREE = {**BASE, "coupon_id": 1, "coupon_type": 1, "discount_amount": None, "target_type": 2}
RATE = {**BASE, "coupon_id": 1019, "coupon_type": 3, "discount_amount": None, "discount_rate": 15, "valid_term_day": 31}


class CouponTest(unittest.TestCase):
    def test_free_coupons_are_listed_not_migrated(self) -> None:
        """**無料クーポンは移さない**（新に割引の種類が無い。2026-10-26 決定）。"""
        ctx = ctx_with({"coupon": [BASE, FREE, RATE]})
        step = cp.CouponsStep()
        rows = step.extract(ctx)
        self.assertEqual(sorted(r["coupon_id"] for r in rows), [4, 1019])
        self.assertEqual([v.key for v in step._take_dropped()], ["coupon:1"])

    def test_values_follow_legacy_state(self) -> None:
        """**旧のとおり有効で移す**（2026-10-26 決定）。決済代行の ID は空文字。"""
        ctx = ctx_with({})
        [amount, rate] = cp.CouponsStep().transform(ctx, [BASE, RATE])
        self.assertEqual(amount.values["id"], ctx.ulid.for_row("coupon", 4))
        self.assertEqual((amount.values["discount_type"], amount.values["discount_value"]), ("amount", 200))
        self.assertEqual((rate.values["discount_type"], rate.values["discount_value"]), ("percent", 15))
        self.assertEqual(amount.values["status"], "active")
        self.assertEqual((amount.values["provider_coupon_id"], amount.values["provider_promotion_id"]), ("", ""))
        self.assertFalse(amount.values["visible_to_learners"])

    def test_deleted_or_invalid_is_inactive(self) -> None:
        self.assertEqual(cp.status_of({**BASE, "del_chk": 1}), "inactive")
        self.assertEqual(cp.status_of({**BASE, "valid_chk": 0}), "inactive")

    def test_validity(self) -> None:
        # 期間: 終了日を含む（翌日 0 時 JST = 当日 15:00 UTC）
        kind, start, end, days = cp.validity_of({**BASE, "coupon_start_date": date(2024, 4, 1), "coupon_end_date": date(2024, 4, 30)})
        self.assertEqual((kind, start, end, days), ("fixed", datetime(2024, 3, 31, 15, 0), datetime(2024, 4, 30, 15, 0), None))
        # 配布日から N 日（全員が対象）→ 登録日から
        self.assertEqual(cp.validity_of(RATE)[0::3], ("registration_days", 31))
        # 個人が対象 → 配布日から
        self.assertEqual(cp.validity_of({**RATE, "target_type": 2})[0::3], ("assignment_days", 31))
        # 登録日からずらす指定は表せない
        self.assertEqual(cp.validity_of({**RATE, "timing_chk": 1})[0], "none")


class CouponChildrenTest(unittest.TestCase):
    def test_targets_of_unmigrated_coupon_are_listed(self) -> None:
        users = [
            {"coupon_user_id": 1, "coupon_id": 1, "user_id": 101, "regist_date": datetime(2024, 1, 1), "del_chk": 0},
            {"coupon_user_id": 2, "coupon_id": 4, "user_id": 102, "regist_date": datetime(2024, 1, 2, 9), "del_chk": 0},
        ]
        ctx = ctx_with({"coupon": [BASE, FREE], "coupon_user": users})
        step = cp.CouponUsersStep()
        rows = step.extract(ctx)
        self.assertEqual([r["coupon_user_id"] for r in rows], [2])
        self.assertEqual([v.key for v in step._take_dropped()], ["coupon_user:1"])
        # 配布日（期限の起点）は旧の登録日
        [record] = step.transform(ctx, rows)
        self.assertEqual(record.values["created_at"], datetime(2024, 1, 2, 0, 0))

    def test_items_are_listed(self) -> None:
        ctx = ctx_with({"coupon_item": [{"coupon_item_id": 7, "coupon_id": 4}]})
        step = cp.CouponItemsStep()
        self.assertEqual(step.extract(ctx), [])
        self.assertEqual([v.key for v in step._take_dropped()], ["coupon_item:7"])


if __name__ == "__main__":
    unittest.main()
