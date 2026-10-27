"""コースの購入・割り当て（受講 03。2026-10-22）の変換テスト。

**DB を立てずに transform だけを通す。** 固定するのは、取り違えると気づかないまま誤データになるもの。

- 1回の購入・付与（旧の `authority_key`）が1行になること
- 購入・無料・管理者の付与の見分け方と、取り消しの状態（購入・無料 → refunded / 付与 → revoked）
- 決済として移した申込だけを `payment_id` に結ぶこと
- 商品を経た権限の受講登録が `via_learning_path` になること
"""

from __future__ import annotations

import logging
import unittest
from datetime import date, datetime

from migrator.config import Config, TenantConfig
from migrator.context import build_context
from migrator.db.target import TargetDatabase
from migrator.steps.enrollment import learning_paths as lpe
from migrator.steps.enrollment.rights import EnrollmentRightsStep
from tests.fakes import FakeSource

CONFIG = Config(
    tenant=TenantConfig(legacy_id=12, slug="recademy", name="ReCADemy"),
    ulid_namespace="lw2-test",
    mappings={"role": {"values": {7: "learner"}}, "prefecture": {"values": {}}},
)


def make_ctx():
    ctx = build_context(CONFIG, FakeSource({}), TargetDatabase(None, dry_run=True), logging.getLogger("test"))
    ctx.tenant_id.resolve("01ARZ3NDEKTSV4RRFFQ69G5FAV")
    return ctx


def row(**over) -> dict:
    base = {
        "authority_key": "893_134_1", "user_id": 893, "item_id": 134, "application_id": None,
        "lesson_id": 1, "authority_start_date": date(2024, 4, 1), "authority_end_date": date(2025, 3, 31),
        "no_limit_chk": 0, "remote_chk": 0, "del_chk": 0,
        "_auto_extension": 0, "_is_cancel": None, "_payment_type": None, "_application_result": None,
    }
    base.update(over)
    return base


class GrantTest(unittest.TestCase):
    def test_one_row_per_authority_key(self) -> None:
        """講座ごとの権限の行を、旧の購入・付与（`authority_key`）で1行にまとめる。"""
        rows = [row(lesson_id=1), row(lesson_id=2), row(authority_key="893_134_2", lesson_id=1)]
        records = lpe.LearningPathEnrollmentsStep().transform(make_ctx(), rows)
        self.assertEqual(len(records), 2)

    def test_courses_include_removed_rows(self) -> None:
        """渡した講座の記録には、削除済みの権限の講座も入れる（取り消しは状態で表す）。"""
        rows = [row(lesson_id=1), row(lesson_id=2, del_chk=1), row(lesson_id=2)]
        records = lpe.LearningPathEnrollmentCoursesStep().transform(make_ctx(), rows)
        self.assertEqual(len(records), 2)


class SourceAndStatusTest(unittest.TestCase):
    def test_source(self) -> None:
        self.assertEqual(lpe.source_of([row()]), "admin")
        self.assertEqual(lpe.source_of([row(application_id=5, _payment_type=0)]), "free")
        self.assertEqual(lpe.source_of([row(application_id=5, _payment_type=1)]), "purchase")

    def test_removed_status_depends_on_source(self) -> None:
        """**旧に返金は無いが、新は revoked を管理者の取り消しに限る**（2026-10-22 決定）。"""
        ctx = make_ctx()
        step = lpe.LearningPathEnrollmentsStep()
        (admin,) = step.transform(ctx, [row(del_chk=1)])
        (bought,) = step.transform(ctx, [row(del_chk=1, application_id=5, _payment_type=1, _application_result=1)])
        self.assertEqual(admin.values["status"], "revoked")
        self.assertEqual(bought.values["status"], "refunded")

    def test_expired_stays_active(self) -> None:
        """新のコースの購入は期限切れを状態にしない（`expires_at` で判定する）。"""
        (record,) = lpe.LearningPathEnrollmentsStep().transform(make_ctx(), [row()])
        self.assertEqual(record.values["status"], "active")
        self.assertIsNotNone(record.values["expires_at"])

    def test_live_subscription_has_expiry(self) -> None:
        """**自動継続の購入も期限を持つ**（いま払っている1か月の終わり。2026-10-23。sync-issues B6）。"""
        (record,) = lpe.LearningPathEnrollmentsStep().transform(
            make_ctx(), [row(application_id=5, _payment_type=1, _application_result=1,
                             _auto_extension=1, _is_cancel=None, authority_end_date=date(2037, 12, 31))])
        self.assertEqual(record.values["status"], "active")
        self.assertEqual(record.values["expires_at"], datetime(2037, 12, 31, 14, 59, 59))


class PaymentLinkTest(unittest.TestCase):
    def test_only_migrated_payments_are_linked(self) -> None:
        """無料の申込は決済にならないので結ばない。お金が動いた申込は決済の ID を結ぶ。"""
        ctx = make_ctx()
        step = lpe.LearningPathEnrollmentsStep()
        (free,) = step.transform(ctx, [row(application_id=5, _payment_type=0, _application_result=1)])
        (paid,) = step.transform(ctx, [row(application_id=6, _payment_type=1, _application_result=1)])
        self.assertIsNone(free.values["payment_id"])
        self.assertEqual(paid.values["payment_id"], ctx.ulid.for_row("payment_application", 6))

    def test_remote_pc_comes_from_the_authority(self) -> None:
        """購入した時点の商品の「リモートPC の利用」（旧 `payment_item_lesson_authority.remote_chk`）。"""
        (record,) = lpe.LearningPathEnrollmentsStep().transform(make_ctx(), [row(remote_chk=1), row(lesson_id=2)])
        self.assertTrue(record.values["remote_pc_enabled"])


class ViaLearningPathTest(unittest.TestCase):
    def test_enrollment_from_item_is_via_learning_path(self) -> None:
        """商品を経た権限の受講登録は、新では講座ごとのリモートPC 対象を効かせない。"""
        ctx = make_ctx()
        step = EnrollmentRightsStep()
        (via,) = step.transform(ctx, [row()])
        (direct,) = step.transform(ctx, [row(item_id=None, authority_key="")])
        self.assertTrue(via.values["via_learning_path"])
        self.assertFalse(direct.values["via_learning_path"])


if __name__ == "__main__":
    unittest.main()
