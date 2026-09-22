"""運営に値を決めてもらうための雛形（`overrides.csv`）を作る。

**空欄のまま移行ツールを流しても事故らない**（未記入の行は適用されない）。
埋めた行だけが効く。
"""

from __future__ import annotations

import csv
from pathlib import Path

from . import proposals
from .plan import OVERRIDE, Task

HEADER = ("table", "key", "column", "value", "memo")


def build(tasks: list[Task], context: dict[str, dict], path: Path, propose: bool = False) -> int:
    """雛形を書き、行数を返す。`context` は `user_id -> 旧の行`（memo に出す材料）。

    `propose=True` なら、**機械的に決まる値だけ**を埋める（`fixups/proposals.py`）。
    判断が要るものは空のままで、空欄は移行時に適用されない。
    """
    rows = []
    for task in tasks:
        if task.how != OVERRIDE:
            continue
        groups = _groups(task, context) if propose else {}
        for key in sorted(task.keys, key=lambda k: int(k) if k.isdigit() else 0):
            row = context.get(key, {})
            value, why = _propose(task, key, row, groups) if propose else ("", "")
            memo = _memo(task, row)
            if why:
                memo = f"{why} / {memo}"
            rows.append(("user", key, task.column, value, memo))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(HEADER)
        writer.writerows(rows)
    return len(rows)


def _groups(task: Task, context: dict[str, dict]) -> dict:
    """同じ値を共有している会員をまとめる（重複の扱いを決めるのに要る）。"""
    if task.kind == "email-duplicate":
        out: dict[str, list[str]] = {}
        for key in task.keys:
            mail = str(context.get(key, {}).get("mail_add") or "").lower()
            out.setdefault(mail, []).append(key)
        return out
    if task.kind == "line-duplicate":
        out_rows: dict[str, list[dict]] = {}
        for key in task.keys:
            row = context.get(key, {})
            out_rows.setdefault(str(row.get("line_id") or ""), []).append(row)
        return out_rows
    return {}


def _propose(task: Task, key: str, row: dict, groups: dict) -> tuple[str, str]:
    if task.kind == "email-missing":
        return proposals.for_missing_email(key, row)
    if task.kind == "email-duplicate":
        group = groups.get(str(row.get("mail_add") or "").lower(), [key])
        return proposals.for_duplicate_email(key, row, group)
    if task.kind == "line-duplicate":
        group = groups.get(str(row.get("line_id") or ""), [row])
        return proposals.for_duplicate_line(key, row, group)
    return "", ""  # ロールなど、判断が要るものは空のまま


def _memo(task: Task, row: dict) -> str:
    """**なぜこの行が要るのか**を1行で。空欄を埋める人がこれだけを見る。"""
    who = " ".join(str(row.get(c) or "") for c in ("name_sei", "name_mei")).strip()
    login = row.get("login_id") or ""
    base = f"{task.title}"
    if who or login:
        base += f" / {who}（{login}）"
    current = row.get(task.column)
    if current:
        base += f" / 現在の値: {current}"
    if task.kind == "line-duplicate":
        base += " / 残す1名以外は NULL と書く"
    if task.kind == "role-missing":
        base += " / 旧 role_id の数値（例 7=受講者）"
    return base
