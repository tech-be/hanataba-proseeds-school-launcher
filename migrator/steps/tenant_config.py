"""フェーズ3 — テナントの設定・定義系。

**会員より先に入れる。** 会員の属性割当やプロフィール値は、ここで作る定義を指す。
"""

from __future__ import annotations

from ..context import RunContext
from ..core.records import Record
from .base import Step

LIMIT_COLUMNS = (
    "tenant_id",
    "user_value",
    "student_value",
    "user_csv_value",
    "user_learning_lesson_value",
    "user_learning_lesson_csv_value",
)

PROFILE_ITEM_COLUMNS = (
    "tenant_id",
    "item_type",
    "item_no",
    "profile_cate_id",
    "field_name",
    "show_chk",
    "edit_chk",
    "required_chk",
    "open_chk",
    "multiple_rows_chk",
)
PROFILE_LABEL_COLUMNS = ("tenant_id", "language", "item_type", "item_no", "title", "memo", "memo_free")
#: プロフィール項目の分類（`profile_cate`）。**全テナント共通のマスタ**
PROFILE_CATE_COLUMNS = ("profile_cate_id", "profile_cate_name", "del_chk")
#: 項目の既定値（`user_item_default`）。**`item_name` は `profile_item.field_name` を指す**
ITEM_DEFAULT_COLUMNS = ("tenant_id", "item_name", "value")

#: 外部サービスの API キー（A3）。**接続情報・SNS シークレットとは扱いが違う** —
#: 旧アプリに紐づかない第三者サービスの鍵で、移しても使える
SECRET_SOURCES: tuple[tuple[str, str, str], ...] = (
    # (旧テーブル, 旧列, tenant_secret_kinds.code)
    ("site", "linkpreview_api_key", "linkpreview_api_key"),
)


class TenantLimitsStep(Step):
    """`tenant_limit_value` の上限5種を `tenant_limits` に移す。"""

    name = "config.tenant_limits"
    description = "会員数・CSV 一括登録などの上限5種を移す"
    source_table = "tenant_limit_value"
    target_table = "tenant_limits"
    depends_on = ("tenant",)

    def extract(self, ctx: RunContext) -> list[dict]:
        return ctx.require_source().fetch_for_tenant("tenant_limit_value", LIMIT_COLUMNS)

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        if not rows:
            return []
        row = rows[0]
        return [
            Record(
                table="tenant_limits",
                values={
                    "tenant_id": ctx.tenant_id.value,
                    "max_users": row.get("user_value"),
                    "max_learners": row.get("student_value"),
                    "max_user_csv_rows": row.get("user_csv_value"),
                    "max_enrollments": row.get("user_learning_lesson_value"),
                    "max_enrollment_csv_rows": row.get("user_learning_lesson_csv_value"),
                },
                natural_key=("tenant_id",),
            )
        ]


class FieldDefaultsStep(Step):
    """テナント単位の**会員列の既定値**を移す（`user_item_default` → A23）。

    **名前に反して会員データではない。** `item_name` は `profile_item` ではなく
    `user` の列名（`profile_open_chk` など）で、会員登録時の初期値として使われる。
    `tenant_profile_items.default_value`（プロフィール項目の既定値）とは別物なので、
    畳まずに別テーブルで持つ。
    """

    name = "config.field_defaults"
    description = "会員列のテナント既定値を移す"
    source_table = "user_item_default"
    target_table = "tenant_field_defaults"
    depends_on = ("tenant",)

    def extract(self, ctx: RunContext) -> list[dict]:
        return ctx.require_source().fetch_for_tenant("user_item_default", ITEM_DEFAULT_COLUMNS)

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        return [
            Record(
                table="tenant_field_defaults",
                values={
                    "id": ctx.ulid.for_row("tenant_field_default", str(row["item_name"])),
                    "tenant_id": ctx.tenant_id.value,
                    "field_code": row["item_name"],
                    "default_value": row["value"],
                },
                natural_key=("tenant_id", "field_code"),
                source_key=str(row["item_name"]),
            )
            for row in rows
        ]


class TenantSecretsStep(Step):
    """外部サービスの API キーを `tenant_secrets` に移す（A3）。

    **「移行できないもの」の平文4件とは別物。** あちらは lw2 自身の DB 接続情報と
    旧アプリに紐づく SNS シークレットで、移しても機能しない。ここで扱うのは
    第三者サービス（LinkPreview）の鍵で、**新環境でもそのまま使える**。

    値そのものはログに出さない（長さだけ記録する）。
    """

    name = "config.secrets"
    description = "外部サービスの API キーを移す"
    source_table = "site"
    target_table = "tenant_secrets"
    depends_on = ("tenant",)

    def extract(self, ctx: RunContext) -> list[dict]:
        source = ctx.require_source()
        rows: list[dict] = []
        for table, column, kind in SECRET_SOURCES:
            for row in source.fetch_global(table, ("site_id", column)):
                value = (row.get(column) or "").strip()
                if value:
                    rows.append({"kind": kind, "value": value})
                    ctx.logger.info("%s.%s を移す（%d 文字）", table, column, len(value))
        return rows

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        return [
            Record(
                table="tenant_secrets",
                values={
                    "id": ctx.ulid.for_row("tenant_secret", row["kind"]),
                    "tenant_id": ctx.tenant_id.value,
                    "kind": row["kind"],
                    "value": row["value"],
                },
                natural_key=("tenant_id", "kind"),
                source_key=row["kind"],
            )
            for row in rows
        ]


class ProfileItemCategoriesStep(Step):
    """プロフィール項目の分類（`profile_cate`）を移す。

    **項目より先に入れる。** `tenant_profile_items.category_id` の参照先になる。
    旧は全テナント共通の1枚だが、新環境はテナントごとに持つので recademy 用として作る。
    """

    name = "config.profile_item_categories"
    description = "プロフィール項目の分類を移す"
    source_table = "profile_cate"
    target_table = "tenant_profile_item_categories"
    depends_on = ("tenant",)

    def extract(self, ctx: RunContext) -> list[dict]:
        return ctx.require_source().fetch_global("profile_cate", PROFILE_CATE_COLUMNS)

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        return [
            Record(
                table="tenant_profile_item_categories",
                values={
                    "id": category_id(ctx, row["profile_cate_id"]),
                    "tenant_id": ctx.tenant_id.value,
                    "legacy_id": int(row["profile_cate_id"]),
                    "name": row.get("profile_cate_name"),
                    "sort_order": int(row["profile_cate_id"]),
                },
                natural_key=("tenant_id", "legacy_id"),
            )
            for row in rows
        ]


def category_id(ctx: RunContext, value: object) -> str | None:
    """`profile_cate_id` を新環境の ULID にする。**`0` は「分類なし」で NULL。**

    旧の `profile_cate` は 1 始まりで、`0` に当たる行は無い。
    """
    if value is None or int(value) == 0:
        return None
    return ctx.ulid.for_row("profile_cate", int(value))


class ProfileItemsStep(Step):
    """`profile_item` / `profile_item_label` を新環境の項目定義に移す。

    **`profile_item` は値ではなく「画面制御の定義」**で、`field_name` が値の在処
    （`user` の列名）を指す。値そのものは
    - `item_type=0` → `users` の対応列（フェーズ4・5で移す）
    - `item_type=1` → `user_profile_values`（フェーズ5）
    """

    name = "config.profile_items"
    description = "プロフィール項目の定義とラベルを移す"
    source_table = "profile_item"
    target_table = "tenant_profile_items"
    depends_on = ("tenant", "config.profile_item_categories")

    def extract(self, ctx: RunContext) -> list[dict]:
        source = ctx.require_source()
        items = source.fetch_for_tenant("profile_item", PROFILE_ITEM_COLUMNS)
        labels = source.fetch_for_tenant("profile_item_label", PROFILE_LABEL_COLUMNS)
        by_key: dict[tuple, list[dict]] = {}
        for label in labels:
            by_key.setdefault((label["item_type"], label["item_no"]), []).append(label)
        for item in items:
            item["_labels"] = by_key.get((item["item_type"], item["item_no"]), [])
        return items

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        records: list[Record] = []
        for row in rows:
            item_id = ctx.ulid.for_row(
                "profile_item", f"{row['item_type']}:{row['item_no']}"
            )
            records.append(
                Record(
                    table="tenant_profile_items",
                    values={
                        "id": item_id,
                        "tenant_id": ctx.tenant_id.value,
                        "item_type": row["item_type"],
                        "item_no": row["item_no"],
                        "field_code": row.get("field_name"),
                        "category_id": category_id(ctx, row.get("profile_cate_id")),
                        "show_flag": bool(row.get("show_chk")),
                        "edit_flag": bool(row.get("edit_chk")),
                        "required_flag": bool(row.get("required_chk")),
                        "open_flag": bool(row.get("open_chk")),
                        "multiline_flag": bool(row.get("multiple_rows_chk")),
                    },
                    natural_key=("tenant_id", "item_type", "item_no"),
                )
            )
        return records


class ProfileItemLabelsStep(Step):
    """言語別のラベル（`title` / `memo` / `memo_free`）を移す。"""

    name = "config.profile_item_labels"
    description = "プロフィール項目のラベルを言語別に移す"
    source_table = "profile_item_label"
    target_table = "tenant_profile_item_labels"
    depends_on = ("config.profile_items",)

    def extract(self, ctx: RunContext) -> list[dict]:
        source = ctx.require_source()
        rows = source.fetch_for_tenant("profile_item_label", PROFILE_LABEL_COLUMNS)
        # **親の無いラベルは入れられない**（`item_id` の FK 先が無い）。
        # 旧データの取り残しなので、落としたことを必ず記録に残す
        items = {
            (r["item_type"], r["item_no"])
            for r in source.fetch_for_tenant("profile_item", ("item_type", "item_no"))
        }
        kept = [r for r in rows if (r["item_type"], r["item_no"]) in items]
        orphans = [(r["item_type"], r["item_no"], r.get("title")) for r in rows if r not in kept]
        if orphans:
            ctx.logger.warning(
                "対応する profile_item が無いラベルを %d 件落とす: %s", len(orphans), orphans
            )
        return kept

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        records = []
        for row in rows:
            key = f"{row['item_type']}:{row['item_no']}"
            records.append(
                Record(
                    table="tenant_profile_item_labels",
                    values={
                        "id": ctx.ulid.for_row("profile_item_label", f"{key}:{row['language']}"),
                        "tenant_id": ctx.tenant_id.value,
                        "item_id": ctx.ulid.for_row("profile_item", key),
                        "locale": row["language"],
                        "label": row.get("title"),
                        "memo": row.get("memo"),
                        "memo_free": row.get("memo_free"),
                    },
                    natural_key=("item_id", "locale"),
                )
            )
        return records


def build() -> list[Step]:
    return [
        TenantLimitsStep(),
        FieldDefaultsStep(),
        TenantSecretsStep(),
        # 分類 → 項目 → ラベル。**FK の参照先を先に作る**
        ProfileItemCategoriesStep(),
        ProfileItemsStep(),
        ProfileItemLabelsStep(),
    ]
