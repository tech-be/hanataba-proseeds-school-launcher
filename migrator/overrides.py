"""補正データ（暫定対応で決めた値）の読み込み。

**移行ツールは値を作らない。** 欠けている値や重複した値をどうするかは運営の判断で、
その結果だけをこのファイルから受け取る。ツールがやるのは「書いてあるとおりに
移行元の行を上書きする」ことだけ。

```csv
table,key,column,value,memo
user,101,mail_add,taro@example.com,欠損のため運営が割り当て
user,911,role_id,7,テスト用アカウント。受講者にする
user,3394,line_id,NULL,同じ LINE を4名が共有。3394 は外す
```

- `key` は移行元テーブルの主キー（`user` なら `user_id`）
- `value` が空の行は**未記入とみなして適用しない**（雛形のまま流しても事故らない）
- `NULL` と書いた場合だけ、値を消す
- `memo` は使わない（なぜそう決めたかを残すための欄）

**このファイルは個人情報を含む。** リポジトリに入れない（`.gitignore` 済み）。
"""

from __future__ import annotations

import csv
import logging
from dataclasses import dataclass, field
from pathlib import Path

from .errors import ConfigError

logger = logging.getLogger(__name__)

#: 既定の置き場所。設定 `overrides` で変えられる
DEFAULT_PATH = Path("overrides.csv")

#: 移行元テーブルの主キー。**ここに無いテーブルは上書きできない**
#: （どの行を指しているか決められないため）
KEY_COLUMNS: dict[str, str] = {
    "user": "user_id",
    "group": "group_id",
    "attribute": "attribute_id",
    "tenant": "tenant_id",
}

#: 値を消すときに書く語
NULL_WORD = "NULL"


@dataclass
class Overrides:
    """`(テーブル, 主キー)` ごとの上書き値。"""

    values: dict[tuple[str, str], dict[str, object]] = field(default_factory=dict)
    applied: int = 0

    @classmethod
    def load(cls, path: Path | str | None) -> "Overrides":
        """補正データを読む。**ファイルが無ければ空**（暫定対応なしで流せる）。"""
        if path is None:
            return cls()
        path = Path(path)
        if not path.exists():
            return cls()
        values: dict[tuple[str, str], dict[str, object]] = {}
        with path.open(encoding="utf-8-sig", newline="") as handle:
            for line, row in enumerate(csv.DictReader(handle), start=2):
                table = (row.get("table") or "").strip()
                key = (row.get("key") or "").strip()
                column = (row.get("column") or "").strip()
                raw = (row.get("value") or "").strip()
                if not table and not key and not column:
                    continue  # 空行
                if table not in KEY_COLUMNS:
                    raise ConfigError(
                        f"{path}:{line} 上書きできないテーブル `{table}`。"
                        f"主キーが分かるのは {sorted(KEY_COLUMNS)} だけ"
                    )
                if not key or not column:
                    raise ConfigError(f"{path}:{line} key と column は必須")
                if not raw:
                    continue  # 未記入。雛形のままの行
                values.setdefault((table, key), {})[column] = None if raw == NULL_WORD else raw
        total = sum(len(v) for v in values.values())
        logger.info("補正データ %s を読んだ: %d 行 / %d 値", path, len(values), total)
        return cls(values=values)

    def for_table(self, table: str) -> bool:
        return any(t == table for t, _ in self.values)

    def apply(self, table: str, rows: list[dict]) -> int:
        """抽出した行に上書きを当てる。**当てた値の数を返す。**"""
        key_column = KEY_COLUMNS.get(table)
        if not key_column or not self.values:
            return 0
        applied = 0
        for row in rows:
            if key_column not in row:
                continue  # その列を抽出していない Step（キーが分からないので触らない）
            patch = self.values.get((table, str(row[key_column])))
            if not patch:
                continue
            for column, value in patch.items():
                if column not in row:
                    continue  # この Step が読んでいない列
                row[column] = value
                applied += 1
        self.applied += applied
        return applied

    def unknown_keys(self, table: str, existing: set[str]) -> list[str]:
        """移行元に存在しないキーを指している行（書き間違いの検出用）。"""
        return sorted(k for t, k in self.values if t == table and k not in existing)
