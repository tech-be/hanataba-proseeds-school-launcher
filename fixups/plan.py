"""「入らない行」を、直し方ごとに分類する。

**大半は巻き添え。** 会員が1人移らないと、その会員の住所・通知設定・所属も移らない。
直す必要があるのは**大本だけ**で、そこを直せば巻き添えは消える。ここではそれを分けて出す。

**「巻き添え」と呼べるのは、参照先が会員のときだけ。** 外部キー違反の旧 ID が数値でも
会員とは限らない（`ondemand.quizzes` の `lesson_id` は見出しユニットを指す）。
**理由に載っている列名で判定する。**
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .exclusions import Exclusion


#: 一覧のキーが「会員 ID」だけでない Step。キーを ":" で区切ったときの会員 ID の位置。
#: **Step の `source_key` と合わせること。** 会員1人に複数行ある表は、会員 ID と別の ID を組にしている
USER_KEY_POSITION: dict[str, int] = {
    "user_attribute_values": 1,  # 属性 ID:会員 ID
    "enrollment.survey_submission_log": 1,  # ユニット ID:会員 ID
    "billing.ticket_grants": 0,  # 会員 ID:チケット ID
    "enrollment.certificates": 0,  # 会員 ID:対象 ID
    "enrollment.certificate_events": 0,
    "enrollment.lesson_progress": 0,  # 会員 ID:ユニット ID
    "enrollment.rights": 0,  # 会員 ID:講座 ID
}

#: 会員を参照するが、**一覧のキーが会員ではない旧 ID** の Step（申込・予約・記録などの ID）。
#: キーを会員 ID とみなすと、たまたま同じ番号の会員の有無で分類が変わってしまう
NON_USER_KEY_STEPS: frozenset[str] = frozenset({
    "billing.assign_logs",
    "billing.monthly_allowances",
    "billing.payments",
    "billing.receipts",
    "billing.ticket_ledger",
    "enrollment.live_reservations",
    "enrollment.live_reviews",
    "enrollment.quiz_attempts",
    "enrollment.survey_responses",
    "enrollment.submissions",
    "support.advice_notes",
    "support.scout_follows",
    "support.usage_snapshot_users",
})


def user_of(step: str, key: str) -> str | None:
    """一覧のキーから会員の旧 ID を取り出す。キーから会員が分からなければ None。"""
    if step in NON_USER_KEY_STEPS:
        return None
    parts = key.split(":")
    position = USER_KEY_POSITION.get(step)
    if position is not None and len(parts) > position:
        candidate = parts[position]
    elif len(parts) == 1:
        candidate = key
    else:
        return None
    return candidate if candidate.isdigit() else None

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
        elif item.kind == "外部キー" and item.column != "user_id":
            # **会員以外の参照先。** 旧 ID が数値でも会員とは限らない
            # （`ondemand.quizzes` の `lesson_id` は見出しユニットを指す、など）
            add(
                "fk-other",
                "参照先が無い行（会員以外）",
                REVIEW,
                "親を先に移すか、対象外にするかを決める",
                f"{item.step}:{item.key}",
            )
        elif item.kind == "外部キー":
            user = user_of(item.step, item.key)
            if user is not None and user not in live_users:
                add(
                    "orphan-row",
                    "移行元に会員が存在しない行",
                    SQL,
                    "会員が消えているので、割当だけ残っても参照できない。削除を提案する",
                    f"{item.step}:{item.key}",
                )
            elif user is not None:
                add(
                    "cascade",
                    "会員が移らないための巻き添え",
                    NONE,
                    "**大本（会員）を直せば消える。** ここを個別に直す必要は無い",
                    f"{item.step}:{item.key}",
                )
            else:
                # 参照先は会員だが、一覧のキーから会員が分からない（申込 ID などで並ぶ Step）
                add(
                    "user-unknown",
                    "会員を参照できない行（キーが会員 ID ではない）",
                    REVIEW,
                    "旧 DB で、その行の会員が残っているかを確かめる",
                    f"{item.step}:{item.key}",
                )
        else:
            # **理由ごとに分ける。** 1つの束にすると、見出しに出る理由が最初の1件だけになり
            # 「video_url が NOT NULL」の束に未提出の課題が紛れ込む
            add(
                f"other:{item.step}:{item.reason}",
                f"その他（{item.step} / {item.reason}）",
                REVIEW,
                "内容を見て決める",
                item.key,
            )

    order = {SQL: 0, OVERRIDE: 1, REVIEW: 2, NONE: 3}
    return sorted(buckets.values(), key=lambda t: (order[t.how], -len(t.keys)))
