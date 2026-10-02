"""グループ・属性（タグ）・講師の担当範囲（A10 / A11 / A18）。

**旧側の親子関係に注意。**

- `group` の階層は **`parent_group_id` が正本**。`group_structure` は派生データなので移行しない
- `user_group` / `user_attribute` / `attribute_lesson` / `instructor_set_*` は
  **`tenant_id` を持たない**ので、親と join してテナントで絞る
"""

from __future__ import annotations

import unicodedata

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


def tag_name_key(name: str) -> str:
    """タグ名を、DB の照合順序（`utf8mb4_unicode_ci`）で同じとみなされる形にそろえる。

    大文字・小文字に加えて、**全角・半角**（NFKC）と前後の空白も同じとみなす。
    `casefold()` だけだと、照合順序では重なる名前がすり抜けて投入で落ちる。
    """
    return unicodedata.normalize("NFKC", name).strip().casefold()


def _distinct_tag_names(rows: list[dict], taken: set[str] | None = None) -> dict[int, str]:
    """属性の名前を、タグの一意制約（`uk_user_tags_name`）に通る形にする。

    **重なった名前は旧 ID を付けて区別する**（`quizzes._distinct_names` と同じ手筋）。
    元の名前のまま残すのは、旧 ID の小さい方。`taken` は移行先に既にあるタグ名
    （新システムで作ったもの。`tag_name_key` でそろえた形）。
    """
    out: dict[int, str] = {}
    seen: set[str] = set(taken or ())
    for row in sorted(rows, key=lambda r: int(r["attribute_id"])):
        name = (row.get("attribute_name") or "").strip() or f"属性 {row['attribute_id']}"
        if tag_name_key(name) in seen:
            name = f"{name}（旧ID {row['attribute_id']}）"
        seen.add(tag_name_key(name))
        out[int(row["attribute_id"])] = name
    return out


class AttributesStep(Step):
    """属性を `user_tags`（タグ）に移す。**旧システムの「属性」が新システムの「タグ」。**

    新の自動付与ルール・会員の絞り込みはタグを使うので、属性はタグに一本化する
    （`tenant_attributes` には書かない）。**削除済みの属性も移す**（`deleted_at`。2026-10-01 の方針。
    新のアプリはまだ `deleted_at` を読まないので、削除済みのタグも一覧に出る）。
    `kiracari_user_chk` はタグに受け皿が無い（docs/db/01-foundation/review.md）。
    """

    name = "config.attributes"
    description = "属性をタグとして移す"
    source_table = "attribute"
    target_table = "user_tags"
    depends_on = ("tenant",)

    def extract(self, ctx: RunContext) -> list[dict]:
        # 新システムで作ったタグ（旧 ID を持たない）の名前とも重ならないようにする
        self._taken = {
            tag_name_key(r["name"])
            for r in ctx.target.query(
                "SELECT name FROM user_tags WHERE tenant_id = %s AND attribute_id IS NULL",
                (ctx.tenant_id.value,),
            )
        }
        return ctx.require_source().fetch_for_tenant("attribute", ATTRIBUTE_COLUMNS)

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        names = _distinct_tag_names(rows, getattr(self, "_taken", set()))
        return [
            Record(
                table="user_tags",
                values={
                    # 講師の担当範囲（scope=attribute）も同じ名前空間で指すので揃える
                    "id": ctx.ulid.for_row("attribute", row["attribute_id"]),
                    "tenant_id": tenant_id,
                    "attribute_id": int(row["attribute_id"]),
                    "name": names[int(row["attribute_id"])],
                    "memo": row.get("attribute_memo"),
                    "sort_order": int(row.get("sort_no") or 0),
                    "deleted_at": _deleted_at(row),
                    "created_at": convert(row.get("regist_date"), ColumnKind.TIMESTAMP),
                },
                natural_key=("tenant_id", "attribute_id"),
                source_key=int(row["attribute_id"]),
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
    """会員の属性を `user_tag_assignments`（会員に付いたタグ）に移す。

    手動・自動の区別は旧に無いので `assigned_by` / `rule_id` は NULL。
    **削除済みの属性への割当も移す**（タグを削除済みとして移すので付けられる）。
    """

    name = "user_attribute_values"
    description = "会員の属性をタグの割当として移す"
    source_table = "user_attribute"
    target_table = "user_tag_assignments"
    depends_on = ("users", "config.attributes")

    def extract(self, ctx: RunContext) -> list[dict]:
        return ctx.require_source().fetch_joined(
            "user_attribute",
            ("attribute_id", "user_id", "regist_date"),
            parent="attribute",
            on="c.attribute_id = p.attribute_id",
        )

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        return [
            Record(
                table="user_tag_assignments",
                values={
                    "id": ctx.ulid.for_row(
                        "user_attribute", f"{row['attribute_id']}:{row['user_id']}"
                    ),
                    "tenant_id": tenant_id,
                    "user_id": ctx.ulid.for_row("user", row["user_id"]),
                    "tag_id": ctx.ulid.for_row("attribute", row["attribute_id"]),
                    "assigned_by": None,
                    "rule_id": None,
                    "assigned_at": convert(row.get("regist_date"), ColumnKind.TIMESTAMP),
                },
                natural_key=("user_id", "tag_id"),
                # 一覧のキーは「属性:会員」（fixups の orphan-row はこの形を読む）
                source_key=f"{row['attribute_id']}:{row['user_id']}",
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
    # 属性の必須講座（旧 attribute_lesson）は移さない。旧でも講座を結んでおらず
    # （作成時に attribute_id だけの行を作る）、属性はタグに一本化した（01 review A11）
    return [GroupsStep(), AttributesStep()]


def assignments() -> list[Step]:
    """フェーズ5（会員に紐づく割当）。"""
    return [GroupMembersStep(), UserAttributeValuesStep(), InstructorAssignmentsStep()]
