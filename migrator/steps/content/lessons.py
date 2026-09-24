"""ondemand.3 — レッスン（旧 `unit`）と動画。

**見出しブロック（`unit_type_id=0`）は入れない。** レッスンではなく表示上の区切りで、
`lessons` に入れると FK と種別の両方が合わなくなる（ETL設計 §5-0）。

動画の配信先は `lecture` ではなく **`lecture_path`** が持つ。`pmovie_chk` が
立っているものは p-movie のトークン、立っていないものは `lecture_path.pc_path`。
"""

from __future__ import annotations

import json

from ...context import RunContext
from ...core.datetimes import ColumnKind, convert
from ...core.records import Record
from ...errors import MappingError
from ..base import Step

UNIT_COLUMNS = (
    "unit_id",
    "lesson_id",
    "unit_type_id",
    "sort_no",
    "title",
    "detail",
    "search_keyword",
    "complete_message",
    "open_datetime",
    "open_day",
    "payment_open_day",
    "close_datetime",
    "close_day_from_lesson_start_date",
    "open_close_chk",
    "payment_unit",
    "not_skill_result_chk",
    "unit_duration",
    "del_chk",
    "regist_date",
)

LECTURE_COLUMNS = (
    "lecture_id",
    "lecture_complete_type",
    "plugin_chk",
    "pmovie_chk",
    "pmovie_complete_type",
    "pmovie_token",
    "is_continue_watch_chk",
    "skip_prevention_setting",
)

LECTURE_PATH_COLUMNS = ("lecture_id", "sort_no", "pc_path", "smartphone_path")

UNIT_PRECONDITION_COLUMNS = ("unit_id", "precondition_unit_id", "precondition_type_id", "regist_date")
UNIT_EXEMPTION_COLUMNS = ("unit_id", "exemption_unit_id", "exemption_score", "regist_date")

#: 旧 `unit.unit_type_id` → 新 `lessons.type`（`lesson_types.code`）。
#: **畳まない。** 0 は入れない（見出し）、5 は対象外区分（集合研修）
UNIT_TYPES: dict[int, str | None] = {
    0: None,  # 見出しブロック。lessons に入れない
    1: "video",
    2: "quiz",
    3: "survey",
    4: "assignment",
    5: None,  # 集合研修。対象外区分（X02）
    6: "document",
    7: "discussion",   # ShareController::UNIT_TYPE_DISCUSSION
    8: "skill_check",  # ShareController::UNIT_TYPE_SKILL
}

#: **ユニットは移すが、中身はこの区分では移さない種別。**
#: 投稿（`discussion` / `discussion_board` / `discussion_board_comment`）は**区分が未分類**、
#: 診断結果（`public_learning_skill_unit*`）は**就職支援（07）**にある。
#: どちらもオンデマンドの範囲外で、その区分を移すまで中身は空のまま
CONTENT_NOT_YET_MIGRATED = {"discussion", "skill_check"}


class LessonsStep(Step):
    """ユニットを `lessons` に移す。

    **対応表に無い `unit_type_id` が来たら止める。** 黙って `text` に倒すと、
    移行後に種別で区別できなくなる。
    """

    name = "content.lessons"
    description = "ユニットをレッスンとして移す（見出しブロックは除く）"
    source_table = "unit"
    target_table = "lessons"
    depends_on = ("content.courses",)

    def extract(self, ctx: RunContext) -> list[dict]:
        return ctx.require_source().fetch_joined(
            "unit", UNIT_COLUMNS, parent="lesson", on="c.lesson_id = p.lesson_id"
        )

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        records: list[Record] = []
        skipped: dict[str, int] = {}
        for row in rows:
            type_id = int(row["unit_type_id"])
            if type_id not in UNIT_TYPES:
                raise MappingError(
                    f"unit_type_id {type_id} が対応表に無い（unit_id={row['unit_id']}）。"
                    "lw2 の定数にも無い種別なので、受け皿を決めてから流す"
                )
            lesson_type = UNIT_TYPES[type_id]
            if lesson_type is None:
                skipped[str(type_id)] = skipped.get(str(type_id), 0) + 1
                continue
            records.append(
                Record(
                    table="lessons",
                    values={
                        "id": ctx.ulid.for_row("unit", row["unit_id"]),
                        "tenant_id": tenant_id,
                        "legacy_id": int(row["unit_id"]),
                        "course_id": ctx.ulid.for_row("lesson", row["lesson_id"]),
                        "title": row.get("title"),
                        "description": row.get("detail"),
                        "type": lesson_type,
                        "status": "deleted" if int(row.get("del_chk") or 0) == 1 else "published",
                        "sort_order": int(row.get("sort_no") or 0),
                        "is_preview": False,
                        # 公開の起点が2種類ある。どちらを使うかは drip_delay_basis で持つ
                        "drip_delay_days": row.get("open_day"),
                        "drip_delay_basis": "payment" if row.get("payment_open_day") else "enrollment",
                        "open_at": convert(row.get("open_datetime"), ColumnKind.DATETIME),
                        "close_at": convert(row.get("close_datetime"), ColumnKind.DATETIME),
                        "close_after_days": row.get("close_day_from_lesson_start_date"),
                        "complete_message": row.get("complete_message"),
                        "search_keyword": row.get("search_keyword"),
                        "duration_min": row.get("unit_duration"),
                        "settings": _settings(row),
                        "created_at": convert(row.get("regist_date"), ColumnKind.TIMESTAMP),
                    },
                    natural_key=("tenant_id", "legacy_id"),
                    source_key=int(row["unit_id"]),
                )
            )
        content_pending = sum(
            1 for r in records if r.values["type"] in CONTENT_NOT_YET_MIGRATED
        )
        if content_pending:
            ctx.logger.warning(
                "ディスカッション・スキル診断のユニットを %d 件移した。"
                "**中身（投稿・診断結果）はオンデマンドの範囲外**で移していない"
                "（投稿は区分が未分類、診断結果は就職支援 07）",
                content_pending,
            )
        if skipped:
            ctx.logger.info(
                "lessons に入れないユニット: %s（0=見出しブロック / 5=集合研修は対象外区分）", skipped
            )
        return records


def _settings(row: dict) -> str:
    return json.dumps(
        {
            "open_close_chk": row.get("open_close_chk"),
            "payment_unit": bool(int(row.get("payment_unit") or 0)),
            "not_skill_result": bool(int(row.get("not_skill_result_chk") or 0)),
            "payment_open_day": row.get("payment_open_day"),
        },
        ensure_ascii=False,
    )


class VideoLessonsStep(Step):
    """講義ユニットの動画を `video_lessons` に移す。

    **配信先は2か所に分かれている。**

    - `pmovie_chk` が立っている … p-movie 配信。`pmovie_token` から URL を組み立てる
    - 立っていない … 自前配信。**`lecture_path.pc_path`** が配信先

    `lecture_path` は1ユニットに複数行を持てる（`sort_no` つき）が、新環境は
    1レッスン1動画なので**`sort_no` の最小を採る**（lw2 も先頭を使っている）。
    `smartphone_path` は行き先が無い（新環境は端末別の配信先を持たない）。
    """

    name = "content.video_lessons"
    description = "講義動画の配信先を移す"
    source_table = "lecture"
    target_table = "video_lessons"
    depends_on = ("content.lessons",)

    def extract(self, ctx: RunContext) -> list[dict]:
        source = ctx.require_source()
        # lecture → unit → lesson の2段。**unit は tenant_id を持たない**
        lectures = source.fetch_joined(
            "lecture",
            LECTURE_COLUMNS + ("unit_id",),
            parent="lesson",
            on="u.lesson_id = p.lesson_id",
            via=[("unit", "u", "c.unit_id = u.unit_id")],
            where="u.unit_type_id = 1",
        )
        paths = source.fetch_joined(
            "lecture_path",
            LECTURE_PATH_COLUMNS,
            parent="lesson",
            on="u.lesson_id = p.lesson_id",
            via=[
                ("lecture", "lec", "c.lecture_id = lec.lecture_id"),
                ("unit", "u", "lec.unit_id = u.unit_id"),
            ],
        )
        first: dict[int, dict] = {}
        for path in sorted(paths, key=lambda r: (int(r["lecture_id"]), int(r.get("sort_no") or 0))):
            first.setdefault(int(path["lecture_id"]), path)
        for lecture in lectures:
            lecture["_path"] = first.get(int(lecture["lecture_id"]))
        return lectures

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        records: list[Record] = []
        missing = 0
        for row in rows:
            url = _video_url(row)
            if not url:
                missing += 1
            records.append(
                Record(
                    table="video_lessons",
                    values={
                        "tenant_id": tenant_id,
                        "lesson_id": ctx.ulid.for_row("unit", row["unit_id"]),
                        "video_url": url,
                        "video_duration": None,  # 旧に尺を持つ列が無い
                        "complete_type": _complete_type(row),
                        "skip_prevention": bool(int(row.get("skip_prevention_setting") or 0)),
                        "settings": json.dumps(
                            {
                                "pmovie": bool(int(row.get("pmovie_chk") or 0)),
                                "plugin": bool(int(row.get("plugin_chk") or 0)),
                                "continue_watch": bool(int(row.get("is_continue_watch_chk") or 0)),
                                # 端末別の配信先は新環境に無い。捨てずにここへ残す
                                "smartphone_path": (row.get("_path") or {}).get("smartphone_path"),
                            },
                            ensure_ascii=False,
                        ),
                    },
                    natural_key=("lesson_id",),
                    source_key=int(row["unit_id"]),
                )
            )
        if missing:
            ctx.logger.warning(
                "配信先が無い動画が %d 件ある（`pmovie_token` も `lecture_path.pc_path` も空）。"
                "`video_url` は NOT NULL なので、この行は移らない",
                missing,
            )
        return records


def _video_url(row: dict) -> str | None:
    """配信先を決める。**p-movie が優先、無ければ `lecture_path`。**"""
    if int(row.get("pmovie_chk") or 0) and (row.get("pmovie_token") or "").strip():
        return str(row["pmovie_token"]).strip()
    path = (row.get("_path") or {}).get("pc_path")
    return str(path).strip() or None if path else None


def _complete_type(row: dict) -> str | None:
    """完了条件。p-movie 配信かどうかで列が分かれている。"""
    value = (
        row.get("pmovie_complete_type")
        if int(row.get("pmovie_chk") or 0)
        else row.get("lecture_complete_type")
    )
    return None if value is None else str(value)


class LessonPreconditionsStep(Step):
    """`unit_precondition` を `lesson_preconditions` に移す（→ A15）。

    **これが無いと全ユニットが最初から受講できる。**
    """

    name = "content.lesson_preconditions"
    description = "ユニットの前提条件を移す"
    source_table = "unit_precondition"
    target_table = "lesson_preconditions"
    depends_on = ("content.lessons",)

    def extract(self, ctx: RunContext) -> list[dict]:
        source = ctx.require_source()
        exemptions = source.fetch_joined(
            "unit_exemption",
            UNIT_EXEMPTION_COLUMNS,
            parent="lesson",
            on="u.lesson_id = p.lesson_id",
            via=[("unit", "u", "c.unit_id = u.unit_id")],
        )
        if exemptions:
            # **受け皿を作らなかったのは、形が違うから。** 会員ごとの免除表
            # （`lesson_exemptions`）は一度 migration に書いたが、旧が規則である以上
            # 何行入れればいいかが決まらないので取り下げた。設計をやり直す
            ctx.logger.warning(
                "unit_exemption が %d 件ある。lw2 は「別ユニットで◯点以上なら免除」という"
                "**規則**（exemption_unit_id + exemption_score）で、会員ごとの免除表では"
                "受けられない。**受け皿を前提条件側の拡張として設計し直すまで移せない**",
                len(exemptions),
            )
        return source.fetch_joined(
            "unit_precondition",
            UNIT_PRECONDITION_COLUMNS,
            parent="lesson",
            on="u.lesson_id = p.lesson_id",
            via=[("unit", "u", "c.unit_id = u.unit_id")],
        )

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        return [
            Record(
                table="lesson_preconditions",
                values={
                    "id": ctx.ulid.for_row(
                        "unit_precondition",
                        f"{int(row['unit_id'])}:{int(row['precondition_unit_id'])}",
                    ),
                    "tenant_id": tenant_id,
                    "lesson_id": ctx.ulid.for_row("unit", row["unit_id"]),
                    "required_lesson_id": ctx.ulid.for_row("unit", row["precondition_unit_id"]),
                    "created_at": convert(row.get("regist_date"), ColumnKind.TIMESTAMP),
                },
                natural_key=("lesson_id", "required_lesson_id"),
                source_key=int(row["unit_id"]),
            )
            for row in rows
        ]


def build() -> list[Step]:
    return [LessonsStep(), VideoLessonsStep(), LessonPreconditionsStep()]
