"""区分とフェーズの並び。

**2つの軸がある。**

- **区分をまたぐ順序**（docs/migration-spec.md 1章）: 共通 → 基盤 → オンデマンド / 運営 → …
- **区分の中の順序**（docs/db/NN-*/migration-spec.md 2章）: テナント → マスタ → 定義 → 会員 → …

識別子は `foundation.2` のように**区分.フェーズ番号**。区分が増えても番号がずれない。

```
common.0       スキーマ確認（追加は移行直前に migration で実施）
foundation.1   マスタの追加値           ← FK の参照先をそろえる
foundation.2   tenants の1行            ← ここで tenant_id が決まる
foundation.3   テナント設定・定義系
foundation.4   会員
foundation.5   会員に紐づくもの
ondemand.*     未作成（突き合わせに修正方法の列が無い）
...
```

`login_history` は純ログのため移行しない。フェーズ表に現れない。
"""

from __future__ import annotations

from ..errors import DependencyError, MigrationError
from ..steps import auth_config, masters, org, tenant_config, user_related, users
from ..steps.schema import SchemaCheckStep
from ..steps.tenant import TenantStep
from ..validation import postcheck
from .base import Phase, Section


def build_sections() -> list[Section]:
    """区分の一覧。**`order` が区分をまたぐ順序。**"""
    return [
        Section(
            key="common",
            order=0,
            title="共通",
            doc="docs/migration-spec.md",
            phases=[
                Phase(
                    number=0,
                    name="スキーマ確認",
                    description="追加スキーマ（各区分の追加一覧）が入っているかを確認する",
                    steps=[SchemaCheckStep()],
                )
            ],
        ),
        Section(
            key="foundation",
            order=1,
            title="基盤",
            doc="docs/db/01-foundation/migration-spec.md",
            phases=[
                # マスタが先。FK の参照先をすべてそろえてから、それを使う行を作る
                Phase(1, "マスタ", "user_roles / tenant_statuses / auth_methods / email_kinds に不足値を足す",
                      steps=masters.build()),
                Phase(2, "テナント", "tenants の1行を作り、tenant_id を確定させる",
                      steps=[TenantStep()], checks=(postcheck.target_tenant_once,)),
                Phase(3, "テナント設定・定義",
                      "上限・プロフィール項目・グループ・属性・認証設定を移す",
                      steps=tenant_config.build() + org.definitions() + auth_config.build()),
                Phase(4, "会員", "users と対応表を移す",
                      steps=users.build(),
                      checks=(postcheck.no_platform_admin, postcheck.email_unique)),
                Phase(5, "会員に紐づくもの",
                      "住所・プロフィール値・公開制限・割当・通知設定・LINE 紐付けを移す",
                      steps=user_related.build() + org.assignments()),
            ],
        ),
        # --- 以降は突き合わせに `修正方法` の列が無く、移行仕様が未作成 ---
        Section("ondemand", 2, "オンデマンド", "docs/db/02-ondemand/review.md", pending=True),
        Section("operations", 2, "運営", "docs/db/06-operations/review.md", pending=True),
        Section("live", 3, "ライブ", "docs/db/03-live/review.md", pending=True),
        Section("enrollment", 3, "受講", "docs/db/04-enrollment/review.md", pending=True),
        Section("billing", 3, "課金", "docs/db/05-billing/review.md", pending=True),
        Section("career", 4, "就職支援", "docs/db/07-career/review.md", pending=True),
    ]


def ordered_phases(sections: list[Section]) -> list[Phase]:
    """全区分のフェーズを、実行順に並べて返す。"""
    phases: list[Phase] = []
    for section in sorted(sections, key=lambda s: (s.order, s.key)):
        phases.extend(sorted(section.phases, key=lambda p: p.number))
    return phases


def find_section(sections: list[Section], key: str) -> Section:
    section = next((s for s in sections if s.key == key), None)
    if section is None:
        raise MigrationError(
            f"区分 {key!r} が無い。使えるのは: " + ", ".join(s.key for s in sections)
        )
    return section


def bootstrap(ctx, sections: list[Section], selected: list[Phase]) -> None:
    """**途中のフェーズから始められるようにする。**

    選んだフェーズより前のフェーズを「完了済み」として扱い、`tenant_id` を用意する。
    実際に投入されているかは**確認しない**（確認は `verify` の仕事）。
    """
    if not selected:
        return
    order = ordered_phases(sections)
    keys = [p.key for p in order]
    start = min(keys.index(p.key) for p in selected)
    if start == 0:
        return

    skipped = order[:start]
    for phase in skipped:
        for step in phase.steps:
            ctx.completed.add(step.name)
        ctx.completed.add(phase.key)
    if skipped:
        ctx.logger.warning(
            "%s から流す。%s は完了済みとして扱う（投入されているかは確認しない）",
            selected[0].key,
            ", ".join(p.key for p in skipped),
        )

    # tenants の行を作るフェーズより後から始めるなら tenant_id が要る。
    # マスタだけを流すときは tenant_id を使わないので引き当てない
    if _needs_tenant_id(order, selected) and not ctx.tenant_id.resolved:
        ctx.tenant_id.resolve(resolve_tenant_id(ctx))
        ctx.logger.info("tenant_id = %s", ctx.tenant_id.value)


def _needs_tenant_id(order: list[Phase], selected: list[Phase]) -> bool:
    """選んだフェーズが `tenant_id` を要るか。

    `tenants` の行を作るフェーズが選択に含まれていれば、そこで採番されるので不要。
    含まれておらず、**それより後のフェーズを流す**なら引き当てが要る。
    """
    tenant_index = next(
        (i for i, p in enumerate(order) if any(s.name == "tenant" for s in p.steps)), None
    )
    if tenant_index is None:
        return False
    keys = [p.key for p in order]
    if order[tenant_index] in selected:
        return False
    return max(keys.index(p.key) for p in selected) > tenant_index


def resolve_tenant_id(ctx) -> str:
    """`tenants.id` を確定させる。**採番はしない**（foundation.1 の仕事）。

    1. 新環境に行があればその `id`（正本）
    2. 無ければ旧 `tenant` 行から決定論 ULID を組み立てる（foundation.1 と同じ値）
    """
    from ..steps.tenant import SOURCE_COLUMNS, created_at_ms

    rows = ctx.target.query("SELECT id FROM tenants WHERE slug = %s", (ctx.config.tenant.slug,))
    if rows:
        return str(rows[0]["id"])

    source = ctx.require_source()
    legacy = source.fetch_for_tenant("tenant", SOURCE_COLUMNS)
    if not legacy:
        raise DependencyError(
            "tenant_id を決められない。新環境に tenants の行が無く、旧 tenant も読めない。"
            "tenants の行を作るフェーズ（foundation.2）から流すこと"
        )
    ctx.logger.warning(
        "新環境に tenants の行が無いので、旧 tenant から決定論 ULID を組み立てて使う"
        "（dry-run 用。実投入は foundation.2 から流すこと）"
    )
    row = legacy[0]
    return ctx.ulid.for_row("tenant", row["tenant_id"], created_at_ms(row.get("regist_date")))
