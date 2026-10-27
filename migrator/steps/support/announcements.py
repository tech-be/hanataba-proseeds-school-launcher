"""support.3 — お知らせ（`news`）とアナウンス（`announce`）を `announcements` に移す。

docs/db/05-support/migration-spec.md 0-1。

- **旧の配信対象は「会員の一覧」。** 配信したときに対象者全員の `news_user` / `announce_user` を
  未読で作る（グループ・属性の条件は検索に使うだけで保存されない）。新ではすべて
  `specific_users` にし、生きている配信先の行を `announcement_user_targets` に入れる
- **既読は、旧で開いた日時がある行だけ**（新は行が無ければ未読）
- 削除済みは `withdrawn`（新の状態にある値。Q1）
- 本文の HTML は**補正データでプレーンテキストに直す**（`fixups`。Q2）。ここでは読むだけ
- 添付は**ファイルを移せない**ので行も移さず、一覧に出す（Q4）
- ID の名前空間 `news` / `announce` は自動割当の付与先（`billing/assign.py`）と同じ
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from ...context import RunContext
from ...core.datetimes import ColumnKind, convert
from ...core.records import Record
from ..base import Step

NEWS_COLUMNS = (
    "news_id", "writer_user_id", "news_title", "news_detail", "disp_start_date",
    "disp_limit_date", "reply_type", "open_chk", "regist_date", "update_date", "del_chk",
)
NEWS_FILE_COLUMNS = tuple(f"news_save_file_name{n}" for n in range(1, 6))
NEWS_USER_COLUMNS = ("news_user_id", "news_id", "user_id", "news_disp_date", "regist_date", "del_chk")
ANNOUNCE_COLUMNS = (
    "announce_id", "set_user_id", "message", "open_chk", "disp_start_date", "disp_end_date",
    "regist_date", "update_date", "del_chk",
)
ANNOUNCE_USER_COLUMNS = ("announce_user_id", "announce_id", "user_id", "disp_time", "regist_date", "del_chk")
REPLY_COLUMNS = (
    "news_reply_id", "news_user_id", "reply_user_id", "reply_detail", "reply_date",
    "comment_user_id", "comment", "comment_date", "del_chk",
)

#: 削除済みのお知らせの配信先・外された配信先は移さない（新に「外した」に当たる状態が無い）
REMOVED_TARGET = "移行対象外"
REMOVED_TARGET_DETAIL = "削除済みのお知らせの配信先、または配信先から外された行"
NO_FILE = "移行対象外"
NO_FILE_DETAIL = "添付のファイルは移せない（2026-10-26 決定）"


def _deleted(row: dict) -> bool:
    return int(row.get("del_chk") or 0) == 1


def status_of(row: dict) -> str:
    """旧の状態 → 新の `status`。削除済みは取り下げ（`withdrawn`）。"""
    if _deleted(row):
        return "withdrawn"
    return "published" if int(row.get("open_chk") or 0) == 1 else "draft"


def start_of(value: object) -> datetime | None:
    """表示開始。旧は JST。`date` なら その日の 0 時。"""
    if value is None:
        return None
    if isinstance(value, datetime):
        return convert(value, ColumnKind.DATETIME)
    if isinstance(value, date):
        return convert(datetime.combine(value, time(0, 0)), ColumnKind.DATETIME)
    return None


def end_of(value: object) -> datetime | None:
    """表示終了。**旧はその日を含む**ので、日付（時刻が 0 時）なら翌日の 0 時（JST）にする。"""
    if value is None:
        return None
    if isinstance(value, datetime) and value.time() != time(0, 0):
        return convert(value, ColumnKind.DATETIME)
    day = value.date() if isinstance(value, datetime) else value
    if not isinstance(day, date):
        return None
    return convert(datetime.combine(day + timedelta(days=1), time(0, 0)), ColumnKind.DATETIME)


def _user(ctx: RunContext, value: object) -> str | None:
    return ctx.ulid.for_row("user", int(value)) if int(value or 0) else None


class NewsStep(Step):
    """お知らせ（`news`）。LINE の本文（`line_message`）を `line_body` に入れる。"""

    name = "support.news"
    description = "お知らせを移す（LINE の本文を含む）"
    source_table = "news"
    target_table = "announcements"
    depends_on = ("users",)

    def extract(self, ctx: RunContext) -> list[dict]:
        source = ctx.require_source()
        rows = source.fetch_for_tenant("news", NEWS_COLUMNS)
        lines = {
            int(r["news_id"]): r["message"]
            for r in source.fetch_joined(
                "line_message", ("news_id", "message"), parent="news", on="c.news_id = p.news_id"
            )
        }
        for row in rows:
            row["_line_body"] = lines.get(int(row["news_id"]))
        return rows

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        records = []
        for row in rows:
            status = status_of(row)
            start = start_of(row.get("disp_start_date"))
            records.append(
                Record(
                    table="announcements",
                    values={
                        "id": ctx.ulid.for_row("news", int(row["news_id"])),
                        "tenant_id": tenant_id,
                        "title": row.get("news_title") or "",
                        "body": row.get("news_detail") or "",
                        "line_body": row.get("_line_body") or None,
                        "status": status,
                        "audience_type": "specific_users",
                        "pinned": False,
                        "reply_type": int(row.get("reply_type") or 0),
                        "publish_start_at": start,
                        "publish_end_at": end_of(row.get("disp_limit_date")),
                        # 旧に公開した日時は無い。表示開始で並ぶので、それを入れる
                        "published_at": start if status != "draft" else None,
                        "created_by": _user(ctx, row.get("writer_user_id")),
                        "created_at": convert(row.get("regist_date"), ColumnKind.TIMESTAMP),
                        "updated_at": convert(row.get("update_date"), ColumnKind.TIMESTAMP),
                    },
                    natural_key=("id",),
                    source_key=f"news:{row['news_id']}",
                )
            )
        return records


class AnnounceStep(Step):
    """アナウンス（`announce`）。**件名が無い**ので、設定の固定の文言を入れる（Q3）。"""

    name = "support.announce"
    description = "アナウンス（トップページの帯）をお知らせとして移す"
    source_table = "announce"
    target_table = "announcements"
    depends_on = ("users",)

    def extract(self, ctx: RunContext) -> list[dict]:
        return ctx.require_source().fetch_for_tenant("announce", ANNOUNCE_COLUMNS)

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        # 設定に無ければ NULL のまま制約の確認に当たり、一覧に出る（黙って文言を作らない）
        title = ctx.provisional("announce_title")
        records = []
        for row in rows:
            status = status_of(row)
            start = start_of(row.get("disp_start_date"))
            records.append(
                Record(
                    table="announcements",
                    values={
                        "id": ctx.ulid.for_row("announce", int(row["announce_id"])),
                        "tenant_id": tenant_id,
                        "title": title,
                        "body": row.get("message") or "",
                        "line_body": None,
                        "status": status,
                        "audience_type": "specific_users",
                        "pinned": False,
                        "reply_type": 0,
                        "publish_start_at": start,
                        "publish_end_at": end_of(row.get("disp_end_date")),
                        "published_at": start if status != "draft" else None,
                        "created_by": _user(ctx, row.get("set_user_id")),
                        "created_at": convert(row.get("regist_date"), ColumnKind.TIMESTAMP),
                        "updated_at": convert(row.get("update_date"), ColumnKind.TIMESTAMP),
                    },
                    natural_key=("id",),
                    source_key=f"announce:{row['announce_id']}",
                )
            )
        return records


class _AudienceStep(Step):
    """配信先（`*_user`）の共通。**生きている行だけ**を移し、外された行は一覧に出す。"""

    kind = ""  # news / announce
    child = ""  # news_user / announce_user
    child_columns: tuple[str, ...] = ()
    child_key = ""

    def _split(self, ctx: RunContext) -> tuple[list[dict], list[dict]]:
        """（生きている行, 外された行）。削除済みのお知らせの配信先も外された行に入れる。"""
        source = ctx.require_source()
        rows = source.fetch_joined(
            self.child, self.child_columns, parent=self.kind, on=f"c.{self.kind}_id = p.{self.kind}_id"
        )
        deleted_parents = {
            int(r[f"{self.kind}_id"])
            for r in source.fetch_for_tenant(self.kind, (f"{self.kind}_id", "del_chk"))
            if _deleted(r)
        }
        alive, removed = [], []
        for row in rows:
            gone = _deleted(row) or int(row[f"{self.kind}_id"]) in deleted_parents
            (removed if gone else alive).append(row)
        return alive, removed

    def _drop_removed(self, rows: list[dict]) -> None:
        for row in rows:
            self.drop(self.target_table, f"{self.child}:{row[self.child_key]}", REMOVED_TARGET, REMOVED_TARGET_DETAIL)


class _TargetsStep(_AudienceStep):
    target_table = "announcement_user_targets"

    def extract(self, ctx: RunContext) -> list[dict]:
        alive, removed = self._split(ctx)
        self._drop_removed(removed)
        return alive

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        return [
            Record(
                table="announcement_user_targets",
                values={
                    "announcement_id": ctx.ulid.for_row(self.kind, int(row[f"{self.kind}_id"])),
                    "user_id": ctx.ulid.for_row("user", int(row["user_id"])),
                    "created_at": convert(row.get("regist_date"), ColumnKind.TIMESTAMP),
                },
                natural_key=("announcement_id", "user_id"),
                source_key=f"{self.child}:{row[self.child_key]}",
            )
            for row in rows
        ]


class _ReadsStep(_AudienceStep):
    """既読。**旧で開いた日時がある行だけ。** 外された配信先の既読は入れ先が無いので一覧に出す。"""

    target_table = "announcement_reads"
    read_column = ""

    def extract(self, ctx: RunContext) -> list[dict]:
        alive, removed = self._split(ctx)
        self._drop_removed([r for r in removed if r.get(self.read_column) is not None])
        return [r for r in alive if r.get(self.read_column) is not None]

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        return [
            Record(
                table="announcement_reads",
                values={
                    "announcement_id": ctx.ulid.for_row(self.kind, int(row[f"{self.kind}_id"])),
                    "user_id": ctx.ulid.for_row("user", int(row["user_id"])),
                    "tenant_id": tenant_id,
                    "read_at": convert(row[self.read_column], ColumnKind.DATETIME),
                },
                natural_key=("announcement_id", "user_id"),
                source_key=f"{self.child}:{row[self.child_key]}",
            )
            for row in rows
        ]


class NewsTargetsStep(_TargetsStep):
    name = "support.news_targets"
    description = "お知らせの配信先を移す"
    source_table = "news_user"
    depends_on = ("support.news",)
    kind, child, child_columns, child_key = "news", "news_user", NEWS_USER_COLUMNS, "news_user_id"


class NewsReadsStep(_ReadsStep):
    name = "support.news_reads"
    description = "お知らせの既読を移す"
    source_table = "news_user"
    depends_on = ("support.news",)
    kind, child, child_columns, child_key = "news", "news_user", NEWS_USER_COLUMNS, "news_user_id"
    read_column = "news_disp_date"


class AnnounceTargetsStep(_TargetsStep):
    name = "support.announce_targets"
    description = "アナウンスの配信先を移す"
    source_table = "announce_user"
    depends_on = ("support.announce",)
    kind, child, child_columns, child_key = "announce", "announce_user", ANNOUNCE_USER_COLUMNS, "announce_user_id"


class AnnounceReadsStep(_ReadsStep):
    name = "support.announce_reads"
    description = "アナウンスの既読を移す"
    source_table = "announce_user"
    depends_on = ("support.announce",)
    kind, child, child_columns, child_key = "announce", "announce_user", ANNOUNCE_USER_COLUMNS, "announce_user_id"
    read_column = "disp_time"


class NewsRepliesStep(Step):
    """受講者からの返信（`news_reply`）。返信は履歴として複数持てる（新 20260923112727）。"""

    name = "support.news_replies"
    description = "お知らせへの返信を移す"
    source_table = "news_reply"
    target_table = "announcement_replies"
    depends_on = ("support.news",)

    def extract(self, ctx: RunContext) -> list[dict]:
        source = ctx.require_source()
        news_of = {
            int(r["news_user_id"]): int(r["news_id"])
            for r in source.fetch_joined(
                "news_user", ("news_user_id", "news_id"), parent="news", on="c.news_id = p.news_id"
            )
        }
        rows = source.fetch_joined(
            "news_reply", REPLY_COLUMNS, parent="news", on="nu.news_id = p.news_id",
            via=[("news_user", "nu", "c.news_user_id = nu.news_user_id")],
        )
        for row in rows:
            row["_news_id"] = news_of[int(row["news_user_id"])]
        return rows

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        return [
            Record(
                table="announcement_replies",
                values={
                    "id": ctx.ulid.for_row("news_reply", int(row["news_reply_id"])),
                    "announcement_id": ctx.ulid.for_row("news", row["_news_id"]),
                    "user_id": ctx.ulid.for_row("user", int(row["reply_user_id"])),
                    "body": row.get("reply_detail") or "",
                    "created_at": convert(row.get("reply_date"), ColumnKind.DATETIME),
                },
                natural_key=("id",),
                source_key=int(row["news_reply_id"]),
            )
            for row in rows
        ]


class NewsReplyCommentsStep(NewsRepliesStep):
    """運営のコメント（`news_reply.comment`）。返信 1 件に 1 件。"""

    name = "support.news_reply_comments"
    description = "返信への運営のコメントを移す"
    target_table = "announcement_reply_comments"
    depends_on = ("support.news_replies",)

    def extract(self, ctx: RunContext) -> list[dict]:
        return [r for r in super().extract(ctx) if (r.get("comment") or "").strip()]

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        return [
            Record(
                table="announcement_reply_comments",
                values={
                    "id": ctx.ulid.for_row("news_reply_comment", int(row["news_reply_id"])),
                    "reply_id": ctx.ulid.for_row("news_reply", int(row["news_reply_id"])),
                    "admin_id": ctx.ulid.for_row("user", int(row["comment_user_id"])),
                    "body": row["comment"],
                    "created_at": convert(row.get("comment_date"), ColumnKind.DATETIME),
                },
                natural_key=("id",),
                source_key=int(row["news_reply_id"]),
            )
            for row in rows
        ]


class NewsAttachmentsStep(Step):
    """添付。**ファイルを移せない**ので行も移さず、ファイルごとに一覧に出す（Q4）。"""

    name = "support.news_attachments"
    description = "お知らせの添付（移さない。一覧に出す）"
    source_table = "news"
    target_table = "announcement_attachments"

    def extract(self, ctx: RunContext) -> list[dict]:
        for row in ctx.require_source().fetch_for_tenant("news", ("news_id", *NEWS_FILE_COLUMNS)):
            for n, column in enumerate(NEWS_FILE_COLUMNS, start=1):
                if (row.get(column) or "").strip():
                    self.drop("announcement_attachments", f"news:{row['news_id']}:{n}", NO_FILE, NO_FILE_DETAIL)
        return []

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        return []


def build() -> list[Step]:
    return [
        NewsStep(), AnnounceStep(),
        NewsTargetsStep(), NewsReadsStep(), AnnounceTargetsStep(), AnnounceReadsStep(),
        NewsRepliesStep(), NewsReplyCommentsStep(), NewsAttachmentsStep(),
    ]
