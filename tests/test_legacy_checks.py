"""旧 DB との突き合わせ（`verify` の一部）のテスト。

**突き合わせが「一致」と言ってしまう誤り**を中心に固定する。
"""

from __future__ import annotations

import json
import unittest
from datetime import date, datetime
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
        # **f 文字列の付け忘れ**（`{AUTHORITY_TERMS}` がそのまま送られる）は実 DB でだけ落ちる
        assert "{" not in sql, f"埋め込まれていない SQL: {sql[:80]}"
        if "COUNT(*) n, COUNT(*) cost FROM live_lesson_reserve" in sql:
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
        return lc.billing_checks(lc.Env(src, dst, 12, "T"))

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
        self.assertIn("決済の状態（1→succeeded / 0・2→failed）", names(results, False))


class FoundationChecksTest(unittest.TestCase):
    NAME = "会員の個別番号・登録番号・スカウトでの名前の出し方"
    OLD = {"FROM user_personal_no p": [
        {"user_id": 101, "regist_no": 1, "personal_no": 1001, "scout_display_type": 2}]}

    def run_checks(self, new_display):
        src, dst = fake(self.OLD, {"FROM user_personal_numbers n": [
            {"user_id": 101, "regist_no": 1, "personal_no": "1001", "scout_display_type": new_display}]})
        return lc.foundation_checks(lc.Env(src, dst, 12, "T"))

    def test_personal_number_matches(self) -> None:
        """旧の数値の `personal_no` と、新の文字列の `personal_no` は同じとみなす。"""
        self.assertIn(self.NAME, names(self.run_checks("personal_no"), True))

    def test_scout_display_type_mixup_is_ng(self) -> None:
        """旧 2（個別番号）が新で `name` になっていたら NG。"""
        self.assertIn(self.NAME, names(self.run_checks("name"), False))


class ContentChecksTest(unittest.TestCase):
    NAME = "コースの名前・価格"

    def run_checks(self, new_price):
        src, dst = fake(
            {"FROM payment_item WHERE": [{"item_id": 1, "item_name": "A", "price": 1500, "valid_chk": 1,
                                         "display_chk": 1, "remote_chk": 0, "del_chk": 0}],
             "COUNT(*)": [{"n": 0}]},
            {"FROM learning_paths WHERE": [{"id": "learning_path:1", "title": "A", "price": new_price,
                                            "status": "published", "listed": 1, "remote_pc_enabled": 0}],
             "COUNT(*)": [{"n": 0}]})
        return lc.content_checks(lc.Env(src, dst, 12, "T"))

    def test_price_compares_by_value(self) -> None:
        """**`1500` と `1500.00` は同じ。** 名前と組にして比べると文字列になり NG になった（2026-10-22）。"""
        self.assertIn(self.NAME, names(self.run_checks(Decimal("1500.00")), True))
        self.assertIn(self.NAME, names(self.run_checks(Decimal("1600.00")), False))


def term(**over) -> dict:
    row = {"del_chk": 0, "no_limit_chk": 0, "authority_end_date": date(2026, 10, 15), "ext": 0, "cancel": None}
    row.update(over)
    return row


class ExpiryTest(unittest.TestCase):
    """**旧の受講期限**（2026-10-23。sync-issues B6）。移行ツールの変換を使わずに旧から出す。"""

    def test_live_subscription_has_the_month_end(self) -> None:
        """**自動継続も期限で切れる。** 無期限（NULL）と言ってしまうと、旧と違う値を一致と見なす。"""
        self.assertEqual(lc.legacy_expiry([term(ext=1)]), date(2026, 10, 15))

    def test_latest_alive_row_wins(self) -> None:
        rows = [term(authority_end_date=date(2026, 1, 1)), term(authority_end_date=date(2027, 1, 1), del_chk=1)]
        self.assertEqual(lc.legacy_expiry(rows), date(2026, 1, 1))

    def test_no_limit_and_far_future_are_unlimited(self) -> None:
        self.assertIsNone(lc.legacy_expiry([term(no_limit_chk=1)]))
        self.assertIsNone(lc.legacy_expiry([term(authority_end_date=date(2124, 6, 24))]))
        self.assertEqual(lc.legacy_expiry([term(authority_end_date=date(2038, 1, 18))]), date(2038, 1, 18))

    def test_new_expiry_is_read_in_japan_time(self) -> None:
        """新は最終日の 23:59:59（日本時間）を UTC で持つ。"""
        self.assertEqual(lc.new_expiry(datetime(2026, 10, 15, 14, 59, 59)), date(2026, 10, 15))
        self.assertIsNone(lc.new_expiry(None))

    def test_live_subscription_row(self) -> None:
        self.assertTrue(lc.is_live_subscription(term(ext=1)))
        self.assertFalse(lc.is_live_subscription(term(ext=1, cancel=1)))
        self.assertFalse(lc.is_live_subscription(term(ext=0)))


class RunTest(unittest.TestCase):
    def test_every_implemented_section_has_checks(self) -> None:
        self.assertEqual(set(lc.CHECKS), {"foundation", "content", "enrollment", "billing", "support"})
        self.assertEqual(set(lc.ORDER), set(lc.CHECKS))


if __name__ == "__main__":
    unittest.main()
