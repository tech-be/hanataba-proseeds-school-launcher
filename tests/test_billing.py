"""課金（04）の決済・帳票の変換テスト。

**暫定の規則（docs/db/04-billing/migration-spec.md 1-3 の P1〜P14）を固定する。**
規則を変えるときは、このテストと仕様書を一緒に直す。
"""

from __future__ import annotations

import json
import logging
import unittest
from datetime import date, datetime

from migrator.config import Config, TenantConfig
from migrator.context import build_context
from migrator.db.target import TargetDatabase
from migrator.steps import tenant as tenant_step
from migrator.steps.billing import payments as pay
from migrator.steps.billing import receipts as rcp
from migrator.steps.enrollment import rights
from tests.fakes import FakeSource

CONFIG = Config(
    tenant=TenantConfig(legacy_id=12, slug="recademy", name="ReCADemy"),
    ulid_namespace="lw2-test",
    mappings={"role": {"values": {7: "learner"}}, "prefecture": {"values": {}}},
)


def make_ctx(tables=None):
    ctx = build_context(CONFIG, FakeSource(tables or {}), TargetDatabase(None, dry_run=True),
                        logging.getLogger("test"))
    ctx.tenant_id.resolve("01ARZ3NDEKTSV4RRFFQ69G5FAV")
    return ctx


def item(item_id=1, item_type=0, auto=0, **over):
    row = {"item_id": item_id, "item_type": item_type, "item_name": f"商品{item_id}", "price": 11000,
           "is_auto_extension": auto, "is_use_trial": 0, "valid_chk": 1, "display_chk": 1,
           "del_chk": 0, "sort_no": 1, "regist_date": datetime(2020, 1, 1)}
    row.update(over)
    return row


def app(application_id=100, payment_type=1, result=1, **over):
    row = {"application_id": application_id, "user_id": 7, "payment_type": payment_type,
           "application_result": result, "amount": 11000,
           "application_date_time": datetime(2024, 4, 1, 10, 0)}
    row.update(over)
    return row


def tables(apps, items, lessons=((1, 500),), links=None):
    return {
        "payment_item": list(items),
        "payment_item_lesson": [
            {"item_set_lesson_id": i, "item_id": it, "lesson_id": ls, "del_chk": 0}
            for i, (it, ls) in enumerate(lessons)
        ],
        "payment_application": list(apps),
        "payment_application_item": [
            {"application_id": a["application_id"], "item_id": (links or {}).get(a["application_id"], 1)}
            for a in apps
        ],
    }


class MigratedTest(unittest.TestCase):
    """P3 / P4: 決済として移すのはお金が動く申込だけ。"""

    def test_money_types_are_migrated(self) -> None:
        for kind in (1, 2, 3):
            self.assertTrue(pay.is_migrated(kind, 1))

    def test_free_and_ticket_payments_are_not(self) -> None:
        """0 無料 / 4 無料クーポン / 5・6・7 チケット払いは金額0。決済一覧を埋めてしまう。"""
        for kind in (0, 4, 5, 6, 7, None):
            self.assertFalse(pay.is_migrated(kind, 1))

    def test_no_payment_required_is_not(self) -> None:
        """`application_result = 3` は管理者が「払わなくてよい」とした申込。入金は無い。"""
        self.assertFalse(pay.is_migrated(3, 3))
        self.assertTrue(pay.is_migrated(3, 0))


class KindTest(unittest.TestCase):
    """P5: 講座が1つに決まらない購入を course_purchase に入れない。"""

    def test_single_course_one_time_is_course_purchase(self) -> None:
        self.assertEqual(pay.payment_kind(item(), 1), "course_purchase")

    def test_bundle_is_lw2_purchase(self) -> None:
        self.assertEqual(pay.payment_kind(item(), 2), "lw2_purchase")
        self.assertEqual(pay.payment_kind(item(), 0), "lw2_purchase")

    def test_ticket_item_is_lw2_purchase(self) -> None:
        self.assertEqual(pay.payment_kind(item(item_type=1), 1), "lw2_purchase")

    def test_auto_extension_is_subscription(self) -> None:
        self.assertEqual(pay.payment_kind(item(auto=1), 3), "subscription")


class PaymentsStepTest(unittest.TestCase):
    def records(self, apps, items=(item(),), **kw):
        ctx = make_ctx(tables(apps, items, **kw))
        step = pay.PaymentsStep()
        return step.transform(ctx, step.extract(ctx))

    def test_status_and_provider(self) -> None:
        recs = self.records([app(1, 1, 1), app(2, 1, 0), app(3, 1, 2), app(4, 3, 1), app(5, 2, 1)])
        got = {r.values["application_id"]: (r.values["status"], r.values["provider"]) for r in recs}
        self.assertEqual(got, {
            1: ("succeeded", "legacy_jpayment"), 2: ("pending", "legacy_jpayment"),
            3: ("failed", "legacy_jpayment"), 4: ("succeeded", "bank_transfer"),
            5: ("succeeded", "legacy_jpayment"),
        })

    def test_cancel_is_not_a_refund(self) -> None:
        """**解約は継続課金を止めただけ。** お金は動いているので succeeded のまま。"""
        [rec] = self.records([app(1, 1, 1, is_cancel=1, cancel_date_time=datetime(2024, 5, 1))])
        self.assertEqual(rec.values["status"], "succeeded")
        self.assertTrue(json.loads(rec.values["settings"])["cancel"]["canceled"])

    def test_skipped_applications_are_not_extracted(self) -> None:
        recs = self.records([app(1, 0, 1, amount=0), app(2, 5, 1, amount=0), app(3, 3, 3)])
        self.assertEqual(recs, [])

    def test_provider_payment_id_is_stable(self) -> None:
        """受講（`enrollments.provider_payment_id`）もこの値で結ぶ。"""
        [rec] = self.records([app(42)])
        self.assertEqual(rec.values["provider_payment_id"], "lw2-42")
        self.assertEqual(rec.values["platform_fee"], 0)

    def test_personal_columns_are_not_read(self) -> None:
        """**申込フォームの個人情報と password は読まない。**"""
        for col in ("password", "name_sei", "mail_add", "tel", "address", "birth_date", "application_memo"):
            self.assertNotIn(col, pay.APPLICATION_COLUMNS)

    def test_split_number_one_means_lump_sum(self) -> None:
        """`split_payment_number = 1` は一括（選択欄があるだけで 1 が入る）。"""
        [rec] = self.records([app(1, is_use_split_payment=1, split_payment_number=1)])
        self.assertNotIn("card_installments", json.loads(rec.values["settings"]))


class PaidAtTest(unittest.TestCase):
    """lw2 の `real_payment_date`（`PaymentModel:110-113`）と同じ規則。"""

    def test_card_deferred_billing(self) -> None:
        a = app(credit_payment_date=datetime(2024, 5, 1))
        self.assertEqual(pay.paid_at(a, item()), datetime(2024, 5, 1))

    def test_card_same_day_uses_application_date(self) -> None:
        a = app(credit_payment_date=datetime(2024, 4, 1, 23, 0))
        self.assertEqual(pay.paid_at(a, item()), datetime(2024, 4, 1, 10, 0))

    def test_card_with_trial_uses_application_date(self) -> None:
        a = app(credit_payment_date=datetime(2024, 5, 1))
        self.assertEqual(pay.paid_at(a, item(is_use_trial=1)), datetime(2024, 4, 1, 10, 0))

    def test_bank_and_convenience_use_their_dates(self) -> None:
        self.assertEqual(pay.paid_at(app(payment_type=3, bank_payment_date=datetime(2024, 4, 3)), None),
                         datetime(2024, 4, 3))
        self.assertEqual(pay.paid_at(app(payment_type=2, convenience_payment_date=datetime(2024, 4, 4)), None),
                         datetime(2024, 4, 4))


class ReceiptsTest(unittest.TestCase):
    def test_issue_no_counts_per_payment_and_keeps_legacy_number(self) -> None:
        """**旧はダウンロードのたびに1行。** 新の issue_no は決済ごとの連番に振り直す。"""
        logs = [
            {"receipt_log_id": 11, "user_id": 7, "application_id": 100, "receipt_price": 11000,
             "receipt_name": "山田", "regist_date": datetime(2024, 4, 5)},
            {"receipt_log_id": 12, "user_id": 7, "application_id": 200, "receipt_price": 5000,
             "receipt_name": "山田", "regist_date": datetime(2024, 4, 6)},
            {"receipt_log_id": 13, "user_id": 7, "application_id": 100, "receipt_price": 11000,
             "receipt_name": "山田", "regist_date": datetime(2024, 4, 7)},
        ]
        t = tables([app(100, payment_type=3, bank_payment_date=datetime(2024, 4, 3)), app(200)], [item()])
        t["receipt_log"] = logs
        ctx = make_ctx(t)
        step = rcp.ReceiptsStep()
        recs = step.transform(ctx, step.extract(ctx))
        got = {r.values["receipt_log_id"]: (r.values["issue_no"], r.values["transaction_date"]) for r in recs}
        self.assertEqual(got, {11: (1, date(2024, 4, 3)), 12: (1, date(2024, 4, 1)), 13: (2, date(2024, 4, 3))})


class LegalDocumentsTest(unittest.TestCase):
    def test_empty_body_is_not_migrated(self) -> None:
        ctx = make_ctx({
            "agreement": [{"agreement": "第1条…", "language_code": "ja"}, {"agreement": " ", "language_code": "en"}],
            "privacy_policy": [{"privacy_policy": "", "language_code": "ja"}],
            "payment_infomation": [{}],
        })
        step = rcp.LegalDocumentsStep()
        recs = step.transform(ctx, step.extract(ctx))
        self.assertEqual([(r.values["kind"], r.values["language_code"]) for r in recs], [("terms", "ja")])

    def test_url_override_counts_only_when_checked(self) -> None:
        """**`*_chk = 1` のときだけ有効。** 値だけ残っていることがある。"""
        info = {"privacy_policy_another_url_chk": 1, "privacy_policy_another_url": "https://example.com/p",
                "agreement_another_url_chk": 0, "agreement_another_url": "https://example.com/old"}
        ctx = make_ctx({
            "agreement": [{"agreement": "", "language_code": "ja"}],
            "privacy_policy": [{"privacy_policy": "", "language_code": "ja"}],
            "payment_infomation": [info],
        })
        step = rcp.LegalDocumentsStep()
        [rec] = step.transform(ctx, step.extract(ctx))
        self.assertEqual((rec.values["kind"], rec.values["external_url"], rec.values["body"]),
                         ("privacy_policy", "https://example.com/p", None))


class EnrollmentPaymentLinkTest(unittest.TestCase):
    """P10: 受講は、畳んだ権限のうち決済として移す最も新しい申込と結ぶ。"""

    def test_latest_migrated_application_wins(self) -> None:
        rows = [
            {"application_id": 10, "_payment_type": 1, "_application_result": 1},
            {"application_id": 30, "_payment_type": 0, "_application_result": 1},  # 無料。決済にならない
            {"application_id": 20, "_payment_type": 3, "_application_result": 1},
            {"application_id": None},
        ]
        self.assertEqual(rights._payment_of(rows), "lw2-20")

    def test_no_payment_means_null(self) -> None:
        self.assertIsNone(rights._payment_of([{"application_id": 5, "_payment_type": 5, "_application_result": 1}]))


class TenantPaymentSettingsTest(unittest.TestCase):
    def test_split_counts_only_when_enabled(self) -> None:
        on = tenant_step._payment_settings({"is_use_split_payment": 1, "use_split_payment_number": "3,5,24"}, None)
        off = tenant_step._payment_settings({"is_use_split_payment": 0, "use_split_payment_number": "3,5"}, None)
        self.assertEqual(on["card_installments"], [3, 5, 24])
        self.assertEqual(off["card_installments"], [])


if __name__ == "__main__":
    unittest.main()
