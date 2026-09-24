"""support.5 — 教材・ライブラリ。

**lw2 の教材は2系統ある。**

- `drive` … テナント共通の資料フォルダ。**中身のファイルは DB に無く**、ディスク上の
  `dir_name` 配下にある。DB から作れるのは**フォルダだけ**
- `unit_attached_file` … ユニットに添付した資料。**フォルダという概念が無い**

新環境は `library_folders` → `library_materials` の2段で、`folder_id` が NOT NULL。
ユニット添付には親フォルダが無いので、**移行用のフォルダを1つ作ってそこに入れ**、
本来の結びつき（どのユニットの資料か）は `library_material_lesson_targets` で持つ。

受講制御（`unit_precondition` / `unit_exemption`）は**講座の構成定義**なので
コンテンツ（2）側にある。`content/lessons.py` を見ること。
"""

from __future__ import annotations

from datetime import datetime, timezone

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
#: ユニット添付資料を入れる移行用フォルダ。**lw2 に対応する行は無い。**
#: `library_materials.folder_id` が NOT NULL なので、1つだけ作って全部そこに入れる
UNIT_FOLDER_KEY = "lw2-unit-attachments"
UNIT_FOLDER_NAME = "ユニット添付資料（lw2 移行）"


def _unit_folder_id(ctx: RunContext) -> str:
    return ctx.ulid.for_row("drive", UNIT_FOLDER_KEY)


class LibraryFoldersStep(Step):
    """`drive` を `library_folders` に移し、ユニット添付用のフォルダを1つ足す。"""

    name = "support.library_folders"
    description = "資料フォルダを移す（ユニット添付用のフォルダも作る）"
    source_table = "drive"
    target_table = "library_folders"
    depends_on = ("content.lessons",)

    def extract(self, ctx: RunContext) -> list[dict]:
        return ctx.require_source().fetch_for_tenant("drive", DRIVE_COLUMNS)

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        records = [
            Record(
                table="library_folders",
                values={
                    "id": ctx.ulid.for_row("drive", row["drive_id"]),
                    "tenant_id": tenant_id,
                    "name": row.get("drive_name") or "",
                    "description": row.get("detail"),
                    # 旧に公開範囲の区分が無い。グループ指定は別表（`drive_group`）で持つ
                    "audience_type": "all_users",
                    "published": bool(int(row.get("open_chk") or 0)),
                    "sort_order": int(row.get("sort_no") or 0),
                    "created_at": convert(row.get("regist_date"), ColumnKind.TIMESTAMP),
                },
                natural_key=("id",),
                source_key=int(row["drive_id"]),
            )
            for row in rows
        ]
        records.append(
            Record(
                table="library_folders",
                values={
                    "id": _unit_folder_id(ctx),
                    "tenant_id": tenant_id,
                    "name": UNIT_FOLDER_NAME,
                    "description": (
                        "lw2 の unit_attached_file を受けるフォルダ。"
                        "どのユニットの資料かは library_material_lesson_targets が持つ"
                    ),
                    "audience_type": "all_users",
                    "published": True,
                    "sort_order": 9000,
                    # **移行が作る行。** lw2 に対応する `regist_date` が無い。
                    # NULL を渡すと既定値は効かず NOT NULL 違反になるので、実行時刻を入れる
                    "created_at": datetime.now(timezone.utc).replace(tzinfo=None),
                },
                natural_key=("id",),
                source_key=UNIT_FOLDER_KEY,
            )
        )
        return records


class LibraryFolderGroupTargetsStep(Step):
    """`drive_group` を `library_folder_group_targets` に移す（→ A18）。"""

    name = "support.library_folder_group_targets"
    description = "資料フォルダの公開グループを移す"
    source_table = "drive_group"
    target_table = "library_folder_group_targets"
    depends_on = ("support.library_folders",)

    def extract(self, ctx: RunContext) -> list[dict]:
        return ctx.require_source().fetch_joined(
            "drive_group", DRIVE_GROUP_COLUMNS, parent="drive", on="c.drive_id = p.drive_id"
        )

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


def _attachments(ctx: RunContext) -> list[dict]:
    return ctx.require_source().fetch_joined(
        "unit_attached_file",
        UNIT_ATTACHED_FILE_COLUMNS,
        parent="lesson",
        on="u.lesson_id = p.lesson_id",
        via=[("unit", "u", "c.unit_id = u.unit_id")],
    )


class LibraryMaterialsStep(Step):
    """`unit_attached_file` を `library_materials` に移す。"""

    name = "support.library_materials"
    description = "ユニット添付資料を移す"
    source_table = "unit_attached_file"
    target_table = "library_materials"
    depends_on = ("support.library_folders",)

    def extract(self, ctx: RunContext) -> list[dict]:
        source = ctx.require_source()
        for table in ("unit_attached_file_group", "unit_attached_file_attribute"):
            scoped = source.fetch_joined(
                table,
                ("unit_attached_file_id",),
                parent="lesson",
                on="u.lesson_id = p.lesson_id",
                via=[
                    ("unit_attached_file", "a", "c.unit_attached_file_id = a.unit_attached_file_id"),
                    ("unit", "u", "a.unit_id = u.unit_id"),
                ],
            )
            if scoped:
                # **新環境の公開範囲はフォルダ単位。** 資料単位の指定は受け皿が無い
                ctx.logger.warning(
                    "%s が %d 件ある。**新環境の公開範囲はフォルダ単位**で、"
                    "資料ごとの公開指定を入れる先が無い（受け皿の追加が要る）",
                    table,
                    len(scoped),
                )
        return _attachments(ctx)

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        folder_id = _unit_folder_id(ctx)
        return [
            Record(
                table="library_materials",
                values={
                    "id": ctx.ulid.for_row("unit_attached_file", row["unit_attached_file_id"]),
                    "tenant_id": tenant_id,
                    "folder_id": folder_id,
                    "title": _text(row.get("disp_file_name")) or _text(row.get("save_file_name")) or "",
                    "description": None,
                    "kind": "file",
                    # L9 の移送後にキーへ置き換える
                    "storage_key": _text(row.get("save_file_name")),
                    "file_name": _text(row.get("disp_file_name")) or _text(row.get("save_file_name")),
                    "content_type": None,
                    "size_bytes": None,
                    "external_url": None,
                    "published": True,
                    "sort_order": int(row.get("sort_no") or 0),
                    "created_at": convert(row.get("regist_date"), ColumnKind.TIMESTAMP),
                },
                natural_key=("id",),
                source_key=int(row["unit_attached_file_id"]),
            )
            for row in rows
        ]


class LibraryMaterialLessonTargetsStep(Step):
    """資料とユニットの結びつきを `library_material_lesson_targets` に移す（→ A18）。

    **ここが本来の親子関係。** フォルダは器にすぎない。
    """

    name = "support.library_material_lesson_targets"
    description = "資料とユニットの結びつきを移す"
    source_table = "unit_attached_file"
    target_table = "library_material_lesson_targets"
    depends_on = ("support.library_materials",)

    def extract(self, ctx: RunContext) -> list[dict]:
        return _attachments(ctx)

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        return [
            Record(
                table="library_material_lesson_targets",
                values={
                    "id": ctx.ulid.for_row(
                        "unit_attached_file_lesson", row["unit_attached_file_id"]
                    ),
                    "tenant_id": tenant_id,
                    "material_id": ctx.ulid.for_row(
                        "unit_attached_file", row["unit_attached_file_id"]
                    ),
                    "lesson_id": ctx.ulid.for_row("unit", row["unit_id"]),
                    "created_at": convert(row.get("regist_date"), ColumnKind.TIMESTAMP),
                },
                natural_key=("material_id", "lesson_id"),
                source_key=int(row["unit_attached_file_id"]),
            )
            for row in rows
        ]


def _text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def build() -> list[Step]:
    """5-5 ファイル。教材・ライブラリ。"""
    return [
        LibraryFoldersStep(),
        LibraryFolderGroupTargetsStep(),
        LibraryMaterialsStep(),
        LibraryMaterialLessonTargetsStep(),
    ]
