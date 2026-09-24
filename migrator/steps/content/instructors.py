"""ondemand.2 — 代理講師（A21）。

**暫定対応。** `courses.instructor_id` は NOT NULL だが、lw2 には講座単位の講師が無い
（`instructor_set_lesson` は担当範囲であって、講座の講師ではない）。
対応表が届くまでの仮置きとして、**講師1人分の `users` 行を作って全講座に割り当てる**。

対応表を受け取ったら付け替え、**代理講師のままの講座が0件になったことを確認する**。
"""

from __future__ import annotations

from ...context import RunContext
from ...core.records import Record
from ..base import Step

#: 代理講師を引くためのキー。`courses` 側と**同じ値**を使う
PROXY_KEY = "proxy-instructor"


class ProxyInstructorStep(Step):
    """代理講師の `users` 行を1件作る。

    **パスワードは空にする**（ログインさせない）。メールは `.invalid` ドメインにして、
    実在のアドレスと衝突しないようにする。
    """

    name = "content.proxy_instructor"
    description = "代理講師の会員を1件作る（暫定。対応表が届いたら付け替える）"
    source_table = ""  # 旧データを読まない。新規に作る行
    target_table = "users"
    depends_on = ("tenant",)

    def extract(self, ctx: RunContext) -> list[dict]:
        return [{}]

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        return [
            Record(
                table="users",
                values={
                    "id": ctx.ulid.for_row("user", PROXY_KEY),
                    "tenant_id": tenant_id,
                    "login_id": None,
                    "email": f"{PROXY_KEY}@lw2.invalid",
                    "mobile_email": None,
                    # **ログインさせない。** 空のハッシュはどのパスワードとも一致しない
                    "password_hash": "",
                    "name": "（講師未設定）",
                    "name_last": None,
                    "name_first": None,
                    "role": "instructor",
                    "status": "inactive",
                    "is_valid": False,
                    "admin_memo": "移行の暫定対応で作成。講座→講師の対応表を受け取ったら付け替える",
                },
                natural_key=("tenant_id", "email"),
                source_key=PROXY_KEY,
            )
        ]

    def run(self, ctx: RunContext):
        result = super().run(ctx)
        ctx.logger.warning(
            "代理講師を作成した（暫定）。**対応表を受け取ったら付け替え、"
            "代理講師のままの講座が0件になったことを確認する**"
        )
        return result


def build() -> list[Step]:
    return [ProxyInstructorStep()]
