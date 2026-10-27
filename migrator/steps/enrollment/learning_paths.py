"""コースの購入・割り当て（受講 03 のデータ。流すのは課金の billing.2 の決済の後）。

school-launcher はコース（`learning_paths`）＝旧の販売商品とし、購入・割り当てを
`learning_path_enrollments` に1行ずつ持つ（20261012014810 / 20261019004848）。渡した講座は
`learning_path_enrollment_courses`（20261019042710）。講座を受けられるかは今までどおり
`enrollments` で決まる（`enrollment.rights`）。

**1回の購入・付与 = 旧の `authority_key` 1つ。** 旧は購入・付与のたびに会員1人・商品1つの
キーを振り、講座ごとに権限の行を作る（`PaymentAuthorityModel`）。キーの無い行（商品を経ない付与）は
コースの購入にならないので、ここでは扱わない（`enrollments` の `source = 'admin'`）。

- 申込（`application_id`）あり … 無料（`payment_type` 0 / 4）は `free`、それ以外は `purchase`。
  **決済として移した申込だけ** `payment_id` を結ぶ（`billing.payments` の `is_migrated`）
- 申込なし … 管理者が商品単位で付与した権限（旧の「購入権限（定額商品単位）」）。`admin`

**流すのは決済の後**（2026-10-22 決定）。`payment_id` は `payments(id)` への外部キー。
"""

from __future__ import annotations

from ...context import RunContext
from ...core.datetimes import ColumnKind
from ...core.records import Record
from ..base import Step
from .rights import AUTHORITY_COLUMNS, fold_period

#: 無料の申込（`payment_type`）。0 無料 / 4 無料クーポン（課金 04 の P3）
FREE_PAYMENT_TYPES = {0, 4}


def _fetch(ctx: RunContext) -> list[dict]:
    """商品に紐づく権限の行。商品の自動継続と申込の状態を添える（`enrollment.rights` と同じ読み方）。"""
    cols = ", ".join(f"c.`{name}`" for name in AUTHORITY_COLUMNS)
    sql = (
        f"SELECT {cols}, "
        "p.`is_auto_extension` AS _auto_extension, "
        "pa.`is_cancel` AS _is_cancel, "
        "pa.`payment_type` AS _payment_type, "
        "pa.`application_result` AS _application_result "
        "FROM `payment_item_lesson_authority` AS c "
        "INNER JOIN `user` AS u ON u.user_id = c.user_id "
        "LEFT JOIN `payment_item` AS p ON c.item_id = p.item_id "
        "LEFT JOIN `payment_application` AS pa ON pa.application_id = c.application_id "
        "WHERE u.tenant_id = %s AND c.item_id IS NOT NULL"
    )
    return ctx.require_source().fetch("payment_item_lesson_authority", sql, (ctx.config.tenant.legacy_id,))


def _fetch_direct(ctx: RunContext) -> list[dict]:
    """商品を経ない権限（直接付与）。**生きている行だけ**（消した直接付与は戻す先にならない）。"""
    cols = ", ".join(f"c.`{name}`" for name in AUTHORITY_COLUMNS)
    sql = (
        f"SELECT {cols} FROM `payment_item_lesson_authority` AS c "
        "INNER JOIN `user` AS u ON u.user_id = c.user_id "
        "WHERE u.tenant_id = %s AND c.item_id IS NULL AND c.del_chk = 0"
    )
    return ctx.require_source().fetch("payment_item_lesson_authority", sql, (ctx.config.tenant.legacy_id,))


def direct_grants(rows: list[dict]) -> dict[tuple[int, int], tuple[str, object]]:
    """(会員, 講座) → 直接付与だけを畳んだ (状態, 期限)。受講登録と同じ規則（`rights.fold_period`）。"""
    from .rights import status_of as enrollment_status

    groups: dict[tuple[int, int], list[dict]] = {}
    for row in rows:
        if row.get("item_id") is not None or int(row.get("del_chk") or 0):
            continue
        groups.setdefault((int(row["user_id"]), int(row["lesson_id"])), []).append(row)
    out = {}
    for key, members in groups.items():
        period = fold_period(members, ColumnKind.DATETIME)
        out[key] = (enrollment_status(period), period.expires_at)
    return out


def grant_key(row: dict) -> str:
    """1回の購入・付与のキー。**旧の `authority_key`**。空なら (会員, 商品, 申込) で代える。"""
    key = str(row.get("authority_key") or "").strip()
    if key:
        return key
    return f"{row['user_id']}:{row['item_id']}:{row.get('application_id') or ''}"


def grants(rows: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for row in rows:
        out.setdefault(grant_key(row), []).append(row)
    return out


def source_of(members: list[dict]) -> str:
    """`purchase` / `free` / `admin`。申込の無い付与は管理者の付与。"""
    apps = [r for r in members if r.get("application_id") is not None]
    if not apps:
        return "admin"
    if all(int(r.get("_payment_type") or 0) in FREE_PAYMENT_TYPES for r in apps):
        return "free"
    return "purchase"


def status_of(source: str, ended: str | None) -> str:
    """取り消されたものは、**申込を経たもの（購入・無料）は `refunded`、管理者の付与は `revoked`**（2026-10-22 決定）。

    旧に返金の概念は無いが、新は `revoked` を管理者の取り消しに限っている。期限切れは状態にしない
    （新は `expires_at` で判定する）。
    """
    if ended is None:
        return "active"
    return "revoked" if source == "admin" else "refunded"


class LearningPathEnrollmentsStep(Step):
    """旧の購入・付与（`authority_key` 単位）を `learning_path_enrollments` に移す。"""

    name = "enrollment.learning_path_enrollments"
    description = "コースの購入・割り当てを移す（旧の購入・付与ごとに1行）"
    source_table = "payment_item_lesson_authority"
    target_table = "learning_path_enrollments"
    depends_on = ("users", "content.learning_paths", "billing.payments")

    def extract(self, ctx: RunContext) -> list[dict]:
        from ..billing.payments import payers

        self._payers = payers(ctx)
        return _fetch(ctx)

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        from ..billing.payments import is_migrated

        payers = getattr(self, "_payers", None)

        tenant_id = ctx.tenant_id.value
        records: list[Record] = []
        for key, members in sorted(grants(rows).items()):
            first = members[0]
            period = fold_period(members, ColumnKind.DATETIME)
            source = source_of(members)
            paid = [
                int(r["application_id"]) for r in members
                if r.get("application_id") is not None
                and is_migrated(r.get("_payment_type"), r.get("_application_result"))
                # **払った会員が権限の会員と違う申込には結ばない**（会員の無い申込は決済が落ちる。0-2 Q8）
                and (payers is None or payers.get(int(r["application_id"])) == int(r["user_id"]))
            ]
            alive = [r for r in members if int(r.get("del_chk") or 0) == 0] or members
            records.append(
                Record(
                    table="learning_path_enrollments",
                    values={
                        "id": ctx.ulid.for_row("authority_key", key),
                        "tenant_id": tenant_id,
                        "user_id": ctx.ulid.for_row("user", first["user_id"]),
                        "learning_path_id": ctx.ulid.for_row("learning_path", first["item_id"]),
                        "payment_id": ctx.ulid.for_row("payment_application", max(paid)) if paid else None,
                        "source": source,
                        "status": status_of(source, period.ended),
                        # NOT NULL。開始日の無い付与は一覧に出る（作り替えない）
                        "enrolled_at": period.enrolled_at,
                        "expires_at": period.expires_at,
                        # **購入した時点の商品の「リモートPC の利用」**（旧 `payment_item_lesson_authority.remote_chk`）
                        "remote_pc_enabled": any(int(r.get("remote_chk") or 0) == 1 for r in alive),
                    },
                    natural_key=("id",),
                    source_key=key,
                )
            )
        return records


class LearningPathEnrollmentCoursesStep(Step):
    """購入・付与で渡した講座を `learning_path_enrollment_courses` に移す。

    **削除済みの権限の講座も入れる。** この表は「渡した講座の記録」で、取り消しは受講登録
    （`enrollments`）とコースの購入の状態で表している。

    **`prev_*` は、同じ (会員, 講座) に商品を経ない生きている権限（直接付与）があるときだけ入れる**
    （03 移行仕様 0-2 Q3）。旧は権限の行が別なので、コースの権限を消しても直接付与で受講を続けられた。
    新はコースの取り消しで `prev_*` に戻すので、直接付与だけを畳んだ状態と期限を入れる。
    """

    name = "enrollment.learning_path_enrollment_courses"
    description = "コースの購入・割り当てで渡した講座を移す"
    source_table = "payment_item_lesson_authority"
    target_table = "learning_path_enrollment_courses"
    depends_on = ("enrollment.learning_path_enrollments", "content.courses")

    def extract(self, ctx: RunContext) -> list[dict]:
        self._direct = direct_grants(_fetch_direct(ctx))
        return _fetch(ctx)

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        direct = getattr(self, "_direct", {})
        records: list[Record] = []
        for key, members in sorted(grants(rows).items()):
            user_id = int(members[0]["user_id"])
            for lesson_id in sorted({int(r["lesson_id"]) for r in members}):
                prev = direct.get((user_id, lesson_id))
                records.append(
                    Record(
                        table="learning_path_enrollment_courses",
                        values={
                            "learning_path_enrollment_id": ctx.ulid.for_row("authority_key", key),
                            "course_id": ctx.ulid.for_row("lesson", lesson_id),
                            "tenant_id": tenant_id,
                            "prev_recorded": prev is not None,
                            "prev_status": prev[0] if prev else None,
                            "prev_expires_at": prev[1] if prev else None,
                        },
                        natural_key=("learning_path_enrollment_id", "course_id"),
                        source_key=f"{key}:{lesson_id}",
                    )
                )
        return records


def build() -> list[Step]:
    return [LearningPathEnrollmentsStep(), LearningPathEnrollmentCoursesStep()]
