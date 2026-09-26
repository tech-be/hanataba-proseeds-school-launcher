# サポート機能テーブルの内訳

移行計画の **5 サポート機能**（LINE 友だち紐付け / クーポン / お知らせ / 問い合わせ / ファイル / 就業支援 / コミュニティ）。

[データ種別対照表](../data-type-mapping.md) が分類したデータ種を、**移行計画の区分**で切り直したもの。
移行ツールの**投入順序を決めるための一覧**として使う。新環境は実 FK を持つため、
前の区分が入っていないと1行も入らない。

- 全件の逆引き: [旧環境](../legacy-table-coverage.md) / [新環境](../new-table-coverage.md)
- カラムの突き合わせ: [review.md](review.md)
- 移行の手順: [migration-spec.md](migration-spec.md)

> **基盤（1）とコンテンツ（2）が終わっていること。** 教材はレッスンを、LINE は会員を参照する。

> **ローカルデータ数と A·B·C の定義は [README.md](../README.md#共通の列の意味) にある。**
> ローカルデータ数は**全73テナントの合計**で ReCADemy 単体ではない。本文中の「ステージング実測」は
> 2026-09-18 のダンプで `tenant_id = 10`（ReCADemy）に絞って数えた値。

---

## 書くこと

ひな形は [00-template/breakdown.md](../00-template/breakdown.md)。実例は [01 基盤の内訳](../01-foundation/breakdown.md)。

1. 大分類の定義と件数（基盤は「マスター系 / ユーザー系」。区分ごとに適切な軸を選ぶ）
2. 中分類ごとの一覧表（旧テーブル / 新テーブル / データ種 / lw2区分 / ローカルデータ数・A·B·C / 説明 / 移行の注意）
3. 投入順序（新環境は実 FK があるため順序が強制される）
4. 新側に受け皿が無い中分類の名指し

作ったら **[review.md](review.md) の `###` 見出しを、この対応表の行と1対1・同じ順序に揃え直すこと**（現状はデータ種軸）。ひな形は [00-template/review.md](../00-template/review.md)。

## S1 LINE 友だち紐付け

| 旧テーブル | 新テーブル | データ種 | lw2区分 | ローカルデータ数 | A·B·C | 説明 | 移行の注意 |
|---|---|---|---|---:|:--:|---|---|
| `user.line_id` ほか | `line_links` | U06 LINE 連携 | データ | — | C | 会員と LINE の紐付け | **実装済み**（`support.1`）。会員の投入後に流す |
| `line_send` / `line_send_batch` | `line_send_logs` | U06 LINE 連携 | イベント・履歴 | 31 / 36 | C | 配信の履歴 | **`tenant_id` を持たない。** 純ログなので移さない |
| `line_message` ほか5件 | — | U06 LINE 連携 | 設定 / データ | 1 / 0 | C | 配信文面・一時データ | 実測はほぼ0件。**同じ LINE 公式アカウントを継続する場合のみ意味がある** |

## S2 クーポン

**移行ツールは未実装。**

| 旧テーブル | 新テーブル | データ種 | lw2区分 | ローカルデータ数 | A·B·C | 説明 | 移行の注意 |
|---|---|---|---|---:|:--:|---|---|
| `coupon` | `coupons` | K10 クーポン | データ | 18 | C | クーポン本体。実測7件 | **`coupons.provider_coupon_id` が NOT NULL**。決済代行側の ID で、lw2 に対応する値が無い |
| `coupon_item` | `coupon_course_targets` | K10 クーポン | 中間 | 21 | C | 対象の商品 | **粒度が商品→講座に変わる。** 商品と講座が 1:N |
| `coupon_group` / `coupon_user` | `coupon_user_targets` / `coupon_audience_types` | K11 対象者割当 | 中間 | 0 / 181 | C | 対象者（グループ・個人） | `coupon_group` は実測0件 |
| `coupon_log` | `coupon_redemptions` | K10 クーポン | イベント・履歴 | 4 | C | 使用履歴 | |
| `coupon_live_lesson` | — | L09 ライブ限定クーポン | データ | 10 | C | ライブに使えるクーポン | **受け皿なし。** `coupon_course_targets` は**コース単位**で、ライブ単位ではない |

## S3 お知らせ

**移行ツールは未実装。**

| 旧テーブル | 新テーブル | データ種 | lw2区分 | ローカルデータ数 | A·B·C | 説明 | 移行の注意 |
|---|---|---|---|---:|:--:|---|---|
| `announce` | `announcements` | U01 お知らせ | データ | 37 | C | 運営からのお知らせ。実測35件 | |
| `news` | `announcements` | U01 お知らせ | データ | 309 | C | ニュース。実測267件 | **`announce` と 2 系統ある**ものを 1 表に寄せる。区別が要るなら列を足す |
| `news_reply` | — | U01 お知らせ | データ | 13 | C | ニュースへの返信 | 受け皿なし |
| `announce_user` / `news_user` | `announcement_reads` | U02 既読 | 中間 | 1,147 / 1,214 | C | 既読 | **`news_user` は写さない方針**（既読 5.5%） |
| （副）`news` の添付 | — | U03 添付ファイル | データ | — | X | お知らせの添付 | **`announcements` に添付カラムが無い**（ファイル 296件） |
| `login_dialog_log` | — | U04 モーダル | イベント・履歴 | 28 | X | ログイン後モーダル | **受け皿なし**。PDF の `config_dialog` は lw2 に実在しない |
| `mail_follow_setting` ほか3件 | `retention_rules` / `retention_sends` / `retention_trigger_kinds` | U05 フォローメール | データ | 5 / 40 | C | フォローメールの設定と送信ログ | |
| `mail_template` / `mail_setting` ほか11件 | `tenant_email_templates` / `email_kinds` / `email_send_logs` ほか | U07 メールテンプレート | 設定 / 履歴 | 10 / 2,771 | C | 文面と送信ログ。実測テンプレート7件 | 送信ログ（`mail_send` 2,771件）は**純ログなので移さない** |
| `message_send` ほか6件 | — | U14 Web Push | データ | 230 / 1,157 | X | Web Push の配信と購読 | **受け皿なし。** `in_app_notifications` はアプリ内通知で Web Push ではない |

## S4 問い合わせ

**移行ツールは未実装。**

| 旧テーブル | 新テーブル | データ種 | lw2区分 | ローカルデータ数 | A·B·C | 説明 | 移行の注意 |
|---|---|---|---|---:|:--:|---|---|
| `inquire` | `inquiries` | U08 問い合わせ | データ | 56 | C | 問い合わせ本体 | **`tenant_id` を持たない。** `inquire_cate` 経由で絞る |
| `inquire_answer` | `inquiries`（回答列） | U08 問い合わせ | データ | 62 | C | 回答 | |
| `inquire_cate` | `inquiry_categories` | U08 問い合わせ | 分類 | 16 | C | カテゴリ。実測7件 | **対応表 CSV が必要**（旧カテゴリ → 新カテゴリ） |
| `inquire_user` / `config_inquire` | — | U08 問い合わせ | 中間 / 設定 | 17 / 1 | C | 宛先と設定 | |
| （副）`inquire_answer` の添付 | — | U09 添付ファイル | データ | — | X | 問い合わせの添付 | **`inquiries` に添付カラムが無い**（ファイル 706件・**最大の塊**） |
| `thread` / `thread_comment` / `thread_member` | — | U10 個別メッセージ | データ | 20 / 25 / 46 | X | 1対1のやり取り | **受け皿なし。** `community_messages` はチャネル型 |

## S5 ファイル

| 旧テーブル | 新テーブル | データ種 | lw2区分 | ローカルデータ数 | A·B·C | 説明 | 移行の注意 |
|---|---|---|---|---:|:--:|---|---|
| `unit_attached_file` | `library_materials` | O21 教材添付 | データ | 6,250 | C | ユニットの添付教材 | **recademy 単体では実測3件**（ETL設計 付録A。全73テナント合計との差が2,083倍） |
| `unit_attached_file_attribute` / `unit_attached_file_group` | `library_folder_user_targets` / `library_folder_course_targets` | O21 教材添付 | 中間 | 3,663 / 4,349 | C | 公開範囲（属性・グループ） | **基盤の属性・グループ（A10/A11）に依存する** |
| `lesson_attached_file` ほか2件 | `library_materials` ほか | O21 教材添付 | データ / 中間 | **0** | C | 講座の添付教材 | **3テーブルとも0行**。移行するデータが無い |
| `document_file_detail` | `library_materials` | O21 教材添付 | データ | 761 | C | 文書ファイルの詳細 | |
| `drive` / `drive_group` | `library_folders` | O21 教材添付 | データ / 中間 | 111 / 429 | C | フォルダと公開範囲 | |
| — | `library_material_kinds` / `library_audience_types` | O21 教材添付 | マスタ | — | — | 教材種別・公開対象の値 | migration で投入 |
| — | `library_downloads` | O21 教材添付 | イベント・履歴 | — | — | ダウンロード履歴 | 旧に対応データなし。**純ログなので空で始める** |

## S6 就業支援

**移行ツールは未実装。** **移行先が career-backend**（別サービス）である点が他と違う。

| 旧テーブル | 新テーブル | データ種 | lw2区分 | ローカルデータ数 | A·B·C | 説明 | 移行の注意 |
|---|---|---|---|---:|:--:|---|---|
| `recruit` / `recruit_cate` / `recruit_user` | `career:job_postings` / `career:job_posting_skills` | S01 求人 | データ | 154 / 2 / 574 | C | 求人と応募。実測 154 / 2件 | **career-backend。** btoc とは別 DB なので投入先が変わる |
| `company` | `career:companies` | S02 企業ページ | データ | 10 | C | 求人企業 | **`tenant_id` を持たない** |
| `job_career` ほか3件 | `career:learner_career_profiles` / `career:learner_career_skills` | S05 就活プロフィール | データ | 76 | C | 職歴・希望職種 | |
| `interview_record` / `interview_contents` / `interview_status` | `career:interviews` / `career:interview_records` / `career:advisors` | S06 面談 | データ | 1 / 80 | C | 面談の予約と記録。実測 1 / 20件 | |
| `scout` ほか4件 | — | S03 スカウト | データ | 111 | X | スカウト | **受け皿なし** |
| `portfolio` ほか7件 | — | S04 ポートフォリオ | データ | 1,846 | X | ポートフォリオ。実測 1,837件 | **受け皿なし。** この区分で**最大のデータ** |
| `skill_unit` ほか29件 | — | S07 スキルチェック | データ | 1 | X | スキルチェック | **30テーブルで合計 1,137行、実質未使用** |
| `public_learning_skill_unit` ほか7件 | — | S08 公開スキルチェック | データ | — | X | 公開版 | **受け皿なし** |

## S7 コミュニティ

**移行ツールは未実装。**

| 旧テーブル | 新テーブル | データ種 | lw2区分 | ローカルデータ数 | A·B·C | 説明 | 移行の注意 |
|---|---|---|---|---:|:--:|---|---|
| `bbs` / `bbs_comment` | `discussion_posts` / `discussion_likes` ほか | U11 掲示板 | データ | 19 / 33 | C | 掲示板。実測 16件 | **PDF は X だが受け皿はある**（構造は異なる）。`bbs_set_*` 5件の公開範囲に受け皿が無い |
| `unit_share` / `unit_share_image` | — | U12 SNS 共有 | データ | 707 / 0 | X | SNS 共有 | **受け皿なし** |
| `footprint` | — | U13 足あと | イベント・履歴 | 77 | X | 足あと。実測 76件 | **受け皿なし。** 純ログ |
