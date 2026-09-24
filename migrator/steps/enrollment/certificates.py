"""ondemand.7 — 修了証（旧 `config_certificate` / `user_certificate`）。

**同じ列名で意味が違う2つがある。取り違えない。**

- `certificate_settings.issuer_name` … テナントの設定。**NULL 可**（NULL なら `tenants.name`）
- `certificates.issuer_name`         … 発行済みの証書。**NOT NULL**（発行時点の値を凍結する）

**バッジの付与実績はここで移せない。** 旧 `badge_item` は「どの講座にどのバッジを出すか」の
**定義**で、誰が取ったかは**外部のバッジシステム**が持っている（`library/BadgeApi.class.php`）。
`digital_badges.user_id` は NOT NULL なので、外部からデータを受け取るまで1行も作れない。

**`cmd/import-certificates`（Go）とは役割分担しない。** 修了証は移行ツールで入れる。
"""

from __future__ import annotations

from ...context import RunContext
from ...core.datetimes import ColumnKind, convert
from ...core.records import Record
from ..base import Step

CONFIG_CERTIFICATE_COLUMNS = ("tenant_id", "message", "issuer_name", "regist_date")
USER_CERTIFICATE_COLUMNS = (
    "user_id",
    "certificate_id",
    "certificate_type",
    "entity_id",
    "certificate_no",
    "regist_date",
    "update_date",
)

#: 旧 `user_certificate.certificate_type`。`1` = 講座、`2` = 商品。
#: **商品単位の修了証は移らない**（`certificates.course_id` が NOT NULL。2026-09-23 決定）
CERTIFICATE_TYPE_COURSE = 1


class CertificateSettingsStep(Step):
    """`config_certificate` を `certificate_settings` に移す。

    **行が無いテナントには作らない。** 既定値だけの行を作ると
    「運営が設定した」のか「移行が埋めた」のか区別が付かなくなる。
    """

    name = "enrollment.certificate_settings"
    description = "修了証のテナント設定を移す"
    source_table = "config_certificate"
    target_table = "certificate_settings"
    depends_on = ("content.lessons",)

    def extract(self, ctx: RunContext) -> list[dict]:
        return ctx.require_source().fetch_for_tenant(
            "config_certificate", CONFIG_CERTIFICATE_COLUMNS
        )

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        if not rows:
            ctx.logger.info(
                "config_certificate に行が無い。**設定は作らない**"
                "（発行済み修了証の発行者名はテナント名で埋める）"
            )
        return [
            Record(
                table="certificate_settings",
                values={
                    "tenant_id": tenant_id,
                    "message": row.get("message"),
                    # **設定側は NULL 可。** NULL なら新環境が `tenants.name` を使う
                    "issuer_name": row.get("issuer_name"),
                    "created_at": convert(row.get("regist_date"), ColumnKind.TIMESTAMP),
                },
                natural_key=("tenant_id",),
                source_key=int(row["tenant_id"]),
            )
            for row in rows
        ]


def _issued(ctx: RunContext) -> list[dict]:
    """発行済みの修了証。**会員を持つが `tenant_id` を持たない**ので `user` で絞る。"""
    return ctx.require_source().fetch_joined(
        "user_certificate",
        USER_CERTIFICATE_COLUMNS,
        parent="user",
        on="c.user_id = p.user_id",
    )


class CertificatesStep(Step):
    """`user_certificate` を `certificates` に移す。"""

    name = "enrollment.certificates"
    description = "発行済みの修了証を移す"
    source_table = "user_certificate"
    target_table = "certificates"
    depends_on = ("enrollment.certificate_settings",)

    def extract(self, ctx: RunContext) -> list[dict]:
        source = ctx.require_source()
        settings = source.fetch_for_tenant("config_certificate", CONFIG_CERTIFICATE_COLUMNS)
        issuer = (settings[0].get("issuer_name") if settings else None) or ctx.config.tenant.name
        message = settings[0].get("message") if settings else None
        rows: list[dict] = []
        for row in _issued(ctx):
            if int(row.get("certificate_type") or 0) != CERTIFICATE_TYPE_COURSE:
                continue  # 商品単位。`course_id` が決まらないので移さない
            rows.append({**row, "_issuer": issuer, "_message": message})
        return rows

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        return [
            Record(
                table="certificates",
                values={
                    "id": _certificate_ulid(ctx, row),
                    "tenant_id": tenant_id,
                    "user_id": ctx.ulid.for_row("user", row["user_id"]),
                    # `certificate_type = 1` のとき `entity_id` は旧 `lesson_id`（講座）
                    "course_id": ctx.ulid.for_row("lesson", row["entity_id"]),
                    "serial_no": int(row.get("certificate_no") or 0),
                    # **NOT NULL。** 旧は整数なので文字列にして入れる（書式は後から適用）
                    "serial_text": str(row.get("certificate_no") or ""),
                    # **NOT NULL。** 発行時点の値を凍結する列。設定が無ければテナント名
                    "issuer_name": row["_issuer"],
                    "message": row["_message"],
                    "issued_at": convert(row.get("regist_date"), ColumnKind.DATETIME),
                },
                natural_key=("tenant_id", "user_id", "course_id"),
                source_key=f"{row['user_id']}:{row['entity_id']}",
            )
            for row in rows
        ]


class CertificateEventsStep(Step):
    """発行を `certificate_events` に1件だけ残す。

    **旧に発行の履歴が無い**ので、`issued` を1件作るだけ。取り消し・再発行は記録が無い。
    """

    name = "enrollment.certificate_events"
    description = "修了証の発行イベントを1件作る"
    source_table = "user_certificate"
    target_table = "certificate_events"
    depends_on = ("enrollment.certificates",)

    def extract(self, ctx: RunContext) -> list[dict]:
        return CertificatesStep().extract(ctx)

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        return [
            Record(
                table="certificate_events",
                values={
                    "id": ctx.ulid.for_row(
                        "user_certificate_event", f"{row['user_id']}:{row['entity_id']}"
                    ),
                    "tenant_id": tenant_id,
                    "certificate_id": _certificate_ulid(ctx, row),
                    "event_kind": "issued",
                    # 旧に「誰が発行したか」が無い。自動発行と区別できないので NULL
                    "actor_user_id": None,
                    "reason_code": None,
                    "note": "lw2 からの移行",
                    "occurred_at": convert(row.get("regist_date"), ColumnKind.DATETIME),
                },
                natural_key=("id",),
                source_key=f"{row['user_id']}:{row['entity_id']}",
            )
            for row in rows
        ]


def _certificate_ulid(ctx: RunContext, row: dict) -> str:
    """**旧 `user_certificate` に単一の主キーが無い。** `(user_id, entity_id)` から採番する。"""
    return ctx.ulid.for_row("user_certificate", f"{int(row['user_id'])}:{int(row['entity_id'])}")


def build() -> list[Step]:
    return [CertificateSettingsStep(), CertificatesStep(), CertificateEventsStep()]
