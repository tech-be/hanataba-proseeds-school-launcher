# データ種分類の差分・要確認事項

[データ種別対照表](data-type-mapping.md) を作る過程で出てきた、PDF との食い違い・資料間の矛盾・判断が要る点をまとめたもの。

---

## 1. ◯/X の再判定で PDF と食い違ったもの（5件）

判定ルール: 新環境にそのデータ種のデータを保持する場所（テーブル **または** カラム）があれば ◯。PDF の定義に合わせ「機能の有無」で見ており、**実際に移行するかどうかは別**。

### 1-1. PDF X → 実際 ◯（4件）

新環境に受け皿があるのに PDF では「無い」とされているもの。移行スコープに入れられる可能性がある。

| ID | データ種 | 新環境の受け皿 | 補足 |
|---|---|---|---|
| O28 | リモート PC | `remote_pc_machines`, `remote_pc_reservations`, `remote_pc_blackouts`, `remote_pc_reservation_statuses` | lw2 側は `remote_api_token` のみ。設計資料も `docs/remote-pc-design.md` がある |
| L07 | チケット消費台帳の再生 | `ticket_ledger_entries`, `ticket_ledger_kinds` | **受け皿はあるが ETL 設計 §5-6 は「履歴は再生しない」方針**。理由は btoc の台帳が「付与 − 消費 = 残高」の整合を前提にしており、lw2 のログ（正本は `user_ticket.ticket_num`）を再生すると必ず食い違うため。機能の有無としては ◯、移行方針としては見送り |
| U11 | 掲示板 | `discussion_posts`, `discussion_likes`, `discussion_post_statuses`, `discussion_post_status_events` | **構造が違う。** lw2 の `bbs` は公開範囲を属性・グループ・講座・商品・権限の5軸で絞る作り（`bbs_set_*` 5テーブル）だが、新環境の `discussion_posts` にその5軸の受け皿は無い。移せるかは別途判断が要る |
| S02 | 求人企業ページ | `career:companies` | career-backend 側。`job_postings` から参照される |

### 1-2. PDF ◯ → 実際 X（1件）

| ID | データ種 | 判定 | 根拠 |
|---|---|---|---|
| B10 | SSO | **受け皿テーブルなし** | `auth_methods` に入っているのは `password` / `google` / `line` / `passkey` / `refresh` の5つだけ。lw2 の `sso_config`（`tenant_id`, `sso_type`, `sso_parameter`）に相当する IdP 設定テーブルが新環境に無い。`docs/authentication.md` は「SAML SSO や Google / LINE OAuth 経由のログインは外部 IdP に委ねる」としており、**設定を DB に持たない設計**。機能としては存在しうるが、**移行するデータの置き場所が無い** |

---

## 2. PDF に書かれているテーブル名が lw2 に実在しないもの（3件）

PDF の「既存の主なテーブル」列を `docs/db/lw2/tables/*.md` の342件と突き合わせた結果。

| PDF の表記 | データ種 | 実態 |
|---|---|---|
| `re_auth_*` | K05 継続課金 | **テーブルではなくカラム。** `payment_application.re_auth_jpayment_application_id` / `re_auth_date`。継続課金そのものは `payment_application.auto_credit_id` / `auto_credit_price` / `is_auto_cancel` / `auto_cancel_term` が持つ |
| `split_payment 系` | K06 分割払いの台帳・入金記録 / K07 分割払いの自動課金送信 | **テーブルではなくカラム。** `payment_application.is_use_split_payment` / `split_payment_number`。分割払い専用テーブルは lw2 に存在しない |
| `config_dialog` | U04 ログイン後モーダル | **実在しない。** lw2 にあるのは `login_dialog_log` だけ |

表記揺れ（実在はするが名前が違うもの）: `two-step-verification` → `twostepverification` / `remote_api` → `remote_api_token` / `document` → `document_file_detail`。

---

## 3. PDF の割り当て・名称が lw2 の実態と合わないもの（2件）

| ID | データ種 | PDF の記載 | 実態 |
|---|---|---|---|
| B11 | **マイナンバー** | `user_personal_no` | **マイナンバーではなく、会員に振る一意の ID**（運用担当に確認済み）。スキーマもそれを裏付けていて、`personal_no` は `int(11)` = signed int の最大 2,147,483,647（10桁）なので**12桁のマイナンバーは格納できない**。列コメントも「登録番号」「個別番号」。**データ種名だけを見て機微情報として扱わないこと**（[基盤の内訳](01-foundation/breakdown.md) U2 / [基盤レビュー](01-foundation/review.md) U2） |
| U10 | 個別メッセージ | `thread`, `message_send*` | `message_send*` 5テーブルのテーブルコメントは**すべて「プッシュ通知送信」**（`message_send` / `_batch` / `_batch_log` / `_user` / `_user_log`）で、1対1メッセージではない。lw2 の個別メッセージは `thread` / `thread_comment` / `thread_member` の3テーブル。本分類では `message_send*` を **U14 Web Push** 側に割り当てている |

---

## 4. テーブル数が資料ごとに食い違う

| 資料 | 件数 |
|---|---:|
| `learningware-kiracari/docs/db/lw2/tables/*.md` | **342** |
| `school-launcher/docs/lw2-migration-tables.md` / `scrun-inventory-results.md` | 335 |
| `school-launcher/docs/kiracari-migration-requirements-estimate.md` | 341 |

本分類は **342 を正**としている（現在のスキーマの `information_schema` 由来のため）。335 との差分 7 件は、`lw2-migration-tables.md` が使った 2026-07-28 ダンプ以降に追加されたと見られるもの:

`config_cookie`, `hosting_capacity`, `lecture_path_test`, `portfolio_category`, `portfolio_like`, `user_cookie_log`, `user_login_chk_log`

この7件はローカルデータ数・サイズ・A/B/C 区分が不明なので、逆引き表では空欄になっている。341 との差分は未確認。

---

## 5. ローカルデータ数は recademy 単体の値ではない

[旧環境逆引き](legacy-table-coverage.md) のローカルデータ数の列は `lw2-migration-tables.md` 由来で、**同一 DB に同居する 73 テナントの合計値**。移行対象は `tenant_id = 12` (recademy) の1テナントのみ（`scrun-etl-design.md` §1）。

`scrun-etl-design.md` 付録 A が実測で補正した例:

| 対象 | 棚卸しの値（全テナント） | recademy 単体 | 倍率 |
|---|---:|---:|---:|
| アンケート回答 | 64,883 | **2,464** | 26倍 |
| 教材添付 | 6,250 | **3** | 2,083倍 |
| 問い合わせ | 14,412 | **3,343** | 4.3倍 |

**逆引き表のローカルデータ数は規模感の参考値としてのみ使うこと。** 移行ツールの処理件数見積もりには使えない。

---

## 6. A 区分（純ログ・移行対象外）なのに新環境に受け皿があるもの（7件）

`lw2-migration-tables.md` が A（純ログ = 移行対象外）に分類しているが、本分類ではデータ種が付き、かつ再判定が ◯ になったもの。

> **決着: 純ログは受け皿があっても移行しない。** 7件はいずれも「いつ・誰に・何を送ったか／ログインしたか」の記録で、**cutover 後の新環境で記録し直せばよい**もの。受け皿（`login_history` / `email_send_logs` / `line_send_logs` / `retention_sends`）は空で始める。
>
> **ただし名前で判断しない。** `user_login_chk_log` は「ログイン有効期間の変更履歴」、`user_learning_unit_log` は「学習実績の本体」で、**いずれも `_log` という名前だが純ログではないので移行する**（[基盤](01-foundation/review.md#user_login_chk_log--なし)）。

| 旧テーブル | データ種 | 新環境の受け皿 |
|---|---|---|
| `user_login_log` | B09 ログイン履歴 | `login_history` |
| `user_login_log_monthly` | B09 ログイン履歴 | `login_history`（月次集計は持たない） |
| `mail_send_batch_log` | U07 メールテンプレート | `email_send_logs` |
| `mail_send_user_log` | U07 メールテンプレート | `email_send_logs` |
| `mail_follow_user_log` | U05 フォローメール | `retention_sends` |
| `line_send_batch_log` | U06 LINE 連携・配信 | `line_send_logs` |
| `line_send_user_log` | U06 LINE 連携・配信 | `line_send_logs` |

---

## 7. ETL 設計に段（L0〜L9）の割当が無いが、受け皿はあるデータ種（18件）

`scrun-etl-design.md` §4 の L0〜L9 はどの段でも扱っていないが、新環境に受け皿があるもの。**ETL 設計の穴か、意図的な対象外かを確認する必要がある。**

| ID | データ種 | 新環境の受け皿 |
|---|---|---|
| B01 | テナント | `tenants` ほか |
| B02 | ロール | `user_roles`（L1 のユーザー移行に含まれる可能性） |
| B09 | ログイン履歴 | `login_history` |
| O27 | バッジ | `digital_badges` ほか |
| O28 | リモート PC | `remote_pc_*` |
| L04 | リマインド | `live_reservations.reminded_at`, `email_send_logs` |
| J04 | 購入時自動割当 | `enrollments.source='purchase'` |
| K05 | 継続課金 | `learner_subscriptions` ほか 9 テーブル |
| K09 | 消費税設定 | `receipt_settings.tax_rate` |
| K12 | 特商法・規約 | `user_consents`, `consent_kinds` |
| U02 | お知らせ既読 | `announcement_reads`（ETL 設計は「`news_user` は写さない」と明記） |
| U05 | フォローメール | `retention_rules`, `retention_sends` |
| U07 | メールテンプレート | `tenant_email_templates` ほか |
| U11 | 掲示板 | `discussion_posts` ほか |
| S01 | 求人の掲載・応募 | `career:job_postings` ほか |
| S02 | 求人企業ページ | `career:companies` |
| S05 | 就活プロフィール | `career:learner_career_profiles` ほか |
| S06 | 面談（予約・記録） | `career:interview_records` ほか |

S01 / S02 / S05 / S06 は career-backend 側で、ETL 設計 §5-8 が「Wave 4 と同時。Step 2 に回すなら移行も第 2 段」としているもの。K05 継続課金は `kiracari-migration-estimate.md` が「最大リスク: 継続課金カードが移行できない」としている項目で、**段の割当が無いこと自体が要確認**。

---

## 8. PDF の 95 データ種に該当しない旧テーブル（27件）

PDF は「これまでのデータ種の粒度で分割した対照表」だが、lw2 の342テーブルのうち27件はどのデータ種にも当てはまらない。**PDF の粒度から漏れている機能の一覧**で、移行スコープを詰めるときに最初に見るべきもの。

| 機能 | テーブル | 件数 |
|---|---|---:|
| ディスカッション | `discussion`, `discussion_board`, `discussion_board_comment`, `user_learning_discussion`, `user_learning_discussion_alert` | 5 |
| テスト成績集計 | `calc_param`, `category_question_result`, `entire_question_result`, `entire_test_result`, `summary_user_learning_test`, `user_test_result` | 6 |
| 学習カルテ | `personal_record_advice`, `personal_record_detail_open_status`, `personal_record_open_status` | 3 |
| テナント課金集計（LMS事業者向け請求） | `accounting_user`, `accounting_user_detail`, `config_closing_date` | 3 |
| バッチ実行管理 | `batch_schedule`, `batch_schedule_detail` | 2 |
| クッキー同意 | `config_cookie`, `user_cookie_log` | 2 |
| いいね・フォロー・既読 | `like_user`, `follow`, `user_content_viewed` | 3 |
| その他 | `user_approver`（承認者）, `community_cate`（コミュニティカテゴリ）, `csv_request`（CSV一括登録） | 3 |

このうち**ディスカッション 5件**は、新環境に `discussion_posts` 系という受け皿がある（U11 掲示板に割り当て済み）ため、データ種を新設して扱う余地がある。**テスト成績集計 6件**は新環境に集計テーブルが無く（btoc は都度計算）、移行対象外で問題ないと思われる。

未分類の残り40件（機能設定16 / 共通マスタ9 / 一時8 / 純ログ7）は [旧環境逆引き](legacy-table-coverage.md) を参照。

---

## 9. 複数のデータ種にまたがる旧テーブル（17件）

種別カラムやポリモーフィック列で1テーブルが複数のデータ種を兼ねているもの。**移行ツールは行単位で振り分ける必要がある。**

| 旧テーブル | 主 | 副 | 振り分けの鍵 |
|---|---|---|---|
| `user` | B06 会員プロフィール | B03 メールログイン, B04 login_id ログイン, B05 パスワード, S05 就活プロフィール | カラム単位 |
| `payment_application` | K02 クレジット決済 | K03 銀行振込, K04 コンビニ決済, K05 継続課金, K06/K07 分割払い, L06 チケット購入 | `payment_type`（0=ライブ予約起票 / 1=クレジット / 3=銀行振込 / 7=チケット利用）+ `is_use_split_payment` |
| `enquete_answer` | O14 ユニットアンケート | O16 お知らせ添付, O17 レポート添付 | `entity_type_id`（1=お知らせ 545件 / 2=ユニット 1,308件 / 3=レポート 611件） |
| `unit` | O04 講義ユニット | O05 見出しブロック, O20 講座資料ユニット | `unit_type_id`（0=見出し / 1=講義 / 2=テスト / 3=アンケート / 4=レポート / 5=集合研修 / 6=講座資料） |
| `user_certificate` | O25 修了証（講座単位） | O26 修了証（商品単位） | `type`（1=講座 / 2=商品） |
| `enquete_question` | O14 ユニットアンケート | O15 ファイル添付設問 | `question_type`（1=単一選択 / 2=複数選択 / 3=自由記述 / 4=ファイル添付 **7件・受け皿なし**） |
| `user_learning_test_sub` | O10 テスト設問別回答 | O11 テスト自由記述 | `question_answer` 列の有無 |
| `user_learning_unit` | J02 ユニット進捗 | J03 SCORM 中断データ | `suspend_data` 列 |
| `user_learning_lesson` | J01 受講権限 | O24 受講期限・延長 | `limit_date` 列 |
| `user_learning_report` | O18 課題 | O19 課題の提出ファイル | `eval_save_file_name1..5` 列 |
| `lesson` | O01 講座 | O03 講座サムネ | `lesson_img_file_name` 列 |
| `lecture` | O04 講義ユニット | O06 講義動画 | `pmovie_*` 列 |
| `test` | O08 テスト定義 | O13 テスト受験回数制限 | `exam_max_number` 列 |
| `news` | U01 お知らせ配信 | U03 お知らせ添付ファイル | `news_save_file_name1..5` 列 |
| `news_user` | U02 お知らせ既読 | O16 お知らせ添付アンケート | `enquete_answer.entity_id` からの参照 |
| `inquire_answer` | U08 問い合わせ | U09 問い合わせ添付ファイル | ファイル列（質問側3本 + 回答側3本） |
| `assign_item` | J04 購入時自動割当 | J06 自動割当（求人） | 割当対象の種別 |

これら17件以外に、複数のデータ種へ二重計上されているテーブルは無い。

---

## 10. 分類の前提と限界

- **lw2 には外部キー制約が1本も無い。** 逆引き表の「根拠 = 関連(推定)」は、lw2 の `docs/db` が列名から推定した関連を辿って引き寄せたもの。実データでの検証はしていない
- **新環境の `docs/db` と `tools/gen_db_docs/` は両リポジトリとも untracked**（作業ツリーにのみ存在する未コミット状態）。本分類はその内容を 2026-09-21 時点で参照した
- **PDF の ◯/X は「機能の有無」**であり、PDF 自身が「データを移せるか、recademy が使っているかは別」と断っている。本分類の再判定も同じ定義に揃えている
- カラムレベルの写像（どの列をどの列へ、どう変換するか）は本分類の範囲外。`school-launcher/docs/scrun-etl-design.md` §5 が持っている

---

## 付録. PDF 原文の転記

PDF からの転記が正しいことは、区分ごとの件数が PDF 冒頭の集計表と一致することで検算した。

| 区分 | PDF の集計 | 転記結果 |
|---|---|---|
| 基盤 | 12（◯6 / X6） | 一致 |
| オンデマンド | 28（◯16 / X12） | 一致 |
| ライブ | 9（◯5 / X4） | 一致 |
| 受講 | 6（◯3 / X3） | 一致 |
| 課金 | 13（◯11 / X2） | 一致 |
| 運営 | 14（◯6 / X8） | 一致 |
| 就職支援 | 8（◯3 / X5） | 一致 |
| 対象外 | 5（◯0 / X5） | 一致 |
| **合計** | **95（◯50 / X45）** | **一致** |

データ種名・既存の主なテーブル・◯X の転記内容は [データ種別対照表](data-type-mapping.md) の「データ種」「旧テーブル」「PDF」列に反映している。

> PDF の抽出について: この環境には poppler / pypdf が無く `pdftotext` が使えない。macOS の PDFKit（`swift` + `PDFDocument.page(at:).string`）で抽出した。ページ内のテキスト順はセル単位で分断され、「データ種」列がまとまって出た後に「既存の主なテーブル + ◯X」がまとまって出るため、両者を順序対応で突き合わせたうえで上記の件数検算を行っている。
