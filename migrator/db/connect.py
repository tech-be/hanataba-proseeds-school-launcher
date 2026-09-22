"""接続の生成。**DSN は環境変数から**受け取り、設定ファイルには書かせない。"""

from __future__ import annotations

from urllib.parse import unquote, urlparse

from ..errors import ConfigError


def connect(dsn: str):
    """`mysql://user:pass@host:port/db` を PyMySQL の接続にする。"""
    if not dsn:
        raise ConfigError("DSN が空")
    try:
        import pymysql
        from pymysql.cursors import DictCursor
    except ModuleNotFoundError as exc:  # pragma: no cover - 環境依存
        raise ConfigError("PyMySQL が要る: pip install -r requirements.txt") from exc

    parsed = urlparse(dsn)
    if parsed.scheme not in ("mysql", "mysql+pymysql"):
        raise ConfigError(f"対応していない DSN: {parsed.scheme}")
    return pymysql.connect(
        host=parsed.hostname or "localhost",
        port=parsed.port or 3306,
        user=unquote(parsed.username or ""),
        password=unquote(parsed.password or ""),
        database=(parsed.path or "/").lstrip("/"),
        charset="utf8mb4",
        cursorclass=DictCursor,
        autocommit=False,
        # `timestamp` 列の変換をセッション TZ に委ねるため、UTC を明示する
        init_command="SET time_zone = '+00:00'",
    )
