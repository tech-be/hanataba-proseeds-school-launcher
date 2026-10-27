"""support.6（career の DB）・support.7（講座のディスカッション）・移行対象外の一覧のテスト。

docs/db/05-support/migration-spec.md 0-5〜0-7・0-9。
"""

from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import date, datetime

from migrator.steps.support import career as cr
from migrator.steps.support import community as cm
from migrator.steps.support import out_of_scope as oos
from tests.test_support_announcements import ctx_with

PREFS = {1: "北海道", 13: "東京都", 26: "京都府", 27: "大阪府", 14: "神奈川県"}


def user(id_, **values):
    return {"user_id": id_, "name_sei": "山田", "name_mei": "太郎", "education": None, "job_category": None,
            "qualification": None, "desired_employment_status": 0, "desired_job_location": 0, **values}


class PrefectureTest(unittest.TestCase):
    def test_short_names(self) -> None:
        self.assertEqual(
            [cr.short_prefecture(i, PREFS) for i in (1, 13, 26, 27, 14, 99)],
            ["北海道", "東京", "京都", "大阪", "神奈川", "海外"],
        )


class CareerProfileTest(unittest.TestCase):
    def ctx(self, rows, in_btoc):
        ctx = ctx_with({"user": rows})
        for u in in_btoc:  # btoc に移った会員（この実行で入れた行として覚えさせる）
            ctx.target._inserted.setdefault(("users", "id"), set()).add(ctx.ulid.for_row("user", u))
        return ctx

    def test_only_members_with_values_and_in_btoc(self) -> None:
        rows = [user(1, education="大学卒"), user(2), user(3, desired_employment_status=2)]
        ctx = self.ctx(rows, in_btoc=[1])
        step = cr.CareerProfilesStep()
        kept = step.extract(ctx)
        self.assertEqual([r["user_id"] for r in kept], [1])
        # **btoc に移っていない会員は作らない**（career は会員の有無を確かめない）
        self.assertEqual([v.key for v in step._take_dropped()], ["3"])
        [record] = step.transform(ctx, kept)
        self.assertEqual(record.values["employment_status"], "")  # Q14
        self.assertEqual(record.values["learner_name"], "山田 太郎")
        self.assertEqual(step.database, "career")

    def test_desired_employment_type(self) -> None:
        ctx = self.ctx([], in_btoc=[])
        [record] = cr.CareerProfilesStep().transform(ctx, [user(1, desired_employment_status=3)])
        self.assertEqual(record.values["desired_employment_types"], "temporary")

    def test_desired_prefecture_row(self) -> None:
        ctx = self.ctx([user(1, desired_job_location=26), user(2, education="x")], in_btoc=[1, 2])
        ctx.config = replace(ctx.config, mappings={**ctx.config.mappings, "prefecture": {"values": PREFS}})
        step = cr.DesiredPrefecturesStep()
        [record] = step.transform(ctx, step.extract(ctx))
        self.assertEqual(record.values["prefecture"], "京都")
        self.assertEqual(record.values["profile_id"], ctx.ulid.for_row("career_profile", 1))


class InterviewTest(unittest.TestCase):
    def test_interview_gets_booked_slot_and_completed_status(self) -> None:
        row = {"interview_id": 1, "interview_date": date(2024, 4, 16), "counselor_user_id": 50,
               "student_user_id": 101, "interview_content1": "", "regist_date": datetime(2024, 4, 16),
               "update_date": datetime(2024, 4, 16), "del_chk": 0,
               **{f"interview_content{n}": "" for n in range(2, 21)}}
        ctx = ctx_with({"interview_record": [row]})
        for u in (50, 101):
            ctx.target._inserted.setdefault(("users", "id"), set()).add(ctx.ulid.for_row("user", u))
        [slot] = cr.InterviewSlotsStep().transform(ctx, cr._interviews(ctx))
        # 面談日の 0 時（JST）= 前日 15:00 UTC。終わりも同じ（R1）
        self.assertEqual((slot.values["start_time"], slot.values["end_time"]), (datetime(2024, 4, 15, 15, 0),) * 2)
        self.assertTrue(slot.values["is_booked"])
        [interview] = cr.InterviewsStep().transform(ctx, [row])
        self.assertEqual((interview.values["status"], interview.values["purpose"]), ("completed", "career_consultation"))
        self.assertEqual(interview.values["slot_id"], slot.values["id"])
        [record] = cr.InterviewRecordsStep().transform(ctx, [row])
        self.assertEqual(record.values["summary"], "")


class DiscussionTest(unittest.TestCase):
    def test_posts_go_to_their_unit_and_parents_first(self) -> None:
        boards = [{"discussion_board_id": 7, "unit_id": 50706, "del_chk": 0}]
        comments = [
            {"discussion_board_comment_id": 2, "ref_discussion_board_comment_id": 1, "discussion_board_id": 7,
             "user_id": 101, "comment": "返信", "regist_date": datetime(2019, 7, 4), "update_date": datetime(2019, 7, 4), "del_chk": 0},
            {"discussion_board_comment_id": 1, "ref_discussion_board_comment_id": 0, "discussion_board_id": 7,
             "user_id": 101, "comment": "投稿", "regist_date": datetime(2019, 7, 3), "update_date": datetime(2019, 7, 3), "del_chk": 0},
        ]
        ctx = ctx_with({"discussion_board": boards, "discussion_board_comment": comments})
        step = cm.DiscussionPostsStep()
        rows = step.extract(ctx)
        self.assertEqual([r["discussion_board_comment_id"] for r in rows], [1, 2])
        # お題は置き場が無いので一覧に出す
        self.assertEqual([v.key for v in step._take_dropped()], ["discussion_board:7"])
        parent, reply = step.transform(ctx, rows)
        self.assertEqual(parent.values["lesson_id"], ctx.ulid.for_row("unit", 50706))
        self.assertIsNone(parent.values["parent_id"])
        self.assertEqual(reply.values["parent_id"], parent.values["id"])


class OutOfScopeTest(unittest.TestCase):
    def test_bbs_rows_are_all_listed(self) -> None:
        """**掲示板は移行対象外。** 黙って落とさず、行ごとに一覧に出す。"""
        ctx = ctx_with({"bbs": [{"bbs_id": 4}], "bbs_comment": [{"bbs_comment_id": 9}],
                        "bbs_set_lesson": [{"bbs_id": 4, "lesson_id": 2533}], "like_user": [{"like_user_id": 3}]})
        step = oos.BbsStep()
        self.assertEqual(step.extract(ctx), [])
        keys = sorted(v.key for v in step._take_dropped())
        self.assertEqual(keys, ["bbs:4", "bbs_comment:9", "bbs_set_lesson:4:2533", "like_user:3"])

    def test_recruit_rows_are_listed(self) -> None:
        ctx = ctx_with({"recruit": [{"recruit_id": 1}], "recruit_user": [{"recruit_user_id": 5}]})
        step = oos.RecruitStep()
        step.extract(ctx)
        self.assertEqual(sorted(v.key for v in step._take_dropped()), ["recruit:1", "recruit_user:5"])


if __name__ == "__main__":
    unittest.main()
