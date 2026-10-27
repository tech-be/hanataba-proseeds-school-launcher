# 課金 — 移行仕様

区分 **4 課金**（チケット / 決済 / 帳票）を移行ツールでどう流すか。共通の方針は
[migration-spec.md](../../migration-spec.md)、突き合わせは [review.md](review.md)、
追加するスキーマは [schema-additions.md](schema-additions.md)。

> **4フェーズとも実装済み。** `billing.1` チケット（6 Step）、`billing.2` 決済（6 Step。5 Step ＋ ライブを予約できる商品の全行
> **2026-10-22 から、`billing.2` で受講（03）のコースの購入・割り当て（2 Step）も流す**（決済の後でないと `payment_id` を結べないため）。
> `billing.live_limit_item_history`）、`billing.3` 帳票（3 Step）、`billing.4` 自動割当（6 Step）。
> **決済・帳票・自動割当のきっかけは暫定の規則で作ってある**（1-3。運営の回答で差し替える）。

> **追加スキーマは school-launcher の4本**: A1〜A8 の `20260928132756_lw2_billing_additions.sql`（`feat/lw2-billing-schema` で作り、`hanataba_dev` に PR #139 でマージ済み）、
> 自動割当の表の `20260927105511`、`tag_auto_assign_rules.assign_id` の `20260930044959`、削除済みの対応・
> 自動割当の列・予約できる商品の全行の `20261001085757`（[schema-additions.md](schema-additions.md) の冒頭）。
> ほかに、自動割当のきっかけのコース（`tag_auto_assign_rule_triggers.learning_path_id`）の `20261023075332`（2026-10-24。
> school-launcher `feat/lw2-auto-assign-learning-path-trigger`。**未マージ**。sync-issues B7）。
> **どれかが当たっていないと `--section billing` はスキーマ確認で止まる**（`migrator/steps/schema.py` の `BILLING_SCHEMA`）。

> **コンテンツ（2）が先。** `ticket_type_lessons` と `live_lesson_ticket_requirements` が
> コンテンツで作るライブの `lessons` を参照する。

---

## 0. 見直し（2026-10-26 決定）

移行の見直しの手順 3（[進捗](../rework-progress.md)）。[テスト仕様書](test-spec.md)のケースが通るように、旧のデータ（ステージング `tenant_id = 10`）と旧のコード（learningware-kiracari `c269a7212`）を確かめて移し方を決める。1 章以降は、決まったあと手順 5 で直す。ステージングの課金のデータは少ない（チケットの残高 8 行、自動割当のルール 9 件）。

### 0-1. 旧のデータで分かったこと

| ケース | 分かったこと |
|---|---|
| チケットの仕組み | 旧のチケットは 3 種類。① **回数チケット**（`user_ticket.ticket_id IS NULL`、期限なし。予約 1 回でライブの商品の `ticket_price` 枚）② **月チケット**（`month_user_ticket`。予約 1 回で 1 枚）③ **専用チケット**（`ticket_id` と `authority_id` あり。予約 1 回で **1 枚**）。**`live_lesson.item_ticket_price` は講座の権限を持つ会員に配る枚数で、1 回の予約で引く枚数ではない**（`admin/controllers/LiveLessonController.php:592, 1078-1100`）。今の移行ツールは要求の枚数（`cost`）にこの値を入れている |
| T-02 | `user_ticket` 8 行・残 17 枚。回数チケット 3 行（残 0・4・1。**旧で今も 2 人が計 5 枚使える**。種別が無いので今は移していない）、専用 5 行。**旧の専用チケットの期限は `ticket_end_date` でなく、結び付く権限（`authority_id`）の期間**（`LiveLessonModel.class.php:4858-4892`）。5 行とも権限の期限が過去（2022-11〜2023-06）で、旧で使える専用チケットは 0 枚。今の移行ツールは `ticket_end_date`（全行 NULL）を期限にするので、**新では 4 行 12 枚が無期限で使えてしまう** |
| T-03 | 開始日・終了日（`ticket_start_date` / `ticket_end_date`）が入っている行は全テナントで 0 件（旧のコードは値を渡していない） |
| T-04 | チケットで払った予約 19 件はすべて過去（2022-11〜12）。**未来の予約は 0 件**。旧は予約したときに残数を引き、キャンセルで戻す（旧の残数は消費後の値）。今の台帳の Step は過去の 2 件に誤った `consumed -3`（1 件は無料の予約）を作り、9 件は戻し先が無い警告を出す |
| T-05 | 種別の使えるレッスンの制限は 2 行、削除済み 0 件 |
| T-07 | `month_user_ticket` は 1 行（2022-11 の期間で期限切れ）。1 行に毎月の上限と**その期間の残り**を持ち、旧の毎日のバッチが次の期間の行を作る（`batch/LiveLessonBatch.class.php:89-135`）。今の期間の残りは 0 件 |
| P-02 | 決済にする申込のうち未入金（`application_result = 0`）が **46 件・1,496,320 円**。カード 39 件（決済の画面に進んで終えなかった申込。2019〜2020）、コンビニ 1 件（入金待ち。1 分後に同額の成功した申込がある）、**振込 6 件・1,404,320 円**（2022-04〜2023-03。旧の未入金の振込の一覧に今も出る）。カードの 5 件には権限が付いている（4 件は期限が 2026-09〜10） |
| P-04 | 成功した決済 295 件。申込日時の月と旧の入金日の月がずれるのは 1 件（振込）。入金日が空のまま成功した振込が 7 件。旧に月別の売上の画面は無い。自動継続の毎月の課金は旧 DB に無い（新の売上は初回の分だけ） |
| P-05 | 1 つの申込が複数の会員に権限を与える例は 0 件。`enrollments.provider_payment_id` は会員をまたいで重ならない |
| P-06 | 申込 322 は `user_id = 0`（既知の不整合 #11）。権限は会員 911 に付いていて、申込と同じ秒に登録されている。決済は会員の外部キーで落ち、**コースの購入（`payment_id` が 322 を指す）も連鎖して落ちる見込み** |
| R-01 | 領収書 21 件は成功した申込 8 件に付き、会員も一致。ただし旧の番号は**(申込, 期間) ごとの再発行の番号**で、自動継続の 2 件の 14 件は期間ごとの領収書。**12 件は金額が決済額を超える**（例: 決済 4,000 円に領収書 48,000 円）。新は 1 回の決済の再発行として 1..n になる |
| R-02 | 領収書の設定は有効、登録番号は `T` ＋ 13 桁 |
| A-01〜A-04 | ルール 9 件（有効 4・削除済み 5）。付与先 13 件はすべて有効。グループの条件は 0 件。購入のきっかけは 1 件で講座の商品（コースになる）。付与先の期間はすべて「期間なし」。**どれも 0 件で問題なし**。旧は運営が会員に属性を足したときにも動いたが、新は会員登録のときだけ |

### 0-2. 決めたこと（2026-10-26。すべて推奨で決定）

| # | ケース | 案 | 推奨 |
|---|---|---|---|
| Q1 | T-02 専用チケットの期限 | (a) 今のまま（`ticket_end_date`。NULL で無期限）<br>(b) 結び付く権限の期間を `expires_at`（終了日の終わり）・`starts_at` に入れる | **(b)**。旧の判定をそのまま写す。ステージングでは 4 行とも期限切れになり、旧の「使える 0 枚」と合う |
| Q2 | T-02 回数チケット（種別なし。3 行・5 枚） | (a) 今のまま一覧に出す<br>(b) 「旧の回数チケット」の種別を 1 つ作って移す | **(b) にする前提で運営に確認**。旧で今も使えるので落とせない。ただ新はレッスンごとに種別が 1 つ（0-7）で、旧で回数と専用の両方を受けていたライブがある。どちらを要求にするかを `open-questions.md` で聞く。決まるまでは (a) |
| Q3 | チケットの必要枚数（`cost`） | (a) 今のまま（`item_ticket_price`。配る枚数）<br>(b) 専用は 1 枚、回数チケットを要求にするならライブの商品の `ticket_price` | **(b)**。今のままだと 1 回の予約に 3 枚かかる |
| Q4 | T-04 消費の台帳 | (a) 今のまま（席を使う予約すべて）<br>(b) **未来の・チケットで払った**予約だけに作る | **(b)**。旧の残数は消費後の値なので、付与は `quantity = remaining` で正しい。台帳はキャンセルで戻すためだけにあり、過去の予約はキャンセルできない。ステージングでは 0 件 |
| Q5 | T-07 毎月の配布 | (a) 今のまま（`monthly_ticket_allowances` だけ）<br>(b) 今の期間の残りを `ticket_grants` にも入れる | **(b)**（ステージングは 0 件）。翌月からの配布は新に処理が無いので、運営の手動付与になることを伝える |
| Q6 | P-02 未入金の申込 46 件 | (a) `pending` のまま<br>(b) `failed` にする（旧の値は `settings` に残る）<br>(c) 移さず一覧に出す | **(b)**。`pending` だと毎時の照合が全テナントの枠を埋め、振込は新の入金確認の一覧に出てボタンで受講権限が付く。**振込 6 件（約 140 万円）にまだ入金を待つものが無いかは運営に確認**。権限の付いた申込も、受講登録・コースの購入はそのまま移る |
| Q7 | P-04 売上の月 | (a) `created_at` は申込日時のまま。ずれる 1 件と入金日の無い 7 件を「分かっている差」として記録<br>(b) `created_at` を旧の入金日にする | **(a)**（日時を作り替えない）。自動継続の毎月の課金が無く、新の売上は初回の分だけになることを運営に伝える |
| Q8 | P-06 申込 322（会員 `0`） | (a) 今のまま（決済とコースの購入が落ちる）<br>(b) 会員のいない申込は、コースの購入の `payment_id` を NULL にして結ばない<br>(c) `fixups` で旧の申込の会員を 911 に直す | **(c)**。権限と登録の時刻から買ったのは 911。直すまでは **(b)** でコースの購入を落とさない |
| Q9 | R-01 期間ごとの領収書 | (a) 今のまま（1 回の決済の再発行として 1..n）<br>(b) 移すが、期間と旧の番号を残し、決済額を超える 12 件を一覧に出す | **(b)**。新で再発行すると決済額の領収書が次の番号で出ることを運営に伝える |
| Q10 | A（自動割当） | 今の規則のまま | 推奨。会員の編集で属性を足しても動かないことを、確認事項 E13 に足す |

### 0-3. 確認用 DB で課金を流す方法（B7）

課金の区分は、自動割当のきっかけのコースの列（`tag_auto_assign_rule_triggers.learning_path_id`。B7 の migration `20261023075332`）が無いと流せない。この migration は、手元の school-launcher の checkout（`feat/lw2-auto-assign-learning-path-trigger`）に未コミットの変更として置かれている。

| 案 | 内容 |
|---|---|
| (a) | B7 の migration のファイルを、作業ブランチ `feat/lw2-migration-rework` に写して当てる（Go の修正は写さない） |
| (b) | 確認用の DB にだけ、B7 の migration の SQL を手で当てる（作業ブランチは変えない） |
| (c) | B7 が `hanataba_dev` に入るのを待つ |

**(a) に決定**（2026-10-26）。推奨は (b) だったが、作業ブランチに B7 の migration のファイルを写す（Go の修正は写さない）。

---


### 0-4. 後から決まったこと

| 日付 | 内容 |
|---|---|
| 2026-10-27 | **移したチケットの種別は、キャンセルで開始まで戻す（`ticket_types.refund_deadline_days = 0`）。** コースのキャンセル・申し込み、ライブのキャンセル・予約を新アプリで確かめたとき、期限内にキャンセルしてもチケットが戻らなかった（NULL は「戻さない」）。旧はキャンセルを受け付けたら回数・月・専用のどのチケットも必ず戻していた（`default/LiveLessonController.php` のキャンセル）。キャンセルできる期限は開催回の設定で別に決まる |

## 1. 前提

### 1-1. 運営への確認事項

**この区分の分も含めて [open-questions.md](../open-questions.md) に1枚でまとめてある。**
同じ話を2か所に置かない。

**課金の項目は D4〜D9**（継続課金の止め方・決済に含めない申込・規約の本文・販売を止めた商品・入金待ちの申込・領収書番号）。1-3 の P の表の「運営への確認」列で、どの P をどの D で聞いているかが分かる。
チケットで決めることは制約に当たる行の扱いなので 1-2 にある。

### 1-2. 制約による不整合

**[constraint-violations.md](../constraint-violations.md) にまとめてある。**
NOT NULL / UNIQUE / CHECK に当たるものと、参照先が物理削除されているものを分けて持つ。

この区分のもの（課金の節）:

| # | 内容 | ステージング | いまの動き |
|---:|---|---:|---|
| 14 | 種別が無いチケット残高（回数チケット） | 3件 | 移さない（理由「受け皿なし」で一覧に出す。**旧で今も 2 人が計 5 枚使える**。種別の決め方は確認事項 D22） |
| 15 | 使い切ったチケット残高（0枚） | 2件 | 移さない。**その残高で予約した9件は台帳に書けず、キャンセルしてもチケットが戻らない**（会員 3181 の種別 2 の残高。`chk_tg_qty` を緩めれば9件とも書ける） |
| 17 | チケットが要るのに種別を引けないライブ | 1件 | **チケット不要のライブとして移る** |
| 旧11 | 会員が物理削除された申込（[旧データの不整合 #11](../constraint-violations.md)） | 11件 | 決済として移らない（`payments.user_id` の外部キー）。明細（`learning_path_purchase_payments`）11件も連鎖する（2026-10-22 から。それまでは `subscription_payments` 10件） |

### 1-3. 決定済み（再確認だけ）

| 決めたこと | 内容 | 決めた日 |
|---|---|---|
| チケットの消費履歴は移さない | キャンセルに要るのは「誰が予約したか」と「何枚使うか」だけ。**台帳の行は予約から組み立てて作る** | 2026-09-24 |
| 欠席も消費済みとして数える | `occupies_seat = 1`。除くと台帳が0行になる | 2026-09-24 |

#### 暫定対応（決定ではない。2026-09-28）

**決済・帳票はこの規則で作ってある。** 運営の回答で差し替える。実装は `migrator/steps/billing/payments.py` /
`receipts.py`、固定しているテストは `tests/test_billing.py`。

| # | 対象 | 暫定の規則 | 理由 | 運営への確認 |
|---|---|---|---|---|
| P1 | 講座の商品（`payment_item.item_type = 0`） | **`tenant_plans` / `plan_courses` には移さない**（2026-10-23 決定）。コース（`learning_paths` / `learning_path_courses`）としてコンテンツの `content.5` で移す | 新の `tenant_plans` は Stripe の継続課金のプランで、旧の商品にあたるのはコース。**2026-10-22 までは**ここに `inactive` で移していた（自動割当のきっかけが `tenant_plans` を指すため）が、新はコースの購入で自動割当を動かさない（B7）ので、残す意味が無い | — |
| P2 | チケット商品・ライブ商品（`item_type` 1/2/3） | 商品は移さない。決済の `settings` に商品の情報を残す | 新の商品は講座の束だけ | 聞かない（新の商品は講座の束だけで、チケット・ライブの商品を置く表が無い。表の制約で決まる） |
| P3 | 無料・無料クーポン・チケット払い（`payment_type` 0/4/5/6/7） | **決済として移さない**。権限は受講（3）、チケットは 4-1 で移っている | 金額0。決済一覧・売上を埋める（本番で86%）。→ 確認事項 D5 | [D5](../open-questions.md#d-cutover-の運用で決めておきたいこと) |
| P4 | 支払い不要（`application_result = 3`） | 決済として移さない | 管理者が「払わなくてよい」とした申込。入金は無い | 聞かない（D5 と一緒に扱える。入金の無い申込を決済にしないのは P3 と同じ理由） |
| P5 | 決済の種類 | **講座の商品（`item_type = 0`）→ `learning_path_purchase`**（コースの購入。買い切りも自動継続も、講座の数によらず。2026-10-22 決定。明細は `learning_path_purchase_payments`）、それ以外の自動継続の商品 → `subscription`、それ以外（チケット・ライブの商品）→ **`lw2_purchase`**（A6） | school-launcher はコース＝旧の販売商品とし、その決済を `learning_path_purchase` で持つ（`20261012014810`）。受講（03）のコースの購入の `payment_id` もこの決済を指す。自動継続だったことは決済の `settings.item.auto_extension` に残す。**2026-10-22 より前は** 講座1つの買い切り → `course_purchase`、自動継続 → `subscription`、それ以外 → `lw2_purchase` だった |
| P6 | 決済の状態 | `application_result` 1 → `succeeded`、**0（入金待ち）・2 → `failed`**（0 は 2026-10-26 に `pending` から変えた。0-2 Q6）。**解約は状態にしない**（`settings` に残す） | 解約は継続課金を止めただけで返金ではない。lw2 に返金の概念は無い | [D8](../open-questions.md#d-cutover-の運用で決めておきたいこと) |
| P7 | 決済代行と決済 ID | カード・コンビニ → `legacy_jpayment`（A5）、振込 → `bank_transfer`。`provider_payment_id` は `lw2-{application_id}` | 一意で決定論的。J-Payment の ID は `settings` | 聞かない（決済 ID の形。利用者に見えない） |
| P8 | 手数料 | `platform_fee = 0` | lw2 に手数料の概念が無い。売上 = `amount - platform_fee` | 聞かない（旧に手数料の概念が無く、他の値にしようがない。売上 = 金額になる） |
| P9 | 継続課金・分割商品 | `learner_subscriptions` / `installment_plans` は作らない。初回の申込だけ決済にする | lw2 に毎月の課金の行が無く、新の必須 ID（Stripe）も無い。**J-Payment の継続課金の止め方は確認事項 D4** | [D4](../open-questions.md#d-cutover-の運用で決めておきたいこと) |
| P10 | 受講との結びつき | `enrollments.provider_payment_id` に、畳んだ権限のうち**決済として移す最も新しい申込**の決済 ID | 返金で受講を取り消す処理と、修了証の金額印字がこの値で決済を引く | 聞かない（新システムの返金・修了証の処理のための結びつけ。利用者に見えない） |
| P11 | 領収書 | `receipt_log` → `receipts`。決済ごとに `issue_no` 1..n（旧の番号は `receipt_log_id`）。旧の期間（`payment_date_from` / `to`）と番号（`seq_no`）は `receipts.settings`（0-2 Q9）。取引日は入金日（lw2 の `real_payment_date`） | lw2 はダウンロードのたびに1行 | [D9](../open-questions.md#d-cutover-の運用で決めておきたいこと) |
| P12 | 規約の本文 | `tenant_legal_documents`（A8）。**本文が空で、外部 URL の上書きも無いものは移さない**（本文が空でも URL の上書きがあれば、本文 NULL・`external_url` ありで移す）。URL・表題の上書き（`payment_infomation` の `*_chk = 1` のもの）も同じ表 | 受け皿を追加して受ける。**アプリはまだ読まない**（→ D6） | [D6](../open-questions.md#d-cutover-の運用で決めておきたいこと) |
| P13 | 決済の設定（`payment_infomation`） | `tenants.settings.lw2_payment` | 既存の JSON 列で受けられる | 聞かない（設定の写し。新の決済処理は読まない） |
| P14 | 消費税の一覧（`tax`） | 移さない | 設定画面の選択肢で、取引の税計算に使っていない | 聞かない（取引の税計算に使っていない一覧） |
| P15 | 自動割当の発動のきっかけ | 旧 `assign` → `tag_auto_assign_rules`。商品のきっかけ（`assign_payment_item`）があるルールは `purchase`、無いルールは `registration`。削除済みのルールは `active = FALSE` で残す。講座の商品のきっかけはコース（`learning_path_id`）を指す（2026-10-24。B7） | 旧は会員の登録・購入・編集のたびに動いた。新は「購入」か「会員登録」のどちらか一方で発動する。新はコースの購入（有料・後から入金・0 円）でも動く | [E13](../open-questions.md#e-切り替え後の機能で決めておきたいこと) |

### 1-4. 本番ダンプ受領後に確認すること

- **チケット種別の使い分け。** 実測は2件だけで**両方とも同じ名前**、区別が読み取れない
- **`payment_item.item_type` の `0` 以外が何か。** 受講可否判定が `= 0` で絞っている
- **`payment_application` の決済手段の判定条件。** 5種類が1表に同居しており、
  **列名から推測せず `PaymentModel` を読んで確定する**（受講の `cancel_chk` と同じ誤りを繰り返さない）
- **流入元計測**（`trigger_media` / `payment_trigger_media`）は実測0件。本番で出たら扱いを決める

### 1-5. ステージングダンプでの実測（2026-09-18 取得）

| 旧テーブル | 全テナント | ReCADemy | 備考 |
|---|---:|---:|---|
| `ticket` | 41 | **2** | 両方とも同じ名前 |
| `user_ticket` | 3,231 | **8** | 種別なし3 / 残0が2 |
| `user_ticket_log` | 986 | — | 移さない |
| `month_user_ticket` | 54 | **1** | |
| `payment_item` | 336 | **301** | 講座の商品 280 → コース（`learning_paths`。02 の `content.5`）。課金では移さない（P1） |
| `payment_item_lesson` | 1,134 | — | `tenant_id` なし |
| `payment_application` | 634 | **479** | 決済にするのは 365（カード 330 / コンビニ 2 / 振込 33）。無料・チケット払い 112 と支払い不要 2 は移さない。会員が物理削除された 11 は外部キーで移らず、**投入 354** |
| `receipt_log` | 21 | **21** | 8決済に付く（再発行を含む。最大10回） |
| `tax` | 1 | — | 全体設定 |
| `agreement` / `cancel_policy` / `privacy_policy` / `tokusyo` | 4 / 2 / 2 / 2 | **2 / 1 / 1 / 1** | |

---

## 2. データ登録順

```
[前提]       区分1 基盤（users）
             区分2 コンテンツ（lessons — ライブぶん）
             区分3 受講（live_reservations — enrollment.6）
                ↓
[migration]  20260928132756（A1〜A8）/ 20260927105511 / 20260930044959 / 20261001085757
                ↓
billing.1    ticket_types → ticket_type_lessons → live_lesson_ticket_requirements
             → ticket_grants → ticket_ledger_entries → monthly_ticket_allowances
                ↓
billing.2    payments（2026-10-23 から tenant_plans / plan_courses は作らない）
             → learning_path_purchase_payments（コースの購入の明細。2026-10-22 から）/ subscription_payments
             → live_lesson_limit_item_history（旧の形のまま。plan_id は NULL）
             → learning_path_enrollments → learning_path_enrollment_courses
               （コースの購入・割り当て。**受講 03 のデータ**だが payment_id が決済を指すのでここ。2026-10-22。
                仕様は [受講の移行仕様](../03-enrollment/migration-spec.md)）
billing.3    receipt_settings → receipts（決済に紐づくので後）→ tenant_legal_documents
billing.4    tag_auto_assign_rules → tag_auto_assign_rule_triggers → tag_auto_assign_rule_conditions
             → tag_auto_assign_rule_group_conditions → tag_auto_assign_rule_grants → tag_auto_assign_logs
             （旧の商品にまつわる記録と並べて課金の最後。商品のきっかけの plan_id は NULL）
```

> **台帳（`ticket_ledger_entries`）は受講（3）のライブ予約を参照する。** 予約が先。
> 実装上は `billing.1` の中で予約から組み立てるため、**`enrollment.6` より後に流す**。

### 2-2. 実行手順

```bash
# 0. 追加スキーマを当てる（school-launcher 側。20260928132756 / 20260927105511 / 20260930044959 / 20261001085757）

# 1. 前提の区分を入れる（台帳が予約を参照するので受講まで）
.venv/bin/python -m migrator run --section foundation --section content --section enrollment

# 2. 課金を流す
.venv/bin/python -m migrator run --dry-run --section billing --skip-preflight
.venv/bin/python -m migrator run --section billing --skip-preflight
.venv/bin/python -m migrator verify --section billing
```

---

## 3. データ移行仕様

### 3.1 抽出（extract）

| 旧テーブル | 絞り込みの経路 |
|---|---|
| `ticket` | `tenant_id` を持つ |
| `user_ticket` / `month_user_ticket` | **`tenant_id` を持たない。** 親の `user` → `tenant_id`（`fetch_joined`） |
| `ticket_limit_lesson` | `ticket` → `tenant_id` |
| `payment_item_lesson` | `payment_item.tenant_id` |
| `payment_application_item` | `payment_application.tenant_id` |
| `tax` | **`tenant_id` を持たない全体設定** |

### 3.2 変換（transform）

**チケット（4-1）**

- `ticket_types.legacy_ticket_type` は旧 `ticket.ticket_type`。**`user_ticket_log` が参照するのはこの値**
  （`ticket_id` ではない）。履歴を移さなくても後から突き合わせられるように残す
- `ticket_types.deprecated_at`（`del_chk = 1` のとき）は旧の `regist_date`（旧に削除日時が無い）。
  `ticket_type_lessons.deleted_at` は旧の `update_date`。**削除済みの `ticket_limit_lesson` も移す**（同じ組が積まれていれば生きている行を優先して1行）
- **必要枚数の種別は `ticket_limit_lesson` から逆引きする。** 旧はライブ側に種別を持たない。
  **逆引きは生きている行（`del_chk = 0`）だけを見る。**
  **引けないライブは行を作らず、チケット不要として移る**（警告ログを出す。#17）
- **1つのライブに種別が2つ以上つながっている場合は、読んだ順の最初の1つを黙って使う**（`setdefault`。警告は出さない。
  `live_lesson_ticket_requirements` の PK が `lesson_id` 単独なので1種別しか持てない）。ステージングは該当なし
- **残高1行 = 付与1行。** 旧 `user_ticket.ticket_num` は引かれたあとの残高なので、
  `quantity` と `remaining_quantity` に同じ値を入れ、`note` に「lw2 移行時点の残高」と書く。
  `source` は `manual`。**専用チケットの期限（`expires_at`）・利用開始（`starts_at`）は結び付く権限
  （`authority_id`）の期間**（終了日の終わり・開始日の始まり。JST。0-2 Q1）。権限が引けなければ残高の行の日付
- **種別の無い回数チケット（`ticket_id` が NULL）は移さない**（理由「受け皿なし」で一覧に出す。確認事項 D22。0-2 Q2）。
  月チケットの今の期間の残りも同じ（`billing.monthly_remaining`。0-2 Q5）
- **予約 1 回で引くのは専用チケット 1 枚**（`live_lesson_ticket_requirements.cost = 1`。0-2 Q3）。
  `live_lesson.item_ticket_price` は権限を持つ会員に配る枚数で、新に入れる先が無い（移さない）
- **台帳は、開催が未来でチケットで払った予約にだけ作る**（`payment_application.live_lesson_reserve_id` の
  `payment_type` 5 回数・6 月・7 専用。0-2 Q4）。専用チケットの予約 1 件につき `consumed` を 1 行（`quantity_delta = -1`）。
  過去の予約はキャンセルできないので作らない。回数・月チケットの予約は戻し先の付与が無い（D22）ので警告に数える。
  **`remaining_quantity` は減らさない** — 旧の残高が既に引かれたあとの値なので、引くと二重に減る
- **戻し先の付与は (会員, 種別) で引き、同じ組に付与が2行以上あれば読んだ順の最初の1行に付ける。**
  種別が無い残高と0枚の残高は戻し先にしない
- **戻し先の付与が移らない予約は台帳行を作れない**（警告に件数を出す。ステージングは未来の予約が 0 件なので 0 件。
  2026-10-26 より前は過去の予約にも作っていて、9 件が #15 の使い切った残高のために書けなかった）
- `monthly_ticket_allowances.deleted_at`（`del_chk = 1` のとき）も旧の `regist_date`
- **月次配布**（`month_user_ticket`）は `monthly_ticket_allowances` に移す。`target_month` は書式を変えない。
  旧の `application_id` は同じ名前の列 `monthly_ticket_allowances.application_id` に旧の値のまま置く（`payments.application_id` と同じ値）

**決済（4-2）**（1-3 の P1〜P10）

- **商品は課金では移さない**（P1。2026-10-23 から）。講座の商品はコースとしてコンテンツで移す。**`price` / `first_price` は税込**
  （コメントの「税抜」は誤り）。決済の `settings.item` に商品の情報（名前・講座・自動継続か）を残す
- 削除済みの商品も、コース（`learning_paths.status = 'deleted'`）として移っている（02）
- 商品と講座の対応はコースの講座（`learning_path_courses`）に移す。削除済みの対応は移行対象外（02。新もコースから外した講座の結び付きは持たない）
  **講座が移行の対象に無い組は移さない**（`out/not-migrated.csv` に「旧データの不整合」で出る）
- **P5 は商品の種類だけで決める**（2026-10-22 から。講座の数は見ない）
- 申込（`payment_application`）は**申込フォームの個人情報と `password` を読まない**。会員は `users` に移っている
- 種類・状態・決済代行は P5〜P7。解約・分割回数（**`split_payment_number = 1` は一括**）・クーポン・
  税の情報（**`payment_application.tax` は常に0で使わない**）・J-Payment の ID は `settings`
- 入金日は lw2 の `real_payment_date` と同じ規則（カードは課金を後ろ倒しにした日、コンビニ・振込はそれぞれの入金日）

**帳票（4-3）**（P11〜P14）

- 領収書の設定は `receipt_settings`。インボイスの有無（`invoice_chk`）は `tenants.settings.lw2_payment`
- 発行済みの領収書は、発行者の情報も**発行時点の写し**のまま移す

### 3.3 投入（load）

| 表 | 自然キー |
|---|---|
| `ticket_types` | `(tenant_id, ticket_id)` |
| `ticket_type_lessons` | `(ticket_type_id, lesson_id)` |
| `live_lesson_ticket_requirements` | `(lesson_id)` |
| `ticket_grants` | `(id)`（旧 UNIQUE の `(user_id, ticket_id, authority_id)` から決定論 ULID） |
| `ticket_ledger_entries` | `(id)`（予約 ID から決定論 ULID） |
| `monthly_ticket_allowances` | `(tenant_id, month_user_ticket_id)` |
| `payments` / `receipts` | `(tenant_id, application_id)` / `(tenant_id, receipt_log_id)` |
| `learning_path_purchase_payments` / `subscription_payments` | `(payment_id)` |
| `receipt_settings` | `(tenant_id)` |
| `tenant_legal_documents` | `(tenant_id, kind, language_code)` |
| `live_lesson_limit_item_history` | `(id)`（旧に主キーが無い。`(live_lesson_id, item_id, regist_date, 同じ組の通し番号)` から決定論 ULID） |
| `tag_auto_assign_rules` | `(tenant_id, assign_id)` |
| `tag_auto_assign_rule_triggers` | `(id)`（`(assign_id, item_type, item_id)` から決定論 ULID） |
| `tag_auto_assign_rule_conditions` / `tag_auto_assign_rule_group_conditions` | `(rule_id, tag_id)` / `(rule_id, group_id)` |
| `tag_auto_assign_rule_grants` | `(rule_id, grant_kind, target_id)` |
| `tag_auto_assign_logs` | `(id)`（`assign_log_id` から決定論 ULID） |

### 3.4 移行の対象外

[review.md の対象外](review.md#移行の対象外移行できないもの--移行しないもの) を参照。

| 対象 | 行数 | 理由 |
|---|---:|---|
| `user_ticket_log` | 986 | 消費履歴。台帳は予約から組み立てる（運営の判断） |
| `analytics_tag` / `trigger_media` / `payment_trigger_media` | 12 / 7 / 7 | 流入元計測。PDF・再判定とも X |
| 継続課金のカード情報 | — | **lw2 の DB に無い**（プロバイダ側） |
| 無料・チケット払い・支払い不要の申込 | 114 | 決済にしない（P3 / P4） |
| 継続課金・分割の毎月の課金 | — | **lw2 に行が無い**（J-Payment が持つ） |
| 消費税の一覧（`tax`） | 1 | P14 |
| 商品の分類（`payment_item_cate` / `payment_item_item_cate`） | 3 / 7 | 現状は移していない（実装が無い。2026-10-02 の確認） |
| 申込と受講の古い対応表（`payment_application_set_user_learning_lesson`） | 27 | 現状は移していない（実装が無い。2026-10-02 の確認） |
| チケット商品・ライブ商品（`payment_item.item_type` 1 / 2 / 3） | 21（2 / 1 / 18） | 商品としては移さない（P2。講座の商品と同じく、2026-10-23 から商品は課金で移さない）。決済の `settings` に商品の情報を残す |
| 講座が移行の対象に無い商品と講座の組（`payment_item_lesson`） | 1 | 講座が物理削除されている（`item_id = 1293`、`lesson_id = 2100034443`、削除済みの対応）。コースの講座（02 の `content.learning_path_courses`）に移さず `out/not-migrated.csv` に出る（2026-10-23 から課金の `plan_courses` には出ない） |

### 3.5 検証

- `verify --section billing` が OK になること。**2段で見る。**
  - 照合: 移行元から作り直した行と全列で突き合わせる（移行先 = 変換結果）
  - **旧 DB との突き合わせ**（`migrator/validation/legacy_checks.py` の `billing_checks`）: 旧 DB から独立に出した件数・金額・日付・本文と比べる。支払い方法 × 状態の組ごとの件数・金額（組の数はデータで変わる）に、状態・会員ごとの金額・総額・種類・領収書・商品・商品と講座の組・受講との結びつき・規約の本文・チケットの残枚数と台帳・自動割当の項目（講座の商品のきっかけが、移したコースを指すか。2026-10-24）、予約できる商品の全行（`live_lesson_limit_item` → `live_lesson_limit_item_history` の件数。削除済みを含む）を足したもの。変換の規則そのものの誤りはここで出る
- 再実行で 0 行（冪等）
- `out/not-migrated.csv` の件数と理由が、1-2 の #14 / #15 と矛盾しないこと
- 台帳を作れなかった予約の件数（警告ログ）が、未来のチケットの予約のうち戻し先の無いものと合うこと（ステージングは 0 件）

---

## 未確定として残っているもの

- **1-3 の暫定対応 P1〜P15。** 運営の回答（確認事項 D4〜D9 / E13）で差し替える
- チケットの #14 / #15 / #17、会員が物理削除された申込（旧データの不整合 #11）（→ [制約に当たって移らない行](../constraint-violations.md)）
- `certificates.product_id`（受講 A6）は未解決。**決済は移ったが、修了証が商品を指す規則は未実装**
- `monthly_ticket_allowances.application_id` を決済に結ぶのも未実装（旧 ID のまま。`payments.application_id` で引ける）
