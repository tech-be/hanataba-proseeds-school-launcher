"""設定の読み込み。

接続情報は**環境変数**、移行の決め事（対応表・テナント・採番の名前空間）は
**設定ファイル**から読む。認証情報を設定ファイルに書かせない。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import envfile
from .core import passwords
from .errors import ConfigError

DEFAULT_CONFIG = "config.yaml"


@dataclass(frozen=True)
class TenantConfig:
    """移行対象のテナント（docs/db/01-foundation/migration-spec.md 1-1 の確認事項1・2）。"""

    legacy_id: int
    slug: str
    name: str | None = None

    def __post_init__(self) -> None:
        if not self.slug:
            raise ConfigError("tenant.slug は必須（既存ツールがテナントを引くキー）")


@dataclass(frozen=True)
class Config:
    tenant: TenantConfig
    #: 決定論 ULID の名前空間。**採番規則を変えたらここも変える**
    ulid_namespace: str = "lw2"
    #: ULID の時刻部の既定値（旧レコードに作成日時が無いとき）
    epoch_ms: int = 1_700_000_000_000
    #: 運営から受け取った対応表（ロール・都道府県など）
    mappings: dict[str, dict] = field(default_factory=dict)
    #: **この移行元には無いと分かっているテーブル。** 設定に書いたときだけ読み飛ばす
    #: （環境差を黙って見逃さないため。本番では空になっているのが正しい）
    absent_source_tables: tuple[str, ...] = ()
    #: 旧環境の秘密鍵（`security.mcrypt.key`）。**環境変数からのみ受け取る**
    legacy_crypt_key: str = ""
    source_dsn: str = ""
    target_dsn: str = ""
    work_dir: Path = Path("./out")
    #: 暫定対応で入れる仮の値（`course_price` など）。**届いたら差し替える**
    provisional: dict = field(default_factory=dict)
    #: 補正データ（暫定対応で決めた値）の置き場所
    overrides_path: Path = Path("overrides.csv")

    @property
    def role_map_source(self) -> str:
        return str(self.mappings.get("role", {}).get("source", ""))


def _load_file(path: Path) -> dict[str, Any]:
    """設定を読む。`.json` なら標準ライブラリだけで読めるようにしてある。"""
    if not path.exists():
        raise ConfigError(f"設定ファイルが無い: {path}")
    if path.suffix == ".json":
        import json

        with path.open(encoding="utf-8") as handle:
            return json.load(handle) or {}
    try:
        import yaml
    except ModuleNotFoundError as exc:  # pragma: no cover - 環境依存
        raise ConfigError("PyYAML が要る: pip install -r requirements.txt") from exc
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def load(path: str | Path = DEFAULT_CONFIG, env: dict[str, str] | None = None) -> Config:
    """設定ファイルと環境変数から `Config` を作る。

    接続情報は環境変数（`SOURCE_DB_URL` / `TARGET_DB_URL`）。`.env` があればそれも読む
    （**実際の環境変数のほうが優先**）。
    """
    env = envfile.load(env=env)
    raw = _load_file(Path(path))

    tenant_raw = raw.get("tenant") or {}
    if "legacy_id" not in tenant_raw:
        raise ConfigError("tenant.legacy_id は必須（recademy は 12）")
    tenant = TenantConfig(
        legacy_id=int(tenant_raw["legacy_id"]),
        slug=str(tenant_raw.get("slug", "")),
        name=tenant_raw.get("name"),
    )

    return Config(
        tenant=tenant,
        ulid_namespace=str(raw.get("ulid_namespace", "lw2")),
        epoch_ms=int(raw.get("epoch_ms", 1_700_000_000_000)),
        mappings=raw.get("mappings") or {},
        absent_source_tables=tuple((raw.get("source") or {}).get("absent_tables") or ()),
        legacy_crypt_key=env.get(passwords.SECRET_ENV, ""),
        source_dsn=env.get("SOURCE_DB_URL", ""),
        target_dsn=env.get("TARGET_DB_URL", ""),
        work_dir=Path(raw.get("work_dir", "./out")),
        overrides_path=Path(raw.get("overrides", "overrides.csv")),
        provisional=raw.get("provisional") or {},
    )
