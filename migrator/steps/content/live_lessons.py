"""content.4 — ライブ本体（旧 `live_lesson`）と開催回（旧 `live_lesson_date`）。

**`lessons.unit_id`（旧 ID）は使わない。** その列はオンデマンドが `unit.unit_id` で使っており、
ステージング実測で **18件中11件**がライブの ID と衝突する。旧 ID は
`live_lessons.live_lesson_id`（A1 で追加。旧 `legacy_id`）に持つ。

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
    # 配布ファイル（最大3本。ファイルの実体は L9 の移送で運ぶ）
    "save_file_name1",
    "disp_file_name1",
    "save_file_name2",
    "disp_file_name2",
    "save_file_name3",
    "disp_file_name3",
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


#: ライブのレッスンの並び順の始まり。ユニット（1 からの通し番号）より必ず後ろに来るようにする
LIVE_ORDER_BASE = 100000


def occurrences(ctx: RunContext) -> list[dict]:
    """開催回を読む（削除済みを含む。移すのは削除されていない回だけ → `OccurrencesStep`）。"""
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
        # 教室で行うライブの会場。**会場の表（`facility`）は対象外（06 X01）なので、
        # ID だけ残しても引けない。** 名前・住所・アクセスを文字列でライブの設定に残す
        venues = {int(f["facility_id"]): f for f in source.fetch_for_tenant("facility", FACILITY_COLUMNS)}
        for live in lives:
            live["_course"] = placement.get(int(live["live_lesson_id"]))
            live["_dates"] = by_live.get(int(live["live_lesson_id"]), [])
            live["_facility"] = venues.get(int(live.get("facility_id") or 0))
        return lives

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        records: list[Record] = []
        # **講座の中でユニットの後ろに、重ならない番号で並べる**（2026-10-26。02 の移行仕様 0-3 の Q4）。
        # ユニットは 1 からの通し番号（`lessons.course_order`）。旧はライブをユニットと別の画面に出していた
        by_course: dict[object, list[dict]] = {}
        for row in rows:
            by_course.setdefault(row["_course"], []).append(row)
        order: dict[int, int] = {}
        for lives in by_course.values():
            ranked = sorted(lives, key=lambda r: (int(r.get("sort_no") or 0), int(r["live_lesson_id"])))
            for number, live in enumerate(ranked, start=1):
                order[int(live["live_lesson_id"])] = LIVE_ORDER_BASE + number
        for row in rows:
            records.append(
                Record(
                    table="lessons",
                    values={
                        "id": ctx.ulid.for_row("live_lesson", row["live_lesson_id"]),
                        "tenant_id": tenant_id,
                        # **`lessons.unit_id` には入れない。** オンデマンドの
                        # `unit.unit_id` と衝突する（実測 18件中11件）
                        "unit_id": None,
                        "course_id": course_for(ctx, row["_course"]),
                        "title": row.get("live_lesson_name") or "",
                        "description": row.get("live_lesson_detail"),
                        "type": "live",
                        "status": _status(row),
                        # **新アプリはレッスンを `deleted_at IS NULL` で絞る**（school-launcher 20261021082002）
                        "deleted_at": (
                            convert(row.get("update_date"), ColumnKind.DATETIME)
                            if int(row.get("del_chk") or 0) == 1
                            else None
                        ),
                        "sort_order": order[int(row["live_lesson_id"])],
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
                        "live_lesson_id": int(row["live_lesson_id"]),
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


#: 会場（旧 `facility`）から残す列。画像・添付ファイルは L9 の移送待ち
FACILITY_COLUMNS = (
    "facility_id", "facility_name", "facility_url", "facility_access", "tel", "zip_code",
    "pref_id", "city_name", "address", "facility_detail",
)


def _facility(row: dict | None) -> dict | None:
    if not row:
        return None
    return {k: row.get(k) for k in FACILITY_COLUMNS if k != "facility_id" and row.get(k) not in (None, "")}


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
            # 会場の中身（会場の表は移さないので、ここに文字列で残す）
            "facility": _facility(row.get("_facility")),
            "reserve_max_count": row.get("reserve_max_count"),
            "reserve_max_count_start_date": str(row.get("reserve_max_count_start_date") or "") or None,
            "detail_tag_head": row.get("detail_tag_head"),
            "detail_tag_body": row.get("detail_tag_body"),
            "send_pc_chk": bool(int(row.get("send_pc_chk") or 0)),
            "send_mobile_chk": bool(int(row.get("send_mobile_chk") or 0)),
            "public_chk": bool(int(row.get("public_chk") or 0)),
            "img_file_name": row.get("img_file_name"),
            # 配布ファイル（並びを保つ。空の枠は詰める）
            "files": [
                {"slot": slot, "save_file_name": row.get(f"save_file_name{slot}"),
                 "disp_file_name": row.get(f"disp_file_name{slot}") or row.get(f"save_file_name{slot}")}
                for slot in (1, 2, 3)
                if (row.get(f"save_file_name{slot}") or "").strip()
            ],
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


class ReservationPoliciesStep(Step):
    """ライブごとの予約・キャンセルの期限を `live_lesson_reservation_policies` に移す（2026-10-22）。

    新システムは期限を「レッスン日の ○日前」でライブごとに持ち、開催回の日時はそこから計算し直す
    （school-launcher 20261013093100）。旧もライブごとに日数で持っていたので、そのまま入れる。

    - `reserve_start_day` → `reserve_open_days_before`（開始日の N 日前の 0:00）
    - `reserve_end_day` / `reserve_end_time` → `reserve_close_days_before` / `_hours_before`
      （`reserve_end_time` は「時間前」。旧 `LiveLessonModel.class.php:1262`）
    - キャンセルは**旧ではテナントに1つ**（`config_live_lesson`）。その値を各ライブに入れる（2026-10-22 決定）

    **キャンセルの期限を日数で表せないテナントは NULL にする**（警告を出す）。時間（`ticket_cancel_time`）が
    0 以外のとき、および**キャンセル不可（`ticket_cancel_chk = 0`）**のとき。新の NULL は「開始まで可」で、
    「不可」を表す値が無い。行ごと移さないと予約の期限まで落ちるので、行は入れる。開催回の
    `cancel_closes_at` は今までどおり旧の式で入っている。
    """

    name = "content.live_reservation_policies"
    description = "ライブごとの予約・キャンセルの期限を移す"
    source_table = "live_lesson"
    target_table = "live_lesson_reservation_policies"
    depends_on = ("content.live_lessons",)

    def extract(self, ctx: RunContext) -> list[dict]:
        source = ctx.require_source()
        rows = source.fetch_for_tenant("live_lesson", LIVE_LESSON_COLUMNS)
        config = source.fetch_for_tenant("config_live_lesson", CONFIG_COLUMNS)
        cancel = config[0] if config else {}
        for row in rows:
            row["_cancel"] = cancel
        return rows

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        records: list[Record] = []
        for row in rows:
            records.append(
                Record(
                    table="live_lesson_reservation_policies",
                    values={
                        "lesson_id": ctx.ulid.for_row("live_lesson", row["live_lesson_id"]),
                        "tenant_id": tenant_id,
                        "reserve_open_days_before": row.get("reserve_start_day"),
                        "reserve_close_days_before": row.get("reserve_end_day"),
                        "reserve_close_hours_before": row.get("reserve_end_time"),
                        "cancel_days_before": cancel_days_before(row["_cancel"]),
                    },
                    natural_key=("lesson_id",),
                    source_key=int(row["live_lesson_id"]),
                )
            )
        cancel = rows[0]["_cancel"] if rows else {}
        if rows and cancel and cancel_days_before(cancel) is None:
            ctx.logger.warning(
                "キャンセルの期限を日数で表せない（ticket_cancel_chk=%s / ticket_cancel_time=%s）。"
                "cancel_days_before は NULL（開始まで可）で入れる。開催回の cancel_closes_at は旧の式で入っている",
                cancel.get("ticket_cancel_chk"),
                cancel.get("ticket_cancel_time"),
            )
        return records


def cancel_days_before(cancel: dict) -> int | None:
    """テナントのキャンセルの設定を「開始日時の N 日前」にする。表せなければ None。"""
    if not cancel or not int(cancel.get("ticket_cancel_chk") or 0):
        return None
    if int(cancel.get("ticket_cancel_time") or 0) != 0:
        return None
    return int(cancel.get("ticket_cancel_day") or 0)


class OccurrencesStep(Step):
    """`live_lesson_date` を `live_lesson_occurrences` に移す。

    **開催回の親は `lessons`**（school-launcher 20260930013549 で `live_lessons` から付け替わった）。
    `live_lessons` の行が無いライブ（開催回が0件で代表日時が決まらないもの）にも開催回は入れられるが、
    そういうライブは開催回を持たないので、移す行は変わらない。

    **`del_chk` を `canceled_at` に写さない。** 削除と中止は別で、混ぜると受講者の履歴に
    「中止された」と見える。中止は予約の `stop_chk` から作る。

    **削除済みの開催回は移さない**（2026-10-26 決定。02 の移行仕様 0-3 の Q14）。新は開催回の
    `deleted_at` を読まず、削除済みの回もカレンダー・予約・リマインドに出す。ステージングの
    削除済み 817 件はすべて過去の回。その回の予約は外部キーで連鎖して一覧に出る。
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
                # 孤児。親のライブが物理削除されている（開催回は tenant_id を持つ）
                self.drop("live_lesson_occurrences", row["live_lesson_date_id"], "旧データの不整合",
                          f"ライブ（live_lesson_id={row['live_lesson_id']}）が物理削除されている")
                continue
            if int(row.get("del_chk") or 0) == 1:
                self.drop("live_lesson_occurrences", row["live_lesson_date_id"], "移行対象外",
                          "削除済みの開催回（新は deleted_at を読まず、カレンダーと予約に出る。2026-10-26 決定）")
                continue
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
                        # 削除済みの回は移さない（extract で一覧に出した）
                        "deleted_at": None,
                        # **旧に開催回ごとのリマインドの止め方は無い**（`mail_send_chk` は「送信済み」の印で、
                        # 予約の `reminded_at` に移す）。旧のバッチは、削除済みでない回のうち、
                        # ライブが削除済みでなく有効（`valid_chk = 1`）なものに送っていた。削除・無効は
                        # 回やライブの状態（`deleted_at` / `status`）に移しているので、ここでは止めない
                        "remind_enabled": True,
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
    return [LiveLessonsStep(), LiveLessonDetailsStep(), ReservationPoliciesStep(), OccurrencesStep()]
