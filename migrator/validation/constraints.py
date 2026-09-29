"""投入前の制約チェック（NOT NULL / CHECK / UNIQUE / 外部キー）。

**dry-run では INSERT が実行されないため、制約違反は本番で初めて現れる。**
それでは遅いので、変換した `Record` を移行先のスキーマと突き合わせて、
**投入する前に**落ちる行を特定する。

**当たった行は移さない。** ツールは「どの行が入らないか」を一覧にするだけで、
値を作り替えて通すことはしない（合成した値で通すと、**何が本物か分からなくなる**）。
直すのは移行の外での暫定対応で、そのあと再実行すれば入る。

ここで見るのは4つ。

- **NOT NULL** — NOT NULL 列に値が無い。**既定値のある列も、Step が書くなら見る**
  （既定値は「列を書かないとき」にしか効かず、NULL を渡すと違反になる）
- **CHECK** — 数値の下限（`quantity >= 1` など）。**式が読める形のときだけ**見る
- **UNIQUE** — 同じ UNIQUE キーの行が**同じバッチの中に**ある。
  `insert_many` は移行先の既存行としか突き合わせないので、バッチ内の重複は素通りする
- **外部キー** — 参照先の行が、移行先にも**この実行の中にも**無い

移行先のスキーマは `information_schema` から読む（定義をコードに写経しない）。
"""

from __future__ import annotations

import re

from dataclasses import dataclass, field
from datetime import datetime

from ..core.records import Record


@dataclass(frozen=True)
class ColumnSpec:
    name: str
    nullable: bool
    has_default: bool
    #: `AUTO_INCREMENT` や `CURRENT_TIMESTAMP` のように DB が埋める列
    auto: bool
    #: `information_schema.columns.data_type`（`timestamp` / `datetime` など）
    data_type: str = ""

    @property
    def must_be_written(self) -> bool:
        """値を必ず渡さなければならない列か。"""
        return not self.nullable and not self.has_default and not self.auto


@dataclass(frozen=True)
class CheckConstraint:
    """`CHECK (...)` のうち、**単純な数値の下限**だけを解釈したもの。

    MySQL の `check_clause` は式そのものなので、一般には評価できない。
    移行先で実際に使われているのは次の形だけなので、**この形に限って**見る。

        (`cost` >= 1)
        ((`capacity` is null) or (`capacity` >= 1))

    解釈できない式（列どうしの比較など）は**無視する**。見落とすほうが、
    誤って行を落とすより害が小さい（落ちれば実 INSERT で止まって気づける）。
    """

    name: str
    column: str
    minimum: int
    nullable: bool


@dataclass(frozen=True)
class UniqueKey:
    name: str
    columns: tuple[str, ...]


@dataclass(frozen=True)
class ForeignKey:
    column: str
    referenced_table: str
    referenced_column: str


@dataclass
class TableSchema:
    """移行先の1テーブルの、投入に効く部分だけ。"""

    table: str
    columns: dict[str, ColumnSpec] = field(default_factory=dict)
    uniques: tuple[UniqueKey, ...] = ()
    foreign_keys: tuple[ForeignKey, ...] = ()
    checks: tuple[CheckConstraint, ...] = ()


class SchemaReader:
    """移行先のスキーマを `information_schema` から読む（1テーブル1回）。"""

    def __init__(self, target) -> None:
        self._target = target
        self._cache: dict[str, TableSchema] = {}

    def get(self, table: str) -> TableSchema | None:
        """接続が無い（テスト・plan）ときは `None`。**チェックは素通りする。**"""
        if self._target.connectionless:
            return None
        if table not in self._cache:
            self._cache[table] = self._read(table)
        return self._cache[table]

    def _read(self, table: str) -> TableSchema:
        columns = {}
        for row in self._target.query(
            "SELECT column_name AS name, is_nullable AS nullable, column_default AS dflt, "
            "extra AS extra, data_type AS dtype FROM information_schema.columns "
            "WHERE table_schema = DATABASE() AND table_name = %s",
            (table,),
        ):
            extra = str(row.get("extra") or "").lower()
            columns[str(row["name"])] = ColumnSpec(
                name=str(row["name"]),
                nullable=str(row["nullable"]).upper() == "YES",
                has_default=row.get("dflt") is not None,
                auto="auto_increment" in extra or "default_generated" in extra,
                data_type=str(row.get("dtype") or "").lower(),
            )

        checks: list[CheckConstraint] = []
        for row in self._target.query(
            "SELECT cc.constraint_name AS name, cc.check_clause AS clause "
            "FROM information_schema.check_constraints cc "
            "JOIN information_schema.table_constraints tc "
            "  ON tc.constraint_name = cc.constraint_name "
            " AND tc.constraint_schema = cc.constraint_schema "
            "WHERE cc.constraint_schema = DATABASE() AND tc.table_name = %s",
            (table,),
        ):
            parsed = _parse_check(str(row["name"]), str(row["clause"]))
            if parsed is not None:
                checks.append(parsed)

        by_index: dict[str, list[tuple[int, str]]] = {}
        for row in self._target.query(
            "SELECT index_name AS name, seq_in_index AS seq, column_name AS col "
            "FROM information_schema.statistics "
            "WHERE table_schema = DATABASE() AND table_name = %s AND non_unique = 0",
            (table,),
        ):
            by_index.setdefault(str(row["name"]), []).append((int(row["seq"]), str(row["col"])))
        uniques = tuple(
            UniqueKey(name, tuple(c for _, c in sorted(cols)))
            for name, cols in sorted(by_index.items())
        )

        foreign_keys = tuple(
            ForeignKey(
                column=str(row["col"]),
                referenced_table=str(row["ref_table"]),
                referenced_column=str(row["ref_col"]),
            )
            for row in self._target.query(
                "SELECT column_name AS col, referenced_table_name AS ref_table, "
                "referenced_column_name AS ref_col FROM information_schema.key_column_usage "
                "WHERE table_schema = DATABASE() AND table_name = %s "
                "AND referenced_table_name IS NOT NULL",
                (table,),
            )
        )
        return TableSchema(table, columns, uniques, foreign_keys, tuple(checks))


_CHECK_MIN = re.compile(r"^\(?`(?P<col>\w+)` >= (?P<min>-?\d+)\)?$")
_CHECK_NULL_OR_MIN = re.compile(
    r"^\(\(`(?P<col>\w+)` is null\) or \(`(?P=col)` >= (?P<min>-?\d+)\)\)$"
)


def _parse_check(name: str, clause: str) -> "CheckConstraint | None":
    """`check_clause` から**数値の下限**だけを取り出す。読めなければ `None`。"""
    text = clause.strip()
    m = _CHECK_NULL_OR_MIN.match(text)
    if m:
        return CheckConstraint(name, m.group("col"), int(m.group("min")), nullable=True)
    m = _CHECK_MIN.match(text)
    if m:
        return CheckConstraint(name, m.group("col"), int(m.group("min")), nullable=False)
    return None


@dataclass(frozen=True)
class Violation:
    """移さなかった行1件。**「誰が」「なぜ」が分かる形で残す。**"""

    table: str
    reason: str
    detail: str
    key: str

    def __str__(self) -> str:
        return f"{self.table}: {self.key} — {self.reason}（{self.detail}）"


def _key_of(record: Record) -> str:
    """一覧に出すときの目印。旧のキーがあればそれを使う。"""
    if record.source_key is not None:
        return str(record.source_key)
    if record.natural_key:
        return "/".join(str(record.values.get(c)) for c in record.natural_key)
    return str(record.values.get("id", "?"))


def filter_valid(
    records: list[Record], schema: TableSchema | None, target
) -> tuple[list[Record], list[Violation]]:
    """入る行と、入らない行に分ける。

    **入らない行は捨てずに返す。** 呼び出し側が一覧に出し、暫定対応の材料にする。
    """
    if not records or schema is None:
        return records, []
    violations: dict[int, Violation] = {}
    _not_null(records, schema, violations)
    _datetime_range(records, schema, violations)
    _checks(records, schema, violations)
    _unique(records, schema, target, violations)
    _foreign_keys(records, schema, target, violations)
    valid = [r for i, r in enumerate(records) if i not in violations]
    return valid, [violations[i] for i in sorted(violations)]


def _not_null(records: list[Record], schema: TableSchema, out: dict[int, Violation]) -> None:
    """NOT NULL に当たる行を拾う。

    **既定値のある列も、Step が書くなら見る。** `created_at TIMESTAMP NOT NULL
    DEFAULT CURRENT_TIMESTAMP` のような列は、書かなければ DB が埋めてくれるが、
    **INSERT の列に入れて NULL を渡すと既定値は効かず、そのまま NOT NULL 違反になる**。
    `must_be_written` だけを見ていると dry-run を素通りし、**実 INSERT で初めて落ちる**
    （オンデマンドの予行で2 Step がこれで停止した）。
    """
    written_columns = set(records[0].values)
    for column in schema.columns.values():
        if column.nullable:
            continue
        written = column.name in written_columns
        if not column.must_be_written and not written:
            continue  # 書かない列。DB の既定値に任せる
        for index, record in enumerate(records):
            if record.values.get(column.name) is not None:
                continue
            detail = "値が NULL" if written else "INSERT の列に入っていない"
            out.setdefault(
                index, Violation(schema.table, f"NOT NULL `{column.name}`", detail, _key_of(record))
            )


#: MySQL の `TIMESTAMP` が持てる範囲（UTC）。`DATETIME` は 1000〜9999 年なので見ない
_TIMESTAMP_MIN = datetime(1970, 1, 1, 0, 0, 1)
_TIMESTAMP_MAX = datetime(2038, 1, 19, 3, 14, 7)


def _datetime_range(records: list[Record], schema: TableSchema, out: dict[int, Violation]) -> None:
    """`TIMESTAMP` の範囲を外れる日時を拾う。

    **旧環境は「無期限」を100年後の日付で表すことがある**（`payment_item_lesson_authority`
    は実測 2124-06-24 まで）。`TIMESTAMP` の上限は 2038-01-19 で、超えると
    `Incorrect datetime value` になる。**型の話なので NOT NULL や CHECK では拾えず、
    dry-run を素通りして実 INSERT で初めて落ちる**（受講の予行がこれで停止した）。
    """
    for column in schema.columns.values():
        if column.data_type != "timestamp":
            continue
        for index, record in enumerate(records):
            value = record.values.get(column.name)
            if not isinstance(value, datetime):
                continue
            if _TIMESTAMP_MIN <= value <= _TIMESTAMP_MAX:
                continue
            out.setdefault(
                index,
                Violation(
                    schema.table,
                    f"TIMESTAMP の範囲外 `{column.name}`",
                    f"{value.isoformat()}（1970-01-01〜2038-01-19）",
                    _key_of(record),
                ),
            )


def _checks(records: list[Record], schema: TableSchema, out: dict[int, Violation]) -> None:
    """`CHECK` の下限に当たる行を拾う。

    **UNIQUE / FK より先に見る。** 当たった行は誰とも衝突しないので、
    後続の判定から外れるほうが一覧が読みやすい。
    """
    for check in schema.checks:
        if check.column not in records[0].values:
            continue  # この Step が書かない列
        for index, record in enumerate(records):
            value = record.values.get(check.column)
            if value is None:
                if check.nullable:
                    continue
                continue  # NULL は NOT NULL 側で見る
            try:
                number = int(value)
            except (TypeError, ValueError):
                continue  # 数値でない値は解釈しない
            if number < check.minimum:
                out.setdefault(
                    index,
                    Violation(
                        schema.table,
                        f"CHECK `{check.name}`",
                        f"{check.column} = {number}（{check.minimum} 以上である必要がある）",
                        _key_of(record),
                    ),
                )


def _unique(
    records: list[Record], schema: TableSchema, target, out: dict[int, Violation]
) -> None:
    natural = set(records[0].natural_key)
    for key in schema.uniques:
        if not all(c in records[0].values for c in key.columns):
            continue  # この Step が書かない列を含むキーは見られない
        # 自然キーと同じ UNIQUE は見ない。**既にある行は `insert_many` が飛ばす**
        # （移行済みを「違反」として数えると、再実行のたびに一覧が汚れる）
        is_natural = set(key.columns) == natural

        groups: dict[tuple, list[int]] = {}
        for index, record in enumerate(records):
            if index in out:
                continue  # **別の理由ですでに移さない行。** 入らない行は誰とも衝突しない
            values = tuple(record.values.get(c) for c in key.columns)
            if any(v is None for v in values):
                continue  # MySQL の UNIQUE は NULL を重複と見なさない
            groups.setdefault(values, []).append(index)

        # (1) 同じバッチの中の重複。**どれを残すかはツールが決めない**ので全部移さない
        for values, indexes in groups.items():
            if len(indexes) > 1:
                for index in indexes:
                    out.setdefault(
                        index,
                        Violation(
                            schema.table,
                            f"UNIQUE `{key.name}` {key.columns}",
                            f"同じ値の行が移行元に {len(indexes)} 件ある: {values}",
                            _key_of(records[index]),
                        ),
                    )
        if is_natural or key.columns == ("id",):
            # **主キーは決定論 ULID。** 同じ値が移行先にあるなら「別の行と衝突した」
            # ではなく「同じ行がすでに入っている」で、`insert_many` が自然キーで飛ばす。
            # ここで違反として数えると、再実行のたびに一覧が汚れる
            continue
        # (2) 移行先にすでに同じ値がある
        singles = {v: i[0] for v, i in groups.items() if len(i) == 1}
        if len(key.columns) == 1 and singles:
            column = key.columns[0]
            wanted = {v[0] for v in singles}
            existing = target.known_ids(schema.table, column, wanted)
            for values, index in singles.items():
                if values[0] in existing and _already_migrated(records[index], target):
                    # **同じ行の再実行。** 自然キーで引くと移行先に居る＝前回入れた行なので、
                    # 「別の行と衝突した」ではない。`insert_many` が自然キーで飛ばす。
                    # ここで違反にすると、再実行のたびに一覧が汚れ、Step によっては
                    # 行が1件も残らず落ちる（旧 ID の列の UNIQUE を足したときに起きた）
                    continue
                if values[0] in existing:
                    out.setdefault(
                        index,
                        Violation(
                            schema.table,
                            f"UNIQUE `{key.name}` {key.columns}",
                            f"移行先に同じ値がすでにある: {values[0]}",
                            _key_of(records[index]),
                        ),
                    )


def _already_migrated(record: Record, target) -> bool:
    """この行が**前回の実行で入れた同じ行**か。自然キーが無ければ判定できない。"""
    if not record.natural_key:
        return False
    try:
        return target.exists(record.table, record.key_values())
    except KeyError:
        return False


def _foreign_keys(
    records: list[Record], schema: TableSchema, target, out: dict[int, Violation]
) -> None:
    """**参照先は「この実行で入る行」で見る。** すでに移さないと決まった行は勘定に入れない。"""
    for fk in schema.foreign_keys:
        if fk.column not in records[0].values:
            continue
        wanted = {r.values[fk.column] for r in records if r.values.get(fk.column) is not None}
        if not wanted:
            continue
        known = target.known_ids(fk.referenced_table, fk.referenced_column, wanted)
        if fk.referenced_table == schema.table:
            # 自己参照（グループの親子など）。**同じバッチの中の行も参照先になる。**
            # 親が先に来ているかは Step の並べ替えの責任
            known |= {
                r.values[fk.referenced_column]
                for i, r in enumerate(records)
                if i not in out and r.values.get(fk.referenced_column) is not None
            }
        for index, record in enumerate(records):
            value = record.values.get(fk.column)
            if value is not None and value not in known:
                out.setdefault(
                    index,
                    Violation(
                        schema.table,
                        f"外部キー `{fk.column}`",
                        f"{fk.referenced_table}.{fk.referenced_column} に参照先が無い",
                        _key_of(record),
                    ),
                )
