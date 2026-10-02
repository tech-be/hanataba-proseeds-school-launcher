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
from migrator.steps.billing import assign
from migrator.steps.content import lessons, live_lessons
from migrator.steps.enrollment import certificates
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


class AssignTest(unittest.TestCase):
    def test_trigger_kind_follows_payment_trigger(self) -> None:
        """**暫定の規則（P15）。** 商品のきっかけがあれば購入、無ければ会員登録。"""
        ctx = make_ctx()
        rows = [{"assign_id": 1, "login_chk": 1, "del_chk": 0, "_has_trigger": False},
                {"assign_id": 9, "login_chk": 0, "del_chk": 1, "_has_trigger": True}]
        first, second = assign.RulesStep().transform(ctx, rows)
        self.assertEqual((first.values["trigger_kind"], first.values["login_only"]), ("registration", True))
        self.assertEqual((second.values["trigger_kind"], second.values["active"]), ("purchase", False))
        self.assertEqual(first.values["name"], "旧 自動割当 #1")

    def test_grant_kinds(self) -> None:
        ctx = make_ctx()
        self.assertEqual(assign.grant_of(ctx, {"item_type": "lesson", "entity_id": 7}),
                         ("course", ctx.ulid.for_row("lesson", 7)))
        self.assertEqual(assign.grant_of(ctx, {"item_type": "news", "entity_id": 7})[0], "announcement")
        self.assertIsNone(assign.grant_of(ctx, {"item_type": "unknown", "entity_id": 7}))


class CoursePolicyTest(unittest.TestCase):
    def test_every_course_gets_a_policy(self) -> None:
        """**行が無い = 発行する** なので、設定の無い講座にも「発行しない」の行を入れる。"""
        ctx = make_ctx()
        rows = [{"lesson_id": 1, "certificate_id": 5}, {"lesson_id": 2, "certificate_id": None},
                {"lesson_id": 3, "certificate_id": 0}]
        recs = certificates.CoursePoliciesStep().transform(ctx, rows + [{"_host_course": True}])
        issue = {r.values["course_id"]: r.values["issue"] for r in recs}
        self.assertEqual(issue[ctx.ulid.for_row("lesson", 1)], True)
        self.assertEqual(issue[ctx.ulid.for_row("lesson", 2)], False)
        self.assertEqual(issue[ctx.ulid.for_row("lesson", 3)], False)
        self.assertEqual(len(recs), 4)  # 受け皿講座（ライブ）の分
        self.assertFalse(recs[-1].values["issue"])
        # どの行も同じ列を書く（そろっていないと、投入がエラーで止まる）
        self.assertEqual(len({tuple(sorted(r.values)) for r in recs}), 1)

    def test_no_host_course_row_without_unrestricted_lives(self) -> None:
        """**受け皿講座を作らないテナントでは、その行も作らない**（外部キーに当たるため）。"""
        ctx = make_ctx()
        recs = certificates.CoursePoliciesStep().transform(ctx, [{"lesson_id": 1, "certificate_id": 5}])
        self.assertEqual(len(recs), 1)


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


class FixedMisreadsTest(unittest.TestCase):
    """2026-09-30 に直した移行ツールの誤り3つ。"""

    def test_eval_files_go_to_the_feedback(self) -> None:
        """**`eval_*` は添削者のファイル。** 受講者の提出ファイルではなく、添削に付ける。"""
        from migrator.steps.enrollment import results

        ctx = make_ctx()
        row = {"user_learning_report_id": 5, "evaluate_date": datetime(2020, 1, 2),
               "eval_save_file_name1": "a.pdf", "eval_disp_file_name1": "講評.pdf",
               "eval_save_file_name3": "b.pdf"}
        recs = results.FeedbackFilesStep().transform(ctx, [row])
        submission = ctx.ulid.for_row("user_learning_report", 5)
        self.assertEqual({r.table for r in recs}, {"submission_feedback_files"})
        self.assertEqual({r.values["feedback_id"] for r in recs},
                         {ctx.ulid.for_row("user_report_feedback", submission)})
        self.assertEqual([(r.values["sort_order"], r.values["file_name"]) for r in recs],
                         [(1, "講評.pdf"), (2, "b.pdf")])

    def test_submission_log_keeps_the_first_answer(self) -> None:
        """**新は回答済みかをこの表だけで見る。** 同じユニットの回答は1行（最初の回答日時）。"""
        from migrator.steps.enrollment import results

        ctx = make_ctx()
        rows = [{"_unit_id": 1, "_user_id": 9, "enquete_reply_time": datetime(2021, 6, 1, 12)},
                {"_unit_id": 1, "_user_id": 9, "enquete_reply_time": datetime(2020, 6, 1, 12)}]
        [rec] = results.SurveySubmissionLogStep().transform(ctx, rows)
        self.assertEqual(rec.table, "survey_submission_log")
        self.assertEqual(rec.values["submitted_at"].year, 2020)
        self.assertTrue(results._suspended({"suspended_chk": 1}))
        self.assertFalse(results._suspended({"suspended_chk": 0}))

    def test_sent_reminder_is_kept_as_sent(self) -> None:
        """**`mail_send_chk` は「送信済み」の印。** 送信済みの回の予約は reminded_at を入れる。"""
        from migrator.steps.billing import tickets

        ctx = make_ctx()

        def reserve(rid, sent):
            return {"live_lesson_reserve_id": rid, "live_lesson_date_id": 7, "user_id": 9,
                    "cancel_chk": 0, "attendance_chk": 0, "stop_chk": 0,
                    "_date": {"live_lesson_date_from": datetime(2020, 1, 1), "mail_send_chk": sent,
                              "update_date": datetime(2019, 12, 31, 9)}}
        sent, unsent = tickets.ReservationsStep().transform(ctx, [reserve(1, 1), reserve(2, 0)])
        self.assertIsNotNone(sent.values["reminded_at"])
        self.assertIsNone(unsent.values["reminded_at"])

    def test_reminder_is_never_before_the_reservation(self) -> None:
        """**送ったあとに入った予約でも、予約より前に送ったことにしない。**"""
        from migrator.steps.billing import tickets

        row = {"reserve_date": datetime(2020, 1, 2, 9),
               "_date": {"mail_send_chk": 1, "update_date": datetime(2020, 1, 1, 9)}}
        self.assertEqual(tickets._reminded_at(row), tickets.convert(row["reserve_date"], tickets.ColumnKind.DATETIME))


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

    def test_trigger_kinds(self) -> None:
        """**きっかけは全行移す。** レッスン → 講座、講座の商品 → プラン、それ以外の商品は旧 ID だけ。"""
        ctx = make_ctx()
        rows = [
            {"assign_id": 1, "item_id": 7, "item_type": 1, "_course_plan": False},
            {"assign_id": 1, "item_id": 8, "item_type": 0, "_course_plan": True},
            {"assign_id": 1, "item_id": 9, "item_type": 0, "_course_plan": False},
        ]
        lesson, plan, other = assign.TriggersStep().transform(ctx, rows)
        self.assertEqual(lesson.values["course_id"], ctx.ulid.for_row("lesson", 7))
        self.assertEqual(plan.values["plan_id"], ctx.ulid.for_row("payment_item", 8))
        self.assertEqual((other.values["course_id"], other.values["plan_id"], other.values["item_id"]), (None, None, 9))

    def test_deleted_and_invalid_grants_are_kept(self) -> None:
        ctx = make_ctx()
        base = {"item_id": 1, "assign_id": 1, "item_type": "lesson", "entity_id": 7, "require_chk": 0,
                "valid_chk": 0, "del_chk": 1, "update_date": datetime(2021, 6, 1, 12)}
        [rec] = assign.GrantsStep().transform(ctx, [base])
        self.assertFalse(rec.values["valid"])
        self.assertIsNotNone(rec.values["deleted_at"])
        self.assertEqual(rec.values["item_id"], 1)

    def test_deleted_survey_answer_is_not_answered(self) -> None:
        """**削除済みの回答は回答済みにしない**（旧は回答し直せた）。回答そのものは移す。"""
        from migrator.steps.enrollment import results

        self.assertTrue(results._deleted({"del_chk": 1}))
        ctx = make_ctx()
        rows = [{"_unit_id": 1, "_user_id": 9, "enquete_reply_time": None, "regist_date": None},
                {"_unit_id": 1, "_user_id": 9, "enquete_reply_time": datetime(2020, 6, 1, 12)}]
        [rec] = results.SurveySubmissionLogStep().transform(ctx, rows)  # 日時の無い行があっても落ちない
        self.assertEqual(rec.values["submitted_at"].year, 2020)


if __name__ == "__main__":
    unittest.main()
