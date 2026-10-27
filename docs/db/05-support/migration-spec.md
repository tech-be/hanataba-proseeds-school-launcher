# サポート機能 — 移行仕様

区分 **5 サポート機能**（LINE 友だち紐付け / クーポン / お知らせ / 問い合わせ / ファイル /
就業支援 / コミュニティ / 利用料の集計 / その他）を移行ツールでどう流すか。共通の方針は
[migration-spec.md](../../migration-spec.md)、突き合わせは [review.md](review.md)、
追加するスキーマは [schema-additions.md](schema-additions.md)。

> **2026-10-26: 5-2 クーポン / 5-3 お知らせ / 5-4 問い合わせ / 5-6 の就活プロフィール・企業・面談 / 5-7 の講座のディスカッション / 5-9 自動メールの文面を実装した。掲示板・お仕事募集は移行対象外。** 決定と移し方は **0 章が正**で、1〜3 章の「未実装」「Step も migration も無い」などの記述は 0 章より前のもの。スキルチェックは未実装のまま。
> 5-6・5-7 の一部と 5-8 は、2026-09-30 に「どの区分にも仕分けていなかった旧テーブル」から足した。

> **この区分は「9項目の寄せ集め」で、依存も投入先もばらばら。** 5-9 その他は移さない表だけ（Step は無い）。
> 1本の流れとして設計せず、項目ごとに独立して扱う。

## 0. 見直し: 未実装の移行（2026-10-26 決定・実装済み）

移行の見直しの手順 3（[進捗](../rework-progress.md)）。[機能仕様書](functional-spec.md)と[テスト仕様書](test-spec.md)のケースが通るように、まだ移していないもの（[not-migrated-summary の 3](../not-migrated-summary.md#3-移行ツールが未実装でまだ移していないもの)）の移し方を決める。
件数はステージング `tenant_id = 10`（削除済みを含む）。旧のコードの場所は learningware-kiracari からの相対パス。

### 0-0. 全体に効くこと

| # | 事実 | 案 |
|---|---|---|
| 0-0-1 | ID の名前空間は決まっている。自動割当の付与先（`billing/assign.py:46-52`）が `ulid.for_row("news" / "announce" / "coupon", 旧 ID)` で作っている（tenant 10 で news 187・188・189・290、coupon 1） | 05 でも同じ名前空間で作る |
| 0-0-2 | **新の `announcements` / `coupons` / `inquiries` / `community_*` には `deleted_at` が無い**。共通のルール「削除済みも `deleted_at` を入れて移す」がそのままでは守れない | **Q1** で決める |
| 0-0-3 | 旧の本文に HTML がある（お知らせ 54・アナウンス 30・求人 154）。新はプレーンテキストで表示し、タグがそのまま見える | 移行ツールは値を作り替えない（HTML のまま入れる）。直すなら `fixups`（**Q2**） |
| 0-0-4 | 投入先が 2 つになる（btoc と career） | career の DB は環境変数 `TARGET_CAREER_DB_URL` で受け取る。career の区分は btoc の会員・テナントの ULID を使う |

### 0-1. お知らせ（`news` 267 件・`announce` 35 件 → `announcements`）

旧は 2 系統: `news`（件名と本文。お知らせの一覧）と `announce`（件名が無い。トップページの帯）。
**旧の配信対象は「会員の一覧」**（配信したときに対象者全員の `news_user` / `announce_user` の行を未読で作る。グループ・属性の条件は検索に使うだけで保存されない）。

| 新 | `news` から | `announce` から |
|---|---|---|
| `id` | ULID（`news`） | ULID（`announce`） |
| `title` | `news_title`（最大 56 字） | **元の値が無い**（**Q3**） |
| `body` | `news_detail` | `message` |
| `status` | 生きている → `published`（下書きは 0 件）。削除済みは **Q1** | 同じ |
| `audience_type` | **すべて `specific_users`**。生きている `news_user` の行を `announcement_user_targets` に | 生きている `announce_user` の行を同じく |
| `publish_start_at` / `published_at` | `disp_start_date`（JST → UTC） | 同じ |
| `publish_end_at` | `disp_limit_date` が 0 でなければその日の終わり（翌日 0 時 JST。1 件） | `disp_end_date` で同じ（7 件） |
| `reply_type` | 0 / 1 / 2 のまま | 0 |
| `created_by` | `writer_user_id` | `set_user_id` |
| `line_body` | `line_message.message`（1 行） | — |
| `announcement_reads` | `news_disp_date` が 0 でない行（102） | `disp_time` がある行（15。旧の不具合で既読がほぼ記録されていない） |
| `announcement_replies` / `_reply_comments` | `news_reply` 12 行、運営のコメント 2 行 | — |
| `announcement_attachments` | 4 件・8 ファイル（**Q4**） | — |

- **既読を移す。** 以前の方針「`news_user` は写さない」は見直す（新は行が無ければ未読なので、移さないと全部未読に見える）。
- **移さないもの**（`not-migrated.csv`）: 対象から外された行・削除済みのお知らせの対象（`news_user` 36・`announce_user` 102）、会員がいない行（各 1）。返信は 12 件すべて移す（新は 20260923112727 から同じ会員の返信を履歴として複数持てる。調査の時点の「2 件目は入らない」は誤り）。`news.disp_end_date`（返信の締め切り 2 件）・アンケート付き（8 件）・催促の設定は受け皿が無い（文書に記録）。
- `purchasers` は使わない（functional-spec 0-1）。

### 0-2. クーポン（7 件 → `coupons`）

**旧の 7 件は、新で旧と同じ意味では使えない。**
- 旧の対象は「商品」（7 件とも講座の商品。商品は新でコースとして移っている）。新のクーポンは対象の商品を持たず（`coupon_course_targets` は配信対象）、**コースの購入では使えない**。
- 無料クーポン（1・3）に当たる割引の種類が無い。
- 有効のまま `one_time` で入れると、**どの講座の単品購入にも使え、旧より広く効く**。

| 新 | 旧 |
|---|---|
| `status` / `visible_to_learners` | **`inactive` / FALSE**（記録として残す。**Q5**） |
| `discount_type` / `discount_value` | 2 → `amount`、3 → `percent`。**1（無料）は Q5** |
| `validity_type` | 期限なし → `none`。1018・1019（作った日と登録日の遅い方から 31 日）→ `registration_days` 31。2（登録日の 1 日後から 1 日）は表せない → `none` で記録 |
| `audience_type` / `coupon_user_targets` | 全員 → `all_users`。個人（クーポン 1 の 181 人）→ `specific_users`、`created_at` に旧の `regist_date` |
| `coupon_redemptions` | `coupon_log` 2 行 |
| `provider_coupon_id` / `provider_promotion_id` | 空文字（recademy の決済がロボットペイメントなら問題ない。**Q6**） |
| `code` / `name` | そのまま（17 字。照合順序で大文字にしても引ける） |

- 対象の商品（`coupon_item` 10 行）は受け皿が無い → 一覧に出す。

### 0-3. 自動メールと LINE の文面（`mail_setting` 39 行 → `tenant_email_templates`、`line_message_mail_setting` 1 行 → `tenant_line_templates`）

- 旧の差し込みは `{UPPER_SNAKE}` だけ。HTML は 0。長さは新の上限に収まる。
- **新に種別があるものだけ移す**（候補: 13 → `password_reset`、20 / 35 → `welcome`、21 / 47 / 34 → `payment_succeeded`、23 / 32 → `subscription_canceled`、31 → `email_verification`、7 → `inquiry_received`）。新に種別が無い・送る処理が無いもの（約 26 行。en の 1 行を含む）は一覧に出す。
- **同じ新の種別に旧の種類が 2 つ以上当たる**（**Q7**）。
- **差し込みの書き換え**（`{USER_NAME}` → `{{user_name}}` など）は値の作り替えなので、**移行ツールでは行わず `fixups` で行う**（**Q8**）。書き換えないと、メールでは文字のまま届き、LINE では消える。`{PASSWORD}` を含む文面（20・35）は新がパスワードを送らないので、文面を直す必要がある。旧の 31（確認コード）と新の `email_verification`（リンク）は仕組みが違う。
- 署名（`mail_footer`）・会員の受信設定（`mail_setting_user` 1,272 行）・手で送るテンプレート（`mail_template` 7 行）は移さない（受け皿が無い）。

### 0-4. 問い合わせ（`inquire` 47 件 → `inquiries`）

- テナントは `inquire_cate.tenant_id` で絞る。旧の `inquire_answer` は 1 行が「質問＋回答」。
- 回答がある → `resolved`（`resolution`・`resolved_at` = `answer_end_time`・`assignee_id` = `answer_user_id`）。回答が無い → `open`。`question` は 1 行目の質問。
- **移さないもの**: ログインしていない人の問い合わせ 15 件（`user_id` が NOT NULL。DB の制約の衝突。メールで会員に結ぶのは値を作ることになるので避ける）、2 往復目の 5 行（新は 1 往復）。講座の指定（7 件）・添付（7 行）は受け皿が無い。
- **分類**（**Q9**）: 新の既定 5 つ（course_content・payment・environment・account・other）を入れ、旧の 7 分類を対応させる。**`other` は必ず入れる**（無いと新しい問い合わせが 500）。

### 0-5. 掲示板（`bbs` 有効 12・削除済み 4 → `community_*`）

- 旧の `bbs` 1 件は 1 スレッド（件名と本文）。公開範囲を講座・商品・属性・ロールで絞れる。新はテナントのチャンネルで、**参加者になれば誰でも読める**（旧の公開範囲は保てない）。
- 掲示板 1 件 → チャンネル 1 件（`name` = 件名、`description` = 本文、`created_by` = 作成者）。コメント・返信（有効 22・削除済み 8）→ `community_messages`（**返信の親子は失われる**）。
- 削除済みの掲示板は `hidden`、期限切れ（1 件）は `archived`（**Q1**）。
- **参加者**（**Q10**）: (a) 旧の公開範囲を展開して入れる（約 21,000 行）／(b) 書いた人と作成者だけ。
- いいね 22 行・既読は受け皿が無い → 一覧に出す。

### 0-6. 講座のディスカッション（投稿 7 件 → `discussion_posts`）

- 7 件とも親の投稿（返信 0）、有効。`lesson_id` = 旧ユニットの ULID（`ulid.for_row("unit", unit_id)`。content で移し済み。共有講座のユニット 2 件を含む）。`parent_id` NULL、`status = active`。
- お題（`discussion_board` 10 件の名前・本文）・採点（3 件）・通知の設定（4 件）は受け皿が無い → 一覧に出す。

### 0-7. career

| 旧 | 事実 | 案 |
|---|---|---|
| `recruit` 154 件（お仕事募集） | **求人票ではない。** 企業・雇用形態・勤務地・給与の列が無く、本文の HTML に書かれているだけ。配信先（`recruit_user` 574 行）はほぼ管理者どうしの回覧（受講者は 1 名） | **`job_postings` に移さない**（必須の企業・雇用形態を作り出すことになる）。**Q11** |
| `recruit_user` 574 行 | 応募ではなく配信先と既読 | `matches` に入れない（一覧に出す） |
| `company` 10 件 | `tenant_id` が無い（`user.company_id` でたどる）。新の必須 `industry` / `contact_email` が無い | **Q12** |
| `interview_record` 1 件 | 日付だけ（時刻・枠が無い）、内容が空。担当者は 1 名 | **Q13**（推奨: 移さない） |
| `user.employment_status` | 旧は 0 = 未就業 / 1 = 就業 の 2 値。新の値（正社員など「今の働き方」）と意味が合わない | **空（`''`）で入れる**（一覧外の値は保存を止める。**Q14**） |
| `user.desired_employment_status` | 1 正社員・2 契約社員・3 派遣社員・4 パート | `desired_employment_types` に 1 → `full_time`・2 → `fixed_term`・3 → `temporary`・4 → `part_time`（92 名） |
| `user.desired_job_location` | 都道府県 ID 1 つ（99 = 海外） | `learner_desired_prefectures` に短い表記（「東京」）で 1 行（91 名）。単数の列は NULL |
| `user.education` / `job_category` / `qualification` | 自由記述（最大 29 / 29 / 18 字） | そのまま |
| `learner_career_profiles` | 会員 1 人に 1 行（UNIQUE） | 上のどれかに値がある会員だけ作る。`learner_name` = `users.name` |

### 0-9. 決まったこと（2026-10-26 の回答）

| # | 決定 | 補足 |
|---|---|---|
| Q1 | **新にある状態に合わせて移す。当てはまる状態が無い表は、新に `deleted_at` を足して入れる** | お知らせ → `withdrawn`。問い合わせ（6 件）は `inquiries.deleted_at` に入れる（school-launcher `20261026120000_add_inquiry_deleted_at.sql` を作った。作業ブランチ `feat/lw2-migration-rework`）。新アプリの一覧・詳細が `deleted_at IS NULL` で絞るよう直した（`inquiry_repo.go`。結合テスト済み）。掲示板は Q10 で対象外 |
| Q2 | **本文をプレーンテキストに直す** | 値の直しは `fixups` で行う（共通のルール）。HTML を除いた本文を補正データにし、移行ツールは読むだけ |
| Q3 | 推奨どおり（固定の文言） | — |
| Q4 | **添付のファイルは移せない** | `announcement_attachments` の行も移さない（ファイルの無い行はリンク切れになる）。4 件・8 ファイルを一覧に出す |
| Q5 | **移す**。ただし**無料クーポン（1・3）は移さない**（新に「N 日間無料」に当たる割引の種類が無い。一覧に出す） | **残る 5 件（2・4・1017・1018・1019）は旧のとおり有効（`active`）で移す**（2026-10-26 決定）。新は対象の商品を持てないので、**どの講座の単品購入にも使える**（旧より広く効く）。受講者に見せるか（`visible_to_learners`）は旧に当たる値が無いので FALSE |
| Q6 | **あるデータを移す** | 旧に決済代行の ID は無いので `provider_*` は空文字 |
| Q7〜Q9 | 推奨どおり | — |
| Q10 | **掲示板は移行対象外** | `bbs` / `bbs_comment` / `bbs_set_*` / いいねを理由「移行対象外」で一覧に出す |
| Q12 | **企業の業種・連絡先メールは NULL で移す** | career `20261026120000_nullable_company_industry_contact_email.sql` で NULL 可にした（作業ブランチ）。新アプリは NULL を Go の string に読むので、読むときは空文字にし、書き戻すときは NULL のまま保つよう直した（`company_repo.go`。結合テスト済み。2026-10-26 にアプリの修正の了承を得た） |
| Q14・Q15 | 推奨どおり | — |
| Q11 | **お仕事募集（`recruit` 154 件）は移さない** | 旧の `recruit` には企業・雇用形態の列が無い（表の作り）。`recruit_user` 574 行・`line_message_recruit` 4 行も移さない。一覧に出す |
| Q13 | **面談 1 件を移す** | 担当者（`advisors`）を旧のカウンセラーの会員から作り、面談日の 0 時（JST）で予約済みの枠（`availability_slots`）を 1 つ作る。状態 `completed`、目的 `career_consultation`、記録の要約は空文字 |

### 0-10. 実装と確認の結果（2026-10-26）

- 実装: `migrator/steps/support/`（`announcements.py`・`coupons.py`・`inquiries.py`・`templates.py`・`community.py`・`career.py`・`out_of_scope.py`）。career の DB は `TARGET_CAREER_DB_URL`
- 確認: 照合の差 0、旧 DB との突き合わせ（support 23 項目）一致、テスト仕様のデータの確認（support 21 項目）通過、流し直しで 0 件、E2E 10 ケース通過（[テスト仕様の結果](test-spec.md#結果)）
- **自動メールの文面 6 件・LINE の文面 1 件は、まだ移らない。** 新に当たる差し込みが無い旧の差し込み（`{PASSWORD}`・`{LOGIN_ID}`・`{URL}`・`{CODE}` など）が残る文面は、移すと文字のまま会員に届くので、**補正データに直した文面が書かれるまで一覧に出す**（`fixups text` の空欄 7 行。運営に文面を決めてもらう）
- 本文のプレーンテキスト化（Q2）は `fixups text` の提案（お知らせ 56・アナウンス 30）を補正データに入れて確かめた。旧で `&lt;` と書かれていた「<」は文字として残る（旧でも文字として見えていた）

**移さないもの（ステージング。`out/not-migrated.csv` の support の 1,236 行）**

| 対象 | 行 | 理由 |
|---|---:|---|
| お仕事募集（`recruit` 154・`recruit_user` 574・`line_message_recruit` 4） | 732 | 移行対象外（Q11） |
| クーポンの対象者（無料クーポン 1 の 181 人） | 181 | 移行対象外（親のクーポンを移さない） |
| 外された配信先（お知らせ 36・アナウンス 102）と、その既読 3 | 141 | 移行対象外 |
| 掲示板（`bbs` 16・コメント 30・公開範囲 5・いいね 22） | 73 | 移行対象外（Q10） |
| 自動メールの文面（新に種別が無い 28・採らなかった種類と英語 5・差し込みの文面待ち 6）・LINE の文面（文面待ち 1） | 40 | 受け皿なし 28 / 移行対象外 12 |
| 問い合わせ（ログインしていない人 15・2 往復目 5・添付 10） | 30 | NOT NULL `user_id` 15 / 受け皿なし 5 / 移行対象外 10 |
| お知らせの添付 | 8 | 移行対象外（ファイルを移せない。Q4） |
| クーポン（無料 2）・対象の商品 10 | 12 | 移行対象外 2 / 受け皿なし 10 |
| ディスカッションのお題 10・採点 3・通知の設定 4 | 17 | 受け皿なし |
| 配信先の会員がいない行（`user_id=911` など） | 2 | 外部キー `user_id` |

### 0-8. 決めてほしいこと（2026-10-26 時点の案。決定は 0-9）

| # | 内容 | 推奨 |
|---|---|---|
| Q1 | **削除済みの行**（お知らせ 14・アナウンス 20・問い合わせ 6・掲示板 4 とコメント 8）。新の表に `deleted_at` が無い | お知らせは `withdrawn`、掲示板は `hidden` / `deleted`（新の状態にある値）で移し、文書に書く。問い合わせは状態に当てはまるものが無いので一覧に出す。（別案: 新に `deleted_at` を足す migration を提案する） |
| Q2 | 本文の HTML（お知らせ・アナウンス・求人） | HTML のまま入れる（値を作り替えない）。表示の崩れは運営に見てもらい、直すなら `fixups` |
| Q3 | アナウンスの件名（元の値が無い） | 固定の文言（例「アナウンス」）を入れ、文書に書く |
| Q4 | お知らせの添付 8 ファイル | 行は移す。ファイルの実体をストレージに移す作業は別にする（ファイルの区分 5-5 と同じ扱い） |
| Q5 | クーポン 7 件（旧と同じ意味で使えない。無料クーポン 2 件は種類が無い） | `inactive`・受講者に見せない、で記録として移す。無料の 2 件は一覧に出す |
| Q6 | recademy の決済（Stripe かロボットペイメントか） | 確認だけ（ロボットペイメントなら `provider_*` は空文字でよい） |
| Q7 | 同じ新の種別に当たる旧の文面（20 と 35、21・47・34、23 と 32） | 一般の登録 20、通常の申込 21、解約 32 |
| Q8 | 差し込みの書き換え・`{PASSWORD}` の削除 | `fixups` で書き換えた値を補正データにし、移行ツールは読むだけ |
| Q9 | 問い合わせの分類の対応 | 既定 5 つを入れ、旧のシステム系 → environment、その他・テスト → other、講座名の分類 → course_content。recademy の software・job_career は本番の分類名を見てから |
| Q10 | 掲示板の参加者 | (a) 旧の公開範囲を展開（旧で読めた人がそのまま読める）。講座・属性などの制限が保てないことは運営に確認 |
| Q11 | お仕事募集 154 件 | 移さない（`job_postings` の形ではない）。残す必要があるかを運営に確認 |
| Q12 | 企業 10 件（業種・連絡先メールが無い） | 運営が値を決めるまで移さない（一覧に出す） |
| Q13 | 面談 1 件（枠・内容が無い） | 移さない（一覧に出す） |
| Q14 | 就業状況（旧の 2 値） | 空で入れる。2 値を残したいなら新に受け皿が要る |
| Q15 | career の DB に書く | 取り決め（career には書かない）を見直し、就活プロフィールと希望勤務地だけを書く（Q11〜Q13 が推奨どおりなら、求人・企業・面談は書かない） |

## 0R. 見直し: 残りの範囲（2026-10-26 決定）

移行の見直しの手順 3（[進捗](../rework-progress.md)）。区分 05 の残り（LINE の友だちの紐付け・ライブラリ・運営メモ・スカウトのフォロー・コミュニティの分類・利用料の集計）について、[テスト仕様書](test-spec-remaining.md)のケースが通るように移し方を決める。

### 0R-1. 旧のデータで分かったこと（ステージング `tenant_id = 10`）

| ケース | 分かったこと |
|---|---|
| N-01・N-03 | `user.line_id` は 4 件で、**すべて同じ LINE の ID**（大文字小文字・空白を除いて同じ）。会員 4 人のうち 3 人は削除済み。補正データ（`overrides.csv`。01 で作った）が削除済みの 3 人の値を空にしているので、移るのは生きている 1 人だけ。形の違う ID は 0 件 |
| N-02 | 今の移行ツールは、形の違う ID を**ログに出すだけで一覧に出さない**（移さない行を黙って落としている） |
| B-01・B-02 | 資料フォルダ（`drive`）3 件。グループで絞ったものは 0 件（1 件は非公開）。講座の資料（`unit_attached_file`）79 件で、グループ・属性での絞り込みは 0 件（共有講座を含む）。ただし今の移行ツールは、グループで絞ったフォルダを**対象 0 件の個別指定**で入れる作りで、新ではそのフォルダが誰にも見えず、運営が開いて保存すると 400 になる |
| B-03 | 資料のファイルの場所（`storage_key`）は旧のファイル名のまま。ファイルの移送（L9）で新のキーに直すまで、開くとストレージで 404 |
| M-01・M-02 | 運営メモ（`personal_record_advice`）1 件。削除済みではなく、書いたのは同じテナントの会員。今の移行ツールは削除済みも `deleted_at` 付きで入れる（新は読まずに表示する） |
| X-01 | フォロー 14 件・コミュニティの分類 3 件・利用料の集計（1・111・18,122 件）。新は読まない |

### 0R-2. 決めたこと（2026-10-26。すべて推奨で決定）

| # | ケース | 案 | 推奨 |
|---|---|---|---|
| Q1 | N-02 形の違う LINE の ID | (a) 今のまま（ログだけ）<br>(b) 理由「旧データの不整合」で一覧に出す | **(b)**（移さない行は黙って落とさない） |
| Q2 | N-01 同じ LINE の ID が複数の会員に付く | (a) 今のまま（補正データで、生きていない会員の値を空にする）<br>(b) 移行ツールで、生きている会員を優先して残りを一覧に出す | **(a) ＋ 重なりが残れば一覧に出す**。重なったまま入れると、後の会員は連携されないのに成功と表示される（新の不具合）。今は UNIQUE に当たった行が制約違反で一覧に出る |
| Q3 | N-03 削除済み・利用停止の会員の紐付け | (a) そのまま移す（新は会員の状態を見ずに LINE を送る）<br>(b) 移すが `is_friend = FALSE` にする（送らない）<br>(c) 移さず一覧に出す | **(b)**。値は残るが、退会者に LINE が届かない。会員を戻しても、友だち追加し直すまで送られない。ステージングは 0 件 |
| Q4 | B-01 グループで絞ったフォルダ | (a) 今のまま（対象 0 件の個別指定。誰にも見えず、運営が保存できない）<br>(b) **全員向け・非公開**で入れる（運営が公開先を決めて公開する）<br>(c) 全員向け・公開で入れる（グループの絞り込みが外れて全員に見える） | **(b)**。ステージングは 0 件 |
| Q5 | B-03 資料のファイルの場所 | ファイルの移送（L9）で新のキー（`library/<tenantID>/<folderID>/<ULID>.<拡張子>`）に直す。それまでは件数を出して NG のまま | 推奨（02 の動画と同じ扱い。L9 は別に決める） |
| Q6 | M-01 削除済みの運営メモ | (a) 今のまま（`deleted_at` 付き。新は生きたメモとして出す）<br>(b) 移さず、理由「受け皿なし」で一覧に出す | **(b)**（03 の削除した受講の記録と同じ扱い）。ステージングは 0 件 |
| Q7 | X-01 新が読まない表 | 今のまま（受け皿として残す） | 推奨 |

---

## 他の区分と違うところ

| 項目 | 違い |
|---|---|
| **5-6 就業支援** | **求人・面談の移行先が career-backend**（btoc とは別 DB）。移行ツールは btoc に接続しており、**そのままでは投入できない**。助言メモ・フォローは btoc に入る |
| 5-8 利用料の集計 | **新のアプリがまだ読まない表**に移す。集計した時点の会員の写しなので、**旧で消えた会員も含む** |
| 5-2 クーポン | **課金（4）の商品→講座の対応が先**。`coupon_item` が商品単位 |
| 5-3 お知らせ / 5-4 問い合わせ | **添付ファイルの受け皿が無い**（296件 / **706件**）。ファイル移送（L9）とセットで決める |

---

## 1. 前提

### 1-1. 運営への確認事項

**この区分の分も含めて [open-questions.md](../open-questions.md) に1枚でまとめてある。**
同じ話を2か所に置かない。

### 1-2. 制約による不整合

**[constraint-violations.md](../constraint-violations.md) にまとめてある。**
NOT NULL / UNIQUE / CHECK に当たるものと、参照先が物理削除されているものを分けて持つ。

### 1-3. 決定済み（再確認だけ）

| 決めたこと | 内容 | 決めた日 |
|---|---|---|
| LINE の公式アカウントは継続する | 基盤（01）で決定済み（[01 1-3](../01-foundation/migration-spec.md)）。`line_links` ほか LINE の表は移す | 2026-09-23 |
| 教材の公開範囲はグループ単位のまま持つ | ユーザー単位に展開すると、**後から会員をグループに足しても自動で公開されない** | 2026-09-24 |
| 教材は旧より広く見せない | 添付資料は講座ごとのフォルダで「その講座の受講者に公開」。新に機能の無い公開範囲は受け皿に残し、機能ができるまで非公開か「対象者なし」 | 2026-10-01 |
| 属性単位の公開の受け皿は作らない | 旧に対応データが無い（`drive_attribute` に相当する表が lw2 に無い） | 2026-09-24 |
| ライブレビューは受講（3）が持つ | ライブ単位のレビューは `enrollment.6`。この区分の担当ではない | 2026-09-24 |
| 仕分けていなかった旧テーブルは 05 に入れる | 既存の表に寄せられるものは寄せ、無ければ旧の構造のまま新設する（助言メモ → `admin_notes`、フォロー・分類・集計は新設） | 2026-09-30 |
| 逆引きで未分類の表は、01・06 が持つもの以外すべて 05 に入れる | 移すもの（5-6〜5-8）と、移さないもの（5-9 その他。ログ・一時データ・システムのマスタなど）に分けた | 2026-09-30 |
| `calc_param` は保留 | 模試の集計条件。模試（06 対象外）と一緒に [E63](../open-questions.md#e-切り替え後の機能で決めておきたいこと) の回答で決める | 2026-09-30 |

### 1-4. 本番ダンプ受領後に確認すること

- **`coupon_group`**（実測0件）。本番で出たら対象者割当の扱いを決める
- **`bbs_set_*` 5種の公開範囲**。実測を見てから受け皿の要否を決める
- **添付ファイルの実体**（L9 の移送対象）。件数と総容量

### 1-5. ステージングダンプでの実測（2026-09-18 取得）

| 項目 | 旧テーブル | 全テナント | ReCADemy |
|---|---|---:|---:|
| 5-1 LINE | `line_send` / `line_send_batch` | 31 / 36 | — |
| 5-2 クーポン | `coupon` / `coupon_user` / `coupon_log` | 18 / 181 / 4 | **7** / — / — |
| 5-3 お知らせ | `announce` / `news` | 37 / 309 | **35 / 267** |
| 〃 既読 | `announce_user` / `news_user` | 1,147 / 1,214 | — |
| 〃 メール | `mail_template` / `mail_send` | 10 / 2,771 | **7** / — |
| 〃 Web Push | `message_send` / `subscription` | 230 / 1,157 | — |
| 5-4 問い合わせ | `inquire` / `inquire_answer` / `inquire_cate` | 56 / 62 / 16 | — / — / **7** |
| 〃 個別メッセージ | `thread` / `thread_comment` | 20 / 25 | — |
| 5-5 ファイル | `drive` / `unit_attached_file` | 111 / 6,250 | **3** / **79**（共有講座 173。移したのは 227） |
| 5-6 就業支援 | `recruit` / `portfolio` / `scout` | 154 / 1,846 / 111 | **154 / 1,837 / 109** |
| 5-7 コミュニティ | `bbs` / `unit_share` / `footprint` | 19 / 707 / 77 | **16** / — / **76** |
| 5-6 助言メモ・フォロー | `personal_record_advice` / `follow` | 33 / 382 | **1 / 14** |
| 5-7 分類 | `community_cate` | 203 | **3** |
| 5-8 利用料の集計 | `config_closing_date` / `accounting_user` / `accounting_user_detail` | 64 / 2,403 / 192,053 | **1 / 111 / 18,122** |
| 5-6 いいね | `like_user` | 27,117 | **6,559**（ポートフォリオ 6,537） |
| 5-7 既読・ディスカッション | `user_content_viewed` / `discussion_board` / `discussion_board_comment` | 271,315 / 13 / 122 | **1,383 / 10 / 7** |
| 5-9 その他（移さない） | `access_log` / `user_session` / `summary_user_learning_test` | 696,319 / 39,207 / 264,521 | **2,759 / 857 / 146** |

> 5-6 助言メモ以下の全テナントの値は [legacy-table-coverage.md](../legacy-table-coverage.md)（2026-07-28 ダンプ）、
> ReCADemy の値は 2026-09-30 にローカルの lw2 で数えた値。

---

## 2. データ登録順

**項目ごとに独立している。** 依存は前の区分に対するものだけ。

```
[前提]       区分1 基盤（users / tenant_groups）
             区分2 コンテンツ（lessons — 教材の公開対象が参照する）
                ↓
support.1    LINE 友だち紐付け        ← users
support.5    ファイル                 ← tenant_groups / lessons
support.6    就業支援（助言メモ・フォロー） ← users
support.7    コミュニティ（分類）      ← tenant_groups
support.8    利用料の集計             ← users（会員の写しが、移した会員を指すため）
                ↓
support.2    クーポン（未実装）        ← 課金（4）の商品→講座の対応
support.3    お知らせ（未実装）
support.4    問い合わせ（未実装）
support.6    就業支援（求人・面談・スキルチェックは未実装） ← **career-backend**
support.7    コミュニティ（掲示板・SNS 共有・足あとは未実装）
```

> **フェーズの番号は項目の番号と同じ**（`support.6` は 5-6）。未実装の項目も番号を空けてある。

### 2-2. 実行手順

```bash
.venv/bin/python -m migrator run --dry-run --section support --skip-preflight
.venv/bin/python -m migrator run --section support --skip-preflight
.venv/bin/python -m migrator verify
```

---

## 3. データ移行仕様

### 3.1 抽出（extract）

**`tenant_id` を持たない表が多い。** 親と join して絞る。

| 旧テーブル | 絞り込みの経路 |
|---|---|
| `unit_attached_file` | `unit` → `lesson.tenant_id` |
| `drive_group` | `drive.tenant_id` |
| `inquire` / `inquire_answer` | `inquire_cate.tenant_id` |
| `coupon_item` / `coupon_user` / `coupon_log` | `coupon.tenant_id` |
| `announce_user` / `news_user` | `announce` / `news` の `tenant_id` |
| `recruit_user` | `recruit.tenant_id` |
| `company` | **経路が無い**（`tenant_id` を持たず親も無い）。実測10件を目視で仕分ける |

`personal_record_advice` / `follow` / `community_cate` / `config_closing_date` / `accounting_user` /
`accounting_user_detail` は `tenant_id` を持つので、そのまま絞る。
`accounting_user_detail` は、**移行先に入っている会員**（`users.user_id`）を移行先から読み、写しの会員を引き当てる。

### 3.2 変換（transform）

**ファイル（5-5、実装済み）**

- `drive` はフォルダだけ。**中身のファイルは DB に無く**、ディスク上の `dir_name` 配下にある（L9 で運ぶ）
- **旧より広く見せない**（2026-10-01）
  - ユニット添付・講座添付は、**講座ごとの移行用フォルダ**に入れ、「その講座の受講者に公開」（`course_enrolled` ＋ `library_folder_course_targets`）
  - どのユニットの資料かは `library_material_lesson_targets` に残す
  - 資料ごとのグループ・属性の指定は `library_material_group_targets` / `library_material_tag_targets` に残し、**指定のある資料は非公開**
  - グループで絞っていたフォルダは `library_folder_group_targets` に残し、**全員向け・非公開**（`all_users`・`published = FALSE`）にする（0R-2 Q4。対象 0 件の個別指定は誰にも見えず、運営が保存できなかった）
  - 削除済みのユニット・講座・フォルダ・添付資料は非公開
- 公開範囲は**グループ単位のまま**。ユーザー単位に展開しない
- `kind` は `file`。`content_type` / `size_bytes` は L9 で入れる。`document_file_detail`（フォルダの中のファイルの説明）も L9 で突き合わせる

**就業支援（5-6、助言メモ・フォロー）**

- 助言メモは既存の `admin_notes` に寄せる。旧の `user_id` は**書いた人**（`author_id`）、`target_user_id` が**対象の会員**（`user_id`）、
  `update_user_id` は**最後に直した人**（`updated_by`。足した列。旧の 0 / NULL は NULL）
- **削除済みの助言メモは移さない**（理由「受け皿なし」で一覧に出す。0R-2 Q6。新は `admin_notes.deleted_at` を読まず表示する）
- フォローは `scout_follows` に旧の構造のまま移す。削除済みは `deleted_at` で残す

**コミュニティ（5-7、分類）**

- 旧のグループ 0（指定なし）は `group_id` を NULL にする。削除済みは `deleted_at` で残す

**利用料の集計（5-8）**

- 集計値は数え直さずに写す
- 会員の写しは、**移行先に会員がいれば `user_id` に ULID、いなければ NULL**。旧 ID は必ず `legacy_user_id` に残す
- ロールは基盤と同じ対応表で `user_roles.code` に読み替える

**残る項目**（クーポン・お知らせ・問い合わせ・求人・面談・掲示板）は未実装。実装前に 1-1 を決める。

### 3.3 投入（load）

| 表 | 自然キー |
|---|---|
| `library_folders` / `library_materials` | `(id)` |
| `library_folder_group_targets` | `(folder_id, group_id)` |
| `library_folder_course_targets` | `(folder_id, course_id)` |
| `library_material_lesson_targets` | `(material_id, lesson_id)` |
| `library_material_group_targets` / `library_material_tag_targets` | `(material_id, group_id)` / `(material_id, tag_id)` |
| `admin_notes`（助言メモ） | `(id)`。旧 ID の列が無いので決定論 ULID で重複を防ぐ |
| `scout_follows` | `(tenant_id, follow_id)` |
| `community_categories` | `(tenant_id, community_cate_id)` |
| `tenant_usage_settings` | `(tenant_id)` |
| `tenant_usage_snapshots` | `(tenant_id, batch_date)` |
| `tenant_usage_snapshot_users` | `(tenant_id, batch_date, legacy_user_id)` |

### 3.4 移行の対象外

[review.md の対象外](review.md#移行の対象外移行できないもの--移行しないもの) を参照。
この区分は**受け皿が無いものが多い**。

| 対象 | 実測 | 理由 |
|---|---:|---|
| `portfolio` ほか7件（S04） | 1,837 | **受け皿なし。** この区分で最大 |
| `unit_share`（U12 SNS 共有） | 707 | 受け皿なし |
| `scout` ほか4件（S03） | 109 | 受け皿なし |
| `footprint`（U13 足あと） | 76 | 受け皿なし。純ログ |
| `thread` ほか2件（U10 個別メッセージ） | 20 / 25 / 46 | `community_messages` はチャネル型で 1対1 ではない |
| `message_send` ほか6件（U14 Web Push） | 230 / 1,157 | 受け皿なし。**購読はブラウザの許可に紐づくので移しても使えない** |
| `login_dialog_log`（U04） | 28 | 受け皿なし |
| `mail_send` / `line_send` ほか送信ログ | 2,771 / 31 | 純ログ。cutover 後の送信から記録を始める |
| `skill_unit` ほか20件（S07） | 1 | 21テーブルで合計 973行、実質未使用 |
| `like_user`（ポートフォリオの分） | 6,537 | 受け皿なし。ポートフォリオ（S04）と一緒に決める |
| `user_content_viewed` | 1,383 | 受け皿なし。掲示板・課題のコメントと一緒に決める（**移さないと切り替え後は全部未読に見える**） |
| S9 その他の30表 | — | ログ・一時データ・システムのマスタ・画面の個人設定・成績の集計。理由は [review S9](review.md#s9-その他仕分けていなかった表のうち移さないもの) |

### 3.5 検証

- `verify` が OK になること
- 再実行で 0 行（冪等）
- `out/not-migrated.csv` の件数と理由が 1-1 で決めた内容と矛盾しないこと

---

## 未確定として残っているもの

- **5-2 / 5-3 / 5-4、5-6 の求人・面談・スキルチェック、5-7 の掲示板は Step も migration も無い。** 1-1 が決まってから着手する
- **5-6 のフォロー・5-7 の分類・5-8 の集計は、新のアプリがまだ読まない。** 受け皿に移しただけ（[features.md](features.md) F11〜F13）
- **ディスカッション**（`discussion` ほか5表）と**既読**（`user_content_viewed`）、**掲示板の「いいね」**（`like_user` の22件）。掲示板（`bbs`）と一緒に受け皿を決める
- `calc_param` と模試の集計の表は 06 対象外の X2 に置いた（E63 の回答待ち）
- **就業支援の投入先**（career-backend）。移行ツールの構造に関わるので早めに決める
- **添付ファイル 1,002件**（問い合わせ 706 + お知らせ 296）の受け皿とファイル移送（L9）
