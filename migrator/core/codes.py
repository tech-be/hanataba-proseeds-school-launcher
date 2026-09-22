"""コード値の対応（docs/migration-spec.md 3.6）。

**対応表に無い値が来たら停止する。** 既定値に倒すと、権限や状態が静かに壊れる。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..errors import MappingError

#: 新環境のロール。**`platform_admin` は移行で絶対に出力しない**（他テナントが見える）。
FORBIDDEN_ROLES = frozenset({"platform_admin"})


@dataclass(frozen=True)
class CodeMap:
    """旧コード値 → 新コード値の対応表。

    `name` は失敗時のメッセージに出る識別子。`source` は運営から受け取った
    対応表の出どころ（`migration-spec.md` 1-1 の確認事項）。
    """

    name: str
    mapping: dict[object, str]
    source: str = ""
    forbidden_values: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        bad = set(self.mapping.values()) & set(self.forbidden_values)
        if bad:
            raise MappingError(f"{self.name}: 出力が禁じられている値を含む: {sorted(bad)}")

    def to_new(self, value: object) -> str:
        if value not in self.mapping:
            raise MappingError(
                f"{self.name}: 対応表に無い値 {value!r}。"
                f"既定値に倒さず停止する（対応表の出どころ: {self.source or '未設定'}）"
            )
        return self.mapping[value]

    def optional(self, value: object) -> str | None:
        return None if value is None else self.to_new(value)


def role_map(mapping: dict[object, str], source: str) -> CodeMap:
    """ロールの対応表を作る。`platform_admin` を含めると作成時点で落ちる。"""
    return CodeMap(name="role", mapping=mapping, source=source, forbidden_values=FORBIDDEN_ROLES)


#: 旧 `user_login_log.user_login_result` → 新 `auth_outcomes.code`。
#: ログは移行対象外だが、`login_history` を後から使うときのために対応だけ残す。
AUTH_OUTCOME_CODES = (
    "success",
    "invalid_password",
    "user_not_found",
    "account_inactive",
    "account_locked",
    "mfa_failed",
    "token_invalid",
    "other_failure",
)


def prefecture_name(pref_id: int | None, table: dict[int, str]) -> str | None:
    """`pref_id`（tinyint のコード値）を都道府県名に展開する。

    新環境は都道府県を文字列で持つ（`desired_prefecture varchar(10)` など）ため、
    コードのまま入れない。
    """
    if pref_id is None or pref_id == 0:
        return None  # `pref_master` は 1 始まり。0 は「未選択」で、NULL と同じ意味
    if pref_id not in table:
        raise MappingError(f"prefecture: 対応表に無い pref_id {pref_id!r}")
    return table[pref_id]
