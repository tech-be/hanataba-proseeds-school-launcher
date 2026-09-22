"""Step がやり取りするデータの型。

`Record` は「新環境の1テーブルに入れる1行」。**Step の出力はこれだけ**にして、
投入の仕方（INSERT か UPSERT か、バッチか）は db 層に任せる。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Record:
    """投入する1行。"""

    table: str
    values: dict[str, object]
    #: 冪等性を担保するキー。ここが一致する行は「同じ行」として扱う。
    #: 業務キー（`slug`、`(tenant_id, external_system, external_id)` など）を入れる。
    natural_key: tuple[str, ...] = ()
    #: **移行元でのキー**（旧 `user_id` など）。制約に当たって移さなかった行を
    #: 一覧にするときに使う。新環境の ULID では、旧のどの行かが分からない
    source_key: object = None

    def key_values(self) -> dict[str, object]:
        missing = [k for k in self.natural_key if k not in self.values]
        if missing:
            raise KeyError(f"{self.table}: natural_key の列が values に無い: {missing}")
        return {k: self.values[k] for k in self.natural_key}


@dataclass
class StepResult:
    """Step 1件の結果。レポートと検証に使う。"""

    step: str
    extracted: int = 0
    transformed: int = 0
    loaded: int = 0
    skipped: int = 0
    #: 制約に当たって**移さなかった**行数。`skipped`（既にある行）とは別物
    excluded: int = 0
    notes: list[str] = field(default_factory=list)

    def note(self, message: str) -> None:
        self.notes.append(message)

    def __str__(self) -> str:
        excluded = f" / 移行しない {self.excluded}" if self.excluded else ""
        return (
            f"{self.step}: 抽出 {self.extracted} / 変換 {self.transformed} / "
            f"投入 {self.loaded} / スキップ {self.skipped}" + excluded
        )
