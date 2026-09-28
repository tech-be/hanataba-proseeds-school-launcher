"""enrollment.2 — 学習履歴。

`user_learning_unit` → `lesson_progress`。

**`progress_status` はユニット種別ごとに意味が変わる。** `unit_learning_progress_master`
が `(progress_id, unit_type_id)` で引く作りで、同じ `2` がテストなら「受験中」、
アンケートなら「回答済」、レポートなら「評価待」、集合研修なら「出席希望」
（`Application_Constants_UserLearningConstants`）。**値だけを移すと意味が消える**ので、
`種別:値` の形で持つ（→ A9）。

**講義（`unit_type_id = 1`）の値は定数ファイルに定義が無い。** 実測でも
`learning_status` と相関しない（4通りすべて出現）。**意味が決まるまで畳まない。**

**修了は `learning_status` で決まる。** 実測（会員側で絞った 13,008件）で `1` の 9,760件は
`complete_date` がすべて非 NULL、`0` の 3,248件はすべて NULL で完全に一致する。
"""

from __future__ import annotations

import json

from ...context import RunContext
from ...core.datetimes import ColumnKind, convert
from ...core.records import Record
from ..base import Step

UNIT_PROGRESS_COLUMNS = (
    "user_learning_unit_id",
    "user_learning_lesson_id",
    "unit_id",
    "learning_status",
    "complete_date",
    "progress_status",
    "score",
    "suspend_data",
    "update_date",
    "del_chk",
)

#: `unit_type_id` → `progress_status` の意味（`UserLearningConstants`）。
#: **講義（1）は定数ファイルに定義が無い**ので入れていない
PROGRESS_LABELS: dict[int, dict[int, str]] = {
    2: {1: "未受験", 2: "受験中", 3: "中断中"},
    3: {1: "未回答", 2: "回答済", 3: "回答中"},
    4: {1: "未提出", 2: "評価待", 3: "評価済", 4: "再提出", 5: "公開待"},
    5: {1: "未予約", 2: "出席希望", 3: "欠席希望", 4: "出席", 5: "欠席"},
}

#: 種別の呼び名。`progress_status` に `種別:値` で持つときの接頭辞
UNIT_KINDS: dict[int, str] = {
    1: "lecture",
    2: "quiz",
    3: "survey",
    4: "report",
    5: "training",
    6: "document",
    7: "discussion",
    8: "skill_check",
}


class LessonProgressStep(Step):
    """`user_learning_unit` を `lesson_progress` に移す（→ A9）。"""

    name = "enrollment.lesson_progress"
    description = "ユニットごとの学習状況を移す"
    source_table = "user_learning_unit"
    target_table = "lesson_progress"
    depends_on = ("users", "content.lessons")

    def extract(self, ctx: RunContext) -> list[dict]:
        # **会員側で絞る。** `lesson` 側で絞ると、共有講座（tenant_id=0）を通じて
        # **他テナントの会員の学習履歴まで拾う**（実測 45名・5,987件）。
        # 学習履歴は「誰の記録か」が決め手なので、`user.tenant_id` を正にする
        rows = ctx.require_source().fetch_joined(
            "user_learning_unit",
            UNIT_PROGRESS_COLUMNS,
            parent="user",
            on="ul.user_id = p.user_id",
            via=[("user_learning_lesson", "ul", "c.user_learning_lesson_id = ul.user_learning_lesson_id")],
        )
        # 会員とユニット種別は親から引く（`user_learning_unit` は持たない）
        self._owners = self._load_owners(ctx)
        self._kinds = self._load_kinds(ctx)
        return rows

    def _load_owners(self, ctx: RunContext) -> dict[int, int]:
        rows = ctx.require_source().fetch_joined(
            "user_learning_lesson",
            ("user_learning_lesson_id", "user_id"),
            parent="user",
            on="c.user_id = p.user_id",
        )
        return {int(r["user_learning_lesson_id"]): int(r["user_id"]) for r in rows}

    def _load_kinds(self, ctx: RunContext) -> dict[int, int]:
        rows = ctx.require_source().fetch_joined(
            "unit",
            ("unit_id", "unit_type_id"),
            parent="lesson",
            on="c.lesson_id = p.lesson_id",
        )
        return {int(r["unit_id"]): int(r["unit_type_id"] or 0) for r in rows}

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        # **(会員, ユニット) が UNIQUE。** 実測で 76件の重複があるので、
        # `update_date` の新しい順で1件に絞る（制約は緩めない）
        latest: dict[tuple[int, int], dict] = {}
        for row in rows:
            owner = self._owners.get(int(row["user_learning_lesson_id"]))
            if owner is None:
                continue  # 親が他テナント。join で落ちているはずだが念のため
            key = (owner, int(row["unit_id"]))
            current = latest.get(key)
            if current is None or _updated_at(row) >= _updated_at(current):
                latest[key] = row

        records: list[Record] = []
        for (user_id, unit_id), row in sorted(latest.items()):
            kind = self._kinds.get(unit_id, 0)
            completed = int(row.get("learning_status") or 0) == 1
            records.append(
                Record(
                    table="lesson_progress",
                    values={
                        "id": ctx.ulid.for_row("user_learning_unit", f"{user_id}:{unit_id}"),
                        "tenant_id": tenant_id,
                        "user_id": ctx.ulid.for_row("user", user_id),
                        "lesson_id": ctx.ulid.for_row("unit", unit_id),
                        # **SCORM の中断データを `last_position` に入れない。**
                        # 動画の再生位置を想定した列で、形式が違う（原文は settings へ）
                        "last_position": None,
                        "completed_at": convert(row.get("complete_date"), ColumnKind.TIMESTAMP)
                        if completed
                        else None,
                        "progress_status": _progress_status(kind, row.get("progress_status")),
                        "settings": _settings(kind, row),
                        "deleted_at": convert(row.get("update_date"), ColumnKind.TIMESTAMP)
                        if int(row.get("del_chk") or 0) == 1
                        else None,
                    },
                    natural_key=("tenant_id", "user_id", "lesson_id"),
                    source_key=f"{user_id}:{unit_id}",
                )
            )
        return records


def _updated_at(row: dict):
    return row.get("update_date") or row.get("complete_date")


def _progress_status(kind: int, value: object) -> str | None:
    """`種別:値` で持つ。**種別を落とすと意味が復元できない。**"""
    if value is None:
        return None
    return f"{UNIT_KINDS.get(kind, f'type{kind}')}:{int(value)}"


def _settings(kind: int, row: dict) -> str | None:
    """新環境に列が無いものを残す。"""
    label = PROGRESS_LABELS.get(kind, {}).get(int(row.get("progress_status") or 0))
    payload: dict = {
        "legacy_unit_type_id": kind,
        "legacy_progress_status": row.get("progress_status"),
    }
    if label:
        payload["progress_label"] = label
    else:
        # **講義（1）は定数ファイルに定義が無い。** 意味が決まるまで畳まない
        payload["progress_label_unknown"] = True
    if row.get("suspend_data"):
        # SCORM の中断データ。原文のまま残す
        payload["suspend_data"] = str(row["suspend_data"])
    if row.get("score") is not None:
        # **テストの得点は quiz_attempts が持つ。** 突き合わせ用に残すだけ
        payload["legacy_score"] = int(row["score"])
    return json.dumps(payload, ensure_ascii=False)


def build() -> list[Step]:
    """3-2 学習履歴。"""
    return [LessonProgressStep()]
