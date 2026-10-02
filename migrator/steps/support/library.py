"""support.5 — 教材・ライブラリ。

**lw2 の教材は3系統ある。**

- `drive` … テナント共通の資料フォルダ。**中身のファイルは DB に無く**、ディスク上の
  `dir_name` 配下にある。DB から作れるのは**フォルダだけ**（ファイルは L9 の移送で運ぶ）
- `unit_attached_file` … 講座資料のユニットに添付した資料
- `lesson_attached_file` … 講座に直接添付した資料（ReCADemy は0件）

新環境は `library_folders` → `library_materials` の2段で、公開先は**フォルダ単位**
（`audience_type`）しか持たない。

**旧より広く見せない。** 移行は次の規則で、新に今ある機能で旧に近い公開範囲を作り、
旧の結びつきは別表に残す（新に同じ機能を作れば、その表を読むだけで旧と同じになる）。

| 旧 | 新 |
|---|---|
| 添付資料（ユニット・講座） | **講座ごとの移行用フォルダ**に入れ、「その講座の受講者に公開」（`course_enrolled`） |
| 資料が属するユニット | `library_material_lesson_targets` |
| 資料ごとの公開グループ・属性 | `library_material_group_targets` / `library_material_tag_targets`。**指定のある資料は非公開** |
| フォルダの公開グループ（`drive_group`） | `library_folder_group_targets`。**公開先を「対象者なし」（`specific_users`）にする** |
| 削除済みのユニット・講座・フォルダの資料 | 旧では見えないので**非公開**で移す |

受講制御（`unit_precondition` / `unit_exemption`）は**講座の構成定義**なので
コンテンツ（2）側にある。`content/lessons.py` を見ること。
"""

from __future__ import annotations

from ...context import RunContext
from ...core.datetimes import ColumnKind, convert
from ...core.records import Record
from ..base import Step

DRIVE_COLUMNS = (
    "drive_id",
    "drive_name",
    "dir_name",
    "detail",
    "open_chk",
    "sort_no",
    "del_chk",
    "regist_date",
)
DRIVE_GROUP_COLUMNS = ("drive_id", "group_id", "regist_date")
UNIT_ATTACHED_FILE_COLUMNS = (
    "unit_attached_file_id",
    "unit_id",
    "save_file_name",
    "disp_file_name",
    "sort_no",
    "regist_date",
)
LESSON_ATTACHED_FILE_COLUMNS = (
    "lesson_attached_file_id",
    "lesson_id",
    "save_file_name",
    "disp_file_name",
    "sort_no",
    "del_chk",
    "regist_date",
)
#: 講座ごとの移行用フォルダの並び。旧の資料フォルダ（`drive`）の後ろに出す
COURSE_FOLDER_SORT = 9000
#: `library_folders.name` は varchar(200)
FOLDER_NAME_MAX = 200

#: (旧の表, 資料の名前空間, 旧 ID の列)
_SOURCES = {
    "unit": ("unit_attached_file", "unit_attached_file_id"),
    "lesson": ("lesson_attached_file", "lesson_attached_file_id"),
}


def course_folder_id(ctx: RunContext, lesson_id: object) -> str:
    """講座ごとの移行用フォルダ。**lw2 に対応する行は無い**ので、講座の旧 ID から作る。"""
    return ctx.ulid.for_row("lw2_course_folder", int(lesson_id))


def material_id(ctx: RunContext, source: str, legacy_id: object) -> str:
    return ctx.ulid.for_row(_SOURCES[source][0], int(legacy_id))


def _drive_groups(ctx: RunContext) -> list[dict]:
    return ctx.require_source().fetch_joined(
        "drive_group", DRIVE_GROUP_COLUMNS, parent="drive", on="c.drive_id = p.drive_id"
    )


def _restrictions(ctx: RunContext, kind: str) -> list[dict]:
    """資料ごとの公開先（`kind` は `group` / `attribute`）。ユニット添付と講座添付の両方。"""
    source = ctx.require_source()
    column = f"{kind}_id"
    rows = [
        {**r, "_source": "unit", "_file_id": r["unit_attached_file_id"]}
        for r in source.fetch_joined(
            f"unit_attached_file_{kind}",
            ("unit_attached_file_id", column, "regist_date"),
            parent="lesson",
            on="u.lesson_id = p.lesson_id",
            via=[
                ("unit_attached_file", "a", "c.unit_attached_file_id = a.unit_attached_file_id"),
                ("unit", "u", "a.unit_id = u.unit_id"),
            ],
        )
    ]
    rows += [
        {**r, "_source": "lesson", "_file_id": r["lesson_attached_file_id"]}
        for r in source.fetch_joined(
            f"lesson_attached_file_{kind}",
            ("lesson_attached_file_id", column, "regist_date"),
            parent="lesson",
            on="a.lesson_id = p.lesson_id",
            via=[("lesson_attached_file", "a", "c.lesson_attached_file_id = a.lesson_attached_file_id")],
        )
    ]
    return rows


def attachments(ctx: RunContext) -> list[dict]:
    """ユニット添付と講座添付を、移行に要る形にそろえて返す。

    各行に `_source`（`unit` / `lesson`）、`_file_id`、`_lesson_id`（講座の旧 ID）、
    `_unit_id`（ユニット添付のみ）、`_hidden`（非公開にする理由。無ければ None）を付ける。
    """
    source = ctx.require_source()
    units = {
        int(u["unit_id"]): u
        for u in source.fetch_joined(
            "unit", ("unit_id", "lesson_id", "del_chk"), parent="lesson", on="c.lesson_id = p.lesson_id"
        )
    }
    deleted_courses = {
        int(r["lesson_id"])
        for r in source.fetch_for_tenant("lesson", ("lesson_id", "del_chk"))
        if int(r.get("del_chk") or 0) == 1
    }
    restricted = {(r["_source"], int(r["_file_id"])) for kind in ("group", "attribute") for r in _restrictions(ctx, kind)}

    rows: list[dict] = []
    for r in source.fetch_joined(
        "unit_attached_file",
        UNIT_ATTACHED_FILE_COLUMNS,
        parent="lesson",
        on="u.lesson_id = p.lesson_id",
        via=[("unit", "u", "c.unit_id = u.unit_id")],
    ):
        unit = units[int(r["unit_id"])]
        rows.append({
            **r,
            "_source": "unit",
            "_file_id": int(r["unit_attached_file_id"]),
            "_lesson_id": int(unit["lesson_id"]),
            "_unit_id": int(r["unit_id"]),
            "_unit_deleted": int(unit.get("del_chk") or 0) == 1,
        })
    for r in source.fetch_joined(
        "lesson_attached_file", LESSON_ATTACHED_FILE_COLUMNS, parent="lesson", on="c.lesson_id = p.lesson_id"
    ):
        rows.append({
            **r,
            "_source": "lesson",
            "_file_id": int(r["lesson_attached_file_id"]),
            "_lesson_id": int(r["lesson_id"]),
            "_unit_id": None,
            "_unit_deleted": False,
        })
    for r in rows:
        r["_hidden"] = _hidden_reason(r, deleted_courses, restricted)
    return rows


def _hidden_reason(row: dict, deleted_courses: set[int], restricted: set[tuple[str, int]]) -> str | None:
    """**旧で見えなかった・見せる相手を絞っていた資料は非公開にする。** 理由を返す。"""
    if (row["_source"], row["_file_id"]) in restricted:
        return "資料ごとの公開グループ・属性がある（新に資料単位の公開先が無い）"
    if row["_unit_deleted"]:
        return "ユニットが削除済み"
    if int(row.get("del_chk") or 0) == 1:
        return "添付資料が削除済み"
    if row["_lesson_id"] in deleted_courses:
        return "講座が削除済み"
    return None


class LibraryFoldersStep(Step):
    """`drive` を `library_folders` に移し、添付資料を持つ講座ごとに移行用のフォルダを作る。"""

    name = "support.library_folders"
    description = "資料フォルダを移す（添付資料を持つ講座ごとのフォルダも作る）"
    source_table = "drive"
    target_table = "library_folders"
    depends_on = ("content.courses",)

    def extract(self, ctx: RunContext) -> list[dict]:
        source = ctx.require_source()
        with_groups = {int(r["drive_id"]) for r in _drive_groups(ctx)}
        rows = [
            {**r, "_kind": "drive", "_has_groups": int(r["drive_id"]) in with_groups}
            for r in source.fetch_for_tenant("drive", DRIVE_COLUMNS)
        ]
        # 講座ごとの移行用フォルダ。作成日時はその講座の最初の添付資料（実行時刻にしない）
        names = {int(r["lesson_id"]): r for r in source.fetch_for_tenant("lesson", ("lesson_id", "name", "del_chk"))}
        first: dict[int, object] = {}
        for a in attachments(ctx):
            lid = a["_lesson_id"]
            when = a.get("regist_date")
            if lid not in first or (when and (first[lid] is None or when < first[lid])):
                first[lid] = when
        for lid in sorted(first):
            course = names.get(lid) or {}
            rows.append({
                "_kind": "course",
                "lesson_id": lid,
                "name": course.get("name") or f"講座 {lid}",
                "regist_date": first[lid],
            })
        return rows

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        records = []
        for row in rows:
            if row["_kind"] == "course":
                suffix = "（lw2 の添付資料）"
                name = str(row["name"]).strip()[: FOLDER_NAME_MAX - len(suffix)] + suffix
                records.append(Record(
                    table="library_folders",
                    values={
                        "id": course_folder_id(ctx, row["lesson_id"]),
                        "tenant_id": tenant_id,
                        "name": name,
                        "description": (
                            "lw2 で講座・ユニットに添付していた資料。どのユニットの資料かは "
                            "library_material_lesson_targets が持つ"
                        ),
                        # **その講座の受講者だけに見せる**（旧は講座を開ける人だけが見えた）
                        "audience_type": "course_enrolled",
                        "published": True,
                        "sort_order": COURSE_FOLDER_SORT,
                        "created_at": convert(row.get("regist_date"), ColumnKind.TIMESTAMP),
                    },
                    natural_key=("id",),
                    source_key=f"course:{row['lesson_id']}",
                ))
                continue
            deleted = int(row.get("del_chk") or 0) == 1
            records.append(Record(
                table="library_folders",
                values={
                    "id": ctx.ulid.for_row("drive", row["drive_id"]),
                    "tenant_id": tenant_id,
                    "name": row.get("drive_name") or "",
                    "description": row.get("detail"),
                    # **グループで絞っていたフォルダは「対象者なし」にする。** 新に「グループに公開」が
                    # 無く、全員に公開すると旧より広がる。グループは library_folder_group_targets に残す
                    "audience_type": "specific_users" if row["_has_groups"] else "all_users",
                    # 削除済みのフォルダは旧で見えないので非公開
                    "published": bool(int(row.get("open_chk") or 0)) and not deleted,
                    "sort_order": int(row.get("sort_no") or 0),
                    "created_at": convert(row.get("regist_date"), ColumnKind.TIMESTAMP),
                },
                natural_key=("id",),
                source_key=int(row["drive_id"]),
            ))
        return records


class LibraryFolderCourseTargetsStep(Step):
    """講座ごとの移行用フォルダを、その講座に結ぶ（`course_enrolled` の公開先）。"""

    name = "support.library_folder_course_targets"
    description = "講座ごとの移行用フォルダを講座に結ぶ"
    source_table = "unit_attached_file"
    target_table = "library_folder_course_targets"
    depends_on = ("support.library_folders",)

    def extract(self, ctx: RunContext) -> list[dict]:
        return [{"lesson_id": lid} for lid in sorted({a["_lesson_id"] for a in attachments(ctx)})]

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        return [
            Record(
                table="library_folder_course_targets",
                values={
                    "folder_id": course_folder_id(ctx, row["lesson_id"]),
                    "course_id": ctx.ulid.for_row("lesson", int(row["lesson_id"])),
                },
                natural_key=("folder_id", "course_id"),
                source_key=int(row["lesson_id"]),
            )
            for row in rows
        ]


class LibraryFolderGroupTargetsStep(Step):
    """`drive_group` を `library_folder_group_targets` に移す（→ A1）。"""

    name = "support.library_folder_group_targets"
    description = "資料フォルダの公開グループを移す"
    source_table = "drive_group"
    target_table = "library_folder_group_targets"
    depends_on = ("support.library_folders",)

    def extract(self, ctx: RunContext) -> list[dict]:
        return _drive_groups(ctx)

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        return [
            Record(
                table="library_folder_group_targets",
                values={
                    "id": ctx.ulid.for_row(
                        "drive_group", f"{int(row['drive_id'])}:{int(row['group_id'])}"
                    ),
                    "tenant_id": tenant_id,
                    "folder_id": ctx.ulid.for_row("drive", row["drive_id"]),
                    # 基盤（A10）で移したグループ
                    "group_id": ctx.ulid.for_row("group", row["group_id"]),
                    "created_at": convert(row.get("regist_date"), ColumnKind.TIMESTAMP),
                },
                natural_key=("folder_id", "group_id"),
                source_key=int(row["drive_id"]),
            )
            for row in rows
        ]


class LibraryMaterialsStep(Step):
    """ユニット添付・講座添付を `library_materials` に移す。"""

    name = "support.library_materials"
    description = "ユニット・講座の添付資料を移す"
    source_table = "unit_attached_file"
    target_table = "library_materials"
    depends_on = ("support.library_folders",)

    def extract(self, ctx: RunContext) -> list[dict]:
        rows = attachments(ctx)
        hidden = [r for r in rows if r["_hidden"]]
        if hidden:
            ctx.logger.info("非公開で移す添付資料: %d 件（旧で見えない、または見せる相手を絞っていた）", len(hidden))
        return rows

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        return [
            Record(
                table="library_materials",
                values={
                    "id": material_id(ctx, row["_source"], row["_file_id"]),
                    "tenant_id": tenant_id,
                    "folder_id": course_folder_id(ctx, row["_lesson_id"]),
                    "title": _text(row.get("disp_file_name")) or _text(row.get("save_file_name")) or "",
                    "description": None,
                    # 新の種別は「アップロードしたファイル」か「外部 URL」の2つ。添付資料はすべてファイル
                    "kind": "file",
                    # L9 の移送後にキーへ置き換える。MIME タイプと大きさも移送のときに入れる
                    "storage_key": _text(row.get("save_file_name")),
                    "file_name": _text(row.get("disp_file_name")) or _text(row.get("save_file_name")),
                    "content_type": None,
                    "size_bytes": None,
                    "external_url": None,
                    "published": row["_hidden"] is None,
                    "sort_order": int(row.get("sort_no") or 0),
                    "created_at": convert(row.get("regist_date"), ColumnKind.TIMESTAMP),
                },
                natural_key=("id",),
                source_key=f"{row['_source']}:{row['_file_id']}",
            )
            for row in rows
        ]


class LibraryMaterialLessonTargetsStep(Step):
    """資料とユニットの結びつきを `library_material_lesson_targets` に移す（→ A1）。

    **ユニット添付だけ。** 講座添付はユニットに属さない（講座はフォルダの公開先が持つ）。
    """

    name = "support.library_material_lesson_targets"
    description = "資料とユニットの結びつきを移す"
    source_table = "unit_attached_file"
    target_table = "library_material_lesson_targets"
    depends_on = ("support.library_materials",)

    def extract(self, ctx: RunContext) -> list[dict]:
        return [a for a in attachments(ctx) if a["_source"] == "unit"]

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        return [
            Record(
                table="library_material_lesson_targets",
                values={
                    "id": ctx.ulid.for_row("unit_attached_file_lesson", row["_file_id"]),
                    "tenant_id": tenant_id,
                    "material_id": material_id(ctx, "unit", row["_file_id"]),
                    "lesson_id": ctx.ulid.for_row("unit", row["_unit_id"]),
                    "created_at": convert(row.get("regist_date"), ColumnKind.TIMESTAMP),
                },
                natural_key=("material_id", "lesson_id"),
                source_key=row["_file_id"],
            )
            for row in rows
        ]


class _MaterialRestrictionStep(Step):
    """資料ごとの公開グループ・属性。**旧は両方あれば両方を満たす会員だけに見せた。**"""

    kind = ""
    column = ""

    def extract(self, ctx: RunContext) -> list[dict]:
        return _restrictions(ctx, self.kind)

    def target_values(self, ctx: RunContext, legacy_id: int) -> dict:
        raise NotImplementedError

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        records = []
        for row in rows:
            legacy = int(row[f"{self.kind}_id"])
            key = f"{row['_source']}:{int(row['_file_id'])}:{legacy}"
            records.append(Record(
                table=self.target_table,
                values={
                    "id": ctx.ulid.for_row(f"attached_file_{self.kind}", key),
                    "tenant_id": tenant_id,
                    "material_id": material_id(ctx, row["_source"], row["_file_id"]),
                    **self.target_values(ctx, legacy),
                    "created_at": convert(row.get("regist_date"), ColumnKind.TIMESTAMP),
                },
                natural_key=("material_id", self.column),
                source_key=key,
            ))
        return records


class LibraryMaterialGroupTargetsStep(_MaterialRestrictionStep):
    name = "support.library_material_group_targets"
    description = "添付資料を見せるグループを移す"
    source_table = "unit_attached_file_group"
    target_table = "library_material_group_targets"
    depends_on = ("support.library_materials", "config.groups")
    kind = "group"
    column = "group_id"

    def target_values(self, ctx: RunContext, legacy_id: int) -> dict:
        return {"group_id": ctx.ulid.for_row("group", legacy_id)}


class LibraryMaterialTagTargetsStep(_MaterialRestrictionStep):
    name = "support.library_material_tag_targets"
    description = "添付資料を見せる属性（タグ）を移す"
    source_table = "unit_attached_file_attribute"
    target_table = "library_material_tag_targets"
    depends_on = ("support.library_materials", "config.attributes")
    kind = "attribute"
    column = "tag_id"

    def target_values(self, ctx: RunContext, legacy_id: int) -> dict:
        # 属性はタグとして移している（基盤）
        return {"tag_id": ctx.ulid.for_row("attribute", legacy_id)}


def _text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def build() -> list[Step]:
    """5-5 ファイル。教材・ライブラリ。"""
    return [
        LibraryFoldersStep(),
        LibraryFolderCourseTargetsStep(),
        LibraryFolderGroupTargetsStep(),
        LibraryMaterialsStep(),
        LibraryMaterialLessonTargetsStep(),
        LibraryMaterialGroupTargetsStep(),
        LibraryMaterialTagTargetsStep(),
    ]
