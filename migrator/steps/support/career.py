"""support.6 — 就業支援のうち、会員どうしの記録（助言メモ・スカウトのフォロー）。

2026-09-30 に「その他」から 05 へ仕分けたもの。求人・面談・スキルチェックの本体は未実装。

- `personal_record_advice` … 管理者・キャリアカウンセラーが会員に残した助言メモ。
  **既存の `admin_notes`（運営メモ）に寄せる**（対象の会員・書いた人・本文の3つが揃う）
- `follow` … 求人企業（と管理者）が受講者をフォローした記録。受け皿 `scout_follows` を新設した
"""

from __future__ import annotations

from ...context import RunContext
from ...core.datetimes import ColumnKind, convert
from ...core.records import Record
from ..base import Step

ADVICE_COLUMNS = (
    "personal_record_advice_id", "user_id", "target_user_id", "advice_memo", "del_chk",
    "update_user_id", "regist_date", "update_date",
)
FOLLOW_COLUMNS = ("follow_id", "user_id", "followed_user_id", "register_date", "update_date", "del_chk")


class AdviceNotesStep(Step):
    """助言メモを `admin_notes` に移す。**削除済みも移す**（`deleted_at`。2026-10-01 の方針）。"""

    name = "support.advice_notes"
    description = "会員への助言メモを運営メモとして移す"
    source_table = "personal_record_advice"
    target_table = "admin_notes"
    depends_on = ("users",)

    def extract(self, ctx: RunContext) -> list[dict]:
        return ctx.require_source().fetch_for_tenant("personal_record_advice", ADVICE_COLUMNS)

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        return [
            Record(
                table="admin_notes",
                values={
                    # 運営メモに旧 ID の列は無い。決定論 ULID で再移行の重複を防ぐ
                    "id": ctx.ulid.for_row("personal_record_advice", int(row["personal_record_advice_id"])),
                    "tenant_id": tenant_id,
                    "user_id": ctx.ulid.for_row("user", int(row["target_user_id"])),
                    "author_id": ctx.ulid.for_row("user", int(row["user_id"])),
                    # 最後に直した人（school-launcher 20260930052453 で足した列）。旧は 0 / NULL = 未更新
                    "updated_by": (
                        ctx.ulid.for_row("user", int(row["update_user_id"]))
                        if int(row.get("update_user_id") or 0) else None
                    ),
                    "body": row.get("advice_memo") or "",
                    "deleted_at": (
                        convert(row.get("update_date"), ColumnKind.DATETIME)
                        if int(row.get("del_chk") or 0) == 1 else None
                    ),
                    "created_at": convert(row.get("regist_date"), ColumnKind.TIMESTAMP),
                    "updated_at": convert(row.get("update_date"), ColumnKind.TIMESTAMP),
                },
                natural_key=("id",),
                source_key=int(row["personal_record_advice_id"]),
            )
            for row in rows
        ]


class ScoutFollowsStep(Step):
    name = "support.scout_follows"
    description = "求人企業による受講者のフォローを移す"
    source_table = "follow"
    target_table = "scout_follows"
    depends_on = ("users",)

    def extract(self, ctx: RunContext) -> list[dict]:
        return ctx.require_source().fetch_for_tenant("follow", FOLLOW_COLUMNS)

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        return [
            Record(
                table="scout_follows",
                values={
                    "id": ctx.ulid.for_row("follow", int(row["follow_id"])),
                    "tenant_id": tenant_id,
                    "follow_id": int(row["follow_id"]),
                    "user_id": ctx.ulid.for_row("user", int(row["user_id"])),
                    "followed_user_id": ctx.ulid.for_row("user", int(row["followed_user_id"])),
                    "deleted_at": (
                        convert(row.get("update_date"), ColumnKind.DATETIME)
                        if int(row.get("del_chk") or 0) == 1 else None
                    ),
                    "created_at": convert(row.get("register_date"), ColumnKind.TIMESTAMP),
                    "updated_at": convert(row.get("update_date"), ColumnKind.TIMESTAMP),
                },
                natural_key=("tenant_id", "follow_id"),
                source_key=int(row["follow_id"]),
            )
            for row in rows
        ]


def build() -> list[Step]:
    return [AdviceNotesStep(), ScoutFollowsStep()]
