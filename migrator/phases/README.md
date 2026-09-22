# フェーズの足し方

1. `migrator/steps/` に Step を書く（1テーブル = 1 Step。`extract` / `transform` / `load`）
2. その区分の `build()` に足す
3. `registry.build_phases()` の該当フェーズに入れる。**新しいフェーズを作るのは順序制約が変わるときだけ**

依存は `Step.depends_on` に名前で書く。実行時に `RunContext.completed` と突き合わせ、
足りなければ `DependencyError` で止まる。
