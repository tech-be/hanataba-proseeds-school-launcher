"""billing.3 — 帳票（領収書・規約の本文）。

**領収書は決済に紐づく**（`receipts.payment_id` NOT NULL、RESTRICT）。決済（billing.2）の後に流す。

- lw2 の `receipt_log` は **PDF をダウンロードするたびに1行**（再発行も1行）。新の `issue_no` は
  決済ごとの連番なので、申込ごとに `receipt_log_id` の順で 1, 2, … と振り直す。
  **旧で印字していた番号は `receipt_log_id`** なので `legacy_id` に残す（P11）
- 取引日は**申込の入金日**（lw2 の `real_payment_date` と同じ規則。→ `payments.paid_at`）
- 規約の本文（`agreement` / `cancel_policy` / `privacy_policy` / `tokusyo`）は新に置き場が無いので
  `tenant_legal_documents` を足して受ける（P12）。**アプリはまだ読まない**。空の本文は移さない
- 消費税の一覧（`tax`）は移さない（P14）。設定画面の選択肢で、取引の税計算に使っていない
"""

from __future__ import annotations

from ...context import RunContext
from ...core.datetimes import ColumnKind, convert
from ...core.records import Record
from ..base import Step
from . import payments as pay

RECEIPT_SETTING_COLUMNS = (
    "tenant_id", "valid_chk", "company_name", "zip_code", "address", "tel",
    "invoice_chk", "tax_rate", "invoice_no", "regist_date", "update_date",
)
RECEIPT_LOG_COLUMNS = (
    "receipt_log_id", "user_id", "application_id", "receipt_date", "receipt_price",
    "company_name", "zip_code", "address", "tel", "invoice_chk", "tax_rate", "tax_rate_treatment",
    "invoice_no", "excluding_tax_price", "receipt_name", "receipt_provision", "seq_no",
    "payment_date_from", "payment_date_to", "regist_date",
)

#: 旧の表 → (新の種類, 本文の列, `payment_infomation` の上書きの接頭辞)
LEGAL_TABLES = (
    ("agreement", "terms", "agreement", "agreement"),
    ("cancel_policy", "cancel_policy", "cancel_policy", "cancel_policy"),
    ("privacy_policy", "privacy_policy", "privacy_policy", "privacy_policy"),
    ("tokusyo", "commercial_disclosure", "tokusyo", "tokusyo"),
)
PAYMENT_INFO_OVERRIDE_COLUMNS = tuple(
    f"{prefix}_{suffix}"
    for _, _, _, prefix in LEGAL_TABLES
    for suffix in ("another_url_chk", "another_url", "title_chk", "title")
)


class ReceiptSettingsStep(Step):
    """`receipt_setting` を `receipt_settings` に移す（テナントに1行）。"""

    name = "billing.receipt_settings"
    description = "領収書の発行設定を移す"
    source_table = "receipt_setting"
    target_table = "receipt_settings"
    depends_on = ("tenant",)

    def extract(self, ctx: RunContext) -> list[dict]:
        return ctx.require_source().fetch_for_tenant("receipt_setting", RECEIPT_SETTING_COLUMNS)

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        return [
            Record(
                table="receipt_settings",
                values={
                    "tenant_id": tenant_id,
                    "enabled": int(row.get("valid_chk") or 0) == 1,
                    "issuer_name": row.get("company_name") or "",
                    "postal_code": row.get("zip_code") or None,
                    "address": row.get("address") or None,
                    "tel": row.get("tel") or None,
                    # インボイスの登録番号。`invoice_chk` はテナントの settings（lw2_payment）に残す
                    "invoice_registration_no": row.get("invoice_no") or None,
                    "tax_rate": row.get("tax_rate"),
                    "created_at": convert(row.get("regist_date"), ColumnKind.DATETIME),
                },
                natural_key=("tenant_id",),
                source_key=ctx.config.tenant.legacy_id,
            )
            for row in rows[:1]
        ]


class ReceiptsStep(Step):
    """発行済みの領収書（`receipt_log`）を `receipts` に移す（P11）。"""

    name = "billing.receipts"
    description = "発行済みの領収書を移す"
    source_table = "receipt_log"
    target_table = "receipts"
    depends_on = ("billing.payments", "billing.receipt_settings")

    def extract(self, ctx: RunContext) -> list[dict]:
        apps = {int(a["application_id"]): a for a in pay.applications(ctx)}
        rows = sorted(
            ctx.require_source().fetch_for_tenant("receipt_log", RECEIPT_LOG_COLUMNS),
            key=lambda r: int(r["receipt_log_id"]),
        )
        # **決済ごとの連番。** 旧の再発行（同じ申込の2行目以降）は 2, 3, …
        seen: dict[int, int] = {}
        for row in rows:
            app_id = int(row["application_id"])
            seen[app_id] = seen.get(app_id, 0) + 1
            row["_issue_no"] = seen[app_id]
            row["_app"] = apps.get(app_id)
        return rows

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        records = []
        for row in rows:
            app = row.get("_app")
            # 決済が移らない申込（無料など）の領収書は、payment_id の外部キーで弾かれて一覧に出る
            paid = pay.paid_at(app, app.get("_item")) if app else None
            records.append(
                Record(
                    table="receipts",
                    values={
                        "id": ctx.ulid.for_row("receipt_log", row["receipt_log_id"]),
                        "tenant_id": tenant_id,
                        "user_id": ctx.ulid.for_row("user", row["user_id"]),
                        "payment_id": ctx.ulid.for_row("payment_application", row["application_id"]),
                        "issue_no": row["_issue_no"],
                        "legacy_id": int(row["receipt_log_id"]),
                        "recipient_name": row.get("receipt_name") or "",
                        "note": row.get("receipt_provision") or "",
                        "amount": row.get("receipt_price") or 0,
                        "currency": "JPY",
                        "tax_excluded_amount": row.get("excluding_tax_price"),
                        "tax_rate": row.get("tax_rate"),
                        # **発行時点の写し。** 旧もダウンロードのたびに設定を写していた
                        "issuer_name": row.get("company_name") or "",
                        "issuer_postal_code": row.get("zip_code") or None,
                        "issuer_address": row.get("address") or None,
                        "issuer_tel": row.get("tel") or None,
                        "issuer_invoice_registration_no": row.get("invoice_no") or None,
                        "transaction_date": pay.as_date(paid) if paid else row.get("payment_date_from"),
                        "issued_at": convert(row.get("regist_date"), ColumnKind.DATETIME),
                    },
                    natural_key=("tenant_id", "legacy_id"),
                    source_key=int(row["receipt_log_id"]),
                )
            )
        return records


class LegalDocumentsStep(Step):
    """規約の本文を `tenant_legal_documents` に移す（P12）。**空の本文は移さない。**"""

    name = "billing.legal_documents"
    description = "規約・プライバシーポリシー・特商法表記の本文を移す"
    source_table = "agreement"
    target_table = "tenant_legal_documents"
    depends_on = ("tenant",)

    def extract(self, ctx: RunContext) -> list[dict]:
        source = ctx.require_source()
        info = source.fetch_for_tenant("payment_infomation", PAYMENT_INFO_OVERRIDE_COLUMNS)
        overrides = info[0] if info else {}
        rows = []
        for table, kind, column, prefix in LEGAL_TABLES:
            url = _override(overrides, prefix, "another_url")
            title = _override(overrides, prefix, "title")
            for row in source.fetch_for_tenant(
                table, (column, "language_code", "regist_date", "update_date")
            ):
                body = (row.get(column) or "").strip()
                if not body and not url:
                    continue  # 本文も外部 URL も無い。移すものが無い
                rows.append({
                    "kind": kind, "language_code": (row.get("language_code") or "ja").strip(),
                    "title": title, "body": body or None, "external_url": url,
                    "regist_date": row.get("regist_date"), "update_date": row.get("update_date"),
                })
        return rows

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        return [
            Record(
                table="tenant_legal_documents",
                values={
                    "id": ctx.ulid.for_row("legal_document", f"{row['kind']}:{row['language_code']}"),
                    "tenant_id": tenant_id,
                    "kind": row["kind"],
                    "language_code": row["language_code"],
                    "title": row["title"],
                    "body": row["body"],
                    "external_url": row["external_url"],
                    "created_at": convert(row.get("regist_date"), ColumnKind.DATETIME),
                },
                natural_key=("tenant_id", "kind", "language_code"),
                source_key=f"{row['kind']}:{row['language_code']}",
            )
            for row in rows
        ]


def _override(info: dict, prefix: str, field: str) -> str | None:
    """`payment_infomation` の上書き。**`*_chk = 1` のときだけ有効**（値だけ残っていることがある）。"""
    if int(info.get(f"{prefix}_{field}_chk") or 0) != 1:
        return None
    return (info.get(f"{prefix}_{field}") or "").strip() or None


def build() -> list[Step]:
    """4-3 帳票。"""
    return [ReceiptSettingsStep(), ReceiptsStep(), LegalDocumentsStep()]
