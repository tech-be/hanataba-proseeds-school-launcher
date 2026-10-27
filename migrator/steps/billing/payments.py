"""billing.2 — 決済（申込）。

**旧の商品は `tenant_plans` / `plan_courses` に入れない**（2026-10-23 決定）。新の `tenant_plans` は Stripe の
継続課金のプランで、旧の商品にあたるのはコース（`learning_paths`。コンテンツの `content.5`）。

**lw2 は申込1行 = 契約1件。** 継続課金・分割の毎月の課金は決済代行（J-Payment）が
持っていて、lw2 には行が無い（`PaymentGatewayController` の継続課金の通知は行を作らない）。
返金の概念も無い。移すのは**申込の時点の決済**（商品はコースとしてコンテンツで移す）。

**暫定の規則（決定ではない。docs/db/04-billing/migration-spec.md 1-3 の P1〜P10）**

- 決済として移すのは**お金が動く申込だけ**（`payment_type` 1 カード / 2 コンビニ / 3 振込）。
  0 無料 / 4 無料クーポン / 5・6・7 チケット払いは金額0で、権限は受講（3）、チケットは
  4-1 で移っている。`application_result = 3`（支払い不要）も移さない
- 種類: **講座の商品（`item_type = 0`）→ `learning_path_purchase`**（コースの購入。買い切りも自動継続も。
  2026-10-22 決定。明細は `learning_path_purchase_payments`）、それ以外の自動継続の商品 → `subscription`、
  それ以外（チケット・ライブの商品、商品なし）→ `lw2_purchase`
- 状態: `application_result` 1 → `succeeded` / 0 → `pending` / 2 → `failed`。
  **解約（`is_cancel`）は状態にしない** — 返金ではなく継続課金を止めただけで、お金は動いている
- 決済代行: カード・コンビニ → `legacy_jpayment`、振込 → `bank_transfer`。
  `provider_payment_id` は `lw2-{application_id}`。受講（`enrollments.provider_payment_id`）も
  この値で結ぶ（→ `provider_payment_id()`）
- 手数料（`platform_fee`）は 0。lw2 に手数料の概念が無い
- 継続課金（`learner_subscriptions`）と分割（`installment_plans`）は作らない。新の必須 ID
  （Stripe）が無く、毎月の課金の行も lw2 に無い

**列名に反するもの**（lw2 の実装を読んで確定。docs/db/04-billing/review.md）

- `payment_item.price` / `first_price` は**税込**（コメントの「税抜」は誤り）
- `payment_application.tax` は常に 0（INSERT で固定値）。使わない
- `credit_payment_date` は「課金を後ろ倒しにした日」。申込日と違うときだけ意味がある
"""

from __future__ import annotations

import json
from datetime import date, datetime

from ...context import RunContext
from ...core.datetimes import ColumnKind, convert
from ...core.records import Record
from ..base import Step

#: 旧 `payment_item` から読む列。フォームの入力項目設定・HTML タグ（`edit_tag_*` など）は読まない
ITEM_COLUMNS = (
    "item_id", "item_type", "live_lesson_id", "item_name", "description",
    "invoice_chk", "tax_rate_treatment", "excluding_tax_price", "excluding_tax_first_price",
    "excluding_tax_extension_price", "price", "first_price", "extension_price", "extension_type",
    "ticket_num", "ticket_count", "ticket_price",
    "is_auto_extension", "is_use_trial", "trial_term", "trial_term_type",
    "is_auto_cancel", "auto_cancel_term", "manual_term", "manual_term_type", "no_limit_chk",
    "valid_chk", "display_chk", "payment_date_type", "payment_day", "sort_no",
    "is_use_credit_card", "is_use_convenience", "is_use_bank", "remote_chk",
    "regist_date", "update_date", "del_chk",
)
ITEM_LESSON_COLUMNS = ("item_set_lesson_id", "item_id", "lesson_id", "del_chk", "regist_date")

#: 旧 `payment_application` から読む列。**申込フォームの個人情報（氏名・住所・電話・
#: メール・生年月日）と `password` は読まない** — 会員は `users` に移っており、
#: 申込の写しを決済に持たせる理由が無い。`application_memo`（自由記述の質問）も読まない
APPLICATION_COLUMNS = (
    "application_id", "user_id", "payment_type", "application_date_time", "payment_date",
    "invoice_chk", "tax_rate", "tax_rate_treatment", "excluding_tax_price",
    "excluding_tax_first_price", "excluding_tax_extension_price", "amount", "first_amount",
    "ticket_num", "ticket_count", "ticket_id", "ticket_price",
    "jpayment_application_id", "application_result", "order_shop_code", "error_code",
    "jpayment_order_code", "auto_credit_id", "auto_credit_price", "payment_status",
    "convenience_code", "convenience_payment_limit", "convenience_payment_date",
    "bank_payment_status", "bank_payment_date", "admin_cancel_chk", "is_cancel",
    "cancel_date_time", "is_use_trial", "is_auto_cancel", "auto_cancel_term", "auto_cancel_date",
    "is_extension_item", "extension_application_id", "is_complete_extension",
    "credit_payment_date", "is_use_split_payment", "split_payment_number",
    "coupon_id", "coupon_type", "coupon_discount", "before_coupon_price", "after_coupon_price",
    "live_lesson_reserve_id", "live_lesson_date_id", "no_payment_required",
)

#: お金が動く `payment_type`（1 カード / 2 コンビニ / 3 振込）
MONEY_TYPES = frozenset({1, 2, 3})
#: `application_result`: 0 入金待ち / 1 支払い完了 / 2 エラー / 3 支払い不要（管理者が設定）
NO_PAYMENT_REQUIRED = 3
#: **入金待ち（0）は `failed`**（0-2 Q6）。`pending` だと新の毎時の照合が全テナントで古い順に 100 件しか見ない枠を埋め、
#: 振込は入金確認の一覧に出てボタンで受講権限が付く。旧の値は `settings.legacy_application_result` に残す
STATUSES = {0: "failed", 1: "succeeded", 2: "failed"}
PROVIDERS = {1: "legacy_jpayment", 2: "legacy_jpayment", 3: "bank_transfer"}
#: `item_type`: 0 講座 / 1 チケット（都度）/ 2 チケット（月次）/ 3 ライブ
COURSE_ITEM = 0


def provider_payment_id(application_id: object) -> str:
    """決済代行の決済 ID。**受講（`enrollments.provider_payment_id`）もこの値で結ぶ。**"""
    return f"lw2-{int(application_id)}"


def is_migrated(payment_type: object, application_result: object) -> bool:
    """この申込を決済として移すか（P3 / P4）。**受講権限の Step も同じ判定を使う。**"""
    if payment_type is None or int(payment_type) not in MONEY_TYPES:
        return False
    return int(application_result or 0) != NO_PAYMENT_REQUIRED


def payment_kind(item: dict | None) -> str:
    """決済の種類（P5）。

    **講座の商品はコースの購入**（2026-10-22 決定）。school-launcher はコース（`learning_paths`）＝旧の
    販売商品とし、その決済を `learning_path_purchase` で持つ（20261012014810）。受講（03）のコースの購入
    （`learning_path_enrollments.payment_id`）もこの決済を指す。**自動継続の商品も同じ**にそろえる
    （新のコースに継続課金は無い。自動継続だったことは決済の `settings.item.auto_extension` に残す）。
    """
    if item is not None and int(item.get("item_type") or 0) == COURSE_ITEM:
        return "learning_path_purchase"
    if item is not None and int(item.get("is_auto_extension") or 0) == 1:
        return "subscription"
    return "lw2_purchase"


def paid_at(app: dict, item: dict | None) -> datetime | None:
    """入金日。**lw2 の `real_payment_date` と同じ規則**（`PaymentModel:110-113`）。

    カードは課金を後ろ倒しにした日（申込日と違い、試用なしのとき）、コンビニ・振込は
    それぞれの入金日、それ以外は申込日。
    """
    applied = app.get("application_date_time")
    kind = int(app.get("payment_type") or 0)
    if kind == 1:
        deferred = app.get("credit_payment_date")
        trial = int((item or {}).get("is_use_trial") or 0) == 1
        if deferred is not None and not trial and applied is not None and as_date(deferred) != as_date(applied):
            return deferred
        return applied
    if kind == 2:
        return app.get("convenience_payment_date")
    if kind == 3:
        return app.get("bank_payment_date")
    return applied


def as_date(value) -> date | None:
    if value is None:
        return None
    return value.date() if isinstance(value, datetime) else value


def _compact(value):
    """None・空文字を落とした JSON 向けの値。"""
    if isinstance(value, dict):
        out = {k: _compact(v) for k, v in value.items()}
        return {k: v for k, v in out.items() if v not in (None, "", {}, [])}
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if hasattr(value, "as_tuple"):  # Decimal
        return float(value) if value != int(value) else int(value)
    return value


def _json(value) -> str | None:
    value = _compact(value)
    return json.dumps(value, ensure_ascii=False) if value else None


# --- 抽出（Step をまたいで使う）----------------------------------------------
def items(ctx: RunContext) -> dict[int, dict]:
    """商品。旧 ID → 行（講座の旧 ID の一覧 `_lessons` を添える）。"""
    source = ctx.require_source()
    rows = {int(r["item_id"]): r for r in source.fetch_for_tenant("payment_item", ITEM_COLUMNS)}
    for row in rows.values():
        row["_lessons"] = []
    for link in source.fetch_joined(
        "payment_item_lesson", ITEM_LESSON_COLUMNS,
        parent="payment_item", on="c.item_id = p.item_id", where="c.del_chk = 0",
    ):
        item = rows.get(int(link["item_id"]))
        if item is not None:
            item["_lessons"].append(int(link["lesson_id"]))
    return rows


def course_item_links(ctx: RunContext, drop) -> list[dict]:
    """講座の商品と講座の結び付き（`payment_item_lesson`）。(商品, 講座) ごとに1行。

    **削除済みの結び付きも返す**（`_alive` が False）。同じ組が積まれていれば生きている行を優先する。
    移行の対象に無い講座を指す行は `drop(table_key, reason, detail)` に渡して返さない。
    `content.learning_path_courses` が使う（課金の `plan_courses` には 2026-10-23 から入れない）。
    """
    course_items = {i for i, row in items(ctx).items() if int(row.get("item_type") or 0) == COURSE_ITEM}
    # このテナントの講座と、移す共有講座。**ここに無い講座は移らない**（削除済みの対応は、講座そのものが
    # 物理削除されていることがある。他テナントの講座を指す行もあり得るが、テナントで絞らずに
    # 旧の講座を引くことはガードで禁じているので、どちらかは区別しない）
    known = {int(r["lesson_id"]) for r in ctx.require_source().fetch_for_tenant("lesson", ("lesson_id",))}
    links = ctx.require_source().fetch_joined(
        "payment_item_lesson", ("item_set_lesson_id", "item_id", "lesson_id", "del_chk", "update_date"),
        parent="payment_item", on="c.item_id = p.item_id",
    )
    best: dict[tuple[int, int], dict] = {}
    for link in links:
        if int(link["item_id"]) not in course_items:
            continue
        key = (int(link["item_id"]), int(link["lesson_id"]))
        if key[1] not in known:
            drop(f"{key[0]}:{key[1]}", "旧データの不整合",
                 f"講座（lesson_id={key[1]}）が移行の対象に無い（物理削除されているか、他テナントの講座）")
            continue
        alive = int(link.get("del_chk") or 0) == 0
        held = best.get(key)
        if held is None or (alive and not held["_alive"]):
            best[key] = {**link, "_alive": alive}
    return [{"item_id": k[0], "lesson_id": k[1], **v} for k, v in sorted(best.items())]


def applications(ctx: RunContext) -> list[dict]:
    """決済として移す申込（P3 / P4 で絞ったあと）。商品を `_item` に添える。

    **1回の実行の中では1度だけ読む。** 決済・明細・領収書の Step が同じものを使う。
    """
    cached = getattr(ctx, "_lw2_applications", None)
    if cached is not None:
        return cached
    source = ctx.require_source()
    catalog = items(ctx)
    item_of = {
        int(r["application_id"]): int(r["item_id"])
        for r in source.fetch_joined(
            "payment_application_item", ("application_id", "item_id"),
            parent="payment_application", on="c.application_id = p.application_id",
        )
    }
    out, skipped = [], {"free_or_ticket": 0, "no_payment_required": 0}
    for app in source.fetch_for_tenant("payment_application", APPLICATION_COLUMNS):
        if not is_migrated(app.get("payment_type"), app.get("application_result")):
            if int(app.get("payment_type") or 0) not in MONEY_TYPES:
                skipped["free_or_ticket"] += 1
            else:
                skipped["no_payment_required"] += 1
            continue
        app["_item"] = catalog.get(item_of.get(int(app["application_id"]), -1))
        out.append(app)
    if any(skipped.values()):
        ctx.logger.info(
            "決済として移さない申込: 無料・チケット払い %d 件 / 支払い不要 %d 件（暫定の規則 P3 / P4）",
            skipped["free_or_ticket"], skipped["no_payment_required"],
        )
    ctx._lw2_applications = out
    return out


def payers(ctx: RunContext) -> dict[int, int]:
    """決済として移す申込 → 払った会員（補正データを当てたあと）。

    **受講登録・コースの購入は、払った会員が権限の会員と同じ申込にだけ結ぶ**（0-2 Q8）。会員の無い申込
    （ステージングの申込 322。`user_id = 0`）は決済が会員の外部キーで落ちるので、結ぶとコースの購入まで
    連鎖して落ちる。補正データで会員を直せば結ばれる。
    """
    return {int(a["application_id"]): int(a.get("user_id") or 0) for a in applications(ctx)}


def _courses(item: dict | None) -> list[int]:
    if item is None or int(item.get("item_type") or 0) != COURSE_ITEM:
        return []
    return item["_lessons"]


# --- Step ---------------------------------------------------------------------
class PaymentsStep(Step):
    """お金が動く申込を `payments` に移す（P3〜P8）。"""

    name = "billing.payments"
    description = "お金が動く申込を決済として移す"
    source_table = "payment_application"
    target_table = "payments"
    depends_on = ("users",)

    def extract(self, ctx: RunContext) -> list[dict]:
        return applications(ctx)

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        records = []
        for app in rows:
            item = app.get("_item")
            records.append(
                Record(
                    table="payments",
                    values={
                        "id": ctx.ulid.for_row("payment_application", app["application_id"]),
                        "tenant_id": tenant_id,
                        "user_id": ctx.ulid.for_row("user", app["user_id"]),
                        "application_id": int(app["application_id"]),
                        # **税込**の請求額（クーポン適用後）
                        "amount": app.get("amount") or 0,
                        "currency": "JPY",
                        "platform_fee": 0,
                        "provider_payment_id": provider_payment_id(app["application_id"]),
                        "provider": PROVIDERS[int(app["payment_type"])],
                        "provider_transfer_id": None,
                        "type": payment_kind(item),
                        "status": STATUSES[int(app.get("application_result") or 0)],
                        "settings": _json(_payment_settings(app, item)),
                        "created_at": convert(app.get("application_date_time"), ColumnKind.TIMESTAMP),
                    },
                    natural_key=("tenant_id", "application_id"),
                    source_key=int(app["application_id"]),
                )
            )
        return records


def _payment_settings(app: dict, item: dict | None) -> dict:
    return {
        "legacy_payment_type": app.get("payment_type"),
        "legacy_application_result": app.get("application_result"),
        "paid_at": paid_at(app, item),
        "item": None if item is None else {
            "item_id": item.get("item_id"), "item_type": item.get("item_type"),
            "name": item.get("item_name"), "courses": _courses(item),
            # 種類はコースの購入にそろえたので、自動継続（継続課金）だったかをここに残す
            "auto_extension": int(item.get("is_auto_extension") or 0) == 1,
            "live_lesson_id": item.get("live_lesson_id"),
        },
        "jpayment": {
            "gid": app.get("jpayment_application_id"), "order_code": app.get("jpayment_order_code"),
            "auto_credit_id": app.get("auto_credit_id"), "auto_credit_price": app.get("auto_credit_price"),
            "status": app.get("payment_status"), "error_code": app.get("error_code"),
            "order_shop_code": app.get("order_shop_code"),
            "credit_payment_date": app.get("credit_payment_date"),
        },
        "convenience": {
            "code": app.get("convenience_code"), "payment_limit": app.get("convenience_payment_limit"),
            "paid_at": app.get("convenience_payment_date"),
        },
        "bank": {"status": app.get("bank_payment_status"), "paid_at": app.get("bank_payment_date")},
        # **解約は返金ではない。** 継続課金を止めただけで、状態（succeeded）は変えない
        "cancel": {
            "canceled": int(app.get("is_cancel") or 0) == 1, "at": app.get("cancel_date_time"),
            "by_admin": int(app.get("admin_cancel_chk") or 0) == 1,
        },
        "subscription": {
            "trial": app.get("is_use_trial"), "auto_cancel": app.get("is_auto_cancel"),
            "auto_cancel_term": app.get("auto_cancel_term"), "auto_cancel_date": app.get("auto_cancel_date"),
            "first_amount": app.get("first_amount"),
        },
        "extension": {
            "is_extension_item": app.get("is_extension_item"),
            "parent_application_id": app.get("extension_application_id") or None,
            "completed": app.get("is_complete_extension"),
        },
        # カード会社の分割。**`split_payment_number = 1` は一括**（選択欄があるだけで 1 が入る）
        "card_installments": (
            int(app["split_payment_number"])
            if int(app.get("is_use_split_payment") or 0) == 1 and int(app.get("split_payment_number") or 0) > 1
            else None
        ),
        "coupon": {
            "coupon_id": app.get("coupon_id") or None, "type": app.get("coupon_type"),
            "discount": app.get("coupon_discount"), "before": app.get("before_coupon_price"),
            "after": app.get("after_coupon_price"),
        },
        "tax": {
            "invoice_chk": app.get("invoice_chk"), "rate": app.get("tax_rate"),
            "treatment": app.get("tax_rate_treatment"),
            "excluding_tax_price": app.get("excluding_tax_price"),
            "excluding_tax_first_price": app.get("excluding_tax_first_price"),
            "excluding_tax_extension_price": app.get("excluding_tax_extension_price"),
        },
        "tickets": {
            "ticket_id": app.get("ticket_id"), "ticket_num": app.get("ticket_num"),
            "ticket_count": app.get("ticket_count"), "ticket_price": app.get("ticket_price"),
        },
        "live": {
            "reserve_id": app.get("live_lesson_reserve_id") or None,
            "date_id": app.get("live_lesson_date_id") or None,
        },
    }


class LearningPathPurchasePaymentsStep(Step):
    """コースの購入の明細（`learning_path_purchase_payments`。決済 → コース）。2026-10-22。

    講座の商品の決済はすべてコースの購入（`learning_path_purchase`）にしたので、どの商品（コース）の
    購入かをここに持つ。それまでの講座1つの商品の明細（`course_purchase_payments`）には入れない。
    """

    name = "billing.learning_path_purchase_payments"
    description = "コースの購入の明細（決済とコース）を移す"
    source_table = "payment_application"
    target_table = "learning_path_purchase_payments"
    depends_on = ("billing.payments", "content.learning_paths")

    def extract(self, ctx: RunContext) -> list[dict]:
        return [a for a in applications(ctx) if payment_kind(a.get("_item")) == "learning_path_purchase"]

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        return [
            Record(
                table="learning_path_purchase_payments",
                values={
                    "payment_id": ctx.ulid.for_row("payment_application", app["application_id"]),
                    "learning_path_id": ctx.ulid.for_row("learning_path", app["_item"]["item_id"]),
                    "created_at": convert(app.get("application_date_time"), ColumnKind.TIMESTAMP),
                },
                natural_key=("payment_id",),
                source_key=int(app["application_id"]),
            )
            for app in rows
        ]


class SubscriptionPaymentsStep(Step):
    """自動継続の商品の初回の申込（`subscription_payments`）。**継続課金の本体は作らない**（P9）。"""

    name = "billing.subscription_payments"
    description = "自動継続の商品の申込の明細を移す"
    source_table = "payment_application"
    target_table = "subscription_payments"
    depends_on = ("billing.payments",)

    def extract(self, ctx: RunContext) -> list[dict]:
        return [
            a for a in applications(ctx)
            if payment_kind(a.get("_item")) == "subscription"
        ]

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        return [
            Record(
                table="subscription_payments",
                values={
                    "payment_id": ctx.ulid.for_row("payment_application", app["application_id"]),
                    # learner_subscriptions は作らない（Stripe の必須 ID が無い）
                    "subscription_id": None,
                    "period_start": None,
                    "period_end": None,
                    "created_at": convert(app.get("application_date_time"), ColumnKind.TIMESTAMP),
                },
                natural_key=("payment_id",),
                source_key=int(app["application_id"]),
            )
            for app in rows
        ]


def build() -> list[Step]:
    """4-2 決済。"""
    return [
        PaymentsStep(),
        LearningPathPurchasePaymentsStep(), SubscriptionPaymentsStep(),
    ]
