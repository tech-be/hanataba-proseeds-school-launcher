"""投入前の制約チェックのテスト。

**当たった行を移さない**ことを確かめるのが目的。実 DB には繋がない。
"""

from __future__ import annotations

import unittest

from migrator.core.records import Record
from migrator.validation.constraints import (
    ColumnSpec,
    ForeignKey,
    TableSchema,
    UniqueKey,
    filter_valid,
)


class FakeTarget:
    """`known_ids` だけを持つ移行先。"""

    def __init__(self, known: set | None = None) -> None:
        self._known = known or set()

    def known_ids(self, table, column, wanted):
        return {v for v in wanted if v in self._known}


def column(name, nullable=True, has_default=False, auto=False):
    return ColumnSpec(name=name, nullable=nullable, has_default=has_default, auto=auto)


class NotNullTest(unittest.TestCase):
    def schema(self):
        return TableSchema(
            "t",
            {"id": column("id", nullable=False), "linked_at": column("linked_at", nullable=False)},
        )

    def test_missing_column_is_not_migrated(self):
        """**INSERT の列に入っていない** NOT NULL 列を捕まえる（external_user_links の事例）。"""
        records = [Record(table="t", values={"id": "A"}, source_key=1)]
        valid, violations = filter_valid(records, self.schema(), FakeTarget())
        self.assertEqual(valid, [])
        self.assertEqual(violations[0].key, "1")
        self.assertIn("linked_at", violations[0].reason)
        self.assertIn("INSERT の列に入っていない", violations[0].detail)

    def test_null_value_is_not_migrated(self):
        records = [Record(table="t", values={"id": "A", "linked_at": None})]
        valid, violations = filter_valid(records, self.schema(), FakeTarget())
        self.assertEqual(valid, [])
        self.assertEqual(len(violations), 1)

    def test_valid_rows_are_kept(self):
        """**当たっていない行は移す。** 1件の違反で全部を止めない。"""
        records = [
            Record(table="t", values={"id": "A", "linked_at": None}, source_key=1),
            Record(table="t", values={"id": "B", "linked_at": "2020-01-01"}, source_key=2),
        ]
        valid, violations = filter_valid(records, self.schema(), FakeTarget())
        self.assertEqual([r.values["id"] for r in valid], ["B"])
        self.assertEqual([v.key for v in violations], ["1"])

    def test_default_and_generated_columns_are_fine(self):
        schema = TableSchema(
            "t",
            {
                "id": column("id", nullable=False),
                "status": column("status", nullable=False, has_default=True),
                "created_at": column("created_at", nullable=False, auto=True),
            },
        )
        valid, violations = filter_valid([Record(table="t", values={"id": "A"})], schema, FakeTarget())
        self.assertEqual(len(valid), 1)
        self.assertEqual(violations, [])


class UniqueTest(unittest.TestCase):
    SCHEMA = TableSchema(
        "t",
        {"id": column("id", nullable=False), "code": column("code")},
        uniques=(UniqueKey("uk_code", ("code",)),),
    )

    def test_every_row_of_a_duplicate_group_is_left_out(self):
        """**どれを残すかはツールが決めない。** 重複した行はどれも移さない。"""
        records = [
            Record(table="t", values={"id": "A", "code": "x"}, source_key=1),
            Record(table="t", values={"id": "B", "code": "x"}, source_key=2),
            Record(table="t", values={"id": "C", "code": "y"}, source_key=3),
        ]
        valid, violations = filter_valid(records, self.SCHEMA, FakeTarget())
        self.assertEqual([r.values["id"] for r in valid], ["C"])
        self.assertEqual([v.key for v in violations], ["1", "2"])

    def test_existing_value_in_target_is_left_out(self):
        records = [Record(table="t", values={"id": "A", "code": "x"}, source_key=1)]
        valid, violations = filter_valid(records, self.SCHEMA, FakeTarget(known={"x"}))
        self.assertEqual(valid, [])
        self.assertIn("移行先に同じ値がすでにある", violations[0].detail)

    def test_null_is_not_a_duplicate(self):
        """MySQL の UNIQUE は NULL を重複と見なさない。"""
        records = [
            Record(table="t", values={"id": "A", "code": None}),
            Record(table="t", values={"id": "B", "code": None}),
        ]
        valid, violations = filter_valid(records, self.SCHEMA, FakeTarget())
        self.assertEqual(len(valid), 2)
        self.assertEqual(violations, [])


class ForeignKeyTest(unittest.TestCase):
    SCHEMA = TableSchema(
        "t",
        {"id": column("id", nullable=False), "user_id": column("user_id")},
        foreign_keys=(ForeignKey("user_id", "users", "id"),),
    )

    def test_missing_parent_is_not_migrated(self):
        records = [Record(table="t", values={"id": "A", "user_id": "U1"}, source_key=7)]
        valid, violations = filter_valid(records, self.SCHEMA, FakeTarget(known=set()))
        self.assertEqual(valid, [])
        self.assertEqual(violations[0].key, "7")
        self.assertIn("users.id", violations[0].detail)

    def test_existing_parent_is_fine(self):
        records = [Record(table="t", values={"id": "A", "user_id": "U1"})]
        valid, violations = filter_valid(records, self.SCHEMA, FakeTarget(known={"U1"}))
        self.assertEqual(len(valid), 1)
        self.assertEqual(violations, [])

    def test_self_reference_uses_the_same_batch(self):
        """グループの親子。**親が同じバッチにいれば参照できる**（並べ替えは Step の責任）。"""
        schema = TableSchema(
            "groups",
            {"id": column("id", nullable=False), "parent_id": column("parent_id")},
            foreign_keys=(ForeignKey("parent_id", "groups", "id"),),
        )
        records = [
            Record(table="groups", values={"id": "P", "parent_id": None}),
            Record(table="groups", values={"id": "C", "parent_id": "P"}),
        ]
        valid, violations = filter_valid(records, schema, FakeTarget())
        self.assertEqual(len(valid), 2)
        self.assertEqual(violations, [])

    def test_no_schema_means_no_check(self):
        """接続が無いとき（テスト・plan）は素通りする。"""
        records = [Record(table="t", values={"id": "A"})]
        valid, violations = filter_valid(records, None, FakeTarget())
        self.assertEqual(valid, records)
        self.assertEqual(violations, [])
