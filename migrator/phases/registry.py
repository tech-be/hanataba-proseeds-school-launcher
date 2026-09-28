"""区分とフェーズの並び。

**2つの軸がある。**

- **区分をまたぐ順序**（docs/migration-spec.md 1章）: 共通 → 基盤 → オンデマンド / 運営 → …
- **区分の中の順序**（docs/db/NN-*/migration-spec.md 2章）: テナント → マスタ → 定義 → 会員 → …

識別子は `foundation.1` のように**区分.フェーズ番号**。区分が増えても番号がずれない。

**区分とフェーズは移行計画の5グループ / 20項目に対応する。**

```
common.0       スキーマ確認（追加は移行直前に migration で実施）
foundation.1   マスター      ← マスタ・テナント・テナント設定。ここで tenant_id が決まる
foundation.2   ユーザ
content.1-4    オンデマンド講座 / テスト定義・課題定義 / アンケート定義 / ライブ講座
enrollment.1-7 受講権限 / 学習履歴 / テスト結果 / 課題提出 / アンケート回答 / ライブ予約 / 修了証
billing.1-3    チケット / 決済 / 帳票
support.1-7    LINE / クーポン / お知らせ / 問い合わせ / ファイル / 就業支援 / コミュニティ
```

`login_history` は純ログのため移行しない。フェーズ表に現れない。
"""

from __future__ import annotations

from ..errors import DependencyError, MigrationError
from ..steps import auth_config, masters, org, tenant_config, user_related, users
from ..steps.billing import extras as bl_extras
from ..steps.billing import tickets as bl_tickets
from ..steps.content import assignments as ct_assignments
from ..steps.content import courses as ct_courses
from ..steps.content import instructors as ct_instructors
from ..steps.content import lessons as ct_lessons
from ..steps.content import live_courses as ct_live_courses
from ..steps.content import live_definitions as ct_live_definitions
from ..steps.content import live_lessons as ct_live_lessons
from ..steps.content import masters as ct_masters
from ..steps.content import quizzes as ct_quizzes
from ..steps.content import surveys as ct_surveys
from ..steps.enrollment import certificates as en_certificates
from ..steps.enrollment import progress as en_progress
from ..steps.enrollment import results as en_results
from ..steps.enrollment import rights as en_rights
from ..steps.schema import SchemaCheckStep
from ..steps.support import library as sp_library
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
        # --- 1 基盤 ---------------------------------------------------------
        Section(
            key="foundation",
            order=1,
            title="基盤",
            doc="docs/db/01-foundation/migration-spec.md",
            phases=[
                # マスタ → テナント → テナント設定。**この順でないと FK が揃わない**
                # （`tenants` の1行が入らないと、FK を持つ子は1行も入らない）
                Phase(1, "マスター", "ルックアップの不足値・テナント・テナント設定を入れる",
                      steps=(masters.build() + [TenantStep()] + tenant_config.build()
                             + org.definitions() + auth_config.build()),
                      checks=(postcheck.target_tenant_once,)),
                Phase(2, "ユーザ", "会員と、会員に紐づくものを入れる",
                      steps=users.build() + user_related.build() + org.assignments(),
                      checks=(postcheck.no_platform_admin, postcheck.email_unique)),
            ],
        ),
        # --- 2 コンテンツ ---------------------------------------------------
        Section(
            key="content",
            order=2,
            title="コンテンツ",
            doc="docs/db/02-content/migration-spec.md",
            phases=[
                Phase(1, "オンデマンド講座", "講座・ユニット・動画・受講制御を移す",
                      steps=(ct_masters.build() + ct_instructors.build() + ct_courses.build()
                             + ct_lessons.build())),
                Phase(2, "テスト定義・課題定義", "問題バンク・テスト・出題条件・課題を移す",
                      steps=ct_quizzes.build() + ct_assignments.build()),
                Phase(3, "アンケート定義", "アンケートの設問と選択肢を移す",
                      steps=ct_surveys.build()),
                # ライブは講座に属さないので、受け皿の講座をここで作る
                Phase(4, "ライブ講座", "受け皿講座・ライブ・開催回・分類を移す",
                      steps=(ct_live_courses.host_course() + ct_live_lessons.build()
                             + ct_live_definitions.build())),
            ],
        ),
        # --- 3 受講 ---------------------------------------------------------
        Section(
            key="enrollment",
            order=3,
            title="受講",
            doc="docs/db/03-enrollment/migration-spec.md",
            phases=[
                Phase(1, "受講権限", "購入で得た受講権限と、受け皿講座への受講登録",
                      steps=en_rights.build() + ct_live_courses.enrollments()),
                Phase(2, "学習履歴", "ユニットごとの学習状況を移す",
                      steps=en_progress.build()),
                Phase(3, "テスト結果", "受験・設問別回答・選んだ選択肢を移す",
                      steps=en_results.quizzes()),
                Phase(4, "課題提出", "提出・提出ファイル・添削を移す",
                      steps=en_results.submissions()),
                Phase(5, "アンケート回答", "回答の見出しと設問別回答を移す",
                      steps=en_results.surveys()),
                # 予約はチケット定義（billing.1）のあと。台帳が予約を参照する
                Phase(6, "ライブ予約", "予約とライブレビューを移す",
                      steps=bl_tickets.reservations_steps() + bl_extras.reviews()),
                Phase(7, "修了証", "修了証の設定と発行済みの証書を移す",
                      steps=en_certificates.build()),
            ],
        ),
        # --- 4 課金 ---------------------------------------------------------
        Section(
            key="billing",
            order=4,
            title="課金",
            doc="docs/db/04-billing/migration-spec.md",
            phases=[
                Phase(1, "チケット", "種別・必要枚数・付与・消費の台帳・月次配布を移す",
                      steps=(bl_tickets.definitions() + bl_tickets.grants()
                             + bl_extras.allowances())),
                Phase(2, "決済", "決済・継続課金・分割払い（未実装）", steps=[]),
                Phase(3, "帳票", "領収書・消費税・規約（未実装）", steps=[]),
            ],
        ),
        # --- 5 サポート機能 -------------------------------------------------
        Section(
            key="support",
            order=5,
            title="サポート機能",
            doc="docs/db/05-support/migration-spec.md",
            phases=[
                Phase(1, "LINE 友だち紐付け", "LINE の紐付け（会員の投入後）",
                      steps=user_related.line_links()),
                Phase(2, "クーポン", "クーポンと対象者割当（未実装）", steps=[]),
                Phase(3, "お知らせ", "お知らせ・配信設定（未実装）", steps=[]),
                Phase(4, "問い合わせ", "問い合わせと個別メッセージ（未実装）", steps=[]),
                Phase(5, "ファイル", "教材・ライブラリを移す", steps=sp_library.build()),
                Phase(6, "就業支援", "求人・面談・スキルチェック（未実装）", steps=[]),
                Phase(7, "コミュニティ", "掲示板・SNS 共有・足あと（未実装）", steps=[]),
            ],
        ),
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
