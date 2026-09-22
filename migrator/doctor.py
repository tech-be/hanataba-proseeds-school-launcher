"""接続と前提の確認（`python -m migrator doctor`）。

**移行を始める前に、繋がるか・何が入っているかを見る。** 書き込みは一切しない。
"""

from __future__ import annotations

from dataclasses import dataclass

from .config import Config
from .db import connect as connect_module
from .errors import MigrationError
from .steps.schema import PLANNED_SCHEMA, REQUIRED_SCHEMA


@dataclass
class Finding:
    """確認の結果1件。

    `todo=True` は「移行は止まらないが、残っている作業」。**OK と混ぜない** —
    残作業を OK と出すと、やり残しに気づけない。
    """

    label: str
    ok: bool
    detail: str = ""
    todo: bool = False

    def __str__(self) -> str:
        mark = "TODO" if self.todo else ("OK " if self.ok else "NG ")
        return f"[{mark}] {self.label}{': ' + self.detail if self.detail else ''}"


def _dsn_summary(dsn: str) -> str:
    """パスワードを伏せて接続先だけ出す。"""
    from urllib.parse import urlparse

    parsed = urlparse(dsn)
    host = parsed.hostname or "?"
    port = parsed.port or 3306
    db = (parsed.path or "/").lstrip("/")
    return f"{parsed.username or '?'}@{host}:{port}/{db}"


def run(config: Config) -> list[Finding]:
    findings: list[Finding] = []
    findings += _source(config)
    findings += _target(config)
    return findings


def _source(config: Config) -> list[Finding]:
    if not config.source_dsn:
        return [Finding("移行元 SOURCE_DB_URL", False, ".env か環境変数に設定する")]
    out = [Finding("移行元 SOURCE_DB_URL", True, _dsn_summary(config.source_dsn))]
    try:
        conn = connect_module.connect(config.source_dsn)
    except Exception as exc:  # 接続できないこと自体が結果
        out.append(Finding("移行元に接続", False, str(exc)[:120]))
        return out
    try:
        cur = conn.cursor()
        cur.execute("SELECT VERSION() AS v")
        out.append(Finding("移行元に接続", True, str(list(cur.fetchall())[0]["v"])))

        cur.execute("SELECT COUNT(*) AS n FROM tenant")
        total = int(list(cur.fetchall())[0]["n"])
        cur.execute("SELECT COUNT(*) AS n FROM tenant WHERE tenant_id = %s", (config.tenant.legacy_id,))
        mine = int(list(cur.fetchall())[0]["n"])
        out.append(
            Finding(
                f"移行対象テナント（tenant_id={config.tenant.legacy_id}）",
                mine == 1,
                f"該当 {mine} 件 / DB 全体 {total} テナント",
            )
        )

        cur.execute("SELECT COUNT(*) AS n FROM user WHERE tenant_id = %s", (config.tenant.legacy_id,))
        out.append(Finding("移行対象の会員数", True, f"{list(cur.fetchall())[0]['n']} 名"))
    except Exception as exc:
        out.append(Finding("移行元の読み出し", False, str(exc)[:160]))
    finally:
        conn.close()
    return out


def _target(config: Config) -> list[Finding]:
    if not config.target_dsn:
        return [Finding("移行先 TARGET_DB_URL", False, ".env か環境変数に設定する")]
    out = [Finding("移行先 TARGET_DB_URL", True, _dsn_summary(config.target_dsn))]
    try:
        conn = connect_module.connect(config.target_dsn)
    except Exception as exc:
        out.append(Finding("移行先に接続", False, str(exc)[:120]))
        return out
    try:
        cur = conn.cursor()
        cur.execute("SELECT VERSION() AS v")
        out.append(Finding("移行先に接続", True, str(list(cur.fetchall())[0]["v"])))

        # **テナントの総数では判断しない。** デモ seed のテナントが居るのが正常
        cur.execute("SELECT id, name FROM tenants WHERE slug = %s", (config.tenant.slug,))
        mine = list(cur.fetchall())
        if not mine:
            out.append(
                Finding(f"移行先の {config.tenant.slug}", True, "まだ無い（foundation.2 で作る）")
            )
        elif len(mine) == 1:
            out.append(Finding(f"移行先の {config.tenant.slug}", True, f"1 件（id={mine[0]['id']}）"))
            cur.execute(
                "SELECT slug FROM tenants WHERE name = %s AND slug <> %s",
                (mine[0]["name"], config.tenant.slug),
            )
            dup = [str(r["slug"]) for r in cur.fetchall()]
            if dup:
                out.append(
                    Finding("同名テナントの重複", False, f"別 slug に同じ name がある: {dup}")
                )
        else:
            out.append(
                Finding(f"移行先の {config.tenant.slug}", False, f"{len(mine)} 件ある（1件であること）")
            )

        cur.execute("SELECT COUNT(*) AS n FROM tenants")
        total = int(list(cur.fetchall())[0]["n"])
        # **リセット＋シード投入が移行の前提条件。** 0 件は「シードが入っていない」
        # であって初期状態ではない（事前検査もここで止まる）
        out.append(
            Finding(
                "移行先がリセット＋シード済み",
                total > 0,
                f"シードのテナント {total} 件"
                if total
                else "テナントが1件も無い。`make reseed` を `make seed` まで通す"
                "（btoc-backend / career-backend / skill-passport が起動している必要がある）",
            )
        )

        lacking = _missing_schema(cur, REQUIRED_SCHEMA)
        out.append(
            Finding(
                f"追加スキーマ（移行に必須 {len(REQUIRED_SCHEMA)} 件）",
                not lacking,
                "すべて入っている"
                if not lacking
                else f"{len(lacking)} 件未適用: "
                + ", ".join(lacking[:6])
                + (" ほか" if len(lacking) > 6 else ""),
            )
        )
        planned = _missing_schema(cur, PLANNED_SCHEMA)
        if planned:
            out.append(
                Finding(
                    "追加スキーマ（移行では使わない）",
                    True,
                    f"{len(planned)} 件未適用: "
                    + ", ".join(planned)
                    + "。移行は止まらないが、cutover 後に失敗ログインを記録できない",
                    todo=True,
                )
            )
    except Exception as exc:
        out.append(Finding("移行先の読み出し", False, str(exc)[:160]))
    finally:
        conn.close()
    return out


def _missing_schema(cursor, entries) -> list[str]:
    missing = []
    for entry in entries:
        table, column = entry[0], entry[1]
        if column is None:
            cursor.execute(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema = DATABASE() AND table_name = %s LIMIT 1",
                (table,),
            )
        else:
            cursor.execute(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_schema = DATABASE() AND table_name = %s AND column_name = %s LIMIT 1",
                (table, column),
            )
        if not list(cursor.fetchall()):
            missing.append(f"{table}.{column}" if column else table)
    return missing


def summarize(findings: list[Finding]) -> tuple[str, bool]:
    ok = all(f.ok for f in findings)
    todos = [f for f in findings if f.todo]
    lines = [str(f) for f in findings]
    lines.append("")
    if not ok:
        lines.append("NG があるので、移行を始める前に解消する")
    elif todos:
        lines.append(f"移行は開始できる。ただし TODO が {len(todos)} 件ある（移行後に対応する）")
    else:
        lines.append("すべて OK")
    return "\n".join(lines), ok
