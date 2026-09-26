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

## 書くこと

ひな形は [00-template/breakdown.md](../00-template/breakdown.md)。実例は [01 基盤の内訳](../01-foundation/breakdown.md)。

1. 大分類の定義と件数（基盤は「マスター系 / ユーザー系」。区分ごとに適切な軸を選ぶ）
2. 中分類ごとの一覧表（旧テーブル / 新テーブル / データ種 / lw2区分 / ローカルデータ数・A·B·C / 説明 / 移行の注意）
3. 投入順序（新環境は実 FK があるため順序が強制される）
4. 新側に受け皿が無い中分類の名指し

作ったら **[review.md](review.md) の `###` 見出しを、この対応表の行と1対1・同じ順序に揃え直すこと**（現状はデータ種軸）。ひな形は [00-template/review.md](../00-template/review.md)。

## B1 チケット定義

| 旧テーブル | 新テーブル | データ種 | lw2区分 | ローカルデータ数 | A·B·C | 説明 | 移行の注意 |
|---|---|---|---|---:|:--:|---|---|
| `ticket` | `ticket_types` | L05 チケット | データ | 41 | C | チケットの種別 | ステージング実測は**2件のみ**で、**両方とも同じ名前**。種別の使い分けが読み取れない |
| `ticket_limit_lesson` | `ticket_type_lessons` | L05 チケット | データ | 41 | C | この種別が使えるライブ | 新の参照先は `lessons` なので、**L1 で作ったライブのレッスン行が先に要る** |
| `live_lesson.item_ticket_price` | `live_lesson_ticket_requirements` | L05 チケット | データ | — | C | ライブ1件あたりの必要枚数 | `ticket_type_id` が **NOT NULL** だが、**旧はライブ側に種別を持たない**。`cost` の CHECK が `>= 1` なので `0`（チケット不要）は行を作らない |
| — | `course_ticket_grants` / `ticket_grant_sources` / `ticket_ledger_kinds` | L05 チケット | データ / マスタ | — | — | 講座購入時の付与と2つのルックアップ | `course_ticket_grants` は旧に対応なし（lw2 の付与は商品側）。ルックアップは**シード済み** |

## B2 チケット残高・台帳

| 旧テーブル | 新テーブル | データ種 | lw2区分 | ローカルデータ数 | A·B·C | 説明 | 移行の注意 |
|---|---|---|---|---:|:--:|---|---|
| `user_ticket` | `ticket_grants` | L05 チケット | データ | 3,231 | C | 会員が持つ残高（8列 → 13列） | **残高1行 = 付与1行**として移す。`ticket_id` が NULL の行と `ticket_num = 0` の行が新の制約（NOT NULL / `chk_tg_qty`）に当たる |
| `month_user_ticket` | — | L05 チケット | データ | 54 | C | 月次のチケット配布 | 受け皿なし。ステージング実測1件 |
| `user_ticket_log` | `ticket_ledger_entries` | L07 台帳 | イベント・履歴 | 986 | B | チケットの増減履歴 | **`grant_id`（NOT NULL）を決められない。** 旧ログは「どの付与に対する消費か」も増減の符号も持たない |

## B3 決済

**移行ツールは未実装。** 受け皿の有無だけ確認してある。

| 旧テーブル | 新テーブル | データ種 | lw2区分 | ローカルデータ数 | A·B·C | 説明 | 移行の注意 |
|---|---|---|---|---:|:--:|---|---|
| `payment_item` | `course_purchase_payments`（一部） | K01 商品 | データ | 336 | C | 商品（講座パッケージ）。実測 301件 | **講座と 1:N。** [コンテンツ B1 の価格](../open-questions.md)と[受講の母集合](../03-enrollment/review.md)の両方がこの表に依存する |
| `payment_item_lesson` | — | K01 商品 | 中間 | 1,134 | C | 商品と講座の対応 | **`tenant_id` を持たない。** `payment_item` と join して絞る |
| `payment_item_cate` / `payment_item_item_cate` | — | K01 商品 | 分類 | 10 / 34 | C | 商品カテゴリ | 受け皿なし |
| `payment_application` | `payments` ほか10表 | K02〜K07 決済 | データ | 634 | C | 決済の申込（実測 479件）。クレジット / 銀行振込 / コンビニ / 継続課金 / 分割払いが**1表に同居** | **`payment_providers` に `legacy_jpayment` を足す migration が要る**。継続課金のカード情報は移せない（プロバイダ側） |
| `payment_application_item` | — | K01 商品 | 中間 | 634 | C | 申込と商品の対応 | |
| `payment_infomation` | — | K01 商品 | 設定 | 3 | C | 決済まわりのテナント設定。実測1件 | |
| `payment_application_set_user_learning_lesson` | — | K01 商品 | 中間 | 27 | C | 申込と受講の対応 | |
| `analytics_tag` / `trigger_media` / `payment_trigger_media` | — | K13 流入元計測 | データ | 12 / 7 / 7 | X | 流入元の計測タグ | **移行対象外**（PDF・再判定とも X）。実測は `analytics_tag` 7件のみで、他は0件 |

## B4 帳票

**移行ツールは未実装。**

| 旧テーブル | 新テーブル | データ種 | lw2区分 | ローカルデータ数 | A·B·C | 説明 | 移行の注意 |
|---|---|---|---|---:|:--:|---|---|
| `receipt_log` | `receipts` | K08 領収書 | データ | 21 | C | 発行済み領収書。実測21件（全件が対象テナント） | 決済（B3）に紐づくので**先に決済が要る** |
| `receipt_setting` | `receipt_settings` | K08 領収書 | 設定 | 1 | C | 領収書の発行設定。実測1件 | |
| `tax` | `receipt_settings.tax_rate` | K09 消費税 | 設定 | 1 | C | 消費税率 | **`tenant_id` を持たない全体設定。** 新は `receipt_settings.tax_rate` の1列で、**期間別の税率を持てない** |
| `agreement` / `cancel_policy` / `privacy_policy` / `tokusyo` | `consent_kinds` / `user_consents` | K12 特商法・規約 | 設定 | 4 / 2 / 2 / 2 | C | 規約・キャンセルポリシー・プライバシーポリシー・特商法表記。実測は各1〜2件 | **本文を置く先が無い。** `user_consents` は「誰がいつ同意したか」で、**規約の本文は持たない** |
