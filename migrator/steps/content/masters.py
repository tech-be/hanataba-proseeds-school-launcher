"""ondemand.1 — マスタの追加値。

新環境のシードは lw2 の種別を覆っていない。**足りない値を先に入れる**
（FK の参照先なので、これらが無いとレッスンもテストも入らない）。

いずれも `tenant_id` を持たないグローバルマスタ。
"""

from __future__ import annotations

from ..masters import LookupValueStep
from ..base import Step


def lesson_types() -> LookupValueStep:
    """`lesson_types` に lw2 のユニット種別を足す。

    新環境のシードは `text` / `video` / `survey` / `live` の4種で、
    **テスト・課題・資料・ディスカッション・スキル診断が無い**。
    旧 `unit.unit_type_id` の 2 / 4 / 6 / 7 / 8 が該当する。

    7（ディスカッション）と 8（スキル診断）は `UnitConstants.php` には無く、
    **`ShareController` / `UnitController` に定数がある**（`UNIT_TYPE_DISCUSSION` /
    `UNIT_TYPE_SKILL`）。正規の種別で、`LessonController` も進捗の更新対象にしている。
    """
    return LookupValueStep(
        name="master.lesson_types",
        table="lesson_types",
        description="lesson_types に quiz / assignment / document を追加する",
        values=[
            {
                "code": code,
                "name_ja": label,
                "has_video_content": False,
                "needs_scheduled_at": False,
                "sort_order": order,
                "is_system": True,
            }
            for code, label, order in (
                ("quiz", "テスト", 50),
                ("assignment", "課題", 60),
                ("document", "資料", 70),
                ("discussion", "ディスカッション", 80),
                ("skill_check", "スキル診断", 90),
            )
        ],
    )


def content_status_deleted() -> LookupValueStep:
    """`content_statuses` に `deleted` を足す（lw2 の `del_chk=1` の受け皿）。

    **削除済みの講座・レッスンも移す**ため、状態として表現できる必要がある。
    """
    return LookupValueStep(
        name="master.content_statuses.deleted",
        table="content_statuses",
        description="content_statuses に deleted を追加する",
        values=[
            {
                "code": "deleted",
                "name_ja": "削除済み",
                "is_visible": False,
                "is_editable": False,
                "accepts_new_users": False,
                "sort_order": 40,
                "is_system": True,
            }
        ],
    )


def quiz_question_types() -> LookupValueStep:
    """`quiz_question_types` に記述式を足す（旧 `question.question_type`）。"""
    return LookupValueStep(
        name="master.quiz_question_types",
        table="quiz_question_types",
        description="quiz_question_types に text_free を追加する",
        values=[
            {
                "code": "text_free",
                "name_ja": "記述式",
                # 選択肢を持たないので「複数正解」という概念が無い
                "allows_multiple_correct": False,
                "sort_order": 30,
                "is_system": True,
            }
        ],
    )


def survey_question_kinds() -> LookupValueStep:
    """`survey_question_kinds` にファイル添付を足す（旧 `enquete_question`）。"""
    return LookupValueStep(
        name="master.survey_question_kinds",
        table="survey_question_kinds",
        description="survey_question_kinds に file_upload を追加する",
        values=[
            {
                "code": "file_upload",
                "name_ja": "ファイル添付",
                "allows_options": False,
                "is_numeric": False,
                "min_value": None,
                "max_value": None,
                "sort_order": 60,
                "is_system": True,
            }
        ],
    )


def build() -> list[Step]:
    return [
        lesson_types(),
        content_status_deleted(),
        quiz_question_types(),
        survey_question_kinds(),
    ]
