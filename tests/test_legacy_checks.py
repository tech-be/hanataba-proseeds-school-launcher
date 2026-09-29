"""旧 DB との突き合わせ（`verify` の一部）のテスト。

**突き合わせが「一致」と言ってしまう誤り**を中心に固定する。
"""

from __future__ import annotations

import json
import unittest
from decimal import Decimal

from migrator.validation import legacy_checks as lc


class SameTest(unittest.TestCase):
    def test_amounts_compare_by_value(self) -> None:
        """**`980` と `980.00` は同じ。** 文字列で比べると違って見える（実際にこれで誤判定した）。"""
        self.assertTrue(lc.same(980, Decimal("980.00")))
        self.assertFalse(lc.same(980, Decimal("981.00")))

    def test_null_and_empty_are_the_same(self) -> None:
        self.assertTrue(lc.same(None, ""))
        self.assertFalse(lc.same(None, "山田"))


def fake(src_rows: dict, dst_rows: dict):
    """表名（旧）/ SQL の断片（新）で行を返す偽物。**無ければ空**（集計は0件）。"""

    def src(table, sql, params):
        if "COUNT(*) n, SUM(l.item_ticket_price)" in sql:
            return [{"n": 0, "cost": None}]
        for key, rows in src_rows.items():
            if key in sql:
                return rows
        return []

    def dst(sql, params):
        if "FROM ticket_ledger_entries" in sql:
            return [{"n": 0, "cost": None}]
        for key, rows in dst_rows.items():
            if key in sql:
                return rows
        return []

    return src, dst


def names(results, ok):
    return [r.name for r in results if r.ok is ok]


class BillingChecksTest(unittest.TestCase):
    GROUPED = "a.payment_type pt, a.application_result ar"  # 支払い方法 × 状態の集計

    def run_checks(self, src_rows, dst_rows):
        src, dst = fake(src_rows, dst_rows)
        return lc.billing_checks(src, dst, 12, "T")

    def test_everything_empty_is_ok(self) -> None:
        results = self.run_checks({}, {})
        self.assertEqual(names(results, False), [])

    def test_missing_payment_is_ng(self) -> None:
        """旧にお金が動いた申込があるのに、新に無い。"""
        results = self.run_checks(
            {self.GROUPED: [{"pt": 1, "ar": 1, "n": 1, "amt": 1000}]}, {})
        self.assertIn("支払い方法 1 / 状態 1: 件数と金額", names(results, False))

    def test_skipped_application_appearing_is_ng(self) -> None:
        """**意図して移さない申込**（0円）が新に入っていたら NG。"""
        settings = json.dumps({"legacy_payment_type": 0, "legacy_application_result": 1})
        results = self.run_checks(
            {self.GROUPED: [{"pt": 0, "ar": 1, "n": 1, "amt": 0}]},
            {"SELECT status, amount, settings FROM payments": [
                {"status": "succeeded", "amount": 0, "settings": settings}]})
        self.assertIn("支払い方法 0 / 状態 1: 決済にしない（P3 / P4）", names(results, False))

    def test_status_mapping_is_checked(self) -> None:
        settings = json.dumps({"legacy_payment_type": 1, "legacy_application_result": 0})
        results = self.run_checks(
            {self.GROUPED: [{"pt": 1, "ar": 0, "n": 1, "amt": 1000}]},
            {"SELECT status, amount, settings FROM payments": [
                {"status": "succeeded", "amount": 1000, "settings": settings}]})
        self.assertIn("決済の状態（1→succeeded / 0→pending / 2→failed）", names(results, False))


class RunTest(unittest.TestCase):
    def test_only_sections_with_checks_run(self) -> None:
        self.assertEqual(set(lc.CHECKS), {"billing"})


if __name__ == "__main__":
    unittest.main()
