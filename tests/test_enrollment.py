"""受講区分の変換テスト。**取り違えると気づかないまま誤データになるもの**に絞る。

lw2 の列名は素直に読むと誤るものが多い。ここで固定しているのは
「旧アプリの実装を読んで決めた」3点で、**列名から推測し直すと壊れる**。
"""

from __future__ import annotations

import json
import logging
import unittest
from datetime import date, datetime

from migrator.config import Config, TenantConfig
from migrator.context import build_context
from migrator.db.target import TargetDatabase
from migrator.steps.enrollment import certificates as en_certificates
from migrator.steps.enrollment import progress as en_progress
from migrator.steps.enrollment import rights as en_rights
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


def authority(**over):
    row = {
        "authority_id": 1, "authority_key": "k1", "user_id": 100, "item_id": 5,
        "application_id": None, "lesson_id": 200,
        "authority_start_date": date(2020, 1, 1), "authority_end_date": date(2021, 1, 1),
        "payment_authority_end_date": date(2021, 1, 1),
        "cancel_chk": 1, "no_limit_chk": 0, "payment_no_limit_chk": 0,
        "remote_chk": 0, "del_chk": 0,
        "_auto_extension": 0, "_is_cancel": None, "_cancel_date_time": None,
    }
    row.update(over)
    return row


class RightsTest(unittest.TestCase):
    def _records(self, rows):
        ctx = make_ctx()
        return en_rights.EnrollmentRightsStep().transform(ctx, rows)

    def test_cancel_chk_is_not_a_cancellation(self) -> None:
        """**`cancel_chk = 1` を取り消しにしない。**

        作成時に定数で入るだけの列で、UPDATE されない。取り消しと読むと
        実測 3,684 行中 3,064 行（83%）が `canceled` になる。
        """
        [rec] = self._records([authority(cancel_chk=1, del_chk=0)])
        self.assertNotEqual(rec.values["status"], "revoked")

    def test_del_chk_is_the_cancellation(self) -> None:
        """**実質の取り消しは `del_chk`。**

        `enrollment_statuses` に `canceled` は無い（`active` / `expired` /
        `refunded` / `revoked`）。**`canceled` を入れると FK で落ちる。**
        """
        [rec] = self._records([authority(cancel_chk=0, del_chk=1)])
        self.assertEqual(rec.values["status"], "revoked")

    def test_source_is_purchase_when_an_item_is_linked(self) -> None:
        """商品に紐づく権限は `purchase`。"""
        [rec] = self._records([authority(item_id=5)])
        self.assertEqual(rec.values["source"], "purchase")

    def test_source_is_admin_without_an_item(self) -> None:
        """**商品を経ていない付与は `admin`。**

        実測 3,282行（2,306組）が `item_id` / `application_id` ともに NULL。
        `purchase` にすると `enrollment_sources.is_paid` が立ち、売上集計に乗る。
        """
        [rec] = self._records([authority(item_id=None, application_id=None, authority_key="")])
        self.assertEqual(rec.values["source"], "admin")

    def test_settings_survive_a_null_item_id(self) -> None:
        """**`legacy_item_ids` が `item_id` の NULL で落ちない。**"""
        [rec] = self._records([
            authority(authority_id=1, item_id=None),
            authority(authority_id=2, item_id=5),
        ])
        self.assertEqual(json.loads(rec.values["settings"])["legacy_item_ids"], [5])

    def test_rows_are_folded_by_user_and_course(self) -> None:
        """**lw2 と同じ粒度に畳む**（`LessonModel::1804` の `GROUP BY`）。"""
        recs = self._records([
            authority(authority_id=1, item_id=5),
            authority(authority_id=2, item_id=9),   # 別商品・同じ講座
            authority(authority_id=3, lesson_id=201),
        ])
        self.assertEqual(len(recs), 2)

    def test_expiry_takes_the_max(self) -> None:
        """**期限は `MAX()`。** 短い方を採ると受講できる期間が縮む。"""
        [rec] = self._records([
            authority(authority_id=1, authority_end_date=date(2021, 1, 1)),
            authority(authority_id=2, authority_end_date=date(2023, 6, 30)),
        ])
        self.assertEqual(rec.values["expires_at"].date(), date(2023, 6, 30))

    def test_expiry_is_end_of_day_in_jst(self) -> None:
        """**終了日は JST の 23:59:59 で補い、UTC で持つ。**

        00:00 にすると期限日当日が切れる。JST を UTC に直すと**前日 15:00**に
        なるので、境界を明示しないと1日ずれる（`DateBoundary`）。
        """
        [rec] = self._records([authority(authority_end_date=date(2021, 1, 1))])
        self.assertEqual(rec.values["expires_at"], datetime(2021, 1, 1, 14, 59, 59))

    def test_unlimited_clears_the_expiry(self) -> None:
        """`no_limit_chk = 1` は無期限。**元の値は settings に残す。**"""
        [rec] = self._records([authority(no_limit_chk=1)])
        self.assertIsNone(rec.values["expires_at"])
        self.assertTrue(json.loads(rec.values["settings"])["unlimited"])

    def test_deleted_rows_do_not_hide_a_live_one(self) -> None:
        """生きている行が1つでもあれば `active`。"""
        [rec] = self._records([
            authority(authority_id=1, del_chk=1),
            authority(authority_id=2, del_chk=0),
        ])
        self.assertNotEqual(rec.values["status"], "revoked")

    def test_past_expiry_becomes_expired(self) -> None:
        """期限切れは `expired`。実測で 1,874組中 1,603組（86%）が該当する。"""
        [rec] = self._records([authority(authority_end_date=date(2021, 1, 1))])
        self.assertEqual(rec.values["status"], "expired")

    def test_future_expiry_stays_active(self) -> None:
        [rec] = self._records([authority(authority_end_date=date(2099, 1, 1))])
        self.assertEqual(rec.values["status"], "active")

    def test_unlimited_is_active(self) -> None:
        """無期限は `expires_at` が NULL なので、期限切れ判定に落ちない。"""
        [rec] = self._records([authority(no_limit_chk=1)])
        self.assertEqual(rec.values["status"], "active")

    def test_far_future_expiry_is_treated_as_unlimited(self) -> None:
        """**`TIMESTAMP` の上限を超える期限は無期限に寄せる。**

        旧は無期限を100年後の日付で表す（実測 2124-06-24）。そのまま入れると
        実 INSERT で `Incorrect datetime value` になる。
        """
        [rec] = self._records([authority(authority_end_date=date(2124, 6, 24))])
        self.assertIsNone(rec.values["expires_at"])
        self.assertEqual(rec.values["status"], "active")
        settings = json.loads(rec.values["settings"])
        self.assertTrue(settings["unlimited"])
        self.assertIn("2124-06-24", settings["legacy_expires_at_beyond_timestamp"])

    def test_source_is_purchase(self) -> None:
        """`manual` という値は存在しない（`enrollment_sources` の5値）。"""
        [rec] = self._records([authority()])
        self.assertEqual(rec.values["source"], "purchase")

    def test_legacy_item_ids_are_kept(self) -> None:
        """**畳んだ商品を捨てない。** 課金（4）の移行後に紐付け直す。"""
        [rec] = self._records([
            authority(authority_id=1, item_id=5),
            authority(authority_id=2, item_id=9),
        ])
        self.assertEqual(json.loads(rec.values["settings"])["legacy_item_ids"], [5, 9])


class SubscriptionRightsTest(unittest.TestCase):
    """**自動継続は期限で切らない。** lw2 の判定は `is_cancel IS NULL` だけ。"""

    def _records(self, rows):
        ctx = make_ctx()
        return en_rights.EnrollmentRightsStep().transform(ctx, rows)

    def test_live_subscription_ignores_past_expiry(self) -> None:
        """**ここが本丸。** 期限が過去でも未解約なら受講できる。

        期限をそのまま写すと、**いま受講できている人が失効扱いになる**
        （ステージング実測で 249 組が該当した）。
        """
        [rec] = self._records([authority(
            authority_end_date=date(2021, 1, 1), _auto_extension=1, _is_cancel=None)])
        self.assertEqual(rec.values["status"], "active")
        self.assertIsNone(rec.values["expires_at"])

    def test_canceled_subscription_is_revoked_not_expired(self) -> None:
        """解約済みは `revoked`。**期限切れ（`expired`）ではない。**"""
        [rec] = self._records([authority(
            authority_end_date=date(2021, 1, 1), _auto_extension=1, _is_cancel=1)])
        self.assertEqual(rec.values["status"], "revoked")

    def test_one_live_subscription_wins_over_expired_rows(self) -> None:
        """**lw2 の判定は OR。** 1つでも生きていれば受講できる。"""
        [rec] = self._records([
            authority(authority_id=1, authority_end_date=date(2021, 1, 1), _auto_extension=0),
            authority(authority_id=2, authority_end_date=date(2021, 1, 1),
                      _auto_extension=1, _is_cancel=None),
        ])
        self.assertEqual(rec.values["status"], "active")
        self.assertIsNone(rec.values["expires_at"])

    def test_original_expiry_is_kept_in_settings(self) -> None:
        """期限を写さない代わりに、元の値を残す。"""
        [rec] = self._records([authority(
            authority_end_date=date(2021, 1, 1), _auto_extension=1)])
        settings = json.loads(rec.values["settings"])
        self.assertTrue(settings["subscription"])
        self.assertIn("2021-01-01", settings["legacy_authority_end_dates"])

    def test_non_subscription_still_expires(self) -> None:
        """買い切りは従来どおり期限で切れる。"""
        [rec] = self._records([authority(
            authority_end_date=date(2021, 1, 1), _auto_extension=0)])
        self.assertEqual(rec.values["status"], "expired")


class AccessDaysTest(unittest.TestCase):
    def test_zero_becomes_null(self) -> None:
        """**旧 `open_period = 0` は「指定なし」。** 0 のまま入れると
        API のバリデーション（`min=1`）に引っかかり、管理画面から編集できなくなる。
        """
        from migrator.steps.content.courses import _access_days
        self.assertIsNone(_access_days(0))
        self.assertIsNone(_access_days(None))
        self.assertEqual(_access_days(7), 210)   # 7ヶ月 = 210日

    def test_months_are_converted_to_days(self) -> None:
        """**単位が違う。** 旧は月、新は日。換算しないと受講期間が 1/30 になる。"""
        from migrator.steps.content.courses import _access_days
        self.assertEqual(_access_days(1), 30)
        self.assertEqual(_access_days(12), 360)


def unit_row(**over):
    row = {
        "user_learning_unit_id": 1, "user_learning_lesson_id": 10, "unit_id": 300,
        "learning_status": 1, "complete_date": datetime(2021, 5, 1, 12, 0),
        "progress_status": 2, "score": None, "suspend_data": None,
        "update_date": datetime(2021, 5, 1, 12, 0), "del_chk": 0,
    }
    row.update(over)
    return row


class ProgressTest(unittest.TestCase):
    def _records(self, rows, kinds=None, owners=None):
        ctx = make_ctx()
        step = en_progress.LessonProgressStep()
        step._owners = owners or {10: 100}
        step._kinds = kinds or {300: 2}
        return step.transform(ctx, rows)

    def test_progress_status_keeps_the_unit_kind(self) -> None:
        """**種別を落とすと意味が復元できない。**

        同じ `2` がテストなら「受験中」、アンケートなら「回答済」。
        """
        [quiz] = self._records([unit_row()], kinds={300: 2})
        [survey] = self._records([unit_row()], kinds={300: 3})
        self.assertEqual(quiz.values["progress_status"], "quiz:2")
        self.assertEqual(survey.values["progress_status"], "survey:2")
        self.assertEqual(json.loads(quiz.values["settings"])["progress_label"], "受験中")
        self.assertEqual(json.loads(survey.values["settings"])["progress_label"], "回答済")

    def test_lecture_progress_is_not_guessed(self) -> None:
        """**講義（`unit_type_id = 1`）は定数ファイルに定義が無い。** 畳まない。"""
        [rec] = self._records([unit_row()], kinds={300: 1})
        self.assertEqual(rec.values["progress_status"], "lecture:2")
        self.assertTrue(json.loads(rec.values["settings"])["progress_label_unknown"])

    def test_completed_at_follows_learning_status(self) -> None:
        """**修了は `learning_status`。** 実測で `complete_date` と完全に一致する。"""
        [done] = self._records([unit_row(learning_status=1)])
        [todo] = self._records([unit_row(learning_status=0, complete_date=None)])
        self.assertIsNotNone(done.values["completed_at"])
        self.assertIsNone(todo.values["completed_at"])

    def test_suspend_data_does_not_go_to_last_position(self) -> None:
        """**SCORM の中断データを再生位置に入れない。** 形式が違う。"""
        [rec] = self._records([unit_row(suspend_data="lesson_location=5;score=80")])
        self.assertIsNone(rec.values["last_position"])
        self.assertEqual(
            json.loads(rec.values["settings"])["suspend_data"], "lesson_location=5;score=80")

    def test_duplicates_keep_the_newest(self) -> None:
        """`(会員, ユニット)` は UNIQUE。**制約は緩めず、新しい方を残す。**"""
        recs = self._records([
            unit_row(user_learning_unit_id=1, update_date=datetime(2020, 1, 1), progress_status=1),
            unit_row(user_learning_unit_id=2, update_date=datetime(2022, 1, 1), progress_status=3),
        ])
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0].values["progress_status"], "quiz:3")

    def test_deleted_rows_are_migrated_with_a_marker(self) -> None:
        """**削除済みも移す**（移行の原則の1）。`deleted_at` で表す。"""
        [rec] = self._records([unit_row(del_chk=1)])
        self.assertIsNotNone(rec.values["deleted_at"])


if __name__ == "__main__":
    unittest.main()


class BadgeDefinitionsTest(unittest.TestCase):
    """**バッジは定義と付与実績で置き場所が違う。**

    定義は lw2 の `badge_item` にあるが、付与実績は外部のバッジシステムにあり
    lw2 の DB に無い。`digital_badges`（付与1枚）に定義は入らない。
    """

    def _records(self, rows):
        ctx = make_ctx()
        return en_certificates.BadgeDefinitionsStep().transform(ctx, rows)

    def _row(self, **over):
        row = {"item_id": 1, "item_type": "lesson", "entity_id": 2506,
               "reference_item_id": None, "update_date": None, "del_chk": 0}
        row.update(over)
        return row

    def test_lesson_goes_to_courses(self) -> None:
        """**旧 `lesson` は講座。** 新環境の `lessons`（ユニット）ではない。"""
        ctx = make_ctx()
        [rec] = en_certificates.BadgeDefinitionsStep().transform(ctx, [self._row(item_type="lesson")])
        self.assertEqual(rec.values["course_id"], ctx.ulid.for_row("lesson", 2506))
        self.assertIsNone(rec.values["lesson_id"])

    def test_unit_goes_to_lessons(self) -> None:
        ctx = make_ctx()
        [rec] = en_certificates.BadgeDefinitionsStep().transform(ctx, [self._row(item_type="unit")])
        self.assertEqual(rec.values["lesson_id"], ctx.ulid.for_row("unit", 2506))
        self.assertIsNone(rec.values["course_id"])

    def test_reference_is_the_external_badge_id(self) -> None:
        """`reference_item_id` は**外部のバッジシステムの ID**。自己参照ではない。

        `BadgeController:838` が `putBadge()` の戻り値 `$json['ID']` を書いている。
        ULID に読み替えると、**参照先の無い外部キーになって行ごと落ちる**。
        """
        ctx = make_ctx()
        [rec] = en_certificates.BadgeDefinitionsStep().transform(ctx, [self._row(reference_item_id=771)])
        self.assertEqual(rec.values["external_badge_id"], 771)

    def test_unknown_item_type_is_skipped(self) -> None:
        """**対応表に無い種別は黙って講座に倒さない。** 警告して移さない。"""
        self.assertEqual(self._records([self._row(item_type="product")]), [])

    def test_exactly_one_target_is_set(self) -> None:
        """`chk_badge_definitions_target` が「どちらか一方」を要求する。"""
        for kind in ("lesson", "unit"):
            [rec] = self._records([self._row(item_type=kind)])
            both = (rec.values["course_id"] is None) == (rec.values["lesson_id"] is None)
            self.assertFalse(both, f"{kind}: 片方だけが入るべき")


class CertificateSettingsTest(unittest.TestCase):
    """修了証のテナント設定。**採番カウンタは別テーブルにある。**"""

    def _extract(self, config_rows, serial_rows):
        ctx = make_ctx({"config_certificate": config_rows, "certificate_no": serial_rows})
        step = en_certificates.CertificateSettingsStep()
        return ctx, step.transform(ctx, step.extract(ctx))

    def test_serial_next_is_carried_over(self) -> None:
        """**旧の次番号を引き継がないと、cutover 後の採番が既存の証書と衝突する。**

        新環境の既定は 1。旧が 7 まで進んでいれば No.4〜6 と重複する。
        """
        _, [rec] = self._extract(
            [{"tenant_id": 10, "message": "m", "issuer_name": None,
              "regist_date": datetime(2024, 5, 24)}],
            [{"tenant_id": 10, "certificate_no": 7, "regist_date": datetime(2024, 5, 24)}],
        )
        self.assertEqual(rec.values["serial_next"], 7)

    def test_row_is_created_for_the_counter_alone(self) -> None:
        """**`config_certificate` が空でも、採番カウンタだけで行を作る。**

        実測の ReCADemy がこれ（文面の設定は 0 行、カウンタだけ 1 行）。
        設定行が無いからと作らないと採番が 1 に戻る。
        """
        _, recs = self._extract(
            [], [{"tenant_id": 10, "certificate_no": 7, "regist_date": datetime(2024, 5, 24)}]
        )
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0].values["serial_next"], 7)
        # `created_at` は NOT NULL。カウンタの登録日で埋まっていること
        self.assertIsNotNone(recs[0].values["created_at"])

    def test_nothing_is_created_without_either(self) -> None:
        """**どちらも無ければ作らない。** 既定値だけの行は「運営の設定」と区別できない。"""
        _, recs = self._extract([], [])
        self.assertEqual(recs, [])


class CertificatesTest(unittest.TestCase):
    """発行済みの修了証。**`entity_id` の読み違いで全件落ちていた。**"""

    def test_entity_id_is_the_learning_row_not_the_course(self) -> None:
        """**`certificate_type = 1` の `entity_id` は `user_learning_lesson_id`。**

        `LessonController:3668` の `$entityId = $userLearningLessonId`。講座 ID と
        取り違えると `certificates.course_id` が参照先なしになり、**3件とも落ちる**。
        """
        ctx = make_ctx({
            "config_certificate": [],
            "user_certificate": [{
                "user_id": 3076, "certificate_id": 1, "certificate_type": 1,
                "entity_id": 35480, "certificate_no": 6,
                "regist_date": datetime(2025, 11, 10), "update_date": datetime(2025, 11, 10),
            }],
            "user_learning_lesson": [
                {"user_learning_lesson_id": 35480, "lesson_id": 2100040382},
            ],
        })
        step = en_certificates.CertificatesStep()
        [rec] = step.transform(ctx, step.extract(ctx))
        self.assertEqual(rec.values["course_id"], ctx.ulid.for_row("lesson", 2100040382))
        self.assertNotEqual(rec.values["course_id"], ctx.ulid.for_row("lesson", 35480))
