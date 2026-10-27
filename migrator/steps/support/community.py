"""support.7 — コミュニティの分類（旧 `community_cate`）と、講座のディスカッションの投稿。

2026-09-30 に「その他」から 05 へ仕分けたもの。受け皿 `community_categories` を新設した。
掲示板は移行対象外（一覧に出す。`out_of_scope.BbsStep`）。SNS 共有・足あとは未実装。

**講座のディスカッション**（docs/db/05-support/migration-spec.md 0-6）: 投稿
（`discussion_board_comment`）を、その旧ユニットの `discussion_posts` に入れる。お題
（`discussion_board` の名前・本文）・採点・通知の設定は受け皿が無いので一覧に出す。
"""

from __future__ import annotations

from ...context import RunContext
from ...core.datetimes import ColumnKind, convert
from ...core.records import Record
from ..base import Step

COMMUNITY_CATE_COLUMNS = (
    "community_cate_id", "community_cate_name", "group_id", "sort_no", "del_chk",
    "regist_date", "update_date",
)


class CommunityCategoriesStep(Step):
    name = "support.community_categories"
    description = "コミュニティの分類を移す"
    source_table = "community_cate"
    target_table = "community_categories"
    depends_on = ("config.groups",)

    def extract(self, ctx: RunContext) -> list[dict]:
        return ctx.require_source().fetch_for_tenant("community_cate", COMMUNITY_CATE_COLUMNS)

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        return [
            Record(
                table="community_categories",
                values={
                    "id": ctx.ulid.for_row("community_cate", int(row["community_cate_id"])),
                    "tenant_id": tenant_id,
                    "community_cate_id": int(row["community_cate_id"]),
                    "name": row.get("community_cate_name") or "",
                    # 旧は 0 =「グループ指定なし」
                    "group_id": (
                        ctx.ulid.for_row("group", int(row["group_id"]))
                        if int(row.get("group_id") or 0) else None
                    ),
                    "sort_order": int(row.get("sort_no") or 0),
                    "deleted_at": (
                        convert(row.get("update_date"), ColumnKind.DATETIME)
                        if int(row.get("del_chk") or 0) == 1 else None
                    ),
                    "created_at": convert(row.get("regist_date"), ColumnKind.TIMESTAMP),
                    "updated_at": convert(row.get("update_date"), ColumnKind.TIMESTAMP),
                },
                natural_key=("tenant_id", "community_cate_id"),
                source_key=int(row["community_cate_id"]),
            )
            for row in rows
        ]


BOARD_COLUMNS = ("discussion_board_id", "unit_id", "del_chk")
COMMENT_COLUMNS = (
    "discussion_board_comment_id", "ref_discussion_board_comment_id", "discussion_board_id",
    "user_id", "comment", "regist_date", "update_date", "del_chk",
)
NO_PLACE = "受け皿なし"


def _boards(ctx: RunContext) -> list[dict]:
    """お題。テナントはユニット → 講座でたどる（共有講座のユニットも含む）。"""
    return ctx.require_source().fetch_joined(
        "discussion_board", BOARD_COLUMNS, parent="lesson", on="u.lesson_id = p.lesson_id",
        via=[("unit", "u", "c.unit_id = u.unit_id")],
    )


class DiscussionPostsStep(Step):
    """講座のディスカッションの投稿。親の投稿を先に、返信は親を指す。"""

    name = "support.discussion_posts"
    description = "講座のディスカッションの投稿を移す"
    source_table = "discussion_board_comment"
    target_table = "discussion_posts"
    depends_on = ("users",)

    def extract(self, ctx: RunContext) -> list[dict]:
        boards = {int(b["discussion_board_id"]): b for b in _boards(ctx)}
        for board in boards.values():
            # お題そのもの（名前・本文）は新に置き場が無い
            self.drop("discussion_board", f"discussion_board:{board['discussion_board_id']}", NO_PLACE,
                      "ディスカッションのお題（名前・本文）。新に置き場が無い")
        rows = []
        for row in ctx.require_source().fetch_joined(
            "discussion_board_comment", COMMENT_COLUMNS, parent="lesson", on="u.lesson_id = p.lesson_id",
            via=[("discussion_board", "b", "c.discussion_board_id = b.discussion_board_id"),
                 ("unit", "u", "b.unit_id = u.unit_id")],
        ):
            row["_unit_id"] = int(boards[int(row["discussion_board_id"])]["unit_id"])
            rows.append(row)
        # 親を先に入れる（返信の外部キー）
        return sorted(rows, key=lambda r: (int(r.get("ref_discussion_board_comment_id") or 0) != 0,
                                           int(r["discussion_board_comment_id"])))

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        records = []
        for row in rows:
            parent = int(row.get("ref_discussion_board_comment_id") or 0)
            records.append(
                Record(
                    table="discussion_posts",
                    values={
                        "id": ctx.ulid.for_row("discussion_board_comment", int(row["discussion_board_comment_id"])),
                        "tenant_id": tenant_id,
                        "lesson_id": ctx.ulid.for_row("unit", row["_unit_id"]),
                        "user_id": ctx.ulid.for_row("user", int(row["user_id"])),
                        "parent_id": ctx.ulid.for_row("discussion_board_comment", parent) if parent else None,
                        "body": row.get("comment") or "",
                        # 削除済みは新の状態 deleted（Q1）
                        "status": "deleted" if int(row.get("del_chk") or 0) == 1 else "active",
                        "created_at": convert(row.get("regist_date"), ColumnKind.TIMESTAMP),
                        "updated_at": convert(row.get("update_date"), ColumnKind.TIMESTAMP),
                    },
                    natural_key=("id",),
                    source_key=int(row["discussion_board_comment_id"]),
                )
            )
        return records


class DiscussionExtrasStep(Step):
    """採点（`user_learning_discussion`）と通知の設定。**受け皿が無い**ので一覧に出す。"""

    name = "support.discussion_extras"
    description = "ディスカッションの採点・通知の設定（移さない。一覧に出す）"
    source_table = "user_learning_discussion"

    def extract(self, ctx: RunContext) -> list[dict]:
        source = ctx.require_source()
        for table, detail in (
            ("user_learning_discussion", "ディスカッションの採点。新に受け皿が無い"),
            ("user_learning_discussion_alert", "ディスカッションの通知の設定。新に受け皿が無い"),
        ):
            for row in source.fetch_joined(
                table, ("user_learning_unit_id",), parent="user", on="ul.user_id = p.user_id",
                via=[
                    ("user_learning_unit", "l", "c.user_learning_unit_id = l.user_learning_unit_id"),
                    ("user_learning_lesson", "ul", "l.user_learning_lesson_id = ul.user_learning_lesson_id"),
                ],
            ):
                self.drop(table, f"{table}:{row['user_learning_unit_id']}", NO_PLACE, detail)
        return []

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        return []


def build() -> list[Step]:
    from .out_of_scope import BbsStep

    return [CommunityCategoriesStep(), DiscussionPostsStep(), DiscussionExtrasStep(), BbsStep()]
