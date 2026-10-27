"""support.2 — クーポン（`coupon`）を `coupons` に移す。

docs/db/05-support/migration-spec.md 0-2・0-9。

- **無料クーポン（`coupon_type = 1`）は移さない。** 新の割引の種類は率と金額だけで、
  「申込から N 日間無料」に当たるものが無い（2026-10-26 決定）。一覧に出す
- それ以外は**旧のとおりの状態で移す**（有効は `active`）。新は対象の商品を持たないので、
  **どの講座の単品購入にも使える**（旧より広く効く。2026-10-26 に了承）
- 対象の商品（`coupon_item`）は受け皿が無い。一覧に出す
- 決済代行の ID（`provider_*`）は旧に無いので空文字（ロボットペイメントの経路は空文字で動く）
- ID の名前空間 `coupon` は自動割当の付与先（`billing/assign.py`）と同じ
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from ...context import RunContext
from ...core.datetimes import ColumnKind, convert
from ...core.records import Record
from ..base import Step

COUPON_COLUMNS = (
    "coupon_id", "coupon_name", "coupon_code", "valid_chk", "coupon_start_date", "coupon_end_date",
    "valid_term_day", "coupon_type", "discount_amount", "discount_rate", "target_type",
    "timing_chk", "regist_date", "update_date", "del_chk",
)
COUPON_USER_COLUMNS = ("coupon_user_id", "coupon_id", "user_id", "regist_date", "del_chk")
COUPON_LOG_COLUMNS = ("coupon_log_id", "coupon_id", "user_id", "regist_date")

FREE = 1
AMOUNT = 2
RATE = 3

NOT_MIGRATED = "移行対象外"
FREE_DETAIL = "無料クーポン（申込から N 日間無料）は新に割引の種類が無い（2026-10-26 決定）"
NO_TARGET_ITEM = "受け皿なし"
TARGET_ITEM_DETAIL = "クーポンの対象の商品。新のクーポンは対象の商品を持たない"
PARENT_DETAIL = "移さないクーポンの対象者・使用の記録"
GROUP_DETAIL = "グループを対象にしたクーポン。新に受け皿が無い"
REMOVED_DETAIL = "対象者から外された行"


def migrates(row: dict) -> bool:
    """移すクーポンか。**無料クーポンは移さない。** グループが対象のものも受け皿が無い。"""
    return int(row.get("coupon_type") or 0) in (AMOUNT, RATE) and int(row.get("target_type") or 0) in (0, 2)


def discount_of(row: dict) -> tuple[str, int]:
    if int(row["coupon_type"]) == RATE:
        return "percent", int(row.get("discount_rate") or 0)
    return "amount", int(row.get("discount_amount") or 0)


def _start(value: date | None) -> datetime | None:
    return None if value is None else convert(datetime.combine(value, time(0, 0)), ColumnKind.DATETIME)


def _end(value: date | None) -> datetime | None:
    """旧の終了日は**その日を含む**。新は `[開始, 終わり)` なので翌日の 0 時（JST）にする。"""
    if value is None:
        return None
    return convert(datetime.combine(value + timedelta(days=1), time(0, 0)), ColumnKind.DATETIME)


def validity_of(row: dict) -> tuple[str, datetime | None, datetime | None, int | None]:
    """（期限の種類, 開始, 終わり, 日数）。

    - 期間（開始日・終了日）→ `fixed`
    - 配布日から N 日: 個人が対象 → `assignment_days`、全員 → `registration_days`
      （旧は「作った日と会員の登録日の遅い方」から数える。新は登録日から）
    - 登録日から M 日ずらす指定（`timing_chk`）は新で表せない → `none`（文書に記録）
    """
    start, end = row.get("coupon_start_date"), row.get("coupon_end_date")
    if start or end:
        return "fixed", _start(start), _end(end), None
    days = int(row.get("valid_term_day") or 0)
    if days and not int(row.get("timing_chk") or 0):
        kind = "assignment_days" if int(row.get("target_type") or 0) == 2 else "registration_days"
        return kind, None, None, days
    return "none", None, None, None


def status_of(row: dict) -> str:
    """削除済み・無効は `inactive`（新の状態にある値。Q1）。"""
    if int(row.get("del_chk") or 0) == 1 or int(row.get("valid_chk") or 0) == 0:
        return "inactive"
    return "active"


class CouponsStep(Step):
    name = "support.coupons"
    description = "クーポンを移す（無料クーポンは移さない）"
    source_table = "coupon"
    target_table = "coupons"

    def extract(self, ctx: RunContext) -> list[dict]:
        rows = []
        for row in ctx.require_source().fetch_for_tenant("coupon", COUPON_COLUMNS):
            if migrates(row):
                rows.append(row)
            elif int(row.get("coupon_type") or 0) == FREE:
                self.drop("coupons", f"coupon:{row['coupon_id']}", NOT_MIGRATED, FREE_DETAIL)
            else:
                self.drop("coupons", f"coupon:{row['coupon_id']}", NO_TARGET_ITEM, GROUP_DETAIL)
        return rows

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        records = []
        for row in rows:
            discount_type, discount_value = discount_of(row)
            validity, starts_at, expires_at, days = validity_of(row)
            records.append(
                Record(
                    table="coupons",
                    values={
                        "id": ctx.ulid.for_row("coupon", int(row["coupon_id"])),
                        "tenant_id": tenant_id,
                        "provider_coupon_id": "",
                        "provider_promotion_id": "",
                        "name": row.get("coupon_name") or "",
                        "code": row.get("coupon_code") or "",
                        "discount_type": discount_type,
                        "discount_value": discount_value,
                        "currency": "JPY",
                        "max_redemptions": None,  # 旧に全体の上限は無い
                        "validity_type": validity,
                        "starts_at": starts_at,
                        "expires_at": expires_at,
                        "validity_days": days,
                        # 旧の商品は講座の単品購入に当たる（コースの購入では新はクーポンを使えない）
                        "applies_to": "one_time",
                        "status": status_of(row),
                        "visible_to_learners": False,  # 旧に当たる値が無い（R2）
                        "audience_type": "specific_users" if int(row.get("target_type") or 0) == 2 else "all_users",
                        "created_at": convert(row.get("regist_date"), ColumnKind.TIMESTAMP),
                        "updated_at": convert(row.get("update_date"), ColumnKind.TIMESTAMP),
                    },
                    natural_key=("tenant_id", "code"),
                    source_key=f"coupon:{row['coupon_id']}",
                )
            )
        return records


def _migrated_ids(ctx: RunContext) -> set[int]:
    return {
        int(r["coupon_id"])
        for r in ctx.require_source().fetch_for_tenant("coupon", ("coupon_id", "coupon_type", "target_type"))
        if migrates(r)
    }


class CouponUsersStep(Step):
    """個人が対象のクーポンの対象者。`created_at` は**配布日**（配布日から N 日の起点）。"""

    name = "support.coupon_users"
    description = "クーポンの対象者を移す"
    source_table = "coupon_user"
    target_table = "coupon_user_targets"
    depends_on = ("support.coupons", "users")

    def extract(self, ctx: RunContext) -> list[dict]:
        migrated = _migrated_ids(ctx)
        rows = []
        for row in ctx.require_source().fetch_joined(
            "coupon_user", COUPON_USER_COLUMNS, parent="coupon", on="c.coupon_id = p.coupon_id"
        ):
            key = f"coupon_user:{row['coupon_user_id']}"
            if int(row["coupon_id"]) not in migrated:
                self.drop("coupon_user_targets", key, NOT_MIGRATED, PARENT_DETAIL)
            elif int(row.get("del_chk") or 0) == 1:
                self.drop("coupon_user_targets", key, NOT_MIGRATED, REMOVED_DETAIL)
            else:
                rows.append(row)
        return rows

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        return [
            Record(
                table="coupon_user_targets",
                values={
                    "coupon_id": ctx.ulid.for_row("coupon", int(row["coupon_id"])),
                    "user_id": ctx.ulid.for_row("user", int(row["user_id"])),
                    "tenant_id": tenant_id,
                    "created_at": convert(row.get("regist_date"), ColumnKind.TIMESTAMP),
                },
                natural_key=("coupon_id", "user_id"),
                source_key=f"coupon_user:{row['coupon_user_id']}",
            )
            for row in rows
        ]


class CouponLogsStep(Step):
    """使用の記録。新は（クーポン, 会員）で 1 行（旧も同じ会員の 2 回目は 0 件）。"""

    name = "support.coupon_logs"
    description = "クーポンの使用の記録を移す"
    source_table = "coupon_log"
    target_table = "coupon_redemptions"
    depends_on = ("support.coupons", "users")

    def extract(self, ctx: RunContext) -> list[dict]:
        migrated = _migrated_ids(ctx)
        rows = []
        for row in ctx.require_source().fetch_joined(
            "coupon_log", COUPON_LOG_COLUMNS, parent="coupon", on="c.coupon_id = p.coupon_id"
        ):
            if int(row["coupon_id"]) in migrated:
                rows.append(row)
            else:
                self.drop("coupon_redemptions", f"coupon_log:{row['coupon_log_id']}", NOT_MIGRATED, PARENT_DETAIL)
        return rows

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        return [
            Record(
                table="coupon_redemptions",
                values={
                    "id": ctx.ulid.for_row("coupon_log", int(row["coupon_log_id"])),
                    "tenant_id": tenant_id,
                    "coupon_id": ctx.ulid.for_row("coupon", int(row["coupon_id"])),
                    "user_id": ctx.ulid.for_row("user", int(row["user_id"])),
                    "redeemed_at": convert(row.get("regist_date"), ColumnKind.TIMESTAMP),
                },
                natural_key=("coupon_id", "user_id"),
                source_key=f"coupon_log:{row['coupon_log_id']}",
            )
            for row in rows
        ]


class CouponItemsStep(Step):
    """対象の商品。**新のクーポンは対象の商品を持たない**ので、行ごとに一覧に出す。"""

    name = "support.coupon_items"
    description = "クーポンの対象の商品（移さない。一覧に出す）"
    source_table = "coupon_item"
    target_table = ""

    def extract(self, ctx: RunContext) -> list[dict]:
        for row in ctx.require_source().fetch_joined(
            "coupon_item", ("coupon_item_id", "coupon_id"), parent="coupon", on="c.coupon_id = p.coupon_id"
        ):
            self.drop("coupon_item", f"coupon_item:{row['coupon_item_id']}", NO_TARGET_ITEM, TARGET_ITEM_DETAIL)
        return []

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        return []


def build() -> list[Step]:
    return [CouponsStep(), CouponUsersStep(), CouponLogsStep(), CouponItemsStep()]
