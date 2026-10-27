"""課金（区分 04）の値の直しの提案（`fixups text` の一部）。docs/db/04-billing/migration-spec.md 0-2。

**移行ツールは値を作り替えない。** ここで提案し、補正データ（`overrides.csv`）に入れたものを移行ツールが読む。

| 対象 | 提案 | 決定 |
|---|---|---|
| 申込（`payment_application`）の会員 | 会員がいない申込（`user_id` が会員にいない）で、その申込の権限がすべて 1 人の会員に付いているなら、その会員に直す。権限の無い申込（会員が物理削除された不整合 #11）は出さない | Q8 |
"""

from __future__ import annotations


def propose_payers(apps: list[dict], members: set[int], holders: dict[int, set[int]]) -> list[tuple]:
    """`apps` は申込（`application_id` / `user_id`）、`holders` は申込 → 権限の会員。"""
    out = []
    for app in apps:
        user = int(app.get("user_id") or 0)
        if user in members:
            continue
        owners = holders.get(int(app["application_id"]), set())
        if not owners:
            continue  # 権限の無い申込（会員が物理削除された既知の不整合 #11）。決済は外部キーで一覧に出る
        if len(owners) == 1:
            [owner] = owners
            out.append(("payment_application", str(app["application_id"]), "user_id", str(owner),
                        f"申込の会員（{user}）がいない。権限はすべて会員 {owner} に付いている（Q8）"))
        else:
            out.append(("payment_application", str(app["application_id"]), "user_id", "",
                        f"申込の会員（{user}）がいない。権限の会員が {len(owners)} 人で決まらない。値を決めて value に書く"))
    return out


def collect(connection, tenant_id: int) -> list[tuple]:
    """旧 DB を読み、04 の提案を返す。**読むだけ。** 対象は決済として移す申込（カード・コンビニ・振込）。"""
    cursor = connection.cursor()

    def rows(sql: str) -> list[dict]:
        cursor.execute(sql, (tenant_id,))
        return [dict(r) for r in cursor.fetchall()]

    apps = rows("""SELECT application_id, user_id FROM payment_application
        WHERE tenant_id = %s AND payment_type IN (1, 2, 3) AND application_result <> 3""")
    members = {int(r["user_id"]) for r in rows("SELECT user_id FROM user WHERE tenant_id = %s")}
    holders: dict[int, set[int]] = {}
    for r in rows("""SELECT c.application_id, c.user_id FROM payment_item_lesson_authority c
        JOIN user u ON u.user_id = c.user_id WHERE u.tenant_id = %s AND c.application_id IS NOT NULL"""):
        holders.setdefault(int(r["application_id"]), set()).add(int(r["user_id"]))
    return propose_payers(apps, members, holders)
