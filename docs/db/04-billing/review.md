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
| `ticket_type` int(11) | — | 性質 | 中 | **種別コードが落ちる。** `ticket_types` は `name` で区別する設計で、**種類を表す列を持たない**。**`user_ticket_log.ticket_type` はこの値を参照している**ので、落とすと履歴と残高を突き合わせられなくなる | A1 の `ticket_types.legacy_ticket_type` を追加して移す。ステージング実測では2件とも `1` |
| `ticket_id` | `id` char(26) | 性質 | 中 | ID の読み替え | A1 の `ticket_types.ticket_id` ＋ `UNIQUE (tenant_id, ticket_id)` を追加し、決定論 ULID で採番する |
| `ticket_name` varchar(200) | `name` varchar(200) | — | — | 対応あり | **ステージング実測では2件が同じ名前**（「3級マンツーマンレッスン専用チケット」）。`ticket_types.name` に UNIQUE は無いので投入は止まらないが、**運営画面で区別が付かない** |
| `del_chk` | `active` / `deprecated_at` | 性質 | 低 | 削除フラグ → 有効フラグ | `del_chk = 1` なら `active = FALSE` + `deprecated_at`。**`deprecated_at` は旧の `regist_date`**（旧に削除日時が無い）。ステージング実測は0件 |
| — | `description` / `refund_deadline_days` | カラム | 低 | 旧に対応なし | NULL のまま。`chk_tt_refund_days` は NULL を許す |

**まとめ**: 受け皿が無い列 1 / 変換規則が要る列 3 / 高 0 件

### `ticket_limit_lesson` → `ticket_type_lessons`

`ticket_limit_lesson` (5列) → `ticket_type_lessons` (4列) ／ ETL段 L6 ／ ローカルデータ数 41 / C ／ ステージング実測 2件

| 旧カラム | 新カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|---|:--:|---|---|
| `live_lesson_id` | `lesson_id` char(26) + FK → `lessons` | 性質 | 中 | **新の参照先は `lessons`**（`live_lessons` ではない）ので、**コンテンツ（2）でライブのレッスン行が先に入っている必要がある** | [投入順序](#投入順序この区分の実行計画)のとおり、コンテンツの後に流す。ステージング実測では孤児0件 |
| `del_chk` | `deleted_at`（2026-10-01 追加） | カラム | 低 | 削除フラグ | **削除済みも移す**（同じ組が積まれていれば生きている行を優先して1行）。新のアプリはまだ読まないので、外したライブにもチケットが使える。ステージング実測は0件 |
| `regist_date` | `created_at` | — | — | 対応あり | |

**まとめ**: 受け皿が無い列 1 / 変換規則が要る列 1 / 高 0 件

### `live_lesson.item_ticket_price` → `live_lesson_ticket_requirements`

`live_lesson.item_ticket_price` → `live_lesson_ticket_requirements` (6列) ／ ETL段 L6 ／ ステージング実測 3件（`item_ticket_price > 0` のライブ）

| 旧カラム | 新カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|---|:--:|---|---|
| — | `ticket_type_id` char(26) **NOT NULL** + FK → `ticket_types` | **テーブル** | **高** | **旧はライブ側に「どの種別のチケットが要るか」を持たない。** `ticket_limit_lesson` が逆向き（種別→ライブ）に持っているだけで、**その行が無いライブは種別を決められない**。ステージング実測で **`item_ticket_price > 0` の3件のうち1件**（`live_lesson_id = 10`）に `ticket_limit_lesson` の行が無い | `ticket_limit_lesson` から逆引きする。**いまの実装は、引けないライブの行を作らない — つまりチケット不要のライブとして移る**（警告ログを出す）。未決: **それでよいか**を運営と決める（→ [制約に当たって移らない行 #17](../constraint-violations.md)）。**1つの種別に絞れない場合は、いまの実装は読んだ順の最初の1つを黙って使う**（行は作る。警告は出さない。`live_lesson_ticket_requirements` の PK は `lesson_id` 単独なので、ライブ1件につき1種別しか持てない）。ステージング実測は該当なし。逆引きは生きている（`del_chk = 0`）`ticket_limit_lesson` の行だけを見る |
| `item_ticket_price` | `cost` int NOT NULL DEFAULT 1 + **CHECK `chk_lltr_cost (cost >= 1)`** | 型 | 中 | **`0` を入れられない** | **`0` の行は行自体を作らない**（[`live_lesson`](../02-content/../02-content/review.md#live_lesson--lessonstypelive--live_lessons) 参照）。ステージング実測は 18件中15件が `0` |

**まとめ**: 受け皿が無い列 — / 変換規則が要る列 2 / **高 1 件**

### なし → `course_ticket_grants` / `ticket_grant_sources` / `ticket_ledger_kinds`

| 新テーブル | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|:--:|---|---|
| `course_ticket_grants` (8列) | テーブル | 低 | **講座購入時のチケット付与。** lw2 は付与を商品（`payment_item`）側で管理していて、講座に紐づく概念が無い | **空で始める**（→ [移行の対象外 B](#b-方針として移行しないもの)）。決済（4-2）は実装済みだが、**この表には現状は書いていない**（実装が無い。2026-10-02 の確認） |
| `ticket_grant_sources` (8列) | — | — | シード済み3値（`manual` / `course_purchase` / `standalone_purchase`） | **移行分はすべて `manual`** とし、`note` に出どころを残す |
| `ticket_ledger_kinds` (9列) | 性質 | 中 | シード済み5値（`granted` / `consumed` / `refunded` / `expired` / `revoked`）。**旧 `action_type` の `update` に対応する値が無い** | [`user_ticket_log`](#user_ticket_log--なし台帳-ticket_ledger_entries-は予約から組み立てる) 参照。**履歴を再生しない方針なら追加は不要** |

## B2 チケット残高・台帳

内訳: [breakdown.md](breakdown.md#b2-チケット残高台帳)

### `user_ticket` → `ticket_grants`

`user_ticket` (8列) → `ticket_grants` (13列) ／ ETL段 L6 ／ ローカルデータ数 3,231 / C ／ ステージング実測 8件 / 4名 / 計17枚

そのまま対応: 2列（`user_id`、`regist_date`→`granted_at`）

| 旧カラム | 新カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|---|:--:|---|---|
| `ticket_id` int(11) **NULL可** | `ticket_type_id` char(26) **NOT NULL** + FK | **型** | **高** | **種別が未設定の残高行を入れられない。** ステージング実測で **8件中3件**が NULL | 未決: **既定の種別を1つ作って入れるか、その行を移さないか**を運営と決める（→ [制約に当たって移らない行 #14](../constraint-violations.md)）。**ツールは移さない**（[共通仕様 3.5.1](../../migration-spec.md#351-not-null--unique--外部キーに当たる行)）ので、決めないとその残高が消える。台帳を作れない予約9件は #15 のもので、**種別を割り当ててもこの9件は戻らない**（3件のうち1件は `ticket_num = 0` で #15 にも当たる） |
| `ticket_num` int(11) | `quantity` int + **CHECK `chk_tg_qty (quantity >= 1)`** | **型** | **高** | **`0` の行を入れられない。** ステージング実測で **8件中2件**が `0`（使い切った残高） | 未決: **使い切った残高を移す必要があるか**を運営と決める（→ [制約に当たって移らない行 #15](../constraint-violations.md)）。**移すなら新環境側の CHECK を緩める**判断になる（`quantity >= 0`）。移さないと、その残高で予約したライブの消費を台帳に書けず、**キャンセルしてもチケットが戻らない**。ステージングで**予約9件**（会員 3181 がライブ `live_lesson_id = 5` を予約したもの。その会員の種別 2 の残高が0枚）。CHECK を緩めれば9件とも台帳に書ける |
| `ticket_num` | `remaining_quantity` int + **CHECK `chk_tg_remaining`** | 性質 | 中 | **残高1行 = 付与1行**として両方に同じ値を入れる。**「何枚付与されて何枚使ったか」は表現できない**（旧が残高しか持たないため） | `quantity = remaining_quantity = ticket_num` とし、`note` に「lw2 移行時点の残高」と書く（ETL設計 §5-6） |
| `ticket_end_date` date | `expires_at` datetime(3) | 型 | 低 | date → datetime。**JST 00:00 を UTC に直すと前日 15:00 になり、有効期限が1日早まる** | **JST の 23:59:59 として変換する**（終了日なので日の終わりを補う）。ステージング実測は**全件 NULL** |
| `ticket_start_date` date | — | カラム | 低 | 利用開始日が落ちる | A1 の `ticket_grants.starts_at` を追加して移す。ステージング実測は全件 NULL |
| `authority_id` | `source_ref` char(26) | 性質 | 低 | 有料受講権限（`payment_item_lesson_authority`）との紐付け。受講（3）はこれを `(会員, 講座)` の組に畳んで `enrollments` に移しているので、**権限1行と受講1行が対応しない** | **NULL のまま**（`source_ref` は NULL 可）。決済（4-2）は実装済みだが、`source_ref` には現状は入れていない（実装が無い。2026-10-02 の確認） |
| — | `source` varchar(32) **NOT NULL** + FK | 性質 | 中 | 旧に対応列なし | `manual` 固定（ETL設計 §5-6） |
| `(user_id, ticket_id, authority_id)` | — | 性質 | 低 | **旧は UNIQUE。** 新に対応する一意制約が無い | 決定論 ULID の入力にこの3列を使う（再実行で同じ ID になる） |

**まとめ**: 受け皿が無い列 1 / 変換規則が要る列 5 / **高 2 件**

### `month_user_ticket` → `monthly_ticket_allowances`

`month_user_ticket` (13列) → `monthly_ticket_allowances`（A2 で追加）／ ローカルデータ数 54 / C ／ ステージング実測 1件

| 旧カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|:--:|---|---|
| `target_month` / `max_ticket_count` / `ticket_count` / `limit_date` / `agreement_date` | テーブル | 中 | **月次のチケット配布（サブスク型）。** 「毎月◯枚まで」の契約と消化状況を持っている | `monthly_ticket_allowances` を追加して移す（→ A2。実装済み）。**配布を実行する機能は新環境に無い**ので、機能を作るかは別途決める |
| `application_id` / `is_application` | カラム | 低 | 申込との紐付け。参照先の申込は決済（4-2）で `payments.application_id` に移る | A2 に `application_id`（旧列名のまま）として保持する。**決済と結ぶのは未実装**（`payments.application_id` で引ける） |
| `is_trial` / `del_chk` | カラム | 低 | 初回無料・削除フラグ | A2 に移す |

**まとめ**: 受け皿が無い列 — （A2 で受ける）/ 高 0 件

### `user_ticket_log` → なし（台帳 `ticket_ledger_entries` は予約から組み立てる）

`user_ticket_log` (10列) → `ticket_ledger_entries` (9列) ／ ETL段 L6 ／ ローカルデータ数 986 / B ／ ステージング実測 34件

> **[データ種別対照表](../data-type-mapping.md) は PDF の X（受け皿なし）を覆して ◯ としている。** 受け皿のテーブルは実在するが、**下の2件が理由で履歴は再生できない。**

| 旧カラム | 新カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|---|:--:|---|---|
| — | `grant_id` char(26) **NOT NULL** + FK → `ticket_grants` | **テーブル** | **高** | **旧ログに「どの付与に対する増減か」を示す列が無い。** 参照しているのは `ticket_type`（種別コード）だけで、**`ticket_id` すら持たない**。新の台帳は付与行にぶら下がる設計なので、**`grant_id` を決められない** | **旧ログは再生しない**（→ [移行の対象外 A](#a-移行できないもの)）。**ただし台帳を空にはしない** — 移行する予約に対して `consumed` 行を作る（2026-09-24 決定）。**無いとキャンセルしてもチケットが戻らない**（`RefundForReservation` が台帳から引いた枚数を読む）。詳細は [migration-spec 3.2](migration-spec.md#32-変換transform) |
| `ticket_num` + `ticket_count` | `quantity_delta` int **NOT NULL** | **性質** | **高** | **増減の符号を持つ列が旧に無い。** ステージング実測では `ticket_num` が**残高のスナップショット**に見え（`create` 5 → `update` 6 → `lesson_cancel` 5）、**`use` の行は全件 NULL**（34件中15件）。**再生すると残高が `user_ticket.ticket_num`（正本）と必ず食い違う** | 同上。**符号を推測して作れば[共通仕様 3.5.1](../../migration-spec.md#351-not-null--unique--外部キーに当たる行)の「値を作り替えない」に反する** |
| `action_type` varchar(50) | `kind` varchar(32) + FK → `ticket_ledger_kinds` | 性質 | 中 | **ステージング実測の値は `create` 4 / `update` 2 / `use` 19 / `lesson_cancel` 9。** **カラムコメントは `create,update,use,cancel` と書いてあり、実データと食い違う**（`lesson_cancel` がコメントに無い）。`update` に対応する新の値も無い | 履歴を再生しないので対応表は不要。**再生するなら `lesson_cancel` → `refunded`、`update` は新値の追加が要る** |
| `live_lesson_reserve_id` | `reservation_id` char(26) + FK | 性質 | 中 | L03 の予約 ID。ステージング実測で34件中19件に入っている。**予約の重複を畳むと参照先が消える行が出る** | 同上 |
| `ticket_item_id` / `payment_item_id` | — | カラム | 低 | チケット商品・支払い商品 | 同上（履歴を移さない） |
| `ticket_type` tinyint(4) | — | 性質 | 中 | **`ticket.ticket_type` を指しており、`ticket_id` ではない。** ステージング実測では `ticket` 2件がどちらも `ticket_type = 1` なので、**種別から `ticket_types` の行を一意に決められない** | 同上。A1 の `ticket_types.legacy_ticket_type` を入れておけば、**後から人が突き合わせられる** |

**まとめ**: 受け皿が無い列 3 / **高 2 件**

---

## B3 決済

**移行ツールは実装済み（暫定の規則。[migration-spec 1-3](migration-spec.md) の P1〜P10）。** 下の「未決:」は、運営の回答で規則を差し替える点。

> **内訳の残り（`payment_item_lesson` / `payment_item_cate` ほか / `payment_application_item` /
> `payment_infomation` / `payment_application_set_user_learning_lesson`）は列の突き合わせをしていない。** いまの扱い:
>
> - `payment_item_lesson` は `plan_courses` に移す（削除済みの対応も `deleted_at` で移す）。`payment_application_item` は決済の商品の特定に使う
> - `payment_infomation` は**移している**。設定は基盤のテナントの Step で `tenants.settings.lw2_payment`（P13）、
>   規約の URL・表題の上書きは `tenant_legal_documents`（`receipts.py`。P12）
> - 商品の分類（`payment_item_cate` 3件 / `payment_item_item_cate` 7件）と申込と受講の古い対応表
>   （`payment_application_set_user_learning_lesson` 27件）は**現状は移していない**（実装が無い。2026-10-02 の確認）。商品・決済の `settings` にも入れていない

### `payment_item` → `course_purchase_payments`（一部）

`payment_item` (—) → `course_purchase_payments` ／ ローカルデータ数 336 / C ／ ステージング実測 301件

商品（講座パッケージ）。**この区分の外にも影響する表**で、コンテンツの価格（B1）と
受講権限の母集合がどちらもここを参照する。

| 旧カラム | 新カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|---|:--:|---|---|
| `(item_id, lesson_id)` | `tenant_plans` / `plan_courses` | 性質 | 中 | **商品と講座が 1:N。** 新環境にも**まとめ商品の受け皿はある**（`tenant_plans` ＋ `plan_courses`、`plan_type = course_bundle`）。買い切りも `interval_type = one_time` で表せる | **商品は `tenant_plans` に移す**（P1。**すべて `inactive`**、`provider_price_id` は `lw2-item-{id}`）。情報は落ちない。**`courses.price`（講座1本の値段）には写す元が無い**ので NULL のままにする — 埋めると lw2 に無かった単品販売を始めることになる（→ [確認事項 B2 / C3](../open-questions.md#c-新環境の制約が意図的かの確認)） |
| `item_type` | — | 性質 | 中 | 商品の種別。0 講座 / 1 チケット（都度）/ 2 チケット（月次）/ 3 ライブ（`PaymentItemController`）。受講可否判定は `item_type = 0` で絞る（`LessonModel::1814`） | **講座（0）だけを `tenant_plans` に移す**（P1）。1/2/3 は新の商品に受け皿が無いので、決済の `settings` に商品の情報を残す（P2） |
| `display_chk` / `valid_chk` / `del_chk` | `tenant_plans.settings` | カラム | 中 | 表示中か・有効か・削除済みか | `settings.legacy` に残す（削除済みは `settings.legacy.deleted = true`。`deleted_at` は入れない）。**新ではすべて `inactive`**（P1）。切り替え後も売るかは[確認事項 D7](../open-questions.md#d-cutover-の運用で決めておきたいこと) |
| `price` / `first_price` | `price` / `settings` | 性質 | 中 | **税込**（コメントの「税抜」は誤り。管理画面の JavaScript が税抜から税込を計算して入れる） | そのまま `price` に入れる |

**まとめ**: 受け皿が無い列 — （A3 の `settings`）/ 高 0 件

### `payment_application` → `payments` ほか

`payment_application` (—) → `payments` / `payment_statuses` / `payment_types` ほか ／ ローカルデータ数 634 / C ／ ステージング実測 479件

決済の申込。**クレジット・銀行振込・コンビニ・継続課金・分割払いが1表に同居**している。

| 旧カラム | 新カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|---|:--:|---|---|
| `payment_type` | `type` / `provider` | **性質** | **高** | 0 無料 / 1 カード / 2 コンビニ / 3 振込 / 4 無料クーポン / 5・6・7 チケット払い（`PaymentApplicationController:630-676`）。**継続課金と分割は支払い方法ではなく、商品のフラグで決まる**（どれもカード） | 1/2/3 だけを決済にする（P3）。種類は商品で決める（P5） |
| `payment_type = 0` | — | **性質** | **高** | **金額0のライブ予約起票が決済の大半を占める**（ETL 設計の本番実測で全 13,737件の86%。→ [db README B](../README.md#b-意味が変わって誤ったデータになるもの変換規則の取り違えが致命傷)）。素直に全件移すと決済データが実際の支払いと合わなくなる | **決済として移さない**（P3。ステージングでは無料・チケット払い 112件）。未決: それでよいか（→ 確認事項 D5） |
| 決済手段（副次列） | `payment_types` / `payment_providers` | **性質** | **高** | **1表に5種類が同居**しており、どの列の組み合わせで種別が決まるかを読み解く必要がある | `PaymentModel` / `PaymentController` を読んで確定した（上の `payment_type` の行）。**支払い済みは `application_result = 1`**（0 入金待ち / 2 エラー / 3 支払い不要）→ P6。入金待ちのまま移す申込の扱いは[確認事項 D8](../open-questions.md#d-cutover-の運用で決めておきたいこと) |
| 決済代行の識別 | `payment_providers` | カラム | 中 | lw2 は J-Payment を使っている。新の `payment_providers` は `bank_transfer` / `robotpayment` / `stripe` の3値 | **`legacy_jpayment` を足した**（A5）。J-Payment の ID（`gid` / 継続課金の `acid`）は `settings.jpayment` |
| 継続課金のカード | — | **性質** | **高** | **カード情報はプロバイダ側にあり lw2 の DB に無い。** 移しても継続課金は引き継げない | **移行の範囲外**（P9）。**J-Payment 側の継続課金は cutover で止めるか移管するかを決める**（→ 確認事項 D4）。止めないと旧の課金が続く |
| 分割払いの未完済 | `installment_plans` / `installment_charges` | 性質 | 中 | **未完済 61件・契約総額 2,907万円が cutover をまたぐ**（ETL設計の実測）。lw2 の「分割」は2種類: カード会社の分割（1回の課金。`split_payment_number`、**1 は一括**）と、自動解約つきの継続課金（分割商品）。**どちらも毎月の課金の行が無い** | `installment_plans` は作らない（P9。作ると新の催促メールのバッチが動く）。初回の申込を `subscription` として移し、回数・解約日は `settings`。残債の扱いは D4 と一緒に決める |
| `is_cancel` / `credit_payment_date` | `settings` | 性質 | 中 | **`is_cancel` は継続課金の解約で、返金ではない**（lw2 に返金の概念が無い）。`credit_payment_date` は課金を後ろ倒しにした日 | 状態は変えず `settings` に残す（P6）。入金日は lw2 の `real_payment_date` の規則で `settings.paid_at` |

**まとめ**: 受け皿が無い列 — （A4 の `settings`）/ 変換規則が要る列 7 / **高 3 件**（継続課金・無料の申込は暫定対応）

### `analytics_tag` / `trigger_media` / `payment_trigger_media` → なし

流入元計測。**移行対象外**（PDF・再判定とも X）。実測は `analytics_tag` 7件のみで、
`trigger_media` / `payment_trigger_media` は対象テナント 0件。

### `analytics_tag_display` → なし

ローカルデータ数 127 ／ ステージング実測11件（`analytics_tag` 経由）。計測タグを出す画面と位置。
**計測タグ本体と一緒に移行対象外。**

## B4 帳票

**移行ツールは実装済み**（P11〜P14）。

### `receipt_log` / `receipt_setting` → `receipts` / `receipt_settings`

ローカルデータ数 21 / 1 ／ ステージング実測 21件 / 1件（どちらも全件が対象テナント）

| 旧カラム | 新カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|---|:--:|---|---|
| 発行済み領収書 | `receipts` | 性質 | 中 | **決済に紐づく。** B3 が先に入っていないと 1 行も入らない。**旧はダウンロードのたびに1行**（再発行も1行）で、印字する番号は `receipt_log_id` | 決済の後に流す。`issue_no` は決済ごとに 1..n、旧の番号は `receipt_log_id`（A7）。取引日は入金日（P11）。再発行で番号が変わってよいかは[確認事項 D9](../open-questions.md#d-cutover-の運用で決めておきたいこと) |
| 発行設定 | `receipt_settings` | 型 | 低 | 実測1件 | そのまま移す。インボイスの有無は `tenants.settings.lw2_payment` |

**まとめ**: 受け皿が無い列 — / 高 0 件

### `tax` → `receipt_settings.tax_rate`

`tax` (—) → `receipt_settings.tax_rate` ／ ローカルデータ数 1 / C

| 旧カラム | 新カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|---|:--:|---|---|
| テーブル全体 | `tax_rate` 1列 | 性質 | 中 | **`tenant_id` を持たない全体設定**で、新はテナントごとの1列。**期間別の税率を持てない** | **`tax` 表は設定画面の選択肢で、取引の税計算に使っていない**（`SelectListModel`）。移さない（P14）。税率は `receipt_setting.tax_rate` → `receipt_settings.tax_rate`、発行時の税率は `receipts.tax_rate` |

**まとめ**: 受け皿が無い列 1 / 高 0 件

### `agreement` / `cancel_policy` / `privacy_policy` / `tokusyo` → `consent_kinds` / `user_consents`

ローカルデータ数 4 / 2 / 2 / 2 ／ ステージング実測 2 / 1 / 1 / 1件

| 旧カラム | 新カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|---|:--:|---|---|
| 本文 | `tenant_legal_documents.body` | **性質** | **高** | **規約の本文を置く先が無かった。** `user_consents` は「誰がいつ何に同意したか」の記録で、**同意した文書そのものは持たない**。新の画面は文面を固定で持つ | `tenant_legal_documents` を足して移す（A8 / P12。**本文が空で、外部 URL の上書きも無いものは移さない**。ステージングは利用規約の ja / en だけ）。**アプリはまだ読まない**（→ 確認事項 D6） |
| 同意の記録 | `user_consents` | 性質 | 中 | **lw2 は同意を記録していない**（購入画面のチェックを確かめるだけ） | 移すものが無い |
| 版・改定日 | — | 性質 | 低 | **lw2 は版を持たない**（テナント × 言語に1行を上書き保存） | 移すものが無い |

**まとめ**: 受け皿が無い列 — （A8）/ **高 1 件**（アプリがまだ読まない）

## 新環境に追加するテーブル・カラム

> **migration に落とした形は [マイグレーション対象](schema-additions.md)。**
> **school-launcher の `20260928132756_lw2_billing_additions.sql`**（ブランチ `feat/lw2-billing-schema`）に A1〜A8 をまとめてある。

| # | 追加するもの | 旧環境の対応 | 変更が必要な機能 |
|---|---|---|---|
| **A1** | `ticket_types.ticket_id` / `legacy_ticket_type` ＋ UNIQUE `uk_tt_legacy`、`ticket_grants.starts_at` | `ticket.ticket_id` / `ticket_type` / `user_ticket.ticket_start_date` | ・**`user_ticket_log.ticket_type` が参照しているのは `legacy_ticket_type`**（`ticket_id` ではない）。履歴を移さなくても**あとで人が突き合わせられる**ようにする<br>・`starts_at` は実測全件 NULL |
| **A2** | `monthly_ticket_allowances`（月次のチケット配布） | `month_user_ticket`（実測1件） | ・「毎月◯枚まで」の契約と消化の判定<br>・`target_month` は `'YYYYMM'` の**書式を変えずに移す**<br>・`application_id` を決済に結ぶのは未実装 |
| **A3** | `tenant_plans.item_id` ＋ UNIQUE、`settings` JSON | `payment_item`（講座の商品） | ・**すべて `inactive`**。新で売るには Stripe の価格を作り直す<br>・試用・受講期間・自動解約・支払日は `settings` にあるだけで、**新の購入処理は読まない** |
| **A4** | `payments.application_id` ＋ UNIQUE、`settings` JSON | `payment_application` | ・決済一覧・売上に移した決済が出る（`platform_fee = 0`）<br>・解約・分割回数・J-Payment の ID は `settings` にあるだけ |
| **A5** | `payment_providers` に `legacy_jpayment` | J-Payment | ・**新の決済処理は扱わない。** 返金ボタンを押しても決済代行に届かない（運用で止める） |
| **A6** | `payment_types` に `lw2_purchase` | 講座が1つに決まらない購入 | ・一覧では講座が空欄になる（`course_purchase_payments` が無い） |
| **A7** | `receipts.receipt_log_id` ＋ UNIQUE | `receipt_log.receipt_log_id` | ・旧で印字していた番号。新は決済ごとの連番（`issue_no`）で番号の付け方が違う |
| **A8** | `tenant_legal_documents` | `agreement` / `cancel_policy` / `privacy_policy` / `tokusyo` | ・**アプリはまだ読まない。** テナントごとの規約を見せるなら画面の改修が要る（→ 確認事項 D6） |

### 移行の対象外（移行できないもの / 移行しないもの）

#### A. 移行できないもの

| 対象 | なぜ移行できないか |
|---|---|
| `user_ticket` のうち種別が無い残高（実測3件） | `ticket_grants.ticket_type_id` の NOT NULL に当たる（→ [#14](../constraint-violations.md)） |
| `user_ticket` のうち `ticket_num = 0` の残高（実測2件） | `ticket_grants` の CHECK `chk_tg_qty (quantity >= 1)` に当たる。**制約を緩めるかは運営の判断**（→ [#15](../constraint-violations.md)）。**CHECK は事前検査でも見る** — 見ていなかった頃は dry-run を通って実 INSERT で落ちた |
| 上の残高で予約したライブの消費（実測で予約9件。すべて `ticket_num = 0` の残高（#15）のもの。会員 3181 の種別 2） | 戻し先の付与が移らないので台帳（`ticket_ledger_entries.grant_id` NOT NULL）に書けない。**キャンセルしてもチケットが戻らない** |

#### B. 方針として移行しないもの

| 対象 | 理由 |
|---|---|
| `user_ticket_log`（消費履歴） | **キャンセルに要るのは「誰が予約したか」と「何枚使うか」だけ**で、履歴そのものは要らない（運営の判断）。**台帳（`ticket_ledger_entries`）の行は移行時に予約から組み立てて入れる**。**欠席（`no_show`）も席を占有する**ので消費済みとして数える — 除くと台帳が0行になる |

---

## 投入順序（この区分の実行計画）

**コンテンツ（2）が先。** `ticket_type_lessons` と `live_lesson_ticket_requirements` が
コンテンツで作るライブの `lessons` を参照する。

```
[migration]  A1〜A8（20260928132756_lw2_billing_additions.sql）
             ＋ 20260927105511 / 20260930044959 / 20261001085757（自動割当の表・列、削除済みの対応、予約できる商品の全行）
                ↓
[billing.1]  ticket_types → ticket_type_lessons → live_lesson_ticket_requirements
             → ticket_grants → ticket_ledger_entries → monthly_ticket_allowances
                ↓
[billing.2]  tenant_plans → plan_courses → payments → course_purchase_payments / subscription_payments
             → live_lesson_limit_item_history
[billing.3]  receipt_settings → receipts → tenant_legal_documents
[billing.4]  tag_auto_assign_rules → tag_auto_assign_rule_triggers → tag_auto_assign_rule_conditions
             → tag_auto_assign_rule_group_conditions → tag_auto_assign_rule_grants → tag_auto_assign_logs
```

> **台帳は受講（3）のライブ予約を参照する。** 予約は `enrollment.6` で入るので、
> 課金は受講の後に流す（区分の順どおり）。
