"""新環境 (school-launcher) への投入。

**冪等に再実行できること**が唯一かつ最大の要件（docs/migration-spec.md 3.7）。
`Record.natural_key` が一致する行は「同じ行」として扱い、二重に作らない。
"""

from __future__ import annotations

from typing import Any, Iterable, Protocol

from ..core.records import Record


class Cursor(Protocol):
    def execute(self, sql: str, args: Any = None) -> Any: ...
    def executemany(self, sql: str, args: Iterable[Any]) -> Any: ...
    def fetchall(self) -> Iterable[dict]: ...
    @property
    def rowcount(self) -> int: ...


class Connection(Protocol):
    def cursor(self) -> Cursor: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...
    def close(self) -> None: ...


class TargetDatabase:
    """school-launcher への書き込み口。

    `dry_run` のときは SQL を組み立てるところまで行い、実行しない。
    """

    def __init__(self, connection: Connection | None, dry_run: bool = False, batch_size: int = 500) -> None:
        self._connection = connection
        self._dry_run = dry_run
        self._batch_size = batch_size
        self.statements: list[str] = []
        #: **この実行の中で入れた**行の識別子。`(テーブル, 列) -> 値`
        #: dry-run でも記録する（親を入れたことにして、子の参照を確かめるため）
        self._inserted: dict[tuple[str, str], set] = {}

    @property
    def dry_run(self) -> bool:
        return self._dry_run

    @property
    def connectionless(self) -> bool:
        """接続が無い（plan / テスト）。**この状態では確認系を素通りさせる。**"""
        return self._connection is None

    def query(self, sql: str, params: tuple = ()) -> list[dict]:
        """読み出し。dry-run でも実行する（存在確認は書き込みではない）。"""
        if self._connection is None:
            return []
        cursor = self._connection.cursor()
        cursor.execute(sql, params)
        return [dict(row) for row in cursor.fetchall()]

    def exists(self, table: str, key: dict[str, object]) -> bool:
        if not key:
            raise ValueError(f"{table}: 存在確認のキーが空")
        where = " AND ".join(f"`{c}` = %s" for c in key)
        rows = self.query(f"SELECT 1 FROM `{table}` WHERE {where} LIMIT 1", tuple(key.values()))
        return bool(rows)

    #: 外部キーの参照先になりうる列。**dry-run でも「この実行で入れた行」として覚える**ので、
    #: ここに無い列を参照先にすると、まだ DB に無い親を「存在しない」と判定してしまう。
    #: `lesson_id` は `survey_lessons` / `live_lessons` の**主キー**（`id` ではない）
    REFERENCED_COLUMNS = ("id", "code", "lesson_id")

    def known_ids(self, table: str, column: str, wanted: set) -> set:
        """`wanted` のうち、**移行先にすでにある / この実行で入れた**ものを返す。"""
        known = set(self._inserted.get((table, column), set())) & set(wanted)
        rest = [v for v in wanted if v not in known]
        if self._connection is None or not rest:
            return known
        for start in range(0, len(rest), 1000):
            chunk = rest[start : start + 1000]
            placeholders = ", ".join(["%s"] * len(chunk))
            rows = self.query(
                f"SELECT `{column}` AS v FROM `{table}` WHERE `{column}` IN ({placeholders})",
                tuple(chunk),
            )
            known |= {row["v"] for row in rows}
        return known

    def _remember(self, table: str, records: list[Record]) -> None:
        for column in self.REFERENCED_COLUMNS:
            if column not in records[0].values:
                continue
            bucket = self._inserted.setdefault((table, column), set())
            bucket |= {r.values[column] for r in records if r.values.get(column) is not None}

    def insert_many(self, records: list[Record]) -> int:
        """まとめて投入する。**同じ自然キーの行がすでにあれば飛ばす。**"""
        if not records:
            return 0
        table = records[0].table
        if any(r.table != table for r in records):
            raise ValueError("insert_many は1テーブル分ずつ呼ぶ")

        pending = [r for r in records if not (r.natural_key and self.exists(table, r.key_values()))]
        if not pending:
            return 0

        columns = list(pending[0].values.keys())
        for record in pending:
            if list(record.values.keys()) != columns:
                raise ValueError(f"{table}: 列の並びが揃っていない（バッチに混ぜられない）")

        placeholders = ", ".join(["%s"] * len(columns))
        cols = ", ".join(f"`{c}`" for c in columns)
        sql = f"INSERT INTO `{table}` ({cols}) VALUES ({placeholders})"
        self.statements.append(f"{sql}  -- {len(pending)} 行")
        self._remember(table, pending)

        if self._dry_run or self._connection is None:
            return len(pending)

        cursor = self._connection.cursor()
        written = 0
        for start in range(0, len(pending), self._batch_size):
            chunk = pending[start : start + self._batch_size]
            cursor.executemany(sql, [tuple(r.values[c] for c in columns) for r in chunk])
            written += len(chunk)
        return written

    def commit(self) -> None:
        if self._connection is not None and not self._dry_run:
            self._connection.commit()

    def rollback(self) -> None:
        if self._connection is not None and not self._dry_run:
            self._connection.rollback()

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
