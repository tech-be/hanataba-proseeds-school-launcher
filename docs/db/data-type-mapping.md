# データ種別 旧⇔新テーブル対照表

`既存機能と新システムの保有.docx.pdf` が定義する **8区分 / 95データ種**を分類軸として、旧環境 learningware-kiracari (lw2) の全342テーブルと、新環境 school-launcher の全256テーブルを対応づけたもの。移行ツールが「何を何処へ移すか」を決めるための一次資料。

- 逆引き（テーブル → データ種）: [旧環境](legacy-table-coverage.md) / [新環境](new-table-coverage.md)
- PDF との差分・要確認事項: [data-type-findings.md](data-type-findings.md)
- 対応づけたテーブルで実際に移せるかの検証: [review/README.md](README.md)

## 凡例

| 列 | 意味 |
|---|---|
| ID | 本ドキュメントで付番したデータ種ID（区分の頭文字 + 連番） |
| 旧テーブル | lw2 側で該当するテーブル。`（副）` は他のデータ種が主で、このデータ種にもまたがるもの |
| 新テーブル | school-launcher 側で該当するテーブル。接頭辞なし = `learningware` DB / `career:` = `career` DB / `sp:` = `skill_passport` DB |
| PDF | PDF の「新システム」列の値（転記） |
| 再判定 | 新環境 `docs/db` を根拠に判定し直した値。**太字**は PDF と食い違うもの |
| ETL段 | `school-launcher/docs/scrun-etl-design.md` §4 の L0〜L9 のうち、このデータ種の移行先テーブルを名指ししている段。`—` は ETL 設計に段の割当が無い |

**再判定のルール**: 新環境にそのデータ種のデータを保持する場所（テーブル **または** カラム）があれば ◯、無ければ X。PDF の定義に合わせ「機能の有無」で判定しており、**実際に移行するかどうかとは別**。受け皿がカラムしか無い場合は新テーブル列が `—` になるので、備考にカラム名を書いている。

## 集計

| 区分 | データ種 | PDF ◯ | PDF X | 再判定 ◯ | 再判定 X | 増減 |
|---|---:|---:|---:|---:|---:|---:|
| 基盤 | 12 | 6 | 6 | 5 | 7 | -1 |
| オンデマンド | 28 | 16 | 12 | 17 | 11 | +1 |
| ライブ | 9 | 5 | 4 | 6 | 3 | +1 |
| 受講 | 6 | 3 | 3 | 3 | 3 | +0 |
| 課金 | 13 | 11 | 2 | 11 | 2 | +0 |
| 運営 | 14 | 6 | 8 | 7 | 7 | +1 |
| 就職支援 | 8 | 3 | 5 | 4 | 4 | +1 |
| 対象外 | 5 | 0 | 5 | 0 | 5 | +0 |
| **合計** | **95** | **50** | **45** | **53** | **42** | **+3** |

PDF 側の件数は PDF 冒頭の集計表と完全に一致する（95 / ◯50 / X45）。再判定で動いたのは 5 件（X→◯ が 4、◯→X が 1）で、内訳は [data-type-findings.md](data-type-findings.md) にある。


## 基盤

| ID | データ種 | 旧テーブル | 新テーブル | PDF | 再判定 | ETL段 | 備考 |
|---|---|---|---|:--:|:--:|:--:|---|
| B01 | テナント | `site`, `tenant`, `tenant_limit_value` | `tenant_db_types`, `tenant_secret_kinds`, `tenant_secrets`, `tenant_statuses`, `tenants` | ◯ | ◯ | — | 新環境はシード値のみでテナント行が無い。**`tenants` の1行作成に ETL 段の割当が無い**（L0 に要追加） |
| B02 | ロール（管理者 / 講師 / 受講者） | `system_admin_role`, `role_master`, `instructor_set_attribute`, `instructor_set_group`, `instructor_set_lesson` | `user_roles` | ◯ | ◯ | — |  |
| B03 | メールログイン | （副）`user` | — | ◯ | ◯ | L1 | 受け皿は `users.email`（専用テーブルなし） |
| B04 | login_id ログイン | （副）`user` | — | X | X | — | 新環境のログインIDはメールのみ |
| B05 | パスワード（現行 3DES のまま利用） | `password_reminder`<br>（副）`user` | — | X | X | L1 | `users.password_hash` は bcrypt。3DES のままは持てない（ETL設計 §7） |
| B06 | 会員プロフィール（氏名・生年・電話） | `edit_form_data`, `profile_cate`, `profile_item`, `profile_item_label`, `user`, `user_attached_info`, `user_item_default`, `user_nationality_info` | `external_user_links`, `user_preferences`, `user_statuses`, `users` | ◯ | ◯ | L1 |  |
| B07 | グループ | `group`, `group_structure`, `user_group` | — | X | X | — |  |
| B08 | 属性 | `attribute`, `attribute_lesson`, `user_attribute` | — | X | X | — |  |
| B09 | ログイン履歴 | `login_limit`, `user_login_chk_log`, `user_login_log`, `user_login_log_monthly` | `auth_methods`, `auth_outcomes`, `login_history` | ◯ | ◯ | — | `login_history` は ETL 段の割当なし |
| B10 | SSO | `sns_setting`, `sso_config` | — | ◯ | **X** | — | **PDFは◯。** `auth_methods` は google/line/passkey/password/refresh のみで、`sso_config` 相当の IdP 設定テーブルが無い |
| B11 | マイナンバー | `user_personal_no` | — | X | X | — | **実体はマイナンバーではなく会員の一意 ID**（確認済み）。PDF のデータ種名が実体と合っていない — [findings §3](data-type-findings.md) |
| B12 | 二要素認証 | `twostepverification`, `twostepverification_log` | — | X | X | — | `user_passkeys` はあるが二要素認証ではない |

## オンデマンド

| ID | データ種 | 旧テーブル | 新テーブル | PDF | 再判定 | ETL段 | 備考 |
|---|---|---|---|:--:|:--:|:--:|---|
| O01 | 講座 | `lesson`, `lesson_is_used`, `lesson_lesson_tag`, `lesson_system`, `lesson_tag` | `content_statuses`, `course_difficulties`, `courses` | ◯ | ◯ | L2 |  |
| O02 | 講座カテゴリ | `lesson_cate` | `course_categories` | ◯ | ◯ | L2 | 受け皿は `course_categories` と `courses.category` |
| O03 | 講座サムネ | （副）`lesson` | — | ◯ | ◯ | L2/L9 | 受け皿は `courses.thumbnail_url`（専用テーブルなし） |
| O04 | 講義ユニット | `lecture`, `lecture_path`, `lecture_path_test`, `unit` | `lesson_types`, `lessons` | ◯ | ◯ | L2 | `unit`(type=0 見出し)は `lessons` ではなく `course_chapters` に入れる（2026-09-30） |
| O05 | 見出しブロック | （副）`unit` | `course_chapters` | X | **◯** | — | **2026-09-30 再判定。** 新に「講座の章」ができた（school-launcher 20260926190305） |
| O06 | 講義動画（p-movie / 自前） | （副）`lecture` | `video_lessons` | ◯ | ◯ | L2/L9 | p-movie 22本はURL付替、自前21本は投入 |
| O07 | 動画字幕（WebVTT） | — | — | X | X | — | 字幕の受け皿なし |
| O08 | テスト定義 | `question`, `question_cate`, `sort_test_sub_question`, `test`, `test_sub`, `test_sub_question` | `quiz_options`, `quiz_question_types`, `quiz_questions`, `quizzes` | ◯ | ◯ | L2 | テストは `lessons.type='text'` + `quizzes` |
| O09 | テスト受験（合否・得点） | `user_learning_test` | `quiz_attempt_event_kinds`, `quiz_attempt_events`, `quiz_attempt_statuses`, `quiz_attempts` | ◯ | ◯ | L4 |  |
| O10 | テスト設問別回答（選択式） | `user_learning_test_sub` | `quiz_answer_selected_options`, `quiz_answers` | ◯ | ◯ | L4 |  |
| O11 | テスト自由記述 | （副）`user_learning_test_sub` | — | X | X | — | `quiz_answers` は選択肢のみ。自由記述の受け皿なし |
| O12 | テスト中断・再開 | `user_learning_test_sub_update`, `user_learning_test_suspend_data`, `user_learning_test_update` | — | X | X | — | `quiz_attempt_statuses` に `in_progress` はあるが中断データは持てない |
| O13 | テスト受験回数制限 | （副）`test` | — | X | X | — | `max_attempts` 相当のカラムなし |
| O14 | ユニットアンケート（定義・回答） | `enquete`, `enquete_answer`, `enquete_page`, `enquete_question` | `survey_answer_selected_options`, `survey_answers`, `survey_lessons`, `survey_question_kinds`, `survey_question_options`, `survey_questions`, `survey_responses`, `survey_submission_log` | ◯ | ◯ | L2/L4 | 移行できるのは entity_type=2 の 1,308 件のみ |
| O15 | アンケートのファイル添付設問 | （副）`enquete_question` | — | X | X | — | `survey_question_kinds` は single_choice/multiple_choice/text_long のみ |
| O16 | お知らせ添付アンケート | （副）`news_user`, `enquete_answer` | — | X | X | — | お知らせに紐づくアンケート回答の受け皿なし（545件） |
| O17 | レポート添付アンケート | （副）`enquete_answer` | — | X | X | — | レポートに紐づくアンケート回答の受け皿なし（611件） |
| O18 | 課題（定義・提出・添削） | `report`, `report_path`, `user_learning_report` | `assignments`, `submission_feedbacks`, `submission_status_events`, `submissions` | ◯ | ◯ | L2/L4 |  |
| O19 | 課題の提出ファイル | （副）`user_learning_report` | — | ◯ | ◯ | L9 | 旧 `eval_*` は添削者が付けたファイル。受け皿は `submission_feedback_files`（5本を行に展開。2026-09-30） |
| O20 | 講座資料ユニット | （副）`unit` | — | ◯ | ◯ | L2 | 受け皿は `lessons.type='text'`（専用テーブルなし） |
| O21 | 教材添付・ライブラリ | `lesson_attached_file`, `lesson_attached_file_attribute`, `lesson_attached_file_group`, `unit_attached_file`, `unit_attached_file_attribute`, `unit_attached_file_group`, `document_file_detail`, `drive`, `drive_group` | `library_audience_types`, `library_downloads`, `library_folder_course_targets`, `library_folder_user_targets`, `library_folders`, `library_material_kinds`, `library_materials` | ◯ | ◯ | L8/L9 | recademy 実測 3 件のみ |
| O22 | ユニット前提条件 | `unit_precondition` | — | X | X | — |  |
| O23 | ユニット免除 | `unit_exemption` | — | X | X | — |  |
| O24 | 受講期限・延長 | （副）`user_learning_lesson` | — | ◯ | ◯ | L3 | 受け皿は `enrollments.expires_at`（専用テーブルなし） |
| O25 | 修了証（講座単位） | `certificate`, `certificate_no`, `config_certificate`, `user_certificate` | `certificate_event_kinds`, `certificate_events`, `certificate_layouts`, `certificate_revoke_reasons`, `certificate_serial_formats`, `certificate_settings`, `certificates`, `course_certificate_policies` | ◯ | ◯ | L7 | `cmd/import-certificates` が実装済み |
| O26 | 修了証（商品単位） | （副）`user_certificate` | — | X | X | — | `certificates` はコース単位のみ |
| O27 | バッジ | `badge_item` | `badge_revoke_reasons`, `digital_badge_event_kinds`, `digital_badge_events`, `digital_badges` | ◯ | ◯ | — | ETL 段の割当なし |
| O28 | リモート PC | `remote_api_token` | `remote_pc_blackouts`, `remote_pc_machines`, `remote_pc_reservation_statuses`, `remote_pc_reservations` | X | **◯** | — | **PDFはX。** `remote_pc_*` 4テーブルが存在する |

## ライブ

| ID | データ種 | 旧テーブル | 新テーブル | PDF | 再判定 | ETL段 | 備考 |
|---|---|---|---|:--:|:--:|:--:|---|
| L01 | ライブ定義 | `live_lesson`, `live_lesson_cate`, `live_lesson_group`, `live_lesson_lesson_cate`, `live_lesson_limit_item`, `live_lesson_preview` | `live_lessons` | ◯ | ◯ | L5 | lw2 の live_lesson は course に属さない。受け皿 course の作り方が未決（ETL設計 §11-4） |
| L02 | 開催日 | `live_lesson_date`, `live_lesson_date_preview`, `live_lesson_date_setting`, `live_lesson_date_setting_detail`, `live_lesson_exclusion_date` | `live_lesson_occurrences` | ◯ | ◯ | L5 |  |
| L03 | 予約・定員・キャンセル・出欠 | `config_live_lesson`, `live_lesson_reserve` | `live_reservation_statuses`, `live_reservations` | ◯ | ◯ | L5 | キャンセル期限は `config_live_lesson` から算出 |
| L04 | リマインド | — | — | ◯ | ◯ | — | 受け皿は `live_reservations.reminded_at` と `email_send_logs` |
| L05 | チケット（付与・残高・予約消費） | `month_user_ticket`, `ticket`, `ticket_limit_lesson`, `user_ticket` | `course_ticket_grants`, `live_lesson_ticket_requirements`, `ticket_grant_sources`, `ticket_grants`, `ticket_type_lessons`, `ticket_types` | ◯ | ◯ | L6 | 残高1行=付与1行として移す |
| L06 | チケット単体の決済購入 | （副）`payment_application` | — | X | X | — | `payment_types` に ticket が無い |
| L07 | チケット消費台帳の再生 | `user_ticket_log` | `ticket_ledger_entries`, `ticket_ledger_kinds` | X | **◯** | L6 | **PDFはX。** `ticket_ledger_entries` は存在する（ETL設計は履歴を再生しない方針） |
| L08 | ライブレビュー | `live_lesson_review` | — | X | X | — | `course_reviews` はコース単位でライブ単位ではない |
| L09 | ライブ限定クーポン | `coupon_live_lesson` | — | X | X | — | `coupon_course_targets` はコース単位。ライブ単位のクーポンは持てない |

## 受講

| ID | データ種 | 旧テーブル | 新テーブル | PDF | 再判定 | ETL段 | 備考 |
|---|---|---|---|:--:|:--:|:--:|---|
| J01 | 受講権限 | `application_user_learning_lesson`, `user_learning_lesson`, `user_learning_lesson_edit_log`, `payment_item_lesson_authority`, `payment_item_lesson_authority_log` | `enrollment_event_kinds`, `enrollment_sources`, `enrollment_status_events`, `enrollment_statuses`, `enrollments` | ◯ | ◯ | L3 | 源泉は `payment_item_lesson_authority`。有効なのは 918 ペアのみ |
| J02 | ユニット進捗 | `summary_finish_unit_num`, `unit_learning_progress_master`, `user_learning_unit`, `user_lesson_session` | `lesson_progress` | ◯ | ◯ | L4 |  |
| J03 | SCORM 詳細ログ / 中断データ | `user_learning_unit_log`<br>（副）`user_learning_unit` | — | X | X | — | SCORM 中断データは捨てる（ETL設計 §5-4） |
| J04 | 購入時自動割当（講座・お知らせ・クーポン） | `assign`, `assign_item`, `assign_log`, `assign_payment_item` | — | ◯ | ◯ | — | 受け皿は `enrollments.source='purchase'`。割当ルール定義テーブルは無い |
| J05 | 自動割当（グループ・属性条件） | `assign_attribute`, `assign_group` | — | X | X | — |  |
| J06 | 自動割当（求人） | （副）`assign_item` | — | X | X | — |  |

## 課金

| ID | データ種 | 旧テーブル | 新テーブル | PDF | 再判定 | ETL段 | 備考 |
|---|---|---|---|:--:|:--:|:--:|---|
| K01 | 商品（講座パッケージ）販売 | `payment_application_item`, `payment_application_set_user_learning_lesson`, `payment_infomation`, `payment_item`, `payment_item_cate`, `payment_item_item_cate`, `payment_item_lesson` | `course_purchase_payments` | ◯ | ◯ | L7 |  |
| K02 | クレジット決済 | `payment_application` | `currencies`, `payment_event_kinds`, `payment_providers`, `payment_refund_reasons`, `payment_status_events`, `payment_statuses`, `payment_types`, `payments`, `provider_webhook_events`, `refund_payments` | ◯ | ◯ | L0/L7 | `payment_providers` に `legacy_jpayment` を足す migration が必要 |
| K03 | 銀行振込 | （副）`payment_application` | — | ◯ | ◯ | L7 | 受け皿は `payment_providers` の `bank_transfer` 行 |
| K04 | コンビニ決済 | （副）`payment_application` | — | ◯ | ◯ | L7 | 受け皿は `payments`。コンビニ専用の provider 行は無く、範囲も未確定 |
| K05 | 継続課金 | （副）`payment_application` | `billing_intervals`, `learner_subscription_event_kinds`, `learner_subscription_status_events`, `learner_subscription_statuses`, `learner_subscriptions`, `plan_courses`, `plan_intervals`, `plan_statuses`, `plan_types`, `specified_continuous_service_categories`, `subscription_cancellation_settlements`, `subscription_payments`, `tenant_plans` | ◯ | ◯ | — | ETL 段の割当なし。継続課金カードの移行は最大リスク |
| K06 | 分割払いの台帳・入金記録 | （副）`payment_application` | `installment_charge_statuses`, `installment_charges`, `installment_plan_statuses`, `installment_plans` | ◯ | ◯ | L7 | 未完済 61 件・契約総額 2,907 万円が cutover をまたぐ |
| K07 | 分割払いの自動課金送信 | （副）`payment_application` | — | X | X | — | 課金実行はプロバイダ側 |
| K08 | 領収書 | `receipt_log`, `receipt_setting` | `receipt_settings`, `receipts` | ◯ | ◯ | L0/L7 |  |
| K09 | 消費税設定 | `tax` | — | ◯ | ◯ | — | 受け皿は `receipt_settings.tax_rate` のみ。期間別税率は持てない |
| K10 | クーポン | `coupon`, `coupon_item`, `coupon_log` | `coupon_applies_to_kinds`, `coupon_redemptions`, `coupon_statuses`, `coupons`, `discount_types` | ◯ | ◯ | L7 | `coupons.provider_coupon_id` が NOT NULL のため方針未決（ETL設計 §11-9） |
| K11 | クーポン対象者割当 | `coupon_group`, `coupon_user` | `coupon_audience_types`, `coupon_course_targets`, `coupon_user_targets` | ◯ | ◯ | L7 | 移行するクーポンの分だけ |
| K12 | 特商法・規約 | `agreement`, `cancel_policy`, `privacy_policy`, `tokusyo` | `consent_kinds`, `user_consents` | ◯ | ◯ | — | 受け皿は `user_consents` + `consent_kinds` |
| K13 | 流入元計測 | `analytics_tag`, `analytics_tag_display`, `trigger_media`, `payment_trigger_media` | — | X | X | — |  |

## 運営

| ID | データ種 | 旧テーブル | 新テーブル | PDF | 再判定 | ETL段 | 備考 |
|---|---|---|---|:--:|:--:|:--:|---|
| U01 | お知らせ / アナウンス配信 | `announce`, `news`, `news_reply`, `summary_news_reply_new` | `announcement_audience_types`, `announcement_course_targets`, `announcement_statuses`, `announcement_user_targets`, `announcements` | ◯ | ◯ | L8 | 6,175 件は 13 年分。直近 N ヶ月に絞る案が未決 |
| U02 | お知らせ既読 | `announce_user`, `news_user`, `summary_news_sub_num` | `announcement_reads` | ◯ | ◯ | — | `news_user` は写さない方針（既読 5.5%） |
| U03 | お知らせ添付ファイル | （副）`news` | — | X | X | L9 | `announcements` に添付カラムが無い（ファイル 296 件） |
| U04 | ログイン後モーダル | `login_dialog_log` | — | X | X | — | PDF の `config_dialog` は lw2 に実在しない |
| U05 | フォローメール | `mail_follow_setting`, `mail_follow_setting_attribute`, `mail_follow_setting_group`, `mail_follow_user_log` | `retention_rules`, `retention_sends`, `retention_trigger_kinds` | ◯ | ◯ | — | 受け皿は `retention_*` 3テーブル |
| U06 | LINE 連携・配信 | `line_message`, `line_message_mail_follow_setting`, `line_message_mail_setting`, `line_message_recruit`, `line_send`, `line_send_batch`, `line_send_batch_log`, `line_send_user`, `line_send_user_log`, `tmp_line_entry`, `tmp_line_message` | `line_links`, `line_send_logs` | ◯ | ◯ | L8 | 同じ LINE 公式アカウントを継続する場合のみ |
| U07 | メールテンプレート | `mail_footer`, `mail_send`, `mail_send_batch`, `mail_send_batch_log`, `mail_send_user`, `mail_send_user_log`, `mail_setting`, `mail_setting_role`, `mail_setting_user`, `mail_template`, `mail_template_group`, `mail_type_master`, `tenant_exclude_mail` | `email_kinds`, `email_send_log_statuses`, `email_send_logs`, `notification_optouts`, `tenant_email_templates` | ◯ | ◯ | — |  |
| U08 | 問い合わせ | `lesson_inquiry_user`, `config_inquire`, `inquire`, `inquire_answer`, `inquire_cate`, `inquire_user` | `inquiries`, `inquiry_categories`, `inquiry_statuses` | ◯ | ◯ | L0/L8 | `inquire_cate` → `inquiry_categories` の対応表 CSV が必要 |
| U09 | 問い合わせ添付ファイル | （副）`inquire_answer` | — | X | X | L9 | `inquiries` に添付カラムが無い（ファイル 706 件・最大の塊） |
| U10 | 個別メッセージ | `thread`, `thread_comment`, `thread_member` | — | X | X | — | `community_messages` はチャネル型で 1 対 1 メッセージではない |
| U11 | 掲示板 | `bbs`, `bbs_comment`, `bbs_set_attribute`, `bbs_set_group`, `bbs_set_lesson`, `bbs_set_payment_item`, `bbs_set_role` | `discussion_likes`, `discussion_post_status_events`, `discussion_post_statuses`, `discussion_posts` | X | **◯** | — | **PDFはX。** `discussion_posts` ほか 4 テーブルが存在する（構造は異なる） |
| U12 | SNS 共有 | `public_unit_share_image`, `unit_share`, `unit_share_image` | — | X | X | — |  |
| U13 | 足あと | `footprint` | — | X | X | — |  |
| U14 | Web Push | `message_send`, `message_send_batch`, `message_send_batch_log`, `message_send_user`, `message_send_user_log`, `subscription`, `tenant_vapid` | — | X | X | — | `in_app_notifications` はアプリ内通知で Web Push ではない |

## 就職支援

| ID | データ種 | 旧テーブル | 新テーブル | PDF | 再判定 | ETL段 | 備考 |
|---|---|---|---|:--:|:--:|:--:|---|
| S01 | 求人の掲載・応募 | `recruit`, `recruit_cate`, `recruit_reply`, `recruit_user`, `summary_recruit_reply_new`, `summary_recruit_sub_num` | `career:job_posting_skills`, `career:job_postings` | ◯ | ◯ | — | career-backend。Wave 4 と同時 |
| S02 | 求人企業ページ | `company` | `career:companies` | X | **◯** | — | **PDFはX。** career-backend `companies` が存在する |
| S03 | スカウト | `scout`, `scout_condition`, `scout_lesson`, `scout_mail_target`, `scout_reply` | — | X | X | — |  |
| S04 | ポートフォリオ | `entitiestags`, `like`, `portfolio`, `portfolio_category`, `portfolio_comment`, `portfolio_comment_like`, `portfolio_like`, `tag` | — | X | X | — |  |
| S05 | 就活プロフィール | `employment_status_master`, `job_career`, `job_category_master`, `job_category_setting`<br>（副）`user` | `career:learner_career_profiles`, `career:learner_career_skills` | ◯ | ◯ | — | career-backend `learner_career_profiles` / `learner_career_skills` |
| S06 | 面談（予約・記録） | `interview_contents`, `interview_record`, `interview_status` | `career:advisors`, `career:availability_slots`, `career:interview_records`, `career:interviews` | ◯ | ◯ | — | career-backend。Step 2 に回すなら移行も第2段 |
| S07 | スキルチェック | `config_skill_unit`, `skill_question`, `skill_question_cate`, `skill_question_result_type`, `skill_result_type`, `skill_unit`, `skill_unit_result`, `skill_unit_result_unit_tag`, `skill_unit_sub`, `skill_unit_sub_question`, `skill_unit_tag`, `sort_skill_unit_sub_question`, `unit_skill_unit_tag`, `user_learning_skill_unit`, `user_learning_skill_unit_sub`, `user_learning_skill_unit_sub_result`, `user_learning_skill_unit_sub_update`, `user_learning_skill_unit_suspend_data`, `user_learning_skill_unit_update`, `user_skill_unit_result`, `user_skill_unit_result_unit_tag` | — | X | X | — | 30テーブルで合計 1,137 行、実質未使用 |
| S08 | 公開スキルチェック | `public_learning_skill_unit`, `public_learning_skill_unit_sub`, `public_learning_skill_unit_sub_result`, `public_learning_skill_unit_sub_update`, `public_learning_skill_unit_suspend_data`, `public_learning_skill_unit_update`, `public_skill_unit_result`, `public_skill_unit_result_unit_tag` | — | X | X | — |  |

## 対象外

| ID | データ種 | 旧テーブル | 新テーブル | PDF | 再判定 | ETL段 | 備考 |
|---|---|---|---|:--:|:--:|:--:|---|
| X01 | 集合研修 | `training`, `training_sub`, `ex_training`, `ex_training_cate`, `ex_training_record`, `facility` | — | X | X | — | recademy に集合研修ユニットは 0 件 |
| X02 | 模試 | `test_mock_setting` | — | X | X | — |  |
| X03 | タイピング | `typing_log`, `typing_question`, `typing_ranking` | — | X | X | — |  |
| X04 | 外部リンク集 | `link`, `link_attribute`, `link_group`, `link_lesson` | — | X | X | — |  |
| X05 | 運営スケジュール | `schedule`, `schedule_attribute`, `schedule_group`, `schedule_lesson`, `schedule_user` | — | X | X | — | 空テーブル |
