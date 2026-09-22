"""「入らない行」を、直し方ごとに分類する。

**大半は巻き添え。** 会員が1人移らないと、その会員の住所・通知設定・所属も移らない。
直す必要があるのは**大本だけ**で、そこを直せば巻き添えは消える。ここではそれを分けて出す。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .exclusions import Exclusion

#: 直し方
SQL = "sql"  # 旧 DB を直す（機械的に決まる）
OVERRIDE = "override"  # 運営が値を決める（補正データ）
NONE = "none"  # 大本を直せば消える（巻き添え）
REVIEW = "review"  # 判断材料が足りない。人が見る


@dataclass
class Task:
    """同じ直し方でまとめられる1件。"""

    kind: str
    title: str
    how: str
    hint: str
    keys: list[str] = field(default_factory=list)
    #: 補正データの雛形に出す列（`how == OVERRIDE` のとき）
    column: str = ""

    def __str__(self) -> str:
        mark = {SQL: "SQL", OVERRIDE: "運営判断", NONE: "対応不要", REVIEW: "要確認"}[self.how]
        return f"[{mark}] {self.title}: {len(self.keys)} 件"


def classify(exclusions: list[Exclusion], live_users: set[str]) -> list[Task]:
    """`live_users` は移行元に**実在する**会員の旧 ID。巻き添えと孤児を分けるために使う。"""
    buckets: dict[str, Task] = {}

    def add(kind: str, title: str, how: str, hint: str, key: str, column: str = "") -> None:
        task = buckets.setdefault(kind, Task(kind, title, how, hint, column=column))
        if key not in task.keys:
            task.keys.append(key)

    for item in exclusions:
        if item.step == "users" and item.kind == "NOT NULL" and item.column == "email":
            add(
                "email-missing",
                "メールアドレスが無い会員",
                OVERRIDE,
                "`users.email` は NOT NULL。1人に1つ、重複しないアドレスを決める",
                item.key,
                column="mail_add",
            )
        elif item.step == "users" and item.kind == "UNIQUE" and "email" in item.reason:
            add(
                "email-duplicate",
                "メールアドレスが重複している会員",
                OVERRIDE,
                "同じ人なら統合、別人なら別アドレスを決める（統合は学習記録も混ざる）",
                item.key,
                column="mail_add",
            )
        elif item.step == "users" and item.kind == "NOT NULL" and item.column == "role":
            add(
                "role-missing",
                "ロールが未設定の会員",
                OVERRIDE,
                "`users.role` は NOT NULL。旧 `role_id` の値を決める",
                item.key,
                column="role_id",
            )
        elif item.step == "users" and item.kind == "UNIQUE" and "login_id" in item.reason:
            add(
                "login-duplicate",
                "`login_id` が重複している会員",
                SQL,
                "**旧 user_id を後ろに足して一意にする。** 各組の最小 user_id はそのまま",
                item.key,
            )
        elif item.step == "line_links" and item.kind == "UNIQUE":
            add(
                "line-duplicate",
                "同じ LINE アカウントを共有している会員",
                OVERRIDE,
                "残す1名を決め、**それ以外の `line_id` を NULL にする**",
                item.key,
                column="line_id",
            )
        elif item.kind == "外部キー":
            if item.key.isdigit() and item.key not in live_users:
                add(
                    "orphan-row",
                    "移行元に会員が存在しない行",
                    SQL,
                    "会員が消えているので、割当だけ残っても参照できない。削除を提案する",
                    f"{item.step}:{item.key}",
                )
            elif item.key.isdigit():
                add(
                    "cascade",
                    "会員が移らないための巻き添え",
                    NONE,
                    "**大本（会員）を直せば消える。** ここを個別に直す必要は無い",
                    f"{item.step}:{item.key}",
                )
            else:
                add(
                    "fk-other",
                    "参照先が無い行（会員以外）",
                    REVIEW,
                    "親を先に移すか、対象外にするかを決める",
                    f"{item.step}:{item.key}",
                )
        else:
            add("other", f"その他（{item.step} / {item.reason}）", REVIEW, "内容を見て決める", item.key)

    order = {SQL: 0, OVERRIDE: 1, REVIEW: 2, NONE: 3}
    return sorted(buckets.values(), key=lambda t: (order[t.how], -len(t.keys)))
