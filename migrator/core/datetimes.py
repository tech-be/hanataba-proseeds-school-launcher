"""日時とタイムゾーン（docs/migration-spec.md 3.3）。

旧は全584列が `datetime`（JST naive）。新は `timestamp` / `datetime(3)` / `datetime` が
**同じテーブル内でも混在する**。

- `timestamp` 列はセッション TZ で UTC に変換されて格納される
- `datetime(3)` / `datetime` 列は変換されない

したがって **列ごとに型を引いて分岐する**。テーブル単位で決め打ちすると必ず事故る。
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from enum import Enum

JST = timezone(timedelta(hours=9), "JST")
UTC = timezone.utc


class ColumnKind(Enum):
    """新環境の日時列の種類。列ごとに指定する。"""

    #: `timestamp` / `timestamp(3)`。セッション TZ = UTC で書くので UTC に直す
    TIMESTAMP = "timestamp"
    #: `datetime` / `datetime(3)`。変換されないので、UTC に直した値を明示的に書く
    DATETIME = "datetime"
    #: `date`。時刻を持たない
    DATE = "date"


class DateBoundary(Enum):
    """`date` → 日時型の補い方。

    JST の 00:00 を UTC に直すと**前日 15:00** になり、日付境界で1日ずれる。
    開始日か終了日かで補う時刻を変える。
    """

    START = "start"  # 00:00:00
    END = "end"  # 23:59:59


def is_zero_date(value: object) -> bool:
    """MySQL のゼロ日付 (`0000-00-00`) か。

    旧環境の `datetime` 列は NOT NULL ではないのに、フォームから空で保存されると
    `0000-00-00 00:00:00` が入っている行がある。**ドライバはこれを日時に直せず、
    生の文字列のまま返す**ので、そのまま使うと型エラーで落ちる。
    値としては「入っていない」なので NULL と同じ扱いにする。
    """
    return isinstance(value, str) and value.startswith("0000-00-00")


def _as_jst(value: datetime) -> datetime:
    """JST naive を JST aware にする。aware ならそのまま返す。"""
    if value.tzinfo is None:
        return value.replace(tzinfo=JST)
    return value


def convert(value: datetime | None, kind: ColumnKind) -> datetime | None:
    """旧の JST naive `datetime` を、新の列の種類に合わせて変換する。"""
    if value is None:
        return None
    if kind is ColumnKind.DATE:
        return value.date()  # type: ignore[return-value]
    return _as_jst(value).astimezone(UTC).replace(tzinfo=None)


def convert_date(
    value: date | None, kind: ColumnKind, boundary: DateBoundary = DateBoundary.START
) -> datetime | date | None:
    """旧の `date` を新の日時型に入れる。

    `boundary` で 00:00:00 / 23:59:59 のどちらを補うかを決める。
    **開始日と終了日で使い分けないと、期間の判定が1日ずれる。**
    """
    if value is None:
        return None
    if kind is ColumnKind.DATE:
        return value
    clock = time(0, 0, 0) if boundary is DateBoundary.START else time(23, 59, 59)
    return convert(datetime.combine(value, clock), kind)


def drop_time(value: datetime | None) -> date | None:
    """時刻部を捨てて日付にする（`birth_date` など。実測で時刻部は全件 00:00:00）。"""
    return None if value is None else value.date()


def split_date(value: datetime | date | None) -> tuple[int | None, int | None, int | None]:
    """日付を年・月・日に分解する。

    新環境は「生年は必須・生月日は任意」を設定できる仕様のため、誕生日を3列で持つ。
    1列の `date` に畳まない（docs/db/01-foundation/migration-spec.md 1-2）。
    """
    if value is None:
        return (None, None, None)
    d = value.date() if isinstance(value, datetime) else value
    return (d.year, d.month, d.day)
