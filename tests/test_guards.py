"""ガードのテスト。**仕様で禁じたことが、実行前に止まる**ことを固定する。"""

from __future__ import annotations

import unittest

from migrator.db import guards
from migrator.errors import ExcludedTableError, ForbiddenColumnError, TenantScopeError


class ForbiddenColumnTest(unittest.TestCase):
    def test_db_credentials_are_blocked(self) -> None:
        """lw2 の DB 接続情報は「移さない」ではなく「読み出さない」。"""
        with self.assertRaises(ForbiddenColumnError):
            guards.check_forbidden_columns("SELECT db_server, password FROM site WHERE tenant_id = 12")

    def test_sns_secret_is_blocked(self) -> None:
        with self.assertRaises(ForbiddenColumnError):
            guards.check_forbidden_columns(
                "SELECT facebook_sercret_key FROM sns_setting WHERE tenant_id = 12"
            )

    def test_input_password_is_blocked(self) -> None:
        with self.assertRaises(ForbiddenColumnError):
            guards.check_forbidden_columns("SELECT input_password FROM user_login_log")

    def test_safe_query_passes(self) -> None:
        guards.check_forbidden_columns("SELECT service_name FROM site WHERE tenant_id = 12")


class ExcludedTableTest(unittest.TestCase):
    def test_pure_log_is_excluded(self) -> None:
        """純ログは受け皿があっても移さない。"""
        for table in ("user_login_log", "user_login_log_monthly", "twostepverification_log"):
            with self.assertRaises(ExcludedTableError):
                guards.check_excluded_tables(table)

    def test_named_log_but_not_a_log(self) -> None:
        """`user_login_chk_log` は名前が _log でも「有効期間の変更履歴」なので移行する。"""
        guards.check_excluded_tables("user_login_chk_log")


class TenantScopeTest(unittest.TestCase):
    def test_missing_scope_is_blocked(self) -> None:
        """絞り込みを落とすと他テナントの行を拾う。"""
        with self.assertRaises(TenantScopeError):
            guards.check_tenant_scope("SELECT * FROM user", "user")

    def test_global_master_is_allowed(self) -> None:
        guards.check_tenant_scope("SELECT * FROM role_master", "role_master")


if __name__ == "__main__":
    unittest.main()
