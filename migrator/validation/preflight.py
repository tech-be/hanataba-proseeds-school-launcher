"""事前検査（docs/db/01-foundation/migration-spec.md 3.1）。

**抽出を始める前に通す。** ここで落ちるものは運営判断か列の変更が要るもので、
流しながら直すことはできない。
"""

from __future__ import annotations

from dataclasses import dataclass

from ..context import RunContext
from ..core.text import LengthCheck, find_mojibake, find_over_length
from ..errors import PreflightError


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str = ""

    def __str__(self) -> str:
        return f"[{'OK' if self.ok else 'NG'}] {self.name}{': ' + self.detail if self.detail else ''}"


def run_all(ctx: RunContext) -> list[CheckResult]:
    """すべての事前検査を通す。**NG が1件でもあれば投入を始めない。**"""
    results = [
        _tenant_row(ctx),
        _tenant_name(ctx),
        _phone_length(ctx),
        _encoding(ctx),
        _role_map(ctx),
        _source_tables(ctx),
        _password_key(ctx),
        _unique_conflicts(ctx),
        _target_is_seeded(ctx),
    ]
    failed = [r for r in results if not r.ok]
    if failed:
        raise PreflightError("事前検査に失敗した:\n" + "\n".join(str(r) for r in failed))
    return results


def _source_tables(ctx: RunContext) -> CheckResult:
    """**Step が読むテーブルが移行元にそろっているか。**

    環境によってテーブルの有無が違う（`user_login_chk_log` は `20230821_cdss.sql` で
    足されたもので、ステージングには無い）。読みに行ってから落ちると、原因が
    ドライバのエラーとしてしか出ない。ここで先にまとめて出す。

    設定 `source.absent_tables` に書いたものだけ「無いと分かっている」として通す。
    **通した分のデータは移らない**ので、件数と名前を必ず出す。
    """
    from ..phases.registry import build_sections

    declared = {
        step.source_table
        for section in build_sections()
        for phase in section.phases
        for step in phase.steps
        if step.source_table
    }
    missing = ctx.require_source().missing_tables(declared)
    absent = ctx.absent_source_tables()
    unexpected = [t for t in missing if t not in absent]
    if unexpected:
        return CheckResult(
            "移行元にテーブルがそろっている",
            False,
            f"{unexpected} が無い。移行元が正しいか確かめる。"
            "この環境に無いと分かっているなら `source.absent_tables` に書く",
        )
    detail = f"{len(declared)} テーブル"
    if missing:
        detail += f" / 無いと宣言済み: {missing}（この分は移らない）"
    return CheckResult("移行元にテーブルがそろっている", True, detail)


def _password_key(ctx: RunContext) -> CheckResult:
    """**旧の秘密鍵で実際に復号できるか。**

    鍵が違っても復号は例外にならず、意味のない文字列が返る。気づかずに流すと
    **全員が「ログインだけできない」状態**で入る。数十件だけ試して確かめる。
    """
    from ..core.passwords import SECRET_ENV, LegacyPasswordCipher

    if not ctx.config.legacy_crypt_key:
        return CheckResult(
            "パスワードを復号できる",
            False,
            f"環境変数 {SECRET_ENV} が空。lw2 の `security.mcrypt.key` を入れる",
        )
    cipher = LegacyPasswordCipher(ctx.config.legacy_crypt_key)
    rows = ctx.require_source().fetch_for_tenant("user", ("user_id", "password"))
    sample = [r for r in rows if r.get("password")][:200]
    if not sample:
        return CheckResult("パスワードを復号できる", True, "旧にパスワードが1件も無い")
    failed = [r["user_id"] for r in sample if cipher.decrypt(r["password"]) is None]
    if len(failed) > len(sample) // 2:
        return CheckResult(
            "パスワードを復号できる",
            False,
            f"{len(sample)} 件中 {len(failed)} 件が復号できない。**鍵が違う可能性が高い**",
        )
    detail = f"{len(sample)} 件試して {len(sample) - len(failed)} 件"
    if failed:
        detail += f" / 復号できない会員: {failed[:5]}"
    return CheckResult("パスワードを復号できる", True, detail)


#: 新環境の UNIQUE に効く、旧側の一意性。**投入してから気づくと、やり直しになる**
#: **残す行の決め方が無いものだけ**を挙げる。`line_id` の重複は
#: `LineLinksStep` が「削除されていない会員に寄せる」と決めてあるので入れない
UNIQUE_SOURCES: tuple[tuple[str, str, str], ...] = (
    ("login_id", "users.login_id", "uk_users_login_id"),
)


def _unique_conflicts(ctx: RunContext) -> CheckResult:
    """旧データの重複が、新環境の UNIQUE に当たらないか**先に**見る。

    変換のときにも止まるが、それだと会員の再ハッシュ（数分）を終えてから落ちる。
    """
    source = ctx.require_source()
    problems = []
    for column, target, index in UNIQUE_SOURCES:
        rows = source.fetch_for_tenant("user", ("user_id", column))
        counts: dict[str, list[int]] = {}
        for row in rows:
            value = row.get(column)
            if value is None or str(value).strip() == "":
                continue
            counts.setdefault(str(value), []).append(int(row["user_id"]))
        duplicated = {v: ids for v, ids in counts.items() if len(ids) > 1}
        if duplicated:
            problems.append(
                f"`user.{column}` が {len(duplicated)} 組重複（→ {target} / {index}）"
                f"。対象 {sum(len(i) for i in duplicated.values())} 名: "
                f"{[ids for ids in list(duplicated.values())[:3]]}"
            )
    if problems:
        # **止めない。** 当たった会員は移らず一覧に出る（暫定対応のあと再実行する）
        return CheckResult(
            "新環境の UNIQUE に当たる重複",
            True,
            " / ".join(problems) + "。**この会員は移行しない**",
        )
    return CheckResult("新環境の UNIQUE に当たる重複", True, f"{len(UNIQUE_SOURCES)} 種を確認: 無し")


#: テナントの1行を作るフェーズ。**ここを含むかどうかで「初回」か「続き」かが決まる**
TENANT_PHASE = "foundation.2"


def _target_is_seeded(ctx: RunContext) -> CheckResult:
    """**移行先の状態が、これから流すフェーズと噛み合っているか。**

    - テナントを作るフェーズを含む（＝初回）: 対象テナントが**まだ無い**こと。
      前の移行の残りが混ざると、件数の照合が意味を失う
    - 含まない（＝続きのフェーズ）: 対象テナントが**すでにある**こと。
      無ければ、前のフェーズを飛ばしている

    どちらの場合も、シードが入っていることは要る。
    """
    target = ctx.target
    if target.connectionless:
        return CheckResult("移行先の状態", True, "接続なし（plan）")

    seeded = target.query("SELECT COUNT(*) AS n FROM tenants")
    count = int(seeded[0]["n"]) if seeded else 0
    if count == 0:
        return CheckResult(
            "移行先の状態",
            False,
            "テナントが1件も無い。**シードが入っていない**"
            "（`make reseed` の `make seed` まで通す）",
        )

    slug = ctx.config.tenant.slug
    already = target.query("SELECT id FROM tenants WHERE slug = %s", (slug,))
    creates_tenant = not ctx.selected or TENANT_PHASE in ctx.selected
    if creates_tenant and already:
        return CheckResult(
            "移行先の状態",
            False,
            f"`{slug}` がすでにある。作り直すなら `make reseed` でリセットしてから流す"
            "（投入自体は冪等だが、件数の照合が前回の結果と混ざる）",
        )
    if not creates_tenant and not already:
        return CheckResult(
            "移行先の状態",
            False,
            f"`{slug}` がまだ無い。**{TENANT_PHASE} を飛ばしている**",
        )
    state = "未登録（これから作る）" if creates_tenant else f"登録済み（id={already[0]['id']}）"
    return CheckResult("移行先の状態", True, f"シードのテナント {count} 件 / `{slug}` は{state}")


def _tenant_row(ctx: RunContext) -> CheckResult:
    rows = ctx.require_source().fetch_for_tenant("tenant", ("tenant_id", "tenant_code", "del_chk"))
    if len(rows) != 1:
        return CheckResult("移行対象テナントが1件", False, f"{len(rows)} 件")
    if int(rows[0].get("del_chk") or 0) == 1:
        return CheckResult("テナントが削除済みでない", False, "del_chk=1")
    return CheckResult("移行対象テナントが1件", True)


def _tenant_name(ctx: RunContext) -> CheckResult:
    rows = ctx.require_source().fetch_for_tenant("tenant", ("tenant_name",))
    value = (rows[0].get("tenant_name") or "").strip() if rows else ""
    if value or ctx.config.tenant.name:
        return CheckResult("tenants.name に入れる値がある", True)
    return CheckResult("tenants.name に入れる値がある", False, "tenant_name が NULL / 空で設定にも name が無い")


def _phone_length(ctx: RunContext) -> CheckResult:
    rows = ctx.require_source().fetch_for_tenant("user", ("user_id", "tel", "mobile_tel"))
    over = find_over_length(rows, (LengthCheck("tel", 32), LengthCheck("mobile_tel", 32)))
    if over:
        return CheckResult("電話番号が32文字に収まる", False, f"{over}（切り捨てず列を広げる）")
    return CheckResult("電話番号が32文字に収まる", True)


def _encoding(ctx: RunContext) -> CheckResult:
    rows = ctx.require_source().fetch_for_tenant("user", ("user_id", "name_sei", "name_mei", "user_memo"))
    hits = find_mojibake(rows, ("name_sei", "name_mei", "user_memo"))
    if hits:
        return CheckResult("文字化けが無い", False, f"{hits}（cp932 混入の疑い）")
    return CheckResult("文字化けが無い", True)


def _role_map(ctx: RunContext) -> CheckResult:
    """ロールの対応表が**旧の全ロールを覆っているか**。

    会員が実際に使っている `user.role_id` だけでなく、**`role_master` の全行**を見る。
    `user_roles` へのマスタ投入は `role_master` を読むので、会員が使っていない
    ロールでも対応表に無ければそこで止まる。
    """
    try:
        role_map = ctx.role_map()
    except Exception as exc:  # 設定不足
        return CheckResult("ロール対応表がある", False, str(exc))

    source = ctx.require_source()
    user_rows = source.fetch_for_tenant("user", ("user_id", "role_id"))
    # **ロールが未設定の会員がいる。** `users.role` は NOT NULL + FK なので入れられない
    no_role = [r["user_id"] for r in user_rows if r["role_id"] is None]

    used = {int(r["role_id"]) for r in user_rows if r["role_id"] is not None}
    defined = {int(r["role_id"]) for r in source.fetch_global("role_master", ("role_id",))}

    unknown_used = sorted(used - set(role_map.mapping))
    unknown_defined = sorted(defined - set(role_map.mapping))
    if unknown_used or unknown_defined:
        detail = []
        if unknown_used:
            detail.append(f"会員が使っている role_id: {unknown_used}")
        if unknown_defined:
            detail.append(f"role_master にある role_id: {unknown_defined}")
        return CheckResult("ロール対応表が全値を覆う", False, " / ".join(detail))
    detail = f"会員 {len(used)} 種 / マスタ {len(defined)} 種"
    if no_role:
        # **既定値に倒さない。** `users.role` は NOT NULL なので、この会員は移らない
        detail += f" / role_id が NULL の {len(no_role)} 名は移行しない（例: {no_role[:5]}）"
    return CheckResult("ロール対応表が全値を覆う", True, detail)
