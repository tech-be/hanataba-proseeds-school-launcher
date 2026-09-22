"""設定と `.env` の読み方のテスト。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from migrator import envfile
from migrator.config import load
from migrator.errors import ConfigError


class EnvFileTest(unittest.TestCase):
    def test_parses_comments_quotes_and_export(self) -> None:
        text = """
        # コメント
        export SOURCE_DB_URL=mysql://u:p@127.0.0.1:3306/lw2
        TARGET_DB_URL="mysql://u:p@127.0.0.1:3307/learningware"
        EMPTY=
        """
        values = envfile.parse(text)
        self.assertEqual(values["SOURCE_DB_URL"], "mysql://u:p@127.0.0.1:3306/lw2")
        self.assertEqual(values["TARGET_DB_URL"], "mysql://u:p@127.0.0.1:3307/learningware")
        self.assertEqual(values["EMPTY"], "")

    def test_real_env_wins(self) -> None:
        """CI や本番で `.env` が紛れ込んでも、環境変数が勝つ。"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text("SOURCE_DB_URL=mysql://file/x\n", encoding="utf-8")
            merged = envfile.load(path, env={"SOURCE_DB_URL": "mysql://env/x"})
            self.assertEqual(merged["SOURCE_DB_URL"], "mysql://env/x")

    def test_missing_file_is_fine(self) -> None:
        self.assertEqual(envfile.load("/nonexistent/.env", env={"A": "1"}), {"A": "1"})


class ConfigLoadTest(unittest.TestCase):
    def test_dsn_comes_from_env(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            path.write_text(
                '{"tenant": {"legacy_id": 12, "slug": "recademy"}}', encoding="utf-8"
            )
            config = load(path, env={"SOURCE_DB_URL": "mysql://a/b", "TARGET_DB_URL": "mysql://c/d"})
            self.assertEqual(config.source_dsn, "mysql://a/b")
            self.assertEqual(config.target_dsn, "mysql://c/d")
            self.assertEqual(config.tenant.legacy_id, 12)

    def test_missing_tenant_stops(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            path.write_text("{}", encoding="utf-8")
            with self.assertRaises(ConfigError):
                load(path, env={})


if __name__ == "__main__":
    unittest.main()
