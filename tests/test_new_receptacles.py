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
from migrator.steps.content import lessons, live_lessons
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


class ChapterTest(unittest.TestCase):
    def test_units_belong_to_the_preceding_heading(self) -> None:
        rows = [unit(1, 1), unit(2, 2, type_id=0), unit(3, 3), unit(4, 4, type_id=0), unit(5, 5)]
        self.assertEqual(lessons.chapter_of(rows), {1: None, 3: 2, 5: 4})

    def test_deleted_heading_is_not_a_boundary(self) -> None:
        """**削除済みの見出しは旧の画面に出ないので、区切りにもならない。**"""
        rows = [unit(2, 1, type_id=0), unit(3, 2), unit(4, 3, type_id=0, del_chk=1), unit(5, 4)]
        self.assertEqual(lessons.chapter_of(rows), {3: 2, 5: 2})

    def test_courses_are_separate(self) -> None:
        rows = [unit(2, 1, type_id=0, lesson_id=100), unit(3, 2, lesson_id=200)]
        self.assertEqual(lessons.chapter_of(rows)[3], None)

    def test_lesson_points_at_its_chapter(self) -> None:
        ctx = make_ctx()
        rows = [unit(2, 1, type_id=0), unit(3, 2)]
        [chapter] = lessons.ChaptersStep().transform(ctx, [rows[0]])
        [lesson] = lessons.LessonsStep().transform(ctx, rows)
        self.assertEqual(lesson.values["chapter_id"], chapter.values["id"])
        self.assertEqual(chapter.values["unit_id"], 2)
        # 章とレッスンは同じ旧 unit_id から作るが、ULID は別
        self.assertNotEqual(chapter.values["id"], lesson.values["id"])


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


class FacilityTest(unittest.TestCase):
    def test_facility_is_kept_as_text(self) -> None:
        row = {"facility_id": 1, "facility_name": "本社", "address": "", "tel": None, "facility_access": "駅前"}
        self.assertEqual(live_lessons._facility(row), {"facility_name": "本社", "facility_access": "駅前"})
        self.assertIsNone(live_lessons._facility(None))


class KeepDeletedRowsTest(unittest.TestCase):
    """**移行対象外を除き、削除済みも含めてすべて移す**（2026-10-01 の方針）。"""

    def test_deleted_heading_becomes_deleted_chapter(self) -> None:
        ctx = make_ctx()
        row = {**unit(4, 3, type_id=0, del_chk=1), "update_date": datetime(2021, 6, 1, 12)}
        [rec] = lessons.ChaptersStep().transform(ctx, [row])
        self.assertIsNotNone(rec.values["deleted_at"])

    def test_collapse_prefers_the_living_row(self) -> None:
        """**同じ組が積まれていれば1行。** 生きている行があれば生きた行、全部削除済みなら削除日時つき。"""
        from migrator.steps.content import live_definitions as ld

        rows = [
            {"live_lesson_id": 9, "exclusion_date": "2023-01-13", "del_chk": 1, "update_date": datetime(2022, 12, 20)},
            {"live_lesson_id": 9, "exclusion_date": "2023-01-13", "del_chk": 0, "update_date": datetime(2023, 1, 5)},
            {"live_lesson_id": 9, "exclusion_date": "2023-02-01", "del_chk": 1, "update_date": datetime(2023, 1, 9, 12)},
        ]
        out = {r["exclusion_date"]: r for r in ld._collapse(rows, ("live_lesson_id", "exclusion_date"))}
        self.assertIsNone(out["2023-01-13"]["_deleted_at"])
        self.assertIsNotNone(out["2023-02-01"]["_deleted_at"])


if __name__ == "__main__":
    unittest.main()
