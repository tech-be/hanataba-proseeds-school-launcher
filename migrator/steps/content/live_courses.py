"""live.2 — ライブの置き場所（受け皿講座と受講登録）。

**lw2 のライブは講座に属さない。** 新環境は `courses` → `lessons`(type=live) の階層で、
`lessons.course_id` が NOT NULL なので、**どの講座に置くかを決めないと1行も入らない。**

**置き場所は2通りある**（2026-09-24 決定。[migration-spec 1-2](../../../docs/db/03-live/migration-spec.md)）。

- **商品で制限しているライブ** … `live_lesson_limit_item` → `payment_item` →
  `payment_item_lesson` で**実在の講座に1対1でたどれる**。その講座の配下に置く。
  旧のアクセス制御（`payment_item_lesson_authority`）は受講（04）で `enrollments` になり、
  新環境の `verifyEnrolled` がそのまま効く
- **制限していないライブ** … lw2 では**全員が予約できた**。新環境に「講座に属さないレッスン」は
  無いので、**受け皿の講座を1本作り、全会員を受講登録する**（決定 ①）

**受講登録はライブ区分で作る。** 書き込み先は受講区分（04）の `enrollments` だが、
**lw2 に元データが無く、ライブの決定から生まれる行**なので、ここで作る。
04 が `payment_item_lesson_authority` から作る行とは**受け皿講座（`course_id`）で区別する**。
"""

from __future__ import annotations

from ...context import RunContext
from ...core.records import Record
from ..base import Step

#: 受け皿講座の採番キー。**lw2 に対応する行が無い**ので固定の文字列から採番する
HOST_COURSE_KEY = "lw2-live-host"
HOST_COURSE_TITLE = "ライブレッスン"

LIVE_LESSON_COLUMNS = ("live_lesson_id", "live_lesson_name", "lesson_instructor_id", "del_chk")


def host_course_id(ctx: RunContext) -> str:
    """制限の無いライブを入れる受け皿講座の ULID。"""
    return ctx.ulid.for_row("lesson", HOST_COURSE_KEY)


def course_for(ctx: RunContext, legacy_course_id: object) -> str:
    """ライブを置く講座の ULID。

    `legacy_course_id` は `payment_item_lesson.lesson_id`（旧の講座）。
    **無ければ受け皿講座**に置く。
    """
    if legacy_course_id is None:
        return host_course_id(ctx)
    return ctx.ulid.for_row("lesson", int(legacy_course_id))


def resolve_placement(ctx: RunContext) -> dict[int, int | None]:
    """ライブ → 置き場所の旧講座 ID（無ければ None）。

    **`del_chk = 0` の制限だけを見る。** 旧は保存のたびに旧行を `del_chk = 1` にして
    積む作りで、ステージングでは50行のうち45行が削除済み（生きているのは5行）。
    """
    rows = ctx.require_source().fetch_joined(
        "live_lesson_limit_item",
        ("live_lesson_id", "item_id"),
        parent="live_lesson",
        on="c.live_lesson_id = p.live_lesson_id",
        where="c.del_chk = 0",
    )
    items = {int(r["item_id"]) for r in rows}
    if not items:
        return {}
    # 商品 → 講座。**商品は講座を1本だけ売っている前提**（ステージング実測で2商品とも1対1）。
    # `payment_item_lesson` は `tenant_id` を持たないので `payment_item` と join して絞る
    placements = [
        r
        for r in ctx.require_source().fetch_joined(
            "payment_item_lesson",
            ("item_id", "lesson_id"),
            parent="payment_item",
            on="c.item_id = p.item_id",
            where="c.del_chk = 0 AND p.del_chk = 0",
        )
        if int(r["item_id"]) in items
    ]
    by_item: dict[int, int] = {}
    for row in placements:
        by_item.setdefault(int(row["item_id"]), int(row["lesson_id"]))
    out: dict[int, int | None] = {}
    for row in rows:
        course = by_item.get(int(row["item_id"]))
        if course is not None:
            out.setdefault(int(row["live_lesson_id"]), course)
    return out


class HostCourseStep(Step):
    """制限の無いライブを入れる受け皿講座を1本作る。

    **`courses.instructor_id` は NOT NULL。** ライブは講師を持っているので、
    **制限の無いライブの講師のうち、担当するライブが最も多い1名**を代表に立てる
    （代理講師は使わない。ライブには実在の講師が居る）。
    """

    name = "content.live_host_course"
    description = "制限の無いライブを入れる受け皿講座を作る"
    source_table = "live_lesson"
    target_table = "courses"
    depends_on = ("tenant",)

    def extract(self, ctx: RunContext) -> list[dict]:
        source = ctx.require_source()
        placement = resolve_placement(ctx)
        lives = source.fetch_for_tenant("live_lesson", LIVE_LESSON_COLUMNS)
        # 受け皿に入るのは、置き場所が決まっていないライブだけ
        return [r for r in lives if int(r["live_lesson_id"]) not in placement]

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        if not rows:
            ctx.logger.info("制限の無いライブが無いので、受け皿講座は作らない")
            return []
        counts: dict[int, int] = {}
        for row in rows:
            instructor = row.get("lesson_instructor_id")
            if instructor is not None:
                counts[int(instructor)] = counts.get(int(instructor), 0) + 1
        if not counts:
            raise ValueError(
                "制限の無いライブに講師が1人も設定されていない。"
                "`courses.instructor_id` は NOT NULL なので代表を決められない"
            )
        # 担当数が多い順、同数なら旧 ID が小さい順（実行のたびに変わらないように）
        representative = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
        ctx.logger.info(
            "受け皿講座の講師に旧 user_id=%s を立てる（制限の無いライブ %d 件中 %d 件を担当）",
            representative,
            len(rows),
            counts[representative],
        )
        return [
            Record(
                table="courses",
                values={
                    "id": host_course_id(ctx),
                    "tenant_id": ctx.tenant_id.value,
                    # **旧 ID は持たせない。** lw2 に対応する講座が無い行なので、
                    # `legacy_lesson_id` を埋めると実在の講座と見分けが付かなくなる
                    "legacy_lesson_id": None,
                    "title": HOST_COURSE_TITLE,
                    "description": (
                        "lw2 の「商品で制限していないライブ」を入れる講座。"
                        "旧環境では全員が予約できたため、全会員を受講登録する"
                    ),
                    "instructor_id": ctx.ulid.for_row("user", representative),
                    "status": "published",
                    "currency": "JPY",
                    "is_sample": False,
                },
                natural_key=("id",),
                source_key=HOST_COURSE_KEY,
            )
        ]


class HostCourseEnrollmentsStep(Step):
    """受け皿講座に**全会員を受講登録する**（2026-09-24 決定 ①）。

    **lw2 に元データが無い。** 旧環境では制限の無いライブを全員が予約できたが、
    新環境は `verifyEnrolled` が `enrollments` を見るため、登録しないと誰も予約できない。

    `source = 'admin'`（管理者付与）で入れる。`enrollment_sources` の5値
    （`purchase` / `subscription` / `free` / `admin` / `marketplace`）のうち、
    **運営が配った行**を表すのがこれ。

    **`source` だけでは受講（3-1）の行と区別できない。** 旧 `payment_item_lesson_authority`
    にも商品を経ていない付与（`item_id IS NULL`）があり、そちらも `admin` になる。
    ここで作る行は**受け皿講座1本にしか付かない**ので、`course_id` で切り分ける。
    """

    name = "enrollment.live_host_enrollments"
    description = "受け皿講座に全会員を受講登録する（旧の「全員に公開」を保つ）"
    source_table = "user"
    target_table = "enrollments"
    depends_on = ("content.live_host_course",)

    def extract(self, ctx: RunContext) -> list[dict]:
        # 受け皿講座が無い（制限の無いライブが1件も無い）なら登録も要らない
        if not HostCourseStep().extract(ctx):
            return []
        return ctx.require_source().fetch_for_tenant("user", ("user_id", "del_chk"))

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        course = host_course_id(ctx)
        records = [
            Record(
                table="enrollments",
                values={
                    "id": ctx.ulid.for_row("live_host_enrollment", row["user_id"]),
                    "tenant_id": tenant_id,
                    "user_id": ctx.ulid.for_row("user", row["user_id"]),
                    "course_id": course,
                    # 旧に対応する購入が無い。運営が配った扱いにする
                    "source": "admin",
                    "status": "active",
                    # **無期限。** lw2 の「全員に公開」に期限は無い
                    "expires_at": None,
                },
                natural_key=("tenant_id", "user_id", "course_id"),
                source_key=int(row["user_id"]),
            )
            for row in rows
        ]
        if records:
            ctx.logger.warning(
                "受け皿講座に %d 名を受講登録する。**lw2 に元データが無い行**で、"
                "旧の「制限の無いライブは全員が予約できる」を保つために作る",
                len(records),
            )
        return records


def host_course() -> list[Step]:
    """2-4 ライブ講座。受け皿の講座そのもの。"""
    return [HostCourseStep()]


def enrollments() -> list[Step]:
    """3-1 受講権限。**受け皿講座への全会員の登録**（lw2 に元データが無い行）。"""
    return [HostCourseEnrollmentsStep()]
