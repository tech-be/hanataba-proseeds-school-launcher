# 旧環境（lw2）テーブル逆引き — 全342件

learningware-kiracari の `docs/db/lw2/tables/*.md` にある **342テーブル全件**を、PDF のデータ種へ割り当てたもの。[データ種別対照表](data-type-mapping.md) の逆引き。

## 列の意味

| 列 | 出どころ |
|---|---|
| テーブル | `learningware-kiracari/docs/db/lw2/tables/<name>.md` |
| 区分 / データ種 | 本作業の割り当て結果。`未分類` は PDF の 95 データ種に該当しないもの |
| 副データ種 | 1テーブルが複数データ種にまたがる場合の従たる割り当て（ポリモーフィック列・種別カラムによる分岐） |
| BC / lw2区分 | lw2 側 `docs/db` の「BC」「区分」行をそのまま |
| ローカルデータ数 / A·B·C | **定義は [README.md](README.md#共通の列の意味) を参照。** `school-launcher/docs/lw2-migration-tables.md`（2026-07-28 ダンプの実測）由来。**ローカルデータ数は全73テナントの合計値**で recademy 単体ではない。A=純ログ / B=要判断 / C=移行対象 |
| 根拠 | `PDF記載(...)` = PDF の「既存の主なテーブル」列に名前がある / `関連(推定)` = lw2 の関連・被参照から引き寄せた / `ETL設計...` = `scrun-etl-design.md` の記述 / それ以外は未分類の理由 |

## 集計

### 区分別

| 区分 | テーブル数 |
|---|---:|
| 運営 | 63 |
| 就職支援 | 56 |
| オンデマンド | 45 |
| 基盤 | 32 |
| 課金 | 24 |
| ライブ | 20 |
| 対象外 | 19 |
| 受講 | 16 |
| **未分類** | **67** |
| **合計** | **342** |

### 未分類 67 件の内訳

| 理由 | 件数 | 意味 |
|---|---:|---|
| 該当なし | 27 | PDF の 95 データ種のどれにも当てはまらない機能。**PDF の粒度から漏れている機能の一覧**であり、移行スコープを詰めるときに最初に見るべきもの |
| 機能設定 | 16 | テナント/管理機能の ON/OFF、トップページ構成など |
| 共通マスタ | 9 | 国・都道府県・言語・翻訳・絵文字などデータ種に紐づかない共通コード |
| 一時 | 8 | セッション・集計用の一時テーブル（`php_session` / `temp_*` / `tmp_*`） |
| 純ログ | 7 | `lw2-migration-tables.md` の A 区分と一致するもの |

## 全342件

| テーブル | 区分 | データ種 | 副データ種 | BC | lw2区分 | ローカルデータ数 | A·B·C | 根拠 |
|---|---|---|---|---|---|---:|:--:|---|
| `access_log` | 未分類 | 未分類 / 純ログ | — | auth | イベント・履歴 | 696,319 | A | A区分(純ログ) |
| `account_setting` | 未分類 | 未分類 / 機能設定 | — | auth | 設定 | 64 | C | アカウント設定 |
| `accounting_user` | 未分類 | 未分類 / 該当なし | — | payment | データ | 2,403 | C | テナント課金集計(LMS事業者向け) |
| `accounting_user_detail` | 未分類 | 未分類 / 該当なし | — | payment | データ | 192,053 | C | テナント課金集計(LMS事業者向け) |
| `agreement` | 課金 | K12 特商法・規約 | — | payment | データ | 53 | C | 規約設定 |
| `analytics_tag` | 課金 | K13 流入元計測 | — | tenant | データ | 77 | C | PDF記載(解析タグ) |
| `analytics_tag_display` | 課金 | K13 流入元計測 | — | tenant | データ | 127 | C | 関連(推定) |
| `announce` | 運営 | U01 お知らせ / アナウンス配信 | — | news | データ | 441 | C | PDF記載(announce) |
| `announce_user` | 運営 | U02 お知らせ既読 | — | news | データ | 192,408 | C | PDF記載(announce_user) |
| `application_config` | 未分類 | 未分類 / 機能設定 | — | tenant | 設定 | 32 | C | テナント機能設定 |
| `application_user_learning_lesson` | 受講 | J01 受講権限 | — | learning | データ | 0 | C | 関連(推定) |
| `assign` | 受講 | J04 購入時自動割当（講座・お知らせ・クーポン） | — | lesson | データ | 603 | C | PDF記載(assign) |
| `assign_attribute` | 受講 | J05 自動割当（グループ・属性条件） | — | lesson | 中間 | 202 | C | PDF記載(assign_attribute) |
| `assign_group` | 受講 | J05 自動割当（グループ・属性条件） | — | lesson | 中間 | 6 | C | PDF記載(assign_group) |
| `assign_item` | 受講 | J04 購入時自動割当（講座・お知らせ・クーポン） | J06 自動割当（求人） | lesson | データ | 888 | C | PDF記載(assign_item) |
| `assign_log` | 受講 | J04 購入時自動割当（講座・お知らせ・クーポン） | — | lesson | イベント・履歴 | 615,893 | B | 関連(推定) |
| `assign_payment_item` | 受講 | J04 購入時自動割当（講座・お知らせ・クーポン） | — | lesson | 中間 | 843 | C | PDF記載(assign_payment_item) |
| `attribute` | 基盤 | B08 属性 | — | user | データ | 427 | C | PDF記載(attribute) |
| `attribute_lesson` | 基盤 | B08 属性 | — | user | データ | 332 | C | PDF記載(attribute_lesson) |
| `badge_item` | オンデマンド | O27 バッジ | — | certificate | データ | 91 | C | PDF記載(badge_item) |
| `batch_schedule` | 未分類 | 未分類 / 該当なし | — | operation | データ | 19 | C | バッチ実行管理 |
| `batch_schedule_detail` | 未分類 | 未分類 / 該当なし | — | operation | データ | 19 | C | バッチ実行管理 |
| `batch_schedule_log` | 未分類 | 未分類 / 純ログ | — | operation | イベント・履歴 | 13,644 | A | A区分(純ログ) |
| `bbs` | 運営 | U11 掲示板 | — | community | データ | 14,287 | C | PDF記載(bbs) |
| `bbs_comment` | 運営 | U11 掲示板 | — | community | データ | 11,030 | C | PDF記載(bbs_comment) |
| `bbs_set_attribute` | 運営 | U11 掲示板 | — | community | 中間 | 4,129 | C | PDF記載(bbs_set_*) |
| `bbs_set_group` | 運営 | U11 掲示板 | — | community | 中間 | 235 | C | PDF記載(bbs_set_*) |
| `bbs_set_lesson` | 運営 | U11 掲示板 | — | community | 中間 | 104 | C | PDF記載(bbs_set_*) |
| `bbs_set_payment_item` | 運営 | U11 掲示板 | — | community | 中間 | 179 | C | PDF記載(bbs_set_*) |
| `bbs_set_role` | 運営 | U11 掲示板 | — | community | 中間 | 180 | C | PDF記載(bbs_set_*) |
| `calc_param` | 未分類 | 未分類 / 該当なし | — | learning | データ | 10 | C | テスト成績集計 |
| `cancel_policy` | 課金 | K12 特商法・規約 | — | payment | データ | 29 | C | 規約設定 |
| `category_question_result` | 未分類 | 未分類 / 該当なし | — | learning | データ | 11 | C | テスト成績集計 |
| `certificate` | オンデマンド | O25 修了証（講座単位） | — | certificate | データ | 15 | C | 関連(推定) |
| `certificate_no` | オンデマンド | O25 修了証（講座単位） | — | certificate | 設定 | 10 | C | ETL設計5-7 |
| `code_master` | 未分類 | 未分類 / 共通マスタ | — | tenant | マスタ | 35 | C | 共通コードマスタ |
| `community_cate` | 未分類 | 未分類 / 該当なし | — | community | データ | 203 | C | コミュニティカテゴリ |
| `company` | 就職支援 | S02 求人企業ページ | — | user | データ | 143 | C | PDF記載(company) |
| `config_certificate` | オンデマンド | O25 修了証（講座単位） | — | certificate | 設定 | 3 | C | 関連(推定) |
| `config_closing_date` | 未分類 | 未分類 / 該当なし | — | payment | 設定 | 64 | C | テナント課金集計(LMS事業者向け) |
| `config_cookie` | 未分類 | 未分類 / 該当なし | — | auth | 設定 | - |  | クッキー同意 |
| `config_inquire` | 運営 | U08 問い合わせ | — | inquiry | 設定 | 1 | C | 関連(推定) |
| `config_live_lesson` | ライブ | L03 予約・定員・キャンセル・出欠 | — | live | 設定 | 64 | C | キャンセル期限の由来(ETL設計5-6) |
| `config_skill_unit` | 就職支援 | S07 スキルチェック | — | lesson | 設定 | 63 | C | スキル診断設定 |
| `content_master` | 未分類 | 未分類 / 共通マスタ | — | community | マスタ | 3 | C | 既読管理コンテンツマスタ |
| `country_master` | 未分類 | 未分類 / 共通マスタ | — | user | マスタ | 193 | C | 共通コードマスタ |
| `coupon` | 課金 | K10 クーポン | — | payment | データ | 533 | C | PDF記載(coupon) |
| `coupon_group` | 課金 | K11 クーポン対象者割当 | — | payment | データ | 15 | C | 関連(推定) |
| `coupon_item` | 課金 | K10 クーポン | — | payment | データ | 6,493 | C | 関連(推定) |
| `coupon_live_lesson` | ライブ | L09 ライブ限定クーポン | — | payment | データ | 10 | C | PDF記載(ライブ紐付けクーポン) |
| `coupon_log` | 課金 | K10 クーポン | — | payment | イベント・履歴 | 1,155 | B | 関連(推定) |
| `coupon_user` | 課金 | K11 クーポン対象者割当 | — | payment | データ | 583,943 | C | PDF記載(coupon_user) |
| `csv_request` | 未分類 | 未分類 / 該当なし | — | operation | データ | 0 | B | CSV一括登録 |
| `debug_trace` | 未分類 | 未分類 / 純ログ | — | operation | データ | 0 | A | A区分(純ログ) |
| `discussion` | 未分類 | 未分類 / 該当なし | — | lesson | データ | 31 | C | ディスカッション |
| `discussion_board` | 未分類 | 未分類 / 該当なし | — | lesson | データ | 13 | C | ディスカッション |
| `discussion_board_comment` | 未分類 | 未分類 / 該当なし | — | community | データ | 122 | C | ディスカッション |
| `display_master` | 未分類 | 未分類 / 共通マスタ | — | tenant | マスタ | 15 | C | 共通コードマスタ |
| `document_file_detail` | オンデマンド | O21 教材添付・ライブラリ | — | document | データ | 761 | C | PDF記載(document) |
| `drive` | オンデマンド | O21 教材添付・ライブラリ | — | document | データ | 111 | C | PDF記載(drive) |
| `drive_group` | オンデマンド | O21 教材添付・ライブラリ | — | document | 中間 | 429 | C | 関連(推定) |
| `edit_form_data` | 基盤 | B06 会員プロフィール（氏名・生年・電話） | — | user | データ | 4,752 | B | 登録フォームデータ |
| `emoji_master` | 未分類 | 未分類 / 共通マスタ | — | tenant | マスタ | 197 | C | 共通コードマスタ |
| `employment_status_master` | 就職支援 | S05 就活プロフィール | — | user | マスタ | 4 | C | 就活プロフィール項目 |
| `enquete` | オンデマンド | O14 ユニットアンケート（定義・回答） | — | survey | データ | 7,414 | C | PDF記載(enquete) |
| `enquete_answer` | オンデマンド | O14 ユニットアンケート（定義・回答） | O16 お知らせ添付アンケート, O17 レポート添付アンケート | survey | データ | 64,883 | C | PDF記載(enquete_answer) |
| `enquete_page` | オンデマンド | O14 ユニットアンケート（定義・回答） | — | survey | データ | 8,311 | C | 関連(推定) |
| `enquete_question` | オンデマンド | O14 ユニットアンケート（定義・回答） | O15 アンケートのファイル添付設問 | survey | データ | 11,179 | C | PDF記載(enquete_question) |
| `entire_question_result` | 未分類 | 未分類 / 該当なし | — | learning | データ | 110 | C | テスト成績集計 |
| `entire_test_result` | 未分類 | 未分類 / 該当なし | — | learning | データ | 8 | C | テスト成績集計 |
| `entitiestags` | 就職支援 | S04 ポートフォリオ | — | portfolio | データ | 3,828 | C | ポートフォリオのタグ |
| `ex_training` | 対象外 | X01 集合研修 | — | learning | データ | 112 | C | PDF記載(ex_training) |
| `ex_training_cate` | 対象外 | X01 集合研修 | — | learning | データ | 22 | C | 関連(推定) |
| `ex_training_record` | 対象外 | X01 集合研修 | — | learning | データ | 103 | C | 関連(推定) |
| `facility` | 対象外 | X01 集合研修 | — | live | データ | 14 | C | PDF記載(facility) |
| `file_download_log` | 未分類 | 未分類 / 純ログ | — | document | イベント・履歴 | 11,980 | A | A区分(純ログ) |
| `follow` | 未分類 | 未分類 / 該当なし | — | community | データ | 382 | C | フォロー |
| `footprint` | 運営 | U13 足あと | — | community | データ | 10,418 | B | PDF記載(footprint) |
| `function_admin_master` | 未分類 | 未分類 / 機能設定 | — | tenant | マスタ | 224 | C | 管理機能のON/OFF |
| `function_admin_role` | 未分類 | 未分類 / 機能設定 | — | tenant | データ | 227 | C | 管理機能のON/OFF |
| `function_admin_tenant` | 未分類 | 未分類 / 機能設定 | — | tenant | データ | 2,524 | C | 管理機能のON/OFF |
| `function_admin_user` | 未分類 | 未分類 / 機能設定 | — | tenant | データ | 0 | C | 管理機能のON/OFF |
| `function_default_master` | 未分類 | 未分類 / 機能設定 | — | tenant | マスタ | 42 | C | 受講者機能のON/OFF |
| `function_default_tenant` | 未分類 | 未分類 / 機能設定 | — | tenant | データ | 2,687 | C | 受講者機能のON/OFF |
| `group` | 基盤 | B07 グループ | — | user | データ | 1,009 | C | PDF記載(group) |
| `group_structure` | 基盤 | B07 グループ | — | user | 中間 | 1,313 | C | PDF記載(group_structure) |
| `hosting_capacity` | 未分類 | 未分類 / 機能設定 | — | tenant | データ | - |  | テナント容量 |
| `inquire` | 運営 | U08 問い合わせ | — | inquiry | データ | 14,072 | C | PDF記載(inquire) |
| `inquire_answer` | 運営 | U08 問い合わせ | U09 問い合わせ添付ファイル | inquiry | データ | 14,426 | C | PDF記載(inquire_answer) |
| `inquire_cate` | 運営 | U08 問い合わせ | — | inquiry | データ | 212 | C | ETL設計5-8 |
| `inquire_user` | 運営 | U08 問い合わせ | — | inquiry | データ | 2,099 | C | 関連(推定) |
| `instructor_set_attribute` | 基盤 | B02 ロール（管理者 / 講師 / 受講者） | — | lesson | 中間 | 11 | C | 講師の担当範囲 |
| `instructor_set_group` | 基盤 | B02 ロール（管理者 / 講師 / 受講者） | — | lesson | 中間 | 19 | C | 講師の担当範囲 |
| `instructor_set_lesson` | 基盤 | B02 ロール（管理者 / 講師 / 受講者） | — | lesson | 中間 | 118 | C | 講師の担当範囲 |
| `interview_contents` | 就職支援 | S06 面談（予約・記録） | — | live | データ | 1,280 | C | 関連(推定) |
| `interview_record` | 就職支援 | S06 面談（予約・記録） | — | live | データ | 386 | C | PDF記載(interview_record) |
| `interview_status` | 就職支援 | S06 面談（予約・記録） | — | live | データ | 23 | C | 関連(推定) |
| `job_career` | 就職支援 | S05 就活プロフィール | — | user | データ | 3,857 | C | PDF記載(職歴) |
| `job_category_master` | 就職支援 | S05 就活プロフィール | — | career | マスタ | 11 | C | 希望職種 |
| `job_category_setting` | 就職支援 | S05 就活プロフィール | — | career | 設定 | 706 | C | 希望職種 |
| `language_master` | 未分類 | 未分類 / 共通マスタ | — | user | マスタ | 13 | C | 共通コードマスタ |
| `lecture` | オンデマンド | O04 講義ユニット | O06 講義動画（p-movie / 自前） | lesson | データ | 26,402 | C | PDF記載(lecture) |
| `lecture_path` | オンデマンド | O04 講義ユニット | — | lesson | データ | 26,953 | C | 関連(推定) |
| `lecture_path_test` | オンデマンド | O04 講義ユニット | — | lesson | データ | - |  | 関連(推定) |
| `lesson` | オンデマンド | O01 講座 | O03 講座サムネ | lesson | データ | 2,208 | C | PDF記載(lesson) |
| `lesson_attached_file` | オンデマンド | O21 教材添付・ライブラリ | — | lesson | データ | 0 | C | 講座添付資料 |
| `lesson_attached_file_attribute` | オンデマンド | O21 教材添付・ライブラリ | — | lesson | 中間 | 0 | C | 関連(推定) |
| `lesson_attached_file_group` | オンデマンド | O21 教材添付・ライブラリ | — | lesson | 中間 | 0 | C | 関連(推定) |
| `lesson_cate` | オンデマンド | O02 講座カテゴリ | — | lesson | データ | 482 | C | PDF記載(lesson_cate) |
| `lesson_inquiry_user` | 運営 | U08 問い合わせ | — | lesson | 中間 | 0 | C | 講座の問い合わせ担当 |
| `lesson_is_used` | オンデマンド | O01 講座 | — | lesson | データ | 2,066 | C | 関連(推定) |
| `lesson_lesson_tag` | オンデマンド | O01 講座 | — | lesson | 中間 | 281 | C | 関連(推定) |
| `lesson_system` | オンデマンド | O01 講座 | — | lesson | データ | 243 | C | 関連(推定) |
| `lesson_tag` | オンデマンド | O01 講座 | — | lesson | データ | 31 | C | 関連(推定) |
| `like` | 就職支援 | S04 ポートフォリオ | — | portfolio | データ | 15,506 | C | ポートフォリオのいいね |
| `like_user` | 未分類 | 未分類 / 該当なし | — | community | データ | 27,117 | C | いいね |
| `line_message` | 運営 | U06 LINE 連携・配信 | — | notification | データ | 1,310 | C | 関連(推定) |
| `line_message_mail_follow_setting` | 運営 | U06 LINE 連携・配信 | — | notification | データ | 96 | C | 関連(推定) |
| `line_message_mail_setting` | 運営 | U06 LINE 連携・配信 | — | notification | 設定 | 58 | C | 関連(推定) |
| `line_message_recruit` | 運営 | U06 LINE 連携・配信 | — | notification | データ | 23 | C | 関連(推定) |
| `line_send` | 運営 | U06 LINE 連携・配信 | — | notification | データ | 12,798 | B | 関連(推定) |
| `line_send_batch` | 運営 | U06 LINE 連携・配信 | — | notification | データ | 183,739 | B | 関連(推定) |
| `line_send_batch_log` | 運営 | U06 LINE 連携・配信 | — | notification | イベント・履歴 | 34,997 | A | 関連(推定) |
| `line_send_user` | 運営 | U06 LINE 連携・配信 | — | notification | データ | 2,127 | B | PDF記載(line_send_user) |
| `line_send_user_log` | 運営 | U06 LINE 連携・配信 | — | notification | イベント・履歴 | 218,736 | A | 関連(推定) |
| `link` | 対象外 | X04 外部リンク集 | — | document | データ | 101 | C | PDF記載(link) |
| `link_attribute` | 対象外 | X04 外部リンク集 | — | document | 中間 | 33 | C | PDF記載(link_attribute) |
| `link_group` | 対象外 | X04 外部リンク集 | — | document | 中間 | 6 | C | PDF記載(link_group) |
| `link_lesson` | 対象外 | X04 外部リンク集 | — | document | 中間 | 181 | C | PDF記載(link_lesson) |
| `live_lesson` | ライブ | L01 ライブ定義 | — | live | データ | 746 | C | PDF記載(live_lesson) |
| `live_lesson_batch_log` | 未分類 | 未分類 / 純ログ | — | live | データ | 52,038 | A | A区分(純ログ) |
| `live_lesson_cate` | ライブ | L01 ライブ定義 | — | live | データ | 65 | C | ETL設計5-6(受け皿course) |
| `live_lesson_date` | ライブ | L02 開催日 | — | live | データ | 23,324 | C | PDF記載(live_lesson_date) |
| `live_lesson_date_preview` | ライブ | L02 開催日 | — | live | データ | 134 | C | 関連(推定) |
| `live_lesson_date_setting` | ライブ | L02 開催日 | — | live | データ | 3,840 | C | 関連(推定) |
| `live_lesson_date_setting_detail` | ライブ | L02 開催日 | — | live | データ | 1,152 | C | 関連(推定) |
| `live_lesson_exclusion_date` | ライブ | L02 開催日 | — | live | データ | 1,096 | C | 関連(推定) |
| `live_lesson_group` | ライブ | L01 ライブ定義 | — | live | データ | 160 | C | 関連(推定) |
| `live_lesson_lesson_cate` | ライブ | L01 ライブ定義 | — | live | 中間 | 614 | C | 関連(推定) |
| `live_lesson_limit_item` | ライブ | L01 ライブ定義 | — | live | データ | 17,345 | C | 関連(推定) |
| `live_lesson_preview` | ライブ | L01 ライブ定義 | — | live | データ | 15 | C | 関連(推定) |
| `live_lesson_reserve` | ライブ | L03 予約・定員・キャンセル・出欠 | — | live | データ | 18,041 | C | PDF記載(live_lesson_reserve) |
| `live_lesson_review` | ライブ | L08 ライブレビュー | — | live | データ | 10 | C | PDF記載(live_lesson_review) |
| `login_dialog_log` | 運営 | U04 ログイン後モーダル | — | auth | イベント・履歴 | 2,225 | A | PDF記載(login_dialog_log) |
| `login_limit` | 基盤 | B09 ログイン履歴 | — | auth | データ | 0 | B | login系 |
| `login_setting` | 未分類 | 未分類 / 機能設定 | — | auth | 設定 | 64 | C | ログイン画面文言 |
| `mail_follow_setting` | 運営 | U05 フォローメール | — | notification | データ | 387 | C | PDF記載(mail_follow_setting) |
| `mail_follow_setting_attribute` | 運営 | U05 フォローメール | — | notification | 中間 | 208 | C | 関連(推定) |
| `mail_follow_setting_group` | 運営 | U05 フォローメール | — | notification | 中間 | 45 | C | 関連(推定) |
| `mail_follow_user_log` | 運営 | U05 フォローメール | — | notification | イベント・履歴 | 188,310 | A | PDF記載(mail_follow_user_log) |
| `mail_footer` | 運営 | U07 メールテンプレート | — | notification | 設定 | 64 | C | メール設定 |
| `mail_send` | 運営 | U07 メールテンプレート | — | notification | データ | 402,243 | B | メール設定 |
| `mail_send_batch` | 運営 | U07 メールテンプレート | — | notification | データ | 0 | B | メール設定 |
| `mail_send_batch_log` | 運営 | U07 メールテンプレート | — | notification | イベント・履歴 | 2,049,243 | A | メール設定 |
| `mail_send_user` | 運営 | U07 メールテンプレート | — | notification | データ | 13,798 | B | メール設定 |
| `mail_send_user_log` | 運営 | U07 メールテンプレート | — | notification | イベント・履歴 | 2,120,331 | A | メール設定 |
| `mail_setting` | 運営 | U07 メールテンプレート | — | notification | 設定 | 412 | C | PDF記載(メール設定) |
| `mail_setting_role` | 運営 | U07 メールテンプレート | — | notification | 中間 | 0 | C | メール設定 |
| `mail_setting_user` | 運営 | U07 メールテンプレート | — | notification | 中間 | 2,578 | C | メール設定 |
| `mail_template` | 運営 | U07 メールテンプレート | — | notification | データ | 165 | C | PDF記載(メールテンプレート) |
| `mail_template_group` | 運営 | U07 メールテンプレート | — | notification | データ | 33 | C | 関連(推定) |
| `mail_type_master` | 運営 | U07 メールテンプレート | — | notification | マスタ | 78 | C | メール設定 |
| `message_send` | 運営 | U14 Web Push | — | notification | データ | 527 | B | プッシュ通知送信(PDFはU10に記載) |
| `message_send_batch` | 運営 | U14 Web Push | — | notification | データ | 0 | B | プッシュ通知送信(PDFはU10に記載) |
| `message_send_batch_log` | 運営 | U14 Web Push | — | notification | イベント・履歴 | 22,398 | A | プッシュ通知送信(PDFはU10に記載) |
| `message_send_user` | 運営 | U14 Web Push | — | notification | データ | 32,019 | B | プッシュ通知送信(PDFはU10に記載) |
| `message_send_user_log` | 運営 | U14 Web Push | — | notification | イベント・履歴 | 22,398 | A | プッシュ通知送信(PDFはU10に記載) |
| `month_user_ticket` | ライブ | L05 チケット（付与・残高・予約消費） | — | live | データ | 54 | C | 関連(推定) |
| `mypage_monthly_access_log` | 未分類 | 未分類 / 純ログ | — | operation | イベント・履歴 | 0 | A | A区分(純ログ) |
| `new_redirect_url` | 未分類 | 未分類 / 機能設定 | — | user | データ | 2,307 | C | 登録後遷移先 |
| `news` | 運営 | U01 お知らせ / アナウンス配信 | U03 お知らせ添付ファイル | news | データ | 7,221 | C | PDF記載(news) |
| `news_reply` | 運営 | U01 お知らせ / アナウンス配信 | — | news | データ | 8,038 | C | 関連(推定) |
| `news_user` | 運営 | U02 お知らせ既読 | O16 お知らせ添付アンケート | news | データ | 1,645,519 | C | PDF記載(news_user) |
| `password_reminder` | 基盤 | B05 パスワード（現行 3DES のまま利用） | — | auth | データ | 5,029 | B | パスワード再発行 |
| `payment_application` | 課金 | K02 クレジット決済 | K03 銀行振込, K04 コンビニ決済, K05 継続課金, K06 分割払いの台帳・入金記録, K07 分割払いの自動課金送信, L06 チケット単体の決済購入 | payment | データ | 50,270 | C | PDF記載(payment) |
| `payment_application_item` | 課金 | K01 商品（講座パッケージ）販売 | — | payment | データ | 50,276 | C | 関連(推定) |
| `payment_application_set_user_learning_lesson` | 課金 | K01 商品（講座パッケージ）販売 | — | payment | データ | 33 | C | 関連(推定) |
| `payment_infomation` | 課金 | K01 商品（講座パッケージ）販売 | — | payment | 設定 | 51 | C | 関連(推定) |
| `payment_item` | 課金 | K01 商品（講座パッケージ）販売 | — | payment | データ | 2,776 | C | PDF記載(payment_item) |
| `payment_item_cate` | 課金 | K01 商品（講座パッケージ）販売 | — | payment | データ | 116 | C | 関連(推定) |
| `payment_item_item_cate` | 課金 | K01 商品（講座パッケージ）販売 | — | payment | 中間 | 574 | C | 関連(推定) |
| `payment_item_lesson` | 課金 | K01 商品（講座パッケージ）販売 | — | payment | データ | 6,769 | C | ETL設計5-7 |
| `payment_item_lesson_authority` | 受講 | J01 受講権限 | — | payment | データ | 108,713 | C | ETL設計5-3(enrollmentsの源泉) |
| `payment_item_lesson_authority_log` | 受講 | J01 受講権限 | — | payment | イベント・履歴 | 99,803 | B | 関連(推定) |
| `payment_trigger_media` | 課金 | K13 流入元計測 | — | payment | データ | 28 | C | きっかけ媒体 |
| `personal_record_advice` | 未分類 | 未分類 / 該当なし | — | user | データ | 33 | C | 学習カルテ |
| `personal_record_detail_open_status` | 未分類 | 未分類 / 該当なし | — | user | データ | 0 | C | 学習カルテ |
| `personal_record_open_status` | 未分類 | 未分類 / 該当なし | — | user | データ | 491 | C | 学習カルテ |
| `php_session` | 未分類 | 未分類 / 一時 | — | auth | データ | 326 | B | PHPセッション |
| `portfolio` | 就職支援 | S04 ポートフォリオ | — | portfolio | データ | 164 | C | PDF記載(portfolio) |
| `portfolio_category` | 就職支援 | S04 ポートフォリオ | — | portfolio | データ | - |  | 関連(推定) |
| `portfolio_comment` | 就職支援 | S04 ポートフォリオ | — | portfolio | データ | 19 | C | PDF記載(portfolio_comment) |
| `portfolio_comment_like` | 就職支援 | S04 ポートフォリオ | — | portfolio | 中間 | 5 | C | 関連(推定) |
| `portfolio_like` | 就職支援 | S04 ポートフォリオ | — | portfolio | データ | - |  | 関連(推定) |
| `pref_master` | 未分類 | 未分類 / 共通マスタ | — | user | マスタ | 48 | C | 共通コードマスタ |
| `privacy_policy` | 課金 | K12 特商法・規約 | — | payment | データ | 29 | C | 規約設定 |
| `profile_cate` | 基盤 | B06 会員プロフィール（氏名・生年・電話） | — | user | マスタ | 5 | C | プロフィール項目定義 |
| `profile_item` | 基盤 | B06 会員プロフィール（氏名・生年・電話） | — | user | データ | 3,123 | C | プロフィール項目定義 |
| `profile_item_label` | 基盤 | B06 会員プロフィール（氏名・生年・電話） | — | user | データ | 3,187 | C | プロフィール項目定義 |
| `public_learning_skill_unit` | 就職支援 | S08 公開スキルチェック | — | learning | データ | 5 | C | PDF記載(public_learning_skill_unit*) |
| `public_learning_skill_unit_sub` | 就職支援 | S08 公開スキルチェック | — | learning | データ | 35 | C | PDF記載(public_learning_skill_unit*) |
| `public_learning_skill_unit_sub_result` | 就職支援 | S08 公開スキルチェック | — | learning | 中間 | 81 | C | PDF記載(public_learning_skill_unit*) |
| `public_learning_skill_unit_sub_update` | 就職支援 | S08 公開スキルチェック | — | learning | データ | 5 | C | PDF記載(public_learning_skill_unit*) |
| `public_learning_skill_unit_suspend_data` | 就職支援 | S08 公開スキルチェック | — | learning | データ | 0 | C | PDF記載(public_learning_skill_unit*) |
| `public_learning_skill_unit_update` | 就職支援 | S08 公開スキルチェック | — | learning | データ | 6 | C | PDF記載(public_learning_skill_unit*) |
| `public_skill_unit_result` | 就職支援 | S08 公開スキルチェック | — | learning | データ | 21 | C | 関連(推定) |
| `public_skill_unit_result_unit_tag` | 就職支援 | S08 公開スキルチェック | — | learning | データ | 8 | C | 関連(推定) |
| `public_unit_share_image` | 運営 | U12 SNS 共有 | — | lesson | データ | 3 | C | SNS共有画像 |
| `question` | オンデマンド | O08 テスト定義 | — | lesson | データ | 64,176 | C | PDF記載(question) |
| `question_cate` | オンデマンド | O08 テスト定義 | — | lesson | データ | 1,407 | C | 関連(推定) |
| `receipt_log` | 課金 | K08 領収書 | — | payment | データ | 2,650 | B | PDF記載(receipt_log) |
| `receipt_setting` | 課金 | K08 領収書 | — | payment | 設定 | 19 | C | PDF記載(receipt_setting) |
| `recruit` | 就職支援 | S01 求人の掲載・応募 | — | career | データ | 210 | C | PDF記載(recruit) |
| `recruit_cate` | 就職支援 | S01 求人の掲載・応募 | — | career | データ | 13 | C | 関連(推定) |
| `recruit_reply` | 就職支援 | S01 求人の掲載・応募 | — | career | データ | 548 | C | PDF記載(recruit_reply) |
| `recruit_user` | 就職支援 | S01 求人の掲載・応募 | — | career | データ | 813,743 | C | 関連(推定) |
| `registration_setting` | 未分類 | 未分類 / 機能設定 | — | auth | 設定 | 14 | C | 登録フォーム設定 |
| `remote_api_token` | オンデマンド | O28 リモート PC | — | user | データ | 5 | C | PDF記載(remote_api) |
| `report` | オンデマンド | O18 課題（定義・提出・添削） | — | lesson | データ | 4,684 | C | PDF記載(report) |
| `report_path` | オンデマンド | O18 課題（定義・提出・添削） | — | lesson | データ | 4,597 | C | 関連(推定) |
| `role_master` | 基盤 | B02 ロール（管理者 / 講師 / 受講者） | — | user | マスタ | 8 | C | PDF記載(role_master) |
| `schedule` | 対象外 | X05 運営スケジュール | — | live | データ | 0 | C | PDF記載(schedule*) |
| `schedule_attribute` | 対象外 | X05 運営スケジュール | — | live | データ | 0 | C | PDF記載(schedule*) |
| `schedule_group` | 対象外 | X05 運営スケジュール | — | live | データ | 0 | C | PDF記載(schedule*) |
| `schedule_lesson` | 対象外 | X05 運営スケジュール | — | live | データ | 0 | C | PDF記載(schedule*) |
| `schedule_user` | 対象外 | X05 運営スケジュール | — | live | データ | 0 | C | PDF記載(schedule*) |
| `scout` | 就職支援 | S03 スカウト | — | career | データ | 2,381 | C | PDF記載(scout) |
| `scout_condition` | 就職支援 | S03 スカウト | — | career | データ | 61 | C | 関連(推定) |
| `scout_lesson` | 就職支援 | S03 スカウト | — | career | 中間 | 635 | C | 関連(推定) |
| `scout_mail_target` | 就職支援 | S03 スカウト | — | career | 中間 | 1,607 | C | 関連(推定) |
| `scout_reply` | 就職支援 | S03 スカウト | — | career | データ | 485 | C | PDF記載(scout_reply) |
| `search_condition` | 未分類 | 未分類 / 機能設定 | — | user | データ | 402 | B | 検索条件保存 |
| `site` | 基盤 | B01 テナント | — | tenant | データ | 1 | C | テナント基本 |
| `skill_question` | 就職支援 | S07 スキルチェック | — | lesson | データ | 21 | C | PDF記載(skill_question) |
| `skill_question_cate` | 就職支援 | S07 スキルチェック | — | lesson | データ | 14 | C | 関連(推定) |
| `skill_question_result_type` | 就職支援 | S07 スキルチェック | — | lesson | データ | 120 | C | 関連(推定) |
| `skill_result_type` | 就職支援 | S07 スキルチェック | — | lesson | データ | 7 | C | 関連(推定) |
| `skill_unit` | 就職支援 | S07 スキルチェック | — | lesson | データ | 12 | C | PDF記載(skill_unit) |
| `skill_unit_result` | 就職支援 | S07 スキルチェック | — | lesson | データ | 29 | C | 関連(推定) |
| `skill_unit_result_unit_tag` | 就職支援 | S07 スキルチェック | — | lesson | データ | 36 | C | 関連(推定) |
| `skill_unit_sub` | 就職支援 | S07 スキルチェック | — | lesson | データ | 9 | C | 関連(推定) |
| `skill_unit_sub_question` | 就職支援 | S07 スキルチェック | — | lesson | 中間 | 52 | C | 関連(推定) |
| `skill_unit_tag` | 就職支援 | S07 スキルチェック | — | lesson | データ | 4 | C | 関連(推定) |
| `sns_setting` | 基盤 | B10 SSO | — | auth | 設定 | 63 | C | SNSログイン設定 |
| `solast_csv_log` | 未分類 | 未分類 / 純ログ | — | operation | データ | 4,665 | A | A区分(純ログ) |
| `sort_skill_unit_sub_question` | 就職支援 | S07 スキルチェック | — | lesson | データ | 57 | C | 関連(推定) |
| `sort_test_sub_question` | オンデマンド | O08 テスト定義 | — | lesson | データ | 114,747 | C | 関連(推定) |
| `sso_config` | 基盤 | B10 SSO | — | auth | 設定 | 1 | C | PDF記載(sso設定) |
| `subscription` | 運営 | U14 Web Push | — | notification | データ | 22,402 | C | PDF記載(subscription) |
| `summary_finish_unit_num` | 受講 | J02 ユニット進捗 | — | learning | データ | 1 | B | 修了ユニット数集計 |
| `summary_news_reply_new` | 運営 | U01 お知らせ / アナウンス配信 | — | news | データ | 5,521 | B | 関連(推定) |
| `summary_news_sub_num` | 運営 | U02 お知らせ既読 | — | news | データ | 0 | B | 関連(推定) |
| `summary_recruit_reply_new` | 就職支援 | S01 求人の掲載・応募 | — | career | データ | 262 | B | 関連(推定) |
| `summary_recruit_sub_num` | 就職支援 | S01 求人の掲載・応募 | — | career | データ | 0 | B | 関連(推定) |
| `summary_user_learning_test` | 未分類 | 未分類 / 該当なし | — | learning | データ | 264,521 | B | テスト成績集計 |
| `system_admin_role` | 基盤 | B02 ロール（管理者 / 講師 / 受講者） | — | tenant | 設定 | 45 | C | 管理者権限 |
| `tag` | 就職支援 | S04 ポートフォリオ | — | portfolio | データ | 158 | C | ポートフォリオのタグ |
| `tax` | 課金 | K09 消費税設定 | — | payment | データ | 1 | C | PDF記載(税設定) |
| `temp_calc_user` | 未分類 | 未分類 / 一時 | — | learning | データ | 338 | B | 集計用一時テーブル |
| `temp_question_result` | 未分類 | 未分類 / 一時 | — | learning | データ | 5 | B | 集計用一時テーブル |
| `temp_test_calc_result` | 未分類 | 未分類 / 一時 | — | learning | データ | 1 | B | 集計用一時テーブル |
| `temp_test_result` | 未分類 | 未分類 / 一時 | — | learning | データ | 1 | B | 集計用一時テーブル |
| `tenant` | 基盤 | B01 テナント | — | tenant | データ | 64 | C | PDF記載(tenant) |
| `tenant_exclude_mail` | 運営 | U07 メールテンプレート | — | notification | データ | 2 | C | メール設定 |
| `tenant_limit_value` | 基盤 | B01 テナント | — | tenant | 設定 | 64 | C | テナント上限値 |
| `tenant_vapid` | 運営 | U14 Web Push | — | notification | 設定 | 63 | C | 関連(推定) |
| `test` | オンデマンド | O08 テスト定義 | O13 テスト受験回数制限 | lesson | データ | 7,989 | C | PDF記載(test) |
| `test_mock_setting` | 対象外 | X02 模試 | — | lesson | データ | 39 | C | PDF記載(test_mock_setting) |
| `test_sub` | オンデマンド | O08 テスト定義 | — | lesson | データ | 8,060 | C | PDF記載(test_sub) |
| `test_sub_question` | オンデマンド | O08 テスト定義 | — | lesson | 中間 | 652,050 | C | 関連(推定) |
| `thread` | 運営 | U10 個別メッセージ | — | community | データ | 1,599 | C | PDF記載(thread) |
| `thread_comment` | 運営 | U10 個別メッセージ | — | community | データ | 8,947 | C | 関連(推定) |
| `thread_member` | 運営 | U10 個別メッセージ | — | community | データ | 3,921 | C | 関連(推定) |
| `ticket` | ライブ | L05 チケット（付与・残高・予約消費） | — | live | データ | 41 | C | PDF記載(ticket) |
| `ticket_limit_lesson` | ライブ | L05 チケット（付与・残高・予約消費） | — | live | データ | 41 | C | ETL設計5-6 |
| `tmp_learning_time` | 未分類 | 未分類 / 一時 | — | learning | データ | 553 | B | 学習時間一時テーブル |
| `tmp_line_entry` | 運営 | U06 LINE 連携・配信 | — | notification | データ | 0 | B | PDF記載(tmp_line_entry) |
| `tmp_line_message` | 運営 | U06 LINE 連携・配信 | — | notification | データ | 9 | B | 関連(推定) |
| `tmp_user_token` | 未分類 | 未分類 / 一時 | — | learning | データ | 16,031 | B | トークン一時テーブル |
| `tokusyo` | 課金 | K12 特商法・規約 | — | payment | データ | 29 | C | PDF記載(特商法) |
| `top_parts_master` | 未分類 | 未分類 / 機能設定 | — | tenant | マスタ | 13 | C | トップページ構成 |
| `top_parts_setting` | 未分類 | 未分類 / 機能設定 | — | tenant | 設定 | 566 | C | トップページ構成 |
| `training` | 対象外 | X01 集合研修 | — | lesson | データ | 0 | C | PDF記載(training) |
| `training_sub` | 対象外 | X01 集合研修 | — | lesson | データ | 0 | C | 関連(推定) |
| `translate_master` | 未分類 | 未分類 / 共通マスタ | — | tenant | マスタ | 1,516 | C | 共通コードマスタ |
| `trigger_media` | 課金 | K13 流入元計測 | — | user | データ | 35 | C | きっかけ媒体 |
| `twostepverification` | 基盤 | B12 二要素認証 | — | auth | データ | 55 | C | PDF記載(two-step-verification) |
| `twostepverification_log` | 基盤 | B12 二要素認証 | — | auth | イベント・履歴 | 192 | A | 関連(推定) |
| `typing_log` | 対象外 | X03 タイピング | — | learning | データ | 1 | A | PDF記載(typing_log) |
| `typing_question` | 対象外 | X03 タイピング | — | learning | データ | 720 | C | PDF記載(typing_question) |
| `typing_ranking` | 対象外 | X03 タイピング | — | learning | データ | 1 | C | PDF記載(typing_ranking) |
| `unit` | オンデマンド | O04 講義ユニット | O05 見出しブロック, O20 講座資料ユニット | lesson | データ | 51,463 | C | PDF記載(unit) |
| `unit_attached_file` | オンデマンド | O21 教材添付・ライブラリ | — | lesson | データ | 6,250 | C | PDF記載(unit_attached_file) |
| `unit_attached_file_attribute` | オンデマンド | O21 教材添付・ライブラリ | — | lesson | 中間 | 3,663 | C | 関連(推定) |
| `unit_attached_file_group` | オンデマンド | O21 教材添付・ライブラリ | — | lesson | 中間 | 4,349 | C | 関連(推定) |
| `unit_exemption` | オンデマンド | O23 ユニット免除 | — | lesson | 中間 | 226 | C | PDF記載(unit_exemption) |
| `unit_learning_progress_master` | 受講 | J02 ユニット進捗 | — | learning | マスタ | 16 | C | 関連(推定) |
| `unit_precondition` | オンデマンド | O22 ユニット前提条件 | — | lesson | 中間 | 7,601 | C | PDF記載(unit_precondition) |
| `unit_share` | 運営 | U12 SNS 共有 | — | lesson | データ | 11,042 | C | PDF記載(unit_share) |
| `unit_share_image` | 運営 | U12 SNS 共有 | — | lesson | データ | 7 | C | PDF記載(unit_share_image) |
| `unit_skill_unit_tag` | 就職支援 | S07 スキルチェック | — | lesson | 中間 | 11 | C | 関連(推定) |
| `unit_type_master` | 未分類 | 未分類 / 共通マスタ | — | lesson | マスタ | 9 | C | 共通コードマスタ |
| `user` | 基盤 | B06 会員プロフィール（氏名・生年・電話） | B03 メールログイン, B04 login_id ログイン, B05 パスワード（現行 3DES のまま利用）, S05 就活プロフィール | user | データ | 48,906 | C | PDF記載(user) |
| `user_approver` | 未分類 | 未分類 / 該当なし | — | user | 中間 | 1 | C | 承認者 |
| `user_attached_info` | 基盤 | B06 会員プロフィール（氏名・生年・電話） | — | user | データ | 15,653 | C | 関連(推定) |
| `user_attribute` | 基盤 | B08 属性 | — | user | 中間 | 48,600 | C | PDF記載(user_attribute) |
| `user_certificate` | オンデマンド | O25 修了証（講座単位） | O26 修了証（商品単位） | certificate | データ | 912 | C | PDF記載(user_certificate) |
| `user_content_viewed` | 未分類 | 未分類 / 該当なし | — | community | データ | 271,315 | C | 既読管理 |
| `user_cookie_log` | 未分類 | 未分類 / 該当なし | — | auth | イベント・履歴 | - |  | クッキー同意 |
| `user_generic_config` | 未分類 | 未分類 / 機能設定 | — | user | データ | 18 | C | ユーザー個別設定 |
| `user_group` | 基盤 | B07 グループ | — | user | 中間 | 10,492 | C | PDF記載(user_group) |
| `user_item_default` | 基盤 | B06 会員プロフィール（氏名・生年・電話） | — | user | データ | 10 | C | プロフィール項目既定値 |
| `user_learning_discussion` | 未分類 | 未分類 / 該当なし | — | community | データ | 2 | C | ディスカッション |
| `user_learning_discussion_alert` | 未分類 | 未分類 / 該当なし | — | community | データ | 11 | C | ディスカッション |
| `user_learning_lesson` | 受講 | J01 受講権限 | O24 受講期限・延長 | learning | データ | 716,042 | C | PDF記載(user_learning_lesson) |
| `user_learning_lesson_edit_log` | 受講 | J01 受講権限 | — | learning | イベント・履歴 | 495,835 | B | 関連(推定) |
| `user_learning_report` | オンデマンド | O18 課題（定義・提出・添削） | O19 課題の提出ファイル | learning | データ | 40,098 | C | PDF記載(user_learning_report) |
| `user_learning_skill_unit` | 就職支援 | S07 スキルチェック | — | learning | データ | 16 | C | PDF記載(user_learning_skill_unit*) |
| `user_learning_skill_unit_sub` | 就職支援 | S07 スキルチェック | — | learning | データ | 99 | C | PDF記載(user_learning_skill_unit*) |
| `user_learning_skill_unit_sub_result` | 就職支援 | S07 スキルチェック | — | learning | 中間 | 265 | C | PDF記載(user_learning_skill_unit*) |
| `user_learning_skill_unit_sub_update` | 就職支援 | S07 スキルチェック | — | learning | データ | 76 | C | PDF記載(user_learning_skill_unit*) |
| `user_learning_skill_unit_suspend_data` | 就職支援 | S07 スキルチェック | — | learning | データ | 0 | C | PDF記載(user_learning_skill_unit*) |
| `user_learning_skill_unit_update` | 就職支援 | S07 スキルチェック | — | learning | データ | 19 | C | PDF記載(user_learning_skill_unit*) |
| `user_learning_test` | オンデマンド | O09 テスト受験（合否・得点） | — | learning | データ | 697,444 | C | PDF記載(user_learning_test) |
| `user_learning_test_sub` | オンデマンド | O10 テスト設問別回答（選択式） | O11 テスト自由記述 | learning | データ | 10,705,972 | C | PDF記載(user_learning_test_sub) |
| `user_learning_test_sub_update` | オンデマンド | O12 テスト中断・再開 | — | learning | データ | 2,212,972 | C | PDF記載(user_learning_test_sub_update) |
| `user_learning_test_suspend_data` | オンデマンド | O12 テスト中断・再開 | — | learning | データ | 326 | C | PDF記載(user_learning_test_suspend_data) |
| `user_learning_test_update` | オンデマンド | O12 テスト中断・再開 | — | learning | データ | 815,895 | C | PDF記載(user_learning_test_update) |
| `user_learning_unit` | 受講 | J02 ユニット進捗 | J03 SCORM 詳細ログ / 中断データ | learning | データ | 1,182,245 | C | PDF記載(user_learning_unit) |
| `user_learning_unit_log` | 受講 | J03 SCORM 詳細ログ / 中断データ | — | learning | データ | 2,929,224 | C | PDF記載(user_learning_unit_log) |
| `user_lesson_session` | 受講 | J02 ユニット進捗 | — | learning | データ | 267,639 | C | 関連(推定) |
| `user_login_chk_log` | 基盤 | B09 ログイン履歴 | — | auth | イベント・履歴 | - |  | login系 |
| `user_login_log` | 基盤 | B09 ログイン履歴 | — | auth | イベント・履歴 | 1,326,645 | A | login系 |
| `user_login_log_monthly` | 基盤 | B09 ログイン履歴 | — | auth | イベント・履歴 | 146,702 | A | login系 |
| `user_nationality_info` | 基盤 | B06 会員プロフィール（氏名・生年・電話） | — | user | データ | 8,478 | C | 関連(推定) |
| `user_personal_no` | 基盤 | B11 マイナンバー | — | user | データ | 53,568 | C | PDF記載(user_personal_no) |
| `user_session` | 未分類 | 未分類 / 一時 | — | auth | データ | 39,207 | B | セッション |
| `user_skill_unit_result` | 就職支援 | S07 スキルチェック | — | learning | データ | 42 | C | 関連(推定) |
| `user_skill_unit_result_unit_tag` | 就職支援 | S07 スキルチェック | — | learning | データ | 21 | C | 関連(推定) |
| `user_test_result` | 未分類 | 未分類 / 該当なし | — | learning | データ | 12 | C | テスト成績集計 |
| `user_ticket` | ライブ | L05 チケット（付与・残高・予約消費） | — | live | データ | 3,231 | C | PDF記載(user_ticket) |
| `user_ticket_log` | ライブ | L07 チケット消費台帳の再生 | — | live | イベント・履歴 | 986 | B | PDF記載(user_ticket_log) |
