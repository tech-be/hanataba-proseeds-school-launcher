"""content.1 — 講座のカテゴリ・講座本体・講座タグ。

- `lesson_cate` → `course_categories`（**テナントを持たないルックアップ**）
- `lesson` → `courses`
- `lesson_tag` / `lesson_lesson_tag` → `course_tags` / `course_tag_links`

**削除済み（`del_chk=1`）の講座も移す。** `status='deleted'` で表現する
（`content_statuses` に `deleted` を足してある）。
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


def category_code(ctx: RunContext, legacy_id: object, legacy_tenant: object = None) -> str | None:
    """`course_categories` はコードが主キー。**旧 ID からコードを組み立てる。**

    テナントを持たないルックアップなので、テナントをまたいで衝突しないよう
    **移行対象テナントの旧 ID を混ぜる**（共有カテゴリも、このテナントのものとして移す）。

    **`0` は「分類なし」** で NULL（旧 `lesson_cate` は 1 始まり）。
    """
    if legacy_id is None or int(legacy_id) == 0:
        return None
    return f"lw2-{ctx.config.tenant.legacy_id}-{int(legacy_id)}"


class CourseCategoriesStep(Step):
    """講座カテゴリを `course_categories` に移す。

    **新環境はコード主キーのルックアップ**で、テナントを持たない。旧はテナントごとに
    持っているため、**コードに旧テナント ID を混ぜて衝突を避ける**。

    **`tenant_id = 0` は共有カテゴリ。** lw2 は
    `LC.tenant_id = 0 OR LC.tenant_id = :TENANT_ID` で引いており、他テナントからも使える。
    recademy の講座8件がこれを参照しているので、**参照されている共有カテゴリも移す**
    （移さないと、その講座ごと移らない）。
    """

    name = "content.course_categories"
    description = "講座カテゴリを移す"
    source_table = "lesson_cate"
    target_table = "course_categories"
    depends_on = ("tenant",)

    def extract(self, ctx: RunContext) -> list[dict]:
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
                ctx.logger.info(
                    "共有カテゴリ（tenant_id=0）を移す: %s %s",
                    row["lesson_cate_id"],
                    row.get("lesson_cate_name"),
                )
        return rows

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        records: list[Record] = []
        for row in rows:
            deleted = int(row.get("del_chk") or 0) == 1
            records.append(
                Record(
                    table="course_categories",
                    values={
                        "code": category_code(ctx, row["lesson_cate_id"]),
                        "name_ja": row.get("lesson_cate_name"),
                        "name_en": None,
                        "parent_code": None,  # 旧に階層は無い
                        "icon": None,
                        # 画像は L9 のファイル移送後に URL を入れる
                        "image_url": None,
                        "created_by": None,
                        "sort_order": int(row.get("sort_no") or 0),
                        "is_system": False,
                        "active": not deleted,
                        "deprecated_at": None,
                    },
                    natural_key=("code",),
                    source_key=int(row["lesson_cate_id"]),
                )
            )
        return records


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
    depends_on = ("tenant", "content.course_categories", "content.proxy_instructor")

    def extract(self, ctx: RunContext) -> list[dict]:
        return ctx.require_source().fetch_for_tenant("lesson", LESSON_COLUMNS)

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
                        "legacy_id": int(row["lesson_id"]),
                        "title": title,
                        "description": row.get("description"),
                        "category": category_code(ctx, row.get("lesson_cate_id")),
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
                        "is_used": int(row.get("sales_status") or 0) == 1,
                        "settings": _settings(row),
                        "created_at": convert(row.get("regist_date"), ColumnKind.TIMESTAMP),
                    },
                    natural_key=("tenant_id", "legacy_id"),
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

    **元の列は残す**（`is_used`）。status は判定結果で、ここに畳むわけではない。
    """
    if int(row.get("del_chk") or 0) == 1:
        return "deleted"
    return "published" if int(row.get("sales_status") or 0) == 1 else "draft"


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
    return json.dumps({"features": flags}, ensure_ascii=False)


class CourseTagsStep(Step):
    """`lesson_tag` を `course_tags` に移す。

    **`category` では代用できない。** カテゴリは1講座に1件だが、タグは複数付く
    （実測 19 タグ / 59 割当）。削除済み（`del_chk=1`）のタグも移す —
    割当が残っている以上、名前が引けないと割当が意味を失う。
    """

    name = "content.course_tags"
    description = "講座タグを移す"
    source_table = "lesson_tag"
    target_table = "course_tags"
    depends_on = ("tenant",)

    def extract(self, ctx: RunContext) -> list[dict]:
        return ctx.require_source().fetch_for_tenant("lesson_tag", TAG_COLUMNS)

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
                        "legacy_id": int(row["lesson_tag_id"]),
                        "name": name,
                        "sort_order": int(row.get("sort_no") or 0),
                    },
                    natural_key=("tenant_id", "legacy_id"),
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
    return [CourseCategoriesStep(), CoursesStep(), CourseTagsStep(), CourseTagLinksStep()]
