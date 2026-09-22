"""ツール全体で使う例外。

**握り潰さない。** 移行は「止まる」ほうが「誤ったデータが入る」より安全なので、
想定外はすべて例外にして停止させる。
"""


class MigrationError(Exception):
    """移行ツールの基底例外。"""


class ConfigError(MigrationError):
    """設定の不備。"""


class GuardError(MigrationError):
    """仕様で禁じられた操作を検出した（ガードに引っかかった）。"""


class ForbiddenColumnError(GuardError):
    """平文の認証情報など、抽出してはいけない列を参照した。

    docs/migration-spec.md 3.8「移行の対象外 / A. 移行できないもの」。
    これらは「移さない」ではなく **「読み出さない」**。
    """


class ExcludedTableError(GuardError):
    """移行対象外のテーブルを扱おうとした（純ログなど）。"""


class TenantScopeError(GuardError):
    """テナントの絞り込みが無いクエリを実行しようとした。

    lw2 は同一 DB に 73 テナントが同居する。絞り込みを落とすと他テナントの行を拾う。
    """


class MappingError(MigrationError):
    """コード値の対応表に無い値が来た。

    既定値に倒さず停止する（docs/migration-spec.md 3.6）。
    """


class PreflightError(MigrationError):
    """事前検査に失敗した。投入を開始しない。"""


class VerificationError(MigrationError):
    """投入後の検証に失敗した。"""


class DependencyError(MigrationError):
    """依存する Step / フェーズが未完了。"""
