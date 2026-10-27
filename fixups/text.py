"""本文の直しの提案（`fixups text`）。docs/db/05-support/migration-spec.md 0-9 の Q2・Q8。

**移行ツールは値を作り替えない。** 本文の直しはここで提案し、補正データ（`overrides.csv`）に
入れたものを移行ツールが読む。

| 対象 | 提案 |
|---|---|
| お知らせ・アナウンスの本文（HTML） | **プレーンテキスト**（新は本文をそのまま表示し、タグが見える。Q2） |
| 自動メール・LINE の文面の差し込み | `{USER_NAME}` → `{{user_name}}` など。**新に当たる差し込みが無いもの**（`{PASSWORD}` など）が残る文面は**提案せず空欄**にする（文面を運営に決めてもらう。Q8） |
"""

from __future__ import annotations

import html
import re

from migrator.steps.support.templates import LINE_KINDS, MAIL_KINDS

_BREAK = re.compile(r"<\s*(br|/p|/div|/li|/h[1-6]|/tr)\s*/?\s*>", re.IGNORECASE)
_ITEM = re.compile(r"<\s*li[^>]*>", re.IGNORECASE)
_TAG = re.compile(r"<[^>]+>")
_BLANKS = re.compile(r"\n{3,}")
_HTML_HINT = re.compile(r"<[a-zA-Z/!][^>]*>|&[a-zA-Z#0-9]+;")


def has_html(text: str | None) -> bool:
    return bool(text) and bool(_HTML_HINT.search(text))


def plain_text(text: str) -> str:
    """HTML をプレーンテキストにする。改行に当たるタグは改行に、箇条書きは「・」にする。"""
    out = text.replace("\r\n", "\n")
    out = _BREAK.sub("\n", out)
    out = _ITEM.sub("・", out)
    out = _TAG.sub("", out)
    out = html.unescape(out).replace("\xa0", " ")
    out = "\n".join(line.rstrip() for line in out.split("\n"))
    return _BLANKS.sub("\n\n", out).strip()


#: 旧の差し込み → 新の差し込み。**種別で値が入るものだけ**（新 `email_service.go`）
COMMON = {"USER_NAME": "user_name", "SERVICE_NAME": "tenant_name"}
BY_KIND: dict[str, dict[str, str]] = {
    "password_reset": {"REMINDER_URL": "reset_link"},
    "welcome": {"URL": "login_url"},
    "payment_succeeded": {"ITEM_NAME": "course_name", "TOTAL_PRICE": "amount", "URL": "course_url"},
    "subscription_canceled": {"ITEM_NAME": "plan_name", "APPLICATION_CLOSE_DATE": "access_end_date"},
    "email_verification": {},
    # 新の値（category_name など）は文面に書けない（許可リストに無い）
    "inquiry_received": {},
}
_LEGACY = re.compile(r"\{([A-Z][A-Z0-9_]*)\}")


def rewrite_placeholders(text: str, kind: str, line: bool = False) -> tuple[str, list[str]]:
    """（書き換えた文面, 新に当たるものが無い旧の差し込み）。

    LINE では `{{tenant_name}}` などの共通の差し込みだけでなく種別の差し込みも同じ。
    """
    table = {**COMMON, **BY_KIND.get(kind, {})}
    unresolved: list[str] = []

    def swap(match: re.Match) -> str:
        name = match.group(1)
        if name in table:
            return "{{" + table[name] + "}}"
        if name not in unresolved:
            unresolved.append(name)
        return match.group(0)

    return _LEGACY.sub(swap, text or ""), unresolved


def propose_bodies(rows: list[dict], table: str, key_column: str, column: str) -> list[tuple]:
    """HTML を含む本文だけ、プレーンテキストを提案する。"""
    out = []
    for row in rows:
        text = row.get(column) or ""
        if has_html(text):
            out.append((table, str(row[key_column]), column, plain_text(text), "HTML をプレーンテキストに直した（Q2）"))
    return out


def propose_mail(rows: list[dict]) -> list[tuple]:
    """移す自動メールの文面（`MAIL_KINDS`）の件名・本文。"""
    out = []
    for row in rows:
        kind = MAIL_KINDS.get(int(row["mail_type_id"]))
        if kind is None or (row.get("language_code") or "ja") != "ja":
            continue
        for column in ("title", "body"):
            text = row.get(column) or ""
            new, unresolved = rewrite_placeholders(text, kind)
            if new == text and not unresolved:
                continue
            if unresolved:
                memo = f"{kind}: 新に当たる差し込みが無い {', '.join('{' + u + '}' for u in unresolved)}。文面を決めて value に書く"
                out.append(("mail_setting", str(row["mail_setting_id"]), column, "", memo))
            else:
                out.append(("mail_setting", str(row["mail_setting_id"]), column, new, f"{kind}: 差し込みを新の書き方に直した（Q8）"))
    return out


def propose_line(rows: list[dict]) -> list[tuple]:
    out = []
    for row in rows:
        kind = LINE_KINDS.get(int(row["mail_type_id"]))
        if kind is None:
            continue
        text = row.get("message") or ""
        new, unresolved = rewrite_placeholders(text, kind, line=True)
        if new == text and not unresolved:
            continue
        key = str(row["mail_type_id"])
        if unresolved:
            memo = f"LINE {kind}: 新に当たる差し込みが無い {', '.join('{' + u + '}' for u in unresolved)}。文面を決めて value に書く"
            out.append(("line_message_mail_setting", key, "message", "", memo))
        else:
            out.append(("line_message_mail_setting", key, "message", new, f"LINE {kind}: 差し込みを新の書き方に直した（Q8）"))
    return out
