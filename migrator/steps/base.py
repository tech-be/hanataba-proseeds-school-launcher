"""Step の基底。

**1 Step = 1 つの責任。** 抽出（どの行を読むか）・変換（どう写すか）・投入（どこに入れるか）を
1テーブル分だけ持つ。他のテーブルのことは知らない。
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from ..context import RunContext
from ..core.records import Record, StepResult
from ..validation import constraints
from ..errors import DependencyError

logger = logging.getLogger(__name__)


class Step(ABC):
    """移行の最小単位。"""

    #: 一意な名前。ログ・レポート・依存解決に使う
    name: str = ""
    #: 投入先の新環境テーブル
    target_table: str = ""
    #: 抽出元の旧環境テーブル（新規作成のみの Step は空）
    source_table: str = ""
    #: 先に完了していなければならない Step の名前
    depends_on: tuple[str, ...] = ()
    #: 何をする Step かの1行説明（`plan` コマンドに出る）
    description: str = ""
    #: **実行した時刻で値が決まる列。** 照合（`verify`）では値ではなく有無だけを見る
    volatile_columns: tuple[str, ...] = ()

    def __init__(self) -> None:
        if not self.name:
            raise ValueError(f"{type(self).__name__}: name が未設定")

    # --- 3つの段 ----------------------------------------------------------
    @abstractmethod
    def extract(self, ctx: RunContext) -> list[dict]:
        """旧環境から読む。**読むだけ**で、判断も変換もしない。"""

    @abstractmethod
    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        """新環境の行に写す。**DB を触らない**ので単体テストできる。"""

    def load(self, ctx: RunContext, records: list[Record]) -> int:
        """投入する。既定では自然キーで重複を避けてまとめて INSERT する。"""
        return ctx.target.insert_many(records)

    # --- 抽出で落とした行 ----------------------------------------------------
    def drop(self, table: str, key: object, reason: str, detail: str = "") -> None:
        """**抽出の段階で落とす行を、一覧（not-migrated.csv）に出す。**

        旧データの不整合（親が物理削除されている など）で変換まで持っていけない行は、
        黙って `continue` せずここに渡す。制約に当たった行と同じく件数と一覧に出る。
        黙って落とすと、旧 DB との突き合わせで「一覧に無い欠け」として NG になる。
        """
        if not hasattr(self, "_dropped"):
            self._dropped = []
        self._dropped.append(constraints.Violation(table, reason, detail, str(key)))

    def _take_dropped(self) -> list:
        dropped, self._dropped = getattr(self, "_dropped", []), []
        return dropped

    # --- 実行 --------------------------------------------------------------
    def check_dependencies(self, ctx: RunContext) -> None:
        missing = [d for d in self.depends_on if d not in ctx.completed]
        if missing:
            raise DependencyError(f"{self.name}: 先に {missing} が要る")

    def run(self, ctx: RunContext) -> StepResult:
        self.check_dependencies(ctx)
        result = StepResult(step=self.name)
        if self.source_table and self.source_table in ctx.absent_source_tables():
            #: 設定で「この環境には無い」と宣言されたテーブル。**移行対象から外れたわけではない**
            result.note(f"{self.source_table} がこの移行元に無いため読み飛ばした（設定で宣言済み）")
            logger.warning("%s: %s", self.name, result.notes[-1])
            return ctx.record(result)
        rows = self.extract(ctx)
        dropped = self._take_dropped()
        result.extracted = len(rows) + len(dropped)
        if dropped:
            result.excluded += len(dropped)
            result.note(ctx.exclusions().add(self.name, dropped))
        records = self.transform(ctx, rows)
        result.transformed = len(records)
        # **投入する前に**移行先の制約と突き合わせる。dry-run では INSERT が
        # 実行されないので、ここで見ないと違反は本番まで見つからない。
        # 当たった行は**移さず**一覧に出す（値を作り替えて通すことはしない）
        if records:
            records, violations = constraints.filter_valid(
                records, ctx.schema_reader().get(records[0].table), ctx.target
            )
            if violations:
                result.excluded += len(violations)
                result.note(ctx.exclusions().add(self.name, violations))
        result.loaded = self.load(ctx, records)
        result.skipped = max(result.transformed - result.loaded, 0)
        return ctx.record(result)


class SchemaStep(Step):
    """新環境のスキーマ追加を**確認する** Step（自分では DDL を流さない）。

    追加（A1〜A21）は school-launcher 側の migration で入れる。ここでは
    「入っていること」を確かめ、入っていなければ止める。
    """

    #: 存在していなければならない (テーブル, 列) の組。列が空ならテーブルの存在だけ見る
    required: tuple[tuple[str, str | None], ...] = ()

    def extract(self, ctx: RunContext) -> list[dict]:
        return []

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        return []
