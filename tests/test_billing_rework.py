"""課金（区分 04）の見直しのテスト（docs/db/04-billing/migration-spec.md 0-2、rework-gap.md G1〜G8・F1）。"""

from __future__ import annotations

import json
import unittest
from datetime import date, datetime

from fixups import billing as fx_billing
from migrator.steps.billing import extras as bl_extras
from migrator.steps.billing import payments as pay
from migrator.steps.billing import receipts as rcp
from migrator.steps.billing import tickets as bl_tickets
from migrator.steps.enrollment import rights
from tests.test_billing import make_ctx


def user_ticket(**over):
    row = {"user_id": 7, "ticket_id": 1, "ticket_num": 3, "ticket_start_date": None, "ticket_end_date": None,
           "authority_id": 50, "regist_date": datetime(2022, 11, 1)}
    row.update(over)
    return row


class TicketGrantTest(unittest.TestCase):
    """G1・G2: 専用チケットの期限は権限の期間。種別の無い回数チケットは一覧に出す。"""

    def _run(self, tickets, authorities):
        ctx = make_ctx({"user_ticket": tickets, "payment_item_lesson_authority": authorities})
        step = bl_tickets.TicketGrantsStep()
        rows = step.extract(ctx)
        return step, step.transform(ctx, rows)

    def test_expiry_follows_the_authority(self) -> None:
        auth = {"authority_id": 50, "authority_start_date": date(2022, 11, 1), "authority_end_date": date(2023, 6, 30)}
        _, [rec] = self._run([user_ticket()], [auth])
        # JST 2023-06-30 23:59:59 → UTC 14:59:59
        self.assertEqual(rec.values["expires_at"], datetime(2023, 6, 30, 14, 59, 59))
        self.assertEqual(rec.values["starts_at"], datetime(2022, 10, 31, 15, 0))

    def test_without_authority_keeps_the_ticket_dates(self) -> None:
        _, [rec] = self._run([user_ticket(authority_id=None)], [])
        self.assertIsNone(rec.values["expires_at"])

    def test_count_ticket_without_type_is_listed(self) -> None:
        """**種別の無い回数チケットは移さず一覧に出す**（D22 の回答待ち）。"""
        step, recs = self._run([user_ticket(ticket_id=None, authority_id=None, ticket_num=4)], [])
        self.assertEqual(recs, [])
        [dropped] = step._take_dropped()
        self.assertEqual((dropped.table, dropped.reason), ("ticket_grants", "受け皿なし"))


class TicketTypeTest(unittest.TestCase):
    """キャンセルでチケットを開始まで戻す（旧はキャンセルを受け付けたら必ず戻していた。04 の 0-4）。"""

    def test_refund_until_start(self) -> None:
        ctx = make_ctx({"ticket": [{"ticket_id": 1, "ticket_type": 3, "ticket_name": "t", "del_chk": 0,
                                    "regist_date": datetime(2022, 1, 1)}]})
        step = bl_tickets.TicketTypesStep()
        [rec] = step.transform(ctx, step.extract(ctx))
        self.assertEqual(rec.values["refund_deadline_days"], 0)


class TicketCostTest(unittest.TestCase):
    """G3: 予約 1 回で引くのは専用チケット 1 枚（`item_ticket_price` は配る枚数）。"""

    def test_cost_is_one(self) -> None:
        ctx = make_ctx({"live_lesson": [{"live_lesson_id": 5, "item_ticket_price": 3}],
                        "ticket_limit_lesson": [{"ticket_id": 2, "live_lesson_id": 5, "del_chk": 0}]})
        step = bl_tickets.TicketRequirementsStep()
        [rec] = step.transform(ctx, step.extract(ctx))
        self.assertEqual(rec.values["cost"], 1)


class TicketLedgerTest(unittest.TestCase):
    """G4: 台帳は、開催が未来でチケットで払った予約にだけ作る。"""

    def _rows(self, starts, payment_type):
        ctx = make_ctx({
            "live_lesson": [{"live_lesson_id": 5, "item_ticket_price": 3}],
            "ticket_limit_lesson": [{"ticket_id": 2, "live_lesson_id": 5, "del_chk": 0}],
            "user_ticket": [user_ticket(ticket_id=2)],
            "live_lesson_date": [{"live_lesson_date_id": 9, "live_lesson_id": 5, "live_lesson_date_from": starts,
                                  "mail_send_chk": 0, "update_date": None}],
            "live_lesson_reserve": [{"live_lesson_reserve_id": 30, "live_lesson_date_id": 9, "user_id": 7,
                                     "reserve_date": datetime(2022, 1, 1), "cancel_chk": 0, "attendance_chk": 0,
                                     "stop_chk": 0}],
            "payment_application": [] if payment_type is None else [
                {"live_lesson_reserve_id": 30, "payment_type": payment_type}],
        })
        return bl_tickets.TicketLedgerStep().extract(ctx)

    def test_future_exclusive_reservation_gets_one_ticket(self) -> None:
        [row] = self._rows(datetime(2099, 1, 1), 7)
        self.assertEqual(row["_cost"], 1)

    def test_past_reservation_gets_nothing(self) -> None:
        self.assertEqual(self._rows(datetime(2022, 12, 1), 7), [])

    def test_free_reservation_gets_nothing(self) -> None:
        self.assertEqual(self._rows(datetime(2099, 1, 1), None), [])

    def test_count_ticket_reservation_has_no_grant_yet(self) -> None:
        self.assertEqual(self._rows(datetime(2099, 1, 1), 5), [])


class MonthlyRemainingTest(unittest.TestCase):
    """G5: 月チケットの今の期間の残りは、種別が決まるまで一覧に出す。"""

    def test_current_period(self) -> None:
        row = {"agreement_date": date(2026, 10, 1), "limit_date": date(2026, 10, 31), "ticket_count": 2, "del_chk": 0}
        self.assertTrue(bl_extras.current_period(row, date(2026, 10, 26)))
        self.assertFalse(bl_extras.current_period({**row, "ticket_count": 0}, date(2026, 10, 26)))
        self.assertFalse(bl_extras.current_period(row, date(2026, 11, 1)))


class PaymentStatusTest(unittest.TestCase):
    """G6: 入金待ちは failed（pending だと新の照合の枠を埋める）。"""

    def test_unpaid_is_failed(self) -> None:
        self.assertEqual(pay.STATUSES[0], "failed")


class PayerTest(unittest.TestCase):
    """G7: 払った会員が権限の会員と違う申込には結ばない。"""

    def test_payment_of_skips_a_foreign_payer(self) -> None:
        rows = [{"application_id": 322, "user_id": 911, "_payment_type": 1, "_application_result": 1}]
        self.assertIsNone(rights._payment_of(rows, {322: 0}))
        self.assertEqual(rights._payment_of(rows, {322: 911}), pay.provider_payment_id(322))


class ReceiptSettingsTest(unittest.TestCase):
    """G8: 旧の期間と番号を残す。"""

    def test_period_and_seq_no_are_kept(self) -> None:
        ctx = make_ctx({"receipt_log": [{
            "receipt_log_id": 1, "user_id": 7, "application_id": 100, "receipt_price": 48000, "seq_no": 2,
            "payment_date_from": date(2024, 4, 1), "payment_date_to": date(2025, 3, 31),
            "regist_date": datetime(2025, 4, 1)}]})
        step = rcp.ReceiptsStep()
        [rec] = step.transform(ctx, step.extract(ctx))
        self.assertEqual(json.loads(rec.values["settings"]),
                         {"period_from": "2024-04-01", "period_to": "2025-03-31", "seq_no": 2})


class PayerProposalTest(unittest.TestCase):
    """F1: 会員のいない申込は、権限の会員に直す提案を出す。"""

    def test_single_holder_is_proposed(self) -> None:
        out = fx_billing.propose_payers([{"application_id": 322, "user_id": 0}], {7, 911}, {322: {911}})
        self.assertEqual([(r[1], r[2], r[3]) for r in out], [("322", "user_id", "911")])

    def test_application_without_holders_is_skipped(self) -> None:
        """権限の無い申込（会員が物理削除された不整合 #11）は空欄の提案を出さない。"""
        self.assertEqual(fx_billing.propose_payers([{"application_id": 1, "user_id": 24}], {7}, {}), [])

    def test_known_member_is_left_alone(self) -> None:
        self.assertEqual(fx_billing.propose_payers([{"application_id": 1, "user_id": 7}], {7}, {}), [])


if __name__ == "__main__":
    unittest.main()
