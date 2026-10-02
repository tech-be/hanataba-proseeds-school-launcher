"""live.4 — ライブの分類・公開範囲・連日設定。

**どれも `lessons`(type=live) が入ったあと。** カテゴリだけはライブより先でも入るが、
割当（`live_lesson_category_links`）がレッスンを参照するので、この段にまとめる。

**削除済みも移す（2026-10-01 の方針）。** 旧は保存のたびに旧行を `del_chk = 1` にして
積む作りで、除外日は 128行のうち110行が削除済み（生きているのは18行）。新の表は
(ライブ, 日付) で一意なので、**組ごとに1行**（生きている行があれば生きた行、全部削除済みなら
`deleted_at` 付き）にし、**積まれた行は旧の形のままの表（`live_lesson_exclusion_date_history`）に全行**入れる。
"""

from __future__ import annotations

from ...context import RunContext
from ...core.datetimes import ColumnKind, convert
from ...core.records import Record
from ..base import Step

CATEGORY_COLUMNS = (
    "live_lesson_cate_id",
    "live_lesson_cate_name",
    "sort_no",
    "del_chk",
    "regist_user_id",
    "regist_date",
)
LINK_COLUMNS = ("live_lesson_id", "live_lesson_cate_id", "regist_date")
GROUP_COLUMNS = ("live_lesson_id", "group_id", "del_chk", "regist_date", "update_date")
RULE_COLUMNS = (
    "live_lesson_date_setting_id",
    "live_lesson_id",
    "date_setting_type",
    "seq_no",
    "starting_date",
    "del_chk",
    "regist_date",
)
DETAIL_COLUMNS = (
    "live_lesson_date_setting_id",
    "date_setting_type",
    "sort_no",
    "target_youbi",
    "timing_month",
    "timing_day",
    "target_time_from",
    "target_time_to",
    "del_chk",
    "regist_date",
)
EXCLUSION_COLUMNS = ("live_lesson_id", "exclusion_date", "del_chk", "regist_date", "update_date")


def _live_ulid(ctx: RunContext, live_lesson_id: object) -> str:
    return ctx.ulid.for_row("live_lesson", int(live_lesson_id))


class CategoriesStep(Step):
    """`live_lesson_cate` を `live_lesson_categories` に移す。"""

    name = "content.live_categories"
    description = "ライブのカテゴリを移す"
    source_table = "live_lesson_cate"
    target_table = "live_lesson_categories"
    depends_on = ("content.live_lessons",)

    def extract(self, ctx: RunContext) -> list[dict]:
        return ctx.require_source().fetch_for_tenant("live_lesson_cate", CATEGORY_COLUMNS)

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        return [
            Record(
                table="live_lesson_categories",
                values={
                    "id": ctx.ulid.for_row("live_lesson_cate", row["live_lesson_cate_id"]),
                    "tenant_id": tenant_id,
                    "live_lesson_cate_id": int(row["live_lesson_cate_id"]),
                    "name": row.get("live_lesson_cate_name") or "",
                    "sort_order": int(row.get("sort_no") or 0),
                    "created_by": _user(ctx, row.get("regist_user_id")),
                    "deprecated_at": (
                        convert(row.get("regist_date"), ColumnKind.DATETIME)
                        if int(row.get("del_chk") or 0) == 1
                        else None
                    ),
                    "created_at": convert(row.get("regist_date"), ColumnKind.DATETIME),
                },
                natural_key=("tenant_id", "live_lesson_cate_id"),
                source_key=int(row["live_lesson_cate_id"]),
            )
            for row in rows
        ]


class CategoryLinksStep(Step):
    """`live_lesson_lesson_cate` を移す。**ライブとカテゴリは多対多。**

    `live_lesson.live_lesson_cate_id` ではなくこちらが正（前者は使われていない）。
    """

    name = "content.live_category_links"
    description = "ライブとカテゴリの割当を移す"
    source_table = "live_lesson_lesson_cate"
    target_table = "live_lesson_category_links"
    depends_on = ("content.live_categories",)

    def extract(self, ctx: RunContext) -> list[dict]:
        return ctx.require_source().fetch_joined(
            "live_lesson_lesson_cate",
            LINK_COLUMNS,
            parent="live_lesson",
            on="c.live_lesson_id = p.live_lesson_id",
        )

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        return [
            Record(
                table="live_lesson_category_links",
                values={
                    "lesson_id": _live_ulid(ctx, row["live_lesson_id"]),
                    "category_id": ctx.ulid.for_row(
                        "live_lesson_cate", row["live_lesson_cate_id"]
                    ),
                    "tenant_id": tenant_id,
                    "created_at": convert(row.get("regist_date"), ColumnKind.DATETIME),
                },
                natural_key=("lesson_id", "category_id"),
                source_key=int(row["live_lesson_id"]),
            )
            for row in rows
        ]


class GroupTargetsStep(Step):
    """`live_lesson_group` を移す。**ステージング実測0件**なので本番で効く。

    **削除済みも移す**（`deleted_at`。新のアプリはまだ読まない）。主キーが (ライブ, グループ) なので、
    同じ組が積まれていれば `_collapse` で1行にする。
    """

    name = "content.live_group_targets"
    description = "ライブの公開グループを移す"
    source_table = "live_lesson_group"
    target_table = "live_lesson_group_targets"
    depends_on = ("content.live_lessons",)

    def extract(self, ctx: RunContext) -> list[dict]:
        rows = ctx.require_source().fetch_joined(
            "live_lesson_group",
            GROUP_COLUMNS,
            parent="live_lesson",
            on="c.live_lesson_id = p.live_lesson_id",
        )
        if not rows:
            ctx.logger.info("ライブの公開グループは0件（ステージングと同じ）")
        return _collapse(rows, ("live_lesson_id", "group_id"))

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        return [
            Record(
                table="live_lesson_group_targets",
                values={
                    "lesson_id": _live_ulid(ctx, row["live_lesson_id"]),
                    # 基盤（A10）で移したグループ
                    "group_id": ctx.ulid.for_row("group", row["group_id"]),
                    "tenant_id": tenant_id,
                    "deleted_at": row["_deleted_at"],
                    "created_at": convert(row.get("regist_date"), ColumnKind.DATETIME),
                },
                natural_key=("lesson_id", "group_id"),
                source_key=int(row["live_lesson_id"]),
            )
            for row in rows
        ]


class RecurrenceRulesStep(Step):
    """`live_lesson_date_setting` を移す（開催回の生成ルール）。

    **生成された開催回は実体化済み**なので過去の予約には影響しないが、
    これが無いと cutover 後に開催回を増やせない。
    """

    name = "content.live_recurrence_rules"
    description = "連日設定（開催回の生成ルール）を移す"
    source_table = "live_lesson_date_setting"
    target_table = "live_lesson_recurrence_rules"
    depends_on = ("content.live_lessons",)

    def extract(self, ctx: RunContext) -> list[dict]:
        return ctx.require_source().fetch_joined(
            "live_lesson_date_setting",
            RULE_COLUMNS,
            parent="live_lesson",
            on="c.live_lesson_id = p.live_lesson_id",
        )

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        return [
            Record(
                table="live_lesson_recurrence_rules",
                values={
                    "id": ctx.ulid.for_row(
                        "live_lesson_date_setting", row["live_lesson_date_setting_id"]
                    ),
                    "tenant_id": tenant_id,
                    "lesson_id": _live_ulid(ctx, row["live_lesson_id"]),
                    "live_lesson_date_setting_id": int(row["live_lesson_date_setting_id"]),
                    # 0=設定しない 1=毎日 2=毎週 3=毎月 4=毎年
                    "rule_type": int(row.get("date_setting_type") or 0),
                    "seq_no": int(row.get("seq_no") or 0),
                    "starting_on": row.get("starting_date"),
                    "deleted_at": _deleted(row),
                    "created_at": convert(row.get("regist_date"), ColumnKind.DATETIME),
                },
                natural_key=("tenant_id", "live_lesson_date_setting_id"),
                source_key=int(row["live_lesson_date_setting_id"]),
            )
            for row in rows
        ]


class RecurrenceDetailsStep(Step):
    """`live_lesson_date_setting_detail` を移す（曜日・時間帯）。"""

    name = "content.live_recurrence_details"
    description = "連日設定の明細を移す"
    source_table = "live_lesson_date_setting_detail"
    target_table = "live_lesson_recurrence_details"
    depends_on = ("content.live_recurrence_rules",)

    def extract(self, ctx: RunContext) -> list[dict]:
        return ctx.require_source().fetch_joined(
            "live_lesson_date_setting_detail",
            DETAIL_COLUMNS,
            parent="live_lesson",
            on="s.live_lesson_id = p.live_lesson_id",
            via=[
                (
                    "live_lesson_date_setting",
                    "s",
                    "c.live_lesson_date_setting_id = s.live_lesson_date_setting_id",
                )
            ],
        )

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        return [
            Record(
                table="live_lesson_recurrence_details",
                values={
                    "rule_id": ctx.ulid.for_row(
                        "live_lesson_date_setting", row["live_lesson_date_setting_id"]
                    ),
                    "sort_order": int(row.get("sort_no") or 0),
                    "rule_type": int(row.get("date_setting_type") or 0),
                    # 対象曜日。旧はカンマ区切りの text。**解釈せずそのまま残す**
                    "target_days": row.get("target_youbi"),
                    "timing_month": row.get("timing_month"),
                    "timing_day": row.get("timing_day"),
                    # 'HH:MM' の文字列のまま（旧が varchar(10)）
                    "time_from": row.get("target_time_from"),
                    "time_to": row.get("target_time_to"),
                    "deleted_at": _deleted(row),
                    "created_at": convert(row.get("regist_date"), ColumnKind.DATETIME),
                },
                natural_key=("rule_id", "sort_order"),
                source_key=int(row["live_lesson_date_setting_id"]),
            )
            for row in rows
        ]


class RecurrenceExclusionsStep(Step):
    """`live_lesson_exclusion_date` を移す（開催しない日）。

    **(ライブ, 日付) ごとに1行。** 旧は同じ組が何行も積まれていて（ステージング実測 128行 / 22組、
    最多8行）、新の `uk_llre_lesson_date` に全行は入らない。生きている行があれば生きた行、
    全部削除済みなら `deleted_at` 付きで入れる。**全行は `ExclusionHistoryStep` が旧の形のまま入れる。**
    """

    name = "content.live_recurrence_exclusions"
    description = "開催しない日を移す（組ごとに1行）"
    source_table = "live_lesson_exclusion_date"
    target_table = "live_lesson_recurrence_exclusions"
    depends_on = ("content.live_recurrence_rules",)

    def extract(self, ctx: RunContext) -> list[dict]:
        rows = ctx.require_source().fetch_for_tenant("live_lesson_exclusion_date", EXCLUSION_COLUMNS)
        # 日付の無い行は新の表に入らない（excluded_on は NOT NULL）。旧の形の表には入る
        return _collapse([r for r in rows if r.get("exclusion_date") is not None],
                         ("live_lesson_id", "exclusion_date"))

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        return [
            Record(
                table="live_lesson_recurrence_exclusions",
                values={
                    # **旧に主キーが無い。** (ライブ, 日付) の組から採番する
                    "id": ctx.ulid.for_row(
                        "live_lesson_exclusion_date",
                        f"{int(row['live_lesson_id'])}:{row['exclusion_date']}",
                    ),
                    "tenant_id": tenant_id,
                    "lesson_id": _live_ulid(ctx, row["live_lesson_id"]),
                    "excluded_on": row["exclusion_date"],
                    "deleted_at": row["_deleted_at"],
                    "created_at": convert(row.get("regist_date"), ColumnKind.DATETIME),
                },
                natural_key=("lesson_id", "excluded_on"),
                source_key=f"{int(row['live_lesson_id'])}:{row['exclusion_date']}",
            )
            for row in rows
        ]


class ExclusionHistoryStep(Step):
    """`live_lesson_exclusion_date` の**全行**を旧の形のまま移す（削除済み・積まれた行を含む）。"""

    name = "content.live_exclusion_history"
    description = "開催しない日の全行を旧の形のまま移す"
    source_table = "live_lesson_exclusion_date"
    target_table = "live_lesson_exclusion_date_history"
    depends_on = ("content.live_lessons",)

    def extract(self, ctx: RunContext) -> list[dict]:
        rows = ctx.require_source().fetch_for_tenant("live_lesson_exclusion_date", EXCLUSION_COLUMNS)
        # **旧に主キーが無い。** 同じ内容の行があり得るので、読んだ順の通し番号で区別する
        rows.sort(key=lambda r: (int(r["live_lesson_id"]), str(r.get("exclusion_date")),
                                 str(r.get("regist_date")), str(r.get("update_date")), int(r.get("del_chk") or 0)))
        seen: dict[tuple, int] = {}
        for row in rows:
            base = (int(row["live_lesson_id"]), str(row.get("exclusion_date")), str(row.get("regist_date")))
            seen[base] = seen.get(base, 0) + 1
            row["_key"] = f"{base[0]}:{base[1]}:{base[2]}:{seen[base]}"
        return rows

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        return [
            Record(
                table="live_lesson_exclusion_date_history",
                values={
                    "id": ctx.ulid.for_row("live_lesson_exclusion_date_history", row["_key"]),
                    "tenant_id": tenant_id,
                    "lesson_id": _live_ulid(ctx, row["live_lesson_id"]),
                    "live_lesson_id": int(row["live_lesson_id"]),
                    "exclusion_date": row.get("exclusion_date"),
                    "del_chk": int(row.get("del_chk") or 0) == 1,
                    "regist_date": convert(row.get("regist_date"), ColumnKind.DATETIME),
                    "update_date": convert(row.get("update_date"), ColumnKind.DATETIME),
                },
                natural_key=("id",),
                source_key=row["_key"],
            )
            for row in rows
        ]


def _collapse(rows: list[dict], key: tuple[str, ...]) -> list[dict]:
    """同じ組の行を1行にまとめ、`_deleted_at` を付ける。

    **生きている行が1つでもあれば生きた行**（最も新しい生きた行）。全部削除済みなら
    最も新しい行を、その `update_date` を削除日時として返す。
    """
    groups: dict[tuple, list[dict]] = {}
    for row in rows:
        groups.setdefault(tuple(str(row.get(k)) for k in key), []).append(row)
    out = []
    for members in groups.values():
        members.sort(key=lambda r: str(r.get("update_date") or r.get("regist_date")))
        alive = [r for r in members if int(r.get("del_chk") or 0) == 0]
        if alive:
            out.append({**alive[-1], "_deleted_at": None})
        else:
            last = members[-1]
            out.append({**last, "_deleted_at": convert(last.get("update_date"), ColumnKind.DATETIME)})
    return out


def _deleted(row: dict):
    return (
        convert(row.get("regist_date"), ColumnKind.DATETIME)
        if int(row.get("del_chk") or 0) == 1
        else None
    )


def _user(ctx: RunContext, value: object) -> str | None:
    if value is None or int(value) == 0:
        return None
    return ctx.ulid.for_row("user", int(value))


def build() -> list[Step]:
    return [
        CategoriesStep(),
        CategoryLinksStep(),
        GroupTargetsStep(),
        RecurrenceRulesStep(),
        RecurrenceDetailsStep(),
        RecurrenceExclusionsStep(),
        ExclusionHistoryStep(),
    ]
