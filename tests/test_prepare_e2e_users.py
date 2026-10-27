"""E2E のテスト用の会員を用意するスクリプトの、**書き込み先の取り違えを止める**部分のテスト。"""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

_PATH = Path(__file__).resolve().parent.parent / "scripts" / "prepare_e2e_users.py"
_spec = importlib.util.spec_from_file_location("prepare_e2e_users", _PATH)
prep = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(prep)


class DatabaseGuardTest(unittest.TestCase):
    def test_development_database_is_refused(self) -> None:
        """**開発の環境の DB（learningware）には書き込まない。**"""
        for name in ("learningware", "school_launcher", ""):
            with self.assertRaises(SystemExit):
                prep.check_database(name)

    def test_check_database_is_accepted(self) -> None:
        self.assertEqual(prep.check_database("lw2_schema_check"), "lw2_schema_check")

    def test_only_database_name_is_replaced(self) -> None:
        dsn = prep.with_database("mysql://u:p@127.0.0.1:3307/learningware", "lw2_schema_check")
        self.assertEqual(dsn, "mysql://u:p@127.0.0.1:3307/lw2_schema_check")

    def test_replacing_with_development_database_is_refused(self) -> None:
        with self.assertRaises(SystemExit):
            prep.with_database("mysql://u:p@127.0.0.1:3307/lw2_schema_check", "learningware")


class CareerDatabaseGuardTest(unittest.TestCase):
    def test_development_career_database_is_refused(self) -> None:
        """**開発の環境の career の DB は読まない。** 確認用の DB（career_ で始まる名前）だけ。"""
        for name in ("career", "learningware", ""):
            with self.assertRaises(SystemExit):
                prep.check_career_database(name)
        self.assertEqual(prep.check_career_database("career_lw2_check"), "career_lw2_check")


class PasswordTest(unittest.TestCase):
    def test_password_comes_from_environment(self) -> None:
        self.assertEqual(prep.e2e_password({prep.PASSWORD_ENV: "e2e-pass-123"}), "e2e-pass-123")

    def test_short_or_missing_password_is_refused(self) -> None:
        for env in ({}, {prep.PASSWORD_ENV: "short"}):
            with self.assertRaises(SystemExit):
                prep.e2e_password(env)


class PersonaTest(unittest.TestCase):
    def test_only_the_change_persona_must_change_password(self) -> None:
        """パスワードの変更を求めるのは F-17 の役だけ（他はログインしてすぐ画面を見る）。"""
        must = sorted(p for p, (flag, _) in prep.PERSONAS.items() if flag)
        self.assertEqual(must, ["learner_change"])

    def test_each_persona_is_picked_once(self) -> None:
        """同じ会員を 2 つの役に当てない（パスワードの変更で他の役のテストが崩れる）。"""

        class Cursor:
            def execute(self, sql, params):
                pass

            def fetchall(self):
                return [{"user_id": 1}, {"user_id": 2}, {"user_id": 3}]

        chosen = prep.pick(Cursor(), "T", set())
        self.assertEqual(len(set(chosen.values())), len(chosen))
        self.assertEqual(len(chosen), 3)


if __name__ == "__main__":
    unittest.main()
