"""補正データ（暫定対応で決めた値）のテスト。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from migrator.errors import ConfigError
from migrator.overrides import Overrides


def write(text: str) -> Path:
    path = Path(tempfile.mkdtemp()) / "overrides.csv"
    path.write_text("table,key,column,value,memo\n" + text, encoding="utf-8")
    return path


class LoadTest(unittest.TestCase):
    def test_missing_file_is_empty(self):
        """**暫定対応が無くても流せる。** 無いこと自体はエラーにしない。"""
        self.assertEqual(Overrides.load(Path("/存在しない/overrides.csv")).values, {})

    def test_blank_value_is_not_applied(self):
        """雛形のまま流しても事故らない（未記入は適用しない）。"""
        overrides = Overrides.load(write("user,101,mail_add,,まだ決まっていない\n"))
        self.assertEqual(overrides.values, {})

    def test_null_word_clears_the_value(self):
        overrides = Overrides.load(write("user,101,line_id,NULL,この会員からは外す\n"))
        self.assertIsNone(overrides.values[("user", "101")]["line_id"])

    def test_unknown_table_stops(self):
        """主キーが分からないテーブルは上書きできない（どの行か決められない）。"""
        with self.assertRaises(ConfigError):
            Overrides.load(write("unknown_table,1,col,value,\n"))


class ApplyTest(unittest.TestCase):
    def setUp(self):
        self.overrides = Overrides.load(
            write("user,101,mail_add,taro@example.test,欠損のため割り当て\nuser,102,role_id,7,\n")
        )

    def test_applies_by_primary_key(self):
        rows = [{"user_id": 101, "mail_add": None}, {"user_id": 103, "mail_add": "x@example.test"}]
        applied = self.overrides.apply("user", rows)
        self.assertEqual(applied, 1)
        self.assertEqual(rows[0]["mail_add"], "taro@example.test")
        self.assertEqual(rows[1]["mail_add"], "x@example.test")

    def test_columns_the_step_did_not_read_are_left_alone(self):
        """その Step が読んでいない列には触らない（抽出列は Step ごとに違う）。"""
        rows = [{"user_id": 102, "line_id": "U1"}]
        self.assertEqual(self.overrides.apply("user", rows), 0)

    def test_table_without_its_key_is_skipped(self):
        rows = [{"mail_add": None}]  # user_id を抽出していない
        self.assertEqual(self.overrides.apply("user", rows), 0)

    def test_unknown_keys_are_reported(self):
        self.assertEqual(self.overrides.unknown_keys("user", {"101"}), ["102"])
