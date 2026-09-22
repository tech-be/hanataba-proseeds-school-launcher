# 新環境（school-launcher）テーブル逆引き — 全256件

school-launcher の 3 データベース（`learningware` 236 / `career` 12 / `skill_passport` 8）の**全256テーブル**を、PDF のデータ種へ割り当てたもの。[データ種別対照表](data-type-mapping.md) の逆引き。

## 列の意味

| 列 | 出どころ |
|---|---|
| テーブル | `school-launcher/docs/db/<db>/tables/<name>.md` |
| DB | `learningware` = btoc-backend / `career` = career-backend / `skill_passport` = skill-passport |
| 区分 / データ種 | 本作業の割り当て結果。`新規` は lw2 に対応する機能が無い新システム固有のもの |
| BC / グループ | 新環境 `docs/db` の「BC」「グループ」行をそのまま |
| 区分(構造) | `docs/db` の 区分（データ / マスタ / 中間 / イベント・履歴 / 設定） |
| ETL段 | `scrun-etl-design.md` §4 の L0〜L9 のうち、このテーブルを名指ししている段 |

> **マスタ（ルックアップ）テーブルは ETL では書かない。** ETL 設計 L0 が「前提マスタの整備（migration で入れる。ETL では書かない）」と定めている。区分(構造) が `マスタ` の 59 件（新規分を除く）はデータ種に紐づいていても移行ツールの書き込み対象ではない。

> **新スキーマは実 FK を持つ**（マスタの `code` 列への `ON UPDATE CASCADE` を含む）。したがって投入順序は強制される。ETL 設計 §4 の L0→L9 の順を崩さないこと。

## 集計

### データ種に紐づくか

| DB | 既存データ種に対応 | 新規（旧に対応なし） | 計 |
|---|---:|---:|---:|
| `learningware` | 146 | 90 | 236 |
| `career` | 9 | 3 | 12 |
| `skill_passport` | 0 | 8 | 8 |
| **合計** | **155** | **101** | **256** |

### 区分別（データ種に紐づく155件 + 新規101件）

| 区分 | テーブル数 |
|---|---:|
| オンデマンド | 52 |
| 課金 | 40 |
| 運営 | 23 |
| 基盤 | 13 |
| ライブ | 12 |
| 就職支援 | 9 |
| 受講 | 6 |
| **新規（旧に対応なし）** | **101** |
| **合計** | **256** |

### 新規101件の内訳

lw2 に対応する機能が無く、**移行ツールの対象外**になるもの。

| DB / BC | 件数 | 中身 |
|---|---:|---|
| `learningware` / core | 44 | AI チャット・ヘルプ 17 / 行動分析 DAP 11 / API キー・監査ログ・パスキー 7 / コースレビュー 4 / スキル紐付け 3 / プラットフォームプラン 2 |
| `learningware` / commerce | 11 | マーケットプレイス（テナント間のコース売買）8 / チャージバック 3 |
| `learningware` / webhook | 8 | Webhook 配信 |
| `learningware` / community | 8 | チャネル型コミュニティ（`community_channels` 系）。`discussion_*` は U11 掲示板に割り当てている |
| `skill_passport` / core | 8 | スキルパスポート（スキル分類・評価・本人確認） |
| `learningware` / learning | 7 | 学習目標・学習パス・行動イベント |
| `learningware` / referral | 4 | 紹介プログラム |
| `learningware` / note | 3 | レッスンノート・ブックマーク |
| `career` / matching | 3 | マッチングスコア・メモ |
| `learningware` / notification | 2 | アプリ内通知 |
| `learningware` / badge | 2 | スキル習熟（`digital_badges` は O27 バッジに割り当てている） |
| `learningware` / favorite | 1 | コースお気に入り |

### 構造区分（データ種に紐づく155件）

| 区分(構造) | 件数 | 移行ツールでの扱い |
|---|---:|---|
| データ | 66 | ETL の書き込み対象 |
| マスタ | 59 | **migration で投入。ETL は書かない** |
| 中間 | 14 | 親の投入後 |
| イベント・履歴 | 13 | 再生するかは個別判断 |
| 設定 | 3 | |

## 全256件

| テーブル | DB | 区分 | データ種 | BC / グループ | 区分(構造) | ETL段 |
|---|---|---|---|---|---|:--:|
| `admin_notes` | learningware | 新規 | 新規（旧に対応なし） | core / テナント・プラットフォーム・運営メモ | データ | — |
| `advisors` | career | 就職支援 | S06 面談（予約・記録） | interview | データ | — |
| `ai_chat_feedback_kinds` | learningware | 新規 | 新規（旧に対応なし） | core / AI チャット・ヘルプ・Google Chat 連携 | マスタ | — |
| `ai_chat_message_chunks` | learningware | 新規 | 新規（旧に対応なし） | core / AI チャット・ヘルプ・Google Chat 連携 | データ | — |
| `ai_chat_message_roles` | learningware | 新規 | 新規（旧に対応なし） | core / AI チャット・ヘルプ・Google Chat 連携 | マスタ | — |
| `ai_chat_messages` | learningware | 新規 | 新規（旧に対応なし） | core / AI チャット・ヘルプ・Google Chat 連携 | データ | — |
| `ai_chat_sessions` | learningware | 新規 | 新規（旧に対応なし） | core / AI チャット・ヘルプ・Google Chat 連携 | データ | — |
| `announcement_audience_types` | learningware | 運営 | U01 お知らせ / アナウンス配信 | announcement | マスタ | L8 |
| `announcement_course_targets` | learningware | 運営 | U01 お知らせ / アナウンス配信 | announcement | 中間 | L8 |
| `announcement_reads` | learningware | 運営 | U02 お知らせ既読 | announcement | 中間 | — |
| `announcement_statuses` | learningware | 運営 | U01 お知らせ / アナウンス配信 | announcement | マスタ | L8 |
| `announcement_user_targets` | learningware | 運営 | U01 お知らせ / アナウンス配信 | announcement | 中間 | L8 |
| `announcements` | learningware | 運営 | U01 お知らせ / アナウンス配信 | announcement | データ | L8 |
| `api_key_revoke_reasons` | learningware | 新規 | 新規（旧に対応なし） | core / ユーザー・認証・監査 | マスタ | — |
| `api_key_statuses` | learningware | 新規 | 新規（旧に対応なし） | core / ユーザー・認証・監査 | マスタ | — |
| `api_keys` | learningware | 新規 | 新規（旧に対応なし） | core / ユーザー・認証・監査 | データ | — |
| `assignments` | learningware | オンデマンド | O18 課題（定義・提出・添削） | assignment | データ | L2/L4 |
| `audit_action_kinds` | learningware | 新規 | 新規（旧に対応なし） | core / ユーザー・認証・監査 | マスタ | — |
| `audit_logs` | learningware | 新規 | 新規（旧に対応なし） | core / ユーザー・認証・監査 | イベント・履歴 | — |
| `audit_resource_kinds` | learningware | 新規 | 新規（旧に対応なし） | core / ユーザー・認証・監査 | マスタ | — |
| `auth_methods` | learningware | 基盤 | B09 ログイン履歴 | core / ユーザー・認証・監査 | マスタ | — |
| `auth_outcomes` | learningware | 基盤 | B09 ログイン履歴 | core / ユーザー・認証・監査 | マスタ | — |
| `availability_slots` | career | 就職支援 | S06 面談（予約・記録） | interview | データ | — |
| `badge_revoke_reasons` | learningware | オンデマンド | O27 バッジ | badge | マスタ | — |
| `billing_intervals` | learningware | 課金 | K05 継続課金 | commerce / サブスクリプション・プラン | マスタ | — |
| `certificate_event_kinds` | learningware | オンデマンド | O25 修了証（講座単位） | certificate | マスタ | L7 |
| `certificate_events` | learningware | オンデマンド | O25 修了証（講座単位） | certificate | イベント・履歴 | L7 |
| `certificate_layouts` | learningware | オンデマンド | O25 修了証（講座単位） | certificate | マスタ | L7 |
| `certificate_revoke_reasons` | learningware | オンデマンド | O25 修了証（講座単位） | certificate | マスタ | L7 |
| `certificate_serial_formats` | learningware | オンデマンド | O25 修了証（講座単位） | certificate | マスタ | L7 |
| `certificate_settings` | learningware | オンデマンド | O25 修了証（講座単位） | certificate | 設定 | L7 |
| `certificates` | learningware | オンデマンド | O25 修了証（講座単位） | certificate | データ | L7 |
| `community_channel_status_events` | learningware | 新規 | 新規（旧に対応なし） | community | イベント・履歴 | — |
| `community_channel_statuses` | learningware | 新規 | 新規（旧に対応なし） | community | マスタ | — |
| `community_channels` | learningware | 新規 | 新規（旧に対応なし） | community | データ | — |
| `community_member_roles` | learningware | 新規 | 新規（旧に対応なし） | community | マスタ | — |
| `community_members` | learningware | 新規 | 新規（旧に対応なし） | community | データ | — |
| `community_message_status_events` | learningware | 新規 | 新規（旧に対応なし） | community | イベント・履歴 | — |
| `community_message_statuses` | learningware | 新規 | 新規（旧に対応なし） | community | マスタ | — |
| `community_messages` | learningware | 新規 | 新規（旧に対応なし） | community | データ | — |
| `companies` | career | 就職支援 | S02 求人企業ページ | matching | データ | — |
| `consent_kinds` | learningware | 課金 | K12 特商法・規約 | core / ユーザー・認証・監査 | マスタ | — |
| `content_statuses` | learningware | オンデマンド | O01 講座 | core / コース・レッスン・スキル | マスタ | L2 |
| `coupon_applies_to_kinds` | learningware | 課金 | K10 クーポン | commerce / クーポン | マスタ | L7 |
| `coupon_audience_types` | learningware | 課金 | K11 クーポン対象者割当 | commerce / クーポン | マスタ | L7 |
| `coupon_course_targets` | learningware | 課金 | K11 クーポン対象者割当 | commerce / クーポン | 中間 | L7 |
| `coupon_redemptions` | learningware | 課金 | K10 クーポン | commerce / クーポン | データ | L7 |
| `coupon_statuses` | learningware | 課金 | K10 クーポン | commerce / クーポン | マスタ | L7 |
| `coupon_user_targets` | learningware | 課金 | K11 クーポン対象者割当 | commerce / クーポン | 中間 | L7 |
| `coupons` | learningware | 課金 | K10 クーポン | commerce / クーポン | データ | L7 |
| `course_categories` | learningware | オンデマンド | O02 講座カテゴリ | core / コース・レッスン・スキル | マスタ | L2 |
| `course_certificate_policies` | learningware | オンデマンド | O25 修了証（講座単位） | certificate | データ | L7 |
| `course_difficulties` | learningware | オンデマンド | O01 講座 | core / コース・レッスン・スキル | マスタ | L2 |
| `course_favorites` | learningware | 新規 | 新規（旧に対応なし） | favorite | 中間 | — |
| `course_purchase_payments` | learningware | 課金 | K01 商品（講座パッケージ）販売 | commerce / 決済・返金・チャージバック | データ | L7 |
| `course_review_moderation_statuses` | learningware | 新規 | 新規（旧に対応なし） | core / コースレビュー | マスタ | — |
| `course_review_reports` | learningware | 新規 | 新規（旧に対応なし） | core / コースレビュー | データ | — |
| `course_reviews` | learningware | 新規 | 新規（旧に対応なし） | core / コースレビュー | データ | — |
| `course_skills` | learningware | 新規 | 新規（旧に対応なし） | core / コース・レッスン・スキル | データ | — |
| `course_ticket_grants` | learningware | ライブ | L05 チケット（付与・残高・予約消費） | ticket | データ | L6 |
| `courses` | learningware | オンデマンド | O01 講座 | core / コース・レッスン・スキル | データ | L2 |
| `currencies` | learningware | 課金 | K02 クレジット決済 | commerce / 決済・返金・チャージバック | マスタ | L0/L7 |
| `dap_inference_sources` | learningware | 新規 | 新規（旧に対応なし） | core / 行動分析 (DAP) | マスタ | — |
| `dap_pilot_config` | learningware | 新規 | 新規（旧に対応なし） | core / 行動分析 (DAP) | 設定 | — |
| `dap_rule_reject_reasons` | learningware | 新規 | 新規（旧に対応なし） | core / 行動分析 (DAP) | マスタ | — |
| `dap_rule_statuses` | learningware | 新規 | 新規（旧に対応なし） | core / 行動分析 (DAP) | マスタ | — |
| `dap_rules` | learningware | 新規 | 新規（旧に対応なし） | core / 行動分析 (DAP) | データ | — |
| `dap_site_report_statuses` | learningware | 新規 | 新規（旧に対応なし） | core / 行動分析 (DAP) | マスタ | — |
| `dap_site_reports` | learningware | 新規 | 新規（旧に対応なし） | core / 行動分析 (DAP) | データ | — |
| `dap_stumble_event_kinds` | learningware | 新規 | 新規（旧に対応なし） | core / 行動分析 (DAP) | マスタ | — |
| `dap_stumble_events` | learningware | 新規 | 新規（旧に対応なし） | core / 行動分析 (DAP) | イベント・履歴 | — |
| `dap_stumble_feedback_kinds` | learningware | 新規 | 新規（旧に対応なし） | core / 行動分析 (DAP) | マスタ | — |
| `dap_threshold_groups` | learningware | 新規 | 新規（旧に対応なし） | core / 行動分析 (DAP) | マスタ | — |
| `digital_badge_event_kinds` | learningware | オンデマンド | O27 バッジ | badge | マスタ | — |
| `digital_badge_events` | learningware | オンデマンド | O27 バッジ | badge | イベント・履歴 | — |
| `digital_badges` | learningware | オンデマンド | O27 バッジ | badge | データ | — |
| `discount_types` | learningware | 課金 | K10 クーポン | commerce / クーポン | マスタ | L7 |
| `discussion_likes` | learningware | 運営 | U11 掲示板 | community | 中間 | — |
| `discussion_post_status_events` | learningware | 運営 | U11 掲示板 | community | イベント・履歴 | — |
| `discussion_post_statuses` | learningware | 運営 | U11 掲示板 | community | マスタ | — |
| `discussion_posts` | learningware | 運営 | U11 掲示板 | community | データ | — |
| `email_kinds` | learningware | 運営 | U07 メールテンプレート | notification | マスタ | — |
| `email_send_log_statuses` | learningware | 運営 | U07 メールテンプレート | line | マスタ | — |
| `email_send_logs` | learningware | 運営 | U07 メールテンプレート | notification | イベント・履歴 | — |
| `enrollment_event_kinds` | learningware | 受講 | J01 受講権限 | core / 受講登録・進捗 | マスタ | L3 |
| `enrollment_sources` | learningware | 受講 | J01 受講権限 | core / 受講登録・進捗 | マスタ | L3 |
| `enrollment_status_events` | learningware | 受講 | J01 受講権限 | core / 受講登録・進捗 | イベント・履歴 | L3 |
| `enrollment_statuses` | learningware | 受講 | J01 受講権限 | core / 受講登録・進捗 | マスタ | L3 |
| `enrollments` | learningware | 受講 | J01 受講権限 | core / 受講登録・進捗 | データ | L3 |
| `external_user_links` | learningware | 基盤 | B06 会員プロフィール（氏名・生年・電話） | core / ユーザー・認証・監査 | データ | L1 |
| `google_chat_analyses` | learningware | 新規 | 新規（旧に対応なし） | core / AI チャット・ヘルプ・Google Chat 連携 | データ | — |
| `google_chat_messages` | learningware | 新規 | 新規（旧に対応なし） | core / AI チャット・ヘルプ・Google Chat 連携 | データ | — |
| `google_chat_spaces` | learningware | 新規 | 新規（旧に対応なし） | core / AI チャット・ヘルプ・Google Chat 連携 | データ | — |
| `help_chat_messages` | learningware | 新規 | 新規（旧に対応なし） | core / AI チャット・ヘルプ・Google Chat 連携 | データ | — |
| `help_chat_sessions` | learningware | 新規 | 新規（旧に対応なし） | core / AI チャット・ヘルプ・Google Chat 連携 | データ | — |
| `help_faq_articles` | learningware | 新規 | 新規（旧に対応なし） | core / AI チャット・ヘルプ・Google Chat 連携 | データ | — |
| `help_items` | learningware | 新規 | 新規（旧に対応なし） | core / AI チャット・ヘルプ・Google Chat 連携 | データ | — |
| `help_release_features` | learningware | 新規 | 新規（旧に対応なし） | core / AI チャット・ヘルプ・Google Chat 連携 | データ | — |
| `help_release_statuses` | learningware | 新規 | 新規（旧に対応なし） | core / AI チャット・ヘルプ・Google Chat 連携 | マスタ | — |
| `help_releases` | learningware | 新規 | 新規（旧に対応なし） | core / AI チャット・ヘルプ・Google Chat 連携 | データ | — |
| `help_sections` | learningware | 新規 | 新規（旧に対応なし） | core / AI チャット・ヘルプ・Google Chat 連携 | データ | — |
| `in_app_kinds` | learningware | 新規 | 新規（旧に対応なし） | notification | マスタ | — |
| `in_app_notifications` | learningware | 新規 | 新規（旧に対応なし） | notification | データ | — |
| `inquiries` | learningware | 運営 | U08 問い合わせ | inquiry | データ | L0/L8 |
| `inquiry_categories` | learningware | 運営 | U08 問い合わせ | inquiry | マスタ | L0/L8 |
| `inquiry_statuses` | learningware | 運営 | U08 問い合わせ | inquiry | マスタ | L0/L8 |
| `installment_charge_statuses` | learningware | 課金 | K06 分割払いの台帳・入金記録 | commerce / 分割払い | マスタ | L7 |
| `installment_charges` | learningware | 課金 | K06 分割払いの台帳・入金記録 | commerce / 分割払い | データ | L7 |
| `installment_plan_statuses` | learningware | 課金 | K06 分割払いの台帳・入金記録 | commerce / 分割払い | マスタ | L7 |
| `installment_plans` | learningware | 課金 | K06 分割払いの台帳・入金記録 | commerce / 分割払い | データ | L7 |
| `interview_records` | career | 就職支援 | S06 面談（予約・記録） | interview | データ | — |
| `interviews` | career | 就職支援 | S06 面談（予約・記録） | interview | データ | — |
| `job_posting_skills` | career | 就職支援 | S01 求人の掲載・応募 | matching | データ | — |
| `job_postings` | career | 就職支援 | S01 求人の掲載・応募 | matching | データ | — |
| `learner_career_profiles` | career | 就職支援 | S05 就活プロフィール | matching | データ | — |
| `learner_career_skills` | career | 就職支援 | S05 就活プロフィール | matching | データ | — |
| `learner_skill_mastery` | learningware | 新規 | 新規（旧に対応なし） | badge | データ | — |
| `learner_subscription_event_kinds` | learningware | 課金 | K05 継続課金 | commerce / サブスクリプション・プラン | マスタ | — |
| `learner_subscription_status_events` | learningware | 課金 | K05 継続課金 | commerce / サブスクリプション・プラン | イベント・履歴 | — |
| `learner_subscription_statuses` | learningware | 課金 | K05 継続課金 | commerce / サブスクリプション・プラン | マスタ | — |
| `learner_subscriptions` | learningware | 課金 | K05 継続課金 | commerce / サブスクリプション・プラン | データ | — |
| `learning_behavior_event_kinds` | learningware | 新規 | 新規（旧に対応なし） | learning | マスタ | — |
| `learning_behavior_events` | learningware | 新規 | 新規（旧に対応なし） | learning | イベント・履歴 | — |
| `learning_goal_statuses` | learningware | 新規 | 新規（旧に対応なし） | learning | マスタ | — |
| `learning_goal_types` | learningware | 新規 | 新規（旧に対応なし） | learning | マスタ | — |
| `learning_goals` | learningware | 新規 | 新規（旧に対応なし） | learning | データ | — |
| `learning_path_courses` | learningware | 新規 | 新規（旧に対応なし） | learning | 中間 | — |
| `learning_paths` | learningware | 新規 | 新規（旧に対応なし） | learning | データ | — |
| `lesson_bookmarks` | learningware | 新規 | 新規（旧に対応なし） | note | データ | — |
| `lesson_note_tags` | learningware | 新規 | 新規（旧に対応なし） | note | データ | — |
| `lesson_notes` | learningware | 新規 | 新規（旧に対応なし） | note | データ | — |
| `lesson_progress` | learningware | 受講 | J02 ユニット進捗 | core / 受講登録・進捗 | データ | L4 |
| `lesson_types` | learningware | オンデマンド | O04 講義ユニット | core / コース・レッスン・スキル | マスタ | L2 |
| `lessons` | learningware | オンデマンド | O04 講義ユニット | core / コース・レッスン・スキル | データ | L2 |
| `library_audience_types` | learningware | オンデマンド | O21 教材添付・ライブラリ | library | マスタ | L8/L9 |
| `library_downloads` | learningware | オンデマンド | O21 教材添付・ライブラリ | library | イベント・履歴 | L8/L9 |
| `library_folder_course_targets` | learningware | オンデマンド | O21 教材添付・ライブラリ | library | 中間 | L8/L9 |
| `library_folder_user_targets` | learningware | オンデマンド | O21 教材添付・ライブラリ | library | 中間 | L8/L9 |
| `library_folders` | learningware | オンデマンド | O21 教材添付・ライブラリ | library | データ | L8/L9 |
| `library_material_kinds` | learningware | オンデマンド | O21 教材添付・ライブラリ | library | マスタ | L8/L9 |
| `library_materials` | learningware | オンデマンド | O21 教材添付・ライブラリ | library | データ | L8/L9 |
| `line_links` | learningware | 運営 | U06 LINE 連携・配信 | line | データ | L8 |
| `line_send_logs` | learningware | 運営 | U06 LINE 連携・配信 | line | イベント・履歴 | L8 |
| `live_lesson_occurrences` | learningware | ライブ | L02 開催日 | live | データ | L5 |
| `live_lesson_ticket_requirements` | learningware | ライブ | L05 チケット（付与・残高・予約消費） | ticket | データ | L6 |
| `live_lessons` | learningware | ライブ | L01 ライブ定義 | core / コース・レッスン・スキル | データ | L5 |
| `live_reservation_statuses` | learningware | ライブ | L03 予約・定員・キャンセル・出欠 | live | マスタ | L5 |
| `live_reservations` | learningware | ライブ | L03 予約・定員・キャンセル・出欠 | live | データ | L5 |
| `login_history` | learningware | 基盤 | B09 ログイン履歴 | core / ユーザー・認証・監査 | イベント・履歴 | — |
| `marketplace_license_event_kinds` | learningware | 新規 | 新規（旧に対応なし） | commerce / マーケットプレイス (テナント間のコース売買) | マスタ | — |
| `marketplace_license_events` | learningware | 新規 | 新規（旧に対応なし） | commerce / マーケットプレイス (テナント間のコース売買) | イベント・履歴 | — |
| `marketplace_license_payments` | learningware | 新規 | 新規（旧に対応なし） | commerce / マーケットプレイス (テナント間のコース売買) | データ | — |
| `marketplace_license_revoke_reasons` | learningware | 新規 | 新規（旧に対応なし） | commerce / マーケットプレイス (テナント間のコース売買) | マスタ | — |
| `marketplace_license_statuses` | learningware | 新規 | 新規（旧に対応なし） | commerce / マーケットプレイス (テナント間のコース売買) | マスタ | — |
| `marketplace_licenses` | learningware | 新規 | 新規（旧に対応なし） | commerce / マーケットプレイス (テナント間のコース売買) | データ | — |
| `marketplace_listing_statuses` | learningware | 新規 | 新規（旧に対応なし） | commerce / マーケットプレイス (テナント間のコース売買) | マスタ | — |
| `marketplace_listings` | learningware | 新規 | 新規（旧に対応なし） | commerce / マーケットプレイス (テナント間のコース売買) | データ | — |
| `match_notes` | career | 新規 | 新規（旧に対応なし） | matching | データ | — |
| `match_scores` | career | 新規 | 新規（旧に対応なし） | matching | データ | — |
| `matches` | career | 新規 | 新規（旧に対応なし） | matching | データ | — |
| `notification_optouts` | learningware | 運営 | U07 メールテンプレート | notification | 中間 | — |
| `payment_dispute_reasons` | learningware | 新規 | 新規（旧に対応なし） | commerce / 決済・返金・チャージバック | マスタ | — |
| `payment_dispute_statuses` | learningware | 新規 | 新規（旧に対応なし） | commerce / 決済・返金・チャージバック | マスタ | — |
| `payment_disputes` | learningware | 新規 | 新規（旧に対応なし） | commerce / 決済・返金・チャージバック | データ | — |
| `payment_event_kinds` | learningware | 課金 | K02 クレジット決済 | commerce / 決済・返金・チャージバック | マスタ | L0/L7 |
| `payment_providers` | learningware | 課金 | K02 クレジット決済 | commerce / 分割払い | マスタ | L0/L7 |
| `payment_refund_reasons` | learningware | 課金 | K02 クレジット決済 | commerce / 決済・返金・チャージバック | マスタ | L0/L7 |
| `payment_status_events` | learningware | 課金 | K02 クレジット決済 | commerce / 決済・返金・チャージバック | イベント・履歴 | L0/L7 |
| `payment_statuses` | learningware | 課金 | K02 クレジット決済 | commerce / 決済・返金・チャージバック | マスタ | L0/L7 |
| `payment_types` | learningware | 課金 | K02 クレジット決済 | commerce / 決済・返金・チャージバック | マスタ | L0/L7 |
| `payments` | learningware | 課金 | K02 クレジット決済 | commerce / 決済・返金・チャージバック | データ | L0/L7 |
| `plan_courses` | learningware | 課金 | K05 継続課金 | commerce / サブスクリプション・プラン | 中間 | — |
| `plan_intervals` | learningware | 課金 | K05 継続課金 | commerce / サブスクリプション・プラン | マスタ | — |
| `plan_statuses` | learningware | 課金 | K05 継続課金 | commerce / サブスクリプション・プラン | マスタ | — |
| `plan_types` | learningware | 課金 | K05 継続課金 | commerce / サブスクリプション・プラン | マスタ | — |
| `platform_plans` | learningware | 新規 | 新規（旧に対応なし） | core / テナント・プラットフォーム・運営メモ | データ | — |
| `provider_webhook_events` | learningware | 課金 | K02 クレジット決済 | commerce / 決済・返金・チャージバック | イベント・履歴 | L0/L7 |
| `quiz_answer_selected_options` | learningware | オンデマンド | O10 テスト設問別回答（選択式） | quiz | 中間 | L4 |
| `quiz_answers` | learningware | オンデマンド | O10 テスト設問別回答（選択式） | quiz | データ | L4 |
| `quiz_attempt_event_kinds` | learningware | オンデマンド | O09 テスト受験（合否・得点） | quiz | マスタ | L4 |
| `quiz_attempt_events` | learningware | オンデマンド | O09 テスト受験（合否・得点） | quiz | イベント・履歴 | L4 |
| `quiz_attempt_statuses` | learningware | オンデマンド | O09 テスト受験（合否・得点） | quiz | マスタ | L4 |
| `quiz_attempts` | learningware | オンデマンド | O09 テスト受験（合否・得点） | quiz | データ | L4 |
| `quiz_options` | learningware | オンデマンド | O08 テスト定義 | quiz | データ | L2 |
| `quiz_question_types` | learningware | オンデマンド | O08 テスト定義 | quiz | マスタ | L2 |
| `quiz_questions` | learningware | オンデマンド | O08 テスト定義 | quiz | データ | L2 |
| `quizzes` | learningware | オンデマンド | O08 テスト定義 | quiz | データ | L2 |
| `receipt_settings` | learningware | 課金 | K08 領収書 | receipt | 設定 | L0/L7 |
| `receipts` | learningware | 課金 | K08 領収書 | receipt | データ | L0/L7 |
| `referral_codes` | learningware | 新規 | 新規（旧に対応なし） | referral | データ | — |
| `referral_rewards` | learningware | 新規 | 新規（旧に対応なし） | referral | データ | — |
| `referral_statuses` | learningware | 新規 | 新規（旧に対応なし） | referral | マスタ | — |
| `referrals` | learningware | 新規 | 新規（旧に対応なし） | referral | データ | — |
| `refund_payments` | learningware | 課金 | K02 クレジット決済 | commerce / 決済・返金・チャージバック | データ | L0/L7 |
| `remote_pc_blackouts` | learningware | オンデマンド | O28 リモート PC | remotepc | データ | — |
| `remote_pc_machines` | learningware | オンデマンド | O28 リモート PC | remotepc | データ | — |
| `remote_pc_reservation_statuses` | learningware | オンデマンド | O28 リモート PC | remotepc | マスタ | — |
| `remote_pc_reservations` | learningware | オンデマンド | O28 リモート PC | remotepc | データ | — |
| `retention_rules` | learningware | 運営 | U05 フォローメール | retention | データ | — |
| `retention_sends` | learningware | 運営 | U05 フォローメール | retention | データ | — |
| `retention_trigger_kinds` | learningware | 運営 | U05 フォローメール | retention | マスタ | — |
| `review_report_reasons` | learningware | 新規 | 新規（旧に対応なし） | core / コースレビュー | マスタ | — |
| `skill_categories` | skill_passport | 新規 | 新規（旧に対応なし） | core | マスタ | — |
| `skill_evaluations` | skill_passport | 新規 | 新規（旧に対応なし） | core | データ | — |
| `skill_mastery_history` | learningware | 新規 | 新規（旧に対応なし） | badge | イベント・履歴 | — |
| `skill_proficiency_levels` | learningware | 新規 | 新規（旧に対応なし） | core / コース・レッスン・スキル | マスタ | — |
| `skills` | skill_passport | 新規 | 新規（旧に対応なし） | core | マスタ | — |
| `skills_cache` | learningware | 新規 | 新規（旧に対応なし） | core / コース・レッスン・スキル | データ | — |
| `specified_continuous_service_categories` | learningware | 課金 | K05 継続課金 | commerce / サブスクリプション・プラン | マスタ | — |
| `submission_feedbacks` | learningware | オンデマンド | O18 課題（定義・提出・添削） | assignment | データ | L2/L4 |
| `submission_status_events` | learningware | オンデマンド | O18 課題（定義・提出・添削） | assignment | イベント・履歴 | L2/L4 |
| `submissions` | learningware | オンデマンド | O18 課題（定義・提出・添削） | assignment | データ | L2/L4 |
| `subscription_cancellation_settlements` | learningware | 課金 | K05 継続課金 | commerce / サブスクリプション・プラン | データ | — |
| `subscription_payments` | learningware | 課金 | K05 継続課金 | commerce / サブスクリプション・プラン | データ | — |
| `survey_answer_selected_options` | learningware | オンデマンド | O14 ユニットアンケート（定義・回答） | survey | 中間 | L2/L4 |
| `survey_answers` | learningware | オンデマンド | O14 ユニットアンケート（定義・回答） | survey | データ | L2/L4 |
| `survey_lessons` | learningware | オンデマンド | O14 ユニットアンケート（定義・回答） | survey | データ | L2/L4 |
| `survey_question_kinds` | learningware | オンデマンド | O14 ユニットアンケート（定義・回答） | survey | マスタ | L2/L4 |
| `survey_question_options` | learningware | オンデマンド | O14 ユニットアンケート（定義・回答） | survey | データ | L2/L4 |
| `survey_questions` | learningware | オンデマンド | O14 ユニットアンケート（定義・回答） | survey | データ | L2/L4 |
| `survey_responses` | learningware | オンデマンド | O14 ユニットアンケート（定義・回答） | survey | データ | L2/L4 |
| `survey_submission_log` | learningware | オンデマンド | O14 ユニットアンケート（定義・回答） | survey | 中間 | L2/L4 |
| `tenant_db_types` | learningware | 基盤 | B01 テナント | core / テナント・プラットフォーム・運営メモ | マスタ | — |
| `tenant_email_templates` | learningware | 運営 | U07 メールテンプレート | notification | データ | — |
| `tenant_plans` | learningware | 課金 | K05 継続課金 | commerce / サブスクリプション・プラン | データ | — |
| `tenant_secret_kinds` | learningware | 基盤 | B01 テナント | core / テナント・プラットフォーム・運営メモ | マスタ | — |
| `tenant_secrets` | learningware | 基盤 | B01 テナント | core / テナント・プラットフォーム・運営メモ | データ | — |
| `tenant_statuses` | learningware | 基盤 | B01 テナント | core / テナント・プラットフォーム・運営メモ | マスタ | — |
| `tenant_webhook_status_event_kinds` | learningware | 新規 | 新規（旧に対応なし） | webhook | マスタ | — |
| `tenant_webhook_status_events` | learningware | 新規 | 新規（旧に対応なし） | webhook | イベント・履歴 | — |
| `tenant_webhook_subscriptions` | learningware | 新規 | 新規（旧に対応なし） | webhook | 中間 | — |
| `tenant_webhooks` | learningware | 新規 | 新規（旧に対応なし） | webhook | データ | — |
| `tenants` | learningware | 基盤 | B01 テナント | core / テナント・プラットフォーム・運営メモ | データ | — |
| `ticket_grant_sources` | learningware | ライブ | L05 チケット（付与・残高・予約消費） | ticket | マスタ | L6 |
| `ticket_grants` | learningware | ライブ | L05 チケット（付与・残高・予約消費） | ticket | データ | L6 |
| `ticket_ledger_entries` | learningware | ライブ | L07 チケット消費台帳の再生 | ticket | データ | L6 |
| `ticket_ledger_kinds` | learningware | ライブ | L07 チケット消費台帳の再生 | ticket | マスタ | L6 |
| `ticket_type_lessons` | learningware | ライブ | L05 チケット（付与・残高・予約消費） | ticket | 中間 | L6 |
| `ticket_types` | learningware | ライブ | L05 チケット（付与・残高・予約消費） | ticket | マスタ | L6 |
| `user_consents` | learningware | 課金 | K12 特商法・規約 | core / ユーザー・認証・監査 | データ | — |
| `user_identities` | skill_passport | 新規 | 新規（旧に対応なし） | core | データ | — |
| `user_identity_links` | skill_passport | 新規 | 新規（旧に対応なし） | core | データ | — |
| `user_match_statuses` | learningware | 新規 | 新規（旧に対応なし） | core / AI チャット・ヘルプ・Google Chat 連携 | マスタ | — |
| `user_passkeys` | learningware | 新規 | 新規（旧に対応なし） | core / ユーザー・認証・監査 | データ | — |
| `user_preferences` | learningware | 基盤 | B06 会員プロフィール（氏名・生年・電話） | core / ユーザー・認証・監査 | 設定 | L1 |
| `user_profiles` | skill_passport | 新規 | 新規（旧に対応なし） | core | データ | — |
| `user_roles` | learningware | 基盤 | B02 ロール（管理者 / 講師 / 受講者） | core / ユーザー・認証・監査 | マスタ | — |
| `user_skill_summaries` | skill_passport | 新規 | 新規（旧に対応なし） | core | データ | — |
| `user_statuses` | learningware | 基盤 | B06 会員プロフィール（氏名・生年・電話） | core / ユーザー・認証・監査 | マスタ | L1 |
| `users` | learningware | 基盤 | B06 会員プロフィール（氏名・生年・電話） | core / ユーザー・認証・監査 | データ | L1 |
| `verification_logs` | skill_passport | 新規 | 新規（旧に対応なし） | core | イベント・履歴 | — |
| `video_lessons` | learningware | オンデマンド | O06 講義動画（p-movie / 自前） | core / コース・レッスン・スキル | データ | L2/L9 |
| `webhook_delivery_attempts` | learningware | 新規 | 新規（旧に対応なし） | webhook | データ | — |
| `webhook_delivery_statuses` | learningware | 新規 | 新規（旧に対応なし） | webhook | マスタ | — |
| `webhook_event_kinds` | learningware | 新規 | 新規（旧に対応なし） | webhook | マスタ | — |
| `webhook_events` | learningware | 新規 | 新規（旧に対応なし） | webhook | データ | — |
