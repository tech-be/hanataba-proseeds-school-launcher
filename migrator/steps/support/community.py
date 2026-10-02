"""support.7 — コミュニティの分類（旧 `community_cate`）。

2026-09-30 に「その他」から 05 へ仕分けたもの。受け皿 `community_categories` を新設した。
掲示板・SNS 共有・足あとの本体は未実装。
"""

from __future__ import annotations

from ...context import RunContext
from ...core.datetimes import ColumnKind, convert
from ...core.records import Record
from ..base import Step

COMMUNITY_CATE_COLUMNS = (
    "community_cate_id", "community_cate_name", "group_id", "sort_no", "del_chk",
    "regist_date", "update_date",
)


class CommunityCategoriesStep(Step):
    name = "support.community_categories"
    description = "コミュニティの分類を移す"
    source_table = "community_cate"
    target_table = "community_categories"
    depends_on = ("config.groups",)

    def extract(self, ctx: RunContext) -> list[dict]:
        return ctx.require_source().fetch_for_tenant("community_cate", COMMUNITY_CATE_COLUMNS)

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        return [
            Record(
                table="community_categories",
                values={
                    "id": ctx.ulid.for_row("community_cate", int(row["community_cate_id"])),
                    "tenant_id": tenant_id,
                    "community_cate_id": int(row["community_cate_id"]),
                    "name": row.get("community_cate_name") or "",
                    # 旧は 0 =「グループ指定なし」
                    "group_id": (
                        ctx.ulid.for_row("group", int(row["group_id"]))
                        if int(row.get("group_id") or 0) else None
                    ),
                    "sort_order": int(row.get("sort_no") or 0),
                    "deleted_at": (
                        convert(row.get("update_date"), ColumnKind.DATETIME)
                        if int(row.get("del_chk") or 0) == 1 else None
                    ),
                    "created_at": convert(row.get("regist_date"), ColumnKind.TIMESTAMP),
                    "updated_at": convert(row.get("update_date"), ColumnKind.TIMESTAMP),
                },
                natural_key=("tenant_id", "community_cate_id"),
                source_key=int(row["community_cate_id"]),
            )
            for row in rows
        ]


def build() -> list[Step]:
    return [CommunityCategoriesStep()]
