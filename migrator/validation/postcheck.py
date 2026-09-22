"""投入後の検証（docs/db/01-foundation/migration-spec.md 3.5）。

**フェーズの区切りで通す。** 1つでも落ちたらそのフェーズをやり直す。
"""

from __future__ import annotations

from ..context import RunContext
from ..errors import VerificationError


def target_tenant_once(ctx: RunContext) -> None:
    """移行先に**対象テナントが1件だけ**あるか。

    **テナントの総数では判断しない。** 動作確認用のローカル環境にはデモ seed の
    テナント（`demo` など9件）が居るのが正常で、総数を見ると必ず落ちる。
    見るのは次の2つ。

    1. `slug = recademy` の行が **ちょうど1件**あるか
    2. **同じ `name` の行が他に無いか** — `tenants.name` に UNIQUE が無く、
       slug を変えれば同じテナントを二重に作れてしまうため
       （[移行時の注意事項](../../docs/db/01-foundation/review.md#移行時の注意事項)）
    """
    slug = ctx.config.tenant.slug
    rows = ctx.target.query("SELECT id, name FROM tenants WHERE slug = %s", (slug,))
    if not rows:
        if ctx.dry_run:
            return  # dry-run では作っていないので見ない
        raise VerificationError(f"slug={slug} のテナントが無い")
    if len(rows) > 1:
        raise VerificationError(f"slug={slug} のテナントが {len(rows)} 件ある")

    name = rows[0]["name"]
    duplicates = ctx.target.query(
        "SELECT id, slug FROM tenants WHERE name = %s AND slug <> %s", (name, slug)
    )
    if duplicates:
        raise VerificationError(
            f"同じ name のテナントが別 slug で存在する: {duplicates}。"
            "二重登録の疑いがあるので、どちらが正しいかを確かめてから進める"
        )


def no_platform_admin(ctx: RunContext) -> None:
    """`platform_admin` が1件も無いか。**1件でもあれば停止して原因を追う。**"""
    rows = ctx.target.query(
        "SELECT COUNT(*) AS n FROM users WHERE tenant_id = %s AND role = 'platform_admin'",
        (ctx.tenant_id.value,),
    )
    if rows and int(rows[0]["n"]) > 0:
        raise VerificationError(
            f"platform_admin が {rows[0]['n']} 件ある。移行では絶対に付けない"
        )


def email_unique(ctx: RunContext) -> None:
    """`UNIQUE (tenant_id, email)` に反する重複が無いか。"""
    rows = ctx.target.query(
        "SELECT email, COUNT(*) AS n FROM users WHERE tenant_id = %s "
        "GROUP BY email HAVING n > 1",
        (ctx.tenant_id.value,),
    )
    if rows:
        raise VerificationError(f"メールが重複している: {[r['email'] for r in rows][:10]}")


def row_count(ctx: RunContext, table: str, expected: int) -> None:
    """抽出時の件数と投入後の件数を照合する。"""
    rows = ctx.target.query(f"SELECT COUNT(*) AS n FROM `{table}` WHERE tenant_id = %s", (ctx.tenant_id.value,))
    if rows and int(rows[0]["n"]) != expected:
        raise VerificationError(f"{table}: 件数が合わない（期待 {expected} / 実際 {rows[0]['n']}）")
