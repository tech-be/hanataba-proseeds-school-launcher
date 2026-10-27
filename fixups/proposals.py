"""雛形に入れる「提案値」。

**提案であって決定ではない。** `overrides.csv` に書き出したあと、人が読んで直せる。
機械的に決まるものだけを埋め、**判断が要るものは空のまま**にする（空欄は適用されない）。

| 種類 | 提案 | 根拠 |
|---|---|---|
| メールが無い | **空のまま**（NULL で入る） | 新はメールを任意にした（school-launcher `20260928061152`）。合成アドレスは新の画面に出て、そこにメールを送ろうとする（2026-10-26 決定） |
| メールが重複 | **最も新しくログインした会員**は現在の値のまま、残りは `NULL` | 統合すると学習記録まで1人に混ざる。どの会員に残すかは運営に確かめる（確認事項 D11。2026-10-26 決定） |
| LINE が重複 | 削除されていない会員に残し、他は `NULL` | 通知が届く先は1人に決まる |
| ロールが未設定 | **空のまま** | 権限の判断。機械的に決められない |
"""

from __future__ import annotations

#: 新環境のブリッジと同じ形式（`internal/service/external_user_import_service.go`）
SYSTEM = "lw2"


def synthetic_email(user_id: str) -> str:
    return f"ext-{user_id}@{SYSTEM}.invalid"


def for_missing_email(user_id: str, row: dict) -> tuple[str, str]:
    """**空のまま**（補正しない）。新はメールを任意にしたので NULL で入る（2026-10-26 決定）。"""
    return "", "移行元にアドレスが無い。新はメールを任意にしたので、空のまま NULL で入る"


def _last_login(row: dict) -> str:
    """並べるための最後のログインの日時（無ければ空文字 = いちばん古い扱い）。"""
    value = row.get("recent_login_date")
    return "" if value is None else str(value)


def keeper_of(group: list[dict]) -> str:
    """重複した組のうち、メールを残す会員。**最も新しくログインした会員**（同じなら旧 ID の小さい方）。"""
    best = max(group, key=lambda r: (_last_login(r), -int(r["user_id"])))
    return str(best["user_id"])


def for_duplicate_email(user_id: str, row: dict, group: list[dict]) -> tuple[str, str]:
    """重複した組のうち、**最も新しくログインした会員は現在の値のまま**、ほかは `NULL`（2026-10-26 決定）。

    提案であって決定ではない。どの会員に残すかは運営に確かめる（確認事項 D11）。
    """
    keep = keeper_of(group)
    if user_id == keep:
        return "", f"現在の値のまま残す（{len(group)} 名中、最も新しくログインした会員）"
    return (
        "NULL",
        f"`{row.get('mail_add')}` を {len(group)} 名が共有。{keep}（最も新しくログインした会員）に残すため、この会員は NULL",
    )


def for_duplicate_line(user_id: str, row: dict, group: list[dict]) -> tuple[str, str]:
    """**削除されていない会員に残す。** それでも複数なら、いちばん古い会員。"""
    alive = [r for r in group if int(r.get("del_chk") or 0) == 0]
    candidates = alive or group
    keep = str(min(candidates, key=lambda r: int(r["user_id"]))["user_id"])
    if user_id == keep:
        reason = "削除されていない会員" if alive else "全員削除済みのため、いちばん古い会員"
        return "", f"この会員に LINE を残す（{reason}）"
    return "NULL", f"{keep} に残すため、この会員からは外す"
