"""ondemand.6 — 受講者の実績（テスト受験・アンケート回答・課題提出）。

**会員は3段たどらないと分からない。** lw2 の実績は
`user_learning_lesson`（会員×講座）→ `user_learning_unit`（会員×ユニット）→
`user_learning_test` / `user_learning_report` とぶら下がっていて、
**実績テーブル自身は `user_id` も `tenant_id` も持たない**。

**新環境の実績は `enrollments` を参照しない**ので、受講区分（04）の移行を待たずに移せる。
必要な参照先は `users`（基盤）と `quizzes` / `survey_lessons` / `assignments`（フェーズ4・5）だけ。

**設問別の回答は、出題条件（`test_sub_type_id = 2`）ぶんが移らない。**
`user_learning_test_sub` は `question_id` しか持たず、どの大問から出た問題かを記録していない。
固定出題（0 / 1）なら `test_sub_question` から一意に引けるが、条件出題には
`quiz_questions` の行そのものが無い（条件だけを `quiz_question_rules` に移しているため）。
ステージング実測では 4,922件中 50件（1%）が該当する。
"""

from __future__ import annotations

import json

from ...context import RunContext
from ...core.datetimes import ColumnKind, convert
from ...core.records import Record
from ..base import Step
from ..content.assignments import MATERIAL_SLOTS
from ..content.instructors import PROXY_KEY
from ..content.quizzes import FIXED_SUB_TYPES, TEST_SUB_COLUMNS, TEST_SUB_QUESTION_COLUMNS, _question_ulid
from ..content.surveys import CHOICE_KINDS, QUESTION_KINDS, _survey_units, question_ulid

USER_LEARNING_TEST_COLUMNS = (
    "user_learning_test_id",
    "user_learning_unit_id",
    "test_start_time",
    "test_end_time",
    "test_score",
    "sum_score",
    "total_score",
    "test_pass",
    "test_time",
    "finished_chk",
    "del_chk",
    "regist_date",
)

USER_LEARNING_TEST_SUB_COLUMNS = (
    "user_learning_test_sub_id",
    "user_learning_test_id",
    "question_id",
    "sort_no",
    "question_pass",
    "question_score",
    "pre_question_pass",
    "option_order",
    "question_answer",
    "del_chk",
)

ENQUETE_ANSWER_COLUMNS = (
    "enquete_answer_id",
    "enquete_id",
    "entity_type_id",
    "entity_id",
    "enquete_reply_time",
    "answer",
    "suspended_chk",
    "del_chk",
    "regist_date",
    "update_date",
)

USER_LEARNING_REPORT_COLUMNS = (
    ("user_learning_report_id", "user_learning_unit_id", "report_id")
    + ("user_report_evaltext", "report_question_comment", "score")
    + tuple(f"eval_disp_file_name{n}" for n in MATERIAL_SLOTS)
    + tuple(f"eval_save_file_name{n}" for n in MATERIAL_SLOTS)
    + ("submit_date", "evaluate_date", "evaluate_user_id")
    + ("send_PC_chk", "send_mobile_chk", "del_chk", "regist_date")
)

#: 旧 `enquete_answer.entity_type_id` → 新 `survey_responses.entity_type`。
#: 出どころは `Application_Constants_EnqueteConstants`
ENTITY_TYPES: dict[int, str] = {1: "news", 2: "lesson", 3: "report"}


# --- 会員の引き当て -----------------------------------------------------------


def _learning_units(ctx: RunContext) -> dict[int, dict]:
    """`user_learning_unit_id` → 会員とユニット。**3段の join をここに閉じる。**"""
    source = ctx.require_source()
    lessons = {
        int(r["user_learning_lesson_id"]): r
        for r in source.fetch_joined(
            "user_learning_lesson",
            ("user_learning_lesson_id", "user_id", "lesson_id"),
            parent="user",
            on="c.user_id = p.user_id",
        )
    }
    units: dict[int, dict] = {}
    for unit in source.fetch_joined(
        "user_learning_unit",
        ("user_learning_unit_id", "user_learning_lesson_id", "unit_id"),
        parent="user",
        on="ull.user_id = p.user_id",
        via=[
            (
                "user_learning_lesson",
                "ull",
                "c.user_learning_lesson_id = ull.user_learning_lesson_id",
            )
        ],
    ):
        parent = lessons.get(int(unit["user_learning_lesson_id"]))
        if parent is None:
            continue  # 孤児。受講の親が物理削除されている
        units[int(unit["user_learning_unit_id"])] = {**unit, "_user_id": parent["user_id"]}
    return units


# --- テスト受験 ---------------------------------------------------------------


def _attempts(ctx: RunContext, drop=None) -> list[dict]:
    """受験に会員とテストを添える。`drop` を渡すと、引けない行を一覧に出す。"""
    source = ctx.require_source()
    units = _learning_units(ctx)
    tests = {
        int(t["unit_id"]): t
        for t in source.fetch_joined(
            "test",
            ("test_id", "unit_id"),
            parent="lesson",
            on="u.lesson_id = p.lesson_id",
            via=[("unit", "u", "c.unit_id = u.unit_id")],
        )
    }
    rows: list[dict] = []
    for attempt in source.fetch_joined(
        "user_learning_test",
        USER_LEARNING_TEST_COLUMNS,
        parent="user",
        on="ull.user_id = p.user_id",
        via=[
            ("user_learning_unit", "ulu", "c.user_learning_unit_id = ulu.user_learning_unit_id"),
            (
                "user_learning_lesson",
                "ull",
                "ulu.user_learning_lesson_id = ull.user_learning_lesson_id",
            ),
        ],
    ):
        unit = units.get(int(attempt["user_learning_unit_id"]))
        if unit is None:
            if drop:
                drop("quiz_attempts", attempt["user_learning_test_id"], "旧データの不整合",
                     "受講の行（user_learning_lesson）が物理削除されている")
            continue
        test = tests.get(int(unit["unit_id"]))
        if test is None:
            # ユニットにテストが無い（ユニットかテストの定義が旧で物理削除されている）
            if drop:
                drop("quiz_attempts", attempt["user_learning_test_id"], "旧データの不整合",
                     f"テストの定義を引けない（unit_id={unit['unit_id']} が物理削除）")
            continue
        rows.append({**attempt, "_user_id": unit["_user_id"], "_test_id": test["test_id"]})
    return rows


class QuizAttemptsStep(Step):
    """`user_learning_test` を `quiz_attempts` に移す。

    **点数の3列を取り違えない**（`UserLearningLessonModel::setUserLearningMark()`）。

    - `sum_score`   … 獲得点 → `score`
    - `total_score` … 満点   → `max_score`
    - `test_score`  … 百分率の**派生値**。移さない（採点処理で確定する）
    """

    name = "enrollment.quiz_attempts"
    description = "テストの受験結果を移す（当時の合否をそのまま）"
    source_table = "user_learning_test"
    target_table = "quiz_attempts"
    depends_on = ("content.quiz_options",)

    def extract(self, ctx: RunContext) -> list[dict]:
        return _attempts(ctx, drop=self.drop)

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        records: list[Record] = []
        for row in rows:
            # **`finished_chk` は使わない。** 同名の列は `user_learning_test_update`
            # （中断・再開）のもので、lw2 は `user_learning_test` 側を一度も更新しない
            # （`UserLearningLessonModel::updateUserLearningTestToFinished` が
            # 更新するのは `user_learning_test_update`）。ステージングでは 371件すべてが
            # `0` のまま、**全件に `test_end_time` があり271件が合格**している。
            # 受験が終わったかどうかは**終了時刻の有無**で判断する
            finished = row.get("test_end_time") is not None
            records.append(
                Record(
                    table="quiz_attempts",
                    values={
                        "id": ctx.ulid.for_row("user_learning_test", row["user_learning_test_id"]),
                        "tenant_id": tenant_id,
                        "user_id": ctx.ulid.for_row("user", row["_user_id"]),
                        "quiz_id": ctx.ulid.for_row("test", row["_test_id"]),
                        "score": int(row.get("sum_score") or 0),
                        "max_score": int(row.get("total_score") or 0),
                        "status": "completed" if finished else "abandoned",
                        "started_at": convert(row.get("test_start_time"), ColumnKind.TIMESTAMP),
                        "completed_at": convert(row.get("test_end_time"), ColumnKind.TIMESTAMP),
                        # **当時の合否をそのまま残す。** 都度計算に任せない（A9）
                        "passed": _flag(row.get("test_pass")),
                        "duration_sec": row.get("test_time"),
                    },
                    natural_key=("id",),
                    source_key=int(row["user_learning_test_id"]),
                )
            )
        return records


def _answer_rows(ctx: RunContext) -> list[dict]:
    """設問別の回答に、対応する `quiz_questions` の ULID を添える。

    **`user_learning_test_sub` はどの大問から出た問題かを持たない。**
    同じテストの固定出題（`test_sub_type_id` 0 / 1）から `question_id` で引き当てる。
    引けないもの（条件出題ぶん）は `quiz_questions` の行が無いので移せない。
    """
    source = ctx.require_source()
    attempts = {int(a["user_learning_test_id"]): a for a in _attempts(ctx)}

    subs = {
        int(s["test_sub_id"]): s
        for s in source.fetch_joined(
            "test_sub",
            TEST_SUB_COLUMNS,
            parent="lesson",
            on="u.lesson_id = p.lesson_id",
            via=[("test", "t", "c.test_id = t.test_id"), ("unit", "u", "t.unit_id = u.unit_id")],
        )
    }
    # (test_id, question_id) → 固定出題の行。**複数あれば引き当てない**（どれか決められない）
    fixed: dict[tuple[int, int], dict | None] = {}
    for link in source.fetch_joined(
        "test_sub_question",
        TEST_SUB_QUESTION_COLUMNS,
        parent="lesson",
        on="u.lesson_id = p.lesson_id",
        via=[
            ("test_sub", "s", "c.test_sub_id = s.test_sub_id"),
            ("test", "t", "s.test_id = t.test_id"),
            ("unit", "u", "t.unit_id = u.unit_id"),
        ],
    ):
        sub = subs.get(int(link["test_sub_id"]))
        if sub is None or int(sub.get("test_sub_type_id") or 0) not in FIXED_SUB_TYPES:
            continue
        key = (int(sub["test_id"]), int(link["question_id"]))
        fixed[key] = None if key in fixed else {**link, "_sub": sub}

    rows: list[dict] = []
    for answer in source.fetch_joined(
        "user_learning_test_sub",
        USER_LEARNING_TEST_SUB_COLUMNS,
        parent="user",
        on="ull.user_id = p.user_id",
        via=[
            ("user_learning_test", "ult", "c.user_learning_test_id = ult.user_learning_test_id"),
            (
                "user_learning_unit",
                "ulu",
                "ult.user_learning_unit_id = ulu.user_learning_unit_id",
            ),
            (
                "user_learning_lesson",
                "ull",
                "ulu.user_learning_lesson_id = ull.user_learning_lesson_id",
            ),
        ],
    ):
        attempt = attempts.get(int(answer["user_learning_test_id"]))
        if attempt is None:
            continue
        link = fixed.get((int(attempt["_test_id"]), int(answer["question_id"])))
        if link is None:
            continue  # 条件出題ぶん、または引き当てが一意でない
        rows.append({**answer, "_attempt": attempt, "_link": link})
    return rows


class QuizAnswersStep(Step):
    """`user_learning_test_sub` を `quiz_answers` に移す。"""

    name = "enrollment.quiz_answers"
    description = "設問別の回答と当時の正誤を移す"
    source_table = "user_learning_test_sub"
    target_table = "quiz_answers"
    depends_on = ("enrollment.quiz_attempts",)

    def extract(self, ctx: RunContext) -> list[dict]:
        rows = _answer_rows(ctx)
        ctx.logger.info("設問別の回答: %d 件を引き当てた", len(rows))
        return rows

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        return [
            Record(
                table="quiz_answers",
                values={
                    "id": ctx.ulid.for_row(
                        "user_learning_test_sub", row["user_learning_test_sub_id"]
                    ),
                    "tenant_id": tenant_id,
                    "attempt_id": ctx.ulid.for_row(
                        "user_learning_test", row["_attempt"]["user_learning_test_id"]
                    ),
                    "question_id": _answer_question_ulid(ctx, row),
                    # **当時の正誤をそのまま残す**（A10）
                    "is_correct": _flag(row.get("question_pass")),
                    "option_order": _fit(row.get("option_order"), 64),
                    "sort_no": row.get("sort_no"),
                    "pre_question_pass": _flag(row.get("pre_question_pass")),
                },
                natural_key=("id",),
                source_key=int(row["user_learning_test_sub_id"]),
            )
            for row in rows
        ]


class QuizAnswerSelectedOptionsStep(Step):
    """選んだ選択肢を `quiz_answer_selected_options` に展開する。

    **`question_answer` はパイプ区切りの選択肢番号**（正解列 `question.answer` と同じ形式）。
    記述式は選択肢を持たないので展開しない。
    """

    name = "enrollment.quiz_answer_selected_options"
    description = "選んだ選択肢を展開する"
    source_table = "user_learning_test_sub"
    target_table = "quiz_answer_selected_options"
    depends_on = ("enrollment.quiz_answers",)

    def extract(self, ctx: RunContext) -> list[dict]:
        return _answer_rows(ctx)

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        records: list[Record] = []
        for row in rows:
            question_ulid_value = _answer_question_ulid(ctx, row)
            answer_id = ctx.ulid.for_row(
                "user_learning_test_sub", row["user_learning_test_sub_id"]
            )
            for number in _numbers(row.get("question_answer")):
                records.append(
                    Record(
                        table="quiz_answer_selected_options",
                        values={
                            "tenant_id": tenant_id,
                            "answer_id": answer_id,
                            "option_id": ctx.ulid.for_row(
                                "question_selection", f"{question_ulid_value}:{number}"
                            ),
                        },
                        natural_key=("answer_id", "option_id"),
                        source_key=int(row["user_learning_test_sub_id"]),
                    )
                )
        return records


# --- アンケート回答 -----------------------------------------------------------


def _responses(ctx: RunContext, drop=None) -> list[dict]:
    """アンケート回答に、回答先のレッスンを添える。

    **`enquete_answer` は会員を直接持たない。** `entity_type_id` で指す先が変わる。

    - `2` ユニット   … `entity_id` は `user_learning_unit_id`
    - `1` お知らせ   … `entity_id` は `news_user_id`
    - `3` レポート   … `entity_id` は `user_learning_report_id`

    **ユニット以外は回答先のレッスンが決まらない**（`survey_responses.lesson_id` は
    `survey_lessons` への FK で NOT NULL）。`entity_type` / `entity_id` の列は
    追加してあるが、**レッスンに紐づかない回答は移せない**。
    """
    source = ctx.require_source()
    units = _learning_units(ctx)
    # enquete_id → その定義を使っているユニット。**複製しているのでレッスンは複数ありうる**
    by_enquete: dict[int, list[dict]] = {}
    for unit in _survey_units(ctx):
        by_enquete.setdefault(int(unit["enquete_id"]), []).append(unit)

    rows: list[dict] = []
    for answer in source.fetch_joined(
        "enquete_answer",
        ENQUETE_ANSWER_COLUMNS,
        parent="enquete",
        on="c.enquete_id = p.enquete_id",
    ):
        entity_type = ENTITY_TYPES.get(int(answer.get("entity_type_id") or 0))
        if entity_type != "lesson":
            continue  # お知らせ・レポート添付は回答先のレッスンが決まらない
        learning_unit = units.get(int(answer.get("entity_id") or 0))
        if learning_unit is None:
            if drop:
                drop("survey_responses", answer["enquete_answer_id"], "旧データの不整合",
                     "回答した学習の行（user_learning_unit）が物理削除されている")
            continue
        # 同じアンケートを複数ユニットが参照している場合、**回答したユニットの複製**を選ぶ
        target = next(
            (
                u
                for u in by_enquete.get(int(answer["enquete_id"]), [])
                if int(u["unit_id"]) == int(learning_unit["unit_id"])
            ),
            None,
        )
        if target is None:
            if drop:
                drop("survey_responses", answer["enquete_answer_id"], "旧データの不整合",
                     f"回答したユニット（unit_id={learning_unit['unit_id']}）がこのアンケート"
                     f"（enquete_id={answer['enquete_id']}）を使っていない")
            continue
        rows.append(
            {**answer, "_unit_id": target["unit_id"], "_user_id": learning_unit["_user_id"]}
        )
    return rows


class SurveyResponsesStep(Step):
    """`enquete_answer` を `survey_responses` に移す。

    **削除済みの回答も移す**（`deleted_at`。2026-10-01 の方針。新のアプリはまだ読まない）。
    """

    name = "enrollment.survey_responses"
    description = "アンケート回答の見出しを移す"
    source_table = "enquete_answer"
    target_table = "survey_responses"
    depends_on = ("content.survey_question_options",)

    def extract(self, ctx: RunContext) -> list[dict]:
        return _responses(ctx, drop=self.drop)

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        return [
            Record(
                table="survey_responses",
                values={
                    "id": ctx.ulid.for_row("enquete_answer", row["enquete_answer_id"]),
                    "tenant_id": tenant_id,
                    "lesson_id": ctx.ulid.for_row("unit", row["_unit_id"]),
                    "user_id": ctx.ulid.for_row("user", row["_user_id"]),
                    "entity_type": "lesson",
                    "entity_id": None,
                    # **NOT NULL。** 回答日時が無い行は登録日時で代替する
                    "submitted_at": convert(
                        row.get("enquete_reply_time") or row.get("regist_date"),
                        ColumnKind.TIMESTAMP,
                    ),
                    "suspended": _suspended(row),
                    "deleted_at": (
                        convert(row.get("update_date"), ColumnKind.DATETIME) if _deleted(row) else None
                    ),
                    "created_at": convert(row.get("regist_date"), ColumnKind.TIMESTAMP),
                },
                natural_key=("id",),
                source_key=int(row["enquete_answer_id"]),
            )
            for row in rows
        ]


def _survey_answer_rows(ctx: RunContext) -> list[dict]:
    """回答 JSON を設問ごとにほどく。**キーは `answer_<enquete_question_id>`。**"""
    source = ctx.require_source()
    questions = {
        int(q["enquete_question_id"]): q
        for q in source.fetch_joined(
            "enquete_question",
            ("enquete_question_id", "enquete_page_id", "question_type", "selection_num"),
            parent="enquete",
            on="p2.enquete_id = p.enquete_id",
            via=[("enquete_page", "p2", "c.enquete_page_id = p2.enquete_page_id")],
        )
    }
    rows: list[dict] = []
    for response in _responses(ctx):
        try:
            payload = json.loads(response.get("answer") or "{}")
        except ValueError:
            # **壊れた JSON は落とさず飛ばす。** 1件で回答全体を止めない
            continue
        if not isinstance(payload, dict):
            continue
        for key, value in payload.items():
            if not key.startswith("answer_"):
                continue
            legacy = key[len("answer_") :]
            if not legacy.isdigit():
                continue
            question = questions.get(int(legacy))
            if question is None:
                continue
            rows.append({"_response": response, "_question": question, "_value": value})
    return rows


class SurveyAnswersStep(Step):
    """回答 JSON を `survey_answers` にほどく。"""

    name = "enrollment.survey_answers"
    description = "アンケートの設問別回答を移す"
    source_table = "enquete_answer"
    target_table = "survey_answers"
    depends_on = ("enrollment.survey_responses",)

    def extract(self, ctx: RunContext) -> list[dict]:
        return _survey_answer_rows(ctx)

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        records: list[Record] = []
        for row in rows:
            response, question = row["_response"], row["_question"]
            kind = QUESTION_KINDS.get(int(question["question_type"]))
            text = _answer_text(row["_value"])
            records.append(
                Record(
                    table="survey_answers",
                    values={
                        "id": _survey_answer_ulid(ctx, response, question),
                        "tenant_id": tenant_id,
                        "response_id": ctx.ulid.for_row(
                            "enquete_answer", response["enquete_answer_id"]
                        ),
                        "question_id": question_ulid(
                            ctx, response["_unit_id"], question["enquete_question_id"]
                        ),
                        "numeric_value": None,
                        # **選択式でも、選んだ番号の生値を残す。** 選択肢が消えても何を選んだか分かる
                        "text_value": text,
                        "created_at": convert(
                            response.get("regist_date"), ColumnKind.TIMESTAMP
                        ),
                    },
                    natural_key=("response_id", "question_id"),
                    source_key=int(response["enquete_answer_id"]),
                )
            )
            _ = kind
        return records


class SurveyAnswerSelectedOptionsStep(Step):
    """選択式の回答を `survey_answer_selected_options` に展開する。"""

    name = "enrollment.survey_answer_selected_options"
    description = "アンケートで選んだ選択肢を展開する"
    source_table = "enquete_answer"
    target_table = "survey_answer_selected_options"
    depends_on = ("enrollment.survey_answers",)

    def extract(self, ctx: RunContext) -> list[dict]:
        return _survey_answer_rows(ctx)

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        records: list[Record] = []
        for row in rows:
            response, question = row["_response"], row["_question"]
            if QUESTION_KINDS.get(int(question["question_type"])) not in CHOICE_KINDS:
                continue
            question_id = question_ulid(
                ctx, response["_unit_id"], question["enquete_question_id"]
            )
            answer_id = _survey_answer_ulid(ctx, response, question)
            for number in _numbers(row["_value"]):
                records.append(
                    Record(
                        table="survey_answer_selected_options",
                        values={
                            "tenant_id": tenant_id,
                            "answer_id": answer_id,
                            "option_id": ctx.ulid.for_row(
                                "enquete_selection", f"{question_id}:{number}"
                            ),
                        },
                        natural_key=("answer_id", "option_id"),
                        source_key=int(response["enquete_answer_id"]),
                    )
                )
        return records


# --- 課題提出 -----------------------------------------------------------------


def _submissions(ctx: RunContext) -> list[dict]:
    source = ctx.require_source()
    units = _learning_units(ctx)
    rows: list[dict] = []
    for report in source.fetch_joined(
        "user_learning_report",
        USER_LEARNING_REPORT_COLUMNS,
        parent="user",
        on="ull.user_id = p.user_id",
        via=[
            ("user_learning_unit", "ulu", "c.user_learning_unit_id = ulu.user_learning_unit_id"),
            (
                "user_learning_lesson",
                "ull",
                "ulu.user_learning_lesson_id = ull.user_learning_lesson_id",
            ),
        ],
    ):
        unit = units.get(int(report["user_learning_unit_id"]))
        if unit is None:
            continue
        rows.append({**report, "_user_id": unit["_user_id"]})
    return rows


class SubmissionsStep(Step):
    """`user_learning_report` を `submissions` に移す。

    **未提出（`submit_date` が NULL）は移らない。** `submissions.submitted_at` は
    NOT NULL のままにすると決めたため（2026-09-23）。ステージング実測で 116件中5件。
    """

    name = "enrollment.submissions"
    description = "課題の提出を移す（未提出は移らない）"
    source_table = "user_learning_report"
    target_table = "submissions"
    depends_on = ("content.assignment_materials",)

    def extract(self, ctx: RunContext) -> list[dict]:
        return _submissions(ctx)

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        records: list[Record] = []
        for row in rows:
            reviewed = row.get("evaluate_date") is not None
            records.append(
                Record(
                    table="submissions",
                    values={
                        "id": ctx.ulid.for_row(
                            "user_learning_report", row["user_learning_report_id"]
                        ),
                        "tenant_id": tenant_id,
                        "assignment_id": ctx.ulid.for_row("report", row["report_id"]),
                        "user_id": ctx.ulid.for_row("user", row["_user_id"]),
                        # **旧の提出物は課題用のアンケートの回答**（`enquete_answer`、種別3）にあり、
                        # 移すかは確認事項 C4 の回答待ち。`eval_*` のファイルは添削者のもので、
                        # 添削に付ける（FeedbackFilesStep）
                        "object_key": None,
                        "body_text": None,
                        "status": "reviewed" if reviewed else "submitted",
                        "reviewer_id": _reviewer(ctx, row),
                        # **NOT NULL。** NULL の行はここで弾かれて一覧に出る
                        "submitted_at": convert(row.get("submit_date"), ColumnKind.DATETIME),
                        "score": row.get("score"),
                        "settings": json.dumps(
                            {
                                "send_pc": bool(int(row.get("send_PC_chk") or 0)),
                                "send_mobile": bool(int(row.get("send_mobile_chk") or 0)),
                            },
                            ensure_ascii=False,
                        ),
                    },
                    natural_key=("id",),
                    source_key=int(row["user_learning_report_id"]),
                )
            )
        return records


class FeedbackFilesStep(Step):
    """添削に付けたファイル（最大5本）を `submission_feedback_files` に展開する。

    **列名は `eval_*` で、中身は添削者が付けたファイル。** 管理画面の評価
    （`admin-lesson/ReportController::evaluationAction`）で書き込み、受講者の画面では添削の
    コメントの下に出す（評価の公開待ちの間は見せない）。受講者の提出物は課題用のアンケートの
    回答にある（確認事項 C4）。**以前は受講者の提出ファイル（`submission_files`）に入れていた**
    （2026-09-30 に直した。旧 DB を読み直して判明）。

    `submission_feedbacks.object_key`（1本）には入れない — 同じファイルを2か所に持たない。
    添削されていない提出にファイルがあれば一覧に出す（添削の行が無いので付けられない）。
    """

    name = "enrollment.submission_feedback_files"
    description = "添削に付けたファイル（最大5本）を移す"
    source_table = "user_learning_report"
    target_table = "submission_feedback_files"
    depends_on = ("enrollment.submission_feedbacks",)

    def extract(self, ctx: RunContext) -> list[dict]:
        rows = []
        for row in _submissions(ctx):
            has_file = any(_text(row.get(f"eval_save_file_name{s}")) for s in MATERIAL_SLOTS)
            if has_file and row.get("evaluate_date") is None:
                self.drop("submission_feedback_files", row["user_learning_report_id"], "旧データの不整合",
                          "添削されていない提出に添削のファイルがある（添削の行が無いので付けられない）")
                continue
            if has_file:
                rows.append(row)
        return rows

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        records: list[Record] = []
        for row in rows:
            submission_id = ctx.ulid.for_row(
                "user_learning_report", row["user_learning_report_id"]
            )
            feedback_id = ctx.ulid.for_row("user_report_feedback", submission_id)
            order = 0
            for slot in MATERIAL_SLOTS:
                saved = _text(row.get(f"eval_save_file_name{slot}"))
                if not saved:
                    continue
                order += 1
                records.append(
                    Record(
                        table="submission_feedback_files",
                        values={
                            "id": ctx.ulid.for_row("user_report_eval_file", f"{submission_id}:{slot}"),
                            "tenant_id": tenant_id,
                            "feedback_id": feedback_id,
                            "sort_order": order,
                            "file_name": _text(row.get(f"eval_disp_file_name{slot}")) or saved,
                            "object_key": saved,  # L9 の移送後にキーへ置き換える
                        },
                        natural_key=("feedback_id", "sort_order"),
                        source_key=int(row["user_learning_report_id"]),
                    )
                )
        return records


class SubmissionFeedbacksStep(Step):
    """添削を `submission_feedbacks` に移す。**添削された提出だけ。**"""

    name = "enrollment.submission_feedbacks"
    description = "課題の添削を移す"
    source_table = "user_learning_report"
    target_table = "submission_feedbacks"
    depends_on = ("enrollment.submissions", "content.proxy_instructor")

    def extract(self, ctx: RunContext) -> list[dict]:
        return [r for r in _submissions(ctx) if r.get("evaluate_date") is not None]

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        records: list[Record] = []
        unknown = sum(1 for r in rows if _reviewer(ctx, r) is None)
        if unknown:
            ctx.logger.warning(
                "添削者が分からない添削が %d 件ある。**代理講師に倒して移す**（暫定対応）。"
                "対応表が届いたら付け替えること",
                unknown,
            )
        for row in rows:
            submission_id = ctx.ulid.for_row(
                "user_learning_report", row["user_learning_report_id"]
            )
            records.append(
                Record(
                    table="submission_feedbacks",
                    values={
                        "id": ctx.ulid.for_row("user_report_feedback", submission_id),
                        "tenant_id": tenant_id,
                        "submission_id": submission_id,
                        "reviewer_id": _feedback_reviewer(ctx, row),
                        "body": row.get("user_report_evaltext") or "",
                        "object_key": None,
                        "score": row.get("score"),
                        # **lw2 の課題に合否の概念が無い。** 点数だけなので「添削済み」を入れる
                        "result": "reviewed",
                        "question_comments": _question_comments(row),
                        "created_at": convert(row.get("evaluate_date"), ColumnKind.TIMESTAMP),
                    },
                    natural_key=("submission_id",),
                    source_key=int(row["user_learning_report_id"]),
                )
            )
        return records


# --- 小道具 -----------------------------------------------------------------


def _answer_question_ulid(ctx: RunContext, row: dict) -> str:
    link = row["_link"]
    return _question_ulid(
        ctx, link["_sub"]["test_sub_id"], link["question_id"], int(link.get("sort_no") or 0)
    )


def _survey_answer_ulid(ctx: RunContext, response: dict, question: dict) -> str:
    return ctx.ulid.for_row(
        "enquete_answer_question",
        f"{int(response['enquete_answer_id'])}:{int(question['enquete_question_id'])}",
    )


def _reviewer(ctx: RunContext, row: dict) -> str | None:
    """添削者。**`submissions.reviewer_id` は NULL 可、`submission_feedbacks` は NOT NULL。**"""
    value = row.get("evaluate_user_id")
    if value is None or int(value) == 0:
        return None
    return ctx.ulid.for_row("user", int(value))


def _feedback_reviewer(ctx: RunContext, row: dict) -> str:
    """添削者が分からない添削の当て先。**代理講師に倒す**（暫定対応。2026-09-23 決定の
    「不明な箇所は仮データを入れる」）。

    `submission_feedbacks.reviewer_id` は NOT NULL なので、倒さないと**添削の本文と点数ごと
    移らない**。ステージング実測では 37件中 33件が `evaluate_user_id` を持たない。
    **代理講師のままの添削は、対応表が届いたら付け替える。**
    """
    return _reviewer(ctx, row) or ctx.ulid.for_row("user", PROXY_KEY)


def _question_comments(row: dict) -> str | None:
    """設問ごとの添削。**旧は1つの text 列**なので、そのまま json に包む。"""
    comment = _text(row.get("report_question_comment"))
    return None if comment is None else json.dumps({"raw": comment}, ensure_ascii=False)


def _numbers(value: object) -> list[int]:
    """パイプ区切りの選択肢番号を取り出す。"""
    if value is None:
        return []
    return [int(p.strip()) for p in str(value).split("|") if p.strip().isdigit()]


def _answer_text(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    text = str(value)
    return text or None


def _text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _fit(value: object, limit: int) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if len(text) <= limit else None


def _flag(value: object) -> bool | None:
    """**NULL は「記録が無い」。** False に倒すと「不正解だった」になってしまう。"""
    return None if value is None else bool(int(value))


def quizzes() -> list[Step]:
    """3-3 テスト結果。"""
    return [QuizAttemptsStep(), QuizAnswersStep(), QuizAnswerSelectedOptionsStep()]


def submissions() -> list[Step]:
    """3-4 課題提出。"""
    return [SubmissionsStep(), SubmissionFeedbacksStep(), FeedbackFilesStep()]


def _suspended(row: dict) -> bool:
    return str(row.get("suspended_chk") or "").strip() not in ("", "0")


def _deleted(row: dict) -> bool:
    return int(row.get("del_chk") or 0) == 1


def _answered_at(row: dict):
    return row.get("enquete_reply_time") or row.get("regist_date")


class SurveySubmissionLogStep(Step):
    """回答済みの記録（`survey_submission_log`）を作る。

    **新は「回答済みか」をこの表だけで判断する**（`response_repo.HasSubmitted`）。作らないと、
    旧で回答した会員が新でもう一度回答できてしまう。**途中保存の回答は回答済みにしない**
    （旧でも回答し直せた）。**削除済みの回答も回答済みにしない**（旧の `findEnqueteAnswer` は
    `del_chk = 0` だけを見るので、回答し直せた）。1人が同じユニットに何度か回答していれば、最初の回答日時を入れる。
    """

    name = "enrollment.survey_submission_log"
    description = "アンケートの回答済みの記録を作る（途中保存は除く）"
    source_table = "enquete_answer"
    target_table = "survey_submission_log"
    depends_on = ("enrollment.survey_responses",)

    def extract(self, ctx: RunContext) -> list[dict]:
        # 落とす行は回答の見出し（SurveyResponsesStep）が一覧に出すので、ここでは出さない
        return [r for r in _responses(ctx) if not _suspended(r) and not _deleted(r)]

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        first: dict[tuple[int, int], dict] = {}
        for row in rows:
            key = (int(row["_unit_id"]), int(row["_user_id"]))
            when = _answered_at(row)
            held = _answered_at(first[key]) if key in first else None
            # 日時の無い行は、日時のある行より後ろに回す（比べられないので）
            if key not in first or (when is not None and (held is None or when < held)):
                first[key] = row
        return [
            Record(
                table="survey_submission_log",
                values={
                    "tenant_id": tenant_id,
                    "lesson_id": ctx.ulid.for_row("unit", unit_id),
                    "user_id": ctx.ulid.for_row("user", user_id),
                    "submitted_at": convert(
                        row.get("enquete_reply_time") or row.get("regist_date"), ColumnKind.TIMESTAMP
                    ),
                },
                natural_key=("tenant_id", "lesson_id", "user_id"),
                source_key=f"{unit_id}:{user_id}",
            )
            for (unit_id, user_id), row in first.items()
        ]


def surveys() -> list[Step]:
    """3-5 アンケート回答。"""
    return [SurveyResponsesStep(), SurveyAnswersStep(), SurveyAnswerSelectedOptionsStep(),
            SurveySubmissionLogStep()]
