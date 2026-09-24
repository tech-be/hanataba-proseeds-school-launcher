"""ondemand.4 — テスト定義（旧 `test` / `test_sub` / `test_sub_question` / `question`）。

**lw2 と新環境で、テストの組み立て方が根本的に違う。**

lw2 は `question`（テナント直下の**共有問題バンク**）から、`test_sub` の
**出題条件**（カテゴリ × レベルから N 問）で問題を引く。**受験者ごとに出る問題が変わる。**
新環境は `quiz_questions` の固定リストが基本。

**条件を固定リストに展開しない**（[review.md](../../../docs/db/02-ondemand/review.md) の A6）。
展開すると「受験者ごとに違う問題が出ていた」という事実が再現できなくなる。代わりに

- `question`      → `quiz_question_banks`（問題の本体）
- `question_cate` → `quiz_question_categories`
- `test_sub`      → `quiz_question_rules`（出題条件をそのまま）
- `test_sub_question` → `quiz_questions`（**固定出題ぶんだけ**。バンクへの参照）

**`test_sub_type_id` で意味が変わる**（`UserLearningLessonModel::208-275`）。

- `0` 固定問題よりそのまま出題 … `test_sub_question` の順に N 問
- `1` 固定問題よりランダム出題 … `test_sub_question` からランダムに N 問
- `2` カテゴリなどの範囲からランダム出題 … `question_cate_id` / `question_level_id` で引く

0 と 1 は `test_sub_question` に実体があるので `quiz_questions` にも入れる。
2 は実体が無く、条件だけを `quiz_question_rules` に残す。
"""

from __future__ import annotations

import json

from ...context import RunContext
from ...core.datetimes import ColumnKind, convert
from ...core.records import Record
from ...errors import MappingError
from ..base import Step

QUESTION_CATE_COLUMNS = (
    "question_cate_id",
    "question_cate_name",
    "sort_no",
    "del_chk",
    "regist_date",
)

#: `question` は58列あるが、**選択肢の画像20列は L9 の移送待ち**なので読まない。
#: 本文・正解・ヒント・分類だけを読む（選択肢は `_SELECTION_COLUMNS`）
QUESTION_COLUMNS = (
    "question_id",
    "question_cate_id",
    "question_level_id",
    "question_type_id",
    "require_chk",
    "question_name",
    "question_text",
    "question_img_file_name",
    "hint",
    "answer",
    "answer_explanation",
    "answer_explanation_img_file_name",
    "selection_num",
    "del_chk",
    "regist_date",
    "update_date",
)
_SELECTION_COLUMNS = tuple(f"selection{n}" for n in range(1, 21))

TEST_COLUMNS = (
    "test_id",
    "unit_id",
    "test_type_id",
    "pass_score",
    "exam_max_number",
    "exam_limit_times",
    "exam_pre_message",
    "suspended_chk",
    "ranking_chk",
    "repeat_chk",
    "disp_question_count",
    "test_result_disp_chk",
    "test_score_disp_chk",
    "error_disp_chk",
    "answer_disp_chk",
    "comment_disp_chk",
    "test_start_time",
    "del_chk",
    "regist_date",
    "update_date",
)

TEST_SUB_COLUMNS = (
    "test_sub_id",
    "test_id",
    "test_sub_type_id",
    "sort_no",
    "question_cate_id",
    "question_level_id",
    "set_question_no",
    "distribution_factor",
    "score_per_question",
    "random_option",
    "del_chk",
)

TEST_SUB_QUESTION_COLUMNS = ("test_sub_question_id", "test_sub_id", "question_id", "sort_no", "del_chk")

#: 旧 `question.question_type_id` → 新 `quiz_questions.type`（`quiz_question_types.code`）。
#: 出どころは `QuestionController::1160`
QUESTION_TYPES: dict[int, str] = {
    1: "single_choice",
    2: "multiple_choice",
    3: "text_free",
}

#: `test_sub_type_id` のうち、`test_sub_question` に問題の実体を持つもの。
#: `2`（カテゴリ範囲からランダム）は実体が無く、条件だけが残る
FIXED_SUB_TYPES = frozenset({0, 1})

#: **`unit` → `lesson` で絞るときの経路。** `test` も `test_sub` も `tenant_id` を持たない
_VIA_UNIT = [("unit", "u", "c.unit_id = u.unit_id")]


class QuizQuestionCategoriesStep(Step):
    """問題カテゴリを移す。**出題条件（`quiz_question_rules`）の参照先**なので先に入れる。"""

    name = "content.quiz_question_categories"
    description = "問題カテゴリを移す（出題条件の参照先）"
    source_table = "question_cate"
    target_table = "quiz_question_categories"
    depends_on = ("content.lessons",)

    def extract(self, ctx: RunContext) -> list[dict]:
        return ctx.require_source().fetch_for_tenant("question_cate", QUESTION_CATE_COLUMNS)

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        return [
            Record(
                table="quiz_question_categories",
                values={
                    "id": ctx.ulid.for_row("question_cate", row["question_cate_id"]),
                    "tenant_id": tenant_id,
                    "legacy_id": int(row["question_cate_id"]),
                    "name": row.get("question_cate_name"),
                    "sort_order": int(row.get("sort_no") or 0),
                    "created_at": convert(row.get("regist_date"), ColumnKind.TIMESTAMP),
                },
                natural_key=("tenant_id", "legacy_id"),
                source_key=int(row["question_cate_id"]),
            )
            for row in rows
        ]


class QuizQuestionBanksStep(Step):
    """`question` を問題バンクに移す。**問題の本体はここ。**

    lw2 の `question` は**テストに属さない共有バンク**で、同じ問題を複数のテストが
    引く。テストごとに複製すると総数が膨らみ、以後の編集も分岐するため、
    本体はバンクに1件だけ置き、`quiz_questions` から参照する。
    """

    name = "content.quiz_question_banks"
    description = "共有問題バンクを移す（問題の本体）"
    source_table = "question"
    target_table = "quiz_question_banks"
    depends_on = ("content.quiz_question_categories",)

    def extract(self, ctx: RunContext) -> list[dict]:
        return ctx.require_source().fetch_for_tenant("question", QUESTION_COLUMNS + _SELECTION_COLUMNS)

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        records: list[Record] = []
        for row in rows:
            _check_type(row)
            records.append(
                Record(
                    table="quiz_question_banks",
                    values={
                        "id": ctx.ulid.for_row("question", row["question_id"]),
                        "tenant_id": tenant_id,
                        "legacy_id": int(row["question_id"]),
                        "category_id": _category_id(ctx, row.get("question_cate_id")),
                        "level": row.get("question_level_id"),
                        "name": row.get("question_name"),
                        "body": row.get("question_text") or "",
                        "hint": row.get("hint"),
                        # 画像は L9 でファイルを移送してから URL を入れる。
                        # **ファイル名のままでは表示できない**ので、移送前は空にする
                        "image_url": None,
                        "explanation_image_url": None,
                        "created_at": convert(row.get("regist_date"), ColumnKind.TIMESTAMP),
                    },
                    natural_key=("tenant_id", "legacy_id"),
                    source_key=int(row["question_id"]),
                )
            )
        pending_images = sum(
            1
            for r in rows
            if (r.get("question_img_file_name") or r.get("answer_explanation_img_file_name"))
        )
        if pending_images:
            ctx.logger.warning(
                "画像を持つ問題が %d 件ある。**L9 でファイルを移送するまで `image_url` は空**",
                pending_images,
            )
        return records


class QuizzesStep(Step):
    """`test` を `quizzes` に移す。

    **`UNIQUE (tenant_id, lesson_id)` があるので、1ユニットに複数のテストがあると
    2件目以降は移らない**（制約は緩めない。2026-09-23 決定）。
    """

    name = "content.quizzes"
    description = "テストを移す（制限時間は分→秒に換算）"
    source_table = "test"
    target_table = "quizzes"
    depends_on = ("content.quiz_question_banks",)

    def extract(self, ctx: RunContext) -> list[dict]:
        return ctx.require_source().fetch_joined(
            "test", TEST_COLUMNS, parent="lesson", on="u.lesson_id = p.lesson_id", via=_VIA_UNIT
        )

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        records: list[Record] = []
        duplicated: dict[int, int] = {}
        for row in rows:
            unit_id = int(row["unit_id"])
            duplicated[unit_id] = duplicated.get(unit_id, 0) + 1
            records.append(
                Record(
                    table="quizzes",
                    values={
                        "id": ctx.ulid.for_row("test", row["test_id"]),
                        "tenant_id": tenant_id,
                        "lesson_id": ctx.ulid.for_row("unit", unit_id),
                        # 旧 `test` にテスト名が無い。ユニット名が画面の見出しになる
                        "title": "",
                        "description": row.get("exam_pre_message"),
                        "passing_score": int(row.get("pass_score") or 0),
                        # **旧は分、新は秒。** 換算を落とすと制限時間が 1/60 になる
                        "time_limit_sec": _minutes_to_sec(row.get("exam_limit_times")),
                        "max_attempts": _positive(row.get("exam_max_number")),
                        "suspend_enabled": bool(int(row.get("suspended_chk") or 0)),
                        "display_settings": _display_settings(row),
                        "created_at": convert(row.get("regist_date"), ColumnKind.TIMESTAMP),
                    },
                    natural_key=("tenant_id", "lesson_id"),
                    source_key=int(row["test_id"]),
                )
            )
        extra = {u: n for u, n in duplicated.items() if n > 1}
        if extra:
            ctx.logger.warning(
                "1ユニットに複数のテストがあるユニットが %d 件ある（%s）。"
                "`quizzes` は UNIQUE (tenant_id, lesson_id) なので**2件目以降は移らない**",
                len(extra),
                dict(list(extra.items())[:5]),
            )
        return records


class QuizQuestionRulesStep(Step):
    """`test_sub` を出題条件として移す。**固定リストに展開しない。**"""

    name = "content.quiz_question_rules"
    description = "出題条件（カテゴリ×レベルから N 問）を移す"
    source_table = "test_sub"
    target_table = "quiz_question_rules"
    depends_on = ("content.quizzes",)

    def extract(self, ctx: RunContext) -> list[dict]:
        return ctx.require_source().fetch_joined(
            "test_sub",
            TEST_SUB_COLUMNS,
            parent="lesson",
            on="u.lesson_id = p.lesson_id",
            via=[
                ("test", "t", "c.test_id = t.test_id"),
                ("unit", "u", "t.unit_id = u.unit_id"),
            ],
        )

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        records: list[Record] = []
        for row in rows:
            sub_type = int(row.get("test_sub_type_id") or 0)
            # 条件で引くのは type 2 だけ。0/1 は固定リストなのでカテゴリを持たせない
            # （持たせると「カテゴリから引く条件」と区別が付かなくなる）
            ranged = sub_type == 2
            records.append(
                Record(
                    table="quiz_question_rules",
                    values={
                        "id": ctx.ulid.for_row("test_sub", row["test_sub_id"]),
                        "tenant_id": tenant_id,
                        "quiz_id": ctx.ulid.for_row("test", row["test_id"]),
                        "category_id": _category_id(ctx, row.get("question_cate_id")) if ranged else None,
                        "level": row.get("question_level_id") if ranged else None,
                        "question_count": int(row.get("set_question_no") or 0),
                        "score_per_question": _positive(row.get("score_per_question")),
                        "distribution_factor": row.get("distribution_factor"),
                        "random_option": bool(int(row.get("random_option") or 0)),
                        "sort_order": int(row.get("sort_no") or 0),
                    },
                    natural_key=("id",),
                    source_key=int(row["test_sub_id"]),
                )
            )
        return records


class QuizQuestionsStep(Step):
    """`test_sub_question` を `quiz_questions` に移す（**固定出題ぶんだけ**）。

    **旧 ID を引き継がない。** `test_sub_question_id` は採番が枯渇していて履歴も
    断裂しているため（`lw2-migration-tables.md`）、`(test_id, question_id, 並び順)` から
    決定論 ULID を採番する。

    `body` / `type` はバンク（`question`）から写す。`quiz_questions.body` が
    NOT NULL で、表示のたびにバンクを引かなくて済むようにするため。
    """

    name = "content.quiz_questions"
    description = "固定出題の設問を移す（本体は問題バンクを参照）"
    source_table = "test_sub_question"
    target_table = "quiz_questions"
    depends_on = ("content.quiz_question_rules",)

    def extract(self, ctx: RunContext) -> list[dict]:
        source = ctx.require_source()
        links = source.fetch_joined(
            "test_sub_question",
            TEST_SUB_QUESTION_COLUMNS,
            parent="lesson",
            on="u.lesson_id = p.lesson_id",
            via=[
                ("test_sub", "s", "c.test_sub_id = s.test_sub_id"),
                ("test", "t", "s.test_id = t.test_id"),
                ("unit", "u", "t.unit_id = u.unit_id"),
            ],
        )
        subs = {
            int(s["test_sub_id"]): s
            for s in source.fetch_joined(
                "test_sub",
                TEST_SUB_COLUMNS,
                parent="lesson",
                on="u.lesson_id = p.lesson_id",
                via=[
                    ("test", "t", "c.test_id = t.test_id"),
                    ("unit", "u", "t.unit_id = u.unit_id"),
                ],
            )
        }
        questions = {
            int(q["question_id"]): q
            for q in source.fetch_for_tenant("question", QUESTION_COLUMNS + _SELECTION_COLUMNS)
        }
        rows: list[dict] = []
        for link in links:
            sub = subs.get(int(link["test_sub_id"]))
            question = questions.get(int(link["question_id"]))
            if sub is None or question is None:
                # 親が読めない行。**親が移らなければ子も移らない**ので落とす
                continue
            if int(sub.get("test_sub_type_id") or 0) not in FIXED_SUB_TYPES:
                continue
            rows.append({**link, "_sub": sub, "_question": question})
        return rows

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        records: list[Record] = []
        for row in rows:
            sub, question = row["_sub"], row["_question"]
            _check_type(question)
            sort_no = int(row.get("sort_no") or 0)
            records.append(
                Record(
                    table="quiz_questions",
                    values={
                        "id": _question_ulid(ctx, sub["test_sub_id"], row["question_id"], sort_no),
                        "tenant_id": tenant_id,
                        "quiz_id": ctx.ulid.for_row("test", sub["test_id"]),
                        "bank_id": ctx.ulid.for_row("question", row["question_id"]),
                        "body": question.get("question_text") or "",
                        "type": QUESTION_TYPES[int(question["question_type_id"])],
                        "points": int(sub.get("score_per_question") or 0) or 1,
                        "sort_order": sort_no,
                        "explanation": question.get("answer_explanation"),
                        "name": question.get("question_name"),
                        "hint": question.get("hint"),
                        "required": bool(int(question.get("require_chk") or 0)),
                        "image_url": None,  # L9 の移送待ち
                    },
                    natural_key=("id",),
                    source_key=int(row["test_sub_question_id"]),
                )
            )
        return records


class QuizOptionsStep(Step):
    """選択肢を横持ち（`selection1..20`）から縦持ち（`quiz_options`）へ展開する。

    **有効な数は `selection_num`。** 21列目以降は存在しないので見ない。
    正解は `question.answer` に**パイプ区切りの選択肢番号**で入っている
    （単一選択は `"2"`、複数選択は `"2|5"`）。**記述式（`text_free`）は選択肢が無く、
    `answer` は期待する文字列そのもの**なので展開しない。
    """

    name = "content.quiz_options"
    description = "選択肢を縦持ちに展開し、正解フラグを立てる"
    source_table = "question"
    target_table = "quiz_options"
    depends_on = ("content.quiz_questions",)

    def extract(self, ctx: RunContext) -> list[dict]:
        return QuizQuestionsStep().extract(ctx)

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        records: list[Record] = []
        no_options = 0
        for row in rows:
            sub, question = row["_sub"], row["_question"]
            question_type = QUESTION_TYPES[int(question["question_type_id"])]
            if question_type == "text_free":
                continue  # 選択肢を持たない
            correct = _correct_numbers(question.get("answer"))
            count = int(question.get("selection_num") or 0)
            if count <= 0:
                no_options += 1
                continue
            question_ulid = _question_ulid(
                ctx, sub["test_sub_id"], row["question_id"], int(row.get("sort_no") or 0)
            )
            for number in range(1, count + 1):
                body = question.get(f"selection{number}")
                if body is None:
                    continue
                records.append(
                    Record(
                        table="quiz_options",
                        values={
                            "id": ctx.ulid.for_row(
                                "question_selection", f"{question_ulid}:{number}"
                            ),
                            "tenant_id": tenant_id,
                            "question_id": question_ulid,
                            "body": body,
                            "is_correct": number in correct,
                            "sort_order": number,
                            "image_url": None,  # L9 の移送待ち
                        },
                        natural_key=("id",),
                        source_key=int(question["question_id"]),
                    )
                )
        if no_options:
            ctx.logger.warning(
                "選択肢が0件の選択式問題が %d 件ある（`selection_num = 0`）。"
                "**旧データの時点で選べない問題**なので、選択肢は作らない",
                no_options,
            )
        return records


# --- 小道具 -----------------------------------------------------------------


def _question_ulid(ctx: RunContext, sub_id: object, question_id: object, sort_no: int) -> str:
    """**旧 `test_sub_question_id` は使わない。** 採番が枯渇・履歴断裂しているため、
    業務的な組み合わせから採番する（A6 / review.md）。

    **大問（`test_sub`）まで含める。** review.md は `(test_id, question_id, 並び順)` と
    書いているが、**同じテストの別の大問に同じ問題が入る**ことがあり（ステージングで1組）、
    テスト単位だと ULID が衝突して両方とも移らなくなる。lw2 の画面でも2問として出るので、
    **大問を含めるほうが元の構造に忠実**。
    """
    return ctx.ulid.for_row("test_sub_question", f"{int(sub_id)}:{int(question_id)}:{sort_no}")


def _category_id(ctx: RunContext, legacy_id: object) -> str | None:
    """問題カテゴリの ULID。**0 は「未分類」**なので NULL にする。"""
    if legacy_id is None or int(legacy_id) == 0:
        return None
    return ctx.ulid.for_row("question_cate", int(legacy_id))


def _check_type(question: dict) -> None:
    """**対応表に無い種別は止める。** 黙って単一選択に倒すと、採点が変わる。"""
    type_id = int(question["question_type_id"])
    if type_id not in QUESTION_TYPES:
        raise MappingError(
            f"question_type_id {type_id} が対応表に無い（question_id={question['question_id']}）。"
            "受け皿の種別を決めてから流す"
        )


def _correct_numbers(answer: object) -> set[int]:
    """`answer` を選択肢番号の集合にする。**区切りはパイプ。**"""
    if answer is None:
        return set()
    numbers: set[int] = set()
    for part in str(answer).split("|"):
        part = part.strip()
        if part.isdigit():
            numbers.add(int(part))
    return numbers


def _minutes_to_sec(value: object) -> int | None:
    """**旧は分、新は秒。** `0` は「制限なし」なので NULL。"""
    minutes = int(value or 0)
    return minutes * 60 if minutes > 0 else None


def _positive(value: object) -> int | None:
    """`0` を「未設定」として NULL に倒す（旧は既定値 0 で未設定を表す）。"""
    number = int(value or 0)
    return number if number > 0 else None


def _display_settings(row: dict) -> str:
    """**正解・解説・点数を見せるかの制御。** 新環境に個別の列が無いので json にまとめる。

    元のカラムコメントは cp932 が utf8 として取り込まれて文字化けしているが、
    列名から意味は読める（`test_result_disp_chk` = テストの合否表示 ほか）。
    """
    return json.dumps(
        {
            "test_type_id": row.get("test_type_id"),
            "ranking": bool(int(row.get("ranking_chk") or 0)),
            "repeat": bool(int(row.get("repeat_chk") or 0)),
            "questions_per_page": row.get("disp_question_count"),
            "show_result": bool(int(row.get("test_result_disp_chk") or 0)),
            "show_score": bool(int(row.get("test_score_disp_chk") or 0)),
            "show_errors": bool(int(row.get("error_disp_chk") or 0)),
            "show_answers": bool(int(row.get("answer_disp_chk") or 0)),
            "show_comments": bool(int(row.get("comment_disp_chk") or 0)),
            "start_time": str(row.get("test_start_time") or ""),
        },
        ensure_ascii=False,
    )


def build() -> list[Step]:
    """フェーズ4の Step 一式。**この順でないと FK が揃わない。**"""
    return [
        QuizQuestionCategoriesStep(),
        QuizQuestionBanksStep(),
        QuizzesStep(),
        QuizQuestionRulesStep(),
        QuizQuestionsStep(),
        QuizOptionsStep(),
    ]
