"""暫定対応ツールの入口。

```bash
python -m fixups plan        # 何を直せばよいかを分類する
python -m fixups sql         # 旧 DB を直す SQL を出す（実行はしない）
python -m fixups template    # 運営が値を決める雛形を出す
python -m fixups check       # 書いてもらった値を検査する
```
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from migrator import config as config_module
from migrator.db import connect as connect_module
from migrator.errors import MigrationError
from migrator.logging_setup import setup
from migrator.overrides import Overrides

from . import check as check_module
from . import exclusions, plan, sql, templates


def _users(connection, tenant_id: int) -> dict[str, dict]:
    """移行元の会員を `user_id` 引きで返す（雛形の memo と検査に使う）。"""
    cursor = connection.cursor()
    cursor.execute(
        "SELECT user_id, login_id, name_sei, name_mei, mail_add, line_id, role_id, del_chk "
        "FROM `user` WHERE tenant_id = %s",
        (tenant_id,),
    )
    return {str(row["user_id"]): dict(row) for row in cursor.fetchall()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser("fixups", description="暫定対応ツール（移行ツールとは別）")
    parser.add_argument("command", choices=("plan", "sql", "template", "check"))
    parser.add_argument("--config", default=config_module.DEFAULT_CONFIG)
    parser.add_argument("--exclusions", default=str(exclusions.DEFAULT_PATH))
    parser.add_argument("--out", default=None, help="出力先（sql / template）")
    parser.add_argument(
        "--propose",
        action="store_true",
        help="template: 機械的に決まる値を埋める（**提案であって決定ではない**。読んで直す）",
    )
    args = parser.parse_args(argv)

    logger = setup()
    try:
        config = config_module.load(args.config)
        connection = connect_module.connect(config.source_dsn)
        tenant_id = config.tenant.legacy_id
        users = _users(connection, tenant_id)

        if args.command == "check":
            overrides = Overrides.load(config.overrides_path)
            findings = check_module.run(overrides, users, tenant_id)
            for finding in findings:
                print(finding)
            return 0 if all(f.ok for f in findings) else 1

        items = exclusions.load(args.exclusions)
        tasks = plan.classify(items, set(users))

        if args.command == "plan":
            print(_plan_text(items, tasks))
            return 0
        if args.command == "sql":
            path = Path(args.out or config.work_dir / "fixups.sql")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(sql.build(tasks, tenant_id, connection), encoding="utf-8")
            logger.info("%s に書いた。**中身を読んでから当てる**", path)
            return 0
        if args.command == "template":
            path = Path(args.out or config.overrides_path)
            if path.exists():
                logger.error("%s がすでにある。消すか --out で別名にする（上書きしない）", path)
                return 1
            written = templates.build(tasks, users, path, propose=args.propose)
            if args.propose:
                logger.info(
                    "%s に %d 行を書いた。**提案値が入っているので、中身を読んでから使う**",
                    path,
                    written,
                )
            else:
                logger.info("%s に %d 行の雛形を書いた。value 列を埋める", path, written)
            return 0
    except (MigrationError, FileNotFoundError) as exc:
        logger.error("%s", exc)
        return 1
    finally:
        pass
    return 0


def _plan_text(items, tasks) -> str:
    lines = [f"=== 入らない行 {len(items)} 件の内訳 ===", ""]
    for task in tasks:
        lines.append(str(task))
        lines.append(f"      {task.hint}")
        lines.append(f"      例: {task.keys[:5]}")
        lines.append("")
    lines.append("次にすること:")
    lines.append("  SQL      → python -m fixups sql      （出した SQL を読んでから移行元に当てる）")
    lines.append("  運営判断 → python -m fixups template （value 列を埋めて python -m fixups check）")
    lines.append("  対応不要 → 大本を直して移行ツールを再実行すれば消える")
    return "\n".join(lines)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
