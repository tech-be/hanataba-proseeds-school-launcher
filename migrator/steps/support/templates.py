"""support.9 — 自動メールの文面（`mail_setting`）と LINE の文面（`line_message_mail_setting`）。

docs/db/05-support/migration-spec.md 0-3・0-9。

- **新に種別があるものだけ移す。** 旧の種類 → 新の種別は下の対応表（Q7 で、同じ新の種別に
  当たる旧の種類から 1 つを採った）
- 採らなかった種類・新に種別が無い種類・英語の文面は一覧に出す
- **差し込みの書き換え（`{USER_NAME}` → `{{user_name}}` など）はしない。** 値の直しなので
  補正データ（`fixups`）で行い、ここでは読むだけ（Q8）
- 削除済みは `enabled = FALSE`（新の状態にある値。Q1）
- LINE の文面は種類 35「登録完了（SNS 連携）」にしか無いので、メールは 20 を採るが
  LINE は 35 を `welcome` に入れる（R3）
"""

from __future__ import annotations

import re

from ...context import RunContext
from ...core.datetimes import ColumnKind, convert
from ...core.records import Record
from ..base import Step

#: 旧の種類（`mail_type_id`）→ 新の種別（`email_kinds.code`）。**メールとして移すもの**
MAIL_KINDS: dict[int, str] = {
    7: "inquiry_received",  # お問い合わせの通知（管理者）
    13: "password_reset",  # パスワードリマインダー
    20: "welcome",  # 登録完了
    21: "payment_succeeded",  # お申込み内容
    31: "email_verification",  # メールアドレスの確認
    32: "subscription_canceled",  # 有料講座の解約
}
#: 同じ新の種別に当たるが、**採らなかった**旧の種類（Q7）
NOT_ADOPTED: dict[int, str] = {
    35: "welcome（20 を採った）",
    47: "payment_succeeded（21 を採った）",
    34: "payment_succeeded（21 を採った）",
    23: "subscription_canceled（32 を採った）",
}
#: LINE の文面の行き先。**新が LINE で 1 人ずつ送れる種別だけ**（`line/service/text.go`）
LINE_KINDS: dict[int, str] = {35: "welcome", 20: "welcome", 21: "payment_succeeded", 32: "subscription_canceled"}

MAIL_COLUMNS = (
    "mail_setting_id", "mail_type_id", "title", "body", "language_code", "regist_date", "update_date", "del_chk",
)
LINE_COLUMNS = ("mail_type_id", "message", "regist_date")

NOT_MIGRATED = "移行対象外"
NO_PLACE = "受け皿なし"
#: 旧の差し込み（`{USER_NAME}` など）。**残ったまま移すと、その文字のまま会員に届く**
LEGACY_PLACEHOLDER = re.compile(r"\{[A-Z][A-Z0-9_]*\}")
WAITING = "移行対象外"
WAITING_DETAIL = "旧の差し込みが残っている（新の書き方に直した文面を補正データに書いてから移す。Q8）"


def has_legacy_placeholder(*texts: object) -> bool:
    return any(LEGACY_PLACEHOLDER.search(str(t or "")) for t in texts)


class MailTemplatesStep(Step):
    name = "support.mail_templates"
    description = "自動メールの文面を移す（新に種別があるものだけ）"
    source_table = "mail_setting"
    target_table = "tenant_email_templates"

    def extract(self, ctx: RunContext) -> list[dict]:
        rows = []
        for row in ctx.require_source().fetch_for_tenant("mail_setting", MAIL_COLUMNS):
            type_id, key = int(row["mail_type_id"]), f"mail_setting:{row['mail_setting_id']}"
            if (row.get("language_code") or "ja").strip() != "ja":
                self.drop("tenant_email_templates", key, NOT_MIGRATED, "日本語以外の文面（新は言語ごとの文面を持たない）")
            elif type_id in NOT_ADOPTED:
                self.drop("tenant_email_templates", key, NOT_MIGRATED, f"同じ新の種別に別の旧の文面を採った: {NOT_ADOPTED[type_id]}")
            elif type_id not in MAIL_KINDS:
                self.drop("tenant_email_templates", key, NO_PLACE, f"旧の種類 {type_id} に当たる新の種別が無い（または新に送る処理が無い）")
            elif has_legacy_placeholder(row.get("title"), row.get("body")):
                self.drop("tenant_email_templates", key, WAITING, WAITING_DETAIL)
            else:
                rows.append(row)
        return rows

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        return [
            Record(
                table="tenant_email_templates",
                values={
                    "id": ctx.ulid.for_row("mail_setting", int(row["mail_setting_id"])),
                    "tenant_id": tenant_id,
                    "kind": MAIL_KINDS[int(row["mail_type_id"])],
                    "subject": row.get("title") or "",
                    "body": row.get("body") or "",
                    "enabled": int(row.get("del_chk") or 0) == 0,
                    "created_at": convert(row.get("regist_date"), ColumnKind.TIMESTAMP),
                    "updated_at": convert(row.get("update_date"), ColumnKind.TIMESTAMP),
                },
                natural_key=("tenant_id", "kind"),
                source_key=f"mail_setting:{row['mail_setting_id']}",
            )
            for row in rows
        ]


class LineTemplatesStep(Step):
    name = "support.line_templates"
    description = "自動メールの LINE の文面を移す"
    source_table = "line_message_mail_setting"
    target_table = "tenant_line_templates"

    def extract(self, ctx: RunContext) -> list[dict]:
        rows = []
        for row in ctx.require_source().fetch_for_tenant("line_message_mail_setting", LINE_COLUMNS):
            key = f"line_message_mail_setting:{row['mail_type_id']}"
            if int(row["mail_type_id"]) in LINE_KINDS and has_legacy_placeholder(row.get("message")):
                self.drop("tenant_line_templates", key, WAITING, WAITING_DETAIL)
            elif int(row["mail_type_id"]) in LINE_KINDS:
                rows.append(row)
            else:
                self.drop(
                    "tenant_line_templates", f"line_message_mail_setting:{row['mail_type_id']}", NO_PLACE,
                    f"旧の種類 {row['mail_type_id']} に当たる、LINE で送れる新の種別が無い",
                )
        return rows

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        legacy = ctx.require_source().tenant_id
        return [
            Record(
                table="tenant_line_templates",
                values={
                    "id": ctx.ulid.for_row("line_message_mail_setting", f"{legacy}:{row['mail_type_id']}"),
                    "tenant_id": tenant_id,
                    "kind": LINE_KINDS[int(row["mail_type_id"])],
                    "body": row.get("message") or "",
                    "created_at": convert(row.get("regist_date"), ColumnKind.TIMESTAMP),
                },
                natural_key=("tenant_id", "kind"),
                source_key=f"line_message_mail_setting:{row['mail_type_id']}",
            )
            for row in rows
        ]


def build() -> list[Step]:
    return [MailTemplatesStep(), LineTemplatesStep()]
