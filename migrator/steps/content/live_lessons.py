"""live.3 / live.4 — ライブ本体（旧 `live_lesson`）と開催回（旧 `live_lesson_date`）。

**`lessons.legacy_id` は使わない。** その列はオンデマンドが `unit.unit_id` で使っており、
ステージング実測で **18件中11件**がライブの ID と衝突する。旧 ID は
`live_lessons.legacy_id`（A1 で追加）に持つ。

**開催回は `datetime(3)`、ライブ本体の `scheduled_at` は `timestamp`。**
同じ区分の中で TZ の扱いが逆になるので、列ごとに `ColumnKind` を使い分ける。
"""

from __future__ import annotations

import json

from ...context import RunContext
from ...core.datetimes import ColumnKind, DateBoundary, convert, convert_date
from ...core.records import Record
from ..base import Step
from .live_courses import course_for, resolve_placement

LIVE_LESSON_COLUMNS = (
    "live_lesson_id",
    "tenant_id",
    "live_lesson_cate_id",
    "live_lesson_type",
    "live_lesson_name",
    "live_lesson_url",
    "facility_id",
    "img_file_name",
    "live_lesson_detail",
    "capacity",
    "reserve_max_count",
    "reserve_max_count_start_date",
    "reserve_start_day",
    "reserve_end_day",
    "reserve_end_time",
    "send_pc_chk",
    "send_mobile_chk",
    "valid_chk",
    "public_chk",
    "lesson_instructor_id",
    "sort_no",
    "item_ticket_price",
    "detail_tag_head",
    "detail_tag_body",
    "regist_user_id",
    "update_user_id",
    "regist_date",
    "update_date",
    "del_chk",
)

LIVE_LESSON_DATE_COLUMNS = (
    "live_lesson_date_id",
    "live_lesson_id",
    "date_type",
    "live_lesson_date_from",
    "live_lesson_date_to",
    "live_lesson_time",
    "capacity",
    "reserve_start_day",
    "reserve_end_day",
    "mail_send_chk",
    "regist_date",
    "update_date",
    "del_chk",
)

CONFIG_COLUMNS = ("tenant_id", "valid_chk", "ticket_cancel_chk", "ticket_cancel_day", "ticket_cancel_time")

#: 旧 `live_lesson_type`。`LiveLessonController::$liveLessonTypeList`
LESSON_TYPES = {0: "オンラインレッスン", 1: "教室レッスン"}


def occurrences(ctx: RunContext) -> list[dict]:
    """開催回を読む。**削除済みも移す**（`deleted_at` で表す）。"""
    return ctx.require_source().fetch_for_tenant("live_lesson_date", LIVE_LESSON_DATE_COLUMNS)


def _representative_starts_at(rows: list[dict], now) -> object:
    """代表日時。**直近の開催予定日、無ければ最後の回**（2026-09-24 決定）。

    `live_lessons.scheduled_at` は NOT NULL。開催回の本体は
    `live_lesson_occurrences` 側で、この列は一覧の表示用。
    """
    alive = [r for r in rows if int(r.get("del_chk") or 0) == 0]
    pool = alive or rows
    if not pool:
        return None
    future = [r for r in pool if r["live_lesson_date_from"] and r["live_lesson_date_from"] >= now]
    if future:
        return min(r["live_lesson_date_from"] for r in future)
    return max(r["live_lesson_date_from"] for r in pool if r["live_lesson_date_from"])


class LiveLessonsStep(Step):
    """`live_lesson` を `lessons`(type=live) + `live_lessons` に移す。

    `lessons` と `live_lessons` は**別テーブルだが1対1**。`live_lessons.lesson_id` が
    `lessons.id` への FK なので、`lessons` を先に入れる。
    """

    name = "content.live_lessons"
    description = "ライブをレッスン（type=live）として移す"
    source_table = "live_lesson"
    target_table = "lessons"
    depends_on = ("content.live_host_course",)

    def extract(self, ctx: RunContext) -> list[dict]:
        source = ctx.require_source()
        lives = source.fetch_for_tenant("live_lesson", LIVE_LESSON_COLUMNS)
        placement = resolve_placement(ctx)
        by_live: dict[int, list[dict]] = {}
        for row in occurrences(ctx):
            by_live.setdefault(int(row["live_lesson_id"]), []).append(row)
        for live in lives:
            live["_course"] = placement.get(int(live["live_lesson_id"]))
            live["_dates"] = by_live.get(int(live["live_lesson_id"]), [])
        return lives

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        records: list[Record] = []
        for row in rows:
            records.append(
                Record(
                    table="lessons",
                    values={
                        "id": ctx.ulid.for_row("live_lesson", row["live_lesson_id"]),
                        "tenant_id": tenant_id,
                        # **`lessons.legacy_id` には入れない。** オンデマンドの
                        # `unit.unit_id` と衝突する（実測 18件中11件）
                        "legacy_id": None,
                        "course_id": course_for(ctx, row["_course"]),
                        "title": row.get("live_lesson_name") or "",
                        "description": row.get("live_lesson_detail"),
                        "type": "live",
                        "status": _status(row),
                        "sort_order": int(row.get("sort_no") or 0),
                        "is_preview": False,
                        "created_at": convert(row.get("regist_date"), ColumnKind.TIMESTAMP),
                    },
                    natural_key=("id",),
                    source_key=int(row["live_lesson_id"]),
                )
            )
        return records


class LiveLessonDetailsStep(Step):
    """`live_lessons`（レッスンの子）に代表日時と旧設定を入れる。"""

    name = "content.live_lesson_details"
    description = "ライブの代表日時と旧設定を移す"
    source_table = "live_lesson"
    target_table = "live_lessons"
    depends_on = ("content.live_lessons",)
    # 代表日時は「実行した時点で直近の回」。開催日を過ぎるたびに変わる
    volatile_columns = ("scheduled_at",)

    def extract(self, ctx: RunContext) -> list[dict]:
        return LiveLessonsStep().extract(ctx)

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        from datetime import datetime

        tenant_id = ctx.tenant_id.value
        now = datetime.now()
        records: list[Record] = []
        without_dates = 0
        for row in rows:
            scheduled = _representative_starts_at(row["_dates"], now)
            if scheduled is None:
                without_dates += 1
            records.append(
                Record(
                    table="live_lessons",
                    values={
                        "lesson_id": ctx.ulid.for_row("live_lesson", row["live_lesson_id"]),
                        "tenant_id": tenant_id,
                        "legacy_id": int(row["live_lesson_id"]),
                        # **NOT NULL。** 開催回が1件も無いライブはここで弾かれて一覧に出る
                        "scheduled_at": convert(scheduled, ColumnKind.TIMESTAMP),
                        # LiveKit のルーム。旧に対応概念が無い（`live_lesson_url` は会議 URL）
                        "live_room_id": None,
                        "settings": _settings(row),
                    },
                    natural_key=("lesson_id",),
                    source_key=int(row["live_lesson_id"]),
                )
            )
        if without_dates:
            ctx.logger.warning(
                "開催回が1件も無いライブが %d 件ある。`scheduled_at` は NOT NULL なので移らない",
                without_dates,
            )
        return records


def _status(row: dict) -> str:
    """**`del_chk` を `valid_chk` より優先する。**"""
    if int(row.get("del_chk") or 0) == 1:
        return "deleted"
    return "published" if int(row.get("valid_chk") or 0) == 1 else "draft"


def _settings(row: dict) -> str:
    """新環境に受け皿が無い列をまとめて残す。

    **レッスン側の予約既定値も生値で残す。** 開催回へ展開したあと、元が何だったかを
    追えるようにするため。**会場（施設）もここ** — `facility` は集合研修（X01）で
    対象外だが、教室レッスンの開催場所が消えると困る。
    """
    return json.dumps(
        {
            "live_lesson_type": row.get("live_lesson_type"),
            "live_lesson_type_name": LESSON_TYPES.get(int(row.get("live_lesson_type") or 0)),
            "facility_id": row.get("facility_id"),
            "reserve_max_count": row.get("reserve_max_count"),
            "reserve_max_count_start_date": str(row.get("reserve_max_count_start_date") or "") or None,
            "detail_tag_head": row.get("detail_tag_head"),
            "detail_tag_body": row.get("detail_tag_body"),
            "send_pc_chk": bool(int(row.get("send_pc_chk") or 0)),
            "send_mobile_chk": bool(int(row.get("send_mobile_chk") or 0)),
            "public_chk": bool(int(row.get("public_chk") or 0)),
            "img_file_name": row.get("img_file_name"),
            "regist_user_id": row.get("regist_user_id"),
            "update_user_id": row.get("update_user_id"),
            # **元の講師。** courses.instructor_id は講座単位なので、案によっては畳まれる
            "lesson_instructor_id": row.get("lesson_instructor_id"),
            # レッスン側の予約既定値（開催回側が優先。単位は「何日前」の int）
            "defaults": {
                "capacity": row.get("capacity"),
                "reserve_start_day": row.get("reserve_start_day"),
                "reserve_end_day": row.get("reserve_end_day"),
                "reserve_end_time": row.get("reserve_end_time"),
            },
        },
        ensure_ascii=False,
    )


class OccurrencesStep(Step):
    """`live_lesson_date` を `live_lesson_occurrences` に移す。

    **`del_chk` を `canceled_at` に写さない。** 削除と中止は別で、混ぜると受講者の履歴に
    「中止された」と見える。削除は `deleted_at`（A5 で追加）、中止は予約の `stop_chk` から作る。
    """

    name = "content.live_occurrences"
    description = "開催回を移す（削除は deleted_at、中止は予約から）"
    source_table = "live_lesson_date"
    target_table = "live_lesson_occurrences"
    depends_on = ("content.live_lesson_details",)

    def extract(self, ctx: RunContext) -> list[dict]:
        source = ctx.require_source()
        rows = occurrences(ctx)
        lives = {
            int(r["live_lesson_id"]): r
            for r in source.fetch_for_tenant("live_lesson", LIVE_LESSON_COLUMNS)
        }
        config = source.fetch_for_tenant("config_live_lesson", CONFIG_COLUMNS)
        cancel = config[0] if config else {}
        # 中止になった開催回は、予約側の stop_chk から拾う
        stopped = {
            int(r["live_lesson_date_id"])
            for r in source.fetch_for_tenant(
                "live_lesson_reserve",
                ("live_lesson_date_id", "stop_chk", "update_date"),
                where="stop_chk = 1",
            )
        }
        out: list[dict] = []
        for row in rows:
            live = lives.get(int(row["live_lesson_id"]))
            if live is None:
                continue  # 孤児。親のライブが物理削除されている
            out.append(
                {
                    **row,
                    "_live": live,
                    "_cancel": cancel,
                    "_stopped": int(row["live_lesson_date_id"]) in stopped,
                }
            )
        return out

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        from datetime import timedelta

        tenant_id = ctx.tenant_id.value
        records: list[Record] = []
        for row in rows:
            live, cancel = row["_live"], row["_cancel"]
            starts = row["live_lesson_date_from"]
            records.append(
                Record(
                    table="live_lesson_occurrences",
                    values={
                        "id": ctx.ulid.for_row("live_lesson_date", row["live_lesson_date_id"]),
                        "tenant_id": tenant_id,
                        "lesson_id": ctx.ulid.for_row("live_lesson", row["live_lesson_id"]),
                        # **datetime(3)。** セッション TZ の変換が効かないので UTC を明示的に書く
                        "starts_at": convert(starts, ColumnKind.DATETIME),
                        "ends_at": convert(row["live_lesson_date_to"], ColumnKind.DATETIME),
                        "capacity": _capacity(row, live),
                        # **date → datetime(3)。** JST の 00:00 を補ってから UTC に直す。
                        # 素で入れると前日15:00 になり、予約開始が1日早まる
                        "reserve_opens_at": convert_date(
                            row.get("reserve_start_day"), ColumnKind.DATETIME, DateBoundary.START
                        ),
                        "reserve_closes_at": convert(row.get("reserve_end_day"), ColumnKind.DATETIME),
                        "cancel_closes_at": _cancel_closes_at(starts, cancel, timedelta),
                        # レッスン側の1つの URL を全開催回に複製する
                        "meeting_url": _text(live.get("live_lesson_url")),
                        "recording_url": None,
                        "recording_published": False,
                        # **中止は予約の stop_chk から。** del_chk ではない
                        "canceled_at": (
                            convert(row.get("update_date"), ColumnKind.DATETIME)
                            if row["_stopped"]
                            else None
                        ),
                        # **削除は canceled_at と別の軸**（A5）
                        "deleted_at": (
                            convert(row.get("update_date"), ColumnKind.DATETIME)
                            if int(row.get("del_chk") or 0) == 1
                            else None
                        ),
                        "remind_enabled": bool(int(row.get("mail_send_chk") or 0)),
                        "settings": json.dumps(
                            {
                                "date_type": row.get("date_type"),
                                "live_lesson_time": row.get("live_lesson_time"),
                            },
                            ensure_ascii=False,
                        ),
                        "created_at": convert(row.get("regist_date"), ColumnKind.DATETIME),
                    },
                    natural_key=("id",),
                    source_key=int(row["live_lesson_date_id"]),
                )
            )
        return records


def _capacity(row: dict, live: dict) -> int | None:
    """**開催回の値が優先、無ければレッスン側。** `0` は CHECK に当たるので NULL に倒す。"""
    for value in (row.get("capacity"), live.get("capacity")):
        if value is None:
            continue
        number = int(value)
        return number if number > 0 else None
    return None


def _cancel_closes_at(starts, cancel: dict, timedelta):
    """キャンセル期限。**旧に対応列が無く、テナント設定から計算する。**

    `starts_at − ticket_cancel_day 日 − ticket_cancel_time 時間`。
    キャンセル不可（`ticket_cancel_chk = 0`）なら開始時刻を入れる（それ以降は取り消せない）。
    """
    if starts is None or not cancel:
        return None
    if not int(cancel.get("ticket_cancel_chk") or 0):
        return convert(starts, ColumnKind.DATETIME)
    days = int(cancel.get("ticket_cancel_day") or 0)
    hours = int(cancel.get("ticket_cancel_time") or 0)
    return convert(starts - timedelta(days=days, hours=hours), ColumnKind.DATETIME)


def _text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def build() -> list[Step]:
    return [LiveLessonsStep(), LiveLessonDetailsStep(), OccurrencesStep()]
