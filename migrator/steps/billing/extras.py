"""月次チケット配布（billing.1）とライブレビュー（enrollment.6）。

どちらも**新環境に受け皿が無かったもの**。月次配布は課金の A2、
ライブレビューは受講の A7 で追加した。流れる区分は別々で、月次配布は
チケットの付与のあと、レビューはライブ（`content.live_lessons`）のあと。
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
                    # 決済（billing.2 の `payments`）に結ぶのは未実装。旧 ID を保持して待つ
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


class MonthlyRemainingStep(Step):
    """**月チケットの今の期間の残り**を `ticket_grants` に入れる（0-2 Q5）。

    `monthly_ticket_allowances` は新が読まないので、今使える残りは付与にしないと消える。
    ただし月チケットには種別が無く、新の付与は種別が要る。**種別を決めるまで（確認事項 D22）は
    一覧に出すだけ**。今の期間は「契約日 ≤ 今日 ≤ 期限」で削除されていないもの（旧の判定。
    `LiveLessonModel` の月チケット）。ステージングは 0 件。
    """

    name = "billing.monthly_remaining"
    description = "月チケットの今の期間の残りを付与にする（種別が決まるまで一覧に出す）"
    source_table = "month_user_ticket"
    target_table = "ticket_grants"
    depends_on = ("billing.monthly_allowances",)

    def extract(self, ctx: RunContext) -> list[dict]:
        today = _today()
        for row in ctx.require_source().fetch_joined(
            "month_user_ticket", MONTH_TICKET_COLUMNS, parent="user", on="c.user_id = p.user_id"
        ):
            if current_period(row, today):
                self.drop("ticket_grants", f"month:{row['month_user_ticket_id']}", "受け皿なし",
                          f"月チケットの今の期間の残り {int(row.get('ticket_count') or 0)} 枚。"
                          "新はチケットに種別が要る。種別を決めるまで移さない（確認事項 D22）")
        return []

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        return []


def _today():
    from datetime import date

    return date.today()


def current_period(row: dict, today) -> bool:
    """今の期間で、残りがあり、削除されていない月チケットか。"""
    agreed, limit = row.get("agreement_date"), row.get("limit_date")
    agreed = agreed.date() if hasattr(agreed, "date") else agreed
    limit = limit.date() if hasattr(limit, "date") else limit
    return (int(row.get("del_chk") or 0) == 0 and int(row.get("ticket_count") or 0) > 0
            and agreed is not None and limit is not None and agreed <= today <= limit)


def allowances() -> list[Step]:
    """4-1 チケット（月次配布）。"""
    return [MonthlyAllowancesStep(), MonthlyRemainingStep()]


def reviews() -> list[Step]:
    """3-6 ライブ予約（レビュー）。受講者が残す記録。"""
    return [ReviewsStep()]
