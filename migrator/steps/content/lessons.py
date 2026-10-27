"""content.1 — レッスン（旧 `unit`）と動画。

**見出しブロック（`unit_type_id=0`）は `lessons` に入れず、`course_chapters`（講座の章）に入れる。**
レッスンではなく表示上の区切りなので、レッスンの種別にはしない（進捗・修了の数え方が狂う）。
旧は講座の中で `sort_no` 順に並べ、**見出しの後ろのユニットをその見出しにまとめていた**。
新は所属を `lessons.chapter_id` で持つ（見出しより前のユニットは NULL）。

動画の配信先は `lecture` ではなく **`lecture_path`** が持つ。`pmovie_chk` が
立っているものは p-movie のトークン、立っていないものは `lecture_path.pc_path`。
"""

from __future__ import annotations

import json
from urllib.parse import urlparse

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
#: 投稿（`discussion` / `discussion_board` / `discussion_board_comment`）は**サポート機能（05）の S7**、
#: 診断結果（`public_learning_skill_unit*`）は**サポート機能（05）の S6**（就業支援）にある。
#: どちらもコンテンツ区分の範囲外で、その区分で移すまで中身は空のまま
CONTENT_NOT_YET_MIGRATED = {"discussion", "skill_check"}

#: **新アプリが扱えるレッスンの種別**（`oneof=video live text survey`。school-launcher
#: `internal/dto/requests_course.go`）。それ以外の旧の種別は `text` で入れ、旧の種別は
#: `settings.legacy_unit_type` に残す（2026-10-26 決定。02 の移行仕様 0-3 の Q2）。
#: テストは今どおり `quizzes.lesson_id` で右パネルのテストのタブに出る
NEW_TYPES = frozenset({"video", "live", "text", "survey"})

DELETED_CHAPTER = "移行対象外"
DELETED_CHAPTER_DETAIL = "削除済みの見出し（新は章の deleted_at を読まず、空の見出しとして出る。2026-10-26 決定）"


def new_type(legacy_type: str, playable: bool) -> str:
    """旧の種別 → 新の `lessons.type`。講義は**再生できる動画のときだけ** `video`（Q6）。"""
    if legacy_type == "video":
        return "video" if playable else "text"
    return legacy_type if legacy_type in NEW_TYPES else "text"


def course_order(rows: list[dict]) -> dict[int, int]:
    """ユニット → 講座の中の通し番号（1 から）。**旧の並び「`sort_no` → `unit_id`」をそのまま番号にする。**

    旧は `sort_no` が重なると `unit_id` の順に出した。新は `sort_order` が同じだと ID（ULID）の順に
    なり並びが変わるので、重ならない番号に振り直す（並びの意味は変えない。Q4）。見出しも同じ番号の列に入る。
    """
    by_course: dict[int, list[dict]] = {}
    for row in rows:
        by_course.setdefault(int(row["lesson_id"]), []).append(row)
    out: dict[int, int] = {}
    for units in by_course.values():
        for number, row in enumerate(
            sorted(units, key=lambda r: (int(r.get("sort_no") or 0), int(r["unit_id"]))), start=1
        ):
            out[int(row["unit_id"])] = number
    return out


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
    並び順が重なる組が 50 ある（自前の講座 21 + 参照している共有講座 29）。2026-10-01 に旧のソースで確かめた）
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

    **削除済みの見出しは移さない**（2026-10-26 決定。02 の移行仕様 0-3 の Q5）。新は章の
    `deleted_at` を読まず、空の見出しとして出す。レッスンの所属（`chapter_of`）は旧の画面どおり
    削除済みの見出しを区切りにしないので、削除済みの章に属するレッスンは無い。
    """

    name = "content.chapters"
    description = "見出しブロックを講座の章として移す"
    source_table = "unit"
    target_table = "course_chapters"
    depends_on = ("content.courses",)

    def extract(self, ctx: RunContext) -> list[dict]:
        units = _fetch_units(ctx)
        order = course_order(units)
        rows = []
        for row in units:
            if not _is_heading(row):
                continue
            if _deleted(row):
                self.drop("course_chapters", str(row["unit_id"]), DELETED_CHAPTER, DELETED_CHAPTER_DETAIL)
                continue
            row["_order"] = order[int(row["unit_id"])]
            rows.append(row)
        return rows

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
                    "sort_order": row.get("_order", int(row.get("sort_no") or 0)),
                    "unit_id": int(row["unit_id"]),
                    "deleted_at": None,  # 削除済みは移さない
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
        units = _fetch_units(ctx)
        lectures = _lectures_by_unit(ctx)
        for row in units:
            row["_lecture"] = lectures.get(int(row["unit_id"]))
        return units

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        chapters = chapter_of(rows)
        order = course_order(rows)
        records: list[Record] = []
        skipped: dict[str, int] = {}
        for row in rows:
            type_id = int(row["unit_type_id"])
            if type_id not in UNIT_TYPES:
                raise MappingError(
                    f"unit_type_id {type_id} が対応表に無い（unit_id={row['unit_id']}）。"
                    "lw2 の定数にも無い種別なので、受け皿を決めてから流す"
                )
            legacy_type = UNIT_TYPES[type_id]
            if legacy_type is None:
                skipped[str(type_id)] = skipped.get(str(type_id), 0) + 1
                continue
            lecture = row.get("_lecture")
            playable = lecture is not None and is_playable(lecture)
            lesson_type = new_type(legacy_type, playable)
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
                        "description": _description(row, legacy_type, playable),
                        "type": lesson_type,
                        "status": "deleted" if _deleted(row) else "published",
                        # **新アプリはレッスンを `deleted_at IS NULL` で絞る**（school-launcher 20261021082002）。
                        # status だけでは管理画面に出る。値は見出しと同じく旧の最終更新日時
                        "deleted_at": (
                            convert(row.get("update_date"), ColumnKind.DATETIME) if _deleted(row) else None
                        ),
                        "sort_order": order[int(row["unit_id"])],
                        # 旧は有料でないユニット（`payment_unit = 0`）を購入の権限なしで開けた
                        # （`PaymentAuthorityModel.class.php:1659`。2026-10-26 決定。Q17）
                        "is_preview": not int(row.get("payment_unit") or 0),
                        # 公開の起点が2種類ある。どちらを使うかは drip_delay_basis で持つ
                        "drip_delay_days": row.get("open_day"),
                        "drip_delay_basis": "payment" if row.get("payment_open_day") else "enrollment",
                        "open_at": convert(row.get("open_datetime"), ColumnKind.DATETIME),
                        "close_at": convert(row.get("close_datetime"), ColumnKind.DATETIME),
                        "close_after_days": row.get("close_day_from_lesson_start_date"),
                        "complete_message": row.get("complete_message"),
                        "search_keyword": row.get("search_keyword"),
                        "duration_min": row.get("unit_duration"),
                        "settings": _settings(row, legacy_type),
                        "created_at": convert(row.get("regist_date"), ColumnKind.TIMESTAMP),
                    },
                    natural_key=("tenant_id", "unit_id"),
                    source_key=int(row["unit_id"]),
                )
            )
        content_pending = sum(
            1 for r in records if json.loads(r.values["settings"]).get("legacy_unit_type") in CONTENT_NOT_YET_MIGRATED
        )
        if content_pending:
            ctx.logger.warning(
                "ディスカッション・スキル診断のユニットを %d 件移した。"
                "**中身（投稿・診断結果）はコンテンツ区分の範囲外**で移していない"
                "（投稿はサポート機能 05 の S7、診断結果は S6）",
                content_pending,
            )
        if skipped:
            ctx.logger.info(
                "lessons に入れないユニット: %s（0=見出しブロックは course_chapters へ / 5=集合研修は対象外区分）", skipped
            )
        return records


def _description(row: dict, legacy_type: str, playable: bool) -> str | None:
    """本文。**再生できない講義は、旧の配信先（URL・ファイルのパス）を本文に載せる**（Q6）。

    旧の講義の多くは動画ではなく、旧サーバーの HTML 教材・PDF・p-movie のプレーヤーの URL
    （ステージングで約 2,000 件）。新の `<video>` では開けないので、`text` のレッスンにして
    URL を本文に残す。旧サーバーを止めると開けなくなる。
    """
    detail = row.get("detail")
    if legacy_type != "video" or playable:
        return detail
    url = _video_url(row.get("_lecture") or {}) if row.get("_lecture") else None
    if not url:
        return detail
    return f"{detail}\n\n{url}" if (detail or "").strip() else url


def _settings(row: dict, legacy_type: str | None = None) -> str:
    return json.dumps(
        {
            # 旧の種別（`video` / `quiz` / `assignment` / `document` / `discussion` / `skill_check` / `survey`）。
            # 新の type に収まらない種別を `text` で入れたので、ここに残す（Q2）
            "legacy_unit_type": legacy_type,
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

    - `pmovie_chk` が立っている … p-movie 配信。**`pmovie_token` をそのまま `video_url` に入れる**（URL は組み立てない）
    - 立っていない … 自前配信。**`lecture_path.pc_path`** が配信先

    **`video_source` は種類だけ正しく入れる**（2026-10-22 決定。`_video_source`）。新アプリは
    `pmovie` を `.m3u8` の URL、`storage` を自前ストレージのキーとして扱うので、旧のトークンや
    旧サーバーの URL のままでは再生できない。再生できるようにするのは移行の外の作業。

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
        # **再生できる動画だけ**（p-movie・YouTube・Vimeo）。それ以外の講義は text のレッスンにして
        # 配信先を本文に載せた（LessonsStep。Q6）
        return [lec for lec in _lectures(ctx) if is_playable(lec)]

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        return self._records(ctx, rows)

    def _records(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
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
                        "video_source": _video_source(row),
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


def _lectures(ctx: RunContext) -> list[dict]:
    """講義と、その先頭の配信先（`lecture_path`）。lecture → unit → lesson の 2 段（unit は tenant_id を持たない）。"""
    source = ctx.require_source()
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


def _lectures_by_unit(ctx: RunContext) -> dict[int, dict]:
    out: dict[int, dict] = {}
    for lecture in _lectures(ctx):
        out.setdefault(int(lecture["unit_id"]), lecture)
    return out


def is_playable(lecture: dict) -> bool:
    """新で動画として再生できる講義か。**p-movie・YouTube・Vimeo だけ**（Q6）。

    storage の行は旧サーバーの HTML 教材・PDF・相対パス・p-movie のプレーヤーの URL などで、
    新の自前ストレージのキーではない（`<video>` では開けない）。p-movie はトークンのままで、
    URL の組み立ての規則を確かめてから補正データで直す。
    """
    return bool(_video_url(lecture)) and _video_source(lecture) in ("pmovie", "youtube", "vimeo")


def _video_url(row: dict) -> str | None:
    """配信先を決める。**p-movie が優先、無ければ `lecture_path`。**"""
    if int(row.get("pmovie_chk") or 0) and (row.get("pmovie_token") or "").strip():
        return str(row["pmovie_token"]).strip()
    path = (row.get("_path") or {}).get("pc_path")
    return str(path).strip() or None if path else None


#: 埋め込みで再生する動画のホスト。**新アプリの `isYouTubeHost` / `isVimeoHost` と同じ一覧**
#: （school-launcher `internal/domain/value_objects_identity.go`）
YOUTUBE_HOSTS = frozenset({
    "youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be",
    "youtube-nocookie.com", "www.youtube-nocookie.com",
})
VIMEO_HOSTS = frozenset({"vimeo.com", "www.vimeo.com", "player.vimeo.com"})


def _video_source(row: dict) -> str:
    """`video_lessons.video_source`。**p-movie は旗で、YouTube・Vimeo はホストで見分ける。**

    どれにも当たらないもの（旧の自前サーバーの URL など）は既定の `storage` のまま。
    """
    if int(row.get("pmovie_chk") or 0) and (row.get("pmovie_token") or "").strip():
        return "pmovie"
    path = str((row.get("_path") or {}).get("pc_path") or "").strip()
    host = (urlparse(path).hostname or "").lower() if "://" in path else ""
    if host in YOUTUBE_HOSTS:
        return "youtube"
    if host in VIMEO_HOSTS:
        return "vimeo"
    return "storage"


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
