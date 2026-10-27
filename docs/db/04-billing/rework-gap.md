# 課金 — 移行仕様と今の移行ツールの差分

移行の見直しの手順 4（[進捗](../rework-progress.md)）。[移行仕様の 0 章](migration-spec.md#0-見直し2026-10-26-決定)（決定は 0-2・0-3）と、今の移行ツール・文書・school-launcher との差分。手順 5 でこの順に直す。

## 1. 移行ツール（`migrator/steps/billing/` ほか）

| # | 直すもの | 直す先 | 今 | 直したあと |
|---|---|---|---|---|
| G1 | 専用チケットの期限（Q1） | `tickets.py` `TicketGrantsStep` | `expires_at` / `starts_at` = `ticket_end_date` / `ticket_start_date`（全行 NULL → 無期限） | 結び付く権限（`authority_id` → `payment_item_lesson_authority`）の `authority_end_date` の終わり（JST）/ `authority_start_date` の始まり。権限が削除済みでも期間はそのまま写す（旧も期限で判定する）。権限の引けない行は今のまま（`settings` などに印） |
| G2 | 種別の無い回数チケット（Q2） | `tickets.py` `TicketGrantsStep` | 種別の外部キーで一覧に出る（理由が「外部キー」） | 運営の回答（D22）まで移さない。**`extract` で理由「受け皿なし」・詳細「種別の無い回数チケット。種別を決めるまで移さない（D22）」として一覧に出す** |
| G3 | 予約 1 回で引く枚数（Q3） | `tickets.py` `TicketRequirementsStep` | `cost = item_ticket_price`（配る枚数） | 専用チケットの要求は **`cost = 1`**。`item_ticket_price` は `ticket_types` か要求の行のどこにも入れる先が無いので、ライブの `lessons.settings` などに残っているかを確かめ、無ければ一覧に出さずに要求の行の注記に残す（実装で決める） |
| G4 | 予約で使ったチケットの記録（Q4） | `tickets.py` `TicketLedgerStep` | 席を使う予約すべて（過去の 2 件に誤った `consumed -3`、9 件で警告） | **開催が未来で、チケットで払った（専用・回数・月）予約だけ**。枚数は Q3 の枚数。ステージングは 0 件 |
| G5 | 月チケットの今の期間の残り（Q5） | `extras.py` に Step を足す | `monthly_ticket_allowances` だけ | 今の期間（`agreement_date <= 今日 <= limit_date`、削除されていない）の残り `ticket_count > 0` を `ticket_grants` にも入れる。**種別が無いので、種別が決まるまで（D22）は理由「受け皿なし」で一覧に出す**。ステージングは 0 件 |
| G6 | 未入金の申込（Q6） | `payments.py` `STATUSES` | `application_result = 0` → `pending` | **`failed`**。旧の値は `settings.legacy_application_result` に残す（46 件） |
| G7 | 会員の無い申込とコースの購入（Q8） | `enrollment/learning_paths.py` `LearningPathEnrollmentsStep`、`enrollment/rights.py` `_payment_of` | 決済が会員の外部キーで落ちるのに、`payment_id` / `provider_payment_id` がその決済を指す（コースの購入が連鎖して落ちる） | **会員が移らない申込（`user_id` が会員にいない）の決済には結ばない**（`payment_id` / `provider_payment_id` を NULL）。補正データで会員を直せば結ばれる |
| G8 | 期間ごとの領収書（Q9） | `receipts.py` `ReceiptsStep` | 期間と旧の番号を捨てる | 旧の期間（`payment_date_from` / `to`）と番号（`seq_no`）を S1 の列に入れる |

## 2. school-launcher

| # | 直すもの | 中身 | 状態 |
|---|---|---|---|
| S0 | B7 の migration（0-3） | `20261023075332_add_learning_path_to_tag_auto_assign_triggers.sql` を、手元の checkout（`feat/lw2-auto-assign-learning-path-trigger`）から作業ブランチ `feat/lw2-migration-rework` に写す。**Go の修正は写さない** | 決定済み（2026-10-26） |
| S1 | 領収書の旧の期間・番号（Q9） | **migration で `receipts.settings JSON NULL` を足す**（旧の期間・番号。アプリは読まない）。新しい migration（例 `20261026120002_add_receipt_settings.sql`） | **要確認**（migration を作る） |

## 3. 補正データ（`fixups/`）

| # | 直すもの | 中身 |
|---|---|---|
| F1 | 申込 322 の会員（Q8） | `payment_application.user_id` を 911 に直す提案（権限と登録の時刻から）。`migrator/overrides.py` の `KEY_COLUMNS` に `payment_application` を足す |

## 4. 確認（`verify`）

| # | 中身 |
|---|---|
| V1 | `spec_checks.billing_spec` に足す: T-01〜T-07、P-01〜P-06、R-01・R-02、A-01〜A-04、L-01（03 の V-01・V-02 は置いてある）。P-04 は月ごとの差を「分かっている差」（申込日時と入金日のずれ 1 件・入金日の無い 7 件）として出す |
| V2 | `legacy_checks.billing_checks` を直す: 決済の状態（未入金 → failed）、チケットの残高の期限、要求の枚数、台帳の件数、領収書の期間 |

## 5. 単体テスト（`tests/`）

| # | 中身 |
|---|---|
| T1 | G1〜G8 の変換と一覧に出す行 |
| T2 | F1 |
| T3 | V1・V2 |

## 6. E2E

| # | 中身 |
|---|---|
| E1 | `e2e/billing.spec.ts`（新規）: T-08・V-03・P-07・R-03・A-05。**移したデータを書き換える操作は流さない**。03 で飛ばした E-07・P-02・P-03（コースの受講）と V-03（予約）もここで流す |

## 7. 文書

| # | 中身 |
|---|---|
| D1 | `migration-spec.md` の 1〜3 章（P6 の状態、チケット、領収書）、`review.md`、`breakdown.md`、`schema-additions.md`（S1） |
| D2 | `../open-questions.md` に **D22**（種別の無い回数チケット・月チケットの種別。ライブにどの種別を要求にするか）、**D5 か D8 に振込の未入金 6 件**（約 140 万円。まだ入金を待つものが無いか）、**E13 に会員の編集で自動割当が動かないこと**、売上は初回の分だけになること、移した決済は返金できないこと、翌月からのチケットの配布は手作業になること |
| D3 | `../not-migrated-summary.md`（G2・G5 の行） |
| D4 | `../sync-issues.md` の B7 を「作業ブランチに migration だけ写した」に更新 |
