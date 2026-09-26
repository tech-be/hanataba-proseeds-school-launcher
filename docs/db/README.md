# DB ドキュメント

旧環境 **learningware-kiracari (lw2)** から新環境 **school-launcher** へのデータ移行を設計するための資料一式。

> **実装の手順は [移行ツール仕様書](../migration-spec.md)。** 本ディレクトリは**旧⇔新の突き合わせ（何をどう移すかの根拠）**で、仕様書はそれを登録順と処理仕様に落としたもの。

## 構成の規約

**1区分 = 1ディレクトリ**とし、その中に**「テーブルの内訳」「突き合わせ」「移行仕様」を3点セットで置く**。

| ファイル | 役割 |
|---|---|
| `NN-<区分>/breakdown.md` | **テーブルの内訳**。その区分のテーブルを持ち主・役割で中分類し、旧⇔新を並べた一覧 |
| `NN-<区分>/review.md` | **突き合わせ**。内訳の中分類を単位に、テーブル・カラム・型・データの性質の4観点で移行可否を検証したもの |
| `NN-<区分>/migration-spec.md` | **移行仕様**。突き合わせの結論を実装の手順に落としたもの。登録前の確認事項（運営判断）／登録順／移行仕様 |
| `NN-<区分>/schema-additions.md` | **マイグレーション対象**（**新環境に足すものがある区分だけ**）。DDL を当てる順序・旧列との対応・ロールバックの注意つきで並べたもの |

> **3つの役割分担。** 内訳は「何があるか」、突き合わせは「何が問題でどう直すか」、移行仕様は「どの順で、どう流すか」。**区分をまたぐ共通規則**（抽出の絞り込み / ULID / 日時 / 文字コード / 冪等性）は [移行ツール仕様書（共通）](../migration-spec.md) に置き、区分の仕様には**その区分固有のことだけ**を書く。

**`review.md` の findings の表は `| 旧カラム | 新カラム | 観点 | 深刻度 | 内容 | 修正方法 |`**（旧のみの形は新カラム列なし）。「内容」は**問題点だけ**、「修正方法」は**どう直すかだけ**を書き、同じことを二度書かない。修正方法は動詞で始める。**まだ決まっていないものは `未決:` で始める** — その件数がそのまま実装前に閉じるべき論点の数になる。

> **移行の原則は [ひな形](00-template/review.md#移行の原則) にまとめてある。** 要点は4つ。
>
> 1. **対象外（未コミット）に区分されたデータ以外はすべて移行する。** 新環境にその機能が無いことは移行しない理由にならない（データは移し、機能は別途用意する）
> 2. **テーブル・カラムが足りなければ追加する。** 追加案 / 旧環境の対応 / 変更が必要な機能の3点をセットで書く
> 3. **元の構造を維持する。** 複数列を1列に畳む・列を削る・粒度を変えるのは、いずれも情報が落ちるので勝手にやらない
> 4. **新環境の構造に寄せる場合は確認する。** 合わせる理由と、それで表現できなくなるものを書いたうえで合意を取る
>
> 「移行しない」と書けるのは**移すこと自体が不適切なもの**だけで（平文の認証情報 / 発行中のトークン・コード / UI の一時状態 / 都度計算できる集計）、その場合は**「移行できないもの」か「方針として移行しないもの」かを分け、理由を明記する**。01 基盤の [新環境に追加するテーブル・カラム](01-foundation/review.md#新環境に追加するテーブルカラム) が書き方の例。

**`review.md` の `###` 見出しは `breakdown.md` の対応表の行と1対1**にする。内訳の行1つにつき突き合わせの見出しを1つ置き、**順序も揃える**。対応先が無い行は `### \`site\` → なし` / `### なし → \`tenant_statuses\`` と書く。指摘が1件も無いときだけ「問題なし」と書ける（「低」だけでも指摘があれば表に残す）。

内訳を先に作り、その中分類を見出しにして突き合わせを書く。**片方だけを更新しない** — テーブルの割り当てを変えたら両方を直す。

ひな形は [00-template/](00-template/breakdown.md)（[breakdown.md](00-template/breakdown.md) / [review.md](00-template/review.md) / [migration-spec.md](00-template/migration-spec.md) / [schema-additions.md](00-template/schema-additions.md)）。**ディレクトリごとコピーして使う。**

> **集計する側の注意。** `00-template` は区分ではないので、区分一覧にも件数の集計にも含めない（`docs/db/0[1-8]-*/` で絞る）。またひな形の記入例は**コードフェンスの中**にあるので、行を数えるときは**フェンス内を読み飛ばす**こと。

### 区分をまたぐ資料（このディレクトリ直下）

| ファイル | 内容 |
|---|---|
| [data-type-mapping.md](data-type-mapping.md) | PDF の 8区分 / 95データ種 × 旧テーブル × 新テーブルの対照表 |
| [legacy-table-coverage.md](legacy-table-coverage.md) | 旧 lw2 全342テーブルの逆引き |
| [new-table-coverage.md](new-table-coverage.md) | 新 school-launcher 全256テーブルの逆引き |
| [data-type-findings.md](data-type-findings.md) | PDF との差分・資料間の矛盾・要確認事項 |

## 共通の列の意味

内訳 (`breakdown.md`) と 旧環境逆引き (`legacy-table-coverage.md`) が共通で持つ2列。どちらも `school-launcher/docs/lw2-migration-tables.md`（2026-07-28 取得のダンプの実測）から取り込んでいる。

### ローカルデータ数

そのテーブルに入っているレコード数。ダンプ（`lw2_kiracari20260728.sql.gz`、展開 8.17 GB）の **INSERT 文を実カウントした値**で、インデックス分は含まない。全335テーブルで 34,174,269 行。

**2点の注意がある。**

- **全73テナントの合計値であって recademy 単体ではない。** lw2 は同一 DB に73テナントが同居しているため、移行対象の `tenant_id = 12` だけに絞ると大幅に減る。`scrun-etl-design.md` 付録A の実測補正では、アンケート回答が 64,883 → **2,464**（26分の1）、教材添付が 6,250 → **3**（2,083分の1）だった。**規模感の参考値としてのみ使い、移行ツールの処理件数見積もりには使わないこと**（[data-type-findings.md](data-type-findings.md) §5）
- **`-` は実測値が無いもの。** 2026-07-28 のダンプ以降に追加された7テーブル（`config_cookie` / `hosting_capacity` / `lecture_path_test` / `portfolio_category` / `portfolio_like` / `user_cookie_log` / `user_login_chk_log`）が該当する

### A·B·C

棚卸しの作成者が付けた**移行可否の3区分**。

| 区分 | 意味 | テーブル数 | ローカルデータ数 |
|---|---|---:|---:|
| **A** | 純ログ。移行対象外 | 19 | 6,910,824 |
| **B** | 要判断（証跡・一時・集計） | 37 | 2,210,950 |
| **C** | 移行対象 | 279 | 25,052,495 |

**データ種の分類とは別の軸**だが、**A（純ログ）は移行しない**方針が決まったため、いまは移行対象の線引きとしても使う。両者が食い違う箇所は洗い出してあり、**A とされている7テーブルに新環境の受け皿が存在する**が、**受け皿があっても移さず空で始める**（`user_login_log` → `login_history` など。[data-type-findings.md](data-type-findings.md) §6）。

A/B/C の判定そのものは棚卸し作成者の見解で機械的な基準ではない。同じ資料に「`user_learning_unit_log` は名前が `_log` だが学習実績の本体なので A に落とさないこと」という注意書きがあり、**名前では判断できない**旨が明記されている。

> **「純ログだから移行しない」と書くときは、名前ではなく中身で判断する。** 基盤では `user_login_chk_log`（ログイン有効期間の変更履歴）が該当し、**`_log` という名前だが移行する**。

## 区分ごとのセット

> **運営に確認したいことは [open-questions.md](open-questions.md) に1枚でまとめてある。** 各区分の `migration-spec.md` の 1-1 から、**回答が要るものだけ**を抜き出したもの（QA表への転記用）。
>
> **制約に当たって移らなかった行は [constraint-violations.md](constraint-violations.md)。** NOT NULL / UNIQUE / CHECK ごとに、何が当たっているかを `out/not-migrated.csv` から集計したもの（移行担当用）。

| 区分 | 内訳 | 突き合わせ | 移行仕様 | 項目 |
|---|---|---|---|---|
| 01 基盤 | [breakdown](01-foundation/breakdown.md) | [review](01-foundation/review.md) | [spec](01-foundation/migration-spec.md) | マスター / ユーザ |
| 02 コンテンツ | [breakdown](02-content/breakdown.md) | [review](02-content/review.md) | [spec](02-content/migration-spec.md) | オンデマンド講座 / テスト定義・課題定義 / アンケート定義 / ライブ講座 |
| 03 受講 | [breakdown](03-enrollment/breakdown.md) | [review](03-enrollment/review.md) | [spec](03-enrollment/migration-spec.md) | 受講権限 / 学習履歴 / テスト結果 / 課題提出 / アンケート回答 / ライブ予約 / 修了証・バッジ |
| 04 課金 | [breakdown](04-billing/breakdown.md) | [review](04-billing/review.md) | [spec](04-billing/migration-spec.md) | チケット / 決済 / 帳票 |
| 05 サポート機能 | [breakdown](05-support/breakdown.md) | [review](05-support/review.md) | [spec](05-support/migration-spec.md) | LINE / クーポン / お知らせ / 問い合わせ / ファイル / 就業支援 / コミュニティ |
| 06 対象外 | [breakdown](06-out-of-scope/breakdown.md) | [review](06-out-of-scope/review.md) | **不要** | 移行しない |

> **区分は移行計画の5グループ。** `既存機能と新システムの保有.docx.pdf` の8区分は
> **データ種の分類軸**として [data-type-mapping.md](data-type-mapping.md) に残してあり、
> **移行の実行単位とは別**（PDF の「ライブ」は、いまはコンテンツ・受講・課金に分かれている）。

> **「未決」は修正方法が `未決:` で始まる件数**で、実装前に運営確認や実データ調査で閉じるべき論点の数。`—` は修正方法の列をまだ持っていない区分。
>
> **01 基盤の未決は 18 → 0。** 減ったのは方針が変わったため（ 「受け皿が無いものは追加して受ける」を既定にしたことで、「機能の要否を運営と決める」形の未決14件が**追加案（A1〜A19）と、それに伴う機能変更の作業**に置き換わった。

> **内訳と突き合わせがそろっているのは 01 基盤と 02 オンデマンドの2区分。** 残り6区分の `breakdown.md` は未作成で、**突き合わせもデータ種（◯のみ）を軸にしたまま**（`修正方法` の列を持たない）。内訳を作るときに揃え直すこと。

## 突き合わせの4つの観点

| 観点 | 問い | 見たもの |
|---|---|---|
| **テーブル** | 対応するテーブルがあるか | 受け皿の有無、1:N / N:1 / 分解・統合の構造変化、NOT NULL な FK の相手が旧に無いケース |
| **カラム** | 対応するカラムがあるか | 旧カラムの行き先、新の NOT NULL 列に入れる値が旧に無いケース |
| **型** | 型に問題がないか | 桁溢れ、NULL可否、既定値、日時型、文字コード、UNIQUE / CHECK 違反 |
| **性質** | データの性質が変わっていないか | フラグの意味、コード値の対応、粒度、タイムゾーン、ソフトデリート、ポリモーフィック |

**深刻度**: 高 = データが落ちる・制約違反で投入できない・意味が変わって誤データになる ／ 中 = 変換規則を決める必要がある ／ 低 = 受け皿の追加だけで済み、判断がほとんど要らない。

> **[移行の原則](00-template/review.md#移行の原則)を入れたので、「受け皿が無い」こと自体は深刻度を上げない。** 追加すれば済むものは「低」、**追加のしかたに判断が要るもの**（構造をどう持つか、極性や粒度が変わる、NOT NULL に入れる値が無い）が「中」以上になる。

### 観点 × 深刻度

| 観点 | 高 | 中 | 低 | 計 |
|---|---:|---:|---:|---:|
| テーブル | 34 | 28 | 14 | 76 |
| カラム | 22 | 77 | 71 | 170 |
| 型 | 8 | 26 | 16 | 50 |
| 性質 | 47 | 93 | 23 | 163 |
| **合計** | **111** | **224** | **124** | **459** |

> **01 基盤と 02 オンデマンドは軸が違う。** 他の6区分はデータ種（◯のみ）を軸にしているが、この2区分は内訳の対応表と1対1で、**X 判定のデータ種も含む全テーブル**を見ている（基盤41ペア / オンデマンド54ペア）。

**件数は各 `review.md` から機械的に数え直した値**（`観点` と `深刻度` の列を持つ行）。**「性質」が高の43件と最多**で、次が「テーブル」の33件。**型の不一致より、構造と意味のずれの方がはるかに多い。** つまりこの移行の難所はデータ変換ではなく、**lw2 の機能概念を btoc の概念に翻訳する判断**にある。

---

## 全区分に共通する横断的な問題

実装に入る前に、ツール全体の方針として決めておくべきもの。

### 1. 日時型が3種類混在し、列ごとに扱いが変わる

旧は **584列すべて `datetime`**（JST naive）。新は **`timestamp` 397 / `datetime(3)` 174 / `datetime` 26 / `timestamp(3)` 2**。

- **`timestamp` 列はセッションTZで UTC に変換されて格納される**。JST naive の値をそのまま書くと保存値がずれる
- **`datetime(3)` 列は変換されない**。UTC に直した値を明示的に書く必要がある
- **同じテーブル内で混在している**例がある。`announcements` は `publish_start_at` が `datetime(3)`、`created_at` が `timestamp`。`live_lesson_occurrences` は全列 `datetime(3)` なのに `live_lessons.scheduled_at` は `timestamp`

→ **列ごとに型を引いて変換を分岐する仕組みを ETL の基盤に入れること。** テーブル単位で決め打ちすると必ず事故る。

### 2. `date` → `timestamp` / `datetime` で1日ずれる

`authority_start_date`・`interview_date`・`reserve_start_day` などの `date` 列が新では日時型になる。**JST の 00:00 を UTC に直すと前日 15:00** になるため、日付境界で1日ずれる。日付の意味（開始日か終了日か）に応じて 00:00:00 / 23:59:59 のどちらを補うかを決めること。

### 3. ID の再採番と、旧IDを引き継げないテーブル

旧 `int(11)` auto_increment → 新 `char(26)` ULID（**26文字の Crockford Base32。先頭10文字が生成時刻 48bit、残り16文字がランダム部 80bit**）。決定論 ULID（ETL設計 §3-1）で採番するが、**`access_log` と `test_sub_question` は採番が枯渇・履歴断裂しており旧 ID を外部キーとして引き継げない**（`lw2-migration-tables.md`）。

> **新環境の実装に決定論 ULID は無い。** `btoc-backend` の ID 生成は306か所すべて `ulid.Make()`（時刻＋乱数）で、旧 ID から ULID を逆算する前提のコードは存在しない。決定論 ULID は**移行ツール側の冪等性のための方式**であって、**新環境が既に作った行と突き合わせる用途には使えない**（相手がランダムなので一致しない）。突き合わせは業務キー（`tenants.slug`、`external_user_links.external_id`）で行う（[基盤](01-foundation/review.md#tenant--tenants)）。

### 4. 文字コード

旧 `utf8`(utf8mb3) / `utf8_unicode_ci` → 新 `utf8mb4` / `utf8mb4_unicode_ci`。拡大方向なので基本は安全だが、**`test` テーブルのカラムコメントが文字化けしている**（cp932 で書かれた定義が utf8 として取り込まれた跡）。`docs/local-setup.md` も「差分SQLに cp932 のファイルがある」と記録している。**実データにも cp932 混入の可能性があるため、抽出時に文字コード検証を入れること。**

### 5. テナントの絞り込み

旧は**同一 DB に 73 テナントが同居**し、移行対象は `tenant_id = 12` (recademy) のみ。**`enquete_answer` のように `tenant_id` 列を持たないテーブルがある**ので、親テーブルと join して絞る必要がある。棚卸しの数値が最大 2,083 倍ずれていたのはこの join を落としたことが原因（ETL設計 付録A）。

### 6. ソフトデリートの扱いが統一されていない

旧は `del_chk` / `valid_chk` の2系統。新は `status` マスタだが、**`content_statuses` に `deleted` が無い**（`draft`/`published`/`archived`）、**`tenant_statuses` にも無い**（`trial`/`active`/`suspended`）など、受け皿がない箇所がある。`users` だけが `deleted` を持つ。**「削除済みの行は移行しない」を既定にし、例外を明示する方針が要る。**

> **`tenant_statuses` には `deleted` を追加する方針で決着**（新環境側の migration + `internal/domain/tenant.go` + フロントの型。[基盤](01-foundation/review.md#なし--tenant_statuses)）。recademy は `active` なので移行ツールの動作には影響しない。

### 7. 極性が反転する設定

「受け取る」→「optout（受け取らない）」、「削除フラグ」→「有効フラグ」など、**真偽が逆になる変換が複数ある**（B06 の `sendmail_*_chk` → `notification_optouts`、U07 の `mail_setting_*`、O02 の `del_chk` → `active`）。取り違えると通知が真逆に出る。

### 8. 新環境は migration のシード値だけの状態から始まる

**新環境に存在するのはシードで入るマスタ値だけで、業務データは1行も無い。** テナント行も無いので、**`tenants` の1行を作るところが移行の起点**になる（[基盤](01-foundation/review.md#tenant--tenants)）。

- **`tenants.id` は移行側で採番する。** この1値が全テーブルの `tenant_id` になるため、**採番を1か所に閉じ、決めた値を設定値として配る**こと。ツールごとに決定論 ULID を計算し直す作りだと、入力が1か所ずれただけでテナントが二重にできる
- **NOT NULL 列とその FK 先は「シードがあるか」で投入可否が決まる。** `tenants` で NOT NULL なのは `slug` / `name` / `db_type` / `status` の4列だけで、FK 先の `tenant_db_types` / `tenant_statuses` は migration がシードまで持っている。**`plan_id` は NULL 可**で、FK 先の `platform_plans` に行を入れるのはデモ用の `cmd/seed` だけなので、移行先では `NULL` を入れる
- **「新側に既にあるから移行不要」という判断は成り立たない。** 受け皿があるものはすべて移行側が作る
- **受け皿が無い列・テーブルは新環境に追加して受ける**（01 基盤で [A1〜A21](01-foundation/review.md#新環境に追加するテーブルカラム)）。**複数列を1列に畳むのも「落とす」と同じ**として扱う（`tel` / `mobile_tel` を `phone` 1列にする、`valid_chk` / `del_chk` を `status` に畳む、など）。ただし**追加するだけでは機能しない** — 構造体 / repository / DTO / フロントの型と画面までを1セットで直す必要があり、**移行ツールの外側の作業**になる

---

## 深刻度「高」106件の内訳

対応の性質で3つに分かれる。**上から順に着手すること。**

### A. 投入そのものが止まるもended（先に決めないと1行も入らない）

| 区分 | データ種 | 内容 |
|---|---|---|
| オンデマンド | O01 講座 | `courses.instructor_id` **NOT NULL** に入れる講師が lw2 に無い。運営から既定講師の CSV が要る |
| オンデマンド | O01 講座 | `courses.category` の FK 先 `course_categories` に**固定シードが無い**。ETL の L0 に「lesson_cate から course_categories を作る」段が欠けている |
| 課金 | K02 決済 | `payment_providers` に `legacy_jpayment` が無い。L0 に migration が要る |
| 課金 | K10 クーポン | `coupons.provider_coupon_id` / `provider_promotion_id` が **NOT NULL**。Stripe 前提のため lw2 のクーポンを入れられない（3案が未決） |
| ライブ | L01 ライブ定義 | lw2 のライブは講座に属さないため、受け皿の course を新規に作る必要がある（案A/案B が未決） |
| 就職支援 | S01 求人 | `job_postings.company_id` **NOT NULL** / `employment_type` **enum NOT NULL** に入れる値が lw2 に無い |
| 就職支援 | S02 企業 | `companies.industry` / `contact_email` が **NOT NULL** で旧に対応列が無い |
| 就職支援 | S06 面談 | `interview_records` を入れるには `interviews` → `availability_slots` → `advisors` を先に作る必要があり、そのデータが lw2 に無い |
| 運営 | U08 問い合わせ | `inquiry_categories` は固定マスタ。lw2 カテゴリとの対応表 CSV が無いと FK 違反 |
| 運営 | U07 メールテンプレート | `email_kinds` に無い種別のテンプレートは移行先が無い |
| 基盤 | B03 メールログイン | `UNIQUE (tenant_id, email)` にメール欠損174名・重複23アドレス/56名が当たる |
| オンデマンド | O27 バッジ | **付与行の移行元テーブルが lw2 の342テーブルに存在しない。** 移行元が特定できるまで着手できない |

### B. 意味が変わって誤ったデータになるもの（変換規則の取り違えが致命傷）

| 区分 | データ種 | 内容 |
|---|---|---|
| 受講 | J01 受講権限 | **`cancel_chk` は返金ではなく「自動延長の解約」**。97%に立っているので `refunded` に写すと全員返金済みになる |
| ライブ | L03 予約 | **`stop_chk` は開催側の中止**。予約の status に入れると受講者都合のキャンセルとして記録される |
| ライブ | L02 開催日 | **`del_chk`（削除）を `canceled_at`（中止）に写すと受講者に「中止」として見える** |
| 課金 | K02 決済 | **`payment_type=0`（金額0のライブ予約起票）が全13,737件の86%**。素直に全件移すと決済データが壊滅的に汚れる |
| オンデマンド | O01 講座 | `open_period` は**月**、`access_days` は**日**。単位変換を忘れると受講期間が 1/30 になる |
| オンデマンド | O09 テスト受験 | `test_score` / `sum_score` / `total_score` の3列のどれを使うかで点数が壊れる |
| 運営 | U02 既読 | `news_user` は**配信対象者**の行で未読も含む。全件入れると全員既読になる |
| ライブ | L04 リマインド | `reminded_at` を埋めないと **cutover 直後に過去分のリマインドが再送される** |
| 基盤 | B06 会員プロフィール | `external_user_links.external_system` の値が資料間で `lw2` と `kiracari` に割れている。**UNIQUE 違反 or 会員の二重登録**になる |
| 課金 | K09 消費税 | 期間別の税率を持てない。**過去の8%期間の決済を再計算すると10%になる** |

### C. 新環境に受け皿が無いもの（追加して受ける）

**「落ちる」ではなく「新環境に追加して受ける」対象。** 主なものだけ挙げる。詳細は各区分のファイルを参照。01 基盤は [A1〜A21](01-foundation/review.md#新環境に追加するテーブルカラム)、02 コンテンツは [A1〜A27](02-content/review.md#新環境に追加するテーブルカラム)、03 受講は [A1〜A7](03-enrollment/review.md#新環境に追加するテーブルカラム)、04 課金は [A1〜A2](04-billing/review.md#新環境に追加するテーブルカラム)、05 サポート機能は [A1](05-support/review.md#新環境に追加するテーブルカラム) に書き出してある。**A 番号は区分ごとの通し番号**で、区分をまたぐときは「基盤 A10」のように区分名を添える。

| 区分 | 落ちるもの |
|---|---|
| 基盤 | **講師の担当範囲**（講座/グループ/属性の3テーブル）、**フリガナ**、**住所2組**、**カスタムプロフィール20項目**、ログイン失敗ログ（`user_id` NOT NULL のため）、曜日・時間帯のログイン制限 |
| オンデマンド | **テストの出題条件（カテゴリ×レベルからN問）**、**問題・選択肢・解説の画像（22列）**、**問題バンクの共有**、テストの表示制御6種、**動画のスキップ防止・修了設定**、絶対日時でのユニット公開、**課題の配布ファイル5本**、アンケート回答の47%（entity_type 1/3） |
| ライブ | 1人あたりの予約上限、出席認証キー、月次チケット配布、**チケット消費履歴（`grant_id` を決められないため再生不能）** |
| 受講 | **進捗状態（学習中/未着手の区別）**、ユニットごとの得点、SCORM 中断データ、`user_learning_unit_log`（2,929,224行 / 780MB）、**割当ルールの定義そのもの** |
| 課金 | **商品という概念**、申込フォームの取得項目設定、商品ごとの支払手段許可、**決済の税額・税抜額・税率**（領収書233件以外）、コンビニ決済の受付情報5列、**規約本文** |
| 運営 | お知らせ添付296ファイル、**問い合わせ添付706ファイル**（L9 最大の塊）、催促メール設定、**フォローメールの条件24列**、掲示板の公開範囲5軸 |
| 就職支援 | **求人への応募記録**、企業ページの訴求コンテンツ9列、構造化された職務経歴、**面談項目20列** |

---

## ETL 設計（`scrun-etl-design.md`）との関係

本レビューは ETL 設計 §5 を検証した結果を含む。**食い違い・抜けとして見つかったもの**:

| 内容 | 箇所 |
|---|---|
| **`tenants` の行作成に段の割当が無い** | §4。新環境はシード値のみでテナント行が無く、**この1行が入らないと FK を持つ子テーブルは1行も入らない**。L0 に要追加 |
| **決定論 ULID は新環境の実装に無い** | §3-1。`btoc-backend` は全件 `ulid.Make()`。移行ツール内の冪等性には使えるが、既存行との突き合わせには使えない |
| **`course_categories` への行作成が L0 に無い** | §4 / §5-2。`courses.category` は FK なので先に作らないと入らない |
| **`external_system` の値が `lw2` と `kiracari` で割れている** | §3-2 / §5-1 と、`external_user_links` の列コメント・`external_user_link_repo_integration_test.go:14` |
| **`user_learning_unit` から見出しブロック（type=0）の行を除外する記述が無い** | §5-0 は unit 側の除外しか書いていない。進捗側を除外しないと FK 違反 |
| **継続課金（K05）に段の割当が無い** | §4。`kiracari-migration-estimate.md` が最大リスクとしている項目 |
| `test_score` / `sum_score` / `total_score` の取り違えの恐れ | §5-4 |
| ETL段の割当が無いが受け皿はあるデータ種 18件 | [差分・要確認事項](data-type-findings.md) §7 |

---

## 実データが無いと判断できないこと

`recademy` の**本番**ダンプはローカルに無いため、**スキーマとドキュメントからの判定に限っている**。ダンプ受領後に必ず確認すること。

> **ただし lw2 リポジトリに `docker/docker-entrypoint-initdb.d/database/lw2.sql`（36MB、スキーマ + データ）が同梱されており、`tenant_id=12` の行も入っている。** プロフィール項目の設定（[基盤 M4](01-foundation/review.md#m4-会員項目状態の定義)）はここから読み取った。**タイムスタンプは 2019-08-28 で本番の最新状態ではない**ので、構造と設定の当たりを付ける用途に限り、件数の根拠には使わないこと。

| 確認すること | なぜ |
|---|---|
| `live_lesson_date.capacity = 0` の行の有無 | CHECK `capacity IS NULL OR capacity >= 1` に当たる |
| `split_payment_number = 0` / `seq_no = 0` / `discount_value <= 0` の行の有無 | 各 CHECK 制約に当たる |
| `user_ticket.ticket_id IS NULL` の行の有無 | `ticket_grants.ticket_type_id` は NOT NULL |
| `news_title` / `recruit_title` に500文字超・255文字超があるか | varchar への切り捨て |
| `enquete_question.question_text` に500文字超があるか | 同上 |
| `user.tel` / `mobile_tel` に32文字超があるか | varchar(32) への切り捨て |
| `user.line_id` の実際の長さ | varchar(64) への切り捨て |
| `tenant` の recademy 行の `tenant_name` / `tenant_code` / `language_code` / `del_chk` の実値 | **新環境はシード値のみでテナント行が無く、この4列がそのまま投入値になる。** `tenants.name` は NOT NULL なので、`tenant_name` が NULL だと投入できない（[基盤](01-foundation/review.md#tenant--tenants)） |
| `lesson_cate_name` に50文字超があるか | `course_categories.code` varchar(50) |
| `coupon_name` に100文字超があるか | `coupons.name` varchar(100) |
| `test.unit_id` に複数テストがぶら下がるユニットの有無 | `quizzes` の UNIQUE (tenant_id, lesson_id) |
| `unit.enquete_id` が同じアンケートを複数ユニットで参照しているか | `survey_lessons.lesson_id` が PK |
| `lecture` が複数ぶら下がる `unit` の有無 | `video_lessons.lesson_id` が PK（実測では最大1） |
| `user_learning_test_sub.question_answer` の格納形式 | 選択式の回答をどう復元するか |
| `test.exam_limit_times` の単位（分か秒か） | `time_limit_sec` との換算 |
| `user_personal_no.personal_no` の用途（会員に見せる番号か、スカウト時の匿名IDか） | 会員の一意 ID と確認済み。**移行先を作るかの判断に要る** |
| 実データへの cp932 混入 | 文字コード検証 |
| `ex_training`（外部研修）の利用件数 | 対象外にしてよいかの判断 |
| `payment_item.price` と `excluding_tax_price` のどちらが正か | 列コメントが両方「税抜」で重複している |
