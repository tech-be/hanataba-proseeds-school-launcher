"""ondemand.3 — レッスン（旧 `unit`）と動画。

**見出しブロック（`unit_type_id=0`）は `lessons` に入れず、`course_chapters`（講座の章）に入れる。**
レッスンではなく表示上の区切りなので、レッスンの種別にはしない（進捗・修了の数え方が狂う）。
旧は講座の中で `sort_no` 順に並べ、**見出しの後ろのユニットをその見出しにまとめていた**。
新は所属を `lessons.chapter_id` で持つ（見出しより前のユニットは NULL）。

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
    "update_date",
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
    0: None,  # 見出しブロック。lessons ではなく course_chapters に入れる（ChaptersStep）
    1: "video",
    2: "quiz",
    3: "survey",
    4: "assignment",
    5: None,  # 集合研修。対象外区分（X01）
    6: "document",
    7: "discussion",   # ShareController::UNIT_TYPE_DISCUSSION
    8: "skill_check",  # ShareController::UNIT_TYPE_SKILL
}

#: **ユニットは移すが、中身はこの区分では移さない種別。**
#: 投稿（`discussion` / `discussion_board` / `discussion_board_comment`）は**区分が未分類**、
#: 診断結果（`public_learning_skill_unit*`）は**就職支援（07）**にある。
#: どちらもオンデマンドの範囲外で、その区分を移すまで中身は空のまま
CONTENT_NOT_YET_MIGRATED = {"discussion", "skill_check"}


#: 章の ULID の名前空間。**レッスン（`unit`）と分ける** — 同じ旧 unit_id から作るが別の表
CHAPTER_NS = "unit_chapter"


def _is_heading(row: dict) -> bool:
    return int(row.get("unit_type_id") or 0) == 0


def _deleted(row: dict) -> bool:
    return int(row.get("del_chk") or 0) == 1


def chapter_of(rows: list[dict]) -> dict[int, int | None]:
    """ユニット → 所属する見出しの旧 unit_id。

    **旧の講座ページと同じ規則。** 講座ごとに `sort_no` 順（同じなら unit_id 順）に並べ、
    （旧 `UnitModel::_buildSql` の `lessonId` の既定の並び `U.sort_no ASC, U.unit_id ASC`。
    受講者の講座ページ `LessonController` → `findUnitByLessonId` が使う。ReCADemy では見出しと
    並び順が重なる組が 77 ある。2026-10-01 に旧のソースで確かめた）
    直前にある**削除されていない**見出しにまとめる。削除済みの見出しは画面に出ないので、
    区切りにもならない。最初の見出しより前のユニットは章に属さない（None）。
    """
    by_course: dict[int, list[dict]] = {}
    for row in rows:
        by_course.setdefault(int(row["lesson_id"]), []).append(row)
    out: dict[int, int | None] = {}
    for units in by_course.values():
        current: int | None = None
        for row in sorted(units, key=lambda r: (int(r.get("sort_no") or 0), int(r["unit_id"]))):
            if _is_heading(row):
                if not _deleted(row):
                    current = int(row["unit_id"])
                continue
            out[int(row["unit_id"])] = current
    return out


def _fetch_units(ctx: RunContext) -> list[dict]:
    # 共有講座（tenant_id=0）のユニットも入る（`SourceDatabase.shared_lessons`）
    return ctx.require_source().fetch_joined(
        "unit", UNIT_COLUMNS, parent="lesson", on="c.lesson_id = p.lesson_id"
    )


class ChaptersStep(Step):
    """見出しブロック（`unit_type_id=0`）を `course_chapters`（講座の章）に移す。

    **削除済みの見出しも移す**（`deleted_at`。2026-10-01 の方針）。新のアプリはまだ `deleted_at` を
    読まないので、削除済みの章も講座に出る。レッスンの所属（`chapter_of`）は旧の画面どおり、
    削除済みの見出しを区切りにしない。
    """

    name = "content.chapters"
    description = "見出しブロックを講座の章として移す"
    source_table = "unit"
    target_table = "course_chapters"
    depends_on = ("content.courses",)

    def extract(self, ctx: RunContext) -> list[dict]:
        return [r for r in _fetch_units(ctx) if _is_heading(r)]

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        return [
            Record(
                table="course_chapters",
                values={
                    "id": ctx.ulid.for_row(CHAPTER_NS, row["unit_id"]),
                    "tenant_id": tenant_id,
                    "course_id": ctx.ulid.for_row("lesson", row["lesson_id"]),
                    "title": (row.get("title") or "").strip(),
                    "sort_order": int(row.get("sort_no") or 0),
                    "unit_id": int(row["unit_id"]),
                    "deleted_at": (
                        convert(row.get("update_date"), ColumnKind.DATETIME) if _deleted(row) else None
                    ),
                    "created_at": convert(row.get("regist_date"), ColumnKind.TIMESTAMP),
                },
                natural_key=("tenant_id", "unit_id"),
                source_key=int(row["unit_id"]),
            )
            for row in rows
        ]


class LessonsStep(Step):
    """ユニットを `lessons` に移す。

    **対応表に無い `unit_type_id` が来たら止める。** 黙って `text` に倒すと、
    移行後に種別で区別できなくなる。
    """

    name = "content.lessons"
    description = "ユニットをレッスンとして移す（見出しブロックは除く）"
    source_table = "unit"
    target_table = "lessons"
    depends_on = ("content.courses", "content.chapters")

    def extract(self, ctx: RunContext) -> list[dict]:
        return _fetch_units(ctx)

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        chapters = chapter_of(rows)
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
                        "unit_id": int(row["unit_id"]),
                        "course_id": ctx.ulid.for_row("lesson", row["lesson_id"]),
                        # 所属する章（直前の見出し）。見出しより前のユニットは NULL
                        "chapter_id": (
                            ctx.ulid.for_row(CHAPTER_NS, chapters[int(row["unit_id"])])
                            if chapters.get(int(row["unit_id"])) is not None
                            else None
                        ),
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
                    natural_key=("tenant_id", "unit_id"),
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
                "lessons に入れないユニット: %s（0=見出しブロックは course_chapters へ / 5=集合研修は対象外区分）", skipped
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
    return [ChaptersStep(), LessonsStep(), VideoLessonsStep(), LessonPreconditionsStep()]
