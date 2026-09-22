"""テスト用の差し替え。**DB を立てずに Step を通す**ための最小実装。"""

from __future__ import annotations

from migrator.db.source import SourceDatabase


class FakeSource(SourceDatabase):
    """旧環境の代わり。テーブル名 → 行のリストを持つ。

    ガード（禁止列・テナント絞り込み）は本物と同じものを通す。
    """

    def __init__(self, tables: dict[str, list[dict]], tenant_id: int = 12) -> None:
        self._tables = tables
        super().__init__(connection=None, tenant_id=tenant_id)  # type: ignore[arg-type]

    def fetch(self, table: str, sql: str, params: tuple = ()) -> list[dict]:
        from migrator.db import guards

        guards.check_excluded_tables(table)
        guards.check_forbidden_columns(sql)
        guards.check_tenant_scope(sql, table)
        return [dict(row) for row in self._tables.get(table, [])]

    def count(self, table: str, where: str = "") -> int:
        return len(self._tables.get(table, []))
