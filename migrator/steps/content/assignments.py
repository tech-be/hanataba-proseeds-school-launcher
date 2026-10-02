"""ondemand.5（後半）— 課題定義（旧 `report` / `report_path`）。

**配布ファイルは5本を5行に展開する。** 旧は `report_disp_file_name1..5` と
`report_save_file_name1..5` の横持ちで、新は `assignment_materials` の縦持ち。
**1本に畳まない**（[review.md](../../../docs/db/02-ondemand/review.md) の A13）。

**提出期限が2種類ある。** `limit_Date`（絶対日時）と `limit_Date_Num`（受講開始からの日数）。
新環境は `due_at` と `due_after_days` の両方を持つので、どちらも移せる。

> **`limit_Date` は大文字混じり。** `limit_date` と書くと取りこぼす。
"""

from __future__ import annotations

import json

from ...context import RunContext
from ...core.datetimes import ColumnKind, convert
from ...core.records import Record
from ..base import Step

#: 配布ファイルは5本。**表示名と実ファイル名が対になっている**
MATERIAL_SLOTS = range(1, 6)

REPORT_COLUMNS = (
    ("report_id", "unit_id", "report_detail", "report_img_file_name")
    + tuple(f"report_disp_file_name{n}" for n in MATERIAL_SLOTS)
    + tuple(f"report_save_file_name{n}" for n in MATERIAL_SLOTS)
    + (
        # **大文字混じり。** limit_date と書くと取りこぼす
        "limit_Date",
        "limit_Date_Num",
        "send_mail_chk",
        "enable_change_chk",
        "complete_condition_chk",
        "no_submit_chk",
        "report_commentary_chk",
        "report_pmovie_chk",
        "report_pmovie_token",
        "del_chk",
        "regist_date",
        "update_date",
    )
)

#: lw2 の共通ホワイトリスト（`UploadUtil::$extension_file`、21種）。
#: 新環境は課題ごとに許可拡張子を持つが、**旧は課題単位の設定を持たない**ので既定値にする。
#: カンマ区切りで89文字なので `varchar(100)` に収まる（桁拡大は要らない）
ALLOWED_TYPES = ",".join(
    (
        "txt", "rtf", "pdf", "csv", "doc", "docx", "xls", "xlsx", "ppt", "pptx",
        "ppsx", "jpg", "jpeg", "gif", "bmp", "png", "htm", "html", "zip", "lzh", "mp3",
    )
)


def _reports(ctx: RunContext) -> list[dict]:
    """課題を読む。**`report` は `tenant_id` を持たない**ので `unit` → `lesson` で絞る。"""
    return ctx.require_source().fetch_joined(
        "report",
        REPORT_COLUMNS,
        parent="lesson",
        on="u.lesson_id = p.lesson_id",
        via=[("unit", "u", "c.unit_id = u.unit_id")],
    )


class AssignmentsStep(Step):
    """`report` を `assignments` に移す。"""

    name = "content.assignments"
    description = "課題を移す（提出期限は絶対日時と相対日数の両方）"
    source_table = "report"
    target_table = "assignments"
    depends_on = ("content.lessons",)

    def extract(self, ctx: RunContext) -> list[dict]:
        source = ctx.require_source()
        reports = _reports(ctx)
        # course_id が NOT NULL。ユニットから講座をたどる
        units = {
            int(u["unit_id"]): u
            for u in source.fetch_joined(
                "unit",
                ("unit_id", "lesson_id", "title"),
                parent="lesson",
                on="c.lesson_id = p.lesson_id",
            )
        }
        rows: list[dict] = []
        for report in reports:
            unit = units.get(int(report["unit_id"]))
            if unit is None:
                # 通らない: 課題は unit → lesson で絞って読むので、ユニットの無い課題は読めない
                # （テナントで絞れないので、このテナントの行かも分からない）
                continue
            rows.append({**report, "_unit": unit})
        return rows

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        records: list[Record] = []
        for row in rows:
            unit = row["_unit"]
            records.append(
                Record(
                    table="assignments",
                    values={
                        "id": ctx.ulid.for_row("report", row["report_id"]),
                        "tenant_id": tenant_id,
                        "course_id": ctx.ulid.for_row("lesson", unit["lesson_id"]),
                        "lesson_id": ctx.ulid.for_row("unit", row["unit_id"]),
                        # 旧 `report` に課題名が無い。**ユニット名が画面の見出し**なので写す
                        "title": unit.get("title") or "",
                        "description": row.get("report_detail"),
                        "allowed_types": ALLOWED_TYPES,
                        # 旧に満点の列が無い（採点は添削側の点数）
                        "max_score": None,
                        "due_at": convert(row.get("limit_Date"), ColumnKind.DATETIME),
                        "due_after_days": _positive(row.get("limit_Date_Num")),
                        "status": "deleted" if int(row.get("del_chk") or 0) == 1 else "published",
                        "video_url": _video_url(row),
                        "settings": _settings(row),
                        # **ゼロ日付が 113件中6件ある。** `created_at` は NOT NULL なので
                        # `update_date` で代替する。両方ゼロの行（1件）は移らない
                        "created_at": convert(
                            row.get("regist_date") or row.get("update_date"), ColumnKind.TIMESTAMP
                        ),
                    },
                    natural_key=("id",),
                    source_key=int(row["report_id"]),
                )
            )
        return records


class AssignmentMaterialsStep(Step):
    """配布ファイル5本を `assignment_materials` に展開する。

    **5本とも移す。** 1本に畳むと「何を配っていたか」が分からなくなる（A13）。
    実体のファイルは L9 で移送し、`storage_key` を移送先のキーに置き換える。
    """

    name = "content.assignment_materials"
    description = "課題の配布ファイル（最大5本）を移す"
    source_table = "report"
    target_table = "assignment_materials"
    depends_on = ("content.assignments",)

    def extract(self, ctx: RunContext) -> list[dict]:
        return _reports(ctx)

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        records: list[Record] = []
        for row in rows:
            assignment_id = ctx.ulid.for_row("report", row["report_id"])
            order = 0
            for slot in MATERIAL_SLOTS:
                saved = _text(row.get(f"report_save_file_name{slot}"))
                if not saved:
                    continue  # 使っていない枠
                order += 1
                records.append(
                    Record(
                        table="assignment_materials",
                        values={
                            "id": ctx.ulid.for_row("report_file", f"{assignment_id}:{slot}"),
                            "tenant_id": tenant_id,
                            "assignment_id": assignment_id,
                            # **空いた枠を詰めて採番する。** UNIQUE (assignment_id, sort_order)
                            "sort_order": order,
                            # 表示名が空なら実ファイル名を出す（画面で名無しにしない）
                            "file_name": _text(row.get(f"report_disp_file_name{slot}")) or saved,
                            # L9 の移送前は旧のファイル名。移送後にキーへ置き換える
                            "storage_key": saved,
                        },
                        natural_key=("assignment_id", "sort_order"),
                        source_key=int(row["report_id"]),
                    )
                )
        return records


# --- 小道具 -----------------------------------------------------------------


def _video_url(row: dict) -> str | None:
    """課題の説明動画。**p-movie 連携が立っているときだけトークンが入っている。**"""
    if not int(row.get("report_pmovie_chk") or 0):
        return None
    return _text(row.get("report_pmovie_token"))


def _settings(row: dict) -> str:
    return json.dumps(
        {
            "send_mail": bool(int(row.get("send_mail_chk") or 0)),
            "enable_change": bool(int(row.get("enable_change_chk") or 0)),
            "complete_condition": bool(int(row.get("complete_condition_chk") or 0)),
            # **提出させず評価だけする課題。** 提出が無くても未提出ではない
            "no_submit": bool(int(row.get("no_submit_chk") or 0)),
            "commentary": bool(int(row.get("report_commentary_chk") or 0)),
            "pmovie": bool(int(row.get("report_pmovie_chk") or 0)),
            "image_file_name": _text(row.get("report_img_file_name")),
        },
        ensure_ascii=False,
    )


def _text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _positive(value: object) -> int | None:
    number = int(value or 0)
    return number if number > 0 else None


def build() -> list[Step]:
    return [AssignmentsStep(), AssignmentMaterialsStep()]
