"""抽出クエリのガード（docs/migration-spec.md 3.1 / 3.8）。

**平文の認証情報は「移さない」ではなく「読み出さない」。** 人のレビューだけに頼らず、
クエリを実行する前に機械で弾く。
"""

from __future__ import annotations

import re

from ..errors import ExcludedTableError, ForbiddenColumnError, TenantScopeError

#: 抽出してはいけない列。理由は docs/db/01-foundation/review.md「移行の対象外 / A」。
FORBIDDEN_COLUMNS: dict[str, tuple[str, ...]] = {
    # lw2 自身の DB 接続情報。新環境は別サーバー・別 DB で、移しても機能しない
    "site": ("db_server", "user_id", "password", "database"),
    # 会員が入力したパスワードの平文。保存してよい場所が新環境に無い
    "user_login_log": ("input_password",),
    # 認証コードの平文
    "twostepverification_log": ("input_code", "correct_code"),
    "twostepverification": ("verification_code",),
}

#: 移行対象外のテーブル（純ログ）。受け皿があっても移さない。
EXCLUDED_TABLES: dict[str, str] = {
    "user_login_log": "純ログ。cutover 後の認証から記録を始める",
    "user_login_log_monthly": "純ログの月次集計。login_history から都度計算できる",
    "twostepverification_log": "純ログ。かつ正解コードの平文を含む",
    "user_auth_token": "発行中の一時トークン。移した時点で無効",
    "password_reminder": "発行中の一時トークン。移した時点で無効",
    "edit_form_data": "UI の一時状態。画面を開き直せば作り直される",
}

#: `tenant_id` を持たない共通マスタ。テナントで絞らず全行読む。
TENANT_GLOBAL_TABLES: frozenset[str] = frozenset(
    {
    "role_master",
    "profile_cate",
    "translate_master",
    "pref_master",
    "country_master",
    # インストール全体で1行。テナント別ではないが、新環境の相当物は
    # テナント単位の設定なので、移行対象テナントの設定として入れる（A3）
    "site",
}
)

_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _identifiers(sql: str) -> set[str]:
    return {m.group(0).lower() for m in _IDENT.finditer(sql.replace("`", " "))}


def check_forbidden_columns(sql: str) -> None:
    """禁止列を参照していないか調べる。**参照していたら実行前に落とす。**"""
    idents = _identifiers(sql)
    for table, columns in FORBIDDEN_COLUMNS.items():
        if table.lower() not in idents:
            continue
        hit = sorted(c for c in columns if c.lower() in idents)
        if hit:
            raise ForbiddenColumnError(
                f"{table} の {hit} を SELECT しようとした。"
                "平文の認証情報は移行できないもので、**読み出してもいけない**"
            )


def check_excluded_tables(table: str) -> None:
    """移行対象外のテーブルを扱おうとしていないか調べる。"""
    reason = EXCLUDED_TABLES.get(table)
    if reason:
        raise ExcludedTableError(f"{table} は移行対象外: {reason}")


def check_tenant_scope(sql: str, table: str) -> None:
    """テナントの絞り込みがあるか調べる。

    `tenant_id` 列を持たないテーブルは**親と join して絞る**。join も無いなら、
    共通マスタとして `TENANT_GLOBAL_TABLES` に登録しておく。
    """
    if table in TENANT_GLOBAL_TABLES:
        return
    lowered = sql.lower()
    if "tenant_id" in lowered and ("where" in lowered or "join" in lowered):
        return
    raise TenantScopeError(
        f"{table}: テナントの絞り込みが無い。lw2 は同一 DB に73テナントが同居しており、"
        "絞り込みを落とすと他テナントの行を拾う"
    )
