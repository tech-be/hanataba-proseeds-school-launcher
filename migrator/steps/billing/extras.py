"""live.8 — 月次チケット配布とライブレビュー。

どちらも**新環境に受け皿が無かったもの**（A9 で追加）。`lessons` と `users` にしか
依存しないので、区分の最後に置く。
"""

from __future__ import annotations

from ...context import RunContext
from ...core.datetimes import ColumnKind, convert
from ...core.records import Record
from ..base import Step

MONTH_TICKET_COLUMNS = (
    "month_user_ticket_id", "user_id", "target_month", "agreement_date",
    "max_ticket_count", "limit_date", "ticket_count", "application_id",
    "is_application", "is_trial", "del_chk", "regist_date",
)
REVIEW_COLUMNS = (
    "live_lesson_review_id", "live_lesson_id", "user_id", "review_title", "review_detail",
    "star_rating", "admin_comment_user_id", "admin_comment", "admin_comment_date",
    "del_chk", "regist_date",
)


class MonthlyAllowancesStep(Step):
    """`month_user_ticket` を移す（「毎月◯枚まで」の契約と消化状況）。"""

    name = "billing.monthly_allowances"
    description = "月次のチケット配布を移す"
    source_table = "month_user_ticket"
    target_table = "monthly_ticket_allowances"
    depends_on = ("billing.ticket_grants",)

    def extract(self, ctx: RunContext) -> list[dict]:
        return ctx.require_source().fetch_joined(
            "month_user_ticket", MONTH_TICKET_COLUMNS, parent="user", on="c.user_id = p.user_id"
        )

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        return [
            Record(
                table="monthly_ticket_allowances",
                values={
                    "id": ctx.ulid.for_row("month_user_ticket", row["month_user_ticket_id"]),
                    "tenant_id": tenant_id,
                    "user_id": ctx.ulid.for_row("user", row["user_id"]),
                    "month_user_ticket_id": int(row["month_user_ticket_id"]),
                    # 'YYYYMM' 等。**書式を変えずに移す**
                    "target_month": row.get("target_month") or "",
                    "agreed_on": row.get("agreement_date"),
                    "max_ticket_count": int(row.get("max_ticket_count") or 0),
                    "remaining_count": int(row.get("ticket_count") or 0),
                    "expires_on": row.get("limit_date"),
                    # 参照先は課金区分（未移行）。旧 ID を保持して待つ
                    "application_id": row.get("application_id"),
                    "is_applied": bool(int(row.get("is_application") or 0)),
                    "is_trial": bool(int(row.get("is_trial") or 0)),
                    "deleted_at": (
                        convert(row.get("regist_date"), ColumnKind.DATETIME)
                        if int(row.get("del_chk") or 0) == 1
                        else None
                    ),
                    "created_at": convert(row.get("regist_date"), ColumnKind.DATETIME),
                },
                natural_key=("tenant_id", "month_user_ticket_id"),
                source_key=int(row["month_user_ticket_id"]),
            )
            for row in rows
        ]


class ReviewsStep(Step):
    """`live_lesson_review` を移す。

    **`course_reviews` には入れない。** あちらはコース単位で、受け皿講座に付けると
    全ライブのレビューが1つの講座に混ざる。
    """

    name = "enrollment.live_reviews"
    description = "ライブのレビューと管理者コメントを移す"
    source_table = "live_lesson_review"
    target_table = "live_lesson_reviews"
    depends_on = ("content.live_lessons",)

    def extract(self, ctx: RunContext) -> list[dict]:
        return ctx.require_source().fetch_for_tenant("live_lesson_review", REVIEW_COLUMNS)

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        return [
            Record(
                table="live_lesson_reviews",
                values={
                    "id": ctx.ulid.for_row("live_lesson_review", row["live_lesson_review_id"]),
                    "tenant_id": tenant_id,
                    "lesson_id": ctx.ulid.for_row("live_lesson", row["live_lesson_id"]),
                    "user_id": ctx.ulid.for_row("user", row["user_id"]),
                    "live_lesson_review_id": int(row["live_lesson_review_id"]),
                    "title": row.get("review_title"),
                    "body": row.get("review_detail"),
                    "star_rating": row.get("star_rating"),
                    "admin_comment_user_id": (
                        ctx.ulid.for_row("user", row["admin_comment_user_id"])
                        if row.get("admin_comment_user_id")
                        else None
                    ),
                    "admin_comment": row.get("admin_comment"),
                    "admin_commented_at": convert(
                        row.get("admin_comment_date"), ColumnKind.DATETIME
                    ),
                    "deleted_at": (
                        convert(row.get("regist_date"), ColumnKind.DATETIME)
                        if int(row.get("del_chk") or 0) == 1
                        else None
                    ),
                    "created_at": convert(row.get("regist_date"), ColumnKind.DATETIME),
                },
                natural_key=("tenant_id", "live_lesson_review_id"),
                source_key=int(row["live_lesson_review_id"]),
            )
            for row in rows
        ]


def allowances() -> list[Step]:
    """4-1 チケット（月次配布）。"""
    return [MonthlyAllowancesStep()]


def reviews() -> list[Step]:
    """3-6 ライブ予約（レビュー）。受講者が残す記録。"""
    return [ReviewsStep()]
