"""変換部品の単体テスト。**Step を動かさずに変換だけを固定する。**"""

from __future__ import annotations

import unittest
from datetime import date, datetime

from migrator.core.codes import CodeMap, prefecture_name, role_map
from migrator.core.datetimes import (
    ColumnKind,
    DateBoundary,
    convert,
    convert_date,
    is_zero_date,
    split_date,
)
from migrator.core.ids import TenantId, UlidFactory
from migrator.core.polarity import Channel, OptoutSource, invert, optouts_for
from migrator.core.text import LengthCheck, find_over_length, join_name
from migrator.errors import MappingError


class UlidTest(unittest.TestCase):
    def setUp(self) -> None:
        self.factory = UlidFactory("lw2", 1_700_000_000_000)

    def test_deterministic(self) -> None:
        """同じ旧行からは同じ ID。再実行しても二重登録にならない。"""
        self.assertEqual(self.factory.for_row("user", 42), self.factory.for_row("user", 42))

    def test_differs_by_table_and_key(self) -> None:
        self.assertNotEqual(self.factory.for_row("user", 42), self.factory.for_row("user", 43))
        self.assertNotEqual(self.factory.for_row("user", 42), self.factory.for_row("tenant", 42))

    def test_namespace_changes_id(self) -> None:
        """採番規則を変えたら namespace も変える、を担保する。"""
        other = UlidFactory("lw2-v2", 1_700_000_000_000)
        self.assertNotEqual(self.factory.for_row("user", 42), other.for_row("user", 42))

    def test_tenant_id_cannot_be_renumbered(self) -> None:
        tenant = TenantId()
        tenant.resolve("0" * 26)
        with self.assertRaises(RuntimeError):
            tenant.resolve("1" * 26)


class DatetimeTest(unittest.TestCase):
    def test_jst_to_utc(self) -> None:
        """JST naive をそのまま書くと9時間ずれる。timestamp 列は UTC に直す。"""
        self.assertEqual(
            convert(datetime(2026, 1, 1, 9, 0, 0), ColumnKind.TIMESTAMP),
            datetime(2026, 1, 1, 0, 0, 0),
        )

    def test_date_boundary(self) -> None:
        """終了日は 23:59:59 を補う。開始日と同じ扱いにすると1日ずれる。"""
        self.assertEqual(
            convert_date(date(2026, 1, 1), ColumnKind.DATETIME, DateBoundary.END),
            datetime(2026, 1, 1, 14, 59, 59),
        )

    def test_birthday_is_split_not_collapsed(self) -> None:
        self.assertEqual(split_date(datetime(1990, 5, 3)), (1990, 5, 3))


class CodeMapTest(unittest.TestCase):
    def test_unknown_value_stops(self) -> None:
        """対応表に無い値は既定値に倒さず停止する。"""
        mapping = CodeMap("role", {2: "tenant_admin"}, source="運営")
        with self.assertRaises(MappingError):
            mapping.to_new(9)

    def test_platform_admin_is_rejected(self) -> None:
        """移行で platform_admin を出力し得ないことを、表の作成時点で固定する。"""
        with self.assertRaises(MappingError):
            role_map({1: "platform_admin"}, "運営")


class PrefectureTest(unittest.TestCase):
    def test_zero_is_unselected(self):
        """`pref_id=0` は未選択。`pref_master` は 1 始まりなので NULL と同じ扱いにする。"""
        self.assertIsNone(prefecture_name(0, {1: "北海道"}))

    def test_unknown_stops(self):
        with self.assertRaises(MappingError):
            prefecture_name(99, {1: "北海道"})


class ZeroDateTest(unittest.TestCase):
    def test_zero_date_string(self):
        """ドライバが日時に直せず文字列で返すゼロ日付を拾う。"""
        self.assertTrue(is_zero_date("0000-00-00 00:00:00"))
        self.assertTrue(is_zero_date("0000-00-00"))

    def test_normal_values(self):
        self.assertFalse(is_zero_date(datetime(2020, 1, 1)))
        self.assertFalse(is_zero_date(None))
        self.assertFalse(is_zero_date("2020-01-01"))


class PolarityTest(unittest.TestCase):
    def test_invert(self) -> None:
        self.assertTrue(invert(0))  # 受け取らない → optout を作る
        self.assertFalse(invert(1))
        self.assertFalse(invert(None))  # 未設定は既定で受け取る

    def test_channel_is_kept(self) -> None:
        """PC と携帯を1つに畳まない。"""
        row = {"pc": 0, "mobile": 1}
        out = optouts_for(
            row,
            (
                OptoutSource("pc", "announcement", Channel.PC),
                OptoutSource("mobile", "announcement", Channel.MOBILE),
            ),
        )
        self.assertEqual([(o.kind, o.channel) for o in out], [("announcement", Channel.PC)])


class TextTest(unittest.TestCase):
    def test_join_name(self) -> None:
        self.assertEqual(join_name("山田", "太郎"), "山田 太郎")
        self.assertEqual(join_name(None, "太郎"), "太郎")

    def test_over_length_is_reported(self) -> None:
        self.assertEqual(find_over_length([{"tel": "0" * 40}], (LengthCheck("tel", 32),)), {"tel": 1})


if __name__ == "__main__":
    unittest.main()
