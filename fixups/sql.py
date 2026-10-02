"""移行元 DB を直す SQL を作る。**実行はしない。**

生成した SQL は移行元（旧環境のローカル DB）を書き換える。中身を読んでから当てること。
本番の DB に当てる前に、ダンプを入れたローカルで結果を確かめる。
"""

from __future__ import annotations

from .plan import Task, user_of

HEADER = """-- 暫定対応: 移行元 (lw2) を直す SQL
-- 作成: python -m fixups sql
--
-- **このファイルは移行元 DB を書き換える。** 中身を読んでから当てること。
-- 当てたあと、移行ツールを再実行すれば、直った分が入る。
--
--   mysql -u<user> -p <db> < out/fixups.sql
--   python -m migrator run --dry-run --section foundation
"""


def build(tasks: list[Task], tenant_id: int, connection) -> str:
    """SQL 本文を組み立てる。対応できない種類は理由をコメントで残す。"""
    parts = [HEADER, "", "START TRANSACTION;", ""]
    for task in tasks:
        if task.kind == "login-duplicate":
            parts.append(_login_duplicates(task, tenant_id, connection))
        elif task.kind == "orphan-row":
            parts.append(_orphan_rows(task, tenant_id))
        else:
            parts.append(f"-- {task.title}: SQL では直せない（{task.how}）")
        parts.append("")
    parts.append("-- 問題なければ COMMIT、やり直すなら ROLLBACK")
    parts.append("COMMIT;")
    return "\n".join(parts)


def _login_duplicates(task: Task, tenant_id: int, connection) -> str:
    """重複した `login_id` を一意にする。

    **各組の最小 `user_id` はそのまま残す。** 生きているアカウント（先に作られたほう）が
    ログイン ID を保つようにするため。残りに `#<user_id>` を足す。
    """
    ids = [int(k) for k in task.keys]
    if not ids:
        return "-- login_id の重複: 対象なし"
    placeholders = ", ".join(["%s"] * len(ids))
    cursor = connection.cursor()
    cursor.execute(
        f"SELECT user_id, login_id FROM `user` WHERE tenant_id = %s AND user_id IN ({placeholders})",
        (tenant_id, *ids),
    )
    rows = [dict(r) for r in cursor.fetchall()]
    groups: dict[str, list[int]] = {}
    for row in rows:
        groups.setdefault(str(row["login_id"]), []).append(int(row["user_id"]))

    lines = ["-- login_id の重複を一意にする（各組の最小 user_id はそのまま）"]
    targets = []
    for login_id, members in sorted(groups.items()):
        keep = min(members)
        rest = sorted(set(members) - {keep})
        lines.append(f"--   {login_id!r}: {keep} を残し、{rest} に #<user_id> を足す")
        targets += rest
    if not targets:
        return "\n".join(lines + ["-- 変更なし"])
    lines.append(
        "UPDATE `user` SET login_id = CONCAT(login_id, '#', user_id)\n"
        f"WHERE tenant_id = {tenant_id} AND user_id IN ({', '.join(str(i) for i in targets)});"
    )
    return "\n".join(lines)


#: 会員が消えている行を削除するときの、**テナントで絞るための親テーブル**。
#: join を落とすと他テナントの行まで消える
ORPHAN_TABLES: dict[str, tuple[str, str, str]] = {
    # step 名 -> (子テーブル, 親テーブル, 結合条件)
    "user_attribute_values": ("user_attribute", "attribute", "c.attribute_id = p.attribute_id"),
    "tenant_group_members": ("user_group", "`group`", "c.group_id = p.group_id"),
}


def _orphan_rows(task: Task, tenant_id: int) -> str:
    by_step: dict[str, list[str]] = {}
    for key in task.keys:
        step, _, rest = key.partition(":")
        user_id = user_of(step, rest)
        if user_id is not None:
            by_step.setdefault(step, []).append(user_id)

    lines = ["-- 移行元に会員が存在しない行を消す"]
    for step, user_ids in sorted(by_step.items()):
        mapping = ORPHAN_TABLES.get(step)
        ids = ", ".join(sorted(set(user_ids), key=int))
        if not mapping:
            lines.append(f"-- {step}: 消し方が決まっていない。対象 user_id: {ids}")
            continue
        child, parent, on = mapping
        lines.append(
            f"DELETE c FROM `{child}` AS c\n"
            f"  INNER JOIN {parent} AS p ON {on}\n"
            f"WHERE p.tenant_id = {tenant_id} AND c.user_id IN ({ids});"
        )
    return "\n".join(lines)
