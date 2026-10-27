"""移行対象外と決めた旧の表を、**行ごとに一覧に出す**（黙って落とさない）。

docs/db/05-support/migration-spec.md 0-9。

- 掲示板（`bbs` / `bbs_comment` / `bbs_set_*` / 掲示板のいいね）… Q10（2026-10-26 決定）
- お仕事募集（`recruit` / `recruit_user` / `line_message_recruit`）… Q11。旧の `recruit` には
  企業・雇用形態の列が無く、新の求人（`job_postings`）の形ではない
"""

from __future__ import annotations

from dataclasses import dataclass

from ...context import RunContext
from ...core.records import Record
from ..base import Step

REASON = "移行対象外"


@dataclass(frozen=True)
class Listed:
    """一覧に出す 1 表。`parent` があれば親と join してテナントで絞る。"""

    table: str
    key: tuple[str, ...]
    detail: str
    parent: str = ""
    on: str = ""
    where: str = ""


def listed_rows(ctx: RunContext, spec: Listed) -> list[dict]:
    source = ctx.require_source()
    if spec.parent:
        return source.fetch_joined(spec.table, spec.key, parent=spec.parent, on=spec.on, where=spec.where)
    return source.fetch_for_tenant(spec.table, spec.key, spec.where)


class ListOnlyStep(Step):
    """何も入れず、旧の行をすべて一覧に出す。"""

    specs: tuple[Listed, ...] = ()

    def extract(self, ctx: RunContext) -> list[dict]:
        for spec in self.specs:
            for row in listed_rows(ctx, spec):
                key = ":".join(str(row[c]) for c in spec.key)
                self.drop(spec.table, f"{spec.table}:{key}", REASON, spec.detail)
        return []

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        return []


BBS = "掲示板は移行対象外（2026-10-26 決定）"
_BBS_SETS = tuple(
    Listed(f"bbs_set_{kind}", ("bbs_id", column), BBS, parent="bbs", on="c.bbs_id = p.bbs_id")
    for kind, column in (
        ("group", "group_id"), ("attribute", "attribute_id"), ("lesson", "lesson_id"),
        ("payment_item", "item_id"), ("role", "role_id"),
    )
)


class BbsStep(ListOnlyStep):
    name = "support.bbs"
    description = "掲示板（移行対象外。一覧に出す）"
    source_table = "bbs"
    specs = (
        Listed("bbs", ("bbs_id",), BBS),
        Listed("bbs_comment", ("bbs_comment_id",), BBS, parent="bbs", on="c.bbs_id = p.bbs_id"),
        *_BBS_SETS,
        # いいね（`like.entity_type_id` 1 = 掲示板、2 = 掲示板のコメント）
        Listed("like_user", ("like_user_id",), BBS, parent="like", on="c.like_id = p.like_id",
               where="p.entity_type_id IN (1, 2)"),
    )


RECRUIT = "お仕事募集は移行対象外（企業・雇用形態の列が無く、求人の形ではない。2026-10-26 決定）"


class RecruitStep(ListOnlyStep):
    name = "support.recruit"
    description = "お仕事募集（移行対象外。一覧に出す）"
    source_table = "recruit"
    specs = (
        Listed("recruit", ("recruit_id",), RECRUIT),
        Listed("recruit_user", ("recruit_user_id",), RECRUIT, parent="recruit", on="c.recruit_id = p.recruit_id"),
        Listed("line_message_recruit", ("line_message_recruit_id",), RECRUIT, parent="recruit",
               on="c.recruit_id = p.recruit_id"),
    )
