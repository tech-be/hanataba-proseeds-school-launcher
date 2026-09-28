"""CLI。

    python -m migrator plan                  実行計画を出す（DB 接続なしで動く）
    python -m migrator doctor                接続と前提を確認する（書き込みなし）
    python -m migrator preflight             事前検査だけ通す
    python -m migrator run --dry-run                    全フェーズを流す（書き込みなし）
    python -m migrator run --dry-run --phase foundation.4   基盤の会員だけ dry-run する
    python -m migrator run --phase foundation.1-3           基盤のフェーズ1〜3を流す
    python -m migrator run --section foundation             基盤まるごと
    python -m migrator verify                投入後の検証（移行元から作り直して移行先と照合する）
    python -m migrator verify --section enrollment      受講だけ照合する
"""

from __future__ import annotations

import argparse
import sys

from . import __version__, config as config_module, reporting
from .context import build_context
from .db import connect as connect_module
from .db.source import SourceDatabase
from .db.target import TargetDatabase
from .errors import MigrationError
from .logging_setup import setup
from .overrides import Overrides
from .phases.registry import bootstrap, build_sections, check_schema, resolve_tenant_id
from .phases.selection import resolve
from .validation import postcheck, preflight, reconcile


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="migrator", description="lw2 → school-launcher データ移行")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--config", default=config_module.DEFAULT_CONFIG, help="設定ファイル")
    parser.add_argument("--log-level", default="INFO")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("plan", help="実行計画を出す（DB 接続なし）")
    sub.add_parser("doctor", help="接続と前提を確認する（書き込みなし）")
    sub.add_parser("preflight", help="事前検査だけ通す")
    verify = sub.add_parser(
        "verify", help="投入後の検証（移行元から作り直して移行先と照合する。書き込みなし）"
    )
    _add_selection(verify)

    run = sub.add_parser("run", help="移行を実行する")
    run.add_argument("--dry-run", action="store_true", help="書き込まず、実行内容だけ出す")
    _add_selection(run)
    run.add_argument("--skip-preflight", action="store_true", help="事前検査を飛ばす（非推奨）")
    return parser


def _add_selection(parser: argparse.ArgumentParser) -> None:
    """`run` と `verify` で**同じ指定**が使えるようにする。"""
    parser.add_argument(
        "--phase",
        action="append",
        default=[],
        metavar="区分.番号",
        help="このフェーズだけ流す（例: --phase foundation.4 / --phase foundation.1-3）",
    )
    parser.add_argument(
        "--section",
        action="append",
        default=[],
        metavar="区分",
        help="この区分をまるごと流す（例: --section foundation）",
    )


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    logger = setup(args.log_level)
    sections = build_sections()

    if args.command == "plan":
        print(reporting.plan(sections))
        return 0

    try:
        config = config_module.load(args.config)
        dry_run = bool(getattr(args, "dry_run", False))

        source_conn = connect_module.connect(config.source_dsn) if config.source_dsn else None
        target_conn = connect_module.connect(config.target_dsn) if config.target_dsn else None
        overrides = Overrides.load(config.overrides_path)
        source = (
            SourceDatabase(source_conn, config.tenant.legacy_id, overrides)
            if source_conn
            else None
        )
        if args.command == "verify":
            # **照合は書かない。** 行は取っておくだけで、移行先には何も送らない
            target = reconcile.RecordingTarget(target_conn)
        else:
            target = TargetDatabase(target_conn, dry_run=dry_run)
        ctx = build_context(config, source, target, logger)
        ctx.verifying = args.command == "verify"

        if args.command == "doctor":
            from . import doctor

            text, ok = doctor.summarize(doctor.run(config))
            print(text)
            return 0 if ok else 1

        if args.command == "preflight":
            for result in preflight.run_all(ctx):
                print(result)
            return 0

        selected = resolve(sections, args.phase, args.section)
        if not selected:
            logger.error("指定に当てはまるフェーズが無い")
            return 1

        # 途中のフェーズから始める場合は、tenant_id と完了印をここで用意する
        bootstrap(ctx, sections, selected)
        ctx.selected = {phase.key for phase in selected}
        # 途中から流しても、選んだ区分の追加スキーマは先に確かめる
        check_schema(ctx, selected)

        if args.command == "verify":
            return _verify(ctx, sections, selected)

        # 事前検査は抽出の前に通す。フェーズ2以降だけを流すときは、
        # 旧データを読む Step が含まれるときだけ通す（マスタ追加だけなら不要）
        needs_source = any(step.source_table for phase in selected for step in phase.steps)
        if not args.skip_preflight and needs_source:
            for result in preflight.run_all(ctx):
                logger.info("%s", result)

        for phase in selected:
            phase.run(ctx)
        print(reporting.summary(ctx))
        return 0

    except MigrationError as exc:
        logger.error("%s", exc)
        return 1
    finally:
        pass


def _verify(ctx, sections, selected) -> int:
    """照合してから、テナント単位の事後検証を通す。**差が1件でもあれば 1 を返す。**"""
    # 制約に当たる行の一覧は `run` の作業リストなので、照合では別の場所に出す
    from .validation.exclusions import ExclusionLog

    ctx._exclusions = ExclusionLog(ctx.config.work_dir / "verify", ctx.logger)
    result = reconcile.reconcile(ctx, selected, sections)
    print(result.summary())

    if not ctx.tenant_id.resolved:
        ctx.tenant_id.resolve(resolve_tenant_id(ctx))
    postcheck.target_tenant_once(ctx)
    postcheck.no_platform_admin(ctx)
    postcheck.email_unique(ctx)
    print("  テナント・管理者・メールの検証 OK")
    return 0 if result.ok else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
