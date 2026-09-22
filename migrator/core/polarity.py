"""フラグの極性（docs/migration-spec.md 3.6）。

lw2 は「受け取る」、新環境の `notification_optouts` は「**受け取らない**」。
**反転を忘れると通知が真逆に出る。**

新環境は `kind` に加えて PC / 携帯を分ける `channel` を持つ（A21）。lw2 は
`sendmail_pc_chk` / `sendmail_mobile_chk` のように宛先ごとに列が分かれている。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Channel(Enum):
    PC = "pc"
    MOBILE = "mobile"


@dataclass(frozen=True)
class OptoutSource:
    """lw2 側の「受け取る」フラグ1つ分。"""

    column: str
    kind: str
    channel: Channel


@dataclass(frozen=True)
class Optout:
    """新環境に入れる「受け取らない」1行。"""

    kind: str
    channel: Channel


def invert(receives: object) -> bool:
    """「受け取る」→「受け取らない」。

    NULL は「設定していない」＝既定で受け取る、と解釈して optout を作らない。
    """
    if receives is None:
        return False
    return not bool(int(receives))


def optouts_for(row: dict[str, object], sources: tuple[OptoutSource, ...]) -> list[Optout]:
    """会員1行から、作るべき optout 行を組み立てる。"""
    out: list[Optout] = []
    for src in sources:
        if src.column not in row:
            raise KeyError(f"通知フラグの列が抽出結果に無い: {src.column}")
        if invert(row[src.column]):
            out.append(Optout(kind=src.kind, channel=src.channel))
    return out
