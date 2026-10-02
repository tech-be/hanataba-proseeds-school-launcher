"""support.8 — 利用料の計上用の集計（旧 `accounting_user` / `accounting_user_detail` / `config_closing_date`）。

2026-09-30 に「その他」から 05 へ仕分けたもの。旧は月に1回、締め日の翌日にテナントの会員数を
数えて残していた。受け皿 `tenant_usage_settings` / `tenant_usage_snapshots` /
`tenant_usage_snapshot_users` を新設した（新のアプリはまだ読まない）。

**会員の写しの `user_id` は、移行先に入っている会員だけに付ける。** 旧で会員が消えている、
または制約に当たって移らなかった会員は NULL にし、旧の ID を `legacy_user_id` に残す。
"""

from __future__ import annotations

from ...context import RunContext
from ...core.datetimes import ColumnKind, convert, convert_date
from ...core.records import Record
from ..base import Step

CLOSING_COLUMNS = ("month_end_chk", "closing_date", "update_date")
SNAPSHOT_COLUMNS = (
    "tenant_name", "accounting_user_count", "student_count", "total_manager_count",
    "group_manager_count", "instructor_manager_count", "closing_date", "batch_date",
)
SNAPSHOT_USER_COLUMNS = (
    "user_id", "login_id", "name_sei", "name_mei", "role_id", "entry_date", "limit_date",
    "regist_date", "update_date", "batch_date",
)


class UsageSettingsStep(Step):
    name = "support.usage_settings"
    description = "利用料の締め日を移す"
    source_table = "config_closing_date"
    target_table = "tenant_usage_settings"
    depends_on = ("tenant",)

    def extract(self, ctx: RunContext) -> list[dict]:
        return ctx.require_source().fetch_for_tenant("config_closing_date", CLOSING_COLUMNS)

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        return [
            Record(
                table="tenant_usage_settings",
                values={
                    "tenant_id": ctx.tenant_id.value,
                    "closing_day": row.get("closing_date"),
                    "month_end": bool(int(row.get("month_end_chk") or 0)),
                    "updated_at": convert(row.get("update_date"), ColumnKind.TIMESTAMP),
                },
                natural_key=("tenant_id",),
            )
            for row in rows
        ]


class UsageSnapshotsStep(Step):
    name = "support.usage_snapshots"
    description = "月次の会員数の集計を移す"
    source_table = "accounting_user"
    target_table = "tenant_usage_snapshots"
    depends_on = ("tenant",)

    def extract(self, ctx: RunContext) -> list[dict]:
        return ctx.require_source().fetch_for_tenant("accounting_user", SNAPSHOT_COLUMNS)

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        return [
            Record(
                table="tenant_usage_snapshots",
                values={
                    "id": ctx.ulid.for_row("accounting_user", str(row["batch_date"])),
                    "tenant_id": tenant_id,
                    "batch_date": convert_date(row.get("batch_date"), ColumnKind.DATE),
                    "closing_date": convert_date(row.get("closing_date"), ColumnKind.DATE),
                    "tenant_name": row.get("tenant_name"),
                    "accounting_user_count": row.get("accounting_user_count"),
                    "student_count": row.get("student_count"),
                    "total_manager_count": row.get("total_manager_count"),
                    "group_manager_count": row.get("group_manager_count"),
                    "instructor_manager_count": row.get("instructor_manager_count"),
                },
                natural_key=("tenant_id", "batch_date"),
                source_key=str(row["batch_date"]),
            )
            for row in rows
        ]


class UsageSnapshotUsersStep(Step):
    name = "support.usage_snapshot_users"
    description = "集計した時点の会員の写しを移す"
    source_table = "accounting_user_detail"
    target_table = "tenant_usage_snapshot_users"
    depends_on = ("users",)

    def extract(self, ctx: RunContext) -> list[dict]:
        rows = ctx.require_source().fetch_for_tenant("accounting_user_detail", SNAPSHOT_USER_COLUMNS)
        # 移行先に入っている会員（旧 ID）。入っていない会員は user_id を NULL にする
        found = ctx.target.query(
            "SELECT user_id FROM users WHERE tenant_id = %s AND user_id IS NOT NULL",
            (ctx.tenant_id.value,),
        )
        migrated = {int(r["user_id"]) for r in found}
        for row in rows:
            row["_migrated"] = int(row["user_id"]) in migrated
        return rows

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        roles = ctx.role_map()
        records = []
        for row in rows:
            key = f"{row['batch_date']}:{int(row['user_id'])}"
            role_id = row.get("role_id")
            records.append(
                Record(
                    table="tenant_usage_snapshot_users",
                    values={
                        "id": ctx.ulid.for_row("accounting_user_detail", key),
                        "tenant_id": tenant_id,
                        "batch_date": convert_date(row.get("batch_date"), ColumnKind.DATE),
                        "user_id": ctx.ulid.for_row("user", int(row["user_id"])) if row["_migrated"] else None,
                        "legacy_user_id": int(row["user_id"]),
                        "login_id": row.get("login_id"),
                        "name_last": row.get("name_sei"),
                        "name_first": row.get("name_mei"),
                        "role": roles.optional(int(role_id)) if role_id is not None else None,
                        "entry_date": convert_date(row.get("entry_date"), ColumnKind.DATE),
                        "limit_date": convert_date(row.get("limit_date"), ColumnKind.DATE),
                        "registered_at": convert(row.get("regist_date"), ColumnKind.DATETIME),
                        "updated_at": convert(row.get("update_date"), ColumnKind.DATETIME),
                    },
                    natural_key=("tenant_id", "batch_date", "legacy_user_id"),
                    source_key=key,
                )
            )
        return records


def build() -> list[Step]:
    return [UsageSettingsStep(), UsageSnapshotsStep(), UsageSnapshotUsersStep()]
