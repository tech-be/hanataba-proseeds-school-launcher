"""書いてもらった補正データを検査する。

**移行を流す前に、ここで気づけるようにする。** 埋め間違いは移行ツール側では
「また入らなかった」という形でしか出ず、原因が分かりにくい。
"""

from __future__ import annotations

from dataclasses import dataclass

from migrator.overrides import Overrides


@dataclass
class Finding:
    ok: bool
    label: str
    detail: str = ""

    def __str__(self) -> str:
        return f"[{'OK' if self.ok else 'NG'}] {self.label}{': ' + self.detail if self.detail else ''}"


def run(overrides: Overrides, users: dict[str, dict], tenant_id: int) -> list[Finding]:
    """`users` は移行元の会員（`user_id` -> 行）。"""
    out: list[Finding] = []
    total = sum(len(v) for v in overrides.values.values())
    out.append(Finding(total > 0, "補正データが書かれている", f"{total} 値"))

    unknown = overrides.unknown_keys("user", set(users))
    out.append(
        Finding(
            not unknown,
            "移行元に存在する会員を指している",
            "" if not unknown else f"存在しない user_id: {unknown[:10]}",
        )
    )

    # **上書きしたあとの状態**で重複を見る。割り当て同士だけを見ても、
    # 「現在の値のまま残す」会員と衝突している場合に気づけない。
    # 削除済みの会員はメールが NULL で入るので数えない（2026-10-26 決定）
    alive = {u: row for u, row in users.items() if not int(row.get("del_chk") or 0)}
    final: dict[str, list[str]] = {}
    for user_id, row in alive.items():
        mail = _mail_after(overrides, user_id, row)
        if mail:
            final.setdefault(mail.lower(), []).append(user_id)
    duplicated = [ids for ids in final.values() if len(ids) > 1]
    out.append(
        Finding(
            not duplicated,
            "上書き後にアドレスが重複していない（削除済みの会員を除く）",
            # **アドレスは出さない**（個人情報）。会員 ID だけ
            ""
            if not duplicated
            else f"{len(duplicated)} 組: " + ", ".join(str(ids) for ids in duplicated[:3]),
        )
    )

    # メールは任意になった（新 `20260928061152`）。空の会員はログイン ID でログインする。
    # **どちらも無い会員はログインできない**ので、それだけを NG にする
    no_mail = [u for u, row in alive.items() if not _mail_after(overrides, u, row)]
    stranded = [u for u in no_mail if not str(alive[u].get("login_id") or "").strip()]
    out.append(
        Finding(
            not stranded,
            "メールもログイン ID も無い会員がいない",
            f"メールの無い会員 {len(no_mail)} 名（ログイン ID でログインする）"
            + ("" if not stranded else f"。どちらも無い: {len(stranded)} 名（例: {stranded[:5]}）"),
        )
    )
    return out


def _mail_after(overrides: Overrides, user_id: str, row: dict) -> str:
    """補正データを当てたあとのメール。"""
    patch = overrides.values.get(("user", user_id), {})
    return str(patch.get("mail_add", row.get("mail_add")) or "").strip()
