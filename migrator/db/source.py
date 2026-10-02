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


#: **テナント 0 を共有として持つ表。** 問題バンクは複数テナントで使い回される。
#: `lesson` は参照されている分だけなので別扱い（`shared_lessons`）。
SHARED_BANK_TABLES = frozenset({"question", "question_cate"})


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
        #: 共有講座の旧 ID（遅延取得）。`shared_lessons` が埋める
        self._shared_lessons: frozenset[int] | None = None
        #: 共有アンケートの旧 ID（遅延取得）。`shared_enquetes` が埋める
        self._shared_enquetes: frozenset[int] | None = None

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

    #: 共有講座を参照している経路。**どれか1つでも指していれば移す。**
    _SHARED_LESSON_SQL = """
        SELECT DISTINCT l.lesson_id AS lid FROM `lesson` AS l WHERE l.tenant_id = 0 AND l.lesson_id IN (
            SELECT a.lesson_id FROM payment_item_lesson_authority a
              JOIN payment_item p ON p.item_id = a.item_id WHERE p.tenant_id = %s
            UNION SELECT ul.lesson_id FROM user_learning_lesson ul
              JOIN user u ON u.user_id = ul.user_id WHERE u.tenant_id = %s
            UNION SELECT al.lesson_id FROM attribute_lesson al
              JOIN attribute at ON at.attribute_id = al.attribute_id WHERE at.tenant_id = %s
            UNION SELECT pil.lesson_id FROM payment_item_lesson pil
              JOIN payment_item p2 ON p2.item_id = pil.item_id WHERE p2.tenant_id = %s
            UNION SELECT ls.lesson_id FROM lesson_system ls WHERE ls.tenant_id = %s
            UNION SELECT ai.entity_id FROM assign_item ai
              WHERE ai.tenant_id = %s AND ai.item_type = 'lesson'
            UNION SELECT ap.item_id FROM assign_payment_item ap
              JOIN assign asg ON asg.assign_id = ap.assign_id WHERE asg.tenant_id = %s AND ap.item_type = 1
        )
    """

    @property
    def shared_lessons(self) -> frozenset[int]:
        """このテナントが参照している**共有講座**（`lesson.tenant_id = 0`）の旧 ID。

        **lw2 は講座をテナント間で共有できる**（実測161件）。このテナントの会員が
        受講権限・学習実績・属性の必須講座・商品で参照している分と、**テナントに公開した分**
        （`lesson_system`）、**自動割当のきっかけ・付与で指している分**（`assign_payment_item` / `assign_item`。
        2026-10-02 追加。拾わないと付与が存在しない講座を指したまま入る）を移す。
        公開されているだけで誰も参照していない講座も、旧では受講者に見えていた。
        **バッジ（`badge_item`）は経路に入れない。** 移行対象外なので、バッジからしか
        参照されていない共有講座を移す理由が無い（ステージング実測では該当 0 件）。

        **拾わないと連鎖して落ちる。** 実測で受講権限807行・バッジ定義27件が
        外部キー違反になっていた。当初これを「他テナントのデータなので弾いて正しい」と
        判断していたが、**共有講座であって他テナントのものではなかった**。

        **1回だけ引いて覚える。** `fetch_joined` が毎回呼ぶため。
        """
        if self._shared_lessons is None:
            rows = self.fetch("lesson", self._SHARED_LESSON_SQL, (self._tenant_id,) * 7)
            self._shared_lessons = frozenset(int(r["lid"]) for r in rows)
        return self._shared_lessons

    @property
    def shared_enquetes(self) -> frozenset[int]:
        """移すユニットが参照している**共有アンケート**（`enquete.tenant_id = 0`）の旧 ID。

        **共有講座のアンケートユニットは、共有のアンケート定義を指している。** 自テナントで
        絞ると定義が見つからず、ユニットが「定義が物理削除された孤児」と誤って扱われ、
        **定義も回答も黙って落ちていた**（ステージングで定義10件・回答6件。旧 DB との
        突き合わせで判明）。移すユニット（自テナントの講座と `shared_lessons`）が
        参照しているものだけを含める。
        """
        if self._shared_enquetes is None:
            lessons = tuple(sorted(self.shared_lessons))
            marks = ", ".join(["%s"] * len(lessons)) or "NULL"
            rows = self.fetch("enquete", f"""
                SELECT DISTINCT e.enquete_id AS eid FROM `enquete` AS e
                INNER JOIN `unit` AS u ON u.enquete_id = e.enquete_id
                INNER JOIN `lesson` AS l ON l.lesson_id = u.lesson_id
                WHERE e.tenant_id = 0 AND (l.tenant_id = %s OR l.lesson_id IN ({marks}))""",
                (self._tenant_id, *lessons))
            self._shared_enquetes = frozenset(int(r["eid"]) for r in rows)
        return self._shared_enquetes

    def fetch_for_tenant(self, table: str, columns: tuple[str, ...], where: str = "") -> list[dict]:
        """`tenant_id` を持つテーブルを、テナントで絞って読む。

        列を明示させる（`SELECT *` を使わない）。禁止列を書けばガードが落とす。

        **共有データ（`tenant_id = 0`）も含める表がある。**

        - `lesson` … このテナントが参照している共有講座だけ（→ `shared_lessons`）
        - `question` / `question_cate` … **問題バンクはテナントをまたいで共有される。**
          共有講座のテストがこれを引くので、`= tenant_id` だけで絞ると
          **設問が親無しと判定されて落ちる**（実測 1,676 件）
        - `enquete` … 移すユニットが参照している共有アンケートだけ（→ `shared_enquetes`）
        """
        cols = ", ".join(f"`{c}`" for c in columns)
        params: tuple = (self._tenant_id,)
        scope = "tenant_id = %s"
        if table == "lesson" and self.shared_lessons:
            ids = tuple(sorted(self.shared_lessons))
            marks = ", ".join(["%s"] * len(ids))
            scope = f"(tenant_id = %s OR lesson_id IN ({marks}))"
            params = (self._tenant_id, *ids)
        elif table == "enquete" and self.shared_enquetes:
            ids = tuple(sorted(self.shared_enquetes))
            marks = ", ".join(["%s"] * len(ids))
            scope = f"(tenant_id = %s OR enquete_id IN ({marks}))"
            params = (self._tenant_id, *ids)
        elif table in SHARED_BANK_TABLES:
            scope = "tenant_id IN (%s, 0)"
        sql = f"SELECT {cols} FROM `{table}` WHERE {scope}"
        if where:
            sql += f" AND {where}"
        return self.fetch(table, sql, params)

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

        **親が `lesson` のときは共有講座（`tenant_id = 0`）も含める。** lw2 は講座を
        テナント間で共有でき（実測161件）、このテナントの会員が受講権限・学習実績・
        バッジで参照している。**絞り込みを `= tenant_id` だけにすると、共有講座に
        ぶら下がる行が丸ごと落ちる**（実測で受講権限807行・バッジ27件が連鎖して落ちた）。
        どの共有講座を含めるかは `shared_lessons` で渡す。
        """
        cols = ", ".join(f"c.`{c}`" for c in columns)
        joins = "".join(f"INNER JOIN `{t}` AS {alias} ON {cond} " for t, alias, cond in (via or ()))
        params: tuple = (self._tenant_id,)
        scope = "p.tenant_id = %s"
        if parent == "lesson" and self.shared_lessons:
            ids = tuple(sorted(self.shared_lessons))
            marks = ", ".join(["%s"] * len(ids))
            scope = f"(p.tenant_id = %s OR p.lesson_id IN ({marks}))"
            params = (self._tenant_id, *ids)
        elif parent == "enquete" and self.shared_enquetes:
            # 共有アンケートのページ・設問・回答も含める（→ `shared_enquetes`）
            ids = tuple(sorted(self.shared_enquetes))
            marks = ", ".join(["%s"] * len(ids))
            scope = f"(p.tenant_id = %s OR p.enquete_id IN ({marks}))"
            params = (self._tenant_id, *ids)
        sql = (
            f"SELECT {cols} FROM `{table}` AS c "
            f"{joins}"
            f"INNER JOIN `{parent}` AS p ON {on} "
            f"WHERE {scope}"
        )
        if where:
            sql += f" AND {where}"
        return self.fetch(table, sql, params)

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
