"""enrollment.1 — 受講権限。

`payment_item_lesson_authority` → `enrollments`。

**粒度が違う。** 旧は商品×講座で、同じ商品が複数講座を売り、同じ講座が複数商品から
売られる。実測 6,966 行が 4,289 組に重なる。**lw2 自身が `GROUP BY user_id, lesson_id`
で畳み、期限に `MAX()` を取っている**（`LessonModel::1804`）ので、同じ規則で寄せる。

**商品に紐づかない権限がある。** 実測 3,282行（2,306組）が `item_id` / `application_id`
ともに NULL で、`authority_key` も空。購入を経ずに直接入った付与で、
**商品で絞ると丸ごと落ちる**。`source` を `admin` にして移す。

**`cancel_chk` は使わない。** 名前に反してキャンセルフラグではなく、
`PaymentAuthorityModel` の INSERT 5か所すべてが**作成時に定数を書き込むだけで、
UPDATE する箇所が存在しない**。実測 1=3,064 / 0=620 は購入経路の違いを表す。
**実質の取り消しは `del_chk`**（実測 828件）。

**無料講座は移らない。** lw2 の受講可否は「権限がある **OR** その講座が有料ユニットを
持たない」の2分岐で（`LessonModel::1363`）、実測 235講座のうち権限が要るのは 71件だけ。
残り164件は権限行を持たないのが正常なので、ここでは作らない
（cutover 後の扱いは [確認事項 E3](../../../docs/db/open-questions.md)）。
"""

from __future__ import annotations

import json
from datetime import datetime

from ...context import RunContext
from ...core.datetimes import ColumnKind, DateBoundary, convert_date
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
        # **権限行だけでは受講可否が決まらない。** lw2 は商品のモード
        # （`payment_item.is_auto_extension`）と申込の解約状態
        # （`payment_application.is_cancel`）を見て分岐する（`PaymentModel:381-383`）。
        # 一緒に読まないと、自動継続の権限を期限切れとして移してしまう。
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
            "pa.`cancel_date_time` AS _cancel_date_time "
            "FROM `payment_item_lesson_authority` AS c "
            "INNER JOIN `user` AS u ON u.user_id = c.user_id "
            "LEFT JOIN `payment_item` AS p ON c.item_id = p.item_id "
            "LEFT JOIN `payment_application` AS pa ON pa.application_id = c.application_id "
            "WHERE u.tenant_id = %s"
        )
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
        # **生きている行だけで判定する。** 全部消えていれば取り消し扱い
        alive = [r for r in members if int(r.get("del_chk") or 0) == 0]
        effective = alive or members

        # **自動継続は期限を見ない。** lw2 の判定は `PA.is_cancel IS NULL` だけで
        # （`PaymentModel:383`）、`authority_end_date` が過去でも受講できる。
        # 期限をそのまま写すと、**いま受講できている人が失効扱いになる**。
        subscribed = [r for r in alive if _is_live_subscription(r)]

        # **無期限が1つでもあれば無期限。** lw2 は MAX() を取るので、
        # NULL 可の列に NULL を入れる形で「上限なし」を表す
        unlimited = any(int(r.get("no_limit_chk") or 0) == 1 for r in effective)
        expires_at = None
        beyond_range = None
        if subscribed:
            # 継続中の購読。解約されるまで有効なので期限を付けない
            unlimited = True
        elif not unlimited:
            # **終了日は 23:59:59 で補う。** 00:00 にすると期限日当日が切れる
            ends = [
                convert_date(r.get("authority_end_date"), ColumnKind.TIMESTAMP, DateBoundary.END)
                for r in effective
            ]
            ends = [e for e in ends if e is not None]
            expires_at = max(ends) if ends else None
            if expires_at is not None and expires_at > TIMESTAMP_MAX:
                # **`TIMESTAMP` に収まらない期限は実質無期限。** 旧は無期限を
                # 100年後の日付で表しており（実測 41件が `no_limit_chk` 無しで
                # 2049年以降）、**列の上限を超えると実 INSERT で落ちる**。
                # NULL（無期限）に寄せ、元の日付は `settings` に残す
                beyond_range = expires_at.isoformat()
                unlimited = True
                expires_at = None

        starts = [
            convert_date(r.get("authority_start_date"), ColumnKind.TIMESTAMP, DateBoundary.START)
            for r in effective
        ]
        starts = [s for s in starts if s is not None]

        # **`enrollment_statuses` は active / expired / refunded / revoked。**
        # `canceled` という値は無い（`revoked` を A8 の migration で足してある）
        if not alive:
            status = "revoked"
        elif subscribed:
            # 購読が続いている。期限切れの判定に落とさない
            status = "active"
        elif _all_subscriptions_canceled(alive):
            # 自動継続の商品なのに全部解約済み。期限ではなく解約で終わっている
            status = "revoked"
        elif expires_at is not None and expires_at < _now():
            # 期限切れ。実測で 1,874組中 1,603組（86%）が該当する
            status = "expired"
        else:
            status = "active"

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
                "enrolled_at": min(starts) if starts else None,
                "expires_at": expires_at,
                # 講座の修了日は `user_learning_lesson` 側。ここでは埋めない
                "completed_at": None,
                # 決済は課金（4）が未移行
                "provider_payment_id": None,
                "subscription_id": None,
                "settings": _settings(members, unlimited, beyond_range, bool(subscribed)),
            },
            natural_key=("tenant_id", "user_id", "course_id"),
            source_key=f"{user_id}:{lesson_id}",
        )


def _has_item(rows: list[dict]) -> bool:
    """1行でも商品に紐づいていれば購入由来とみなす。"""
    return any(r.get("item_id") is not None for r in rows)


def _is_live_subscription(row: dict) -> bool:
    """自動継続の商品で、まだ解約されていないか。

    **lw2 の受講可否はこれだけで決まる**（`PaymentModel:383` の
    `PI.is_auto_extension = 1 AND PA.is_cancel IS NULL`）。`authority_end_date` は見ない。
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
            # **`cancel_chk` は取り消しではない**（作成時の定数）。値だけ残す
            "legacy_cancel_chk": sorted({int(r.get("cancel_chk") or 0) for r in members}),
            "legacy_rows": len(members),
    }
    if subscribed:
        # 自動継続の権限は期限を写していない。元の値を残す
        payload["legacy_authority_end_dates"] = sorted(
            {str(r["authority_end_date"]) for r in members if r.get("authority_end_date")}
        )
    if beyond_range:
        # 元の日付を残す。**`TIMESTAMP` の上限を超えたので NULL に寄せた**印
        payload["legacy_expires_at_beyond_timestamp"] = beyond_range
    return json.dumps(payload, ensure_ascii=False)


def build() -> list[Step]:
    """3-1 受講権限。"""
    return [EnrollmentRightsStep()]
