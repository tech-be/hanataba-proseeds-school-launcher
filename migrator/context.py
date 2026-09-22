"""実行時に Step が共有するもの。

**Step は自分で接続を張らない / 自分で採番規則を決めない。** すべてここから受け取る。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from .config import Config
from .core.codes import CodeMap, role_map
from .core.ids import TenantId, UlidFactory
from .core.records import StepResult
from .db.source import SourceDatabase
from .db.target import TargetDatabase
from .errors import ConfigError


@dataclass
class RunContext:
    """1回の実行の文脈。"""

    config: Config
    source: SourceDatabase | None
    target: TargetDatabase
    ulid: UlidFactory
    tenant_id: TenantId = field(default_factory=TenantId)
    logger: logging.Logger = field(default_factory=lambda: logging.getLogger("migrator"))
    results: list[StepResult] = field(default_factory=list)
    completed: set[str] = field(default_factory=set)
    #: この実行で流すフェーズの識別子。**事前検査が「初回か続きか」を見分けるのに使う**
    selected: set[str] = field(default_factory=set)
    #: `pref_master` の読み込み結果（1回だけ引く）
    _prefectures: dict[int, str] | None = None
    _countries: dict[str, str] | None = None
    _schema_reader: object | None = None
    _exclusions: object | None = None

    @property
    def dry_run(self) -> bool:
        return self.target.dry_run

    def require_source(self) -> SourceDatabase:
        if self.source is None:
            raise ConfigError("旧環境への接続が無い（SOURCE_DB_URL を設定する）")
        return self.source

    def record(self, result: StepResult) -> StepResult:
        self.results.append(result)
        self.completed.add(result.step)
        self.logger.info("%s", result)
        return result

    # --- 対応表 ------------------------------------------------------------
    def country_table(self) -> dict[str, str]:
        """国コード → 国名。**旧 DB の `country_master` から引く**（都道府県と同じ扱い）。

        コードのまま入れると、画面に `AR` と出る。
        """
        if self._countries is None:
            rows = self.require_source().fetch_global(
                "country_master", ("country_code", "country_name")
            )
            self._countries = {str(r["country_code"]): str(r["country_name"]) for r in rows}
            self.logger.info("country_master から国名 %d 件を読んだ", len(self._countries))
        return self._countries

    def exclusions(self):
        """制約に当たって移さなかった行の一覧（`work_dir/移行しない行.csv`）。"""
        if self._exclusions is None:
            from .validation.exclusions import ExclusionLog

            self._exclusions = ExclusionLog(self.config.work_dir, self.logger)
        return self._exclusions

    def schema_reader(self):
        """移行先のスキーマ読み取り（1テーブル1回だけ問い合わせる）。"""
        if self._schema_reader is None:
            from .validation.constraints import SchemaReader

            self._schema_reader = SchemaReader(self.target)
        return self._schema_reader

    def password_migration(self):
        """パスワードの復号・再ハッシュ。**鍵が無ければ止める。**

        黙って空のハッシュを入れると、**エラーにならないまま全員がログインできない**
        状態で cutover を迎える。ここで止めるのはそのため。
        """
        from .core.passwords import DEFAULT_COST, LegacyPasswordCipher, PasswordMigration

        cost = int((self.config.mappings.get("password") or {}).get("bcrypt_cost", DEFAULT_COST))
        return PasswordMigration(LegacyPasswordCipher(self.config.legacy_crypt_key), cost=cost)

    def absent_source_tables(self) -> frozenset[str]:
        """移行元に無いと**設定で宣言された**テーブル。宣言が無ければ空。"""
        return frozenset(self.config.absent_source_tables)

    def role_map(self) -> CodeMap:
        raw = (self.config.mappings.get("role") or {}).get("values") or {}
        if not raw:
            raise ConfigError(
                "ロールの対応表が設定に無い。運営から受け取って config に書く"
                "（docs/db/01-foundation/migration-spec.md 1-1 の確認事項4）"
            )
        return role_map({int(k): str(v) for k, v in raw.items()}, self.config.role_map_source)

    def prefecture_table(self) -> dict[int, str]:
        """`pref_id` → 都道府県名。

        **既定は旧 DB の `pref_master` から引く。** 47件を設定ファイルに手で持つと、
        書き漏れた1件で住所の移行が止まる（`MappingError`）。

        **`pref_name` は `PREF_CODE_01` のようなコードで、名称は `description`。**
        `role_master.role_name` と同じ作りなので取り違えない。

        設定に `mappings.prefecture.values` があればそちらを優先する（旧 DB を読めない
        環境や、名称を上書きしたい場合のため）。
        """
        raw = (self.config.mappings.get("prefecture") or {}).get("values") or {}
        if raw:
            return {int(k): str(v) for k, v in raw.items()}
        if self._prefectures is None:
            rows = self.require_source().fetch_global(
                "pref_master", ("pref_id", "description")
            )
            self._prefectures = {int(r["pref_id"]): str(r["description"]) for r in rows}
            self.logger.info("pref_master から都道府県 %d 件を読んだ", len(self._prefectures))
        return self._prefectures


def build_context(
    config: Config,
    source: SourceDatabase | None,
    target: TargetDatabase,
    logger: logging.Logger | None = None,
) -> RunContext:
    return RunContext(
        config=config,
        source=source,
        target=target,
        ulid=UlidFactory(config.ulid_namespace, config.epoch_ms),
        logger=logger or logging.getLogger("migrator"),
    )
