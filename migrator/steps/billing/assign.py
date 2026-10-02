"""billing.4 — 自動割当（旧 `assign`）を、タグの自動付与ルール（`tag_auto_assign_*`）に移す。

**受講（J04）のデータだが、課金の最後に置く。** きっかけの商品（`tenant_plans`）が
課金の2で入るため。条件のタグ（旧の属性）は基盤、付与する講座はコンテンツで入る。

| 旧 | 新 |
|---|---|
| `assign` | `tag_auto_assign_rules` |
| `assign_payment_item` | `tag_auto_assign_rule_triggers`（講座の商品 → `plan_id`、レッスン → `course_id`、それ以外の商品は旧 ID だけ） |
| `assign_attribute` | `tag_auto_assign_rule_conditions`（属性 → タグ） |
| `assign_group` | `tag_auto_assign_rule_group_conditions`（2026-10-01 新設。新のアプリはまだ読まない） |
| `assign_item` | `tag_auto_assign_rule_grants`（削除済み・無効も `deleted_at` / `valid` で移す） |
| `assign_log` | `tag_auto_assign_logs` |

**暫定の規則（04 migration-spec P15）。** 旧のルールは会員登録・購入・会員の編集のたびに動いた。
新は「購入」か「会員登録」のどちらかで発動する。商品のきっかけがあるルールは `purchase`、
無いルールは `registration` にする。

**付与するもののうち、お知らせ・クーポンは 05 で移す。** `target_id` に FK は無いので、
05 で移すときと同じ決定論 ULID（`news` / `coupon` の名前空間）を先に入れておく。

**旧のデータはすべて移す（2026-10-01 の方針）。** ルールは旧の状態のまま有効にする。新のアプリは
グループの条件・旧 ID だけのきっかけ・付与の `valid` / `deleted_at` をまだ読まないので、
**旧より広く効くルールがあり得る**（グループで絞っていたルールが全員に効く、など）。
"""

from __future__ import annotations

from ...context import RunContext
from ...core.datetimes import ColumnKind, convert, convert_date
from ...core.records import Record
from ..base import Step
from .payments import COURSE_ITEM, items

ASSIGN_COLUMNS = ("assign_id", "login_chk", "del_chk", "regist_date")
ASSIGN_ITEM_COLUMNS = (
    "item_id", "assign_id", "item_type", "entity_id", "lesson_start_date", "lesson_end_date",
    "require_chk", "valid_chk", "del_chk", "regist_date", "update_date",
)
ASSIGN_LOG_COLUMNS = ("assign_log_id", "user_id", "assign_id", "item_id", "regist_date")
#: 旧 `assign_payment_item.item_type`
TRIGGER_PRODUCT = 0
TRIGGER_LESSON = 1

#: 旧 `assign_item.item_type` → (新 `tag_auto_assign_grant_kinds.code`, 決定論 ULID の名前空間)
GRANT_KINDS: dict[str, tuple[str, str]] = {
    "lesson": ("course", "lesson"),
    "news": ("announcement", "news"),
    "announce": ("announcement", "announce"),
    "coupon": ("coupon", "coupon"),
    "recruit": ("recruit", "recruit"),
}


def rule_name(assign_id: object) -> str:
    """旧のルールに名前が無いので、旧 ID から作る。**ルールと記録で同じ名前にする。**"""
    return f"旧 自動割当 #{int(assign_id)}"


def _rule_id(ctx: RunContext, assign_id: object) -> str:
    return ctx.ulid.for_row("assign", int(assign_id))


def _payment_triggers(ctx: RunContext) -> list[dict]:
    return ctx.require_source().fetch_joined(
        "assign_payment_item", ("assign_id", "item_id", "item_type", "regist_date"),
        parent="assign", on="c.assign_id = p.assign_id",
    )


def grant_of(ctx: RunContext, row: dict) -> tuple[str, str] | None:
    """`assign_item` → (付与の種別, 対象の ULID)。対応の無い種別は None。"""
    kind = GRANT_KINDS.get(str(row.get("item_type") or ""))
    if kind is None:
        return None
    code, ns = kind
    return code, ctx.ulid.for_row(ns, int(row["entity_id"]))


class RulesStep(Step):
    name = "billing.assign_rules"
    description = "自動割当のルールを移す"
    source_table = "assign"
    target_table = "tag_auto_assign_rules"
    depends_on = ("tenant",)

    def extract(self, ctx: RunContext) -> list[dict]:
        rows = ctx.require_source().fetch_for_tenant("assign", ASSIGN_COLUMNS)
        with_trigger = {int(r["assign_id"]) for r in _payment_triggers(ctx)}
        for row in rows:
            row["_has_trigger"] = int(row["assign_id"]) in with_trigger
        return rows

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        return [
            Record(
                table="tag_auto_assign_rules",
                values={
                    "id": _rule_id(ctx, row["assign_id"]),
                    "tenant_id": tenant_id,
                    "name": rule_name(row["assign_id"]),
                    # 暫定の規則（P15）。旧は登録・購入・会員の編集のたびに動いた
                    "trigger_kind": "purchase" if row["_has_trigger"] else "registration",
                    "login_only": bool(int(row.get("login_chk") or 0)),
                    # 削除の列が無いので、削除済みのルールは止めた状態で残す
                    "active": int(row.get("del_chk") or 0) != 1,
                    "assign_id": int(row["assign_id"]),
                    "created_at": convert(row.get("regist_date"), ColumnKind.TIMESTAMP),
                },
                natural_key=("tenant_id", "assign_id"),
                source_key=int(row["assign_id"]),
            )
            for row in rows
        ]


class TriggersStep(Step):
    """きっかけ。**旧の行はすべて移す。**

    - 商品（`item_type = 0`）で講座の商品 → `plan_id`（`tenant_plans`。P2）
    - 商品で講座以外（チケット・ライブ）→ `tenant_plans` に移していないので、旧の商品 ID（`item_id`）だけを持つ行
    - レッスン（`item_type = 1`）→ `course_id`（`item_id` は講座の旧 ID）
    """

    name = "billing.assign_triggers"
    description = "自動割当のきっかけ（商品・レッスン）を移す"
    source_table = "assign_payment_item"
    target_table = "tag_auto_assign_rule_triggers"
    depends_on = ("billing.assign_rules", "billing.plans", "content.courses")

    def extract(self, ctx: RunContext) -> list[dict]:
        catalog = items(ctx)
        rows = _payment_triggers(ctx)
        for row in rows:
            kind = int(row.get("item_type") or 0)
            item = catalog.get(int(row["item_id"])) if kind == TRIGGER_PRODUCT else None
            row["_course_plan"] = item is not None and int(item.get("item_type") or 0) == COURSE_ITEM
        return rows

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        records = []
        for row in rows:
            kind = int(row.get("item_type") or 0)
            key = f"{row['assign_id']}:{kind}:{row['item_id']}"
            records.append(
                Record(
                    table="tag_auto_assign_rule_triggers",
                    values={
                        "id": ctx.ulid.for_row("assign_payment_item", key),
                        "rule_id": _rule_id(ctx, row["assign_id"]),
                        "course_id": (
                            ctx.ulid.for_row("lesson", int(row["item_id"])) if kind == TRIGGER_LESSON else None
                        ),
                        "plan_id": (
                            ctx.ulid.for_row("payment_item", int(row["item_id"])) if row["_course_plan"] else None
                        ),
                        "item_id": int(row["item_id"]),
                        "item_type": kind,
                    },
                    natural_key=("id",),
                    source_key=key,
                )
            )
        return records


class ConditionsStep(Step):
    """発動の条件のうち属性 → タグ。削除済みの属性もタグとして移っている。"""

    name = "billing.assign_conditions"
    description = "自動割当の条件（属性）を移す"
    source_table = "assign_attribute"
    target_table = "tag_auto_assign_rule_conditions"
    depends_on = ("billing.assign_rules", "config.attributes")

    def extract(self, ctx: RunContext) -> list[dict]:
        return ctx.require_source().fetch_joined(
            "assign_attribute", ("assign_id", "attribute_id"), parent="assign",
            on="c.assign_id = p.assign_id",
        )

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        return [
            Record(
                table="tag_auto_assign_rule_conditions",
                values={
                    "rule_id": _rule_id(ctx, row["assign_id"]),
                    "tag_id": ctx.ulid.for_row("attribute", int(row["attribute_id"])),
                },
                natural_key=("rule_id", "tag_id"),
                source_key=f"{row['assign_id']}:{row['attribute_id']}",
            )
            for row in rows
        ]


class GroupConditionsStep(Step):
    """発動の条件のうちグループ（2026-10-01 新設の受け皿）。**新のアプリはまだ読まない。**"""

    name = "billing.assign_group_conditions"
    description = "自動割当の条件（グループ）を移す"
    source_table = "assign_group"
    target_table = "tag_auto_assign_rule_group_conditions"
    depends_on = ("billing.assign_rules", "config.groups")

    def extract(self, ctx: RunContext) -> list[dict]:
        return ctx.require_source().fetch_joined(
            "assign_group", ("assign_id", "group_id", "regist_date"), parent="assign",
            on="c.assign_id = p.assign_id",
        )

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        return [
            Record(
                table="tag_auto_assign_rule_group_conditions",
                values={
                    "rule_id": _rule_id(ctx, row["assign_id"]),
                    "group_id": ctx.ulid.for_row("group", int(row["group_id"])),
                    "created_at": convert(row.get("regist_date"), ColumnKind.TIMESTAMP),
                },
                natural_key=("rule_id", "group_id"),
                source_key=f"{row['assign_id']}:{row['group_id']}",
            )
            for row in rows
        ]


class GrantsStep(Step):
    """付与するもの。**削除済み・無効も移す**（`deleted_at` / `valid`。新のアプリはまだ読まない）。"""

    name = "billing.assign_grants"
    description = "自動割当で付与するものを移す"
    source_table = "assign_item"
    target_table = "tag_auto_assign_rule_grants"
    depends_on = ("billing.assign_rules", "content.courses")

    def extract(self, ctx: RunContext) -> list[dict]:
        rows = []
        for row in ctx.require_source().fetch_for_tenant("assign_item", ASSIGN_ITEM_COLUMNS):
            if grant_of(ctx, row) is None:
                self.drop("tag_auto_assign_rule_grants", row["item_id"], "受け皿なし",
                          f"付与の種別 {row.get('item_type')!r} に対応が無い")
                continue
            rows.append(row)
        return rows

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        records = []
        for row in rows:
            kind, target = grant_of(ctx, row)
            records.append(
                Record(
                    table="tag_auto_assign_rule_grants",
                    values={
                        "id": ctx.ulid.for_row("assign_item", int(row["item_id"])),
                        "rule_id": _rule_id(ctx, row["assign_id"]),
                        "grant_kind": kind,
                        "target_id": target,
                        "starts_on": convert_date(row.get("lesson_start_date"), ColumnKind.DATE),
                        "ends_on": convert_date(row.get("lesson_end_date"), ColumnKind.DATE),
                        "required": bool(int(row.get("require_chk") or 0)),
                        "sort_order": 0,
                        "item_id": int(row["item_id"]),
                        # 旧の valid_chk は NULL を「有効」と読む
                        "valid": int(row["valid_chk"]) != 0 if row.get("valid_chk") is not None else True,
                        "deleted_at": (
                            convert(row.get("update_date"), ColumnKind.DATETIME)
                            if int(row.get("del_chk") or 0) == 1 else None
                        ),
                    },
                    natural_key=("rule_id", "grant_kind", "target_id"),
                    source_key=int(row["item_id"]),
                )
            )
        return records


class LogsStep(Step):
    """付与の記録。何を付けたかは `assign_item` から引く（旧の記録は item_id しか持たない）。"""

    name = "billing.assign_logs"
    description = "自動割当の記録を移す"
    source_table = "assign_log"
    target_table = "tag_auto_assign_logs"
    depends_on = ("billing.assign_rules", "users")

    def extract(self, ctx: RunContext) -> list[dict]:
        source = ctx.require_source()
        by_item = {int(r["item_id"]): r for r in source.fetch_for_tenant("assign_item", ASSIGN_ITEM_COLUMNS)}
        rows = []
        for row in source.fetch_for_tenant("assign_log", ASSIGN_LOG_COLUMNS):
            item = by_item.get(int(row.get("item_id") or 0))
            if item is None or grant_of(ctx, item) is None:
                # 旧はルールを編集するたびに assign_item を消して作り直す。記録は古い item_id を
                # 指したまま残るので、何を付与したかが旧にも残っていない（ステージングで 4,908件中 3,907件）
                self.drop("tag_auto_assign_logs", row["assign_log_id"], "旧データの不整合",
                          f"付与したもの（assign_item.item_id={row.get('item_id')}）が物理削除されている"
                          "（旧はルールの編集で付与の行を作り直す）")
                continue
            row["_item"] = item
            rows.append(row)
        return rows

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        records = []
        for row in rows:
            kind, target = grant_of(ctx, row["_item"])
            records.append(
                Record(
                    table="tag_auto_assign_logs",
                    values={
                        "id": ctx.ulid.for_row("assign_log", int(row["assign_log_id"])),
                        "tenant_id": tenant_id,
                        "user_id": ctx.ulid.for_row("user", int(row["user_id"])),
                        "rule_id": _rule_id(ctx, row["assign_id"]),
                        "rule_name": rule_name(row["assign_id"]),
                        "grant_kind": kind,
                        "target_id": target,
                        "granted_at": convert(row.get("regist_date"), ColumnKind.TIMESTAMP),
                    },
                    natural_key=("id",),
                    source_key=int(row["assign_log_id"]),
                )
            )
        return records


def build() -> list[Step]:
    return [RulesStep(), TriggersStep(), ConditionsStep(), GroupConditionsStep(), GrantsStep(), LogsStep()]
