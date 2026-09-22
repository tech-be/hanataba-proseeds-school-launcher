"""暫定対応ツール。

**移行ツールとは別にする。** 移行ツールは「入らない行」を一覧にするだけで、
値を作り替えない（[migrator/validation/constraints.py](../migrator/validation/constraints.py)）。
足りない値や重複をどう直すかは**移行の外の判断**で、それを扱うのがここ。

```
移行ツール  run --dry-run  →  out/not-migrated.csv（入らない行の一覧）
                                     ↓
暫定対応    fixups plan             何を直せばよいかを分類する
            fixups sql              旧 DB を直す SQL を出す（実行はしない）
            fixups template         運営が値を決める雛形（overrides.csv）を出す
            fixups check            書いてもらった値を検査する
                                     ↓
移行ツール  run                      直った分が入る
```

**直し方は2通りある。**

| 直し方 | 何を直すか | 当てる先 |
|---|---|---|
| **SQL** | 機械的に決まるもの（重複した `login_id` の一意化、会員が存在しない行の削除） | 移行元 DB |
| **補正データ** | 運営の判断が要るもの（メールアドレスの割り当て、ロール、どの会員に LINE を残すか） | `overrides.csv` |

SQL は**生成するだけで実行しない。** 移行元を書き換える操作なので、
人が中身を読んでから当てる。
"""
