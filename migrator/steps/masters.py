"""フェーズ2 — マスタの追加値。

新環境のシードだけでは lw2 の値を受けきれない。**足りない値を先に入れる**
（FK の参照先なので、これらが無いと会員も設定も入らない）。

`user_roles` は `name_ja` / `sort_order` を持つグローバルマスタなので、
**旧 `role_master` の表示名と並び順をそのまま移せる**（新テーブルは作らない）。

**どのテーブルも `tenant_id` を持たない。** テナントの行より先に入れて、
FK の参照先をそろえてから、それを使う行（`tenants` / `users`）を作る。
"""

from __future__ import annotations

from ..context import RunContext
from ..core.records import Record
from ..errors import MappingError
from .base import Step

#: 旧 `role_master` から読む列
ROLE_COLUMNS = ("role_id", "role_name", "role_index", "del_chk")
#: 表示名の出どころ。`role_master.role_name` は 'COMPANY_MANAGER' のようなコードで、
#: **表示名ではない**。表示名は `translate_master` に言語別で入っている
TRANSLATE_COLUMNS = ("master_type", "language_code", "code", "text")

#: 新環境のシードに既にある `user_roles.code`
SEEDED_ROLES = frozenset({"platform_admin", "tenant_admin", "instructor", "learner", "system"})


class UserRolesStep(Step):
    """lw2 の8ロールのうち、新環境に無いものを `user_roles` に足す。"""

    name = "master.user_roles"
    description = "user_roles に不足するロールを追加する（表示名と並び順も移す）"
    source_table = "role_master"
    target_table = "user_roles"
    # 削除日は旧に無く、移行した時刻を入れている
    volatile_columns = ("deprecated_at",)
    # tenant_id を使わない（user_roles は tenant_id を持たないグローバルマスタ）ので
    # テナントに依存しない。FK の参照先として、テナントより先に入れる

    def extract(self, ctx: RunContext) -> list[dict]:
        source = ctx.require_source()
        roles = source.fetch_global("role_master", ROLE_COLUMNS)
        labels = source.fetch_global(
            "translate_master", TRANSLATE_COLUMNS, where="master_type = 'role'"
        )
        by_code = {
            (r["code"], r["language_code"]): r["text"] for r in labels
        }
        for role in roles:
            role["_label_ja"] = by_code.get((role["role_name"], "ja"))
        return roles

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        role_map = ctx.role_map()
        records: list[Record] = []
        for row in rows:
            code = role_map.to_new(int(row["role_id"]))
            if code in SEEDED_ROLES:
                continue  # シード済み。表示名を上書きしない
            deprecated = int(row.get("del_chk") or 0) == 1
            records.append(
                Record(
                    table="user_roles",
                    values={
                        "code": code,
                        "name_ja": row.get("_label_ja") or code,
                        "is_admin": code in {"system_admin"},
                        "is_instructor": code in {"instructor"},
                        "sort_order": int(row.get("role_index") or 0),
                        "is_system": True,
                        # 削除状態は deprecated_at の有無で判断できるようにし、
                        # active はそこから導出する（二重管理にしない）
                        "active": not deprecated,
                        "deprecated_at": _now_if(deprecated),
                    },
                    natural_key=("code",),
                )
            )
        return records


class LookupValueStep(Step):
    """ルックアップ表に値を1つ足すだけの Step。

    `tenant_statuses` の `deleted`、`auth_methods` の SNS / SAML / TOTP、
    `email_kinds` の通知種別など、**旧データに依存しない追加**をこれで表す。
    """

    def __init__(self, name: str, table: str, values: list[dict], description: str = "") -> None:
        self.name = name
        self.target_table = table
        self.description = description or f"{table} に値を追加する"
        self._values = values
        super().__init__()

    def extract(self, ctx: RunContext) -> list[dict]:
        return list(self._values)

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        return [Record(table=self.target_table, values=dict(r), natural_key=("code",)) for r in rows]


def tenant_status_deleted() -> LookupValueStep:
    """`tenant_statuses` に `deleted` を足す（lw2 の `del_chk=1` の受け皿）。"""
    return LookupValueStep(
        name="master.tenant_statuses.deleted",
        table="tenant_statuses",
        description="tenant_statuses に deleted を追加する",
        values=[
            {
                "code": "deleted",
                "name_ja": "削除済み",
                "is_operational": False,
                "is_trial": False,
                "sort_order": 40,
                "is_system": True,
            }
        ],
    )


def auth_methods() -> LookupValueStep:
    """SNS ログイン・SAML・2FA の値を足す（lw2 の `sns_setting` / `sso_config`）。"""
    return LookupValueStep(
        name="master.auth_methods",
        table="auth_methods",
        description="auth_methods に SNS / SAML / TOTP を追加する",
        values=[
            {"code": code, "name_ja": label, "sort_order": order, "is_system": True}
            for code, label, order in (
                ("saml", "SAML SSO", 60),
                ("facebook", "Facebook", 70),
                ("twitter", "X (Twitter)", 80),
                ("instagram", "Instagram", 90),
                ("totp", "二要素認証 (TOTP)", 100),
            )
        ],
    )


def email_kinds() -> LookupValueStep:
    """lw2 の通知種別を足す（現行13種別には無い）。"""
    return LookupValueStep(
        name="master.email_kinds",
        table="email_kinds",
        description="email_kinds にお知らせ / スカウト / 足あと / 掲示板コメントを追加する",
        values=[
            {"code": code, "name_ja": label, "sort_order": order, "is_system": True}
            for code, label, order in (
                ("announcement", "アナウンス・お知らせ", 200),
                ("scout", "スカウト", 210),
                ("footprint", "足あと", 220),
                ("bbs_comment", "掲示板コメント", 230),
            )
        ],
    )


def _now_if(flag: bool):
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).replace(tzinfo=None) if flag else None


def build() -> list[Step]:
    """フェーズ2の Step 一式。"""
    return [UserRolesStep(), tenant_status_deleted(), auth_methods(), email_kinds()]
