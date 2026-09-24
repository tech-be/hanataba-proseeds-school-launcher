"""フェーズと区分の定義。

**識別子は2階層。** 区分（basename）とフェーズ番号で `foundation.2` のように指す。
区分をまたぐ順序（基盤 → オンデマンド → …）と、区分の中の順序（テナント → 会員 → …）は
別の軸なので、1つの通し番号に押し込むと、区分が増えたときに番号がずれる。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..context import RunContext
from ..core.records import StepResult
from ..errors import MigrationError
from ..steps.base import Step


@dataclass
class Phase:
    """区分の中の順序の単位。"""

    number: int
    name: str
    description: str
    steps: list[Step] = field(default_factory=list)
    #: フェーズ終了時に通す検証（`validation.postcheck` の関数）
    checks: tuple = ()
    #: 所属する区分のキー。`Section` が登録時に入れる
    section: str = ""

    @property
    def key(self) -> str:
        """`foundation.2` のような識別子。**CLI で指定するのはこれ。**"""
        return f"{self.section}.{self.number}"

    def run(self, ctx: RunContext) -> list[StepResult]:
        ctx.logger.info("=== %s %s ===", self.key, self.name)
        results = []
        for step in self.steps:
            try:
                results.append(step.run(ctx))
            except MigrationError:
                ctx.target.rollback()
                ctx.logger.error("%s の %s で停止した", self.key, step.name)
                raise
        for check in self.checks:
            check(ctx)
        ctx.target.commit()
        ctx.completed.add(self.key)
        return results


@dataclass
class Section:
    """区分（docs/db/NN-<区分> と1対1）。

    区分をまたぐ順序は `order` で決まる。**基盤が終わるまで他区分は1行も入らない**
    （docs/migration-spec.md 1章）。
    """

    key: str
    order: int
    title: str
    doc: str
    phases: list[Phase] = field(default_factory=list)
    #: まだ流せない区分。`plan` には出すが、流そうとすると止める
    pending: bool = False
    #: なぜ流せないか。`plan` と選択時のエラーにそのまま出す
    pending_reason: str = "移行仕様が未作成"
    #: 何から着手すればよいか。選択時のエラーにだけ出す
    pending_next: str = "突き合わせに `修正方法` の列を足し、追加一覧を作るところから"

    def __post_init__(self) -> None:
        for phase in self.phases:
            phase.section = self.key

    def phase(self, number: int) -> Phase | None:
        return next((p for p in self.phases if p.number == number), None)
