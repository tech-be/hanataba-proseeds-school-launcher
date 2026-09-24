"""フェーズの選び方（`--phase` / `--section` の解釈）。

**指定は `区分.フェーズ番号`。** 区分が増えても番号がずれないようにするため。

    --phase foundation.4          1つ
    --phase foundation.1-3        区分の中の範囲
    --phase common.0 --phase foundation.1
    --section foundation          区分まるごと
    --phase 4                     区分が1つに決まるときだけ許す（後方互換）
"""

from __future__ import annotations

from ..errors import MigrationError
from .base import Phase, Section
from .registry import find_section, ordered_phases


def _numbers(spec: str) -> list[int]:
    if "-" in spec:
        start, _, end = spec.partition("-")
        return list(range(int(start), int(end) + 1))
    return [int(spec)]


def resolve(sections: list[Section], phase_specs: list[str], section_keys: list[str]) -> list[Phase]:
    """指定を実行対象のフェーズ列に変える。**実行順に並べて返す。**"""
    order = ordered_phases(sections)
    if not phase_specs and not section_keys:
        return order

    wanted: set[str] = set()

    for key in section_keys:
        section = find_section(sections, key)
        _reject_pending(section)
        if not section.phases:
            raise MigrationError(f"{section.key}: 実行できるフェーズが無い")
        wanted.update(p.key for p in section.phases)

    for spec in phase_specs:
        for part in str(spec).split(","):
            part = part.strip()
            if not part:
                continue
            if "." in part:
                section_key, _, number_spec = part.partition(".")
                section = find_section(sections, section_key)
                _reject_pending(section)
                for number in _numbers(number_spec):
                    phase = section.phase(number)
                    if phase is None:
                        raise MigrationError(
                            f"{section_key}.{number} は無い。使えるのは: "
                            + ", ".join(p.key for p in section.phases)
                        )
                    wanted.add(phase.key)
            else:
                wanted.update(_unqualified(sections, _numbers(part)))

    return [p for p in order if p.key in wanted]


def _unqualified(sections: list[Section], numbers: list[int]) -> list[str]:
    """区分を省いた指定（`--phase 4`）を解く。

    **その番号を持つ区分が1つに決まるときだけ許す。** 複数あるなら曖昧なので止める。
    """
    keys: list[str] = []
    for number in numbers:
        matched = [s.phase(number) for s in sections if not s.pending and s.phase(number)]
        if not matched:
            raise MigrationError(f"フェーズ {number} を持つ区分が無い")
        if len(matched) > 1:
            raise MigrationError(
                f"フェーズ {number} が複数の区分にある: "
                + ", ".join(p.key for p in matched if p)
                + "。`--phase 区分.番号` の形で指定すること"
            )
        keys.append(matched[0].key)  # type: ignore[union-attr]
    return keys


def _reject_pending(section: Section) -> None:
    if section.pending:
        raise MigrationError(
            f"{section.key}（{section.title}）はまだ流せない: {section.pending_reason}。"
            f"{section.pending_next}（{section.doc}）"
        )
