# 課金 — 新システムの機能仕様（移したデータの見え方）

移行の見直しの手順 1（[進捗](../rework-progress.md)）。**新システムが課金のデータ（チケット・ライブの予約・決済・領収書・規約・自動割当）をどう読み書きするか**を、移したデータがどう見えるかの観点で書き出したもの。手順 2 のテスト仕様書と手順 3 の移行仕様の材料にする。

- **基準**: school-launcher `hanataba_dev` の `584026af`（2026-10-24）＋ 作業ブランチの変更。コードを読んで調べた（動かしてはいない）。自動割当のきっかけをコースに結ぶ変更（B7。`20261023075332` と Go の修正）は `584026af` に無く、別ブランチ `feat/lw2-auto-assign-learning-path-trigger` にある。その分は **【B7】** と書く。
- **コードの場所**は school-launcher の `btoc-backend/` からの相対パス。
- **時刻はすべて UTC で読む**（接続で `time_zone='+00:00'`）。

## 0. 移し方に効く点（先に）

### チケット・予約

| # | 内容 | 場所 |
|---|---|---|
| 0-1 | **使える枚数は `ticket_grants.remaining_quantity` の合計だけで決まる**（`remaining_quantity > 0` かつ期限内）。台帳（`ticket_ledger_entries`）は合計に使わない。付与の台帳行が無くても残高・予約・画面は動く。台帳を見せる画面・API は無い | `internal/ticket/domain/ticket.go:201-208, 334-343`、`internal/ticket/repository/grant_repo.go:57-73` |
| 0-2 | **CHECK で `quantity >= 1`、`0 <= remaining_quantity <= quantity`。** 付与 0・残 0 の旧の行はそのままでは入らない | `MIG/20260909001459_live_tickets.sql:176-178` |
| 0-3 | **キャンセルでチケットを戻すのは、その予約の台帳行（`consumed`、負の値）からだけ。** 台帳行の無い予約はキャンセルできるがチケットは戻らない。戻すとき `remaining + n <= quantity` でないとエラーになり、**キャンセルごと取り消される**。台帳行を付けるなら、付与の `quantity` に消費分を含める | `internal/ticket/service/ticket_service.go:143-200`、`ticket.go:233-236` |
| 0-4 | 戻すかは、キャンセル時点のレッスンのチケットの要求（`live_lesson_ticket_requirements`）と種別の `refund_deadline_days`（NULL は戻さない、0 は開始まで戻す）で決まる。**移した種別は 0（開始まで戻す）で入れる**（旧はキャンセルを受け付けたら必ず戻していた。移行仕様 0-4）。要求の無いレッスンは台帳があっても戻さない | `internal/live/service/reservation_service.go:317-330`、`ticket.go:136-152` |
| 0-5 | **`ticket_grants.starts_at`（利用開始日）は読まない。** 開始前の付与もすぐ使える | `grant_repo.go:21, 31-36` |
| 0-6 | **`ticket_type_lessons.deleted_at` は読まない。** 削除済みの行も「この種別はこのレッスンだけ」の制限として効く。運営が種別を保存し直すと、削除済みの行も生きた行として作り直される | `ticket_type_repo.go:76-143` |
| 0-7 | チケットの要求は 1 レッスン 1 種別（主キーが `lesson_id`） | `MIG/20260909001459:212-226` |
| 0-8 | **毎月の配布のバッチは無い。** `monthly_ticket_allowances` は読み書きされない。切り替えで二重に配られることは無いが、翌月からの配布も自動では行われない（運営の手動付与） | `MIG/20260928132756:33`、`cmd/worker/main.go` |
| 0-9 | チケットの期限切れのバッチは 1 日 1 回・最大 500 件。期限切れで残のある付与は、片付くまで画面に「期限切れ」で出る（使える枚数からは外れる） | `cmd/worker/main.go:1157-1172`、`grant_repo.go:87-101` |
| 0-10 | **リマインドの対象は `status = 'reserved'`・`reminded_at IS NULL`・開始が今から 24 時間以内**（毎時）。旧で送った予約は `reminded_at` を入れないと再送される | `internal/live/repository/reservation_repo.go:136-154`、`internal/live/domain/live.go:352-357` |
| 0-11 | **予約の状態 `host_canceled` を Go・画面が知らない**（ラベルが空、キャンセルは 404、予約し直すと 500、出欠を付けられる）。残席は lookup の `occupies_seat` で数えるので正しい | `live.go:25-30, 290-346`、`btoc-frontend/src/types/live-reservation.ts:10` |
| 0-12 | (開催回, 会員) は UNIQUE。キャンセル済みの行は予約し直すときに使い回される | `MIG/20260908105014:116`、`reservation_service.go:187-203` |
| 0-13 | 付与元（`source`）は外部キーで `course_purchase` / `manual` / `standalone_purchase`。Go は読むときに値を確かめず、画面は知らない値をそのまま出す | `MIG/20260909001459:55-59`、`btoc-frontend/src/components/ticket/ticket-balance-card.tsx:89` |
| 0-14 | 講座の購入でのチケットの付与は購入のイベントでだけ起きる。移した購入からは配られないので、旧の残りは `ticket_grants` に入れる | `internal/server/wire_events_domain.go:178-193` |

### 決済・領収書

| # | 内容 | 場所 |
|---|---|---|
| 0-15 | **返金のボタンは `succeeded` の決済すべてに出て、決済代行を見ずに Stripe を呼ぶ。** 移した決済は Stripe がエラーを返して 500 になり、データは変わらない（返金できない）。ボタンが出ること自体は避けられない | `btoc-frontend/src/app/(tenant)/admin/payments/page.tsx:128-137`、`internal/service/payment_service.go:790-816` |
| 0-16 | **毎時の照合のバッチが、`pending` で作成から 4 日を過ぎた決済を、決済代行もテナントも問わず古い順に 100 件まで Stripe に問い合わせる。** 移した `pending` が 100 件を超えると、新しい未決済が照合されなくなる | `internal/commerce/repository/payment_repo.go:161-172`、`payment_service.go:1043-1104` |
| 0-17 | 決済 ID（`provider_payment_id`）での検索はテナントも決済代行も見ない（Stripe の webhook・ロボペイの結果通知）。新の値（`pi_…`・ULID）とぶつからない接頭辞付きにする。ロボペイの ID をそのまま `pending` で入れると、通知で成立して受講登録ができうる | `payment_repo.go:103-108`、`internal/service/robotpayment_kickback_service.go:213-229, 275-296` |
| 0-18 | 決済代行の値: Go は `stripe` / `bank_transfer` / `robotpayment` だけを知る。`bank_transfer` にすると振込の入金確認の一覧に出て、確認ボタンで受講権限が出る | `internal/commerce/domain/payment.go:35-47`、`bank_transfer_order_repo.go:50-66` |
| 0-19 | **売上は `status = 'succeeded'` の `SUM(amount - platform_fee)` を `created_at` の月・日で集める。** 移行した日時を入れると全額が移行日の売上になる。講座別の売上は `course_purchase` の決済だけ | `internal/repository/revenue_analytics_repo.go:34-77`、`dashboard_repo.go:123-230` |
| 0-20 | **返金で受講を取り消すとき、`enrollments.provider_payment_id` が同じ受講登録をすべて（会員を問わず）`refunded` にする。** 同じ値を複数の会員に入れると、1 件の返金で全員が落ちる。コースは `learning_path_enrollments.payment_id` で引く | `payment_service.go:543-619, 745-781` |
| 0-21 | 修了証の金額は、`provider_payment_id` が同じ受講登録が 1 件だけのときに決済から引く | `internal/certificate/repository/certificate_facts_repo.go:43-55` |
| 0-22 | **領収書を出せるのは `succeeded` の課金の決済だけ。** 取引日は `payments.created_at`（JST の日付）。番号は決済ごとの `MAX(issue_no) + 1`（`UNIQUE (payment_id, issue_no)`）。**PDF に印字する番号は `"No. " + receipts.id`（ULID）で、旧の番号（`receipt_log_id`）は出ない** | `internal/receipt/service/receipt_service.go:126-173, 240-245`、`receipt_repo.go:82-101`、`internal/server/receipt_pdf.go:66, 86` |
| 0-23 | 領収書の持ち主は `receipts.user_id`。決済の会員と同じにする | `receipt_service.go:62, 182` |
| 0-24 | `receipt_settings.enabled = FALSE` か行が無いと発行できない | `internal/receipt/repository/settings_repo.go:20-56` |
| 0-25 | **規約の本文（`tenant_legal_documents`）は読まれない**（受け皿だけ） | — |

### 自動割当

| # | 内容 | 場所 |
|---|---|---|
| 0-26 | **全員を評価し直すバッチは無い。** 発動は購入・会員登録のイベントの瞬間だけ。`pending` で移した会員がメールの確認を終えると「会員登録」のルールが動く（`inactive` は動かない） | `internal/server/wire_events_domain.go:145-167`、`internal/service/auth_service.go:216-220, 394-410` |
| 0-27 | **きっかけの行が 0 件の「購入」のルールは、すべての購入で動く**（コースの購入も）。`584026af` では、きっかけのあるルールはコースの購入では動かない。【B7】`learning_path_id` で照合し、0 円の申し込みでも動く | `internal/domain/user_tag.go:249-262`、`internal/service/learning_path_purchase.go:442` |
| 0-28 | **`tag_auto_assign_rule_triggers.learning_path_id` は `584026af` に無い。** この列に書く移行は B7 の migration（`20261023075332`）が当たるまで失敗する | `internal/repository/tag_auto_assign_rule_repo.go:69, 170-177` |
| 0-29 | **読まれない「無効」の印は効かない**: 付与先の `valid = FALSE` / `deleted_at`、グループの条件（`tag_auto_assign_rule_group_conditions`）、タグの `deleted_at`。グループで絞ったルールは全員に効く | `MIG/20261001085757:47-68` |
| 0-30 | **運営がルールを開いて保存し直すと、きっかけ・条件・付与先が作り直される。** 画面は講座・プラン（【B7】コース）を指さないきっかけを落とすので、商品だけのきっかけは消えて「すべての購入で動く」ルールに変わる。付与先が条件（講座がアーカイブでない、クーポンが有効・期限内など）を満たさないと保存が 400 | `tag_auto_assign_rule_repo.go:44-63`、`btoc-frontend/.../rule-form.tsx:104`、`internal/service/tag_auto_assign_service.go:200-208` |
| 0-31 | 重複の判定は付与先の状態で行う（講座は受講登録があれば見送る）。履歴（`tag_auto_assign_logs`）は書くだけで、画面は読まない | `tag_auto_assign_service.go:290-395` |
| 0-32 | 付与先の終了日（`ends_on`）が過去だと、付与した瞬間に期限切れになる | `tag_auto_assign_service.go:338-358` |

## 1. チケット

| 表 | 読まれる列・使われ方 | 読まれない列 |
|---|---|---|
| `ticket_types` | `name`（残高・付与の画面）、`refund_deadline_days`（0-4）、`active` / `deprecated_at`（手動付与・一覧。消費では見ない）、`is_system` | `ticket_id`、`legacy_ticket_type` |
| `ticket_type_lessons` | 行があれば、その種別は列挙したレッスンだけで使える（0-6） | `deleted_at`、`created_at` |
| `ticket_grants` | `quantity` / `remaining_quantity` / `expires_at` / `source` / `note` / `granted_at`。消費は期限の近い順。取消は残があって期限内の分だけ | `starts_at`、`source_ref` |
| `ticket_ledger_entries` | 予約の `consumed` / `refunded` の行（`grant_id`・`quantity_delta` の符号）だけ（0-3）。`kind` は granted / consumed / refunded / expired / revoked（外部キー） | 予約の無い行すべて、`user_id`、`note` |
| `monthly_ticket_allowances` | 読み書きされない（0-8） | 全列 |
| `live_lesson_ticket_requirements` | `ticket_type_id` / `cost`（予約の消費とキャンセルの戻し） | `created_at` / `updated_at` |

**画面・API**: 受講者 `GET /api/v1/my-tickets`（/my-tickets）、運営 `GET /api/v1/tenant/users/:id/ticket-grants`（/admin/tickets）。どちらも `[{ticket_type_id, ticket_type_name, usable, grants: [{quantity, remaining_quantity, expires_at, expired, source, note, granted_at}]}]`。期限切れ・使い切りの付与も内訳に出る。

## 2. ライブの予約（受講 03 のデータ。移すのは課金の区分）

| 列 | 扱い |
|---|---|
| `status` | reserved / canceled / attended / no_show / host_canceled（0-11）。席を使うのは reserved / attended / no_show |
| `reserved_at` / `canceled_at` / `attended_at` | 画面に出る |
| `reminded_at` | 0-10 |
| `verification_key` / `settings` | **読まれない** |

**画面・API**: 受講者 `GET /api/v1/live/my-reservations`（削除済みのレッスンは出ない）、`GET /api/v1/live/calendar`、`POST/DELETE /api/v1/live/occurrences/:id/reservations`。運営 `GET /api/v1/live/occurrences/:id/reservations`（名簿）、`POST .../attendance`。キャンセルできるのは `reserved` で期限内。

`live_lesson_reviews` と `live_lesson_limit_item_history` は**読み書きされない**。

## 3. 決済

| 列 | 扱い |
|---|---|
| `provider` | stripe / robotpayment / bank_transfer / legacy_jpayment（外部キー）。0-18 |
| `provider_payment_id` | 0-15・0-17・0-20・0-21。`UNIQUE (provider, provider_payment_id)` |
| `type` | course_purchase / subscription / marketplace_license / refund / lw2_purchase / learning_path_purchase（外部キー）。`learning_path_purchase` は返金のときコースを取り消す。Go は `lw2_purchase` を知らない（文字列のまま通る） |
| `status` | pending / succeeded / failed / refunded / partially_refunded（外部キー）。`succeeded` で売上・領収書・返金のボタン、`pending` で照合（0-16） |
| `amount` / `currency` / `platform_fee` | 売上は `amount - platform_fee`。`platform_fee` は NOT NULL（既定値なし） |
| `created_at` | 並び順・売上の月日・領収書の取引日 |
| `application_id` / `settings` | **読まれない** |

**画面・API**: 運営 `GET /api/v1/tenant/payments`（収益の画面。全種類・全状態。画面は最新 20 件だけ出る既存の不具合あり）、月別・日別の売上。受講者の決済の一覧は画面に無い（`GET /api/v1/tenant/my-payments` はあるが使われない）。受講者は領収書の画面で決済を見る。

- `subscription_payments` / `learner_subscriptions` は Stripe の継続課金のもの。作ると継続課金の売上（MRR）・解約率に入る
- `learning_path_purchase_payments` は決済をコースに結ぶ（振込の一覧・入金待ちの判定）
- `learning_path_enrollments`: 受講中は `status = 'active'` かつ期限内。`payment_id` が返金の対象を決める。取り消しの画面は `source = 'admin'` だけ

## 4. 領収書

| 表 | 扱い |
|---|---|
| `receipts` | PDF は保存した列だけで描く（宛名・但し書き・金額・税・発行者・取引日・`issue_no`）。`issue_no > 1` は「再発行」。`receipt_log_id` は**読まれない** |
| `receipt_settings` | `enabled` / 発行者 / 登録番号 / 税率。検証（登録番号は `T` ＋ 13 桁など）は運営が保存するときだけ |

**画面・API**: 受講者 `/my-receipts/issuable`（決済の最新 200 件の `succeeded`）、`/my-receipts`、`/my-receipts/:id/pdf`、`POST /payments/:id/receipt`。運営 `GET/PUT /tenant/receipt-settings`。運営向けの発行履歴の画面は無い。

## 5. 自動割当

| 表 | 扱い |
|---|---|
| `tag_auto_assign_rules` | `active = TRUE` で `trigger_kind`（purchase / registration）が合うものが動く。`login_only` なら `active` の会員だけ。`assign_id` は引き継ぐだけ |
| `tag_auto_assign_rule_triggers` | `course_id` / `plan_id`（【B7】`learning_path_id`）で照合（0-27・0-28）。`item_id` / `item_type` は読まれない |
| `tag_auto_assign_rule_conditions` | どれか 1 つのタグを持っていれば成立。0 件なら絞らない |
| `tag_auto_assign_rule_group_conditions` | **読まれない**（0-29） |
| `tag_auto_assign_rule_grants` | `grant_kind`（course / coupon / announcement / recruit。recruit は付与のときエラー）・`target_id`・`starts_on` / `ends_on`。`valid` / `deleted_at` / `item_id` / `required` は**効かない** |
| `tag_auto_assign_logs` | 書くだけ（0-31） |

自動割当の画面は運営の /admin/tags/auto-assign-rules。

## 6. 新システムの E2E（参考）

チケット `68-tickets-lifecycle`、予約 `67-live-reservation-seats`、領収書 `70-receipt-issue`、収益 `12-payment-subscription`・`35-paid-checkout-flow`、売上 `63-admin-settings-billing-roster`・`15-admin-analytics`・`04-admin-dashboard`、振込・コース `74-bank-transfer`・`76`・`79`・`80`。**自動割当の E2E は無い。**
