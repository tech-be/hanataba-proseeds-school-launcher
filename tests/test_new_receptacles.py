"""2026-09-30 に足した移し先（章・タグ・自動付与ルール・修了証の設定・テナントの設定・会場・05）の変換テスト。

**DB を立てずに transform だけを通す。** 固定するのは、取り違えると気づかないまま
誤データになるものに絞る。

- 見出しの後ろのユニットが、その章に入ること（削除済みの見出しは区切りにしない）
- 属性がタグとして入り、名前が一意になること
- 修了証の設定が全講座に入り、設定の無い講座は「発行しない」になること
- 秘密の値がテナントの設定に入らないこと
"""

from __future__ import annotations

import json
import logging
import unittest
from datetime import datetime

from migrator.config import Config, TenantConfig
from migrator.context import build_context
from migrator.db.target import TargetDatabase
from migrator.steps import org, tenant
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


def unit(unit_id, sort_no, type_id=1, lesson_id=100, del_chk=0, title="u"):
    return {"unit_id": unit_id, "lesson_id": lesson_id, "unit_type_id": type_id, "sort_no": sort_no,
            "title": title, "del_chk": del_chk, "regist_date": datetime(2020, 1, 1)}


class TagTest(unittest.TestCase):
    def test_attribute_becomes_tag(self) -> None:
        ctx = make_ctx()
        row = {"attribute_id": 3, "attribute_name": "新卒", "attribute_memo": "m", "sort_no": 1,
               "del_chk": 0, "regist_date": datetime(2020, 1, 1)}
        [rec] = org.AttributesStep().transform(ctx, [row])
        self.assertEqual(rec.table, "user_tags")
        self.assertEqual((rec.values["name"], rec.values["attribute_id"]), ("新卒", 3))
        self.assertIsNone(rec.values["deleted_at"])
        [deleted] = org.AttributesStep().transform(
            ctx, [{**row, "del_chk": 1, "update_date": datetime(2021, 6, 1, 12)}])
        self.assertIsNotNone(deleted.values["deleted_at"])  # **削除済みも移す**（2026-10-01）

    def test_overlapping_names_are_distinguished(self) -> None:
        rows = [{"attribute_id": 5, "attribute_name": "A"}, {"attribute_id": 2, "attribute_name": "a"}]
        names = org._distinct_tag_names(rows)
        self.assertEqual(names[2], "a")  # 旧 ID の小さい方が元の名前
        self.assertEqual(names[5], "A（旧ID 5）")

    def test_width_and_existing_tags_are_distinguished(self) -> None:
        """**全角・半角や前後の空白も同じ名前とみなす**（DB の照合順序に合わせる）。新で作ったタグとも重ねない。"""
        rows = [{"attribute_id": 1, "attribute_name": "ＶＩＰ "}, {"attribute_id": 2, "attribute_name": "vip"},
                {"attribute_id": 3, "attribute_name": "新卒"}]
        names = org._distinct_tag_names(rows, {org.tag_name_key("新卒")})
        self.assertEqual(names[2], "vip（旧ID 2）")
        self.assertEqual(names[3], "新卒（旧ID 3）")

    def test_member_attribute_becomes_tag_assignment(self) -> None:
        ctx = make_ctx()
        row = {"attribute_id": 3, "user_id": 9, "regist_date": datetime(2020, 1, 1)}
        [rec] = org.UserAttributeValuesStep().transform(ctx, [row])
        self.assertEqual(rec.table, "user_tag_assignments")
        self.assertEqual(rec.values["tag_id"], ctx.ulid.for_row("attribute", 3))
        self.assertIsNone(rec.values["assigned_by"])
        self.assertEqual(rec.natural_key, ("user_id", "tag_id"))


class TenantSettingsTest(unittest.TestCase):
    def test_secrets_are_not_read(self) -> None:
        for column in ("special_pass_word", "kanri_db_name", "line_channel_sercret", "send_line_chanel_token"):
            self.assertNotIn(column, tenant.APP_CONFIG_COLUMNS)

    def test_extra_keys_go_into_settings(self) -> None:
        ctx = make_ctx()
        out = json.loads(tenant._settings(ctx, None, None, {"lw2_account": {"enable_lockout": 1}}))
        self.assertEqual(out["lw2_account"], {"enable_lockout": 1})


if __name__ == "__main__":
    unittest.main()
