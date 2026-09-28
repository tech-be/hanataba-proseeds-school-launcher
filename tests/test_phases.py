"""フェーズの実行単位のテスト。**途中のフェーズだけを流せる**ことを固定する。"""

from __future__ import annotations

import logging
import unittest
from datetime import datetime

from migrator.config import Config, TenantConfig
from migrator.context import build_context
from migrator.db.target import TargetDatabase
from migrator.errors import DependencyError, MigrationError
from migrator.phases.registry import bootstrap, build_sections, ordered_phases
from migrator.phases.selection import resolve
from tests.fakes import FakeSource

TENANT_ROW = {
    "tenant_id": 12,
    "tenant_code": "recademy",
    "tenant_name": "ReCADemy",
    "tenent_name_short": "RCD",
    "language_code": "ja",
    "del_chk": 0,
    "regist_date": datetime(2019, 8, 28, 14, 29, 17),
}

CONFIG = Config(
    tenant=TenantConfig(legacy_id=12, slug="recademy", name="ReCADemy"),
    ulid_namespace="lw2-test",
    mappings={
        "role": {"values": {7: "learner"}},
        "prefecture": {"values": {}},
        # 会員のフェーズ（foundation.2）を流すので、パスワード移行の設定が要る
        "password": {"bcrypt_cost": 4},
    },
    legacy_crypt_key="test-key",
)


def make_ctx(tables: dict | None = None):
    return build_context(
        CONFIG,
        FakeSource(tables if tables is not None else {"tenant": [TENANT_ROW]}),
        TargetDatabase(None, dry_run=True),
        logging.getLogger("test"),
    )


class PhaseSpecTest(unittest.TestCase):
    """指定は `区分.番号`。**区分が増えても番号がずれない**ことを固定する。"""

    def setUp(self) -> None:
        self.sections = build_sections()

    def test_qualified(self) -> None:
        self.assertEqual([p.key for p in resolve(self.sections, ["content.4"], [])], ["content.4"])

    def test_range_within_section(self) -> None:
        self.assertEqual(
            [p.key for p in resolve(self.sections, ["content.1-3"], [])],
            ["content.1", "content.2", "content.3"],
        )

    def test_section_whole(self) -> None:
        self.assertEqual(
            [p.key for p in resolve(self.sections, [], ["foundation"])],
            ["foundation.1", "foundation.2"],
        )

    def test_unqualified_allowed_while_unambiguous(self) -> None:
        """その番号を持つ区分が1つに決まるうちは、区分を省いても通る（後方互換）。

        **5区分になって、番号だけで決まるのは `0`（共通）だけになった。**
        1〜7 はどれも複数の区分が持つ。実質この後方互換は使えない。
        """
        self.assertEqual([p.key for p in resolve(self.sections, ["0"], [])], ["common.0"])

    def test_unqualified_becomes_ambiguous(self) -> None:
        """同じ番号を複数の区分が持つなら、区分を書かせる。

        **4 は content / enrollment / support が持つ**ので、番号だけでは決まらない。
        """
        with self.assertRaises(MigrationError) as caught:
            resolve(self.sections, ["4"], [])
        self.assertIn("区分.番号", str(caught.exception))

    def test_pending_section_is_rejected(self) -> None:
        """**まだ流せない区分は指定できない。**

        いまは5区分とも流せるので、合成した区分で挙動だけを固定する。
        """
        from migrator.phases.base import Phase, Section

        sections = self.sections + [
            Section("later", 9, "あとで", "doc", phases=[Phase(1, "x", "")], pending=True)
        ]
        with self.assertRaises(MigrationError):
            resolve(sections, ["later.1"], [])

    def test_default_is_everything_in_order(self) -> None:
        self.assertEqual(
            [p.key for p in resolve(self.sections, [], [])],
            [p.key for p in ordered_phases(self.sections)],
        )


class BootstrapTest(unittest.TestCase):
    def test_mid_phase_run_without_bootstrap_fails(self) -> None:
        """用意をせずに foundation.2 だけ流すと、依存で止まる（止まるのが正しい）。"""
        ctx = make_ctx()
        with self.assertRaises(DependencyError):
            resolve(build_sections(), ["foundation.2"], [])[0].run(ctx)

    def test_bootstrap_enables_mid_phase_dry_run(self) -> None:
        """ユーザだけの dry-run が通る。tenant_id は旧行から組み立てる。"""
        ctx = make_ctx({"tenant": [TENANT_ROW], "user": []})
        sections = build_sections()
        selected = resolve(sections, ["foundation.2"], [])
        bootstrap(ctx, sections, selected)
        self.assertTrue(ctx.tenant_id.resolved)
        self.assertIn("tenant", ctx.completed)
        selected[0].run(ctx)  # 依存で落ちない

    def test_bootstrap_tenant_id_matches_tenant_phase(self) -> None:
        """bootstrap が組み立てる tenant_id は、テナントのフェーズが採番する値と一致する。"""
        from migrator.steps.tenant import TenantStep

        tenant_ctx = make_ctx()
        TenantStep().transform(tenant_ctx, [TENANT_ROW])
        expected = tenant_ctx.tenant_id.value

        later_ctx = make_ctx()
        sections = build_sections()
        bootstrap(later_ctx, sections, resolve(sections, ["foundation.2"], []))
        self.assertEqual(later_ctx.tenant_id.value, expected)

    def test_bootstrap_is_noop_from_the_first_phase(self) -> None:
        ctx = make_ctx()
        sections = build_sections()
        bootstrap(ctx, sections, resolve(sections, ["common.0", "foundation.1"], []))
        self.assertFalse(ctx.tenant_id.resolved)  # foundation.1 が採番する

    def test_masters_only_does_not_need_tenant_id(self) -> None:
        """マスタは tenant_id を使わないので、引き当てずに流せる。"""
        ctx = make_ctx({})  # 旧 tenant を読めない状態でも通る
        sections = build_sections()
        selected = resolve(sections, ["foundation.1"], [])
        bootstrap(ctx, sections, selected)
        self.assertFalse(ctx.tenant_id.resolved)

    def test_tenant_phase_in_selection_does_not_resolve(self) -> None:
        """テナントのフェーズを含むなら、そこで採番するので引き当てない。"""
        ctx = make_ctx()
        sections = build_sections()
        bootstrap(ctx, sections, resolve(sections, ["foundation.1-2"], []))
        self.assertFalse(ctx.tenant_id.resolved)


if __name__ == "__main__":
    unittest.main()


class TenantVerificationTest(unittest.TestCase):
    """**テナントの総数では判断しない**ことを固定する。"""

    class _Target(TargetDatabase):
        def __init__(self, rows: list[dict]) -> None:
            super().__init__(None, dry_run=False)
            self._rows = rows

        def query(self, sql: str, params: tuple = ()) -> list[dict]:
            if "WHERE slug = %s" in sql:
                return [r for r in self._rows if r["slug"] == params[0]]
            if "WHERE name = %s AND slug <> %s" in sql:
                return [r for r in self._rows if r["name"] == params[0] and r["slug"] != params[1]]
            return list(self._rows)

    def _ctx(self, rows: list[dict]):
        return build_context(CONFIG, FakeSource({}), self._Target(rows), logging.getLogger("test"))

    def test_demo_tenants_do_not_fail_the_check(self) -> None:
        """デモ seed のテナントが同居していても、recademy が1件なら OK。"""
        from migrator.validation.postcheck import target_tenant_once

        rows = [
            {"id": "a", "slug": "demo", "name": "デモスクール"},
            {"id": "b", "slug": "tech-academy", "name": "テックアカデミー"},
            {"id": "c", "slug": "recademy", "name": "ReCADemy"},
        ]
        target_tenant_once(self._ctx(rows))  # 例外が出なければ OK

    def test_missing_target_tenant_fails(self) -> None:
        from migrator.errors import VerificationError
        from migrator.validation.postcheck import target_tenant_once

        with self.assertRaises(VerificationError):
            target_tenant_once(self._ctx([{"id": "a", "slug": "demo", "name": "デモスクール"}]))

    def test_same_name_with_other_slug_fails(self) -> None:
        """slug を変えれば同じテナントを二重に作れてしまうので、name の重複も見る。"""
        from migrator.errors import VerificationError
        from migrator.validation.postcheck import target_tenant_once

        rows = [
            {"id": "a", "slug": "recademy", "name": "ReCADemy"},
            {"id": "b", "slug": "recademy-old", "name": "ReCADemy"},
        ]
        with self.assertRaises(VerificationError):
            target_tenant_once(self._ctx(rows))


class PreflightRoleMapTest(unittest.TestCase):
    """**事前検査は `role_master` の全行を見る。**

    会員が使っている `role_id` だけを見ていると、マスタ投入の段で初めて止まる
    （実際に dry-run でそうなった）。
    """

    def _ctx(self, users: list[dict], master: list[dict]):
        return build_context(
            CONFIG,
            FakeSource({"user": users, "role_master": master}),
            TargetDatabase(None, dry_run=True),
            logging.getLogger("test"),
        )

    def test_unused_role_in_master_is_detected(self) -> None:
        from migrator.validation.preflight import _role_map

        ctx = self._ctx([{"user_id": 1, "role_id": 7}], [{"role_id": 7}, {"role_id": 3}])
        result = _role_map(ctx)
        self.assertFalse(result.ok)
        self.assertIn("role_master", result.detail)

    def test_full_coverage_passes(self) -> None:
        from migrator.validation.preflight import _role_map

        ctx = self._ctx([{"user_id": 1, "role_id": 7}], [{"role_id": 7}])
        self.assertTrue(_role_map(ctx).ok)

    def test_null_role_id_is_reported(self) -> None:
        """**ロールが未設定の会員は既定値に倒さない。**

        `users.role` は NOT NULL + FK なので入れる値が無く、その会員は移らない。
        対応表そのものは欠けていないので、事前検査は止めずに人数を出す。
        """
        from migrator.validation.preflight import _role_map

        ctx = self._ctx([{"user_id": 9, "role_id": None}], [{"role_id": 7}])
        result = _role_map(ctx)
        self.assertTrue(result.ok)
        self.assertIn("移行しない", result.detail)


class _SchemalessTarget(TargetDatabase):
    """接続はあるが、追加スキーマが1つも当たっていない移行先。"""

    def __init__(self) -> None:
        super().__init__(None, dry_run=True)

    @property
    def connectionless(self) -> bool:
        return False

    def query(self, sql: str, params: tuple = ()) -> list[dict]:
        return []


class SchemaCheckTest(unittest.TestCase):
    """**途中の区分から流しても、スキーマ確認は飛ばさない。**

    `bootstrap` が `common.0` を完了扱いにするので、以前は migration が当たって
    いない区分（課金など）を `--section` で流すと、確認で止まらずに Step の SQL が
    `Unknown column` で落ちていた。
    """

    def _ctx(self, selected):
        from migrator.phases.registry import check_schema

        ctx = build_context(CONFIG, FakeSource({}), _SchemalessTarget(), logging.getLogger("test"))
        ctx.selected = {p.key for p in selected}
        return ctx, check_schema

    def test_mid_section_run_checks_schema(self) -> None:
        from migrator.errors import PreflightError

        selected = resolve(build_sections(), [], ["billing"])
        ctx, check_schema = self._ctx(selected)
        with self.assertRaises(PreflightError) as caught:
            check_schema(ctx, selected)
        # 見るのは選んだ区分の分だけ
        self.assertIn("ticket_types.legacy_id", str(caught.exception))
        self.assertNotIn("enrollments", str(caught.exception))

    def test_not_repeated_when_common_is_selected(self) -> None:
        selected = resolve(build_sections(), ["common.0", "foundation.1"], [])
        ctx, check_schema = self._ctx(selected)
        check_schema(ctx, selected)  # common.0 が流すので、ここでは何もしない
        self.assertEqual(ctx.results, [])
