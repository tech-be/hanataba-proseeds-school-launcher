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
    ("users", "user_id"),
    ("tenants", "tenant_id"),
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
    # 属性はタグに一本化した（school-launcher 20260927105511 / 20260930044959）
    ("user_tags", "attribute_id"),
    # 削除済みも移す（2026-10-01。school-launcher 20261001085757）
    ("user_tags", "deleted_at"),
    ("user_tag_assignments", None),
    # A13 / A18 会員に紐づく残り
    ("user_field_visibility", None),
    ("instructor_assignments", None),
    # A3 外部サービスの API キー
    ("tenant_secrets", None),
    # A6 / A8 認証まわり（SSO とログイン時間制限は Step が行を入れる）
    ("tenant_sso_configs", None),
    ("tenant_login_windows", None),
)

#: コンテンツ（2）の追加。オンデマンド講座・テスト/課題定義・アンケート定義・ライブ講座。
#: **school-launcher の `*_lw2_content_additions.sql` と1対1で対応させる。**
#: ここに書き漏らすと `common.0` の存在確認を素通りして、実 INSERT で初めて落ちる。
CONTENT_SCHEMA: tuple[tuple[str, str | None], ...] = (
    # A3 カテゴリ
    ("course_categories", "image_url"),
    ("course_categories", "created_by"),
    # A1 講座
    ("courses", "legacy_lesson_id"),
    ("courses", "allowed_ip_address"),
    ("courses", "is_used"),
    ("courses", "settings"),
    ("course_tags", None),
    ("course_tag_links", None),
    # A4 レッスン
    ("lessons", "unit_id"),
    # 見出しブロック → 講座の章（school-launcher 20260926190305 / 20260930044959）
    ("course_chapters", "unit_id"),
    # 削除済みも移す（2026-10-01。school-launcher 20261001085757）
    ("course_chapters", "deleted_at"),
    ("lessons", "chapter_id"),
    ("lessons", "open_at"),
    ("lessons", "close_at"),
    ("lessons", "close_after_days"),
    ("lessons", "drip_delay_basis"),
    ("lessons", "complete_message"),
    ("lessons", "search_keyword"),
    ("lessons", "duration_min"),
    ("lessons", "settings"),
    # A5 動画
    ("video_lessons", "complete_type"),
    ("video_lessons", "skip_prevention"),
    ("video_lessons", "settings"),
    # A15 受講制御（免除は受け皿の形が違うので作っていない）
    ("lesson_preconditions", None),
    # A6 / A7 / A8 テスト定義（共有問題バンクと出題条件）
    # 分類は quiz_question_labels に統合した（school-launcher 20260928082433）
    ("quiz_question_labels", "question_cate_id"),
    ("quiz_question_banks", None),
    ("quiz_question_rules", None),
    ("quiz_questions", "bank_id"),
    ("quiz_questions", "image_url"),
    ("quiz_questions", "name"),
    ("quiz_questions", "hint"),
    ("quiz_questions", "required"),
    ("quiz_options", "image_url"),
    ("quizzes", "max_attempts"),
    ("quizzes", "suspend_enabled"),
    ("quizzes", "display_settings"),
    # A13 課題定義（提出側は受講（3）の担当）
    ("assignments", "due_after_days"),
    ("assignments", "video_url"),
    ("assignments", "settings"),
    ("assignment_materials", None),
    # A12 アンケート定義（回答側は受講（3）の担当）
    ("survey_pages", None),
    ("survey_lessons", "name"),
    ("survey_questions", "page_id"),
    ("survey_questions", "image_url"),
    ("survey_question_options", "image_url"),
    # ライブ講座（2-4）
    ("live_lessons", "live_lesson_id"),
    ("live_lessons", "settings"),
    ("live_lesson_categories", None),
    ("live_lesson_category_links", None),
    ("live_lesson_group_targets", None),
    ("live_lesson_occurrences", "deleted_at"),
    ("live_lesson_occurrences", "remind_enabled"),
    ("live_lesson_occurrences", "settings"),
    ("live_lesson_recurrence_rules", None),
    ("live_lesson_recurrence_details", None),
    ("live_lesson_recurrence_exclusions", None),
    # 削除済みも移す（2026-10-01。school-launcher 20261001085757）
    ("live_lesson_group_targets", "deleted_at"),
    ("live_lesson_exclusion_date_history", "live_lesson_id"),
)

#: 区分ごとの必須スキーマ。**その区分を流すときだけ確認する**
#: （基盤だけを流し直すのに、オンデマンドの追加を待つ必要は無い）
#: 受講（3）の追加。テスト結果・課題提出・アンケート回答・ライブ予約・修了証。
#: **対応する migration はまだ無い。** `doctor` が TODO で出すのが正しい状態
#: （区分3 を作り直す回で `*_lw2_enrollment_additions.sql` を書く）。
ENROLLMENT_SCHEMA: tuple[tuple[str, str | None], ...] = (
    # 講座ごとの修了証の発行方針（既存の表。設定の無い講座は issue = FALSE で入れる）
    ("course_certificate_policies", None),
    # 受講権限（A8）
    ("enrollments", "settings"),
    # 学習履歴（A9）
    ("lesson_progress", "progress_status"),
    ("lesson_progress", "settings"),
    ("lesson_progress", "deleted_at"),
    # テスト結果
    ("quiz_attempts", "passed"),
    ("quiz_attempts", "duration_sec"),
    ("quiz_answers", "is_correct"),
    ("quiz_answers", "option_order"),
    ("quiz_answers", "sort_no"),
    ("quiz_answers", "pre_question_pass"),
    # 課題提出
    ("submissions", "score"),
    ("submissions", "settings"),
    # 添削に付けたファイル（旧 eval_*。受講者の提出ファイルではない。school-launcher 20260930052453）
    ("submission_feedback_files", None),
    ("survey_submission_log", None),
    # 削除済みも移す（2026-10-01。school-launcher 20261001085757）
    ("survey_responses", "deleted_at"),
    ("submission_feedbacks", "question_comments"),
    # アンケート回答
    ("survey_responses", "entity_type"),
    ("survey_responses", "entity_id"),
    ("survey_responses", "suspended"),
    # ライブ予約
    ("live_reservations", "verification_key"),
    ("live_reservations", "settings"),
    ("live_lesson_reviews", None),
)

#: 課金（4）の追加。チケット
BILLING_SCHEMA: tuple[tuple[str, str | None], ...] = (
    # 自動割当（旧 assign → タグの自動付与ルール。school-launcher 20260927105511 / 20260930044959）
    ("tag_auto_assign_rules", "assign_id"),
    ("tag_auto_assign_rule_triggers", None),
    ("tag_auto_assign_rule_conditions", None),
    ("tag_auto_assign_rule_grants", None),
    # 削除済みも移す（2026-10-01。school-launcher 20261001085757）
    ("tag_auto_assign_rule_triggers", "item_type"),
    ("tag_auto_assign_rule_group_conditions", None),
    ("tag_auto_assign_rule_grants", "deleted_at"),
    ("plan_courses", "deleted_at"),
    ("ticket_type_lessons", "deleted_at"),
    ("live_lesson_limit_item_history", "live_lesson_id"),
    ("tag_auto_assign_logs", None),
    ("ticket_types", "ticket_id"),
    ("ticket_types", "legacy_ticket_type"),
    ("ticket_grants", "starts_at"),
    ("monthly_ticket_allowances", None),
    # 決済（A3 / A4）と帳票（A7 / A8）。school-launcher 20260928132756
    ("tenant_plans", "item_id"),
    ("tenant_plans", "settings"),
    ("payments", "application_id"),
    ("payments", "settings"),
    ("receipts", "receipt_log_id"),
    ("tenant_legal_documents", None),
)

#: サポート機能（5）の追加。教材・ライブラリの公開対象。
#: **対応する migration はまだ無い**（区分5 を作り直す回で書く）。
#: 属性単位の公開（`library_folder_attribute_targets`）は**旧に対応データが無い**ので作らない。
SUPPORT_SCHEMA: tuple[tuple[str, str | None], ...] = (
    ("library_folder_group_targets", None),
    ("library_material_lesson_targets", None),
    # 添付資料ごとの公開グループ・属性（旧 *_attached_file_group / _attribute）
    ("library_material_group_targets", None),
    ("library_material_tag_targets", None),
    # 2026-09-30 に「その他」から仕分けた受け皿（school-launcher 20260930052453）
    ("scout_follows", "follow_id"),
    ("community_categories", "community_cate_id"),
    ("tenant_usage_settings", None),
    ("tenant_usage_snapshots", None),
    ("tenant_usage_snapshot_users", "legacy_user_id"),
    # 助言メモの「最後に直した人」
    ("admin_notes", "updated_by"),
    # 削除済みも移す（2026-10-01。school-launcher 20261001085757）
    ("admin_notes", "deleted_at"),
)

#: **キーは `Phase.key` の接頭辞と一致させること。** `SchemaCheckStep.run()` が
#: `ctx.selected` を `.` で分割して突き合わせるので、**ずれても例外にならず確認が素通りする**
SCHEMA_BY_SECTION: dict[str, tuple[tuple[str, str | None], ...]] = {
    "foundation": REQUIRED_SCHEMA,
    "content": CONTENT_SCHEMA,
    "enrollment": ENROLLMENT_SCHEMA,
    "billing": BILLING_SCHEMA,
    "support": SUPPORT_SCHEMA,
}

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
        # **これから流す区分の分だけ確認する。** 基盤を流し直すのに、
        # オンデマンドの追加が当たっているかは関係ない
        sections = {key.split(".")[0] for key in ctx.selected} or set(SCHEMA_BY_SECTION)
        entries: list[tuple[str, str | None]] = []
        for section in sorted(sections & set(SCHEMA_BY_SECTION)):
            entries += list(SCHEMA_BY_SECTION[section])
        lacking = missing(ctx, tuple(entries))
        if lacking:
            raise PreflightError(
                "新環境に追加スキーマが入っていない: "
                + ", ".join(lacking)
                + "。該当区分の schema-additions.md の migration を先に当てる"
            )
        result.note(f"必須 {len(entries)} 件を確認（区分: {', '.join(sorted(sections)) or '全部'}）")
        planned = missing(ctx, PLANNED_SCHEMA)
        if planned:
            result.note(f"未実装 Step 用の {len(planned)} 件は未適用（移行には影響しない）")
        return ctx.record(result)
