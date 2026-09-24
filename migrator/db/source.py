"""旧環境 (lw2) からの読み出し。

**責務は I/O とガードだけ。** 変換は core/ が、業務判断は steps/ が持つ。
"""

from __future__ import annotations

import logging
from collections import Counter
from typing import Any, Iterable, Protocol

from ..core.datetimes import is_zero_date
from . import guards

logger = logging.getLogger(__name__)


class Cursor(Protocol):
    def execute(self, sql: str, args: Any = None) -> Any: ...
    def fetchall(self) -> Iterable[dict]: ...


class Connection(Protocol):
    def cursor(self) -> Cursor: ...
    def close(self) -> None: ...


class SourceDatabase:
    """lw2 の読み出し口。

    すべてのクエリが **(1) 禁止列を参照していない (2) テナントで絞られている**
    ことを、実行前に確認する。
    """

    def __init__(
        self, connection: Connection, tenant_id: int, overrides: object | None = None
    ) -> None:
        self._connection = connection
        self._tenant_id = tenant_id
        #: 暫定対応で決めた値。**移行元の行を読んだ直後に当てる**ので、
        #: 以降の Step はどれも「直ったあとの値」を見る
        self.overrides = overrides
        #: ゼロ日付を NULL に倒した件数。`(テーブル, 列)` ごと
        self.zero_dates: Counter[tuple[str, str]] = Counter()

    @property
    def tenant_id(self) -> int:
        """移行対象の旧テナント ID（recademy は 12）。"""
        return self._tenant_id

    def fetch(self, table: str, sql: str, params: tuple = ()) -> list[dict]:
        """1テーブル分を読む。`table` はガードと件数記録のための宣言。"""
        guards.check_excluded_tables(table)
        guards.check_forbidden_columns(sql)
        guards.check_tenant_scope(sql, table)
        cursor = self._connection.cursor()
        cursor.execute(sql, params)
        rows = [self._clean(table, dict(row)) for row in cursor.fetchall()]
        if self.overrides is not None:
            applied = self.overrides.apply(table, rows)
            if applied:
                logger.info("%s に補正データを %d 値あてた", table, applied)
        return rows

    def _clean(self, table: str, row: dict) -> dict:
        """ゼロ日付を NULL に倒す。**黙って捨てず、件数を数えて警告に出す。**"""
        for column, value in row.items():
            if is_zero_date(value):
                row[column] = None
                key = (table, column)
                if not self.zero_dates[key]:
                    logger.warning(
                        "%s.%s にゼロ日付 (0000-00-00) がある。NULL として移行する", table, column
                    )
                self.zero_dates[key] += 1
        return row

    def fetch_for_tenant(self, table: str, columns: tuple[str, ...], where: str = "") -> list[dict]:
        """`tenant_id` を持つテーブルを、テナントで絞って読む。

        列を明示させる（`SELECT *` を使わない）。禁止列を書けばガードが落とす。
        """
        cols = ", ".join(f"`{c}`" for c in columns)
        sql = f"SELECT {cols} FROM `{table}` WHERE tenant_id = %s"
        if where:
            sql += f" AND {where}"
        return self.fetch(table, sql, (self._tenant_id,))

    def fetch_global(self, table: str, columns: tuple[str, ...], where: str = "") -> list[dict]:
        """`tenant_id` を持たない共通マスタを読む（`role_master` など）。"""
        if table not in guards.TENANT_GLOBAL_TABLES:
            raise ValueError(f"{table} は共通マスタとして登録されていない")
        cols = ", ".join(f"`{c}`" for c in columns)
        sql = f"SELECT {cols} FROM `{table}`"
        if where:
            sql += f" WHERE {where}"
        return self.fetch(table, sql)

    def fetch_joined(
        self,
        table: str,
        columns: tuple[str, ...],
        parent: str,
        on: str,
        where: str = "",
        via: list[tuple[str, str, str]] | None = None,
    ) -> list[dict]:
        """**`tenant_id` を持たない子テーブル**を、親と join してテナントで絞る。

        `user_group` / `user_attribute` / `attribute_lesson` / `instructor_set_*` が該当する。
        **join を落とすと他テナントの行を拾う**（最大 2,083 倍。ETL設計 付録A）。

        `on` は `c` (子) と `p` (親) の別名で書く。例: ``"c.group_id = p.group_id"``

        **親が `tenant_id` を持たないときは `via` で中間テーブルを挟む。**
        `lecture` は `unit` にぶら下がり、`unit` は `lesson` にぶら下がる、のように
        2段たどらないとテナントに届かない経路がある。`via` は `(テーブル, 別名, 結合条件)`
        の並びで、最後の要素が `tenant_id` を持つこと。

            fetch_joined(
                "lecture", COLUMNS,
                parent="lesson", on="u.lesson_id = p.lesson_id",
                via=[("unit", "u", "c.unit_id = u.unit_id")],
            )
        """
        cols = ", ".join(f"c.`{c}`" for c in columns)
        joins = "".join(f"INNER JOIN `{t}` AS {alias} ON {cond} " for t, alias, cond in (via or ()))
        sql = (
            f"SELECT {cols} FROM `{table}` AS c "
            f"{joins}"
            f"INNER JOIN `{parent}` AS p ON {on} "
            f"WHERE p.tenant_id = %s"
        )
        if where:
            sql += f" AND {where}"
        return self.fetch(table, sql, (self._tenant_id,))

    def missing_tables(self, tables: Iterable[str]) -> list[str]:
        """指定したテーブルのうち、**この移行元に存在しないもの**を返す。

        環境によってテーブルの有無が違う（lw2 は個別 SQL でテーブルを足すことがあり、
        ステージングと本番で構成が揃っていない）。読む前に確かめて、原因の分かる形で止める。
        """
        names = sorted({t for t in tables if t})
        if not names:
            return []
        placeholders = ", ".join(["%s"] * len(names))
        cursor = self._connection.cursor()
        cursor.execute(
            "SELECT table_name AS name FROM information_schema.tables "
            f"WHERE table_schema = DATABASE() AND table_name IN ({placeholders})",
            tuple(names),
        )
        found = {str(dict(row)["name"]) for row in cursor.fetchall()}
        return [name for name in names if name not in found]

    def count(self, table: str, where: str = "") -> int:
        """件数を数える（事前検査・事後照合用）。"""
        sql = f"SELECT COUNT(*) AS n FROM `{table}` WHERE tenant_id = %s"
        if where:
            sql += f" AND {where}"
        rows = self.fetch(table, sql, (self._tenant_id,))
        return int(rows[0]["n"])

    def close(self) -> None:
        self._connection.close()
