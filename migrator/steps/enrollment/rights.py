"""enrollment.1 — 受講権限。

`payment_item_lesson_authority` → `enrollments`。

**粒度が違う。** 旧は商品×講座で、同じ商品が複数講座を売り、同じ講座が複数商品から
売られる。実測 3,684 行が 2,246 組に重なる。**lw2 自身が `GROUP BY user_id, lesson_id`
で畳み、期限に `MAX()` を取っている**（`LessonModel::1804`）ので、同じ規則で寄せる。

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
        # **`tenant_id` を持たない。** 商品（`payment_item`）と join して絞る
        return ctx.require_source().fetch_joined(
            "payment_item_lesson_authority",
            AUTHORITY_COLUMNS,
            parent="payment_item",
            on="c.item_id = p.item_id",
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

        # **無期限が1つでもあれば無期限。** lw2 は MAX() を取るので、
        # NULL 可の列に NULL を入れる形で「上限なし」を表す
        unlimited = any(int(r.get("no_limit_chk") or 0) == 1 for r in effective)
        expires_at = None
        beyond_range = None
        if not unlimited:
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
                # 商品の購入で得た権限。`manual` という値は存在しない
                "source": "purchase",
                "status": status,
                # **畳んだので最も早い開始日を採る。** 権限が続いていた期間の起点
                "enrolled_at": min(starts) if starts else None,
                "expires_at": expires_at,
                # 講座の修了日は `user_learning_lesson` 側。ここでは埋めない
                "completed_at": None,
                # 決済は課金（4）が未移行
                "provider_payment_id": None,
                "subscription_id": None,
                "settings": _settings(members, unlimited, beyond_range),
            },
            natural_key=("tenant_id", "user_id", "course_id"),
            source_key=f"{user_id}:{lesson_id}",
        )


def _now() -> datetime:
    """期限切れの判定に使う「いま」。**投入時刻で固定される**ので、
    cutover から日が空くと `active` のまま期限切れの行が残る（再実行で直る）。
    """
    return datetime.utcnow()


def _settings(members: list[dict], unlimited: bool, beyond_range: str | None) -> str:
    """新環境に列が無いものを残す。

    **畳んで捨てない。** どの商品で買ったか・無期限だったか・リモート PC を
    使えたかは、課金（4）の移行後や問い合わせ調査で要る
    （[移行の原則](../../../docs/db/00-template/review.md#移行の原則)の1）。
    """
    payload = {
            "unlimited": unlimited,
            "remote_pc": any(int(r.get("remote_chk") or 0) == 1 for r in members),
            # **旧 ID のまま残す。** 商品は課金（4）で移すので、そのとき紐付け直す
            "legacy_item_ids": sorted({int(r["item_id"]) for r in members}),
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
    if beyond_range:
        # 元の日付を残す。**`TIMESTAMP` の上限を超えたので NULL に寄せた**印
        payload["legacy_expires_at_beyond_timestamp"] = beyond_range
    return json.dumps(payload, ensure_ascii=False)


def build() -> list[Step]:
    """3-1 受講権限。"""
    return [EnrollmentRightsStep()]
