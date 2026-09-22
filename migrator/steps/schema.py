"""フェーズ common.0 — 新環境のスキーマ追加が入っているかを確認する。

追加（A1〜A21）は school-launcher 側の migration で入れる。**移行直前に実施する**
という決定のため、ここでは「入っていること」を確かめ、入っていなければ止める。

一覧と DDL は [基盤のマイグレーション対象](../../docs/db/01-foundation/schema-additions.md)。

2種類に分けてある。

- `REQUIRED_SCHEMA` — **実装済みの Step が実際に書き込む先。** 1つでも欠けたら止める
- `PLANNED_SCHEMA` — 追加一覧にはあるが、**対応する Step がまだ無い**もの。
  欠けていても止めず、`doctor` で残作業として見せる
"""

from __future__ import annotations

from ..context import RunContext
from ..core.records import StepResult
from ..errors import PreflightError
from .base import SchemaStep

#: 実装済みの Step が書き込む先。(テーブル, 列)。列が None ならテーブルの存在だけ見る
REQUIRED_SCHEMA: tuple[tuple[str, str | None], ...] = (
    # A1 / A2 テナント
    ("tenants", "short_name"),
    ("tenants", "language_code"),
    # A4 上限
    ("tenant_limits", None),
    # A9 プロフィール項目（値は item_type=1 の自由記述だけがここに入る）
    ("tenant_profile_item_categories", None),
    ("tenant_profile_items", None),
    ("tenant_profile_item_labels", None),
    ("user_profile_values", None),
    # A12 会員の氏名・会員番号
    ("users", "name_last"),
    ("users", "name_first"),
    ("users", "name_kana_last"),
    ("users", "name_kana_first"),
    ("users", "member_no"),
    ("user_addresses", None),
    # A14 ログイン状態（畳まず同じ粒度で持つ）
    ("users", "is_lockout"),
    ("users", "failed_login_started_at"),
    ("users", "failed_login_count"),
    ("users", "last_login_at"),
    ("users", "last_access_at"),
    ("users", "total_login_count"),
    # A20 会員のその他の列
    ("users", "login_id"),
    ("users", "mobile_email"),
    ("users", "mobile_phone"),
    ("users", "nickname"),
    ("users", "gender"),
    ("users", "blood_type"),
    ("users", "self_introduction"),
    ("users", "login_start_date"),
    ("users", "login_end_date"),
    ("users", "admin_memo"),
    ("users", "external_data"),
    ("users", "password_changed_at"),
    ("users", "is_valid"),
    ("users", "is_new"),
    ("users", "is_career_counselor"),
    # A22 / A23 実装して判明した不足分
    ("users", "language_code"),
    ("tenant_field_defaults", None),
    # A21 通知（PC / 携帯を分ける）
    ("notification_optouts", "channel"),
    # A10 / A11 グループ・属性
    ("tenant_groups", None),
    ("tenant_group_members", None),
    ("tenant_attributes", None),
    ("user_attribute_values", None),
    ("attribute_required_courses", None),
    # A13 / A17 / A18 会員に紐づく残り
    ("user_field_visibility", None),
    ("user_login_periods", None),
    ("instructor_assignments", None),
    # A3 外部サービスの API キー
    ("tenant_secrets", None),
    # A6 / A8 認証まわり（SSO とログイン時間制限は Step が行を入れる）
    ("tenant_sso_configs", None),
    ("tenant_login_windows", None),
)

#: **移行では使わない**もの（新環境の運用のための改善）。欠けていても止めない
PLANNED_SCHEMA: tuple[tuple[str, str | None, str], ...] = (
    # **移行では使わない。** 純ログを移行しないと決めたため、login_history には1行も入れない。
    # ただし auth_outcomes に user_not_found があるのに失敗ログインを記録できないのは、
    # cutover 後の運用でそのまま効く問題なので、残作業として出す
    ("login_history", "input_login_id", "A16 失敗ログインの記録（新環境の運用のための改善）"),
    ("login_history", "logged_out_at", "A16 滞在時間の集計"),
    ("login_history", "session_id", "A16 セッション追跡"),
    # **2FA は受け皿を作るだけ。** 旧 `twostepverification` が持つのは発行中の
    # 確認コードだけで（秘密鍵ではない）、移した時点で無効になる。移す行が無いので
    # 「必須」には入れない
    ("user_two_factor_secrets", None, "A15 2FA の受け皿（移す行は無い）"),
)


def missing(ctx: RunContext, entries) -> list[str]:
    """入っていないものを返す。接続が無いときは空（確認できないため）。"""
    if ctx.target.connectionless:
        return []
    out = []
    for entry in entries:
        table, column = entry[0], entry[1]
        if column is None:
            rows = ctx.target.query(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema = DATABASE() AND table_name = %s LIMIT 1",
                (table,),
            )
        else:
            rows = ctx.target.query(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_schema = DATABASE() AND table_name = %s AND column_name = %s LIMIT 1",
                (table, column),
            )
        if not rows:
            out.append(f"{table}.{column}" if column else table)
    return out


class SchemaCheckStep(SchemaStep):
    """追加スキーマの存在確認。**必須が1つでも欠けたら移行を始めない。**"""

    name = "schema.check"
    description = "追加スキーマ（A1〜A21）が新環境に入っているかを確認する"
    required = REQUIRED_SCHEMA

    def run(self, ctx: RunContext) -> StepResult:
        result = StepResult(step=self.name)
        lacking = missing(ctx, REQUIRED_SCHEMA)
        if lacking:
            raise PreflightError(
                "新環境に追加スキーマが入っていない: "
                + ", ".join(lacking)
                + "。docs/db/01-foundation/schema-additions.md の migration を先に当てる"
            )
        result.note(f"必須 {len(REQUIRED_SCHEMA)} 件を確認")
        planned = missing(ctx, PLANNED_SCHEMA)
        if planned:
            result.note(f"未実装 Step 用の {len(planned)} 件は未適用（移行には影響しない）")
        return ctx.record(result)
