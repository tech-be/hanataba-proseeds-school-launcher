# 課金 — 移行仕様

区分 **4 課金**（チケット / 決済 / 帳票）を移行ツールでどう流すか。共通の方針は
[migration-spec.md](../../migration-spec.md)、突き合わせは [review.md](review.md)、
追加するスキーマは [schema-additions.md](schema-additions.md)。

> **3フェーズとも実装済み**（2026-09-28）。`billing.1` チケット（6 Step）、`billing.2` 決済（5 Step）、
> `billing.3` 帳票（3 Step）。**決済・帳票は暫定の規則で作ってある**（1-3。運営の回答で差し替える）。

> **追加スキーマ（A1〜A8）は school-launcher の `20260928132756_lw2_billing_additions.sql`**
> （ブランチ `feat/lw2-billing-schema`）。当たっていないと `--section billing` はスキーマ確認で止まる。

> **コンテンツ（2）が先。** `ticket_type_lessons` と `live_lesson_ticket_requirements` が
> コンテンツで作るライブの `lessons` を参照する。

---

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
| 14 | 種別が無いチケット残高 | 3件 | 移さない。**その残高で予約した9件は台帳に書けず、キャンセルしてもチケットが戻らない** |
| 15 | 使い切ったチケット残高（0枚） | 2件 | 移さない（この残高で予約したものは無い） |
| 17 | チケットが要るのに種別を引けないライブ | 1件 | **チケット不要のライブとして移る** |
| 旧11 | 会員が物理削除された申込（[旧データの不整合 #11](../constraint-violations.md)） | 11件 | 決済として移らない（`payments.user_id` の外部キー）。明細（`subscription_payments`）10件も連鎖する |

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
| P1 | 講座の商品（`payment_item.item_type = 0`） | `tenant_plans` に移す。買い切りは `one_time`、自動継続は `month`。**すべて `inactive`**。`provider_price_id` は `lw2-item-{item_id}`。講座は `plan_courses` | 新で売るには Stripe の価格を作り直す。`active` にすると購入ボタンが出て決済が失敗する | [D7](../open-questions.md#d-cutover-の運用で決めておきたいこと) |
| P2 | チケット商品・ライブ商品（`item_type` 1/2/3） | 商品は移さない。決済の `settings` に商品の情報を残す | 新の商品は講座の束だけ | 聞かない（新の商品は講座の束だけで、チケット・ライブの商品を置く表が無い。表の制約で決まる） |
| P3 | 無料・無料クーポン・チケット払い（`payment_type` 0/4/5/6/7） | **決済として移さない**。権限は受講（3）、チケットは 4-1 で移っている | 金額0。決済一覧・売上を埋める（本番で86%）。→ 確認事項 D5 | [D5](../open-questions.md#d-cutover-の運用で決めておきたいこと) |
| P4 | 支払い不要（`application_result = 3`） | 決済として移さない | 管理者が「払わなくてよい」とした申込。入金は無い | 聞かない（D5 と一緒に扱える。入金の無い申込を決済にしないのは P3 と同じ理由） |
| P5 | 決済の種類 | 自動継続の商品 → `subscription`、講座1つの買い切り → `course_purchase`、それ以外（講座2つ以上・講座なし・チケット商品）→ **`lw2_purchase`**（A6） | 講座が1つに決まらない購入を `course_purchase` に入れると講座を選ぶことになる | 聞かない（新の表の制約で決まる。利用者に見える違いは一覧で講座が空欄になるだけ） |
| P6 | 決済の状態 | `application_result` 1 → `succeeded`、0 → `pending`、2 → `failed`。**解約は状態にしない**（`settings` に残す） | 解約は継続課金を止めただけで返金ではない。lw2 に返金の概念は無い | [D8](../open-questions.md#d-cutover-の運用で決めておきたいこと) |
| P7 | 決済代行と決済 ID | カード・コンビニ → `legacy_jpayment`（A5）、振込 → `bank_transfer`。`provider_payment_id` は `lw2-{application_id}` | 一意で決定論的。J-Payment の ID は `settings` | 聞かない（決済 ID の形。利用者に見えない） |
| P8 | 手数料 | `platform_fee = 0` | lw2 に手数料の概念が無い。売上 = `amount - platform_fee` | 聞かない（旧に手数料の概念が無く、他の値にしようがない。売上 = 金額になる） |
| P9 | 継続課金・分割商品 | `learner_subscriptions` / `installment_plans` は作らない。初回の申込だけ決済にする | lw2 に毎月の課金の行が無く、新の必須 ID（Stripe）も無い。**J-Payment の継続課金の止め方は確認事項 D4** | [D4](../open-questions.md#d-cutover-の運用で決めておきたいこと) |
| P10 | 受講との結びつき | `enrollments.provider_payment_id` に、畳んだ権限のうち**決済として移す最も新しい申込**の決済 ID | 返金で受講を取り消す処理と、修了証の金額印字がこの値で決済を引く | 聞かない（新システムの返金・修了証の処理のための結びつけ。利用者に見えない） |
| P11 | 領収書 | `receipt_log` → `receipts`。決済ごとに `issue_no` 1..n（旧の番号は `receipt_log_id`）。取引日は入金日（lw2 の `real_payment_date`） | lw2 はダウンロードのたびに1行 | [D9](../open-questions.md#d-cutover-の運用で決めておきたいこと) |
| P12 | 規約の本文 | `tenant_legal_documents`（A8）。空の本文は移さない。URL・表題の上書きも同じ表 | 受け皿を追加して受ける。**アプリはまだ読まない**（→ D6） | [D6](../open-questions.md#d-cutover-の運用で決めておきたいこと) |
| P13 | 決済の設定（`payment_infomation`） | `tenants.settings.lw2_payment` | 既存の JSON 列で受けられる | 聞かない（設定の写し。新の決済処理は読まない） |
| P14 | 消費税の一覧（`tax`） | 移さない | 設定画面の選択肢で、取引の税計算に使っていない | 聞かない（取引の税計算に使っていない一覧） |

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
| `payment_item` | 336 | **301** | 講座の商品 280 → `tenant_plans` |
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
                ↓
[migration]  A1 ticket_types.ticket_id / legacy_ticket_type、ticket_grants.starts_at
             A2 monthly_ticket_allowances
                ↓
billing.1    ticket_types → ticket_type_lessons → live_lesson_ticket_requirements
             → ticket_grants → ticket_ledger_entries → monthly_ticket_allowances
                ↓
billing.2    tenant_plans → plan_courses → payments
             → course_purchase_payments / subscription_payments
billing.3    receipt_settings → receipts（決済に紐づくので後）→ tenant_legal_documents
```

> **台帳（`ticket_ledger_entries`）は受講（3）のライブ予約を参照する。** 予約が先。
> 実装上は `billing.1` の中で予約から組み立てるため、**`enrollment.6` より後に流す**。

### 2-2. 実行手順

```bash
# 0. 追加スキーマを当てる（school-launcher 側。20260928132756_lw2_billing_additions.sql）

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
| `ticket` / `user_ticket` | `tenant_id` を持つ |
| `ticket_limit_lesson` | `ticket` → `tenant_id` |
| `payment_item_lesson` | `payment_item.tenant_id` |
| `payment_application_item` | `payment_application.tenant_id` |
| `tax` | **`tenant_id` を持たない全体設定** |

### 3.2 変換（transform）

**チケット（4-1）**

- `ticket_types.legacy_ticket_type` は旧 `ticket.ticket_type`。**`user_ticket_log` が参照するのはこの値**
  （`ticket_id` ではない）。履歴を移さなくても後から突き合わせられるように残す
- **必要枚数の種別は `ticket_limit_lesson` から逆引きする。** 旧はライブ側に種別を持たない。
  **引けないライブは行を作らず、チケット不要として移る**（警告ログを出す。#17）
- **残高1行 = 付与1行。** 旧 `user_ticket.ticket_num` は引かれたあとの残高なので、
  `quantity` と `remaining_quantity` に同じ値を入れ、`note` に「lw2 移行時点の残高」と書く。
  `source` は `manual`。`expires_at` は終了日なので日の終わり（23:59:59）を補う
- **台帳は予約から組み立てる。** 旧に消費履歴が無いため、`live_reservations` の
  席を占有する予約（`reserved` / `attended` / `no_show`）1 件につき `consumed` を 1 行作る
  （`quantity_delta` は必要枚数の負）。**欠席（`no_show`）も占有する**。
  **`remaining_quantity` は減らさない** — 旧の残高が既に引かれたあとの値なので、引くと二重に減る
- **戻し先の付与が移らない予約は台帳行を作れない**（ステージングで9件。すべて #14 の種別が無い残高で予約したもの）。
  その予約はキャンセルしてもチケットが戻らない
- **月次配布**（`month_user_ticket`）は `monthly_ticket_allowances` に移す。`target_month` は書式を変えない。
  旧の `application_id` は同じ名前の列 `monthly_ticket_allowances.application_id` に旧の値のまま置く（`payments.application_id` と同じ値）

**決済（4-2）**（1-3 の P1〜P10）

- 商品は講座の商品（`item_type = 0`）だけ `tenant_plans` に移す。**`price` / `first_price` は税込**
  （コメントの「税抜」は誤り）。新の列に無い設定（試用・受講期間・自動解約・支払日など）は `settings`
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
| `tenant_plans` / `payments` / `receipts` | `(tenant_id, item_id)` / `(tenant_id, application_id)` / `(tenant_id, receipt_log_id)` |
| `plan_courses` | `(tenant_id, plan_id, course_id)` |
| `course_purchase_payments` / `subscription_payments` | `(payment_id)` |
| `receipt_settings` | `(tenant_id)` |
| `tenant_legal_documents` | `(tenant_id, kind, language_code)` |

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

### 3.5 検証

- `verify --section billing` が OK になること。**2段で見る。**
  - 照合: 移行元から作り直した行と全列で突き合わせる（移行先 = 変換結果）
  - **旧 DB との突き合わせ**（34 項目）: 旧 DB から独立に出した件数・金額・日付・本文と比べる（`migrator/validation/legacy_checks.py`）。変換の規則そのものの誤りはここで出る
- 再実行で 0 行（冪等）
- `out/not-migrated.csv` の件数と理由が、1-2 の #14 / #15 と矛盾しないこと
- 台帳を作れなかった予約の件数（警告ログ）が、#14 / #15 の残高で予約した件数と合うこと（ステージングは #14 で9件）

---

## 未確定として残っているもの

- **1-3 の暫定対応 P1〜P14。** 運営の回答（確認事項 D4〜D9）で差し替える
- チケットの #14 / #15 / #17、会員が物理削除された申込（旧データの不整合 #11）（→ [制約に当たって移らない行](../constraint-violations.md)）
- `certificates.product_id`（受講 A6）は未解決。**決済は移ったが、修了証が商品を指す規則は未実装**
- `monthly_ticket_allowances.application_id` を決済に結ぶのも未実装（旧 ID のまま。`payments.application_id` で引ける）
