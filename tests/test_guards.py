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

    def test_sns_secret_is_readable(self) -> None:
        """**SNS の認証情報は読む。** 新環境でもそのまま使えるため移行対象。

        「読み出さない」のは lw2 自身の DB 接続情報と、失効済みの認証コードだけ。
        """
        guards.check_forbidden_columns(
            "SELECT facebook_consumer_sercret_key FROM sns_setting WHERE tenant_id = 12"
        )

    def test_tenant_config_secrets_are_blocked(self) -> None:
        """**平文のパスワードと旧の DB 名は読まない。** 列の一覧から外すだけでなく、仕組みで止める。"""
        for column in ("special_pass_word", "kanri_db_name"):
            with self.assertRaises(ForbiddenColumnError):
                guards.check_forbidden_columns(
                    f"SELECT tenant_id, {column} FROM application_config WHERE tenant_id = 12")
        # LINE の秘密の値は移す（tenant_secrets）
        guards.check_forbidden_columns(
            "SELECT line_channel_sercret FROM application_config WHERE tenant_id = 12")

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

    def test_badge_is_out_of_scope(self) -> None:
        """バッジは移行対象外（2026-09-28 決定）。定義も読まない。"""
        with self.assertRaises(ExcludedTableError):
            guards.check_excluded_tables("badge_item")

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
