# 課金 — 突き合わせ

[課金の内訳](breakdown.md) の対応表と **1対1で対応**する。内訳の行それぞれに `###` 見出しが1つあり、
**順序も内訳と同じ**。ひな形は [00-template/review.md](../00-template/review.md)。

- 観点（テーブル / カラム / 型 / 性質）と深刻度（高 / 中 / 低）の定義は [README.md](../README.md#突き合わせの4つの観点)
- **「内容」は問題点だけ、「修正方法」はどう直すかだけ。** 修正方法が `未決:` で始まるものは**実装前に閉じるべき論点**
- 本文中の「ステージング実測」は 2026-09-18 のダンプで `tenant_id = 10`（ReCADemy）に絞った値

> **[移行の原則](../00-template/review.md#移行の原則)に従う。** 対象外のデータ以外はすべて移行し、
> 受け皿が無ければ追加し、元の構造を維持する。

---

## B1 チケット定義

内訳: [breakdown.md](breakdown.md#b1-チケット定義)

### `ticket` → `ticket_types`

`ticket` (7列) → `ticket_types` (10列) ／ ETL段 L6 ／ ローカルデータ数 41 / C ／ ステージング実測 2件

そのまま対応: 2列（`ticket_name`→`name`、`tenant_id`）

| 旧カラム | 新カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|---|:--:|---|---|
| `ticket_type` int(11) | — | 性質 | 中 | **種別コードが落ちる。** `ticket_types` は `name` で区別する設計で、**種類を表す列を持たない**。**`user_ticket_log.ticket_type` はこの値を参照している**ので、落とすと履歴と残高を突き合わせられなくなる | A1 の `ticket_types.legacy_type` を追加して移す。ステージング実測では2件とも `1` |
| `ticket_id` | `id` char(26) | 性質 | 中 | ID の読み替え | A1 の `ticket_types.legacy_id` ＋ `UNIQUE (tenant_id, legacy_id)` を追加し、決定論 ULID で採番する |
| `ticket_name` varchar(200) | `name` varchar(200) | — | — | 対応あり | **ステージング実測では2件が同じ名前**（「3級マンツーマンレッスン専用チケット」）。`ticket_types.name` に UNIQUE は無いので投入は止まらないが、**運営画面で区別が付かない** |
| `del_chk` | `active` / `deprecated_at` | 性質 | 低 | 削除フラグ → 有効フラグ | `del_chk = 1` なら `active = FALSE` + `deprecated_at`。ステージング実測は0件 |
| — | `description` / `refund_deadline_days` | カラム | 低 | 旧に対応なし | NULL のまま。`chk_tt_refund_days` は NULL を許す |

**まとめ**: 受け皿が無い列 1 / 変換規則が要る列 3 / 高 0 件

### `ticket_limit_lesson` → `ticket_type_lessons`

`ticket_limit_lesson` (5列) → `ticket_type_lessons` (4列) ／ ETL段 L6 ／ ローカルデータ数 41 / C ／ ステージング実測 2件

| 旧カラム | 新カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|---|:--:|---|---|
| `live_lesson_id` | `lesson_id` char(26) + FK → `lessons` | 性質 | 中 | **新の参照先は `lessons`**（`live_lessons` ではない）ので、**L1 でライブのレッスン行が先に入っている必要がある** | [投入順序](#投入順序この区分の実行計画)でフェーズ5に置く。ステージング実測では孤児0件 |
| `del_chk` | — | カラム | 低 | 削除フラグ | **削除済みの行は移さない**（中間表なので、行の不在で表現できる）。ステージング実測は0件 |
| `regist_date` | `created_at` | — | — | 対応あり | |

**まとめ**: 受け皿が無い列 1 / 変換規則が要る列 1 / 高 0 件

### `live_lesson.item_ticket_price` → `live_lesson_ticket_requirements`

`live_lesson.item_ticket_price` → `live_lesson_ticket_requirements` (6列) ／ ETL段 L6 ／ ステージング実測 3件（`item_ticket_price > 0` のライブ）

| 旧カラム | 新カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|---|:--:|---|---|
| — | `ticket_type_id` char(26) **NOT NULL** + FK → `ticket_types` | **テーブル** | **高** | **旧はライブ側に「どの種別のチケットが要るか」を持たない。** `ticket_limit_lesson` が逆向き（種別→ライブ）に持っているだけで、**その行が無いライブは種別を決められない**。ステージング実測で **`item_ticket_price > 0` の3件のうち1件**（`live_lesson_id = 10`）に `ticket_limit_lesson` の行が無い | 未決: **`ticket_limit_lesson` から逆引きし、引けないライブをどうするか**を運営と決める。**1つの種別に絞れない場合も同じ**（`live_lesson_ticket_requirements` の PK は `lesson_id` 単独なので、ライブ1件につき1種別しか持てない） |
| `item_ticket_price` | `cost` int NOT NULL DEFAULT 1 + **CHECK `chk_lltr_cost (cost >= 1)`** | 型 | 中 | **`0` を入れられない** | **`0` の行は行自体を作らない**（[`live_lesson`](../02-content/../02-content/review.md#live_lesson--lessonstypelive--live_lessons) 参照）。ステージング実測は 18件中15件が `0` |

**まとめ**: 受け皿が無い列 — / 変換規則が要る列 2 / **高 1 件**

### なし → `course_ticket_grants` / `ticket_grant_sources` / `ticket_ledger_kinds`

| 新テーブル | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|:--:|---|---|
| `course_ticket_grants` (8列) | テーブル | 低 | **講座購入時のチケット付与。** lw2 は付与を商品（`payment_item`）側で管理していて、講座に紐づく概念が無い | **空で始める**（→ [移行の対象外 B](#b-方針として移行しないもの)）。課金区分（未コミット）の移行時に、商品→講座の対応が付くなら埋め直す |
| `ticket_grant_sources` (8列) | — | — | シード済み3値（`manual` / `course_purchase` / `standalone_purchase`） | **移行分はすべて `manual`** とし、`note` に出どころを残す |
| `ticket_ledger_kinds` (9列) | 性質 | 中 | シード済み5値（`granted` / `consumed` / `refunded` / `expired` / `revoked`）。**旧 `action_type` の `update` に対応する値が無い** | [`user_ticket_log`](#user_ticket_log--ticket_ledger_entries) 参照。**履歴を再生しない方針なら追加は不要** |

## B2 チケット残高・台帳

内訳: [breakdown.md](breakdown.md#b2-チケット残高台帳)

### `user_ticket` → `ticket_grants`

`user_ticket` (8列) → `ticket_grants` (13列) ／ ETL段 L6 ／ ローカルデータ数 3,231 / C ／ ステージング実測 8件 / 4名 / 計17枚

そのまま対応: 2列（`user_id`、`regist_date`→`granted_at`）

| 旧カラム | 新カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|---|:--:|---|---|
| `ticket_id` int(11) **NULL可** | `ticket_type_id` char(26) **NOT NULL** + FK | **型** | **高** | **種別が未設定の残高行を入れられない。** ステージング実測で **8件中3件**が NULL | 未決: **既定の種別を1つ作って入れるか、その行を移さないか**を運営と決める。**ツールは移さない**（[共通仕様 3.5.1](../../migration-spec.md#351-not-null--unique--外部キーに当たる行)）ので、決めないと3名分の残高が消える |
| `ticket_num` int(11) | `quantity` int + **CHECK `chk_tg_qty (quantity >= 1)`** | **型** | **高** | **`0` の行を入れられない。** ステージング実測で **8件中2件**が `0`（使い切った残高） | 未決: **使い切った残高を移す必要があるか**を運営と決める。**移すなら新環境側の CHECK を緩める**判断になる（`quantity >= 0`）。移さないなら「過去にチケットを持っていた」記録が消える |
| `ticket_num` | `remaining_quantity` int + **CHECK `chk_tg_remaining`** | 性質 | 中 | **残高1行 = 付与1行**として両方に同じ値を入れる。**「何枚付与されて何枚使ったか」は表現できない**（旧が残高しか持たないため） | `quantity = remaining_quantity = ticket_num` とし、`note` に「lw2 移行時点の残高」と書く（ETL設計 §5-6） |
| `ticket_end_date` date | `expires_at` datetime(3) | 型 | 低 | date → datetime。**JST 00:00 を UTC に直すと前日 15:00 になり、有効期限が1日早まる** | **JST の 23:59:59 として変換する**（終了日なので日の終わりを補う）。ステージング実測は**全件 NULL** |
| `ticket_start_date` date | — | カラム | 低 | 利用開始日が落ちる | A1 の `ticket_grants.starts_at` を追加して移す。ステージング実測は全件 NULL |
| `authority_id` | `source_ref` char(26) | 性質 | 低 | 有料受講権限との紐付け。**参照先は課金区分（未コミット）** | その区分の移行後に埋める。**それまでは NULL**（`source_ref` は NULL 可） |
| — | `source` varchar(32) **NOT NULL** + FK | 性質 | 中 | 旧に対応列なし | `manual` 固定（ETL設計 §5-6） |
| `(user_id, ticket_id, authority_id)` | — | 性質 | 低 | **旧は UNIQUE。** 新に対応する一意制約が無い | 決定論 ULID の入力にこの3列を使う（再実行で同じ ID になる） |

**まとめ**: 受け皿が無い列 1 / 変換規則が要る列 5 / **高 2 件**

### `month_user_ticket` → なし

`month_user_ticket` (13列) → なし ／ ETL段 — ／ ローカルデータ数 54 / C ／ ステージング実測 1件

| 旧カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|:--:|---|---|
| `target_month` / `max_ticket_count` / `ticket_count` / `limit_date` / `agreement_date` | テーブル | 中 | **月次のチケット配布（サブスク型）が落ちる。** 「毎月◯枚まで」の契約と消化状況を持っている | `monthly_ticket_allowances` を追加する（→ A2）。**配布を実行する機能は新環境に無い**ので、機能を作るかは別途決める |
| `application_id` / `is_application` | カラム | 低 | 申込との紐付け。**参照先は課金区分（未コミット）** | A2 に `legacy_application_id` として保持し、課金区分の移行後に解決する |
| `is_trial` / `del_chk` | カラム | 低 | 初回無料・削除フラグ | A2 に移す |

**まとめ**: 受け皿が無い列 13 / 高 0 件

### `user_ticket_log` → `ticket_ledger_entries`

`user_ticket_log` (10列) → `ticket_ledger_entries` (9列) ／ ETL段 L6 ／ ローカルデータ数 986 / B ／ ステージング実測 34件

> **[データ種別対照表](../data-type-mapping.md) は PDF の X（受け皿なし）を覆して ◯ としている。** 受け皿のテーブルは実在するが、**下の2件が理由で履歴は再生できない。**

| 旧カラム | 新カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|---|:--:|---|---|
| — | `grant_id` char(26) **NOT NULL** + FK → `ticket_grants` | **テーブル** | **高** | **旧ログに「どの付与に対する増減か」を示す列が無い。** 参照しているのは `ticket_type`（種別コード）だけで、**`ticket_id` すら持たない**。新の台帳は付与行にぶら下がる設計なので、**`grant_id` を決められない** | **旧ログは再生しない**（→ [移行の対象外 A](#a-移行できないもの)）。**ただし台帳を空にはしない** — 移行する予約に対して `consumed` 行を作る（2026-09-24 決定）。**無いとキャンセルしてもチケットが戻らない**（`RefundForReservation` が台帳から引いた枚数を読む）。詳細は [migration-spec 3.2](migration-spec.md#32-変換transform) |
| `ticket_num` + `ticket_count` | `quantity_delta` int **NOT NULL** | **性質** | **高** | **増減の符号を持つ列が旧に無い。** ステージング実測では `ticket_num` が**残高のスナップショット**に見え（`create` 5 → `update` 6 → `lesson_cancel` 5）、**`use` の行は全件 NULL**（34件中15件）。**再生すると残高が `user_ticket.ticket_num`（正本）と必ず食い違う** | 同上。**符号を推測して作れば[共通仕様 3.5.1](../../migration-spec.md#351-not-null--unique--外部キーに当たる行)の「値を作り替えない」に反する** |
| `action_type` varchar(50) | `kind` varchar(32) + FK → `ticket_ledger_kinds` | 性質 | 中 | **ステージング実測の値は `create` 4 / `update` 2 / `use` 19 / `lesson_cancel` 9。** **カラムコメントは `create,update,use,cancel` と書いてあり、実データと食い違う**（`lesson_cancel` がコメントに無い）。`update` に対応する新の値も無い | 履歴を再生しないので対応表は不要。**再生するなら `lesson_cancel` → `refunded`、`update` は新値の追加が要る** |
| `live_lesson_reserve_id` | `reservation_id` char(26) + FK | 性質 | 中 | L03 の予約 ID。ステージング実測で34件中19件に入っている。**予約の重複を畳むと参照先が消える行が出る** | 同上 |
| `ticket_item_id` / `payment_item_id` | — | カラム | 低 | チケット商品・支払い商品。**参照先は課金区分（未コミット）** | 同上 |
| `ticket_type` tinyint(4) | — | 性質 | 中 | **`ticket.ticket_type` を指しており、`ticket_id` ではない。** ステージング実測では `ticket` 2件がどちらも `ticket_type = 1` なので、**種別から `ticket_types` の行を一意に決められない** | 同上。A1 の `ticket_types.legacy_type` を入れておけば、**後から人が突き合わせられる** |

**まとめ**: 受け皿が無い列 3 / **高 2 件**

---

## B3 決済

**移行ツールは未実装。** ここに書いてあるのは**受け皿の有無と、実装前に決めが要る点**。

### `payment_item` → `course_purchase_payments`（一部）

`payment_item` (—) → `course_purchase_payments` ／ ローカルデータ数 336 / C ／ ステージング実測 301件

商品（講座パッケージ）。**この区分の外にも影響する表**で、コンテンツの価格（B1）と
受講権限の母集合がどちらもここを参照する。

| 旧カラム | 新カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|---|:--:|---|---|
| `(item_id, lesson_id)` | `tenant_plans` / `plan_courses` | 性質 | 中 | **商品と講座が 1:N。** 新環境にも**まとめ商品の受け皿はある**（`tenant_plans` ＋ `plan_courses`、`plan_type = course_bundle`）。買い切りも `interval_type = one_time` で表せる | **商品は `tenant_plans` に移す。** 情報は落ちない。**`courses.price`（講座1本の値段）には写す元が無い**ので NULL のままにする — 埋めると lw2 に無かった単品販売を始めることになる（→ [確認事項 D4](../open-questions.md#d-cutover-の運用で決めておきたいこと)） |
| `item_type` | — | 性質 | 中 | 商品の種別。受講可否判定が `item_type = 0` で絞っている（`LessonModel::1814`） | 受け皿が無い。**`0` 以外の商品が何かを本番ダンプで確認する** |
| `display_chk` / `valid_chk` / `del_chk` | — | カラム | 中 | 表示中か・有効か・削除済みか。**受講可否判定はこの3つを見る** | 決済を移すときに `payments` 側の状態へ写す規則を決める |

**まとめ**: 受け皿が無い列 3 / 高 1 件

### `payment_application` → `payments` ほか

`payment_application` (—) → `payments` / `payment_statuses` / `payment_types` ほか ／ ローカルデータ数 634 / C ／ ステージング実測 479件

決済の申込。**クレジット・銀行振込・コンビニ・継続課金・分割払いが1表に同居**している。

| 旧カラム | 新カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|---|:--:|---|---|
| 決済手段（副次列） | `payment_types` / `payment_providers` | **性質** | **高** | **1表に5種類が同居**しており、どの列の組み合わせで種別が決まるかを読み解く必要がある | 実装前に `PaymentModel` を読んで判定条件を確定する。**列名から推測しない**（受講の `cancel_chk` と同じ誤りを繰り返さない） |
| 決済代行の識別 | `payment_providers` | カラム | 中 | lw2 は J-Payment を使っている | **`payment_providers` に `legacy_jpayment` を足す migration が要る** |
| 継続課金のカード | — | **性質** | **高** | **カード情報はプロバイダ側にあり lw2 の DB に無い。** 移しても継続課金は引き継げない | **移行の範囲外。** 切り替え時に会員へ再登録を依頼するか、プロバイダ間で移管できるかを別途確認する |
| 分割払いの未完済 | `installment_plans` / `installment_charges` | 性質 | 中 | **未完済 61件・契約総額 2,907万円が cutover をまたぐ**（ETL設計の実測） | 受け皿はある。**残債の引き継ぎ方を運営と決める** |
| `is_cancel` / `credit_payment_date` | `payment_status_events` | 性質 | 中 | 取り消しと決済日。受講可否判定でも使われる | `payment_statuses` の値に写す |

**まとめ**: 受け皿が無い列 2 / 変換規則が要る列 4 / **高 2 件**

### `analytics_tag` / `trigger_media` / `payment_trigger_media` → なし

流入元計測。**移行対象外**（PDF・再判定とも X）。実測は `analytics_tag` 7件のみで、
`trigger_media` / `payment_trigger_media` は対象テナント 0件。

## B4 帳票

**移行ツールは未実装。**

### `receipt_log` / `receipt_setting` → `receipts` / `receipt_settings`

ローカルデータ数 21 / 1 ／ ステージング実測 21件 / 1件（どちらも全件が対象テナント）

| 旧カラム | 新カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|---|:--:|---|---|
| 発行済み領収書 | `receipts` | 性質 | 中 | **決済に紐づく。** B3 が先に入っていないと 1 行も入らない | 決済の移行後に流す |
| 発行設定 | `receipt_settings` | 型 | 低 | 実測1件 | そのまま移す |

**まとめ**: 受け皿が無い列 — / 高 0 件

### `tax` → `receipt_settings.tax_rate`

`tax` (—) → `receipt_settings.tax_rate` ／ ローカルデータ数 1 / C

| 旧カラム | 新カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|---|:--:|---|---|
| テーブル全体 | `tax_rate` 1列 | 性質 | 中 | **`tenant_id` を持たない全体設定**で、新はテナントごとの1列。**期間別の税率を持てない** | 現在の税率を `receipt_settings.tax_rate` に入れる。**過去の領収書は当時の税率で発行済み**なので、`receipts` 側に税率を持たせるかを決める |

**まとめ**: 受け皿が無い列 1 / 高 0 件

### `agreement` / `cancel_policy` / `privacy_policy` / `tokusyo` → `consent_kinds` / `user_consents`

ローカルデータ数 4 / 2 / 2 / 2 ／ ステージング実測 2 / 1 / 1 / 1件

| 旧カラム | 新カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|---|:--:|---|---|
| 本文 | — | **性質** | **高** | **規約の本文を置く先が無い。** `user_consents` は「誰がいつ何に同意したか」の記録で、**同意した文書そのものは持たない** | 本文の受け皿を追加するか、**新環境で登録し直す**かを決める。過去の同意記録だけ移しても、**何に同意したかが辿れない** |
| 版・改定日 | `consent_kinds` | 性質 | 中 | 規約の版 | `consent_kinds` は種別のマスタで、版を持つかは要確認 |

**まとめ**: 受け皿が無い列 2 / **高 1 件**

## 新環境に追加するテーブル・カラム

> **migration に落とした形は [マイグレーション対象](schema-additions.md)。**
> **この区分の migration はまだ無い** — `doctor` が `[TODO]` で出るのが現在の正しい状態。

| # | 追加するもの | 旧環境の対応 | 変更が必要な機能 |
|---|---|---|---|
| **A1** | `ticket_types.legacy_id` / `legacy_type` ＋ UNIQUE `uk_tt_legacy`、`ticket_grants.starts_at` | `ticket.ticket_id` / `ticket_type` / `user_ticket.ticket_start_date` | ・**`user_ticket_log.ticket_type` が参照しているのは `legacy_type`**（`ticket_id` ではない）。履歴を移さなくても**あとで人が突き合わせられる**ようにする<br>・`starts_at` は実測全件 NULL |
| **A2** | `monthly_ticket_allowances`（月次のチケット配布） | `month_user_ticket`（実測1件） | ・「毎月◯枚まで」の契約と消化の判定<br>・`target_month` は `'YYYYMM'` の**書式を変えずに移す**<br>・`legacy_application_id` は決済（4-2）の移行後に解決する |

### 移行の対象外（移行できないもの / 移行しないもの）

#### A. 移行できないもの

| 対象 | なぜ移行できないか |
|---|---|
| `user_ticket` のうち `ticket_num = 0` の残高（実測2件） | `ticket_grants` の CHECK `chk_tg_qty (quantity >= 1)` に当たる。**制約を緩めるかは運営の判断**（[確認事項](migration-spec.md)）。**CHECK は事前検査でも見る** — 見ていなかった頃は dry-run を通って実 INSERT で落ちた |

#### B. 方針として移行しないもの

| 対象 | 理由 |
|---|---|
| `user_ticket_log`（消費履歴） | **キャンセルに要るのは「誰が予約したか」と「何枚使うか」だけ**で、履歴そのものは要らない（運営の判断）。**台帳（`ticket_ledger_entries`）の行は移行時に予約から組み立てて入れる**。**欠席（`no_show`）も席を占有する**ので消費済みとして数える — 除くと台帳が0行になる |

---

## 投入順序（この区分の実行計画）

**コンテンツ（2）が先。** `ticket_type_lessons` と `live_lesson_ticket_requirements` が
コンテンツで作るライブの `lessons` を参照する。

```
[migration]  A1 ticket_types / ticket_grants への列追加
             A2 monthly_ticket_allowances
                ↓
[billing.1]  ticket_types → ticket_type_lessons → live_lesson_ticket_requirements
             → ticket_grants → ticket_ledger_entries → monthly_ticket_allowances
                ↓
[billing.2]  決済（未実装）
[billing.3]  帳票（未実装）
```
