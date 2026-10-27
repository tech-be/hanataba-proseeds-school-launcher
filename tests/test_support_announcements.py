"""support.3 お知らせ（docs/db/05-support/migration-spec.md 0-1・0-9）のテスト。"""

from __future__ import annotations

import logging
import unittest
from dataclasses import replace
from datetime import date, datetime

from migrator.context import build_context
from migrator.db.target import TargetDatabase
from migrator.steps.support import announcements as an
from tests.fakes import FakeSource
from tests.test_steps import CONFIG

TENANT = "01ARZ3NDEKTSV4RRFFQ69G5FAV"

NEWS = {
    "news_id": 187, "writer_user_id": 5, "news_title": "件名", "news_detail": "本文",
    "disp_start_date": datetime(2024, 4, 1, 9, 0), "disp_limit_date": None, "reply_type": 2,
    "open_chk": 1, "regist_date": datetime(2024, 3, 31, 10, 0), "update_date": datetime(2024, 3, 31, 10, 0),
    "del_chk": 0,
}
ANNOUNCE = {
    "announce_id": 3, "set_user_id": 5, "message": "帯の文", "open_chk": 1,
    "disp_start_date": date(2024, 4, 1), "disp_end_date": date(2024, 4, 30),
    "regist_date": datetime(2024, 3, 31, 10, 0), "update_date": datetime(2024, 3, 31, 10, 0), "del_chk": 0,
}


def ctx_with(tables: dict, provisional: dict | None = None):
    config = replace(CONFIG, provisional=provisional or {"announce_title": "アナウンス"})
    ctx = build_context(config, FakeSource(tables), TargetDatabase(None, dry_run=True), logging.getLogger("test"))
    ctx.tenant_id.resolve(TENANT)
    return ctx


def nu(id_, news_id, user_id, read=None, deleted=0):
    return {"news_user_id": id_, "news_id": news_id, "user_id": user_id, "news_disp_date": read,
            "regist_date": datetime(2024, 4, 1), "del_chk": deleted}


class NewsTest(unittest.TestCase):
    def test_news_maps_to_specific_users_announcement(self) -> None:
        ctx = ctx_with({"news": [NEWS], "line_message": [{"news_id": 187, "message": "LINE の本文"}]})
        step = an.NewsStep()
        [record] = step.transform(ctx, step.extract(ctx))
        v = record.values
        # **自動割当の付与先と同じ名前空間**（billing/assign.py）
        self.assertEqual(v["id"], ctx.ulid.for_row("news", 187))
        self.assertEqual((v["status"], v["audience_type"], v["reply_type"]), ("published", "specific_users", 2))
        self.assertEqual(v["line_body"], "LINE の本文")
        # 表示開始は JST → UTC。公開日時は表示開始
        self.assertEqual(v["publish_start_at"], datetime(2024, 4, 1, 0, 0))
        self.assertEqual(v["published_at"], v["publish_start_at"])

    def test_deleted_news_is_withdrawn(self) -> None:
        """**削除済みは取り下げ**（新の状態にある値。Q1）。"""
        self.assertEqual(an.status_of({**NEWS, "del_chk": 1}), "withdrawn")
        self.assertEqual(an.status_of({**NEWS, "open_chk": 0}), "draft")


class AnnounceTest(unittest.TestCase):
    def test_announce_gets_fixed_title_and_inclusive_end(self) -> None:
        ctx = ctx_with({"announce": [ANNOUNCE]})
        step = an.AnnounceStep()
        [record] = step.transform(ctx, step.extract(ctx))
        v = record.values
        self.assertEqual(v["title"], "アナウンス")
        # 終了日は**その日を含む**: 4/30 の翌日 0 時 JST = 4/30 15:00 UTC
        self.assertEqual(v["publish_end_at"], datetime(2024, 4, 30, 15, 0))
        self.assertEqual(v["publish_start_at"], datetime(2024, 3, 31, 15, 0))

    def test_missing_title_setting_leaves_null(self) -> None:
        """設定が無ければ**作らない**（NULL のまま制約の確認に当たり、一覧に出る）。"""
        ctx = ctx_with({"announce": [ANNOUNCE]}, provisional={"other": 1})
        [record] = an.AnnounceStep().transform(ctx, [ANNOUNCE])
        self.assertIsNone(record.values["title"])


class AudienceTest(unittest.TestCase):
    def tables(self):
        return {
            "news": [NEWS, {**NEWS, "news_id": 188, "del_chk": 1}],
            "news_user": [
                nu(1, 187, 101, read=datetime(2024, 4, 2, 12, 0)),
                nu(2, 187, 102),
                nu(3, 187, 103, read=datetime(2024, 4, 2), deleted=1),  # 外された（既読あり）
                nu(4, 188, 104, read=datetime(2024, 4, 2)),  # 削除済みのお知らせ
            ],
        }

    def test_targets_are_alive_rows_and_removed_are_listed(self) -> None:
        ctx = ctx_with(self.tables())
        step = an.NewsTargetsStep()
        rows = step.extract(ctx)
        dropped = sorted(v.key for v in step._take_dropped())
        self.assertEqual(sorted(r["news_user_id"] for r in rows), [1, 2])
        self.assertEqual(dropped, ["news_user:3", "news_user:4"])

    def test_reads_only_where_opened(self) -> None:
        """**既読は開いた日時がある行だけ。** 未読の行を入れると、新では既読に見える。"""
        ctx = ctx_with(self.tables())
        step = an.NewsReadsStep()
        rows = step.extract(ctx)
        self.assertEqual([r["news_user_id"] for r in rows], [1])
        # 外された配信先の既読は入れ先が無いので一覧に出す（既読の無い外された行は出さない）
        self.assertEqual(sorted(v.key for v in step._take_dropped()), ["news_user:3", "news_user:4"])
        [record] = step.transform(ctx, rows)
        self.assertEqual(record.values["read_at"], datetime(2024, 4, 2, 3, 0))
        self.assertEqual(record.values["tenant_id"], TENANT)


class RepliesTest(unittest.TestCase):
    def test_replies_and_comments(self) -> None:
        reply = {"news_reply_id": 9, "news_user_id": 1, "reply_user_id": 101, "reply_detail": "返信",
                 "reply_date": datetime(2024, 4, 3), "comment_user_id": 5, "comment": "運営の返事",
                 "comment_date": datetime(2024, 4, 4), "del_chk": 0}
        tables = {"news_user": [nu(1, 187, 101)], "news_reply": [reply, {**reply, "news_reply_id": 10, "comment": ""}]}
        ctx = ctx_with(tables)
        replies = an.NewsRepliesStep()
        records = replies.transform(ctx, replies.extract(ctx))
        self.assertEqual(len(records), 2)  # 同じ会員の返信も履歴として 2 件
        self.assertEqual(records[0].values["announcement_id"], ctx.ulid.for_row("news", 187))
        comments = an.NewsReplyCommentsStep()
        [comment] = comments.transform(ctx, comments.extract(ctx))
        self.assertEqual(comment.values["reply_id"], ctx.ulid.for_row("news_reply", 9))


class AttachmentsTest(unittest.TestCase):
    def test_files_are_listed_not_migrated(self) -> None:
        """**ファイルを移せない**ので行も入れず、ファイルごとに一覧に出す（Q4）。"""
        row = {"news_id": 187, **{f"news_save_file_name{n}": "" for n in range(1, 6)}}
        row["news_save_file_name1"] = "a.pdf"
        row["news_save_file_name3"] = "b.pdf"
        ctx = ctx_with({"news": [row]})
        step = an.NewsAttachmentsStep()
        self.assertEqual(step.extract(ctx), [])
        self.assertEqual(sorted(v.key for v in step._take_dropped()), ["news:187:1", "news:187:3"])


if __name__ == "__main__":
    unittest.main()
