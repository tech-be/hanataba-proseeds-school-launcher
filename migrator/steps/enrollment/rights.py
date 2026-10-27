"""enrollment.1 — 受講権限。

`payment_item_lesson_authority` → `enrollments`。

**粒度が違う。** 旧は商品×講座で、同じ商品が複数講座を売り、同じ講座が複数商品から
売られる。実測 6,966 行が 4,289 組に重なる。**lw2 自身が `GROUP BY user_id, lesson_id`
で畳み、期限に `MAX()` を取っている**（`LessonModel::1804`）ので、同じ規則で寄せる。

**商品に紐づかない権限がある。** 実測 3,282行（2,306組）が `item_id` / `application_id`
ともに NULL で、`authority_key` も空。購入を経ずに直接入った付与で、
**商品で絞ると丸ごと落ちる**。`source` を `admin` にして移す。

**`cancel_chk` は使わない。** 名前に反して取り消しではなく、**毎月の自動延長の対象から外す印**。
買い切りなどは作成時から 1 で、自動継続は解約されると毎日のバッチ（`AuthorityCheckBatch` の
`updateCancelChk`）が 1 にする。受講できるかは期限で決まり（`LessonModel::1363`）、この列は見ない。
実測（全行）1=3,116 / 0=3,850 で、`item_id` のある行に限ると 1=3,064 / 0=620。
**実質の取り消しは `del_chk`**（実測 828件）。

**自動継続も期限で切れる。** 旧の毎日のバッチが、`cancel_chk = 0` で前日に期限が切れた権限を
1か月延ばす（`PaymentAuthorityModel::updateAuthrityExtendList`）。期限の列には
「いま払っている1か月の終わり」が入っているので、そのまま写す（2026-10-23）。

**無料講座は移らない。** lw2 の受講可否は「権限がある **OR** その講座が有料ユニットを
持たない」の2分岐で（`LessonModel::1363`）、実測 235講座のうち権限が要るのは 71件だけ。
残り164件は権限行を持たないのが正常なので、ここでは作らない
（cutover 後の扱いは [確認事項 E3](../../../docs/db/open-questions.md)）。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime

from ...context import RunContext
from ...core.datetimes import ColumnKind, DateBoundary, convert, convert_date, is_zero_date
from ...core.records import Record
from ..base import Step

#: MySQL の `TIMESTAMP` が持てる上限（UTC）。`enrollments.expires_at` がこの型。
#: **旧は「無期限」を100年後の日付で表しており**（実測 2124-06-24 など）、
#: そのまま入れると実 INSERT で `Incorrect datetime value` になる
TIMESTAMP_MAX = datetime(2038, 1, 19, 3, 14, 7)

AUTHORITY_COLUMNS = (
    "authority_id",
    "authority_key",
    "user_id",
    "item_id",
    "application_id",
    "lesson_id",
    "authority_start_date",
    "authority_end_date",
    "payment_authority_end_date",
    "cancel_chk",
    "no_limit_chk",
    "payment_no_limit_chk",
    "remote_chk",
    "del_chk",
)


class EnrollmentRightsStep(Step):
    """`payment_item_lesson_authority` を `enrollments` に移す（→ A8）。"""

    name = "enrollment.rights"
    description = "購入で得た講座の受講権限を移す"
    source_table = "payment_item_lesson_authority"
    target_table = "enrollments"
    depends_on = ("users", "content.courses")

    def extract(self, ctx: RunContext) -> list[dict]:
        # 商品のモード（`payment_item.is_auto_extension`）と申込の解約状態
        # （`payment_application.is_cancel`）を添える。期限はほかと同じに写し、
        # 自動継続だったことと、全部解約済みかを決めるのに使う。
        #
        # **`tenant_id` を持たない。絞るのは会員側。** 商品で絞ると
        # **`item_id` が NULL の権限（実測 3,282行 / 2,306組）が丸ごと落ちる**。
        # 購入を経ずに直接入った付与で、`authority_key` も `application_id` も空だが、
        # 開始日・終了日は入っていて lw2 の受講可否判定は他と同じに扱う
        # （`LessonModel::1804` は `item_id` を見ない）。商品は LEFT JOIN で添える。
        cols = ", ".join(f"c.`{name}`" for name in AUTHORITY_COLUMNS)
        sql = (
            f"SELECT {cols}, "
            "p.`is_auto_extension` AS _auto_extension, "
            "pa.`is_cancel` AS _is_cancel, "
            "pa.`payment_type` AS _payment_type, "
            "pa.`application_result` AS _application_result, "
            "pa.`cancel_date_time` AS _cancel_date_time "
            "FROM `payment_item_lesson_authority` AS c "
            "INNER JOIN `user` AS u ON u.user_id = c.user_id "
            "LEFT JOIN `payment_item` AS p ON c.item_id = p.item_id "
            "LEFT JOIN `payment_application` AS pa ON pa.application_id = c.application_id "
            "WHERE u.tenant_id = %s"
        )
        self._completions = completions(_fetch_completions(ctx))
        from ..billing.payments import payers

        self._payers = payers(ctx)
        return ctx.require_source().fetch(
            "payment_item_lesson_authority", sql, (ctx.config.tenant.legacy_id,)
        )

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        # **(会員, 講座) で畳む。** lw2 の受講可否判定と同じ粒度
        groups: dict[tuple[int, int], list[dict]] = {}
        for row in rows:
            key = (int(row["user_id"]), int(row["lesson_id"]))
            groups.setdefault(key, []).append(row)

        records: list[Record] = []
        for key, members in sorted(groups.items()):
            records.append(self._fold(ctx, tenant_id, key, members))
        return records

    def _fold(
        self, ctx: RunContext, tenant_id: str, key: tuple[int, int], members: list[dict]
    ) -> Record:
        """同じ (会員, 講座) の複数行を1行に畳む。"""
        user_id, lesson_id = key
        period = fold_period(members, ColumnKind.TIMESTAMP)
        expires_at = period.expires_at

        status = status_of(period)

        return Record(
            table="enrollments",
            values={
                "id": ctx.ulid.for_row("payment_item_lesson_authority", f"{user_id}:{lesson_id}"),
                "tenant_id": tenant_id,
                "user_id": ctx.ulid.for_row("user", user_id),
                "course_id": ctx.ulid.for_row("lesson", lesson_id),
                # **商品を経ていない権限は `admin`。** `enrollment_sources` の
                # `admin`（管理者付与、`is_paid = FALSE`）が対応する。購入由来と
                # 混ぜると売上集計に乗ってしまう
                "source": "purchase" if _has_item(members) else "admin",
                "status": status,
                # **畳んだので最も早い開始日を採る。** 権限が続いていた期間の起点
                "enrolled_at": period.enrolled_at,
                "expires_at": expires_at,
                # **旧の講座の修了日**（`user_learning_lesson.lesson_complete_date`）。旧の画面と修了証は
                # この日で修了を判定していた。新の規則（全レッスンの完了）で計算し直すと、資料を含む
                # 講座で修了が消える（03 移行仕様 0-2 Q1）
                "completed_at": getattr(self, "_completions", {}).get(key),
                # **決済と結ぶ値**（課金 04 の暫定の規則 P10）。返金で受講を取り消す処理と、
                # 修了証の金額印字がこの値で決済を引く（外部キーではない）
                "provider_payment_id": _payment_of(members, getattr(self, "_payers", None)),
                "subscription_id": None,
                # **商品を経た権限はコースの購入で作った受講登録**（2026-10-22。school-launcher
                # 20261012174140）。新はこの受講登録に講座ごとのリモートPC 対象を効かせず、
                # コースの購入（`learning_path_enrollments.remote_pc_enabled`）とコースの設定で決める。
                # 旧の判定（権限の `remote_chk` AND 商品の `remote_chk`）と同じになる
                "via_learning_path": _has_item(members),
                "settings": _settings(members, period.unlimited, period.beyond_range, period.subscribed),
            },
            natural_key=("tenant_id", "user_id", "course_id"),
            source_key=f"{user_id}:{lesson_id}",
        )


def status_of(period: "Period") -> str:
    """**`enrollment_statuses` は active / expired / refunded / revoked。**

    `canceled` という値は無い（`revoked` を A8 の migration で足してある）。
    """
    if period.ended is not None:
        # 全部消えている、または自動継続の商品なのに全部解約済み（期限ではなく解約で終わっている）
        return "revoked"
    if period.expires_at is not None and period.expires_at < _now():
        # 期限切れ。実測で 4,289組中 3,381組が該当する（active 534 / revoked 374）
        return "expired"
    return "active"


def _fetch_completions(ctx: RunContext) -> list[dict]:
    """削除されていない受講の行の修了日と、その日のユニットの完了日時。**旧は削除した受講の行を見ない。**"""
    sql = (
        "SELECT ull.`user_id`, ull.`lesson_id`, ull.`lesson_complete_date`, ulu.`complete_date` "
        "FROM `user_learning_lesson` AS ull "
        "INNER JOIN `user` AS u ON u.user_id = ull.user_id "
        "LEFT JOIN `user_learning_unit` AS ulu ON ulu.user_learning_lesson_id = ull.user_learning_lesson_id "
        "AND DATE(ulu.complete_date) = ull.lesson_complete_date "
        "WHERE u.tenant_id = %s AND ull.del_chk = 0 AND ull.lesson_complete_date IS NOT NULL"
    )
    return ctx.require_source().fetch("user_learning_lesson", sql, (ctx.config.tenant.legacy_id,))


def completions(rows: list[dict]) -> dict[tuple[int, int], datetime]:
    """(会員, 講座) → 修了日時（UTC）。

    修了日は DATE なので、**時刻はその日の最後のユニットの完了日時**を使い、無ければその日の 0 時（JST）。
    受講の行が複数あれば最も新しい修了日。受講開始より前の修了日（権限の付け直し）も作り替えない（Q2）。
    """
    days: dict[tuple[int, int], date] = {}
    times: dict[tuple[int, int, date], datetime] = {}
    for row in rows:
        day = row.get("lesson_complete_date")
        if day is None or is_zero_date(day):
            continue
        day = day.date() if isinstance(day, datetime) else day
        key = (int(row["user_id"]), int(row["lesson_id"]))
        days[key] = max(days.get(key, day), day)
        done = row.get("complete_date")
        if isinstance(done, datetime) and done.date() == day:
            slot = (*key, day)
            times[slot] = max(times.get(slot, done), done)
    out: dict[tuple[int, int], datetime] = {}
    for key, day in days.items():
        done = times.get((*key, day))
        out[key] = (convert(done, ColumnKind.TIMESTAMP) if done is not None
                    else convert_date(day, ColumnKind.TIMESTAMP, DateBoundary.START))
    return out


@dataclass(frozen=True)
class Period:
    """権限の行（畳む単位ぶん）から決めた、受講できる期間と終わり方。"""

    enrolled_at: datetime | None
    expires_at: datetime | None
    #: 無期限（無期限の印、列の上限を超える期限）
    unlimited: bool
    #: `TIMESTAMP` の上限を超えたので NULL に寄せた元の期限
    beyond_range: str | None
    #: 自動継続の商品で、まだ解約されていない
    subscribed: bool
    #: 期限ではなく取り消しで終わっている: `"removed"`（全行 `del_chk=1`）/ `"canceled"`（購読を解約）
    ended: str | None


def fold_period(members: list[dict], kind: ColumnKind) -> Period:
    """権限の行をまとめて、期間と終わり方を決める。**受講登録とコースの購入で同じ規則を使う。**

    `kind` は書き込む列の型（`enrollments` は `timestamp`、`learning_path_enrollments` は `datetime(3)`）。
    """
    # **生きている行だけで判定する。** 全部消えていれば取り消し扱い
    alive = [r for r in members if int(r.get("del_chk") or 0) == 0]
    effective = alive or members

    # **自動継続も期限で切る。** 旧の受講可否は `authority_end_date >= 今日`（`LessonModel::1363`）で、
    # 自動継続の期限は毎日のバッチが1か月ずつ延ばしている。無期限にすると、cutover 後に
    # 継続課金を止めても受講が止まらない（sync-issues B6。2026-10-23）
    subscribed = [r for r in alive if _is_live_subscription(r)]

    # **無期限が1つでもあれば無期限。** lw2 は MAX() を取るので、
    # NULL 可の列に NULL を入れる形で「上限なし」を表す
    unlimited = any(int(r.get("no_limit_chk") or 0) == 1 for r in effective)
    expires_at = None
    beyond_range = None
    if not unlimited:
        # **終了日は 23:59:59 で補う。** 00:00 にすると期限日当日が切れる
        ends = [convert_date(r.get("authority_end_date"), kind, DateBoundary.END) for r in effective]
        ends = [e for e in ends if e is not None]
        expires_at = max(ends) if ends else None
        if expires_at is not None and expires_at > TIMESTAMP_MAX:
            # **`TIMESTAMP` に収まらない期限は実質無期限。** 旧は無期限を
            # 100年後の日付で表しており（実測 41件が `no_limit_chk` 無しで
            # 2049年以降）、**列の上限を超えると実 INSERT で落ちる**。
            # NULL（無期限）に寄せ、元の日付は `settings` に残す。`datetime(3)` の列でも
            # 同じにする（新は受講登録の期限をコースの購入の期限に合わせるので、そろえる）
            beyond_range = expires_at.isoformat()
            unlimited = True
            expires_at = None

    starts = [convert_date(r.get("authority_start_date"), kind, DateBoundary.START) for r in effective]
    starts = [s for s in starts if s is not None]

    if not alive:
        ended = "removed"
    elif not subscribed and _all_subscriptions_canceled(alive):
        ended = "canceled"
    else:
        ended = None
    return Period(
        # **畳んだので最も早い開始日を採る。** 権限が続いていた期間の起点
        enrolled_at=min(starts) if starts else None,
        expires_at=expires_at,
        unlimited=unlimited,
        beyond_range=beyond_range,
        subscribed=bool(subscribed),
        ended=ended,
    )


def _payment_of(rows: list[dict], payers: dict[int, int] | None = None) -> str | None:
    """畳んだ権限のうち、**決済として移す申込の最も新しいもの**の決済 ID。

    無料・チケット払い・支払い不要の申込は決済にならないので結ばない（→ `billing.payments`）。
    `payers`（申込 → 払った会員）を渡すと、**払った会員が権限の会員と違う申込にも結ばない**（0-2 Q8）。
    """
    from ..billing.payments import is_migrated, provider_payment_id

    ids = [
        int(r["application_id"])
        for r in rows
        if r.get("application_id") is not None
        and is_migrated(r.get("_payment_type"), r.get("_application_result"))
        and (payers is None or payers.get(int(r["application_id"])) == int(r["user_id"]))
    ]
    return provider_payment_id(max(ids)) if ids else None


def _has_item(rows: list[dict]) -> bool:
    """1行でも商品に紐づいていれば購入由来とみなす。"""
    return any(r.get("item_id") is not None for r in rows)


def _is_live_subscription(row: dict) -> bool:
    """自動継続の商品で、まだ解約されていないか（`PaymentModel:383` の「ご利用中」の条件
    `PI.is_auto_extension = 1 AND PA.is_cancel IS NULL`）。

    **受講できるかはこれでは決まらない**（期限で決まる）。自動継続だった印を残すのに使う。
    """
    if int(row.get("_auto_extension") or 0) != 1:
        return False
    cancel = row.get("_is_cancel")
    return cancel is None or int(cancel) == 0


def _all_subscriptions_canceled(rows: list[dict]) -> bool:
    """生きている行がすべて「自動継続だが解約済み」か。

    期限ではなく**解約で終わっている**ので、`expired` ではなく `revoked` にする。
    """
    subs = [r for r in rows if int(r.get("_auto_extension") or 0) == 1]
    return bool(subs) and len(subs) == len(rows) and not any(_is_live_subscription(r) for r in rows)


def _now() -> datetime:
    """期限切れの判定に使う「いま」。**投入時刻で固定される**ので、
    cutover から日が空くと `active` のまま期限切れの行が残る（再実行で直る）。
    """
    return datetime.utcnow()


def _settings(
    members: list[dict], unlimited: bool, beyond_range: str | None, subscribed: bool
) -> str:
    """新環境に列が無いものを残す。

    **畳んで捨てない。** どの商品で買ったか・無期限だったか・リモート PC を
    使えたかは、課金（4）の移行後や問い合わせ調査で要る
    （[移行の原則](../../../docs/db/00-template/review.md#移行の原則)の1）。
    """
    payload = {
            "unlimited": unlimited,
            # **購読由来かどうかを残す。** `source` は `purchase` のままで、
            # `subscription_id` は課金（4-2）の移行後でないと埋められない
            "subscription": subscribed,
            "remote_pc": any(int(r.get("remote_chk") or 0) == 1 for r in members),
            # **旧 ID のまま残す。** 商品は課金（4）で移すので、そのとき紐付け直す。
            # **`item_id` は NULL 可**（購入を経ていない付与）
            "legacy_item_ids": sorted(
                {int(r["item_id"]) for r in members if r.get("item_id") is not None}
            ),
            "legacy_application_ids": sorted(
                {int(r["application_id"]) for r in members if r.get("application_id") is not None}
            ),
            "legacy_authority_keys": sorted(
                {str(r["authority_key"]) for r in members if r.get("authority_key")}
            ),
            # **`cancel_chk` は取り消しではない**（自動延長の対象外の印）。値だけ残す
            "legacy_cancel_chk": sorted({int(r.get("cancel_chk") or 0) for r in members}),
            "legacy_rows": len(members),
    }
    if beyond_range:
        # 元の日付を残す。**`TIMESTAMP` の上限を超えたので NULL に寄せた**印
        payload["legacy_expires_at_beyond_timestamp"] = beyond_range
    return json.dumps(payload, ensure_ascii=False)


def build() -> list[Step]:
    """3-1 受講権限。"""
    return [EnrollmentRightsStep()]
