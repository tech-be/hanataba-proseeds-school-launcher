"""content.1 — 講座のカテゴリ・講座本体・講座タグ。

- `lesson_cate` → `tenant_course_categories`（テナントごとのカテゴリ。2026-10-22 から）と
  `course_category_links`。**全テナント共通の `course_categories` には入れず、`courses.category` は NULL**
  （2026-10-26 決定。02 の移行仕様 0-3 の Q16。新の `/courses` の絞り込みは recademy の
  `settings.top_catalog.categories` の 6 つのコードを見るので、旧のコードとは合わない。
  対応表を受け取ったら入れる）
- `lesson` → `courses`
- `lesson_tag` / `lesson_lesson_tag` → `course_tags` / `course_tag_links`

**削除済み（`del_chk=1`）の講座も移す。** `status='archived'` で表現する（2026-10-26 決定。
新は `deleted` の講座を受講者に見せ、状態を変える編集も 400 にする）。
"""

from __future__ import annotations

import json

from ...context import RunContext
from ...core.datetimes import ColumnKind, convert
from ...core.records import Record
from ...errors import PreflightError
from ..base import Step

CATEGORY_COLUMNS = (
    "lesson_cate_id",
    "tenant_id",
    "lesson_cate_name",
    "lesson_cate_img_file_name",
    "sort_no",
    "update_date",
    "del_chk",
)

LESSON_COLUMNS = (
    "lesson_id",
    "tenant_id",
    "name",
    "description",
    "lesson_cate_id",
    "sort_no",
    "sales_status",
    "allowed_ip_address",
    "open_pc_chk",
    "open_smartphone_chk",
    "progress_display_chk",
    "drill_chk",
    "quiz_chk",
    "sns_shared_chk",
    "inquiry_chk",
    "open_period",
    "del_chk",
    "regist_date",
)

TAG_COLUMNS = (
    "lesson_tag_id",
    "tenant_id",
    "tag_name",
    "sort_no",
    "del_chk",
)

TAG_LINK_COLUMNS = (
    "lesson_tag_id",
    "lesson_id",
)

from .instructors import PROXY_KEY as PROXY_INSTRUCTOR_KEY


def _categories(ctx: RunContext, log: bool = False) -> list[dict]:
    """移すカテゴリ（`tenant_course_categories`）。**講座側の参照チェックにも使う。**"""
    source = ctx.require_source()
    rows = source.fetch_for_tenant("lesson_cate", CATEGORY_COLUMNS)
    known = {int(r["lesson_cate_id"]) for r in rows}
    # 共有カテゴリ（tenant_id=0）のうち、**このテナントの講座が参照しているもの**だけ
    shared = source.fetch_joined(
        "lesson_cate",
        CATEGORY_COLUMNS,
        parent="lesson",
        on="c.lesson_cate_id = p.lesson_cate_id",
        where="c.tenant_id = 0",
    )
    for row in shared:
        if int(row["lesson_cate_id"]) not in known:
            known.add(int(row["lesson_cate_id"]))
            rows.append(row)
            if log:
                ctx.logger.info(
                    "共有カテゴリ（tenant_id=0）を移す: %s %s",
                    row["lesson_cate_id"],
                    row.get("lesson_cate_name"),
                )
    return rows


class TenantCourseCategoriesStep(Step):
    """講座カテゴリを `tenant_course_categories`（テナントごとのカテゴリ）に移す（2026-10-22）。

    school-launcher 20261020001030 で、講座のカテゴリがテナントごとのマスタになった（受講者の
    「講座・コースを探す」の絞り込みに使う）。旧 `lesson_cate` もテナントごとなので、こちらが
    受け皿として合う。全テナント共通の `course_categories` には入れない（2026-10-26。Q16）。

    移すカテゴリは `_categories`（共有カテゴリは講座が使っている分だけ）。
    **削除済みは `deprecated_at`** に入れる（新の「講座に付いたまま残し、選べなくする」が旧の削除にあたる）。
    """

    name = "content.tenant_course_categories"
    description = "講座カテゴリをテナントのカテゴリとして移す"
    source_table = "lesson_cate"
    target_table = "tenant_course_categories"
    depends_on = ("tenant",)

    def extract(self, ctx: RunContext) -> list[dict]:
        return _categories(ctx)

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        records: list[Record] = []
        for row in rows:
            name = (row.get("lesson_cate_name") or "").strip()
            deleted = int(row.get("del_chk") or 0) == 1
            records.append(
                Record(
                    table="tenant_course_categories",
                    values={
                        "id": ctx.ulid.for_row("tenant_course_category", row["lesson_cate_id"]),
                        "tenant_id": tenant_id,
                        # 空の名前は NOT NULL に当たって一覧に出る（作り替えない）
                        "name": name or None,
                        "sort_order": int(row.get("sort_no") or 0),
                        "is_system": False,
                        "active": True,
                        "deprecated_at": (
                            convert(row.get("update_date"), ColumnKind.DATETIME) if deleted else None
                        ),
                    },
                    natural_key=("id",),
                    source_key=int(row["lesson_cate_id"]),
                )
            )
        return records


class CourseCategoryLinksStep(Step):
    """講座の `lesson_cate_id` を `course_category_links` に移す（1 講座に 1 件）。

    参照先の無い `lesson_cate_id`（旧データの不整合）は、講座と同じく分類なしとして扱う（`CoursesStep`）。
    """

    name = "content.course_category_links"
    description = "講座とテナントのカテゴリの結び付きを移す"
    source_table = "lesson"
    target_table = "course_category_links"
    depends_on = ("content.courses", "content.tenant_course_categories")

    def extract(self, ctx: RunContext) -> list[dict]:
        rows = CoursesStep().extract(ctx)
        return [r for r in rows if r.get("lesson_cate_id") and int(r["lesson_cate_id"]) != 0]

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        return [
            Record(
                table="course_category_links",
                values={
                    "course_id": ctx.ulid.for_row("lesson", row["lesson_id"]),
                    "category_id": ctx.ulid.for_row("tenant_course_category", row["lesson_cate_id"]),
                    "tenant_id": tenant_id,
                },
                natural_key=("course_id", "category_id"),
                source_key=int(row["lesson_id"]),
            )
            for row in rows
        ]


class CoursesStep(Step):
    """講座を `courses` に移す。

    **`instructor_id` は NOT NULL。** 講座→講師の対応表が無いため、暫定対応として
    代理講師（A21）を全講座に割り当てる。対応表を受け取ったら付け替え、
    **代理講師のままの講座が0件になったことを確認する**。

    **価格も暫定。** lw2 は価格を商品（`payment_item`）に持ち、商品と講座が 1:N なので
    どの価格を入れるかが決まらない。対応表が届くまで仮の値を入れる。
    """

    name = "content.courses"
    description = "講座を移す（講師と価格は暫定値）"
    source_table = "lesson"
    target_table = "courses"
    depends_on = ("tenant", "content.tenant_course_categories", "content.proxy_instructor")

    def extract(self, ctx: RunContext) -> list[dict]:
        source = ctx.require_source()
        # 共有講座（tenant_id=0）も入る（`SourceDatabase.shared_lessons`）
        rows = source.fetch_for_tenant("lesson", LESSON_COLUMNS)
        # **参照先の無い `lesson_cate_id` を持つ講座がある**（実測9件。1055 / 1057 / 5120 は
        # `lesson_cate` に行が無い旧データの不整合）。`courses.category` は NULL 可なので、
        # **分類だけ落として講座は移す**。落とすと 329 ユニット・161 学習履歴まで連鎖する
        known = {int(r["lesson_cate_id"]) for r in _categories(ctx)}
        for row in rows:
            cate = row.get("lesson_cate_id")
            if cate and int(cate) not in known:
                ctx.logger.warning(
                    "lesson_id=%s: lesson_cate_id=%s が lesson_cate に無い。分類なしで移す",
                    row["lesson_id"],
                    cate,
                )
                row["lesson_cate_id"] = None
        # **利用中の講座**（旧 `lesson_is_used`）。旧は受講登録・購入のたびに1行作り、管理画面の
        # 「利用中の講座だけ」の絞り込みに使っていた（02 review A1）。販売状態（`sales_status`）とは別物
        used = {int(r["lesson_id"]) for r in source.fetch_for_tenant("lesson_is_used", ("lesson_id",))}
        for row in rows:
            row["_is_used"] = int(row["lesson_id"]) in used
        return rows

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        instructor_id = ctx.ulid.for_row("user", PROXY_INSTRUCTOR_KEY)
        price = ctx.provisional("course_price")
        records: list[Record] = []
        for row in rows:
            title = (row.get("name") or "").strip()
            if not title:
                raise PreflightError(f"lesson_id={row['lesson_id']}: name が空。courses.title は NOT NULL")
            records.append(
                Record(
                    table="courses",
                    values={
                        "id": ctx.ulid.for_row("lesson", row["lesson_id"]),
                        "tenant_id": tenant_id,
                        "legacy_lesson_id": int(row["lesson_id"]),
                        "title": title,
                        "description": row.get("description"),
                        # 新のトップの 6 つのコードとの対応表を受け取るまで NULL（Q16）。
                        # テナントのカテゴリは course_category_links で付く
                        "category": None,
                        # **暫定**: 対応表を受け取るまで代理講師に寄せる
                        "instructor_id": instructor_id,
                        "price": price,
                        "currency": "JPY",
                        "status": _status_of(row),
                        "difficulty": None,
                        "access_days": _access_days(row.get("open_period")),
                        "thumbnail_url": None,  # 画像は L9 で移送
                        "is_sample": False,
                        "remote_pc_enabled": False,
                        "final_quiz_id": None,  # テスト移行後に埋める
                        "allowed_ip_address": row.get("allowed_ip_address"),
                        "is_used": bool(row.get("_is_used")),
                        "settings": _settings(row),
                        "created_at": convert(row.get("regist_date"), ColumnKind.TIMESTAMP),
                    },
                    natural_key=("tenant_id", "legacy_lesson_id"),
                    source_key=int(row["lesson_id"]),
                )
            )
        return records


#: `lesson.open_period` の単位は**月**。新環境の `access_days` は**日**。
#: lw2 は `strtotime(開始日 . ' +' . open_period . ' month')` で期限を出しており
#: （`UserController:3700`）、管理画面のラベルも「ヶ月間」。
#: **換算しないと受講期間が 1/30 になる。**
DAYS_PER_MONTH = 30


def _access_days(value: object) -> int | None:
    """旧 `lesson.open_period`（月）を `courses.access_days`（日）に写す。

    **単位が違う。** そのまま入れると `7ヶ月` が `7日` になる。
    30日/月で換算する（lw2 は暦月で計算するが、新環境は日数しか持てない）。

    **`0` は「指定なし」なので NULL に倒す。** 新環境も `0` を無期限として扱うので
    挙動は同じだが、**API のバリデーションが `min=1` で `0` を受け付けない**
    （`AccessDays *int validate:"omitempty,min=1,max=3650"`）。0 のまま入れると
    **管理画面から編集できない値**になる。新環境自身も `> 0` のときだけ書くので、
    `0` は移行ツールだけが作る値だった。
    """
    months = int(value or 0)
    return months * DAYS_PER_MONTH if months > 0 else None


def _status_of(row: dict) -> str:
    """`del_chk` / `sales_status` から `content_statuses.code` を決める。

    **販売停止（`sales_status=0`）は `archived`**（2026-10-22 決定）。新システムは講座の下書きを
    やめ（school-launcher 20261012065004）、画面から公開にする操作が無い。`draft` で入れると
    運営が戻せないので、アーカイブの解除で戻せる `archived` にする。

    **元の列は残す**（`is_used`、`settings.sales_status`）。status は判定結果で、ここに畳むわけではない。

    **削除済みも `archived`**（2026-10-26 決定。02 の移行仕様 0-3 の Q1）。新は `deleted` の講座を
    受講者に見せ（除外は `<> 'archived'` だけ）、状態を変える編集も 400 にする。
    """
    if int(row.get("del_chk") or 0) == 1:
        return "archived"
    return "published" if int(row.get("sales_status") or 0) == 1 else "archived"


def _settings(row: dict) -> str:
    """新環境に列が無い表示・機能フラグを `settings` にまとめる。

    **畳んで捨てるのではなく、キーを分けて残す。** 新環境に対応する機能が無くても移す
    （[移行の原則](../../../docs/db/00-template/review.md#移行の原則)の1）。
    """
    flags = {
        "open_pc": bool(int(row.get("open_pc_chk") or 0)),
        "open_smartphone": bool(int(row.get("open_smartphone_chk") or 0)),
        "progress_display": bool(int(row.get("progress_display_chk") or 0)),
        "drill": bool(int(row.get("drill_chk") or 0)),
        "quiz": bool(int(row.get("quiz_chk") or 0)),
        "sns_shared": bool(int(row.get("sns_shared_chk") or 0)),
        "inquiry": bool(int(row.get("inquiry_chk") or 0)),
    }
    # 旧の販売状態（1 販売中 / 0 販売停止）。status には `archived` として畳んでいるので値も残す
    sales_status = row.get("sales_status")
    return json.dumps(
        {"features": flags, "sales_status": None if sales_status is None else int(sales_status)},
        ensure_ascii=False,
    )


class CourseTagsStep(Step):
    """`lesson_tag` を `course_tags` に移す。

    **`category` では代用できない。** カテゴリは1講座に1件だが、タグは複数付く
    （実測 19 タグ / 割当は ReCADemy の講座 39・共有講座 13）。削除済み（`del_chk=1`）のタグも移す —
    割当が残っている以上、名前が引けないと割当が意味を失う。

    **共有のタグ（`tenant_id = 0`）も移す**（2026-10-02）。移す講座（共有講座を含む）の割当が
    指していれば、このテナントのタグとして入れる。拾わないと割当が外部キーで落ちる（実測 3 タグ / 9 割当）。
    """

    name = "content.course_tags"
    description = "講座タグを移す"
    source_table = "lesson_tag"
    target_table = "course_tags"
    depends_on = ("tenant",)

    def extract(self, ctx: RunContext) -> list[dict]:
        source = ctx.require_source()
        rows = source.fetch_for_tenant("lesson_tag", TAG_COLUMNS)
        own = {int(r["lesson_tag_id"]) for r in rows}
        # 移す講座の割当が指すタグ（講座で絞る）。このテナントのものは上で読んでいる
        for tag in source.fetch_joined(
            "lesson_tag",
            TAG_COLUMNS,
            parent="lesson",
            on="x.lesson_id = p.lesson_id",
            via=[("lesson_lesson_tag", "x", "c.lesson_tag_id = x.lesson_tag_id")],
        ):
            if int(tag["lesson_tag_id"]) not in own and int(tag.get("tenant_id") or 0) == 0:
                own.add(int(tag["lesson_tag_id"]))
                rows.append(tag)
        return rows

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        records: list[Record] = []
        for row in rows:
            name = (row.get("tag_name") or "").strip()
            if not name:
                raise PreflightError(
                    f"lesson_tag_id={row['lesson_tag_id']}: tag_name が空。course_tags.name は NOT NULL"
                )
            records.append(
                Record(
                    table="course_tags",
                    values={
                        "id": ctx.ulid.for_row("lesson_tag", row["lesson_tag_id"]),
                        "tenant_id": tenant_id,
                        "lesson_tag_id": int(row["lesson_tag_id"]),
                        "name": name,
                        "sort_order": int(row.get("sort_no") or 0),
                    },
                    natural_key=("tenant_id", "lesson_tag_id"),
                    source_key=int(row["lesson_tag_id"]),
                )
            )
        return records


class CourseTagLinksStep(Step):
    """`lesson_lesson_tag` を `course_tag_links` に移す。

    **`tenant_id` を持たないので講座と join して絞る。** 絞らないと他テナントの
    割当を拾う。**タグ側のテナントでは絞れない** — 割当が指しているのは講座なので、
    講座のテナントが正。
    """

    name = "content.course_tag_links"
    description = "講座とタグの対応を移す"
    source_table = "lesson_lesson_tag"
    target_table = "course_tag_links"
    depends_on = ("content.courses", "content.course_tags")

    def extract(self, ctx: RunContext) -> list[dict]:
        return ctx.require_source().fetch_joined(
            "lesson_lesson_tag",
            TAG_LINK_COLUMNS,
            parent="lesson",
            on="c.lesson_id = p.lesson_id",
        )

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        records: list[Record] = []
        for row in rows:
            key = (int(row["lesson_tag_id"]), int(row["lesson_id"]))
            records.append(
                Record(
                    table="course_tag_links",
                    values={
                        "id": ctx.ulid.for_row("lesson_lesson_tag", key),
                        "tenant_id": tenant_id,
                        "tag_id": ctx.ulid.for_row("lesson_tag", row["lesson_tag_id"]),
                        "course_id": ctx.ulid.for_row("lesson", row["lesson_id"]),
                    },
                    natural_key=("tag_id", "course_id"),
                    source_key=key,
                )
            )
        return records


def build() -> list[Step]:
    return [
        TenantCourseCategoriesStep(),
        CoursesStep(),
        CourseCategoryLinksStep(),
        CourseTagsStep(),
        CourseTagLinksStep(),
    ]
