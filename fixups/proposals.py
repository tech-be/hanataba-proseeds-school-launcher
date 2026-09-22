"""雛形に入れる「提案値」。

**提案であって決定ではない。** `overrides.csv` に書き出したあと、人が読んで直せる。
機械的に決まるものだけを埋め、**判断が要るものは空のまま**にする（空欄は適用されない）。

| 種類 | 提案 | 根拠 |
|---|---|---|
| メールが無い | `ext-<user_id>@lw2.invalid` | 新環境のブリッジが作る合成アドレスと**同じ形式**。違うと同じ会員が別人になる |
| メールが重複 | 最小 `user_id` は現在の値のまま、残りに合成アドレス | 統合すると学習記録まで1人に混ざる |
| LINE が重複 | 削除されていない会員に残し、他は `NULL` | 通知が届く先は1人に決まる |
| ロールが未設定 | **空のまま** | 権限の判断。機械的に決められない |
"""

from __future__ import annotations

#: 新環境のブリッジと同じ形式（`internal/service/external_user_import_service.go`）
SYSTEM = "lw2"


def synthetic_email(user_id: str) -> str:
    return f"ext-{user_id}@{SYSTEM}.invalid"


def for_missing_email(user_id: str, row: dict) -> tuple[str, str]:
    return synthetic_email(user_id), "移行元にアドレスが無い。ブリッジと同じ形式の合成アドレス"


def for_duplicate_email(user_id: str, row: dict, group: list[str]) -> tuple[str, str]:
    """重複した組のうち、**最初に作られた会員は現在の値のまま**にする。"""
    keep = min(group, key=int)
    if user_id == keep:
        return "", f"現在の値のまま残す（{len(group)} 名中いちばん古い会員）"
    return (
        synthetic_email(user_id),
        f"`{row.get('mail_add')}` を {len(group)} 名が共有。{keep} に現在の値を残す",
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
