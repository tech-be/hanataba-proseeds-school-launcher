"""実行結果のまとめ。"""

from __future__ import annotations

from .context import RunContext


def summary(ctx: RunContext) -> str:
    lines = ["", "=== 実行結果 ==="]
    if ctx.dry_run:
        lines.append("（dry-run: 書き込みはしていない）")
    total = 0
    for result in ctx.results:
        lines.append(f"  {result}")
        for note in result.notes:
            lines.append(f"      - {note}")
        total += result.loaded
    lines.append(f"  合計 {total} 行")
    excluded = sum(r.excluded for r in ctx.results)
    if excluded:
        lines.append(
            f"  制約に当たって移さない行: {excluded} 行 → {ctx.exclusions().path}"
        )
        lines.append("  （暫定対応で移行元を直してから、同じコマンドで再実行すれば入る）")
    if ctx.dry_run and ctx.target.statements:
        lines.append("")
        lines.append("=== 実行される SQL ===")
        lines.extend(f"  {s}" for s in ctx.target.statements)
    return "\n".join(lines)


def plan(sections) -> str:
    """実行計画。**指定に使う識別子（区分.番号）をそのまま出す。**"""
    lines = ["=== 実行計画 ===", "指定は `区分.フェーズ番号`（例: --phase foundation.4 / --section foundation）", ""]
    for section in sorted(sections, key=lambda s: (s.order, s.key)):
        head = f"[{section.order}] {section.key:<12} {section.title}"
        if section.pending:
            lines.append(f"{head}  — {section.pending_reason}（{section.doc}）")
            continue
        lines.append(head)
        for phase in sorted(section.phases, key=lambda p: p.number):
            lines.append(f"  {phase.key:<14} {phase.name} — {phase.description}")
            for step in phase.steps:
                src = step.source_table or "—"
                lines.append(f"      {step.name:<30} {src:<20} → {step.target_table or '—'}")
    return "\n".join(lines)
