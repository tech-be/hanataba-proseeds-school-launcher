"""投入後の照合（`verify`）。**移行元から作り直した行と、移行先の行を突き合わせる。**

`run` の再実行は自然キーが既にある行を飛ばすだけで、**値までは見ない**。
古いコードで入れた行に誤りが残っていても、件数は合い、再実行も 0 行で終わる。
ここではそれを拾うために、次の3つを見る。

1. **行が無い** — 変換結果にあるのに、移行先に自然キーが一致する行が無い
2. **値が違う** — 自然キーは一致するが、列の値が違う（`id` を含む。決定論 ULID の照合を兼ねる）
3. **移行先にだけある** — 対象テナントの行なのに、変換結果のどれにも当たらない

**書き込みは一切しない。** Step は `run --dry-run` と同じ経路で流し、
`insert_many` に渡る行を横取りして突き合わせる。制約に当たって移さない行は
`run` と同じく照合の対象から外れる（一覧は `work_dir/verify/` に出す）。
"""

from __future__ import annotations

import csv
import datetime as dt
import json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Iterable

from ..core.passwords import PasswordToVerify
from ..core.records import Record
from ..db.target import TargetDatabase

#: 差の一覧。`not-migrated.csv` と同じく ASCII 名で、中身は日本語
FILENAME = "differences.csv"
HEADER = ("step", "table", "key", "kind", "column", "expected", "actual")

MISSING = "行が無い"
VALUE = "値が違う"
EXTRA = "移行先にだけある"

#: 一覧に出す値の長さ。JSON の設定値などは長いので切る
MAX_SHOWN = 200
#: 一度に引く自然キーの数
CHUNK = 500


class RecordingTarget(TargetDatabase):
    """**書かずに、渡された行を取っておく**移行先。

    `run` の再実行と違い、既にある行も含めて**すべて**取っておく
    （飛ばされた行こそ照合したい）。「この実行で入れた行」としても覚えるので、
    後ろの Step の外部キー確認は `run` を最初から流したときと同じ結果になる。
    """

    def __init__(self, connection, batch_size: int = 500) -> None:
        super().__init__(connection, dry_run=True, batch_size=batch_size)
        self.captured: list[Record] = []

    def insert_many(self, records: list[Record]) -> int:
        if not records:
            return 0
        self._remember(records[0].table, records)
        self.captured.extend(records)
        return 0

    def take(self) -> list[Record]:
        taken, self.captured = self.captured, []
        return taken


class TargetReader:
    """照合のための読み出し。**テストでは差し替える**ので、SQL はここに閉じ込める。"""

    def __init__(self, target: TargetDatabase) -> None:
        self._target = target
        self._columns: dict[str, set[str]] = {}

    def columns(self, table: str) -> set[str]:
        if table not in self._columns:
            rows = self._target.query(
                "SELECT COLUMN_NAME AS c FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s",
                (table,),
            )
            self._columns[table] = {str(r["c"]) for r in rows}
        return self._columns[table]

    def fetch(self, table: str, key_columns: tuple[str, ...], keys: list[tuple]) -> list[dict]:
        """自然キーが `keys` のどれかに当たる行を返す。"""
        out: list[dict] = []
        # NULL を含むキーは `IN` で当たらないので、1件ずつ `<=>` で引く
        plain = [k for k in keys if None not in k]
        nullable = [k for k in keys if None in k]
        cols = ", ".join(f"`{c}`" for c in key_columns)
        row_ph = "(" + ", ".join(["%s"] * len(key_columns)) + ")"
        for start in range(0, len(plain), CHUNK):
            chunk = plain[start : start + CHUNK]
            sql = (
                f"SELECT * FROM `{table}` WHERE ({cols}) IN ("
                + ", ".join([row_ph] * len(chunk))
                + ")"
            )
            out.extend(self._target.query(sql, tuple(v for k in chunk for v in k)))
        for key in nullable:
            where = " AND ".join(f"`{c}` <=> %s" for c in key_columns)
            out.extend(self._target.query(f"SELECT * FROM `{table}` WHERE {where}", key))
        return out

    def tenant_keys(self, table: str, key_columns: tuple[str, ...], tenant_id: str) -> list[tuple]:
        cols = ", ".join(f"`{c}`" for c in key_columns)
        rows = self._target.query(
            f"SELECT {cols} FROM `{table}` WHERE `tenant_id` = %s", (tenant_id,)
        )
        return [tuple(r[c] for c in key_columns) for r in rows]


# --- 値の比べ方 --------------------------------------------------------------
def _key_part(value: object) -> object:
    """自然キーの突き合わせ用。**MySQL の照合順序に合わせて大文字小文字と末尾空白を無視する。**"""
    value = _plain(value)
    if isinstance(value, str):
        return value.rstrip().casefold()
    return value


def _plain(value: object) -> object:
    """ドライバの型の違いをならす（bool / bytes / Decimal / 日時）。"""
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (bytes, bytearray)):
        return bytes(value).decode("utf-8", "replace")
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, dt.datetime):
        return value.replace(tzinfo=None)
    return value


def _json(value: object) -> object:
    """JSON として読めるなら読む。キーの順や空白の違いを差にしない。"""
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str) and value.lstrip()[:1] in ("{", "["):
        try:
            return json.loads(value)
        except ValueError:
            return value
    return value


def same(expected: object, actual: object) -> bool:
    """期待値（変換結果）と実際の値（移行先）が同じか。"""
    if isinstance(expected, PasswordToVerify):
        return expected.matches(actual)
    a, b = _plain(expected), _plain(actual)
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, dt.datetime) and isinstance(b, dt.datetime):
        # **秒未満は列の精度で丸められる。** 1秒未満の差は同じとみなす
        return abs((a - b).total_seconds()) < 1
    if isinstance(a, dt.date) and isinstance(b, dt.date):
        return a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(float(a) - float(b)) < 1e-9
    a, b = _json(a), _json(b)
    if a == b:
        return True
    # 数値の列に文字列で入れた（またはその逆）。表記が同じなら同じ
    return str(a) == str(b)


def _shown(value: object) -> str:
    if isinstance(value, PasswordToVerify):
        return "（旧パスワード）"  # **平文は出さない**
    if value is None:
        return "NULL"
    text = value.isoformat(sep=" ") if isinstance(value, dt.datetime) else str(_plain(value))
    return text if len(text) <= MAX_SHOWN else text[:MAX_SHOWN] + "…"


# --- 結果 --------------------------------------------------------------------
@dataclass
class Difference:
    step: str
    table: str
    key: str
    kind: str
    column: str = ""
    expected: str = ""
    actual: str = ""


@dataclass
class StepReport:
    """1 Step 分の照合結果。"""

    step: str
    table: str
    expected: int = 0
    matched: int = 0
    missing: int = 0
    differing: int = 0
    #: 列 → 値が違った行数
    by_column: Counter = field(default_factory=Counter)

    @property
    def ok(self) -> bool:
        return self.missing == 0 and self.differing == 0

    def __str__(self) -> str:
        head = f"{self.step}: 期待 {self.expected} / 一致 {self.matched}"
        if self.missing:
            head += f" / 行が無い {self.missing}"
        if self.differing:
            cols = ", ".join(f"{c} {n}" for c, n in self.by_column.most_common(5))
            head += f" / 値が違う {self.differing}（{cols}）"
        return head + ("" if self.ok else "  <-- 差あり")


@dataclass
class TableReport:
    """移行先にだけある行（テーブル単位）。"""

    table: str
    extra: int = 0
    #: 数えられなかった理由。空なら数えた
    skipped: str = ""

    def __str__(self) -> str:
        if self.skipped:
            return f"{self.table}: 移行先にだけある行は数えていない（{self.skipped}）"
        return f"{self.table}: 移行先にだけある {self.extra} 行" + ("  <-- 差あり" if self.extra else "")


class Reconciler:
    """Step ごとに行を受け取り、移行先と突き合わせる。"""

    def __init__(self, reader: TargetReader, work_dir: Path, password_workers: int = 8) -> None:
        self._reader = reader
        self._path = Path(work_dir) / FILENAME
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("w", encoding="utf-8-sig", newline="") as handle:
            csv.writer(handle).writerow(HEADER)
        self._workers = password_workers
        self.steps: list[StepReport] = []
        self.tables: list[TableReport] = []
        #: テーブル → 変換結果のキー（`移行先にだけある` を数えるため）。
        #: テーブル → (キーの列, キーの集合)
        self._seen: dict[str, tuple[tuple[str, ...] | None, set]] = {}

    @property
    def path(self) -> Path:
        return self._path

    @property
    def ok(self) -> bool:
        return all(s.ok for s in self.steps) and not any(t.extra for t in self.tables)

    # --- Step 単位 ------------------------------------------------------------
    def check_step(self, step, records: list[Record]) -> StepReport | None:
        if not records:
            return None
        by_table: dict[str, list[Record]] = {}
        for record in records:
            by_table.setdefault(record.table, []).append(record)
        report = None
        for table, rows in by_table.items():
            report = self._check_table(step, table, rows)
            self.steps.append(report)
        return report

    def _check_table(self, step, table: str, records: list[Record]) -> StepReport:
        report = StepReport(step=step.name, table=table, expected=len(records))
        key_columns = records[0].natural_key or (("id",) if "id" in records[0].values else ())
        self._note_keys(table, records)
        if not key_columns:
            # 自然キーも id も無い行は引き当てられない。**黙って一致扱いにしない**
            report.missing = len(records)
            self._write(
                [Difference(step.name, table, "", MISSING, "", "自然キーが無く照合できない", "")]
            )
            return report

        keys = [tuple(r.values.get(c) for c in key_columns) for r in records]
        found: dict[tuple, dict] = {}
        for row in self._reader.fetch(table, key_columns, keys):
            found.setdefault(tuple(_key_part(row.get(c)) for c in key_columns), row)

        volatile = set(getattr(step, "volatile_columns", ()) or ())
        diffs: list[Difference] = []
        pending_passwords: list[tuple[Record, str, dict]] = []
        for record, key in zip(records, keys):
            label = _label(record, key_columns)
            actual = found.get(tuple(_key_part(v) for v in key))
            if actual is None:
                report.missing += 1
                diffs.append(Difference(step.name, table, label, MISSING))
                continue
            row_diffs: list[Difference] = []
            for column, expected in record.values.items():
                if column not in actual:
                    row_diffs.append(
                        Difference(step.name, table, label, VALUE, column, _shown(expected), "（列が無い）")
                    )
                    continue
                if isinstance(expected, PasswordToVerify):
                    pending_passwords.append((record, column, actual))
                    continue
                if column in volatile:
                    if (expected is None) != (actual[column] is None):
                        row_diffs.append(
                            Difference(step.name, table, label, VALUE, column,
                                       "NULL" if expected is None else "（値あり）", _shown(actual[column]))
                        )
                    continue
                if not same(expected, actual[column]):
                    row_diffs.append(
                        Difference(step.name, table, label, VALUE, column, _shown(expected), _shown(actual[column]))
                    )
            self._tally(report, row_diffs, diffs)
            if not row_diffs:
                report.matched += 1

        # **bcrypt は1件に数十ミリ秒かかる。** 会員数ぶん直列に回すと分単位になるので並べる
        if pending_passwords:
            differing = {d.key for d in diffs if d.kind == VALUE}
            self._check_passwords(step, table, key_columns, pending_passwords, report, diffs, differing)
        self._write(diffs)
        return report

    def _check_passwords(self, step, table, key_columns, pending, report, diffs, differing) -> None:
        def verdict(item):
            record, column, actual = item
            return item, record.values[column].matches(actual[column])

        with ThreadPoolExecutor(max_workers=self._workers) as pool:
            results = list(pool.map(verdict, pending))
        for (record, column, _actual), ok in results:
            if ok:
                continue
            label = _label(record, key_columns)
            diffs.append(
                Difference(step.name, table, label, VALUE, column, "（旧パスワード）", "旧パスワードと合わない")
            )
            report.by_column[column] += 1
            if label not in differing:
                # 他の列では一致していた行。一致から差ありに数え直す
                differing.add(label)
                report.differing += 1
                report.matched -= 1

    @staticmethod
    def _tally(report: StepReport, row_diffs: list[Difference], diffs: list[Difference]) -> None:
        if not row_diffs:
            return
        report.differing += 1
        for diff in row_diffs:
            report.by_column[diff.column] += 1
        diffs.extend(row_diffs)

    # --- 移行先にだけある行 ---------------------------------------------------
    def _note_keys(self, table: str, records: list[Record]) -> None:
        """**同じテーブルに書く Step が複数ある**（`users` / `enrollments` など）ので、
        キーはテーブル単位で合算する。Step ごとに自然キーが違うときは `id` で揃える。
        """
        if all("id" in r.values for r in records):
            columns: tuple[str, ...] | None = ("id",)
        else:
            columns = records[0].natural_key or None
        prior = self._seen.get(table)
        if prior is not None and prior[0] != columns:
            columns = None  # 揃えられない
        keys = prior[1] if prior else set()
        if columns:
            keys |= {tuple(_key_part(r.values.get(c)) for c in columns) for r in records}
        self._seen[table] = (columns, keys)

    def check_extras(self, tenant_id: str, complete_tables: Iterable[str]) -> None:
        """対象テナントの行のうち、変換結果のどれにも当たらないものを数える。

        `complete_tables` は**書く Step がすべて今回の照合に含まれる**テーブル。
        一部の Step しか流していないテーブルで数えると、流していない Step の行が
        「移行先にだけある」に化けるので数えない。
        """
        complete = set(complete_tables)
        diffs: list[Difference] = []
        for table, (columns, keys) in sorted(self._seen.items()):
            report = TableReport(table=table)
            if table not in complete:
                report.skipped = "このテーブルに書く Step の一部しか照合していない"
            elif columns is None:
                report.skipped = "Step ごとに行の識別子が違う"
            elif "tenant_id" not in self._reader.columns(table):
                report.skipped = "tenant_id を持たない"
            else:
                for key in self._reader.tenant_keys(table, columns, tenant_id):
                    if tuple(_key_part(v) for v in key) not in keys:
                        report.extra += 1
                        label = ", ".join(f"{c}={_shown(v)}" for c, v in zip(columns, key))
                        diffs.append(Difference("", table, label, EXTRA))
            self.tables.append(report)
        self._write(diffs)

    # --- 出力 -----------------------------------------------------------------
    def _write(self, diffs: list[Difference]) -> None:
        if not diffs:
            return
        with self._path.open("a", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle)
            for d in diffs:
                writer.writerow([d.step, d.table, d.key, d.kind, d.column, d.expected, d.actual])

    def summary(self) -> str:
        lines = ["", "=== 照合結果 ==="]
        lines.extend(f"  {s}" for s in self.steps)
        extras = [t for t in self.tables if t.extra or t.skipped]
        if extras:
            lines.append("")
            lines.append("  --- 移行先にだけある行 ---")
            lines.extend(f"  {t}" for t in extras)
        counted = [t for t in self.tables if not t.skipped]
        lines.append("")
        total = sum(s.expected for s in self.steps)
        bad = sum(s.missing + s.differing for s in self.steps) + sum(t.extra for t in self.tables)
        lines.append(
            f"  {len(self.steps)} Step / {total} 行を照合、"
            f"移行先にだけある行は {len(counted)} テーブルで数えた"
        )
        if self.ok:
            lines.append("  照合 OK")
        else:
            lines.append(f"  照合 NG: 差のある行 {bad} 行 → {self._path}")
        return "\n".join(lines)


def reconcile(ctx, selected, sections) -> Reconciler:
    """選んだフェーズを**書かずに**流し、Step ごとに移行先と突き合わせる。

    `ctx.target` は `RecordingTarget` であること。フェーズの区切りの検証（`Phase.checks`）と
    コミットは通さない — 何も書かないので要らない。
    """
    target = ctx.target
    if not isinstance(target, RecordingTarget):
        raise TypeError("照合は RecordingTarget で流す（書き込みを伴う移行先では流さない）")
    reconciler = Reconciler(TargetReader(target), Path(ctx.config.work_dir) / "verify")
    ran: set[str] = set()
    for phase in selected:
        ctx.logger.info("=== %s %s（照合） ===", phase.key, phase.name)
        for step in phase.steps:
            step.run(ctx)
            report = reconciler.check_step(step, target.take())
            if report is not None and not report.ok:
                ctx.logger.warning("%s", report)
            ran.add(step.name)
        ctx.completed.add(phase.key)

    if ctx.tenant_id.resolved:
        reconciler.check_extras(ctx.tenant_id.value, _complete_tables(sections, ran))
    return reconciler


def _complete_tables(sections, ran: set[str]) -> list[str]:
    """書く Step が**すべて**今回流れたテーブル。"""
    owners: dict[str, set[str]] = {}
    for section in sections:
        for phase in section.phases:
            for step in phase.steps:
                if step.target_table:
                    owners.setdefault(step.target_table, set()).add(step.name)
    return [table for table, names in owners.items() if names <= ran]


def _label(record: Record, key_columns: tuple[str, ...]) -> str:
    """一覧に出すキー。**旧キーがあればそれを使う**（新環境の ULID では旧のどの行か分からない）。"""
    if record.source_key is not None:
        return str(record.source_key)
    return ", ".join(f"{c}={_shown(record.values.get(c))}" for c in key_columns)
