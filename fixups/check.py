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
    # 「現在の値のまま残す」会員と衝突している場合に気づけない
    final: dict[str, list[str]] = {}
    for user_id, row in users.items():
        patch = overrides.values.get(("user", user_id), {})
        mail = patch.get("mail_add", row.get("mail_add"))
        mail = str(mail or "").strip().lower()
        if mail:
            final.setdefault(mail, []).append(user_id)
    duplicated = {m: ids for m, ids in final.items() if len(ids) > 1}
    out.append(
        Finding(
            not duplicated,
            "上書き後にアドレスが重複していない",
            ""
            if not duplicated
            else f"{len(duplicated)} 件: "
            + ", ".join(f"{m}={ids}" for m, ids in list(duplicated.items())[:3])
            + "（移行しない会員が含まれていれば、そのぶんは実害なし）",
        )
    )

    missing = [u for u, row in users.items() if not str(
        overrides.values.get(("user", u), {}).get("mail_add", row.get("mail_add")) or ""
    ).strip()]
    out.append(
        Finding(
            not missing,
            "上書き後にアドレスが埋まっている",
            "" if not missing else f"{len(missing)} 名が空のまま（例: {missing[:5]}）",
        )
    )
    return out
