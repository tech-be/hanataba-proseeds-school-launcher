"""lw2 (learningware-kiracari) → school-launcher データ移行ツール。

仕様は docs/migration-spec.md（共通）と docs/db/NN-*/migration-spec.md（区分ごと）。
コードの責任範囲は次のとおり。

    core/       変換部品。DB を知らない。Step はここを呼ぶだけで、変換ロジックを持たない
    db/         I/O のみ。SQL の実行とガード（禁止列・テナント絞り込み）
    steps/      1テーブル = 1 Step。extract → transform → load の3メソッド
    phases/     Step の集合と実行順。フェーズ境界で停止・検証する
    validation/ 事前検査（extract 前）と事後検証（load 後）。Step から独立
"""

__version__ = "0.1.0"
