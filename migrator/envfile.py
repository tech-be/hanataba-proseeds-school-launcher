"""`.env` の読み込み。

接続情報は**環境変数で渡す**取り決めだが、ローカルでの動作確認のたびに `export` を
書くのは手間なので `.env` も読む。**実際の環境変数のほうが強い**（CI や本番で
`.env` が紛れ込んでも上書きされない）。
"""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_ENV_FILE = ".env"


def parse(text: str) -> dict[str, str]:
    """`KEY=VALUE` 形式を読む。`#` 始まりと空行は飛ばす。"""
    values: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        key, sep, value = line.partition("=")
        if not sep:
            continue
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key:
            values[key] = value
    return values


def load(path: str | Path = DEFAULT_ENV_FILE, env: dict[str, str] | None = None) -> dict[str, str]:
    """`.env` と環境変数を合わせた辞書を返す。**環境変数が優先。**"""
    base = dict(os.environ if env is None else env)
    file_path = Path(path)
    if not file_path.exists():
        return base
    from_file = parse(file_path.read_text(encoding="utf-8"))
    from_file.update(base)  # 環境変数で上書き
    return from_file
