# サポート機能テーブルの内訳

移行計画の **5 サポート機能**（LINE 友だち紐付け / クーポン / お知らせ / 問い合わせ / ファイル / 就業支援 / コミュニティ / 利用料の集計 / その他）。

> **S6 / S7 の一部と S8・S9 は、2026-09-30 に「どの区分にも仕分けていなかった旧テーブル」から足した。**
> 旧の逆引き（[legacy-table-coverage.md](../legacy-table-coverage.md)）で区分が `未分類` の表のうち、
> 01 基盤・06 対象外が持たないものは**すべてこの区分に入れた**（同ファイルの「未分類 67 件の移行区分」）。

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
| `line_send` / `line_send_batch` / `line_send_user` / `line_send_user_log` / `line_send_batch_log` | `line_send_logs` | U06 LINE 連携 | イベント・履歴 | 12,798 / 183,739 / 2,127 / 218,736 / 34,997 | C | 配信の履歴。実測 31 / 36 / 0 / 41 / 5 | **`tenant_id` を持たない。** 純ログなので移さない |
| `line_message` / `line_message_mail_follow_setting` / `line_message_mail_setting` / `line_message_recruit` / `tmp_line_entry` / `tmp_line_message` | — | U06 LINE 連携 | 設定 / データ | 1,310 / 96 / 58 / 23 / 0 / 9 | C | 配信文面・一時データ。実測 1 / — / 1 / 4 / 0 / 0 | 実測はほぼ0件。**同じ LINE 公式アカウントを継続する場合のみ意味がある** |

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
| `summary_news_reply_new` / `summary_news_sub_num` | — | U01 / U02 | データ | 5,521 / 0 | C | ニュースの新着返信・既読数の集計。実測 10 / 0件 | **集計なので移さない**（本体から作り直せる） |
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
| `lesson_inquiry_user` | — | U08 問い合わせ | 中間 | 0 | C | 講座ごとの問い合わせ先 | **0件**。移すものが無い |
| （副）`inquire_answer` の添付 | — | U09 添付ファイル | データ | — | X | 問い合わせの添付 | **`inquiries` に添付カラムが無い**（ファイル 706件・**最大の塊**） |
| `thread` / `thread_comment` / `thread_member` | — | U10 個別メッセージ | データ | 20 / 25 / 46 | X | 1対1のやり取り | **受け皿なし。** `community_messages` はチャネル型 |

## S5 ファイル

**実装済み**（`support.5`）。**旧より広く見せない**（2026-10-01）。添付資料は講座ごとの移行用フォルダに入れて
「その講座の受講者に公開」にし、新に機能の無い公開範囲（ユニット・資料ごとのグループ・属性・フォルダのグループ）は
受け皿に残して、**機能ができるまで非公開か「対象者なし」**にする。

| 旧テーブル | 新テーブル | データ種 | lw2区分 | ローカルデータ数 | A·B·C | 説明 | 移行の注意 |
|---|---|---|---|---:|:--:|---|---|
| `unit_attached_file` | `library_materials` ＋ `library_material_lesson_targets` | O21 教材添付 | データ | 6,250 | C | 講座資料のユニットに添付した資料。実測 ReCADemy の講座 79件・共有講座 173件（移したのは共有講座の選び方に入る 227件） | 講座ごとの移行用フォルダに入れる。どのユニットの資料かは `library_material_lesson_targets`。**削除済みのユニットの資料（4件）は非公開** |
| — | `library_folders`（講座ごとの移行用フォルダ）/ `library_folder_course_targets` | O21 教材添付 | — | — | — | 添付資料を持つ講座ごとに1つ。実測66件 | **lw2 に対応する行は無い。** 公開先は `course_enrolled`（その講座の受講者）。旧は講座を開ける人だけが資料を見られた |
| `unit_attached_file_group` / `unit_attached_file_attribute` | `library_material_group_targets` / `library_material_tag_targets`（新設） | O21 教材添付 | 中間 | 4,349 / 3,663 | C | 資料ごとに見せるグループ・属性。実測 0 / 0件 | **新に資料単位の公開先が無い。** 指定のある資料は**非公開**で移し、指定はこの2表に残す（属性はタグとして） |
| `lesson_attached_file` / `_group` / `_attribute` | `library_materials` / `library_material_group_targets` / `library_material_tag_targets` | O21 教材添付 | データ / 中間 | **0 / 0 / 0** | C | 講座に直接添付した資料と、その公開範囲 | **ユニット添付と同じ経路で移す**（講座のフォルダに入れる。ユニットには結ばない）。削除済みは非公開 |
| `document_file_detail` | — | O21 教材添付 | データ | 761 | C | 資料フォルダの中のファイルの説明文。キーはディスク上のファイルのパスの md5 | **DB だけでは移せない。** `tenant_id` も `drive` への参照も無く、フォルダの中のファイル自体も DB に無い。ファイルの移送（L9）でパスから md5 を作って突き合わせる |
| `drive` / `drive_group` | `library_folders` / `library_folder_group_targets` | O21 教材添付 | データ / 中間 | 111 / 429 | C | 資料フォルダとその公開グループ。実測 3 / 0件 | **フォルダの中のファイルは L9 で運ぶ。** グループで絞っていたフォルダは公開先を「対象者なし」（`specific_users`）にする。削除済みは非公開 |
| — | `library_material_kinds` / `library_audience_types` | O21 教材添付 | マスタ | — | — | 教材種別・公開対象の値 | migration で投入 |
| — | `library_downloads` | O21 教材添付 | イベント・履歴 | — | — | ダウンロード履歴 | 旧に対応データなし。**純ログなので空で始める** |

## S6 就業支援

**移行ツールは助言メモとフォローだけ実装済み**（`support.6`。いずれも btoc に入る）。
求人・面談・スキルチェックは未実装で、**移行先が career-backend**（別サービス）である点が他と違う。

| 旧テーブル | 新テーブル | データ種 | lw2区分 | ローカルデータ数 | A·B·C | 説明 | 移行の注意 |
|---|---|---|---|---:|:--:|---|---|
| `recruit` / `recruit_cate` / `recruit_user` | `career:job_postings` / `career:job_posting_skills` | S01 求人 | データ | 154 / 2 / 574 | C | 求人と応募。実測 154 / 2件 | **career-backend。** btoc とは別 DB なので投入先が変わる |
| `recruit_reply` / `summary_recruit_reply_new` / `summary_recruit_sub_num` | — | S01 求人 | データ | 548 / 262 / 0 | C | 応募へのやり取りと、その集計。実測 0 / 0 / 0 | **ReCADemy は0件。** 求人（`recruit_user`）と一緒に career-backend へ移すかを決める |
| `company` | `career:companies` | S02 企業ページ | データ | 10 | C | 求人企業 | **`tenant_id` を持たない** |
| `job_career` ほか3件 | `career:learner_career_profiles` / `career:learner_career_skills` | S05 就活プロフィール | データ | 76 | C | 職歴・希望職種 | |
| `interview_record` / `interview_contents` / `interview_status` | `career:interviews` / `career:interview_records` / `career:advisors` | S06 面談 | データ | 1 / 80 | C | 面談の予約と記録。実測 1 / 20件 | |
| `scout` ほか4件 | — | S03 スカウト | データ | 111 | X | スカウト | **受け皿なし** |
| `portfolio` ほか7件 | — | S04 ポートフォリオ | データ | 1,846 | X | ポートフォリオ。実測 1,837件 | **受け皿なし。** この区分で**最大のデータ** |
| `skill_unit` ほか20件 | — | S07 スキルチェック | データ | 1 | X | スキルチェック | **21テーブルで合計 973行、実質未使用** |
| `public_learning_skill_unit` ほか7件 | — | S08 公開スキルチェック | データ | — | X | 公開版 | **受け皿なし** |
| `personal_record_advice` | `admin_notes`（既存） | 未分類 | データ | 33 | C | 管理者・キャリアカウンセラーが会員に残した助言メモ（学習カルテ）。実測1件 | **実装済み**（`support.6`）。既存の運営メモに寄せる。削除済みも `deleted_at` 付きで移す |
| `follow` | `scout_follows`（新設） | 未分類 | データ | 382 | C | 求人企業（と管理者）が受講者をフォローした記録。実測14件 | **実装済み**（`support.6`）。削除済みは `deleted_at` で残す |
| `like_user` | — | 未分類 | データ | 27,117 | C | 「いいね」を押した会員。親の `like`（S04）の種別で、ポートフォリオ 6,537 / 掲示板の投稿 4 / 掲示板のコメント 18（実測） | **ポートフォリオの分は受け皿なし**（`portfolio` と同じ）。掲示板の分は S7 の掲示板と一緒に `discussion_likes` へ（未実装） |
| `personal_record_open_status` / `personal_record_detail_open_status` | — | 未分類 | データ | 491 / 0 | C | 学習カルテ（自己紹介・職歴・希望条件など）を誰に見せるかの設定。実測 0 / 0件 | **受け皿なし・実測0件。** 学習カルテの本体（S05）と一緒に決める |

## S7 コミュニティ

**移行ツールは分類だけ実装済み**（`support.7`）。掲示板・SNS 共有・足あとは未実装。

| 旧テーブル | 新テーブル | データ種 | lw2区分 | ローカルデータ数 | A·B·C | 説明 | 移行の注意 |
|---|---|---|---|---:|:--:|---|---|
| `bbs` / `bbs_comment` | `discussion_posts` / `discussion_likes` ほか | U11 掲示板 | データ | 19 / 33 | C | 掲示板。実測 16件 | **PDF は X だが受け皿はある**（構造は異なる）。`bbs_set_*` 5件の公開範囲に受け皿が無い |
| `unit_share` / `unit_share_image` / `public_unit_share_image` | — | U12 SNS 共有 | データ | 707 / 7 / 3 | X | SNS 共有 | **受け皿なし** |
| `footprint` | — | U13 足あと | イベント・履歴 | 77 | X | 足あと。実測 76件 | **受け皿なし。** 純ログ |
| `community_cate` | `community_categories`（新設） | 未分類 | データ | 203 | C | コミュニティの分類。実測3件 | **実装済み**（`support.7`）。旧のグループ 0（指定なし）は NULL |
| `user_content_viewed` / `content_master` | — | 未分類 | データ / マスタ | 271,315 / 3 | C | 既読の印。種別（`content_master`）で掲示板 112 / 課題 613 / 学習ユニット 623 / 不明（種別4、マスタに無い）35（実測） | **受け皿なし。** 新の既読は `announcement_reads`（お知らせ）だけ。掲示板の本体と一緒に決める（未実装） |
| `discussion` / `discussion_board` / `discussion_board_comment` | `discussion_posts` ほか | 未分類 | データ | 31 / 13 / 122 | C | ディスカッションのユニットの設定・板・書き込み。実測 25 / 10 / 7（共有講座を含む） | **未実装。** ユニットは 02 で `discussion` 型として移している（中身は移していない）。新の `discussion_posts` は掲示板向けで、ユニットに結びつかない |
| `user_learning_discussion` / `user_learning_discussion_alert` | — | 未分類 | データ | 2 / 11 | C | ディスカッションの採点・通知設定。実測 3 / 4 | **未実装。** 上のディスカッションと一緒に決める |

## S8 利用料の集計

**実装済み**（`support.8`）。旧は月に1回、締め日の翌日にテナントの会員数を数えて残していた
（LMS 事業者への課金の計上用）。**新のアプリはまだ読まない**（受け皿だけ新設した。[features F13](features.md)）。

| 旧テーブル | 新テーブル | データ種 | lw2区分 | ローカルデータ数 | A·B·C | 説明 | 移行の注意 |
|---|---|---|---|---:|:--:|---|---|
| `config_closing_date` | `tenant_usage_settings`（新設） | 未分類 | 設定 | 64 | C | 締め日。実測1件 | テナントに1行 |
| `accounting_user` | `tenant_usage_snapshots`（新設） | 未分類 | データ | 2,403 | C | 月次の会員数の集計。実測111件（2017-06〜2026-08） | `(tenant_id, batch_date)` で一意 |
| `accounting_user_detail` | `tenant_usage_snapshot_users`（新設） | 未分類 | データ | 192,053 | C | 集計した時点の会員の写し。実測18,122件 | **旧で消えた会員もいる。** 移行先に会員がいれば `user_id`、いなければ NULL にし、旧 ID を `legacy_user_id` に残す |

> **`calc_param`（模試の集計条件）は 06 対象外の [X2 模試](../06-out-of-scope/breakdown.md#x2-模試) に置く。**
> 利用料の集計ではない。模試と一緒に [E63](../open-questions.md#e-切り替え後の機能で決めておきたいこと) の回答で決める。

## S9 その他（仕分けていなかった表のうち、移さないもの）

**どれも移さない。** ログ・一時データ・システム全体のマスタ・画面の個人設定で、新環境に持っていっても意味を持たない。
実データのあるものは理由を添える。

| 旧テーブル | 新テーブル | データ種 | lw2区分 | ローカルデータ数 | A·B·C | 説明 | 移行の注意 |
|---|---|---|---|---:|:--:|---|---|
| `access_log` / `file_download_log` / `live_lesson_batch_log` / `batch_schedule_log` / `solast_csv_log` / `mypage_monthly_access_log` / `debug_trace` | — | 未分類 | イベント・履歴 | 696,319 / 11,980 / 52,038 / 13,644 / 4,665 / 0 / 0 | A | アクセス・ダウンロード・バッチ・CSV 連携の記録。ReCADemy 実測 2,759 / 1 / 1,417 / — / — / 0 / 0 | **純ログなので移さない。** cutover 後の記録から始める |
| `php_session` / `user_session` / `tmp_user_token` / `tmp_learning_time` / `new_redirect_url` / `csv_request` | — | 未分類 | データ | 326 / 39,207 / 16,031 / 553 / 2,307 / 0 | B | セッション・ワンタイムのトークン・学習時間の書きかけ・ログイン後の遷移先・CSV 取り込みの受付。ReCADemy 実測 — / 857 / 17 / — / 3 / 0 | **一時データなので移さない。** 切り替えで全員ログインし直す |
| `code_master` / `display_master` / `emoji_master` / `language_master` / `unit_type_master` | — | 未分類 | マスタ | 35 / 15 / 197 / 13 / 9 | C | システム全体のコード表（テナントのデータではない） | **移さない。** ユニットの種別は 02 で `lesson_types` に読み替え済み。言語・国・都道府県は新のマスタを使う |
| `function_admin_master` / `function_default_master` / `top_parts_master` / `function_admin_user` | — | 未分類 | マスタ / データ | 224 / 42 / 13 / 0 | C | 管理画面・受講者画面の機能とトップページの部品の定義 | **移さない。** テナントごとの設定（`function_*_tenant` ほか）は 01 で `tenants.settings` に**コードのまま**残した。定義そのものは旧の画面の部品で、新に対応が無い。`function_admin_user` は0件 |
| `batch_schedule` / `batch_schedule_detail` | — | 未分類 | データ | 19 / 19 | C | 旧のバッチの実行予定（全テナント共通） | **移さない。** 新のバッチは新の仕組みで動く |
| `search_condition` / `user_generic_config` | — | 未分類 | データ | 402 / 18 | B / C | 管理画面の検索条件の保存・画面の個人設定（講座一覧の表示の切り替えなど）。ReCADemy 実測 27 / 2 | **移さない。** 旧の画面の部品に結びつく値で、新の画面に対応が無い |
| `summary_user_learning_test` | — | 未分類 | データ | 264,521 | B | テストの成績の集計（初回・最終・最高点・受験回数）。ReCADemy 実測146件 | **移さない。** 受験結果（03 の `quiz_attempts`）から作り直せる集計 |
| `config_cookie` / `hosting_capacity` / `user_cookie_log` | — | 未分類 | 設定 / データ / 履歴 | — | — | クッキー同意・テナントの容量 | **lw2 の DB に表が無い**（ドキュメントにだけある）。移すものが無い |
