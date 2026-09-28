# 課金テーブルの内訳

移行計画の **4 課金**（チケット / 決済 / 帳票）。

[データ種別対照表](../data-type-mapping.md) が分類したデータ種を、**移行計画の区分**で切り直したもの。
移行ツールの**投入順序を決めるための一覧**として使う。新環境は実 FK を持つため、
前の区分が入っていないと1行も入らない。

- 全件の逆引き: [旧環境](../legacy-table-coverage.md) / [新環境](../new-table-coverage.md)
- カラムの突き合わせ: [review.md](review.md)
- 移行の手順: [migration-spec.md](migration-spec.md)

> **受講（3）のライブ予約が終わっていること。** 消費の台帳が予約を参照する。

> **ローカルデータ数と A·B·C の定義は [README.md](../README.md#共通の列の意味) にある。**
> ローカルデータ数は**全73テナントの合計**で ReCADemy 単体ではない。本文中の「ステージング実測」は
> 2026-09-18 のダンプで `tenant_id = 10`（ReCADemy）に絞って数えた値。

---

## 大分類

| 大分類 | 中分類 | 移行ツール | 新環境の受け皿 |
|---|---|---|---|
| **チケット** | B1 定義 / B2 残高・台帳 | 実装済み（`billing.1`、6 Step） | 既存の表 ＋ A1 / A2 |
| **決済** | B3 | 実装済み（`billing.2`、5 Step。**暫定の規則**） | 既存の表 ＋ A3〜A6 |
| **帳票** | B4 | 実装済み（`billing.3`、3 Step。**暫定の規則**） | 既存の表 ＋ A7 / A8 |

**追加スキーマ（A1〜A8）は school-launcher の `20260928132756_lw2_billing_additions.sql`。** 決済・帳票は
暫定の規則で作ってある（[migration-spec 1-3](migration-spec.md)）。

## B1 チケット定義

| 旧テーブル | 新テーブル | データ種 | lw2区分 | ローカルデータ数 | A·B·C | 説明 | 移行の注意 |
|---|---|---|---|---:|:--:|---|---|
| `ticket` | `ticket_types` | L05 チケット | データ | 41 | C | チケットの種別 | ステージング実測は**2件のみ**で、**両方とも同じ名前**。種別の使い分けが読み取れない |
| `ticket_limit_lesson` | `ticket_type_lessons` | L05 チケット | データ | 41 | C | この種別が使えるライブ | 新の参照先は `lessons` なので、**コンテンツ（2）で作るライブのレッスン行が先に要る** |
| `live_lesson.item_ticket_price` | `live_lesson_ticket_requirements` | L05 チケット | データ | — | C | ライブ1件あたりの必要枚数 | `ticket_type_id` が **NOT NULL** だが、**旧はライブ側に種別を持たない**（`ticket_limit_lesson` から逆引きする）。**引けないライブはチケット不要として移る**（ステージングで3件中1件）。`cost` の CHECK が `>= 1` なので `0`（チケット不要）は行を作らない |
| — | `course_ticket_grants` / `ticket_grant_sources` / `ticket_ledger_kinds` | L05 チケット | データ / マスタ | — | — | 講座購入時の付与と2つのルックアップ | `course_ticket_grants` は旧に対応なし（lw2 の付与は商品側）。ルックアップは**シード済み** |

## B2 チケット残高・台帳

| 旧テーブル | 新テーブル | データ種 | lw2区分 | ローカルデータ数 | A·B·C | 説明 | 移行の注意 |
|---|---|---|---|---:|:--:|---|---|
| `user_ticket` | `ticket_grants` | L05 チケット | データ | 3,231 | C | 会員が持つ残高（8列 → 13列） | **残高1行 = 付与1行**として移す。`ticket_id` が NULL の行と `ticket_num = 0` の行が新の制約（NOT NULL / `chk_tg_qty`）に当たる |
| `month_user_ticket` | `monthly_ticket_allowances`（A2 で追加） | L05 チケット | データ | 54 | C | 月次のチケット配布 | 受け皿を追加して移す。ステージング実測1件。**配布を実行する機能は新環境に無い** |
| `user_ticket_log` | — | L07 台帳 | イベント・履歴 | 986 | B | チケットの増減履歴 | **移さない**（2026-09-24 決定）。旧ログは「どの付与に対する消費か」も増減の符号も持たず、`grant_id`（NOT NULL）を決められない |
| （`live_lesson_reserve`） | `ticket_ledger_entries` | L07 台帳 | — | — | — | 予約が消費したチケット | **予約から組み立てる。** 席を占める予約（予約中・出席・欠席）1件につき `consumed` を1行。**戻し先の付与が移らない予約は行を作れない**（ステージングで9件。キャンセルしてもチケットが戻らない） |

## B3 決済

**お金が動く申込（カード・コンビニ・振込）だけを決済にする**（暫定。無料・チケット払いは移さない）。

| 旧テーブル | 新テーブル | データ種 | lw2区分 | ローカルデータ数 | A·B·C | 説明 | 移行の注意 |
|---|---|---|---|---:|:--:|---|---|
| `payment_item` | `tenant_plans`（A3） | K01 商品 | データ | 336 | C | 商品（講座パッケージ）。実測 301件（講座の商品 280件を移す。**すべて `inactive`**） | **講座と 1:N。** 新環境のまとめ商品（`plan_type = course_bundle`）で受けられる。[講座の価格（確認事項 B2 / C3）](../open-questions.md)と[受講の母集合](../03-enrollment/review.md)の両方がこの表に依存する |
| `payment_item_lesson` | `plan_courses` | K01 商品 | 中間 | 1,134 | C | 商品と講座の対応 | **`tenant_id` を持たない。** `payment_item` と join して絞る |
| `payment_item_cate` / `payment_item_item_cate` | — | K01 商品 | 分類 | 10 / 34 | C | 商品カテゴリ | 受け皿なし。移していない |
| `payment_application` | `payments`（A4）＋ `course_purchase_payments` / `subscription_payments` | K02〜K07 決済 | データ | 634 | C | 決済の申込（実測 479件）。**申込1行 = 契約1件**で、継続課金・分割の毎月の課金は J-Payment が持ち lw2 に行が無い | 決済にするのは 365件、投入 354件（会員が物理削除された11件は移らない）。決済代行は `legacy_jpayment`（A5）/ `bank_transfer`。**継続課金（`learner_subscriptions`）・分割（`installment_plans`）は作らない** |
| `payment_application_item` | —（決済の種類の判定に使う） | K01 商品 | 中間 | 634 | C | 申込と商品の対応（1申込に1商品） | |
| `payment_infomation` | `tenants.settings.lw2_payment` / `tenant_legal_documents` | K01 商品 | 設定 | 3 | C | 決済まわりのテナント設定。実測1件 | 支払い方法・カードブランド・分割回数はテナントの設定、規約の URL・表題の上書きは規約の本文と一緒に |
| `payment_application_set_user_learning_lesson` | — | K01 商品 | 中間 | 27 | C | 申込と受講の対応 | |
| `analytics_tag` / `trigger_media` / `payment_trigger_media` | — | K13 流入元計測 | データ | 12 / 7 / 7 | X | 流入元の計測タグ | **移行対象外**（PDF・再判定とも X）。実測は `analytics_tag` 7件のみで、他は0件 |

## B4 帳票

**実装済み**（暫定の規則 P11〜P14）。

| 旧テーブル | 新テーブル | データ種 | lw2区分 | ローカルデータ数 | A·B·C | 説明 | 移行の注意 |
|---|---|---|---|---:|:--:|---|---|
| `receipt_log` | `receipts` | K08 領収書 | データ | 21 | C | 発行済み領収書。実測21件（全件が対象テナント） | 決済（B3）に紐づくので**先に決済が要る**。8決済に21件（再発行を含む）。`issue_no` は決済ごとに振り直し、旧の番号は `legacy_id`（A7） |
| `receipt_setting` | `receipt_settings` | K08 領収書 | 設定 | 1 | C | 領収書の発行設定。実測1件 | |
| `tax` | `receipt_settings.tax_rate` | K09 消費税 | 設定 | 1 | C | 消費税率 | **`tenant_id` を持たない全体設定。** 新は `receipt_settings.tax_rate` の1列で、期間別の税率は持てない。発行済みの領収書は `receipts.tax_rate` に当時の税率を持てる |
| `agreement` / `cancel_policy` / `privacy_policy` / `tokusyo` | `tenant_legal_documents`（A8） | K12 特商法・規約 | 設定 | 4 / 2 / 2 / 2 | C | 規約・キャンセルポリシー・プライバシーポリシー・特商法表記。実測は各1〜2件 | 本文があるのは利用規約（ja / en）だけで、他は空（移さない）。**アプリはまだ読まない**。lw2 は同意を記録していないので `user_consents` には何も入らない |
