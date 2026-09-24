"""live.5 / live.6 / live.7 — チケットと予約。

**残高1行 = 付与1行。** lw2 の `user_ticket.ticket_num` は**すでに引かれたあとの残高**で、
「何枚配って何枚使ったか」を持たない。`quantity` と `remaining_quantity` に同じ値を入れる。

**消費の台帳行は移行時に作る**（2026-09-24 決定）。lw2 の `user_ticket_log` は
`grant_id` も符号も持たず再生できないが、**台帳が空だとキャンセルしてもチケットが戻らない**
（`RefundForReservation` が `ticket_ledger_entries` から引いた枚数を読む）。
席を占める予約に対して `consumed` を1行作る。**`remaining_quantity` は減らさない** —
旧の残高が既に引かれたあとの値なので、引くと二重に減る。
"""

from __future__ import annotations

import json

from ...context import RunContext
from ...core.datetimes import ColumnKind, DateBoundary, convert, convert_date
from ...core.records import Record
from ..base import Step

TICKET_COLUMNS = ("ticket_id", "ticket_type", "ticket_name", "del_chk", "regist_date")
TICKET_LIMIT_COLUMNS = ("ticket_id", "live_lesson_id", "del_chk", "regist_date")
USER_TICKET_COLUMNS = (
    "user_id",
    "ticket_id",
    "ticket_num",
    "ticket_start_date",
    "ticket_end_date",
    "authority_id",
    "regist_date",
)
RESERVE_COLUMNS = (
    "live_lesson_reserve_id",
    "live_lesson_date_id",
    "user_id",
    "reserve_date",
    "cancel_chk",
    "cancel_date",
    "attendance_chk",
    "attendance_date",
    "verification_key",
    "recent_access_date",
    "stop_chk",
    "change_reserve_id",
    "base_reserve_id",
    "regist_date",
    "update_date",
)

#: チケットを保持したままの status。**`live_reservation_statuses.occupies_seat = 1` と揃える**
#: （`reserved` / `attended` / `no_show`）。**欠席でもチケットは消費済み** — lw2 は予約時に
#: 引き、来なくても戻さない。`canceled` と `host_canceled` は席を解放するので対象外
HOLDS_SEAT = frozenset({"reserved", "attended", "no_show"})


def _live_ulid(ctx: RunContext, live_lesson_id: object) -> str:
    return ctx.ulid.for_row("live_lesson", int(live_lesson_id))


def _grant_ulid(ctx: RunContext, row: dict) -> str:
    """**旧 `user_ticket` に単一の主キーが無い。** 旧 UNIQUE の3列から採番する。"""
    return ctx.ulid.for_row(
        "user_ticket",
        f"{int(row['user_id'])}:{row.get('ticket_id')}:{row.get('authority_id')}",
    )


class TicketTypesStep(Step):
    """`ticket` を `ticket_types` に移す。"""

    name = "billing.ticket_types"
    description = "チケットの種別を移す"
    source_table = "ticket"
    target_table = "ticket_types"
    depends_on = ("content.live_lessons",)

    def extract(self, ctx: RunContext) -> list[dict]:
        rows = ctx.require_source().fetch_for_tenant("ticket", TICKET_COLUMNS)
        names = [r.get("ticket_name") for r in rows]
        if len(set(names)) != len(names):
            ctx.logger.warning(
                "同じ名前のチケット種別がある: %s。**`name` に UNIQUE は無いので投入は止まらない**が、"
                "運営画面で区別が付かない",
                sorted({n for n in names if names.count(n) > 1}),
            )
        return rows

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        return [
            Record(
                table="ticket_types",
                values={
                    "id": ctx.ulid.for_row("ticket", row["ticket_id"]),
                    "tenant_id": tenant_id,
                    "legacy_id": int(row["ticket_id"]),
                    # **`user_ticket_log.ticket_type` が参照しているのはこの値**
                    # （`ticket_id` ではない）。履歴を移さなくても後から突き合わせられるよう残す
                    "legacy_type": row.get("ticket_type"),
                    "name": row.get("ticket_name") or "",
                    "description": None,
                    "refund_deadline_days": None,  # 旧に対応なし
                    "active": int(row.get("del_chk") or 0) == 0,
                    "deprecated_at": (
                        convert(row.get("regist_date"), ColumnKind.DATETIME)
                        if int(row.get("del_chk") or 0) == 1
                        else None
                    ),
                    "created_at": convert(row.get("regist_date"), ColumnKind.DATETIME),
                },
                natural_key=("tenant_id", "legacy_id"),
                source_key=int(row["ticket_id"]),
            )
            for row in rows
        ]


def _ticket_limits(ctx: RunContext) -> list[dict]:
    """**`del_chk = 0` の行だけ。** 中間表なので、行の不在で「割当が無い」を表す。"""
    return ctx.require_source().fetch_joined(
        "ticket_limit_lesson",
        TICKET_LIMIT_COLUMNS,
        parent="ticket",
        on="c.ticket_id = p.ticket_id",
        where="c.del_chk = 0",
    )


class TicketTypeLessonsStep(Step):
    """`ticket_limit_lesson` を `ticket_type_lessons` に移す。"""

    name = "billing.ticket_type_lessons"
    description = "チケット種別が使えるライブを移す"
    source_table = "ticket_limit_lesson"
    target_table = "ticket_type_lessons"
    depends_on = ("billing.ticket_types",)

    def extract(self, ctx: RunContext) -> list[dict]:
        return _ticket_limits(ctx)

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        return [
            Record(
                table="ticket_type_lessons",
                values={
                    "ticket_type_id": ctx.ulid.for_row("ticket", row["ticket_id"]),
                    # **参照先は `lessons`**（`live_lessons` ではない）
                    "lesson_id": _live_ulid(ctx, row["live_lesson_id"]),
                    "tenant_id": tenant_id,
                    "created_at": convert(row.get("regist_date"), ColumnKind.DATETIME),
                },
                natural_key=("ticket_type_id", "lesson_id"),
                source_key=int(row["live_lesson_id"]),
            )
            for row in rows
        ]


class TicketRequirementsStep(Step):
    """`live_lesson.item_ticket_price` を `live_lesson_ticket_requirements` に移す。

    **`item_ticket_price = 0` は行を作らない**（`chk_lltr_cost (cost >= 1)` に当たるため）。
    行が無い = チケット不要。

    **種別は `ticket_limit_lesson` から逆引きする。** 旧はライブ側に種別を持たないので、
    引けないライブは行を作れない（ステージング実測で3件中1件）。
    """

    name = "billing.ticket_requirements"
    description = "ライブ1件あたりの必要枚数を移す"
    source_table = "live_lesson"
    target_table = "live_lesson_ticket_requirements"
    depends_on = ("billing.ticket_type_lessons",)

    def extract(self, ctx: RunContext) -> list[dict]:
        source = ctx.require_source()
        lives = [
            r
            for r in source.fetch_for_tenant(
                "live_lesson", ("live_lesson_id", "item_ticket_price")
            )
            if int(r.get("item_ticket_price") or 0) > 0
        ]
        by_live: dict[int, int] = {}
        for row in _ticket_limits(ctx):
            by_live.setdefault(int(row["live_lesson_id"]), int(row["ticket_id"]))
        out, unresolved = [], []
        for live in lives:
            ticket = by_live.get(int(live["live_lesson_id"]))
            if ticket is None:
                unresolved.append(int(live["live_lesson_id"]))
                continue
            out.append({**live, "_ticket_id": ticket})
        if unresolved:
            ctx.logger.warning(
                "チケットが要るのに種別を引けないライブが %d 件ある（旧 live_lesson_id=%s）。"
                "**`ticket_limit_lesson` に行が無い**ので、チケット不要として移る",
                len(unresolved),
                unresolved,
            )
        return out

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        return [
            Record(
                table="live_lesson_ticket_requirements",
                values={
                    "lesson_id": _live_ulid(ctx, row["live_lesson_id"]),
                    "tenant_id": tenant_id,
                    "ticket_type_id": ctx.ulid.for_row("ticket", row["_ticket_id"]),
                    "cost": int(row["item_ticket_price"]),
                },
                natural_key=("lesson_id",),
                source_key=int(row["live_lesson_id"]),
            )
            for row in rows
        ]


def reservations(ctx: RunContext) -> list[dict]:
    """予約を読み、開催回とライブを添える。"""
    source = ctx.require_source()
    dates = {
        int(r["live_lesson_date_id"]): r
        for r in source.fetch_for_tenant(
            "live_lesson_date", ("live_lesson_date_id", "live_lesson_id", "live_lesson_date_from")
        )
    }
    rows: list[dict] = []
    for row in source.fetch_for_tenant("live_lesson_reserve", RESERVE_COLUMNS):
        date = dates.get(int(row["live_lesson_date_id"]))
        if date is None:
            continue  # 孤児。開催回が物理削除されている
        rows.append({**row, "_date": date})
    return rows


class ReservationsStep(Step):
    """`live_lesson_reserve` を `live_reservations` に移す。

    **3フラグを `status` に畳むが、元の値は `settings` に残す。**

    - `stop_chk = 1` … 開催側の中止。**`canceled`（受講者都合）と混ぜない**ので `host_canceled`
    - `cancel_chk = 1` … 受講者がキャンセル
    - `attendance_chk = 1` … 出席
    - いずれでもなく開催回が過去 … `no_show`、未来 … `reserved`

    **重複はツールが畳まない。** `UNIQUE (occurrence_id, user_id)` に当たる組は
    どれも移さず一覧に出る（[共通仕様 3.5.1](../../../docs/migration-spec.md)）。
    ステージング実測で4組8行。
    """

    name = "enrollment.live_reservations"
    description = "予約を移す（3フラグを status に畳む）"
    source_table = "live_lesson_reserve"
    target_table = "live_reservations"
    depends_on = ("content.live_occurrences",)

    def extract(self, ctx: RunContext) -> list[dict]:
        return reservations(ctx)

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        from datetime import datetime

        tenant_id = ctx.tenant_id.value
        now = datetime.now()
        records: list[Record] = []
        for row in rows:
            starts = row["_date"].get("live_lesson_date_from")
            records.append(
                Record(
                    table="live_reservations",
                    values={
                        "id": ctx.ulid.for_row(
                            "live_lesson_reserve", row["live_lesson_reserve_id"]
                        ),
                        "tenant_id": tenant_id,
                        "occurrence_id": ctx.ulid.for_row(
                            "live_lesson_date", row["live_lesson_date_id"]
                        ),
                        "user_id": ctx.ulid.for_row("user", row["user_id"]),
                        "status": _status(row, starts, now),
                        # **NOT NULL（既定値あり）。** NULL を渡すと既定値は効かず違反になる
                        "reserved_at": convert(row.get("reserve_date"), ColumnKind.DATETIME),
                        "canceled_at": convert(row.get("cancel_date"), ColumnKind.DATETIME),
                        "attended_at": convert(row.get("attendance_date"), ColumnKind.DATETIME),
                        # **過去の開催回にリマインドは飛ばない**（バッチの窓が [now, now+24h)）。
                        # cutover 直前に始まる回は旧の送信ログを見て埋める（未実装）
                        "reminded_at": None,
                        "verification_key": row.get("verification_key") or None,
                        "settings": json.dumps(
                            {
                                "cancel_chk": int(row.get("cancel_chk") or 0),
                                "attendance_chk": row.get("attendance_chk"),
                                "stop_chk": int(row.get("stop_chk") or 0),
                                "recent_access_date": str(row.get("recent_access_date") or "")
                                or None,
                                "change_reserve_id": row.get("change_reserve_id"),
                                "base_reserve_id": row.get("base_reserve_id"),
                            },
                            ensure_ascii=False,
                        ),
                        "created_at": convert(row.get("regist_date"), ColumnKind.DATETIME),
                    },
                    natural_key=("occurrence_id", "user_id"),
                    source_key=int(row["live_lesson_reserve_id"]),
                )
            )
        return records


def _status(row: dict, starts, now) -> str:
    if int(row.get("stop_chk") or 0) == 1:
        return "host_canceled"
    if int(row.get("cancel_chk") or 0) == 1:
        return "canceled"
    if int(row.get("attendance_chk") or 0) == 1:
        return "attended"
    if starts is not None and starts < now:
        return "no_show"
    return "reserved"


class TicketGrantsStep(Step):
    """`user_ticket` を `ticket_grants` に移す。**残高1行 = 付与1行。**"""

    name = "billing.ticket_grants"
    description = "会員が持つチケット残高を移す"
    source_table = "user_ticket"
    target_table = "ticket_grants"
    depends_on = ("billing.ticket_requirements",)

    def extract(self, ctx: RunContext) -> list[dict]:
        return ctx.require_source().fetch_joined(
            "user_ticket", USER_TICKET_COLUMNS, parent="user", on="c.user_id = p.user_id"
        )

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        records: list[Record] = []
        for row in rows:
            quantity = int(row.get("ticket_num") or 0)
            records.append(
                Record(
                    table="ticket_grants",
                    values={
                        "id": _grant_ulid(ctx, row),
                        "tenant_id": tenant_id,
                        "user_id": ctx.ulid.for_row("user", row["user_id"]),
                        # **NOT NULL。** 種別が未設定の残高は移らない（実測 8件中3件）
                        "ticket_type_id": (
                            ctx.ulid.for_row("ticket", row["ticket_id"])
                            if row.get("ticket_id") is not None
                            else None
                        ),
                        # **旧は残高しか持たない。** 付与枚数と残枚数に同じ値を入れる。
                        # `chk_tg_qty (quantity >= 1)` に当たる 0 枚の行は移らない
                        "quantity": quantity,
                        "remaining_quantity": quantity,
                        # date → datetime。**終了日なので日の終わりを補う**
                        "expires_at": convert_date(
                            row.get("ticket_end_date"), ColumnKind.DATETIME, DateBoundary.END
                        ),
                        "starts_at": convert_date(
                            row.get("ticket_start_date"), ColumnKind.DATETIME, DateBoundary.START
                        ),
                        "source": "manual",
                        # 有料受講権限。参照先は課金区分（未移行）なので、いまは入れない
                        "source_ref": None,
                        "note": "lw2 移行時点の残高",
                        "granted_at": convert(row.get("regist_date"), ColumnKind.DATETIME),
                    },
                    natural_key=("id",),
                    source_key=f"{row['user_id']}:{row.get('ticket_id')}",
                )
            )
        return records


class TicketLedgerStep(Step):
    """席を占める予約に `consumed` の台帳行を作る（2026-09-24 決定）。

    **lw2 の `user_ticket_log` は再生しない。** `grant_id` も符号も持たないため。
    ここで作るのは**キャンセル時に戻す枚数を決めるための行**で、
    `RefundForReservation` が `ListByReservation` で読む。

    **`remaining_quantity` は減らさない。** 旧の残高が既に引かれたあとの値。
    """

    name = "billing.ticket_ledger"
    description = "予約が消費したチケットの台帳行を作る"
    source_table = "live_lesson_reserve"
    target_table = "ticket_ledger_entries"
    depends_on = ("billing.ticket_grants", "enrollment.live_reservations")

    def extract(self, ctx: RunContext) -> list[dict]:
        from datetime import datetime

        source = ctx.require_source()
        now = datetime.now()
        # ライブ → 必要枚数と種別
        need: dict[int, tuple[int, int]] = {}
        for row in TicketRequirementsStep().extract(ctx):
            need[int(row["live_lesson_id"])] = (
                int(row["item_ticket_price"]),
                int(row["_ticket_id"]),
            )
        # 会員 × 種別 → 付与（**使える付与だけ**。0枚の行は移らないので対象外）
        grants: dict[tuple[int, int], dict] = {}
        for row in source.fetch_joined(
            "user_ticket", USER_TICKET_COLUMNS, parent="user", on="c.user_id = p.user_id"
        ):
            if row.get("ticket_id") is None or int(row.get("ticket_num") or 0) < 1:
                continue
            grants.setdefault((int(row["user_id"]), int(row["ticket_id"])), row)

        out, unresolved = [], 0
        for res in reservations(ctx):
            starts = res["_date"].get("live_lesson_date_from")
            if _status(res, starts, now) not in HOLDS_SEAT:
                continue  # 席を占めていない予約はチケットを保持していない
            requirement = need.get(int(res["_date"]["live_lesson_id"]))
            if requirement is None:
                continue  # チケットの要らないライブ
            cost, ticket_id = requirement
            grant = grants.get((int(res["user_id"]), ticket_id))
            if grant is None:
                unresolved += 1
                continue
            out.append({**res, "_cost": cost, "_grant": grant})
        if unresolved:
            ctx.logger.warning(
                "チケットを使った予約 %d 件で、戻し先の付与が見つからない。"
                "**キャンセルしてもチケットが戻らない**（会員が使い切って `ticket_num = 0` の付与は移らないため）",
                unresolved,
            )
        return out

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        return [
            Record(
                table="ticket_ledger_entries",
                values={
                    "id": ctx.ulid.for_row(
                        "live_reserve_consumed", row["live_lesson_reserve_id"]
                    ),
                    "tenant_id": tenant_id,
                    "grant_id": _grant_ulid(ctx, row["_grant"]),
                    "user_id": ctx.ulid.for_row("user", row["user_id"]),
                    "kind": "consumed",
                    # **消費なので負。** `RefundForReservation` が -delta で戻す枚数を数える
                    "quantity_delta": -int(row["_cost"]),
                    "reservation_id": ctx.ulid.for_row(
                        "live_lesson_reserve", row["live_lesson_reserve_id"]
                    ),
                    "note": "lw2 移行時点の予約が保持している枚数",
                    "created_at": convert(row.get("reserve_date"), ColumnKind.DATETIME),
                },
                natural_key=("id",),
                source_key=int(row["live_lesson_reserve_id"]),
            )
            for row in rows
        ]


def definitions() -> list[Step]:
    """4-1 チケット（種別と必要枚数）。**予約より先**に入れる。"""
    return [TicketTypesStep(), TicketTypeLessonsStep(), TicketRequirementsStep()]


def reservations_steps() -> list[Step]:
    """3-6 ライブ予約。**チケット定義のあと、付与の前。**"""
    return [ReservationsStep()]


def grants() -> list[Step]:
    """4-1 チケット（付与と台帳）。**予約が入ってから**（台帳が予約を参照する）。"""
    return [TicketGrantsStep(), TicketLedgerStep()]
