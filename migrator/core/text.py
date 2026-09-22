"""文字列の検査（docs/migration-spec.md 3.4 / 3.5）。

- 旧 `utf8`(utf8mb3) → 新 `utf8mb4`。拡大方向なので基本は安全だが、
  **cp932 混入の可能性がある**ので抽出時に検証する
- `varchar` の縮小がある箇所は**超過件数を検査**し、0件でなければ**列を広げる**。
  切り捨てない（元の構造を維持する / 原則3）
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LengthCheck:
    """桁の検査1件。"""

    column: str
    limit: int

    def over(self, value: object) -> bool:
        return isinstance(value, str) and len(value) > self.limit


def find_over_length(rows: list[dict], checks: tuple[LengthCheck, ...]) -> dict[str, int]:
    """桁溢れの件数を列ごとに数える。**0件でなければ投入しない。**"""
    counts: dict[str, int] = {}
    for row in rows:
        for check in checks:
            if check.over(row.get(check.column)):
                counts[check.column] = counts.get(check.column, 0) + 1
    return counts


def looks_mojibake(value: object) -> bool:
    """cp932 を utf8 として読み込んだ跡がないか、簡易に見る。

    厳密な判定はできないので**検出したら人が見る**ための目印として使う。
    """
    if not isinstance(value, str):
        return False
    # U+FFFD（置換文字）か、cp932 の機種依存文字が化けたときに出やすい範囲
    return "�" in value or any("\u0080" <= ch <= "\u009f" for ch in value)


def find_mojibake(rows: list[dict], columns: tuple[str, ...]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        for column in columns:
            if looks_mojibake(row.get(column)):
                counts[column] = counts.get(column, 0) + 1
    return counts


def join_name(last: object, first: object, separator: str = " ") -> str:
    """姓と名を表示用に連結する。

    **分割列が正**で、`users.name` はここから生成する（二重管理にしない）。
    両方空の行は呼び出し側で止める（`users.name` は NOT NULL）。
    """
    parts = [str(p).strip() for p in (last, first) if p is not None and str(p).strip()]
    return separator.join(parts)
