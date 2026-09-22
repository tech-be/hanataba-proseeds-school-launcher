"""フェーズ = Step の集合と実行順。

**前のフェーズが終わるまで次に進まない。** 新環境は実 FK を持つため、順序を
守らないと FK 違反で止まる（docs/db/01-foundation/migration-spec.md 2章）。
"""
