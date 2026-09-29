"""グループ・属性・講師の担当範囲（A10 / A11 / A18）。

**旧側の親子関係に注意。**

- `group` の階層は **`parent_group_id` が正本**。`group_structure` は派生データなので移行しない
- `user_group` / `user_attribute` / `attribute_lesson` / `instructor_set_*` は
  **`tenant_id` を持たない**ので、親と join してテナントで絞る
"""

from __future__ import annotations

from ..context import RunContext
from ..core.datetimes import ColumnKind, convert
from ..core.records import Record
from .base import Step

GROUP_COLUMNS = (
    "group_id",
    "parent_group_id",
    "hierarchy",
    "group_name",
    "group_code",
    "memo",
    "sort_no",
    "del_chk",
    "regist_date",
    "update_date",
)
ATTRIBUTE_COLUMNS = (
    "attribute_id",
    "attribute_name",
    "attribute_memo",
    "sort_no",
    "del_chk",
    "regist_date",
    "update_date",
)

#: 講師の担当範囲。旧テーブル → scope と、親の旧テーブル名
INSTRUCTOR_SCOPES = (
    ("instructor_set_lesson", "course", "lesson_id"),
    ("instructor_set_group", "group", "group_id"),
    ("instructor_set_attribute", "attribute", "attribute_id"),
)


def _deleted_at(row: dict):
    """`del_chk=1` を日時で表す。**`active` のようなフラグと二重管理にしない。**"""
    if int(row.get("del_chk") or 0) != 1:
        return None
    return convert(row.get("update_date"), ColumnKind.DATETIME)


class GroupsStep(Step):
    name = "config.groups"
    description = "グループ定義を移す（階層は parent_id。group_structure は作らない）"
    source_table = "group"
    target_table = "tenant_groups"
    depends_on = ("tenant",)

    def extract(self, ctx: RunContext) -> list[dict]:
        return ctx.require_source().fetch_for_tenant("group", GROUP_COLUMNS)

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        known = {int(r["group_id"]) for r in rows}
        records = []
        for row in rows:
            parent = int(row.get("parent_group_id") or 0)
            if parent and parent not in known:
                # 親が抽出結果に無い（削除済みなど）。木が壊れるので根に寄せて記録を残す
                ctx.logger.warning(
                    "group_id=%s の親 %s が見つからない。parent_id を NULL にする",
                    row["group_id"],
                    parent,
                )
                parent = 0
            records.append(
                Record(
                    table="tenant_groups",
                    values={
                        "id": ctx.ulid.for_row("group", row["group_id"]),
                        "tenant_id": tenant_id,
                        "group_id": int(row["group_id"]),
                        "parent_id": ctx.ulid.for_row("group", parent) if parent else None,
                        "depth": int(row.get("hierarchy") or 0),
                        "code": row.get("group_code"),
                        "name": row.get("group_name"),
                        "memo": row.get("memo"),
                        "sort_order": int(row.get("sort_no") or 0),
                        "deleted_at": _deleted_at(row),
                        "created_at": convert(row.get("regist_date"), ColumnKind.TIMESTAMP),
                    },
                    natural_key=("tenant_id", "group_id"),
                )
            )
        # 親より先に子を入れると FK 違反になるので、深さの浅い順に並べる
        records.sort(key=lambda r: r.values["depth"])
        return records


class AttributesStep(Step):
    name = "config.attributes"
    description = "属性定義を移す"
    source_table = "attribute"
    target_table = "tenant_attributes"
    depends_on = ("tenant",)

    def extract(self, ctx: RunContext) -> list[dict]:
        return ctx.require_source().fetch_for_tenant("attribute", ATTRIBUTE_COLUMNS)

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        return [
            Record(
                table="tenant_attributes",
                values={
                    "id": ctx.ulid.for_row("attribute", row["attribute_id"]),
                    "tenant_id": tenant_id,
                    "attribute_id": int(row["attribute_id"]),
                    "code": None,
                    "name": row.get("attribute_name"),
                    "memo": row.get("attribute_memo"),
                    "sort_order": int(row.get("sort_no") or 0),
                    "deleted_at": _deleted_at(row),
                    "created_at": convert(row.get("regist_date"), ColumnKind.TIMESTAMP),
                },
                natural_key=("tenant_id", "attribute_id"),
            )
            for row in rows
        ]


class AttributeRequiredCoursesStep(Step):
    """属性による必須講座。**講座が未移行なので `course_id` は NULL で始める。**"""

    name = "config.attribute_required_courses"
    description = "属性による必須講座の指定を移す（course_id は講座移行後に埋める）"
    source_table = "attribute_lesson"
    target_table = "attribute_required_courses"
    depends_on = ("config.attributes",)

    def extract(self, ctx: RunContext) -> list[dict]:
        return ctx.require_source().fetch_joined(
            "attribute_lesson",
            ("attribute_id", "lesson_id"),
            parent="attribute",
            on="c.attribute_id = p.attribute_id",
        )

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        return [
            Record(
                table="attribute_required_courses",
                values={
                    "id": ctx.ulid.for_row(
                        "attribute_lesson", f"{row['attribute_id']}:{row['lesson_id']}"
                    ),
                    "tenant_id": tenant_id,
                    "attribute_id": ctx.ulid.for_row("attribute", row["attribute_id"]),
                    "course_id": None,  # オンデマンド移行後に legacy_lesson_id で埋める
                    "legacy_lesson_id": int(row["lesson_id"]),
                },
                natural_key=("attribute_id", "legacy_lesson_id"),
            )
            for row in rows
        ]


class GroupMembersStep(Step):
    name = "tenant_group_members"
    description = "会員のグループ割当を移す"
    source_table = "user_group"
    target_table = "tenant_group_members"
    depends_on = ("users", "config.groups")

    def extract(self, ctx: RunContext) -> list[dict]:
        return ctx.require_source().fetch_joined(
            "user_group", ("group_id", "user_id"), parent="group", on="c.group_id = p.group_id"
        )

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        return [
            Record(
                table="tenant_group_members",
                values={
                    "id": ctx.ulid.for_row("user_group", f"{row['group_id']}:{row['user_id']}"),
                    "tenant_id": tenant_id,
                    "group_id": ctx.ulid.for_row("group", row["group_id"]),
                    "user_id": ctx.ulid.for_row("user", row["user_id"]),
                },
                natural_key=("group_id", "user_id"),
                source_key=int(row["user_id"]),
            )
            for row in rows
        ]


class UserAttributeValuesStep(Step):
    name = "user_attribute_values"
    description = "会員の属性割当を移す"
    source_table = "user_attribute"
    target_table = "user_attribute_values"
    depends_on = ("users", "config.attributes")

    def extract(self, ctx: RunContext) -> list[dict]:
        return ctx.require_source().fetch_joined(
            "user_attribute",
            ("attribute_id", "user_id"),
            parent="attribute",
            on="c.attribute_id = p.attribute_id",
        )

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        return [
            Record(
                table="user_attribute_values",
                values={
                    "id": ctx.ulid.for_row(
                        "user_attribute", f"{row['attribute_id']}:{row['user_id']}"
                    ),
                    "tenant_id": tenant_id,
                    "attribute_id": ctx.ulid.for_row("attribute", row["attribute_id"]),
                    "user_id": ctx.ulid.for_row("user", row["user_id"]),
                },
                natural_key=("attribute_id", "user_id"),
                source_key=int(row["user_id"]),
            )
            for row in rows
        ]


class InstructorAssignmentsStep(Step):
    """講師の担当範囲3種を1つの表に移す。

    **`scope='course'` の `target_id` は NULL で始まる**（講座が未移行のため）。
    `legacy_target_id` を持っておき、オンデマンド移行後に埋める。
    """

    name = "instructor_assignments"
    description = "講師の担当講座・グループ・属性を移す"
    source_table = "instructor_set_lesson"
    target_table = "instructor_assignments"
    depends_on = ("users", "config.groups", "config.attributes")

    def extract(self, ctx: RunContext) -> list[dict]:
        source = ctx.require_source()
        rows: list[dict] = []
        for table, scope, key in INSTRUCTOR_SCOPES:
            for row in source.fetch_joined(
                table, ("user_id", key), parent="user", on="c.user_id = p.user_id"
            ):
                rows.append({"scope": scope, "user_id": row["user_id"], "target": row[key]})
        return rows

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        records = []
        for row in rows:
            scope = row["scope"]
            target_id = None
            if scope == "group":
                target_id = ctx.ulid.for_row("group", row["target"])
            elif scope == "attribute":
                target_id = ctx.ulid.for_row("attribute", row["target"])
            records.append(
                Record(
                    table="instructor_assignments",
                    values={
                        "id": ctx.ulid.for_row(
                            "instructor_assignment", f"{scope}:{row['user_id']}:{row['target']}"
                        ),
                        "tenant_id": tenant_id,
                        "user_id": ctx.ulid.for_row("user", row["user_id"]),
                        "scope": scope,
                        "target_id": target_id,
                        "legacy_target_id": int(row["target"]),
                    },
                    natural_key=("user_id", "scope", "legacy_target_id"),
                    source_key=int(row["user_id"]),
                )
            )
        return records


def definitions() -> list[Step]:
    """フェーズ3（定義系）。"""
    return [GroupsStep(), AttributesStep(), AttributeRequiredCoursesStep()]


def assignments() -> list[Step]:
    """フェーズ5（会員に紐づく割当）。"""
    return [GroupMembersStep(), UserAttributeValuesStep(), InstructorAssignmentsStep()]
