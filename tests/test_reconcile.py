"""投入後の照合（`verify`）のテスト。

**照合が「一致」と言ってしまう誤り**を中心に固定する。差を見逃す照合は、
照合しないより悪い（確かめたつもりになる）。
"""

from __future__ import annotations

import csv
import tempfile
import unittest
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import bcrypt

from migrator.core.passwords import LegacyPasswordCipher, PasswordMigration, PasswordToVerify
from migrator.core.records import Record
from migrator.validation import reconcile
from migrator.validation.reconcile import EXTRA, MISSING, VALUE, Reconciler, RecordingTarget, same

TENANT = "01ARZ3NDEKTSV4RRFFQ69G5FAV"


class FakeReader:
    """移行先の代わり。テーブル名 → 行のリスト。"""

    def __init__(self, tables: dict[str, list[dict]]) -> None:
        self.tables = tables

    def columns(self, table: str) -> set[str]:
        rows = self.tables.get(table) or [{}]
        return set(rows[0])

    def fetch(self, table, key_columns, keys):
        wanted = {tuple(reconcile._key_part(v) for v in k) for k in keys}
        return [
            r for r in self.tables.get(table, [])
            if tuple(reconcile._key_part(r.get(c)) for c in key_columns) in wanted
        ]

    def tenant_keys(self, table, key_columns, tenant_id):
        return [
            tuple(r[c] for c in key_columns)
            for r in self.tables.get(table, [])
            if r.get("tenant_id") == tenant_id
        ]


class Step:
    def __init__(self, name="s", volatile=()):
        self.name = name
        self.volatile_columns = volatile


def rec(id_, **values):
    return Record(
        table="t",
        values={"id": id_, "tenant_id": TENANT, **values},
        natural_key=("id",),
        source_key=id_,
    )


def make(tables):
    work = Path(tempfile.mkdtemp())
    return Reconciler(FakeReader(tables), work), work


def rows_of(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


class SameTest(unittest.TestCase):
    def test_driver_types_are_evened_out(self) -> None:
        self.assertTrue(same(True, 1))
        self.assertTrue(same(3, Decimal("3")))
        self.assertTrue(same(date(2020, 1, 2), date(2020, 1, 2)))
        self.assertTrue(same('{"b": 1, "a": 2}', '{"a": 2, "b": 1}'))

    def test_sub_second_rounding_is_not_a_difference(self) -> None:
        self.assertTrue(same(datetime(2020, 1, 1, 0, 0, 0, 600000), datetime(2020, 1, 1, 0, 0, 1)))

    def test_null_is_not_empty(self) -> None:
        # **NULL と空文字を同じにしない。** 意味が違う（未設定 / 空で設定済み）
        self.assertFalse(same(None, ""))
        self.assertFalse(same("", None))
        self.assertTrue(same(None, None))

    def test_real_differences_are_caught(self) -> None:
        self.assertFalse(same(False, 1))
        self.assertFalse(same(datetime(2020, 1, 1), datetime(2020, 1, 2)))
        self.assertFalse(same("active", "expired"))
        self.assertFalse(same('{"a": 1}', '{"a": 2}'))


class ReconcilerTest(unittest.TestCase):
    def test_all_three_kinds_are_reported(self) -> None:
        tables = {"t": [
            {"id": "A", "tenant_id": TENANT, "status": "active"},
            {"id": "B", "tenant_id": TENANT, "status": "expired"},
            {"id": "Z", "tenant_id": TENANT, "status": "active"},   # 変換結果に無い
            {"id": "X", "tenant_id": "other", "status": "active"},  # 他テナント
        ]}
        r, work = make(tables)
        report = r.check_step(Step(), [rec("A", status="active"), rec("B", status="active"), rec("C", status="active")])
        r.check_extras(TENANT, ["t"])

        self.assertEqual((report.matched, report.differing, report.missing), (1, 1, 1))
        self.assertEqual(r.tables[0].extra, 1)
        self.assertFalse(r.ok)
        kinds = sorted((d["kind"], d["key"]) for d in rows_of(r.path))
        self.assertEqual(kinds, sorted([(VALUE, "B"), (MISSING, "C"), (EXTRA, "id=Z")]))

    def test_matching_rows_are_ok(self) -> None:
        r, _ = make({"t": [{"id": "A", "tenant_id": TENANT, "n": 1}]})
        r.check_step(Step(), [rec("A", n=True)])
        r.check_extras(TENANT, ["t"])
        self.assertTrue(r.ok)

    def test_id_is_compared_when_looked_up_by_natural_key(self) -> None:
        # **決定論 ULID の照合を兼ねる。** 自然キーで当たっても id が違えば差
        r, _ = make({"t": [{"id": "OLD", "tenant_id": TENANT, "code": "x"}]})
        record = Record("t", {"id": "NEW", "tenant_id": TENANT, "code": "x"}, natural_key=("tenant_id", "code"))
        report = r.check_step(Step(), [record])
        self.assertEqual(report.by_column["id"], 1)

    def test_key_lookup_ignores_case_like_mysql(self) -> None:
        # 照合順序で大文字小文字を区別しない列。引き当てでは同じ行、値としては差
        r, _ = make({"t": [{"id": "A", "tenant_id": TENANT, "email": "Foo@example.com"}]})
        record = Record("t", {"id": "A", "tenant_id": TENANT, "email": "foo@example.com"},
                        natural_key=("tenant_id", "email"))
        report = r.check_step(Step(), [record])
        self.assertEqual((report.missing, report.by_column["email"]), (0, 1))

    def test_volatile_column_checks_presence_only(self) -> None:
        r, _ = make({"t": [
            {"id": "A", "tenant_id": TENANT, "at": datetime(2026, 9, 27)},
            {"id": "B", "tenant_id": TENANT, "at": None},
        ]})
        report = r.check_step(Step(volatile=("at",)), [rec("A", at=datetime(2026, 10, 3)),
                                                      rec("B", at=datetime(2026, 10, 3))])
        self.assertEqual((report.matched, report.differing), (1, 1))

    def test_extras_are_not_counted_when_some_writers_did_not_run(self) -> None:
        # `users` は会員と代理講師の2 Step が書く。片方だけ流すと、もう片方の行が
        # 「移行先にだけある」に化ける
        r, _ = make({"t": [{"id": "A", "tenant_id": TENANT}, {"id": "P", "tenant_id": TENANT}]})
        r.check_step(Step(), [rec("A")])
        r.check_extras(TENANT, [])
        self.assertEqual(r.tables[0].extra, 0)
        self.assertTrue(r.tables[0].skipped)

    def test_keys_are_pooled_across_steps_writing_one_table(self) -> None:
        r, _ = make({"t": [{"id": "A", "tenant_id": TENANT}, {"id": "P", "tenant_id": TENANT}]})
        r.check_step(Step("users"), [rec("A")])
        r.check_step(Step("proxy"), [rec("P")])
        r.check_extras(TENANT, ["t"])
        self.assertTrue(r.ok)

    def test_complete_tables_need_every_writer(self) -> None:
        class S:
            def __init__(self, name, table):
                self.name, self.target_table = name, table

        class P:
            def __init__(self, steps):
                self.steps = steps

        class Sec:
            def __init__(self, phases):
                self.phases = phases

        sections = [Sec([P([S("users", "users"), S("proxy", "users"), S("x", "x")])])]
        self.assertEqual(reconcile._complete_tables(sections, {"users", "x"}), ["x"])
        self.assertEqual(sorted(reconcile._complete_tables(sections, {"users", "proxy", "x"})),
                         ["users", "x"])


class PasswordTest(unittest.TestCase):
    """bcrypt はソルトが毎回違う。**作り直したハッシュどうしは比べられない。**"""

    def hashed(self, plaintext: str) -> str:
        return bcrypt.hashpw(plaintext.encode(), bcrypt.gensalt(4, prefix=b"2a")).decode()

    def test_hash_is_checked_against_the_plaintext(self) -> None:
        r, _ = make({"t": [
            {"id": "A", "tenant_id": TENANT, "password_hash": self.hashed("secret1")},
            {"id": "B", "tenant_id": TENANT, "password_hash": self.hashed("other")},
            {"id": "C", "tenant_id": TENANT, "password_hash": ""},
        ]})
        report = r.check_step(Step(), [
            rec("A", password_hash=PasswordToVerify("secret1")),
            rec("B", password_hash=PasswordToVerify("secret1")),
            rec("C", password_hash=PasswordToVerify("secret1")),
        ])
        self.assertEqual((report.matched, report.differing), (1, 2))

    def test_row_with_other_differences_is_counted_once(self) -> None:
        r, _ = make({"t": [{"id": "A", "tenant_id": TENANT, "name": "x", "password_hash": "bad"}]})
        report = r.check_step(Step(), [rec("A", name="y", password_hash=PasswordToVerify("p"))])
        self.assertEqual((report.matched, report.differing), (0, 1))
        self.assertEqual(sorted(report.by_column), ["name", "password_hash"])

    def test_plaintext_never_reaches_the_report(self) -> None:
        r, _ = make({"t": [{"id": "A", "tenant_id": TENANT, "password_hash": "bad"}]})
        r.check_step(Step(), [rec("A", password_hash=PasswordToVerify("hunter2-plain"))])
        self.assertNotIn("hunter2-plain", r.path.read_text(encoding="utf-8-sig"))
        self.assertNotIn("hunter2-plain", repr(PasswordToVerify("hunter2-plain")))
        self.assertNotIn("hunter2-plain", str(PasswordToVerify("hunter2-plain")))

    def test_verifying_migration_does_not_rehash(self) -> None:
        cipher = LegacyPasswordCipher("key")
        migration = PasswordMigration(cipher, verifying=True)
        # 暗号文を作る手段が無いので、復号結果を差し替えて確かめる
        cipher.decrypt = lambda stored: "plain"  # type: ignore[method-assign]
        value = migration.hash_for("ignored", 1)
        self.assertIsInstance(value, PasswordToVerify)
        self.assertTrue(value.matches(self.hashed("plain")))


class RecordingTargetTest(unittest.TestCase):
    def test_keeps_every_row_and_writes_nothing(self) -> None:
        target = RecordingTarget(None)
        records = [rec("A"), rec("B")]
        self.assertEqual(target.insert_many(records), 0)
        self.assertEqual(target.take(), records)
        self.assertEqual(target.take(), [])
        # 後ろの Step の外部キー確認のため、入れたことにして覚える
        self.assertEqual(target.known_ids("t", "id", {"A", "Q"}), {"A"})
        self.assertEqual(target.statements, [])


if __name__ == "__main__":
    unittest.main()
