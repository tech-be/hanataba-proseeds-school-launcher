"""career の DB への投入（2 つ目の移行先）のテスト。

**career は btoc とは別の DB。** 取り違えると、career の表が btoc に入ろうとして落ちるか、
照合が別の DB を引いて「行が無い」になる。
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from migrator.context import build_context
from migrator.core.records import Record
from migrator.db.target import TargetDatabase
from migrator.errors import ConfigError
from migrator.steps.base import Step
from migrator.validation.reconcile import Reconciler
from tests.fakes import FakeSource
from tests.test_reconcile import FakeReader
from tests.test_steps import CONFIG


class _Recorder(TargetDatabase):
    def __init__(self) -> None:
        super().__init__(None, dry_run=True)
        self.loaded: list[Record] = []

    def insert_many(self, records):
        self.loaded.extend(records)
        return len(records)


class _CareerStep(Step):
    name = "test.career"
    database = "career"

    def extract(self, ctx):
        return [{"id": "A"}]

    def transform(self, ctx, rows):
        return [Record("companies", {"id": r["id"]}, natural_key=("id",)) for r in rows]


class _BtocStep(_CareerStep):
    name = "test.btoc"
    database = "btoc"


class CareerTargetTest(unittest.TestCase):
    def test_career_step_loads_into_career(self) -> None:
        btoc, career = _Recorder(), _Recorder()
        ctx = build_context(CONFIG, FakeSource({}), btoc, career=career)
        _CareerStep().run(ctx)
        _BtocStep().run(ctx)
        self.assertEqual([r.table for r in career.loaded], ["companies"])
        self.assertEqual(len(btoc.loaded), 1)  # btoc の Step の分だけ

    def test_career_step_without_connection_stops(self) -> None:
        """**接続が無ければ止める。** 黙って btoc に入れない。"""
        ctx = build_context(CONFIG, FakeSource({}), _Recorder())
        with self.assertRaises(ConfigError):
            _CareerStep().run(ctx)

    def test_targets_include_career(self) -> None:
        btoc, career = _Recorder(), _Recorder()
        self.assertEqual(build_context(CONFIG, None, btoc, career=career).targets(), [btoc, career])
        self.assertEqual(build_context(CONFIG, None, btoc).targets(), [btoc])


class ReconcileByDatabaseTest(unittest.TestCase):
    def test_career_rows_are_checked_against_career(self) -> None:
        """career の行は career の DB で引く（btoc で引くと「行が無い」になる）。"""
        work = Path(tempfile.mkdtemp())
        btoc = FakeReader({})
        career = FakeReader({"companies": [{"id": "A"}]})
        reconciler = Reconciler(btoc, work, others={"career": career})
        report = reconciler.check_step(_CareerStep(), [Record("companies", {"id": "A"}, natural_key=("id",))])
        self.assertTrue(report.ok, report)


if __name__ == "__main__":
    unittest.main()
