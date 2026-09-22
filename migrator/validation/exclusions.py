"""移さなかった行の一覧。

制約に当たった行は**移さず、ここに集める**。この一覧がそのまま
「暫定対応でどれを直せばよいか」の作業リストになる。

出力先は `work_dir/not-migrated.csv`（既定 `./out`）。dry-run でも書く
（**書き込みではなく報告**なので、実投入の前に中身を見て判断できる必要がある）。
"""

from __future__ import annotations

import csv
from pathlib import Path

from .constraints import Violation

#: ASCII 名にする（CI やシェルで扱うため）。中身は日本語
FILENAME = "not-migrated.csv"
HEADER = ("step", "table", "key", "reason", "detail")


class ExclusionLog:
    """1回の実行で移さなかった行を、ファイルとログの両方に残す。"""

    def __init__(self, work_dir: Path, logger) -> None:
        self._path = Path(work_dir) / FILENAME
        self._logger = logger
        self._started = False
        self.total = 0

    @property
    def path(self) -> Path:
        return self._path

    def add(self, step: str, violations: list[Violation]) -> str:
        """一覧に足して、ログ1行分の要約を返す。"""
        if not violations:
            return ""
        self._write(step, violations)
        self.total += len(violations)

        by_reason: dict[str, list[str]] = {}
        for violation in violations:
            by_reason.setdefault(violation.reason, []).append(violation.key)
        parts = [
            f"{reason}: {len(keys)} 行（例: {keys[:5]}）" for reason, keys in sorted(by_reason.items())
        ]
        summary = f"{len(violations)} 行を移さない — " + " / ".join(parts)
        self._logger.warning(
            "%s: %s。一覧: %s（暫定対応のあと再実行すれば入る）", step, summary, self._path
        )
        return summary

    def _write(self, step: str, violations: list[Violation]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # **実行のたびに作り直す。** 前の実行の分が残っていると作業リストにならない
        mode = "a" if self._started else "w"
        with self._path.open(mode, encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle)
            if not self._started:
                writer.writerow(HEADER)
                self._started = True
            for violation in violations:
                writer.writerow(
                    [step, violation.table, violation.key, violation.reason, violation.detail]
                )
