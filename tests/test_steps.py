"""Step の結合テスト。**DB を立てずに extract → transform まで通す。**"""

from __future__ import annotations

import logging
import unittest
from datetime import date, datetime

from migrator.config import Config, TenantConfig
from migrator.context import build_context
from migrator.db.target import TargetDatabase
from migrator.errors import PreflightError
from migrator.steps.tenant import TenantStep
from migrator.steps.user_related import NotificationOptoutsStep, UserAddressesStep
from migrator.steps.users import UsersStep
from tests.fakes import FakeSource

CONFIG = Config(
    tenant=TenantConfig(legacy_id=12, slug="recademy", name="ReCADemy"),
    ulid_namespace="lw2-test",
    mappings={
        "role": {"source": "テスト", "values": {2: "tenant_admin", 7: "learner"}},
        "prefecture": {"values": {13: "東京都"}},
        # テストでは bcrypt のコストを下げる（本番は新環境と同じ 10）
        "password": {"bcrypt_cost": 4},
    },
    legacy_crypt_key="test-key",
)

TENANT_ROW = {
    "tenant_id": 12,
    "tenant_code": "recademy",
    "tenant_name": "ReCADemy",
    "tenent_name_short": "RCD",
    "language_code": "ja",
    "del_chk": 0,
    "regist_date": datetime(2019, 8, 28, 14, 29, 17),
}

USER_ROW = {
    "user_id": 101,
    "tenant_id": 12,
    "login_id": "taro",
    "role_id": 7,
    "name_sei": "山田",
    "name_mei": "太郎",
    "kana_sei": "ヤマダ",
    "kana_mei": "タロウ",
    "mail_add": "taro@example.test",
    "mobile_mail_add": "taro@mobile.test",
    "tel": "03-1234-5678",
    "mobile_tel": "090-1234-5678",
    "nick_name": "たろ",
    "sex_type": 1,
    "birth_date": datetime(1990, 5, 3, 0, 0, 0),
    "blood_type": 1,
    "self_introduction": "よろしく",
    "entry_date": date(2020, 4, 1),
    "limit_date": date(2027, 3, 31),
    "user_memo": "メモ",
    "system_data": None,
    "recent_login_date": datetime(2026, 9, 1, 10, 0, 0),
    "recent_access_time": datetime(2026, 9, 1, 10, 30, 0),
    "total_login_count": 12,
    "password_change_date": date(2025, 1, 1),
    "is_lockout": 0,
    "start_date_failing_login": None,
    "number_of_failing_login": 0,
    "valid_chk": 1,
    "del_chk": 0,
    "new_user_chk": 0,
    "regist_date": datetime(2020, 4, 1, 9, 0, 0),
    "update_date": datetime(2026, 9, 1, 9, 0, 0),
    "zip_code": "1000001",
    "pref_id": 13,
    "city_name": "千代田区",
    "address": "千代田1-1 ビル101",
    "zip_code2": None,
    "pref_id2": None,
    "city_name2": None,
    "address2": None,
    "sendmail_pc_chk": 1,
    "sendmail_mobile_chk": 0,
    "sendmail_scout_chk": 1,
    "notify_footprint_pc_chk": 1,
    "notify_footprint_mobile_chk": 1,
}


def make_ctx(tables: dict) -> object:
    ctx = build_context(
        CONFIG,
        FakeSource(tables),
        TargetDatabase(None, dry_run=True),
        logging.getLogger("test"),
    )
    return ctx


class TenantStepTest(unittest.TestCase):
    def test_creates_one_row_and_fixes_tenant_id(self) -> None:
        ctx = make_ctx({"tenant": [TENANT_ROW]})
        records = TenantStep().transform(ctx, [TENANT_ROW])
        self.assertEqual(len(records), 1)
        values = records[0].values
        self.assertEqual(values["slug"], "recademy")
        self.assertEqual(values["status"], "active")  # 既定値の trial に任せない
        self.assertEqual(values["db_type"], "shared")
        self.assertIsNone(values["plan_id"])
        self.assertEqual(values["short_name"], "RCD")
        self.assertTrue(ctx.tenant_id.resolved)

    def test_deleted_tenant_stops(self) -> None:
        ctx = make_ctx({"tenant": [TENANT_ROW]})
        with self.assertRaises(PreflightError):
            TenantStep().transform(ctx, [{**TENANT_ROW, "del_chk": 1}])

    def test_missing_name_stops(self) -> None:
        config = Config(tenant=TenantConfig(legacy_id=12, slug="recademy", name=None))
        ctx = build_context(config, FakeSource({}), TargetDatabase(None, dry_run=True))
        with self.assertRaises(PreflightError):
            TenantStep().transform(ctx, [{**TENANT_ROW, "tenant_name": None}])


class UsersStepTest(unittest.TestCase):
    def setUp(self) -> None:
        self.ctx = make_ctx({"tenant": [TENANT_ROW], "user": [USER_ROW]})
        self.ctx.tenant_id.resolve("0" * 26)
        self.records = UsersStep().transform(self.ctx, [USER_ROW])

    def test_invalid_member_stays_invalid(self) -> None:
        """**`valid_chk = 0` を有効にしない。** `or 1` と書くと 0 が 1 に化けていた。"""
        [rec] = UsersStep().transform(self.ctx, [{**USER_ROW, "valid_chk": 0, "del_chk": 0}])
        self.assertEqual((rec.values["is_valid"], rec.values["status"]), (False, "inactive"))
        [rec] = UsersStep().transform(self.ctx, [{**USER_ROW, "valid_chk": None}])
        self.assertTrue(rec.values["is_valid"])

    def test_name_is_split_and_generated(self) -> None:
        """姓 / 名は分割のまま持ち、name は生成する。"""
        values = self.records[0].values
        self.assertEqual(values["name_last"], "山田")
        self.assertEqual(values["name_first"], "太郎")
        self.assertEqual(values["name"], "山田 太郎")

    def test_phones_are_not_collapsed(self) -> None:
        values = self.records[0].values
        self.assertEqual(values["phone"], "03-1234-5678")
        self.assertEqual(values["mobile_phone"], "090-1234-5678")

    def test_birthday_kept_as_three_columns(self) -> None:
        values = self.records[0].values
        self.assertEqual((values["birth_year"], values["birth_month"], values["birth_day"]), (1990, 5, 3))

    def test_status_does_not_swallow_original_flags(self) -> None:
        """status は判定結果。元の列（is_valid / 期間）も残す。"""
        values = self.records[0].values
        self.assertEqual(values["status"], "active")
        self.assertTrue(values["is_valid"])
        # login_start_date / login_end_date は date 列。日付のまま持つのでズレない
        self.assertEqual(values["login_start_date"], date(2020, 4, 1))
        self.assertEqual(values["login_end_date"], date(2027, 3, 31))

    def test_avatar_is_not_migrated(self) -> None:
        self.assertIsNone(self.records[0].values["avatar_url"])

    def test_missing_email_stays_empty(self) -> None:
        """**合成アドレスを作らない。** 空のまま出し、制約チェックで移行対象から外す。

        作り替えて通すと、どれが本物のアドレスか分からなくなる。
        """
        records = UsersStep().transform(self.ctx, [{**USER_ROW, "mail_add": None}])
        self.assertIsNone(records[0].values["email"])

    def test_duplicate_email_is_left_as_is(self) -> None:
        """**統合も作り替えもしない。** 重複したまま出し、制約チェックに任せる。"""
        rows = [USER_ROW, {**USER_ROW, "user_id": 102, "mail_add": USER_ROW["mail_add"].upper()}]
        records = UsersStep().transform(self.ctx, rows)
        emails = [r.values["email"] for r in records]
        self.assertEqual(emails, ["taro@example.test", "TARO@EXAMPLE.TEST"])

    def test_null_role_is_not_filled_in(self) -> None:
        """`role_id` が NULL の会員は**既定値に倒さない**（権限が静かに変わる）。"""
        records = UsersStep().transform(self.ctx, [{**USER_ROW, "role_id": None}])
        self.assertIsNone(records[0].values["role"])

    def test_source_key_is_the_legacy_id(self) -> None:
        """移さなかった行の一覧で「誰が」を出すために、旧 `user_id` を持たせる。"""
        records = UsersStep().transform(self.ctx, [USER_ROW])
        self.assertEqual(records[0].source_key, USER_ROW["user_id"])


class UserRelatedTest(unittest.TestCase):
    def setUp(self) -> None:
        self.ctx = make_ctx({"user": [USER_ROW]})
        self.ctx.tenant_id.resolve("0" * 26)

    def test_prefecture_comes_from_pref_master_when_config_is_empty(self) -> None:
        """**都道府県は旧 DB の `pref_master` から引く。**

        47件を設定に手で持つと、書き漏れた1件で住所の移行が止まる。
        `pref_name` はコード（`PREF_CODE_13`）で、**名称は `description`**。
        """
        from migrator.config import Config, TenantConfig
        from migrator.steps.user_related import UserAddressesStep

        config = Config(
            tenant=TenantConfig(legacy_id=12, slug="recademy", name="R"),
            mappings={"role": {"values": {7: "learner"}}},  # prefecture は書かない
        )
        ctx = build_context(
            config,
            FakeSource({"pref_master": [{"pref_id": 13, "description": "東京都"}]}),
            TargetDatabase(None, dry_run=True),
            logging.getLogger("test"),
        )
        ctx.tenant_id.resolve("0" * 26)
        records = UserAddressesStep().transform(ctx, [USER_ROW])
        self.assertEqual(records[0].values["prefecture"], "東京都")

    def test_address_is_split_into_four(self) -> None:
        records = UserAddressesStep().transform(self.ctx, [USER_ROW])
        self.assertEqual(len(records), 1)  # 住所2は空なので作らない
        values = records[0].values
        self.assertEqual(values["kind"], "primary")
        self.assertEqual(values["postal_code"], "1000001")
        self.assertEqual(values["prefecture"], "東京都")  # コード値のまま入れない
        self.assertEqual(values["city"], "千代田区")
        self.assertEqual(values["street"], "千代田1-1 ビル101")

    def test_optout_polarity_is_inverted(self) -> None:
        """lw2 の「受け取る」→ 新環境の「受け取らない」。"""
        records = NotificationOptoutsStep().transform(self.ctx, [USER_ROW])
        made = {(r.values["kind"], r.values["channel"]) for r in records}
        self.assertEqual(made, {("announcement", "mobile")})


if __name__ == "__main__":
    unittest.main()


GROUP_ROWS = [
    {"group_id": 1, "parent_group_id": 0, "hierarchy": 0, "group_name": "本社",
     "group_code": "HQ", "memo": None, "sort_no": 1, "del_chk": 0,
     "regist_date": datetime(2020, 1, 1), "update_date": datetime(2020, 1, 1)},
    {"group_id": 2, "parent_group_id": 1, "hierarchy": 1, "group_name": "営業部",
     "group_code": "SALES", "memo": None, "sort_no": 2, "del_chk": 0,
     "regist_date": datetime(2020, 1, 1), "update_date": datetime(2020, 1, 1)},
]


class OrgStepTest(unittest.TestCase):
    """グループ・属性・担当範囲。**階層は parent_id で持ち、group_structure は作らない。**"""

    def setUp(self) -> None:
        self.ctx = make_ctx({"group": GROUP_ROWS})
        self.ctx.tenant_id.resolve("0" * 26)

    def test_hierarchy_uses_parent_id(self) -> None:
        from migrator.steps.org import GroupsStep

        records = GroupsStep().transform(self.ctx, GROUP_ROWS)
        by_legacy = {r.values["legacy_id"]: r.values for r in records}
        self.assertIsNone(by_legacy[1]["parent_id"])                    # 根は NULL
        self.assertEqual(by_legacy[2]["parent_id"], by_legacy[1]["id"])  # 子は親の ULID
        self.assertEqual(by_legacy[2]["depth"], 1)

    def test_parents_come_before_children(self) -> None:
        """親より先に子を入れると FK 違反になる。"""
        from migrator.steps.org import GroupsStep

        depths = [r.values["depth"] for r in GroupsStep().transform(self.ctx, GROUP_ROWS)]
        self.assertEqual(depths, sorted(depths))

    def test_missing_parent_falls_back_to_root(self) -> None:
        from migrator.steps.org import GroupsStep

        orphan = [{**GROUP_ROWS[1], "parent_group_id": 999}]
        records = GroupsStep().transform(self.ctx, orphan)
        self.assertIsNone(records[0].values["parent_id"])

    def test_deleted_group_uses_timestamp_not_flag(self) -> None:
        from migrator.steps.org import GroupsStep

        deleted = [{**GROUP_ROWS[0], "del_chk": 1}]
        self.assertIsNotNone(GroupsStep().transform(self.ctx, deleted)[0].values["deleted_at"])

    def test_instructor_course_target_is_null_until_courses_migrate(self) -> None:
        """講座は未移行なので target_id は NULL、旧 ID を残す。"""
        from migrator.steps.org import InstructorAssignmentsStep

        rows = [{"scope": "course", "user_id": 5, "target": 77}]
        values = InstructorAssignmentsStep().transform(self.ctx, rows)[0].values
        self.assertIsNone(values["target_id"])
        self.assertEqual(values["legacy_target_id"], 77)

    def test_instructor_group_target_is_resolved(self) -> None:
        from migrator.steps.org import InstructorAssignmentsStep

        rows = [{"scope": "group", "user_id": 5, "target": 1}]
        values = InstructorAssignmentsStep().transform(self.ctx, rows)[0].values
        self.assertEqual(values["target_id"], self.ctx.ulid.for_row("group", 1))


class VisibilityStepTest(unittest.TestCase):
    """公開制限は**極性を反転しない**（通知の optout とは違う）。"""

    def test_open_chk_is_copied_as_is(self) -> None:
        from migrator.steps.user_related import UserFieldVisibilityStep

        ctx = make_ctx({})
        ctx.tenant_id.resolve("0" * 26)
        row = {"user_id": 1, "profile_open_chk": 1, "name_open_chk": 0,
               "address_open_chk": None, "birthday_open_chk": 1,
               "diary_open_chk": 0, "lesson_open_chk": 1}
        made = {r.values["field_code"]: r.values["visible"]
                for r in UserFieldVisibilityStep().transform(ctx, [row])}
        self.assertEqual(made, {"profile": True, "name": False, "birthday": True,
                                "diary": False, "lesson": True})  # None の列は作らない
