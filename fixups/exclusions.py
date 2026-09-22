"""移行ツールが出した「入らない行」の一覧を読む。"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

DEFAULT_PATH = Path("out/not-migrated.csv")


@dataclass(frozen=True)
class Exclusion:
    step: str
    table: str
    key: str
    reason: str
    detail: str

    #: 理由の頭に付く種類。**`NOT NULL` は空白を含む**ので、先頭の語では切れない
    KINDS = ("NOT NULL", "UNIQUE", "外部キー")

    @property
    def kind(self) -> str:
        for kind in self.KINDS:
            if self.reason.startswith(kind):
                return kind
        return self.reason

    @property
    def column(self) -> str:
        """理由に含まれる列名（`NOT NULL \\`email\\`` → `email`）。"""
        parts = self.reason.split("`")
        return parts[1] if len(parts) > 1 else ""


def load(path: Path | str = DEFAULT_PATH) -> list[Exclusion]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"{path} が無い。先に移行ツールを流す: python -m migrator run --dry-run --section foundation"
        )
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return [
            Exclusion(
                step=row["step"],
                table=row["table"],
                key=row["key"],
                reason=row["reason"],
                detail=row["detail"],
            )
            for row in csv.DictReader(handle)
        ]
