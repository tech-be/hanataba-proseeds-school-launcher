"""content.5 — コース（旧の講座の販売商品）。

school-launcher は「コース（`learning_paths`）＝旧の販売商品（`payment_item`）」という作りにした
（20261009113244。講座はコースを通して売る）。商品の定義をここで移す（2026-10-22 決定）。
購入の記録（`learning_path_enrollments`）は受講・課金の区分で扱う。

- `payment_item`（`item_type = 0` 講座）→ `learning_paths`
- `payment_item_lesson` → `learning_path_courses`

読み方は課金（`billing.payments` の `items` / `course_item_links`）と同じものを使う。
"""

from __future__ import annotations

from ...context import RunContext
from ...core.datetimes import ColumnKind, convert
from ...core.records import Record
from ..base import Step
from ..billing.payments import COURSE_ITEM, course_item_links, items

#: 旧 `manual_term_type`（`PaymentItemController.php:737`）→ (新の単位, 掛ける数)。
#: 新は日・月しか持たないので、**週は 7 日、年は 12 ヶ月**に直す（意味は変わらない）。
#: 4（期限なし）は無期限
TERM_UNITS: dict[int, tuple[str, int] | None] = {
    0: ("day", 1),
    1: ("day", 7),
    2: ("month", 1),
    3: ("month", 12),
    4: None,
}


def access_period(row: dict) -> tuple[int | None, str | None]:
    """受講期間（数, 単位）。**無期限は (None, None)**（新の CHECK は両方 NULL か両方あり）。

    - `no_limit_chk = 1` は無期限（ステージングでは種類 3・100 年のまま印だけ立っている）
    - 種類が NULL の商品は自動継続（月額）で、旧も期間を持たない。無期限として入れる
    - 数が 0 / NULL で種類があるものは、旧でも期間が決まらない。**作り替えず、数を None のまま渡す**
      （CHECK に当たって一覧に出る）
    """
    if int(row.get("no_limit_chk") or 0) == 1:
        return None, None
    kind = row.get("manual_term_type")
    if kind is None:
        return None, None
    unit = TERM_UNITS.get(int(kind), ("?", 0))
    if unit is None:
        return None, None
    term = int(row.get("manual_term") or 0)
    if term <= 0 or unit[0] == "?":
        return None, unit[0]
    return term * unit[1], unit[0]


def _status(row: dict) -> str:
    """削除済み・無効 → `archived`、有効 → `published`。

    **削除済みも `archived`**（2026-10-26 決定。02 の移行仕様 0-3 の Q1）。新のコースの状態は
    draft / published / archived だけで、`deleted` は画面と API が扱えない。
    """
    if int(row.get("del_chk") or 0) == 1:
        return "archived"
    return "published" if int(row.get("valid_chk") or 0) == 1 else "archived"


class LearningPathsStep(Step):
    """講座の商品（`item_type = 0`）を `learning_paths` に移す。

    **`display_chk = 2`（一覧と購入画面に出さない）は `listed = FALSE` にしかならない。** 新は一覧に
    出さなくても申込フォームの URL から申し込める。「購入画面に出さない」を表す列は無い（ステージング 2 件）。
    `extension_type`（期限切れの後も延長できるか）も受け皿が無い。
    """

    name = "content.learning_paths"
    description = "講座の販売商品をコースとして移す"
    source_table = "payment_item"
    target_table = "learning_paths"
    depends_on = ("tenant",)

    def extract(self, ctx: RunContext) -> list[dict]:
        return [r for r in items(ctx).values() if int(r.get("item_type") or 0) == COURSE_ITEM]

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        records: list[Record] = []
        for row in sorted(rows, key=lambda r: int(r["item_id"])):
            value, unit = access_period(row)
            extension = row.get("extension_price")
            records.append(
                Record(
                    table="learning_paths",
                    values={
                        "id": ctx.ulid.for_row("learning_path", row["item_id"]),
                        "tenant_id": tenant_id,
                        "title": row.get("item_name"),
                        "description": row.get("description"),
                        "sort_order": int(row.get("sort_no") or 0),
                        "status": _status(row),
                        # **税込**（コメントの「税抜」は誤り。billing.payments と同じ）
                        "price": row.get("price"),
                        "currency": "JPY",
                        "access_period_value": value,
                        "access_period_unit": unit,
                        "remote_pc_enabled": int(row.get("remote_chk") or 0) == 1,
                        # 旧の延長は、この料金で月額の自動継続に切り替える（`PaymentController.php:1026`）
                        "extension_fee": extension if extension else None,
                        # 1 表示する / 0 一覧に出さない / 2 一覧・購入画面に出さない
                        "listed": int(row.get("display_chk") or 0) == 1,
                        # 旧は商品の中の講座に受講の順を付けない（順はユニットの前提条件で、講座の中の話）
                        "sequential": False,
                        "created_at": convert(row.get("regist_date"), ColumnKind.TIMESTAMP),
                    },
                    natural_key=("id",),
                    source_key=int(row["item_id"]),
                )
            )
        return records


class LearningPathCoursesStep(Step):
    """商品と講座の結び付き（`payment_item_lesson`）を `learning_path_courses` に移す。

    **削除済みの結び付きは移さず一覧に出す**（2026-10-23 決定。移行対象外）。新もコースから外した講座の
    結び付きは物理削除で、持たない（`learning_path_repo.go` の `Remove`）。入れると、外した講座まで購入で
    受講できるようになる（ステージングは 985 件中 619 件が削除済み）。誰に何を渡したかは
    `learning_path_enrollment_courses`（受講 03）に、外した講座も含めて残している。
    """

    name = "content.learning_path_courses"
    description = "コースの講座を移す（削除済みの結び付きは一覧へ）"
    source_table = "payment_item_lesson"
    target_table = "learning_path_courses"
    depends_on = ("content.learning_paths", "content.courses")

    def extract(self, ctx: RunContext) -> list[dict]:
        def drop(key: str, reason: str, detail: str) -> None:
            self.drop("learning_path_courses", key, reason, detail)

        out = []
        for link in course_item_links(ctx, drop):
            if not link["_alive"]:
                drop(f"{link['item_id']}:{link['lesson_id']}", "移行対象外",
                     "削除済みの結び付き（コースから外した講座）。新でも外した結び付きは持たない")
                continue
            out.append(link)
        return out

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        return [
            Record(
                table="learning_path_courses",
                values={
                    "id": ctx.ulid.for_row("learning_path_course", f"{row['item_id']}:{row['lesson_id']}"),
                    "tenant_id": tenant_id,
                    "learning_path_id": ctx.ulid.for_row("learning_path", row["item_id"]),
                    "course_id": ctx.ulid.for_row("lesson", row["lesson_id"]),
                    # 旧は商品の中の講座に並びを持たない。旧の結び付きの登録順にする
                    "sort_order": int(row.get("item_set_lesson_id") or 0),
                },
                natural_key=("tenant_id", "learning_path_id", "course_id"),
                source_key=f"{row['item_id']}:{row['lesson_id']}",
            )
            for row in rows
        ]


def build() -> list[Step]:
    return [LearningPathsStep(), LearningPathCoursesStep()]
