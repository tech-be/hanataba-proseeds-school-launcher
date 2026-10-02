"""ondemand.5（前半）— アンケート定義（旧 `enquete` / `enquete_page` / `enquete_question`）。

**lw2 のアンケートはユニットに属さない。** `unit.enquete_id` が指す独立した定義で、
**同じアンケートを複数のユニットが参照できる**（ステージング実測で 7件）。
新環境の `survey_lessons` は `lesson_id` が主キーなので、**ユニットごとに複製して移す**。

複製するため、ページ・設問・選択肢の ULID は**レッスンごとに別**になる。
`survey_pages.enquete_page_id`（旧 ID）も同じ値がレッスンの数だけ現れるので、
**UNIQUE は `(tenant_id, lesson_id, enquete_page_id)` でなければならない**
（[schema-additions](../../../docs/db/02-ondemand/schema-additions.md) の M6 を参照）。
"""

from __future__ import annotations

from ...context import RunContext
from ...core.datetimes import ColumnKind, convert
from ...core.records import Record
from ...errors import MappingError
from ..base import Step

UNIT_ENQUETE_COLUMNS = ("unit_id", "lesson_id", "enquete_id", "open_datetime", "close_datetime")
ENQUETE_COLUMNS = ("enquete_id", "enquete_name", "enquete_type_id", "del_chk", "regist_date")
ENQUETE_PAGE_COLUMNS = (
    "enquete_page_id",
    "enquete_id",
    "enquete_type",
    "page_detail",
    "del_chk",
    "regist_date",
)
ENQUETE_QUESTION_COLUMNS = (
    "enquete_question_id",
    "enquete_page_id",
    "sort_no",
    "question_type",
    "required_chk",
    "question_text",
    "question_img_file_name",
    "selection_num",
    "del_chk",
    "regist_date",
)
_SELECTION_COLUMNS = tuple(f"selection{n}" for n in range(1, 21))

#: 旧 `enquete_question.question_type` → 新 `survey_questions.kind`。
#: 出どころは `Application_Constants_EnqueteConstants`（1=単一 2=複数 3=記述 4=添付）。
#: **`rating_5` / `rating_10` に当たる種別は lw2 に無い**ので使わない
QUESTION_KINDS: dict[int, str] = {
    1: "single_choice",
    2: "multiple_choice",
    3: "text_long",
    4: "file_upload",
}

#: 選択肢を持つ種別。記述・添付は `survey_question_options` を作らない
CHOICE_KINDS = frozenset({"single_choice", "multiple_choice"})


def _survey_units(ctx: RunContext, drop=None) -> list[dict]:
    """アンケートユニットと、それが指す定義を組み立てる。

    **`unit_type_id = 3` かつ `enquete_id` が入っているものだけ。** `0` は未設定。
    """
    source = ctx.require_source()
    units = source.fetch_joined(
        "unit",
        UNIT_ENQUETE_COLUMNS,
        parent="lesson",
        on="c.lesson_id = p.lesson_id",
        where="c.unit_type_id = 3 AND c.enquete_id IS NOT NULL AND c.enquete_id <> 0",
    )
    enquetes = {int(e["enquete_id"]): e for e in source.fetch_for_tenant("enquete", ENQUETE_COLUMNS)}
    rows: list[dict] = []
    for unit in units:
        enquete = enquetes.get(int(unit["enquete_id"]))
        if enquete is None:
            # **孤児**。アンケート定義が物理削除されている。親は復元できないので移さない。
            # **共有アンケート（tenant_id = 0）は `shared_enquetes` で拾うので、ここには来ない**
            if drop:
                drop("survey_lessons", unit["unit_id"], "旧データの不整合",
                     f"アンケートの定義（enquete_id={unit['enquete_id']}）が物理削除されている")
            continue
        rows.append({**unit, "_enquete": enquete})
    return rows


class SurveyLessonsStep(Step):
    """アンケートユニットを `survey_lessons` に移す。"""

    name = "content.survey_lessons"
    description = "アンケートの器をユニットごとに作る"
    source_table = "enquete"
    target_table = "survey_lessons"
    depends_on = ("content.lessons",)

    def extract(self, ctx: RunContext) -> list[dict]:
        return _survey_units(ctx, drop=self.drop)

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        shared: dict[int, int] = {}
        records: list[Record] = []
        for row in rows:
            enquete = row["_enquete"]
            shared[int(enquete["enquete_id"])] = shared.get(int(enquete["enquete_id"]), 0) + 1
            records.append(
                Record(
                    table="survey_lessons",
                    values={
                        "lesson_id": ctx.ulid.for_row("unit", row["unit_id"]),
                        "tenant_id": tenant_id,
                        "name": enquete.get("enquete_name"),
                        "open_at": convert(row.get("open_datetime"), ColumnKind.TIMESTAMP),
                        "close_at": convert(row.get("close_datetime"), ColumnKind.TIMESTAMP),
                        # 旧に匿名回答の設定が無い。既定の FALSE のまま
                        "anonymous_allowed": False,
                        "created_at": convert(enquete.get("regist_date"), ColumnKind.TIMESTAMP),
                    },
                    natural_key=("lesson_id",),
                    source_key=int(row["unit_id"]),
                )
            )
        duplicated = {e: n for e, n in shared.items() if n > 1}
        if duplicated:
            ctx.logger.warning(
                "複数のユニットが同じアンケートを参照している: %d 件。"
                "**ユニットごとに複製して移す**ので、以後の編集は連動しない",
                len(duplicated),
            )
        return records


class SurveyPagesStep(Step):
    """`enquete_page` をレッスンごとに複製して移す。"""

    name = "content.survey_pages"
    description = "アンケートのページを移す"
    source_table = "enquete_page"
    target_table = "survey_pages"
    depends_on = ("content.survey_lessons",)

    def extract(self, ctx: RunContext) -> list[dict]:
        source = ctx.require_source()
        pages = source.fetch_joined(
            "enquete_page",
            ENQUETE_PAGE_COLUMNS,
            parent="enquete",
            on="c.enquete_id = p.enquete_id",
        )
        by_enquete: dict[int, list[dict]] = {}
        for page in sorted(pages, key=lambda r: int(r["enquete_page_id"])):
            by_enquete.setdefault(int(page["enquete_id"]), []).append(page)
        rows: list[dict] = []
        for unit in _survey_units(ctx):
            for order, page in enumerate(by_enquete.get(int(unit["enquete_id"]), []), start=1):
                rows.append({**page, "_unit_id": unit["unit_id"], "_sort": order})
        return rows

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        return [
            Record(
                table="survey_pages",
                values={
                    "id": page_ulid(ctx, row["_unit_id"], row["enquete_page_id"]),
                    "tenant_id": tenant_id,
                    "lesson_id": ctx.ulid.for_row("unit", row["_unit_id"]),
                    "enquete_page_id": int(row["enquete_page_id"]),
                    "sort_order": int(row["_sort"]),
                    # 旧はページ名を持たず説明文だけ。200文字に収まらないものは切らずに
                    # NULL にする（本文は設問側に残る）
                    "title": _fit(row.get("page_detail"), 200),
                    "created_at": convert(row.get("regist_date"), ColumnKind.TIMESTAMP),
                },
                natural_key=("id",),
                source_key=int(row["enquete_page_id"]),
            )
            for row in rows
        ]


class SurveyQuestionsStep(Step):
    """`enquete_question` をレッスンごとに複製して移す。"""

    name = "content.survey_questions"
    description = "アンケートの設問を移す"
    source_table = "enquete_question"
    target_table = "survey_questions"
    depends_on = ("content.survey_pages",)

    def extract(self, ctx: RunContext) -> list[dict]:
        source = ctx.require_source()
        questions = source.fetch_joined(
            "enquete_question",
            ENQUETE_QUESTION_COLUMNS + _SELECTION_COLUMNS,
            parent="enquete",
            on="p2.enquete_id = p.enquete_id",
            via=[("enquete_page", "p2", "c.enquete_page_id = p2.enquete_page_id")],
        )
        pages = {
            int(p["enquete_page_id"]): p
            for p in source.fetch_joined(
                "enquete_page",
                ENQUETE_PAGE_COLUMNS,
                parent="enquete",
                on="c.enquete_id = p.enquete_id",
            )
        }
        by_enquete: dict[int, list[dict]] = {}
        for question in questions:
            page = pages.get(int(question["enquete_page_id"]))
            if page is None:
                # 通らない: 設問は enquete_page → enquete で絞って読むので、ページの無い設問は読めない
                # （テナントで絞れないので、このテナントの行かも分からない）
                continue
            by_enquete.setdefault(int(page["enquete_id"]), []).append(question)
        rows: list[dict] = []
        for unit in _survey_units(ctx):
            for question in by_enquete.get(int(unit["enquete_id"]), []):
                rows.append({**question, "_unit_id": unit["unit_id"]})
        return rows

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        records: list[Record] = []
        for row in rows:
            kind = _kind(row)
            records.append(
                Record(
                    table="survey_questions",
                    values={
                        "id": question_ulid(ctx, row["_unit_id"], row["enquete_question_id"]),
                        "tenant_id": tenant_id,
                        "lesson_id": ctx.ulid.for_row("unit", row["_unit_id"]),
                        "page_id": page_ulid(ctx, row["_unit_id"], row["enquete_page_id"]),
                        "sort_order": int(row.get("sort_no") or 0),
                        "kind": kind,
                        "prompt": row.get("question_text") or "",
                        "description": None,
                        "required": bool(int(row.get("required_chk") or 0)),
                        "max_length": None,  # 旧に入力上限が無い
                        "image_url": None,   # L9 の移送待ち
                        "created_at": convert(row.get("regist_date"), ColumnKind.TIMESTAMP),
                    },
                    natural_key=("id",),
                    source_key=int(row["enquete_question_id"]),
                )
            )
        return records


class SurveyQuestionOptionsStep(Step):
    """選択肢を横持ち（`selection1..20`）から縦持ちへ展開する。"""

    name = "content.survey_question_options"
    description = "アンケートの選択肢を縦持ちに展開する"
    source_table = "enquete_question"
    target_table = "survey_question_options"
    depends_on = ("content.survey_questions",)

    def extract(self, ctx: RunContext) -> list[dict]:
        return SurveyQuestionsStep().extract(ctx)

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        records: list[Record] = []
        for row in rows:
            if _kind(row) not in CHOICE_KINDS:
                continue
            question_id = question_ulid(ctx, row["_unit_id"], row["enquete_question_id"])
            for number in range(1, int(row.get("selection_num") or 0) + 1):
                label = row.get(f"selection{number}")
                if label is None:
                    continue
                records.append(
                    Record(
                        table="survey_question_options",
                        values={
                            "id": ctx.ulid.for_row(
                                "enquete_selection", f"{question_id}:{number}"
                            ),
                            "tenant_id": tenant_id,
                            "question_id": question_id,
                            # **255文字で切り捨てない。** 超えたら制約に当たって移らない
                            "label": label,
                            "sort_order": number,
                            "image_url": None,  # L9 の移送待ち
                        },
                        natural_key=("id",),
                        source_key=int(row["enquete_question_id"]),
                    )
                )
        return records


# --- 小道具 -----------------------------------------------------------------


def page_ulid(ctx: RunContext, unit_id: object, page_id: object) -> str:
    """**レッスンごとに別の ULID。** 同じページが複数のユニットに複製されるため。"""
    return ctx.ulid.for_row("enquete_page", f"{int(unit_id)}:{int(page_id)}")


def question_ulid(ctx: RunContext, unit_id: object, question_id: object) -> str:
    return ctx.ulid.for_row("enquete_question", f"{int(unit_id)}:{int(question_id)}")


def _kind(row: dict) -> str:
    """**対応表に無い種別は止める。** 黙って記述式に倒すと回答の持ち方が変わる。"""
    type_id = int(row["question_type"])
    if type_id not in QUESTION_KINDS:
        raise MappingError(
            f"enquete_question.question_type {type_id} が対応表に無い"
            f"（enquete_question_id={row['enquete_question_id']}）"
        )
    return QUESTION_KINDS[type_id]


def _fit(value: object, limit: int) -> str | None:
    """収まらない値は**切り捨てずに NULL**。切ると中途半端な文が残る。"""
    if value is None:
        return None
    text = str(value)
    return text if len(text) <= limit else None


def build() -> list[Step]:
    return [
        SurveyLessonsStep(),
        SurveyPagesStep(),
        SurveyQuestionsStep(),
        SurveyQuestionOptionsStep(),
    ]
