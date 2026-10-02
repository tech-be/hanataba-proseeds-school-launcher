# 基盤 — 突き合わせ

[基盤の内訳](breakdown.md) の対応表と **1対1で対応**する。内訳の41行それぞれに `###` 見出しが1つあり、**順序も内訳と同じ**。ひな形は [00-template/review.md](../00-template/review.md)。

- 観点（テーブル / カラム / 型 / 性質）と深刻度（高 / 中 / 低）の定義は [README.md](../README.md#突き合わせの4つの観点) を参照
- **「内容」は何が起きるか、「修正方法」はどう直すか。** 修正方法が `未決:` で始まるものは**実装前に閉じるべき論点**
- ローカルデータ数と A·B·C の定義は [README.md](../README.md#共通の列の意味) を参照

## この区分の要点

- **移行ツールが書き込むのは 24 テーブル**（`migrator/phases/registry.py` の `foundation.1` マスター / `foundation.2` ユーザ。LINE の `line_links` は `support.1` で入れるので数えていない）。ETL設計 §4 は `users` / `login_history` / `user_preferences` の3つしか想定していないが、**受け皿が無いものは追加して受ける**方針のため対象が広い。スキーマ追加（A1〜A24）は school-launcher 側の migration で入れる（[マイグレーション対象](schema-additions.md)）
- **NOT NULL / UNIQUE / 外部キーに当たる行は移さない。** 移行ツールは値を作り替えず、`out/not-migrated.csv` に「誰が・なぜ」を出すだけ。直すのは**移行の外の暫定対応**（`fixups`）で、そのあと再実行すれば入る（[移行仕様 3.3](migration-spec.md#33-投入load)）
- **調査時点では旧32件のうち新側に受け皿があるのは 4件**（`tenant` / `role_master` / `user` / `user_login_log`）だった。**いまは追加した受け皿で受けており**、受け皿を持たないのは移行の対象外と、[現状は移していないもの](#現状は移していないもの実装が無い)だけ
- **[移行の原則](../00-template/review.md#移行の原則)に従う。** 対象外区分のデータ以外はすべて移行し、受け皿が無ければ追加し、元の構造を維持する。追加するテーブル・カラムと、それに伴って直す機能は [新環境に追加するテーブル・カラム](#新環境に追加するテーブルカラム)（**A1〜A23**。うち A17 は取り消し）にまとめた。**移行しないのは例外**で、同じ節の[移行の対象外](#移行の対象外移行できないもの--移行しないもの)に理由つきで 16 件（移行できないもの 7 件 / 方針として移行しないもの 9 件）ある。**決定ではなく実装が無いために移っていないもの**は、別に[現状は移していないもの](#現状は移していないもの実装が無い)に挙げた
- **グループの階層は `group.parent_group_id` が正本**（`group_structure` は派生データなので移行しない）。SSO・ログイン時間制限・2FA は**移行と同時に受け皿を作る**（2FA は受け皿だけで、移す行は無い）
- **純ログは移行しない。** `user_login_log`（1,326,645行）/ `user_login_log_monthly` / `twostepverification_log` の3件が該当し、[移行の対象外](#移行の対象外移行できないもの--移行しないもの)に入れてある。**`user_login_chk_log` も移行しない** — 名前のとおりバッチが作るログで、**ステージングの lw2 には存在しない**（受け皿も作らない）
- **U1 会員基本情報は全列を移す。** 列を落とさず、複数列を1列に畳まない（`tel` / `mobile_tel`、`user_img_file_name` の2枚、`valid_chk` / `del_chk` など）
- 例外の中に**平文の認証情報**がある（`site` の DB 接続情報、`application_config.special_pass_word` / `kanri_db_name`、`user_login_log.input_password`、2段階認証の認証コード）。**移行しないだけでなく、抽出時にも読み出さない**（`migrator/db/guards.py` の `FORBIDDEN_COLUMNS`）。**`user.password`、`sns_setting` の6列、`application_config` の LINE の2列、`site.linkpreview_api_key` は読む** — いずれも移行対象のため

---

## M1 テナント基盤

内訳: [breakdown.md](breakdown.md) の同名の節

### `tenant` → `tenants`

`tenant` (8列) → `tenants` (10列) ／ ETL段 —（**割当が無い。L0 に追加が要る**）／ ローカルデータ数 64 / C

そのまま対応: 2列（`tenant_name`→`name`、`regist_date`→`created_at`）／**新環境にカラムを追加して受ける: 2列**（`tenent_name_short`→`short_name`、`language_code`→`language_code`）

> 移行対象は recademy の1件のみ（旧 `tenant_id` は設定 `tenant.legacy_id`。**本番 12 / ステージング 10**）。**新環境に入っているのは migration のシード値だけで、recademy のテナント行は存在しない。** したがって **`tenants` の行は移行側で新規に作る。** この1行が移行全体の起点で、`tenants.id` が決まらないと他の全テーブルの `tenant_id` が決まらず、この行が入らないと FK を持つ子テーブルは1行も入らない。
>
> **新環境の実スキーマ**（`btoc-backend/db/migrations/` の `100_initial_schema.sql` / `152_core_foreign_keys.sql` / `172_tenant_lesson_quiz_lookup.sql`。`164_tenant_secrets.sql` が `db_dsn` と `provider_account_id` を削除済みで、現在は10列）:
>
> ```
> id            CHAR(26)     PRIMARY KEY
> slug          VARCHAR(63)  NOT NULL UNIQUE
> name          VARCHAR(255) NOT NULL
> db_type       VARCHAR(32)  NOT NULL DEFAULT 'shared'   -- FK → tenant_db_types(code)
> plan_id       CHAR(26)     NULL                        -- FK → platform_plans(id)
> settings      JSON         NULL
> custom_domain VARCHAR(255) NULL
> status        VARCHAR(32)  NOT NULL DEFAULT 'trial'    -- FK → tenant_statuses(code)
> created_at    TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
> updated_at    TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
> ```
>
> **NOT NULL は `slug` / `name` / `db_type` / `status` の4列だけ**で、`plan_id` / `settings` / `custom_domain` はいずれも NULL 可。**投入を止める制約は無い。** FK 先の `tenant_db_types` / `tenant_statuses` は 172 の migration が INSERT まで含むのでシードで入っている。

| 旧カラム | 新カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|---|:--:|---|---|
| `tenant_id` int(11) | `id` char(26) | 型 | 中 | 整数の連番から ULID に変わるため旧 ID をそのまま使えない。**新環境にテナント行が無いので、誰が採番するかが決まっていない。** 採番を複数のツールが別々に行うと、**別テナントの ID が生まれてデータが2つに割れる** | ETL の L0 で `tenants` を1行 INSERT し、**採番した `id` を設定値として配る**（既存ツールは `SELECT id FROM tenants WHERE slug = ?` で引くので、値そのものに要件は無い）。採番は1か所に閉じ、ツールごとに計算し直さない。投入の前後の確認は下の「移行時の注意事項」で行う |
| `tenant_code` varchar(20) | `slug` varchar(63) + UNIQUE | 性質 | 中 | `slug` はサブドメインでのテナント解決キーで、**既存ツール3本（`cmd/import-certificates` / `cmd/helpfaq` / `cmd/bridgerollback`）が `recademy` 前提**。旧 `tenant_code` が別値のまま入ると、どのツールもテナントを引けない。旧の実値は未確認 | `slug` に `recademy` を入れる。ダンプ受領後に旧 `tenant_code` と照合し、違う値なら旧値をどこにも残さないでよいか運営に確認する |
| `tenant_name` varchar(50) NULL可 | `name` varchar(255) NOT NULL | 型 | 中 | 旧は NULL 可、新は NOT NULL。**旧が NULL / 空だと NOT NULL 違反で1行も入らない。** recademy の実値は未確認（桁は 50→255 で拡大のため切り捨ては起きない） | ダンプ受領後に `tenant_id=12` の `tenant_name` が NULL / 空でないことを確認し、値をそのまま `name` に入れる。NULL / 空なら運営に正式名称を出してもらう（`slug` からの自動生成で埋めない） |
| `tenent_name_short` varchar(20) | `short_name` varchar(64) NULL **（新設）** | カラム | 低 | 略称を入れる列が無い。`settings` が読む7キーにも略称は無いため、現状のスキーマでは行き先が無い（旧の列名は `tenent` と綴り誤り） | **新環境に `short_name VARCHAR(64) NULL` を追加する migration を入れ**、値をそのまま移す（→ [追加一覧](#新環境に追加するテーブルカラム) A1）。綴り誤りは踏襲しない。**列を足しただけでは画面に出ないので機能修正が要る** — `internal/domain/tenant.go` の `Tenant` 構造体、`internal/repository/tenant_repo.go` の SELECT / INSERT / UPDATE、`internal/dto/`（`requests_tenant.go` / `responses_auth.go`）、`btoc-frontend/src/types/tenant.ts` とテナント設定画面に追加する。**表示先の決定は移行の前提ではない** |
| `language_code` char(2) | `language_code` varchar(5) NOT NULL DEFAULT 'ja' **（新設）** | カラム | 低 | **テナント単位の既定言語を持つ列が無い。** 新環境の i18n は next-intl（`ja` / `en`）が入っているが、言語は**閲覧者の cookie で決まる個人設定**で、cookie が無ければ `defaultLocale = 'ja'` に固定される（`btoc-frontend/src/i18n/request.ts`）。切替 UI も未配線（`setLocale` の呼び出し元が無い） | **新環境に `language_code VARCHAR(5) NOT NULL DEFAULT 'ja'` を追加する migration を入れ**、値をそのまま移す（→ [追加一覧](#新環境に追加するテーブルカラム) A2）。**効かせるには機能修正が要る** — `src/i18n/request.ts` の判定を「cookie → テナントの既定言語 → `defaultLocale`」に変え、テナント値をフロントに渡す経路を作る。バックエンド側は `short_name` と同じ4か所（構造体 / repo / DTO / フロント型）。`ja` / `en` 以外なら `src/messages/<locale>.json` の追加も要る |
| `del_chk` tinyint(4) | `status` varchar(32) | 性質 | 低 | **列の既定値が `trial`** なので、明示せずに INSERT するとテナントがトライアル扱いで入る。また `tenant_statuses` に `deleted` が無く、旧 `del_chk=1` を写す先が無い。recademy の実値は未確認 | `status` に **`active` を明示して INSERT する**（既定値に任せない）。ダンプで `tenant_id=12` の `del_chk=0` を確認する（`1` なら削除済みテナントなので移行方針から見直し）。`deleted` の追加は [なし → `tenant_statuses`](#なし--tenant_statuses) で行う |
| — | `db_type` varchar(32) NOT NULL | テーブル | 低 | 旧に対応列が無い NOT NULL 列。lw2 に共有 DB / 専用 DB の区別が無い | `shared` を入れる（`tenant_db_types` にシード済みで、列の既定値も `shared`） |
| — | `plan_id` char(26) NULL | テーブル | 低 | 旧に対応列が無い。FK 先の `platform_plans` に行を入れるのは**デモ用の `cmd/seed` だけ**なので、移行先は空のまま | `NULL` で作る。プラットフォームのプラン運用を始めるときに `platform_plans` を用意して設定する |
| — | `custom_domain` varchar(255) NULL | テーブル | 低 | 旧に独自ドメイン運用が無く、移行元のデータが無い | `NULL` で作る（`<slug>.<ベースドメイン>` で解決される）。必要になったら cutover 後に画面（`PATCH /tenant/custom-domain`）から設定する |
| — | `settings` json NULL | テーブル | 低 | 旧に対応列が無い。読まれる7キー（下表）のいずれにも lw2 側の移行元が無い | **lw2 の値を独自キーで入れる**（`{}` ではない）: `legacy_site_id` / `service` / `features`（`site`。A3）、`lw2_payment`（`payment_infomation` / `receipt_setting`。課金 P13）、`lw2_config` / `lw2_account` / `lw2_login`（`data_type` 順のリスト）/ `lw2_registration` / `lw2_top_parts` / `lw2_functions`（[テナントの設定](#テナントの設定2026-09-30-に仕分け)）。旧に行が無いキーは作らない。**どれも新のアプリは読まない**。読まれる7キー（`branding` など）は入れないので、cutover 後に画面から設定する |

#### 移行時の注意事項

投入前後に必ず通す3つの確認。**どれも `tenants` を1行だけ作るという前提が守られているかを見るもの**で、崩れると全テーブルの `tenant_id` が巻き添えになる。

1. **重複登録の防止 — 投入前に `tenants.name` で既登録がないかを確認する。**
   `tenants` の UNIQUE は **`slug` だけで、`name` には制約が無い**。テナント作成時のチェックも slug の重複しか見ていない（`internal/service/tenant_service.go`）ため、**同じ名前のテナントを何行でも作れる**。ETL を流し直したときや、検証で手作業で作った行が残っているときに気づけないまま二重になる。

   ```sql
   SELECT id, slug, name, status, created_at FROM tenants WHERE name = '<正式名称>';
   ```

   **0件であることを確認してから INSERT する。** 1件でもあれば新規に作らず、その行の `id` を使うか、不要な行と確認したうえで消してから流す。**slug の UNIQUE 違反で止まることを冪等性の担保にしない**（slug を別値にすれば通ってしまう）。

2. **移行対象が recademy だけかを確認する。**
   lw2 は**同一 DB に多数のテナントが同居**しており（本番73件、ステージング4件）、抽出クエリからテナントの絞り込みが抜けると他テナントの行が混ざる。**対象の旧 `tenant_id` は設定 `tenant.legacy_id`**（本番 12 / ステージング 10）で、環境ごとに違う（[README](../README.md) の横断的な問題 §5）。

   ```sql
   -- 旧: 移行対象として抽出される tenant 行
   SELECT tenant_id, tenant_code, tenant_name, del_chk FROM tenant WHERE tenant_id = <設定の legacy_id>;
   -- 新: 投入後の行数（デモ seed を入れていない環境なら1行）
   SELECT id, slug, name, status FROM tenants;
   ```

   **旧側が1行**であることを投入前に確認する。新側は**件数では判断しない** — 動作確認用の環境にはデモ seed のテナント（`demo` など9件）が居るのが正常なので、**`slug = 'recademy'` の行がちょうど1件あるか**で見る。

   ```sql
   -- 新: 移行先の対象テナント（総数ではなく slug で見る）
   SELECT id, name FROM tenants WHERE slug = 'recademy';
   -- 同じ name が別 slug に無いか（1 の重複登録の確認と対）
   SELECT id, slug FROM tenants WHERE name = '<正式名称>' AND slug <> 'recademy';
   ```

   **移行の前にローカルデータを削除して seed を入れ直す**（school-launcher の `make reseed`）。毎回同じ初期状態から始められ、前回の移行結果が混ざらない。

3. **テナントごとに `slug` を確認する。**
   recademy 以外も移行対象になった場合は、**テナント1件ずつ slug を決めて確認する**。1件でも衝突・不正値があるとそのテナントは投入できない。

   - **文字種**: `^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$`（`internal/domain/value_objects.go`）。**英小文字・数字・ハイフンのみ、3〜63文字、先頭と末尾は英数**。旧 `tenant_code` に大文字・アンダースコア・日本語が入っていればそのままでは使えない
   - **重複**: `slug` は UNIQUE。旧 `tenant_code` は73テナント分あるので、**投入前に全件の重複と文字種をまとめて確認する**
   - **既存ツールとの整合**: `-tenant <slug>` を取るツール（`cmd/import-certificates` / `cmd/helpfaq` / `cmd/bridgerollback`）が期待する値と一致していること。recademy は `recademy`

#### `settings` が受け付けるキー

`tenants.settings` は JSON NULL で、**アプリが読むのは名前空間キー7つだけ**。いずれも「キーが無ければ既定値」に落ちるので、移行時に埋める必要はない。未知のキーを書いても壊れはしないが（更新系は他キーを保持して書き戻す）、**読む実装が無いものは画面に出ない。**

| キー | 中身 | 定義 |
|---|---|---|
| `branding` | `logo_url` / `favicon_url` / `primary_color` / `accent_color` / `footer_text` / `hero_title` / `hero_subtitle` | `internal/handler/tenant_handler.go` |
| `payment` | 利用する支払手段 | `internal/commerce/domain/payment_methods.go` |
| `referral` | 紹介プログラム設定 | `internal/referral/domain/referral_config.go` |
| `line` | `enabled` / `official_account_id` / `add_friend_message` / `notification_kinds`（シークレットは `tenant_secrets`） | `internal/line/domain/line.go` |
| `community` | コミュニティ機能の設定 | `internal/community/domain/community_config.go` |
| `help_chat_rollout` | ヘルプチャットの段階公開 | `internal/domain/help_chat_rollout.go` |
| `profile_fields` | **`birth_year` / `birth_month_day` / `phone` の3項目固定**。各 `enabled` / `required` / `at_signup` | `internal/domain/profile_fields.go` |

> **`profile_fields` は3項目の固定リストで、任意項目を追加する仕組みではない。** lw2 の M4 カスタムプロフィール20項目（`profile_item_label`）の受け皿にはならない。
>
> **`theme` / `locale` は死にキー。** `cmd/seed` が書いているだけで読む実装が無い。言語は next-intl が cookie で決めており（`btoc-frontend/src/i18n/request.ts`）、`settings.locale` は参照されないため、**`language_code` はここではなく列として追加する**（上表）。
**まとめ**: 受け皿が無い列 0（2列は新環境にカラムを追加して受ける）/ 変換規則が要る列 3 / 高 0 件

### `site` → なし

`site` (17列) ／ ローカルデータ数 1 / C

**該当テーブルなし。** DB 接続情報・サービス名・機能フラグを持つ運用テーブル。
**接続情報4列だけが対象外**（移しても機能せず、平文なので読み出しもしない）で、
**残りは `tenants.settings` と `tenant_secrets` に移す**（A3・実装済み）。
`site` はインストール全体で1行なので、移行対象テナントの設定として入れる。

| 旧カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|:--:|---|---|
| `db_server` / `user_id` / `password` / `database` varchar(200) | **性質** | **高** | **DB 接続情報を平文で保持している。** 新環境の相当物は `tenant_secrets`（`kind='db_dsn'`）だが、**lw2 の接続情報を移す意味はなく、移してはいけない。** 抽出クエリでこの4列を SELECT しない設計にすること | **例外: 移行しない。** lw2 の接続情報は新環境で使わず、**抽出クエリでこの4列を SELECT しない**ようにしてレビューで確認する。新環境の接続情報は `tenant_secrets`（`kind='db_dsn'`）に運用で登録する |
| `service_name` / `description` / `service_start_date` / `service_end_date` | カラム | 低 | サービス名・説明・提供期間を入れる列が無い。`settings` にも該当キーが無い | **実装済み。** `tenants.settings` の `service` キーに移す（→ [追加一覧](#新環境に追加するテーブルカラム) A3）。`site` は**インストール全体で1行**（テナント別でない）ため、移行対象テナントの設定として入れる |
| `test_analysis` / `user_ranking_flg` / `daily_mail_send_flg` / `lw_type` | カラム | 低 | バッチ実行フラグ・機能フラグを入れる列が無い。新環境にランキング / テスト分析の機能自体は無いが、**機能の有無は移行の可否に関係しない** | **実装済み。** フラグの値を `tenants.settings` の `features` キーに移す（→ [追加一覧](#新環境に追加するテーブルカラム) A3）。**機能を作るかどうかは移行とは別の判断**なので、ここでは値を移すところまでを行う |
| `application_path` / `linkpreview_api_key` | カラム | 低 | 外部 API キーの置き場所が無い（`tenant_secrets` に該当の `kind` が無い）。`application_path` は**新環境で参照されないが、それは移行しない理由にならない** | **両方とも移す。** `application_path` は `settings.service.application_path` へ（ステージングは空）。`linkpreview_api_key` は `tenant_secret_kinds` の種別（M2 で追加済み）を使って `tenant_secrets` に入れる（→ [追加一覧](#新環境に追加するテーブルカラム) A7。ステージングは値あり） |

**まとめ**: 受け皿が無い列 17 / **高 1 件**

### `tenant_limit_value` → なし

`tenant_limit_value` (6列) ／ ローカルデータ数 64 / C

**該当テーブルなし。** 新環境に上限管理の受け皿が無い。

| 旧カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|:--:|---|---|
| `user_value` / `student_value` / `user_csv_value` / `user_learning_lesson_value` / `user_learning_lesson_csv_value` | カラム | 中 | **ユーザー数・受講者数・CSV一括登録・受講講座数の上限5種がすべて落ちる。** 上限運用をしていたなら**移行後は無制限になる** | `tenant_limits` を新設して上限5種を移す（→ [追加一覧](#新環境に追加するテーブルカラム) A4） |

**まとめ**: 受け皿が無い列 6 / 高 0 件

### なし → `tenant_statuses`

`tenant_statuses` (10列, マスタ)

**旧に対応テーブルなし。** `172_tenant_lesson_quiz_lookup.sql` が CREATE と INSERT を両方持っているので、**migration を当てた時点で `trial`/`active`/`suspended` の3行が入っている。** `tenants.status` はこの `code` への FK（`fk_tenants_status`、`ON UPDATE CASCADE`）。

**`deleted` を追加する。** `tenant.del_chk=1` に当たる値が無く、削除済みテナントを表現できない。recademy は `active` なので**今回の移行では使わない**が、テナントの削除を lw2 と同じ意味で扱えるようにするため入れる。

| 変える場所 | 内容 |
|---|---|
| `btoc-backend/db/migrations/` に新しい migration | `INSERT INTO tenant_statuses (code, name_ja, is_operational, is_trial, sort_order, is_system) VALUES ('deleted', '削除済み', FALSE, FALSE, 40, TRUE);`。`is_operational=FALSE`（ただし**この列を読むコードは現状どこにも無く**、判定は `status == 'active'` で行われている。`deleted` は `active` でないので利用不可になる） |
| `btoc-backend/internal/domain/tenant.go` | `TenantStatusDeleted` を追加し、`validTenantTransitions` に `active → deleted` / `suspended → deleted` を足す。**`deleted` からの復帰は入れない**（戻す運用なら `suspended` を使う） |
| `btoc-frontend/src/types/tenant.ts` | `status` のユニオン型に `"deleted"` を足す |

> **ロールバックに注意。** `172` の Down は `tenants.status` を `ENUM('active','suspended','trial')` に戻すため、**`deleted` の行または `deleted` のテナントが1件でもあると 172 まで巻き戻せない。** 追加する migration の Down で `deleted` 行を消す前に、`deleted` のテナントが無いことを確認する作りにする。

**移行ツールから見た影響は無い。** recademy は `active` で入れるため、`deleted` の追加は新環境側のスキーマ変更として独立して進められる。

### なし → `tenant_db_types`

`tenant_db_types` (9列, マスタ)

**旧に対応テーブルなし。** migration で投入する。`tenants.db_type` の取りうる値で `shared`/`dedicated` の2値。lw2 に対応する概念が無いので `shared` 既定でよい。

### なし → `tenant_secrets`

`tenant_secrets` (7列)

**旧に対応テーブルなし。** テナントごとの機密値（DB DSN・Webhook シークレット等）。**移行ツールが入れるのは3か所の値**（`config.secrets`）: `site.linkpreview_api_key`、`sns_setting` の6列（A7）、`application_config` の `line_channel_sercret` / `send_line_chanel_token`（→ `line_channel_secret` / `line_channel_access_token`）。値はログに出さない（長さだけ記録する）。lw2 の `site` が持つ DB 接続情報は**移行元としては使わない**（上記 `site` の項を参照）。

### なし → `tenant_secret_kinds`

`tenant_secret_kinds` (9列, マスタ)

**旧に対応テーブルなし。** migration で投入する。`tenant_secrets.kind` の取りうる値で `db_dsn` / `oauth_client_secret` / `webhook_secret` / `line_channel_*` / `robotpayment_*` など9種。

---

## M2 権限・ロール定義

内訳: [breakdown.md](breakdown.md) の同名の節

### `role_master` → `user_roles`

`role_master` (4列) → `user_roles` (12列, マスタ) ／ ETL段 L1 ／ ローカルデータ数 8 / C

そのまま対応: 3列（`role_name`→`code`、`role_index`→`sort_order`、`del_chk`→`active` + `deprecated_at`）

> **テーブルごと移す。** `user_roles` は `code` を PK にしたグローバルマスタで、**`name_ja`（表示名）と `sort_order`（表示順）を最初から持っている**（`165_user_role_status_lookup.sql`）。migration のシードは `platform_admin` / `tenant_admin` / `instructor` / `learner` / `system` の5行だが、**lw2 の8ロールのうち5つ（削除済みの `facility_manager` / `supporter` を含む）に対応先が無い**ので追加する（`master.user_roles`）。
>
> `users.role` は VARCHAR(32) で `user_roles(code)` への FK（`fk_users_role`、`ON UPDATE CASCADE`）。**マスタに行を足せば `users.role` に入れられる。**

| 旧カラム | 新カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|---|:--:|---|---|
| `role_id` int(11) | `code` varchar(32) PK | 型 | 中 | 整数 ID から文字列コードへの変更。**`role_id` を残す列が無い**ので、旧 ID で引いている箇所は全部コードに置き換わる | `role_name` を小文字化して `code` にする（`COMPANY_MANAGER` → `company_manager`）。旧 `role_id` との対応は下の[ロール対応表](#ロール対応表)を正とし、ETL の変換表に持つ |
| `role_name` varchar | `name_ja` varchar(64) NOT NULL | 性質 | 中 | **`role_name` は表示名ではなくコード**（`SYSTEM_MANAGER` / `COMPANY_MANAGER` など）。**表示名は `translate_master`**（`master_type='role'` + `language_code` + `code` + `text`）に言語別で入っている | `translate_master` の `language_code='ja'` の `text` を `name_ja` に移す。`en` は `user_roles` に受け皿が無いので、多言語対応（A2）の判断に含める |
| `role_index` int(11) | `sort_order` int | 性質 | 中 | **`role_index` は `role_id` とは別の並び順の値。** 例: `role_id=6`（`GROUP_MANAGER`）の `role_index` は 4（`database/20191108_cdss.sql`）。lw2 の定数が `ROLE_GROUP_MANAGER=6` と `ROLE_INDEX_GROUP_MANAGER=4` に分かれているのはこのためで、**取り違えると求人企業とグループ管理者が入れ替わる** | `sort_order` にそのまま移す。**変換表は `UserConstants.php` の定数ではなく `role_master` の実データを正とする** |
| `del_chk` tinyint(4) | `active` bool + `deprecated_at` datetime(3) | 性質 | 中 | **削除状態を2列で持っていて二重管理になる**（`active=TRUE` かつ `deprecated_at` に値がある、という矛盾した行を作れる）。旧側に削除日時が無いため `deprecated_at` に入れる値が決まらない | `del_chk=1` は `active=FALSE` + `deprecated_at=<cutover 日時>` で入れる。**判定は `deprecated_at IS NULL` に寄せ、`active` はそこから導出する**（`active = (deprecated_at IS NULL)`）ようにアプリ側を揃え、以後 `active` を単独で更新しない |
| `user.role_id` | `users.role` | 性質 | 中 | **8ロールすべてを移す。** 既定5値のうち使えるのは `tenant_admin` / `instructor` / `learner` の3つで、残り4ロールを `learner` に倒すと**権限が消える**（求人企業が受講者になる等）。`platform_admin` はテナントを越えて見えるため付けてはいけない | 下の[ロール対応表](#ロール対応表)で1対1に移す。不足する5ロールは `user_roles` に追加する（→ [追加一覧](#新環境に追加するテーブルカラム) A5）。**`platform_admin` を出力し得ないことをテストで固定する** |

#### ロール対応表

根拠は**ローカル DB の `role_master` / `translate_master` の実データ**（`application/constants/UserConstants.php` と `database/20191108_cdss.sql` とも一致）。**`role_index` は `role_id` と食い違う**（4↔6 が入れ替わっている）ので、**定数ではなく実データを正とする**。

> **削除済みロール（3 / 8）も移す。** `active=FALSE` + `deprecated_at` で入れ、過去の会員が参照していた場合に備える（原則3）。

| 旧 `role_id` | 旧 `role_name` | 表示名 | 新 `users.role` | 対応 |
|---:|---|---|---|---|
| 1 | `SYSTEM_MANAGER` | システム管理者 | `system_admin` | **追加**。テナント内の全権。`platform_admin` は付けない |
| 2 | `TOTAL_MANAGER` | 全体管理者 | `tenant_admin` | 既存（実測 31名） |
| 3 | `FACILITY_MANAGER` | 運営管理者 | `facility_manager` | **追加**（**`del_chk=1` の削除済み**）。`AuthModel::$is_manager` が 1/2/3 を管理者扱い |
| 4 | `COMPANY_MANAGER` | 求人企業 | `company_manager` | **追加**。就職支援（S02 企業（未コミット））と紐づく |
| 5 | `INSTRUCTOR_MANAGER` | 講座管理者 | `instructor` | 既存（実測 18名） |
| 6 | `GROUP_MANAGER` | グループ管理者 | `group_manager` | **追加**。A10 のグループと紐づく（`role_index` は 4） |
| 7 | `STUDENT` | 受講者 | `learner` | 既存 |
| 8 | `SUPPORTER` | サポーター | `supporter` | **追加**（**`del_chk=1` の削除済み**）。2019年に「現在使用されていない」として `role_id` を 8 に移した経緯がある |

> **`user.career_counselor_chk` はロールではない。** `role_id=6`（グループ管理者）に付く追加フラグで（`UserController.php:1258`）、ロールに畳むとグループ管理者の権限が消える。**`users.is_career_counselor` 列で受ける**（→ [追加一覧](#新環境に追加するテーブルカラム) A19）。

**まとめ**: 受け皿が無い列 0 / 変換規則が要る値 5 / 高 0 件

---

## M3 認証・ログイン設定

内訳: [breakdown.md](breakdown.md) の同名の節

### `sso_config` → なし

`sso_config` (3列) ／ ローカルデータ数 1 / C

**該当テーブルなし。** IdP 設定の置き場所が新環境に無い。

| 旧カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|:--:|---|---|
| `tenant_id` + `sso_type` int(11) + `sso_parameter` text | **テーブル** | **高** | `docs/authentication.md` は「SAML SSO や Google / LINE OAuth は外部 IdP に委ねる」としており**設定を DB に持たない**。**B10 SSO を ◯→X に再判定した根拠がこの1件**（[data-type-findings.md](../data-type-findings.md) §1-2） | `tenant_sso_configs` を新設し、`auth_methods` に `saml` を追加する（→ [追加一覧](#新環境に追加するテーブルカラム) A6）。`sso_parameter` は IdP ごとに形が違うので JSON 列で受ける。**移行と同時に作る** |

**まとめ**: 受け皿が無い列 3 / **高 1 件**

### `sns_setting` → なし

`sns_setting` (9列) ／ ローカルデータ数 63 / C

**該当テーブルなし。** SNS ログインのアプリ認証情報（6列）を持つ。**受け皿を追加して移行する** — `tenant_secret_kinds` に `facebook_client_id` など6種別を足し、`tenant_secrets` に入れる（A7）。

> **recademy は Facebook と Twitter の consumer key が設定済み**（instagram は空。ステージング実測）。
> 使っているのは `LoginController` の SNS ログインと `RegistrationController` の SNS 登録で、
> **cutover 後は止まる**。継続するかは [移行仕様 1-1 #5](../open-questions.md) の判断。
>
> **会員側には SNS の ID を保存していない。** `SocialOauth::twitterOauthCallback()` の戻り値の
> `email` で会員を引く実装なので、**突き合わせはメールアドレス頼み**。今回の移行で合成アドレスに
> なった会員は、新環境で SNS ログインを用意しても突き合わせできない。

| 旧カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|:--:|---|---|
| `facebook_consumer_key` / `twitter_consumer_key` / `instagram_consumer_key` ＋ 各 `*_sercret_key`（**6列**） | **性質** | **高** | **SNS のシークレットキーを平文で保持している。** さらに `auth_methods` は `password`/`google`/`line`/`passkey`/`refresh` の5値で、**Facebook / Twitter / Instagram に対応する値が無い**。`tenant_secret_kinds` に `oauth_client_secret` はあるが対応する `auth_methods` が無いため、**SNS ログインを使っていた会員は移行後ログインできない**（列名の `sercret` は lw2 側の綴り誤り） | `auth_methods` に `facebook` / `twitter` / `instagram` を追加し、**6列を読んで `tenant_secrets` に移す**（`facebook_client_id` など6種別。`config.secrets`。→ [追加一覧](#新環境に追加するテーブルカラム) A7）。新環境でもそのまま使えるため移行対象で、**読み出し禁止の対象ではない**。ステージングは Facebook / Twitter に値あり |

**まとめ**: 受け皿が無い列 9 / **高 1 件**

### `login_limit` → なし

`login_limit` (7列) ／ ローカルデータ数 0 / B

**該当テーブルなし。** 曜日・時間帯ごとのログイン制限。

| 旧カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|:--:|---|---|
| `youbi_type` / `detail_no` / `limit_type` / `start_time` / `end_time` | カラム | 中 | **「この曜日のこの時間しかログインできない」機能ごと落ちる。** ただし**ローカルデータ数0**なので recademy では未使用 | `tenant_login_windows` を新設する（→ [追加一覧](#新環境に追加するテーブルカラム) A8）。**移行と同時に作る**。ローカルデータ数0なので移行するデータは無く、cutover 後に運営が設定する |

**まとめ**: 受け皿が無い列 7 / 高 0 件

### なし → `auth_methods`

`auth_methods` (10列, マスタ)

**旧に対応テーブルなし。** migration で投入する。`login_history.method` の取りうる値で `password`/`google`/`line`/`passkey`/`refresh` の5値。旧 `user_login_log` に認証方式の列が無いので、移行時は既定の `password` を入れる。

> **SNS ログインと SSO の値を追加する。** lw2 は `sns_setting`（Facebook / Twitter / Instagram）と `sso_config`（SAML）を持つので、この5値では足りない（→ [追加一覧](#新環境に追加するテーブルカラム) A6 / A7）。

### なし → `auth_outcomes`

`auth_outcomes` (10列, マスタ)

**旧に対応テーブルなし。** migration で投入する。`login_history.outcome` の取りうる値で8種（`success`/`invalid_password`/`user_not_found`/`account_inactive`/`account_locked`/`mfa_failed`/`token_invalid`/`other_failure`）。

| 旧カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|:--:|---|---|
| `user_login_log.user_login_result` tinyint(4) | 性質 | 中 | **数値と8値の対応表が必要。** lw2 の定数を確認しないと変換規則が書けない | lw2 の定数定義から数値→8値の対応表を作り、ETL の変換規則に落とす |

---

## M4 会員項目・状態の定義

内訳: [breakdown.md](breakdown.md) の同名の節

> **3テーブルの関係。** `profile_cate`（カテゴリ）／ `profile_item`（項目の振る舞い）／ `profile_item_label`（表示名）に分かれていて、**どれも値は持たない**。値は常に `user` テーブル側にある。
>
> ```
> profile_cate        カテゴリ定義（ユーザー情報 / 基本情報 / 経歴・資格 / 希望条件 / 追加情報）
>      ↑ profile_cate_id
> profile_item        PK (tenant_id, item_type, item_no)
>                     field_name          = 値が入っている user の列名
>                     show_chk / edit_chk / required_chk / open_chk ＋ 各 *_static_chk
>                     multiple_rows_chk   = 複数行入力の可否
>      ↓ 同じキー + language で 1 対 N
> profile_item_label  PK (tenant_id, language, item_type, item_no)
>                     title（項目名）/ memo（注記）/ memo_free（自由項目の注記）
>
> 値 = user テーブルの列
>      item_type=0 → field_name が指す既存列（name / mail_add / birth_date / education …）
>      item_type=1 → user_profile1〜15（user 側の列は user_profile20 まである）
> ```
>
> **`profile_item` は「値」ではなく「画面制御の定義」**で、`field_name` が値の在処（`user` の列名）を指しているだけ。1項目 = `profile_item` 1行 + `profile_item_label` を言語数分、という関係になる。`*_static_chk` は**テナント管理者が設定を変えられないように固定する**フラグ。
>
> **recademy (tenant_id=12) の設定**（リポジトリ同梱の `lw2.sql` ダンプ、2019-08-28 時点。**本番の最新状態はダンプ受領後に再確認する**）:
>
> - `item_type=0` が 30項目、`item_type=1`（自由記述）が 15項目
> - 自由記述で**名前が付いているのは 1〜8**（出身学校 / 学部・専攻 / 部活・サークル / 出身地 / 星座 / 特技 / 趣味 / 将来の夢）。9〜15 は `自由記述項目9` のような既定名のまま
> - **画面に出している（`show_chk=1`）のは 1〜3 だけ**で、4〜15 は非表示。**ただし移行は `show_chk` で絞らず全項目を移す**（`show_flag` に値を残す。ステージングは 49項目中 42項目が `show_chk=1`）

### `profile_cate` → なし

`profile_cate` (5列) ／ ローカルデータ数 5 / C

**該当テーブルなし。** プロフィール項目のカテゴリ定義。

| 旧カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|:--:|---|---|
| テーブル全体 | 性質 | 中 | **`tenant_id` を持たない全テナント共通のカテゴリ**（5行）。新環境はテナントごとに持つ | `tenant_profile_item_categories` を新設し、**recademy 用の5行として投入する**（`config.profile_item_categories`。`profile_cate_id` に旧 `profile_cate_id` を残す）。→ [追加一覧](#新環境に追加するテーブルカラム) A9。**項目より先に入れる** — `tenant_profile_items.category_id` の FK 先になるため。旧 `profile_item.profile_cate_id = 0` は「分類なし」で NULL |

**まとめ**: 受け皿が無い列 5 / 高 0 件

### `profile_item` → なし

`profile_item` (16列) ／ ローカルデータ数 3,123 / C

**該当テーブルなし。** テナントが定義するカスタムプロフィール項目の本体。

| 旧カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|:--:|---|---|
| `item_type` / `item_no` / `field_name` ＋ `show_chk` / `edit_chk` / `required_chk` / `open_chk` ＋ 各 `*_static_chk` | **テーブル** | **高** | **カスタムプロフィール項目が定義ごと落ちる。** 表示・編集・入力必須・他ユーザーへの公開を項目単位で制御する仕組みで、新環境に相当機能が無い | `tenant_profile_items` と `user_profile_values` を新設して項目定義と値を移す（→ [追加一覧](#新環境に追加するテーブルカラム) A9）。**`show_chk` で絞らず全項目を移す**（`show_chk` は `show_flag` に残す。`config.profile_items`） |

**まとめ**: 受け皿が無い列 16 / **高 1 件**

### `profile_item_label` → なし

`profile_item_label` (9列) ／ ローカルデータ数 3,187 / C

**該当テーブルなし。** プロフィール項目のラベル。

| 旧カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|:--:|---|---|
| **`language` char(2)** | **性質** | **高** | **項目ラベルを言語別に持てない。** 新環境の i18n（next-intl / `ja`・`en`）は**画面固定文言の翻訳**で、テナントが登録したラベルは `name_ja` 1列しか持てない。言語ごとのラベルは行き先が無い | `tenant_profile_item_labels` に `locale` を持たせて言語別ラベルを移す（→ [追加一覧](#新環境に追加するテーブルカラム) A9）。日本語以外のラベルが登録されているかは実データで確認する |
| `title` / `memo` / `memo_free` | カラム | 低 | 項目名・注記が落ちる | A9 の `tenant_profile_item_labels` に `title` / `memo` 列を持たせて移す |

**まとめ**: 受け皿が無い列 9 / **高 1 件**

### `user_item_default` → なし

`user_item_default` (4列) ／ ローカルデータ数 10 / C

**該当テーブルなし。** `item_name` + `tenant_id` + `value` で、**テナント単位の既定値**（名前に反して会員データではない）。

| 旧カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|:--:|---|---|
| `item_name` + `value` | カラム | 中 | 新環境に既定値の概念が無い | **`tenant_field_defaults` を新設して移す**（A23。`config.field_defaults`）。`item_name` は `profile_item` ではなく `user` の列名なので、`tenant_profile_items.default_value` には入れない（ステージング実測1件 `profile_open_chk`） |

**まとめ**: 受け皿が無い列 4 / 高 0 件

### なし → `user_statuses`

`user_statuses` (10列, マスタ)

**旧に対応テーブルなし。** migration で投入する。`users.status` の取りうる値で `active`/`inactive`/`pending`/`deleted` の4値。

| 旧カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|:--:|---|---|
| `user.del_chk` / `valid_chk` / `entry_date` | 性質 | 中 | 新側は状態ごとに**ログイン可否フラグ**（`can_login` / `is_active_like`）を持つ4値のマスタ。**旧の3列を `status` 1列に畳むと、`valid_chk=0` と `del_chk=1` の組み合わせや有効期間そのものが復元できなくなる** | `status` は**判定結果**として `del_chk=1`→`deleted` / `valid_chk=0`→`inactive` / それ以外→`active` を入れる（`users._status_of`）。**`limit_date` は `status` の判定に使わない**（`login_end_date` に入れるだけ）。以前の記述（ETL設計 §5-1）は「`limit_date` 超過→`inactive`」だったが、実装はそうなっておらず、**ステージングでは期限切れの有効会員 39名が `active` で入る**（2026-10-02 の確認）。**元の3列は畳まず `users.is_valid` / `login_start_date` / `login_end_date` に残す**（→ [追加一覧](#新環境に追加するテーブルカラム) A20） |

---

## M5 組織・属性の定義

内訳: [breakdown.md](breakdown.md) の同名の節

> **調査時点では新側が丸ごと0件だった**（いまは `tenant_groups` と `user_tags` で受ける）。グループ・属性は lw2 の配信対象の絞り込み（お知らせ・フォローメール・掲示板・自動割当・講師の担当範囲）の土台なので、**ここが落ちると他区分の機能も連鎖して落ちる**。

### `group` → なし

`group` (12列) ／ ローカルデータ数 1,009 / C

**該当テーブルなし。** グループの定義。

| 旧カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|:--:|---|---|
| テーブル全体 | **テーブル** | **高** | **グループの定義が丸ごと落ちる。** `group_name` / `group_code` / `memo` / `sort_no` すべて受け皿なし | `tenant_groups` を新設して定義を移す（→ [追加一覧](#新環境に追加するテーブルカラム) A10）。階層は `parent_id`（旧 `parent_group_id`）で持つ |
| `parent_group_id` + `hierarchy` | **性質** | **高** | **階層を2通りで持っている。** `group.parent_group_id`（親1つ）と `group_structure`（祖先→子孫の全組み合わせ）。`hierarchy` は階層の深さ | **`parent_group_id` が正本。** `GroupModel::makeGroupStructure()` が `parent_group_id` を遡って `group_structure` を全消し＋作り直ししており、**`group_structure` は派生データ**（[対象外 B](#移行の対象外移行できないもの--移行しないもの)）。A10 の `tenant_groups` は `parent_id` と `depth` を持てばよい |

**まとめ**: 受け皿が無い列 12 / **高 2 件**

### `group_structure` → なし

`group_structure` (2列) ／ ローカルデータ数 1,313 / C

**該当テーブルなし。** `group_id` + `slave_group_id` でグループの親子を持つ。

| 旧カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|:--:|---|---|
| `group_id` + `slave_group_id` | テーブル | 中 | `group_id`（上位）+ `slave_group_id`（配下）で**祖先→子孫の全組み合わせ**を持つ閉包テーブル。`group.parent_group_id` から作り直される派生データで、グループの作成・削除のたびに全消し＋再生成される | **例外: 移行しない。** `parent_group_id` から再構築できる派生データ。新環境で配下グループを引く必要が出たら、再帰 CTE（MySQL 8.4）か同等の閉包テーブルをアプリ側で作る |

**まとめ**: 受け皿が無い列 2 / 高 0 件

### `attribute` → なし

`attribute` (9列) ／ ローカルデータ数 427 / C

**該当テーブルなし。** 属性の定義。

| 旧カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|:--:|---|---|
| テーブル全体 | **テーブル** | **高** | **属性の定義が丸ごと落ちる** | **新の `user_tags` に移す**（旧の「属性」が新の「タグ」。`config.attributes`。→ [追加一覧](#新環境に追加するテーブルカラム) A11）。旧 ID は `user_tags.attribute_id`。**削除済みの属性も `deleted_at` 付きで移す**。タグ名が重なるものは `（旧ID n）` を付けて区別する |
| `kiracari_user_chk` | 性質 | 中 | 「キラキャリ会員区分」という lw2 固有のフラグ。**属性の中に会員区分が紛れている** | **現状は移していない**（`user_tags` に受け皿が無い。2026-10-02 の確認。ステージングは7件中1件が `1`）。会員区分として使われているかを実データで確認し、使われていれば表現方法を決める |

**まとめ**: 受け皿が無い列 9 / **高 1 件**

### `attribute_lesson` → なし

`attribute_lesson` (3列) ／ ローカルデータ数 332 / C

**該当テーブルなし。** `lesson_id` + `attribute_id` で、属性に必須講座を紐づける定義。

| 旧カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|:--:|---|---|
| `lesson_id` + `attribute_id` | カラム | 中 | **属性による必須講座の指定が落ちる。** 必須受講の運用があれば機能欠落 | **移さない**（A11）。旧でも講座を結んでいない（作成時に `attribute_id` だけの行を作る）うえ、属性はタグに一本化した。`attribute_required_courses` は school-launcher にあるが移行ツールは書かない（ステージング実測5行） |

**まとめ**: 受け皿が無い列 3 / 高 0 件

---

## U1 会員基本情報

内訳: [breakdown.md](breakdown.md) の同名の節

### `user` → `users`

`user` (**95列**) → `users` (17列) ／ ETL段 L1 ／ ローカルデータ数 48,906 / C ／ recademy 実測 4,912名（削除込み 5,733）

そのまま対応: 3列（`regist_date`→`created_at`、`update_date`→`updated_at`、`tenant_id`）

> ロール値（`role_id` → `users.role`）の写像は [`role_master` → `user_roles`](#role_master--user_roles) に置いている。
>
> **この節は全列を移す。列を落とさず、複数列を1列に畳まない。** 新環境の `users` は17列しか無いので、**差分はすべて列追加かサイドテーブルで受ける**（A12 / A13 / A14 / A20）。下の[全列の行き先](#全列の行き先)に90列すべての対応を書いた。

#### 全列の行き先

列は `lw2.sql`（同梱ダンプ、2019-08-28 時点）の `user` 90列。**本番はここに `nationality` / `foreign_*` / `line_id` / `line_entry_chk` / `personal_record_chk` / `career_counselor_chk` / `scout_display_type` などが加わって95列**なので、ダンプ受領後に差分を確認する。

| 旧カラム | 行き先 | 備考 |
|---|---|---|
| `user_id` | `external_user_links.external_id` ＋ **`users.user_id`（追加）** | `users.id` は ULID で新採番。旧 ID は対応表と `users.user_id`（A24。外部のバッジシステムが旧 ID で引く）の両方に残す |
| `tenant_id` | `users.tenant_id` | recademy の ULID 定数 |
| `login_id` varchar(100) utf8_bin | **`users.login_id`（追加）** | **新はログイン識別子が `email` だけで、`login_id` の受け皿が無い。** 大文字小文字を区別する照合順 (`utf8_bin`) なので、そのまま移すなら照合順も合わせる |
| `password` | `users.password_hash` | **3DES 復号 → bcrypt 再ハッシュ**（`migrator/core/passwords.py`）。鍵は環境変数 `LW2_CRYPT_KEY` |
| `role_id` | `users.role` | [ロール対応表](#ロール対応表)で8値を1対1 |
| `name_sei` / `name_mei` | **`users.name_last` / `name_first`（追加）** | `name` は連結した表示用として生成 |
| `kana_sei` / `kana_mei` | **`users.name_kana_last` / `name_kana_first`（追加）** | A12 |
| `mail_add` | `users.email` | 欠損・重複の対処が要る（下表の「高」。ステージング実測 欠損 2,698名 / 重複 389名） |
| `mobile_mail_add` | **`users.mobile_email`（追加）** | 携帯メール。`email` に畳まない |
| `tel` / `mobile_tel` | `users.phone` / **`mobile_phone`（追加）** | 固定と携帯を分けたまま |
| `zip_code` / `pref_id` / `city_name` / `address` ＋ 同 `*2` | **`user_addresses`（新設）** | 4項目 × 2組。A12 |
| `nick_name` | **`users.nickname`（追加）** | |
| `sex_type` | **`users.gender`（追加）** | コード値。マスタ化するかは新環境の作法に合わせる |
| `birth_date` | `users.birth_year` / `birth_month` / `birth_day` | 時刻部は全件 `00:00:00`。`birthday` date 1列にする案は下表参照 |
| `blood_type` | **`users.blood_type`（追加）** | コード値 |
| `self_introduction` | **`users.self_introduction`（追加）** | 自己PR。career 側の職務経歴とは別物 |
| `user_img_file_name` / `user_img_file_name1` | `users.avatar_url`（**データは移行しない**） | 画像は移行対象外。列は使うが空で始める |
| `user_profile1`〜`20` | **`user_profile_values`（新設）** | A9。`profile_item.field_name` と突き合わせる |
| `profile_open_chk` / `name_open_chk` / `address_open_chk` / `birthday_open_chk` / `diary_open_chk` / `lesson_open_chk` | **`user_field_visibility`（新設）** | A13 |
| `sendmail_pc_chk` / `sendmail_mobile_chk` / `sendmail_scout_chk` / `notify_footprint_pc_chk` / `notify_footprint_mobile_chk` | `notification_optouts`（**`channel` と不足種別を追加**） | **全件移す。極性を反転**。A21 |
| `sendmail_bbs_comment_pc_chk` / `sendmail_bbs_comment_mobile_chk` | — | **現状は移していない**（実装が無い。2026-10-02 の確認）。`email_kinds` に `bbs_comment` は足したが、`OPTOUT_SOURCES` にこの2列が無い。ステージングは 3,155名中 PC 3,154名・携帯 3,155名が `0`（受け取らない） |
| `entry_date` / `limit_date` | **`users.login_start_date` / `login_end_date`（追加）** | `status` に畳まない |
| `user_memo` | **`users.admin_memo`（追加）** | 運営メモ |
| `system_data` | **`users.external_data`（追加）** | 連携用フィールド。中身の形式を実データで確認する |
| `recent_login_date` / `recent_access_time` / `total_login_count` | **`users.last_login_at` / `last_access_at` / `total_login_count`（追加）** | A14 |
| `password_change_date` | **`users.password_changed_at`（追加）** | パスワード有効期限の運用があるなら必要 |
| `is_lockout` / `start_date_failing_login` / `number_of_failing_login` | **`users.is_lockout` / `failed_login_started_at` / `failed_login_count`（追加）** | A14。3列のまま |
| `valid_chk` / `del_chk` | `users.status` ＋ **`users.is_valid`（追加）** | 2フラグを1列に畳まない |
| `regist_date` / `update_date` | `users.created_at` / `updated_at` | |
| `education` / `employment_status` / `job_category` / `desired_job_type` / `desired_job_location` / `desired_employment_status` / `job_career_*` / `qualification` | career DB の `learner_career_profiles` | **別DB。** 就職支援（未コミット） S05 |
| `new_user_chk` | **`users.is_new`（追加）** | 新規会員バッジの表示に使っていたかを確認する |
| `scout_count` / `disp_name_chk` / `cashback_chk` | career DB 側 | スカウト・Like・キャッシュバックは就職支援の機能 |
| `company_id` | career DB の `companies` | S02 |



| 旧カラム | 新カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|---|:--:|---|---|
| `mail_add` varchar(200) **NULL可・UNIQUE無し** | `email` varchar(255) **NOT NULL** + `UNIQUE (tenant_id, email)` | **型** | **高** | **欠損と重複がそのままでは入らない。** ステージング（2026-09-18 取得）の実測で**欠損 2,698名・重複 389名＝会員の 98%**。旧は NULL 可・UNIQUE 無しのため、同じアドレスを数十名が共有している（最大 57名） | **移行ツールは旧の値をそのまま入れ、当たった会員は移さない**（[移行仕様 3.3](migration-spec.md#33-投入load)）。**合成アドレスをツールが作ることはしない** — 作ると何が本物か分からなくなる。アドレスの割り当ては**暫定対応**（`fixups`）で `overrides.csv` に書き、移行ツールはそれを読むだけ。ステージングでは `ext-<user_id>@lw2.invalid`（新環境のブリッジの `syntheticEmail` と同じ形式）を当て、重複した組の**いちばん古い会員は現在の値のまま**にした |
| `name_sei` + `name_mei` | `name` varchar(255) | 性質 | 中 | 新は `name` 1列。**lw2 は入力と CSV が姓/名の2欄**（会員登録フォーム・プロフィール編集・管理画面 `user/edit.phtml`・CSV インポート）で、**表示は常に `CONCAT(name_sei,' ',name_mei)`**。連結して1列に入れると**姓/名の2欄に戻せない**。両方 NULL の行があると連結結果が空になる | **`users` に `name_last` / `name_first` を追加し、分割のまま移す**（→ [追加一覧](#新環境に追加するテーブルカラム) A12）。`name` は表示用に連結した値を入れるが、**分割列を正とし `name` は保存時に生成する**（二重管理を避ける）。**両方 NULL でも停止しない** — `name` を NULL にして入れる（ステージングは0件） |
| `kana_sei` / `kana_mei` | — | **カラム** | **高** | **フリガナを入れる列が無い。** lw2 はフリガナを**入力・表示・会員検索**に使っている（`name_sei LIKE … OR kana_sei LIKE …`）。なお**五十音順ソートは lw2 に実装されていない**（`ORDER BY kana*` が1件も無い）ので、並べ替えは移行で失われる機能ではない | `users` に `name_kana_last` / `name_kana_first` を追加して移す（→ [追加一覧](#新環境に追加するテーブルカラム) A12） |
| `zip_code` / `pref_id` / `city_name` / `address` ＋ 同 `*2` | — | **カラム** | **高** | **住所2組・計8列を入れる列が無い。** lw2 のフォームは1組につき**郵便番号 / 都道府県（コードの select）/ 市区町村 / 以下住所**の4項目（`user/edit.phtml`、CSV も同じ4列×2組）。`pref_id` は tinyint の**都道府県コード**、`address` は text で**番地・建物名を1欄にまとめている**。2組の用途（自宅 / 勤務先など）は定義されておらず「住所1 / 住所2」としか書かれていない | `user_addresses` を新設し、**`postal_code` / `prefecture` / `city` / `street`（番地・建物名）**の4列＋種別で2組を移す（→ [追加一覧](#新環境に追加するテーブルカラム) A12）。**`pref_id` はコードなので都道府県名に展開して入れる**（新環境は就職支援の `desired_prefecture varchar(10)` のように文字列で持っている）。展開表は**旧 DB の `pref_master` から引く**（48行。`pref_name` はコード `PREF_CODE_01` で、**名称は `description`**。`99=海外`）。**`pref_id=0` は「未選択」なので NULL**（`pref_master` は 1 始まりで 0 の行は無い。ステージング実測で住所1に465件・住所2に569件）。海外住所（`foreign_*`）は都道府県が無いので `country` + `city` + `street` で受ける |
| `user_profile1` 〜 `user_profile20` (text×20) | — | **カラム** | **高** | **カスタムプロフィール20項目の値が落ちる。** 定義側（M4）も落ちるので復元不能 | A9 の `user_profile_values` に移す。**`profile_item` の `field_name` と `item_no` で列と項目を突き合わせる**（値だけ移しても項目名が分からない） |
| `tel` / `mobile_tel` varchar(50) | `phone` varchar(32) | 型 | 中 | **固定電話と携帯電話が別の列なのに、新は `phone` varchar(32) の1列しかない。** 1列に畳むと**どちらの番号か分からなくなり、片方が消える**。桁も 50 → 32 に縮む | **`users` に `mobile_phone` varchar(32) を追加して2列のまま移す**（→ [追加一覧](#新環境に追加するテーブルカラム) A20）。`tel`→`phone`、`mobile_tel`→`mobile_phone`。桁は**32文字超の件数を抽出時に検査**し、あれば `varchar(50)` に広げる（切り捨てない） |
| `birth_date` datetime | `birth_year` / `birth_month` / `birth_day` | 型 | 低 | 新は `birth_year` / `birth_month` / `birth_day` の3列に分かれている。**lw2 の `birth_date` は datetime だが時刻部は全件 `00:00:00`** なので、日付としての情報は落ちない。3列にするのは新環境が**「生年は必須、生月日は任意」を設定できる**仕様（`internal/domain/profile_fields.go`。`生月日だけを有効にはできない` というバリデーションがある）に合わせたもの | 3列に分解して移す（`birth_year` / `birth_month` / `birth_day`。時刻部は捨てる）。**`birthday` date 1列に一本化する選択もある** — 移行データは年月日がそろっているので情報は落ちないが、**`profile_fields` の「生月日は任意」が表現できなくなる**ため、その仕様を使わないと決めた場合に限る（未決の扱いは本文を参照） |
| `password` varchar(200) (3DES) | `password_hash` varchar(255) (bcrypt) | 性質 | 高 | **復号できる形で保持している。** `base64(3DES-CBC(平文))` で、鍵は `application.ini` の `security.mcrypt.key`（鍵 = `substr(md5(秘密鍵),0,24)` / IV = `substr(md5(鍵),0,8)` / ゼロ埋め）。新環境は bcrypt（`libs/auth/password.go`、`bcrypt.DefaultCost` = 10） | **移行ツールで実装済み**（`migrator/core/passwords.py`）。復号 → bcrypt（`$2a$` / コスト10）に入れ替え、**会員にパスワード再設定を求めない**。秘密鍵は**環境変数 `LW2_CRYPT_KEY`**（設定ファイルに書かない）。**平文はログにも例外にも出さない。** 復号できないもの・旧が空のものは**空のハッシュ（`''`）で入れ**、件数と会員 ID を警告に出す（その会員はログインできない状態で移る）。ステージング実測で 3,155件中 3,154件が復号でき、旧パスワードで新ハッシュが通ることを確認済み |
| `entry_date` / `limit_date` (date) | `login_start_date` / `login_end_date` **（追加）** | 性質 | 中 | **ログイン開始日・終了日を入れる列が無い。** 新は `status` しか無いので、期限切れを `inactive` に畳むと**「いつからいつまで」が消え、期限が来ても自動で切り替わらない** | **`users` に `login_start_date` / `login_end_date`（date）を追加して2列とも移す**（→ [追加一覧](#新環境に追加するテーブルカラム) A20）。`status` は現時点の判定結果として別に持ち、**期限の判定はこの2列で行う** |
| `del_chk` / `valid_chk` | `status` | 性質 | 中 | **2つのフラグを `status` 1列に畳むため、`valid_chk=0`（無効）と `del_chk=1`（削除）の組み合わせが区別できなくなる**（両方立っている行の情報が落ちる） | `status` の4値へ振り分けたうえで、**`users` に `is_valid` を追加して `valid_chk` を素のまま残す**（→ [追加一覧](#新環境に追加するテーブルカラム) A20）。`del_chk=1` は `status='deleted'`、`valid_chk=0` は `status='inactive'` に対応させ、**両方立っている行は `deleted` を優先**する |
| `user_img_file_name` / `user_img_file_name1` | `avatar_url` varchar(512) | 型 | 低 | lw2 は画像列が2本ある（`user_img_file_name` / `user_img_file_name1`）。**プロフィール画像は移行対象外**と決めたので、列は要るがデータは入れない | **例外: プロフィール画像のデータは移行しない**（運営の判断）。列は既存の `avatar_url` をそのまま使い、**L9 のファイル移送からも外す**。2枚目の受け皿は作らない。cutover 後は空で始まり、会員が登録し直す |
| `*_open_chk` 8列 / `sendmail_*_chk` 6列 / `is_lockout` 系 3列 / `recent_login_date` 系 3列 ほか | — | カラム | 中 | **公開制限・通知受取・ロックアウト状態・最終ログインを入れる列が無い**（計20列前後）。通知受取は新 `notification_optouts` で**極性が反転**する。さらに **`notification_optouts` は `kind` 1列で PC / 携帯の区別が無く、`email_kinds` の13種別にもお知らせ・スカウト・足あと・掲示板コメントが無い** | **全列を移す。** 公開制限は `user_field_visibility` を新設し、`user` の `*_open_chk` 6列を**短いコード（`profile` / `name` / `address` / `birthday` / `diary` / `lesson`）の `field_code`** にして移す（→ [追加一覧](#新環境に追加するテーブルカラム) A13）。ロックアウト3列・最終ログイン3列は `users` に同じ粒度で追加（A14）。通知受取は `email_kinds` に不足種別を追加し、`notification_optouts` に `channel` を足したうえで極性を反転して移す（A21） |
| `line_id` varchar(100) | `line_links` | テーブル | 中 | **LINE 公式アカウントは継続すると決まった**ので移行対象。`line_links.line_user_id` は Messaging API の userId（`U` で始まる33文字）で、**lw2 の `line_id` が別プロバイダー発行だと値が一致せず push が届かない**。友だち状態に相当する列も lw2 に無い | ETL で `line_links` を作る（`user_id` + `line_user_id` + `is_friend` + `linked_at`）。**移行前に `line_id` が `U` 始まり33文字かを検査**し、形式が違うものは移さず一覧を運営に渡す。`is_friend` は `TRUE` で入れ、**初回 push の 403 で落とす**運用にする |
| `employment_status` / `job_category` / `desired_job_*` / `job_career_*` / `education` / `qualification` | career:`learner_career_profiles` | テーブル | 中 | **別DB（career）へ行く。** 就職支援（未コミット） S05 を参照 | career-backend の移行時期（Wave 4 / Step 2）が決まってから着手する |
| `company_id` | career:`companies` | テーブル | 低 | 就職支援（未コミット） S02 を参照 | 同上。career-backend 側で `companies` を作ってから紐付ける |

**まとめ**: 受け皿が無い列 約60（**すべて列追加かサイドテーブルで受ける**。[全列の行き先](#全列の行き先)）/ 変換規則が要る列 9 / **高 4 件**

### `user_attached_info` → なし

`user_attached_info` (7列) ／ ローカルデータ数 15,653 / C

**該当テーブルなし。** 会員の付属情報。

| 旧カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|:--:|---|---|
| `career_counselor_chk` | **カラム** | **高** | **キャリアカウンセラー権限がここにある。** `role_master` でも `system_admin_role` でもなく会員の付属情報に権限フラグが入っており、**権限の棚卸しで見落としやすい**。新環境に該当ロールが無い（`user_roles` は5値） | `users.is_career_counselor` を追加して移す（→ [追加一覧](#新環境に追加するテーブルカラム) A19）。**ロールに畳まない** — lw2 では `role_id=6`（グループ管理者）に付く追加フラグで、ロールにすると本来の権限が消える |
| `personal_record_chk` / `line_entry_chk` | カラム | 低 | 個人カルテ表示設定・LINE 連携登録フラグを入れる列が無い | **どちらも現状は移していない**（実装が無い。2026-10-02 の確認）。`personal_record_chk` は A13 の `user_field_visibility`（`field_code='personal_record'`）で受ける想定だったが、`user_field_visibility` の Step は `user` の6列しか読まない（ステージングで値があるのは87名）。`line_entry_chk` も `line_links` の Step（`support.1`）は参照しない。**残る列（`user_id` / 登録・更新日時）は親行のキーと監査列**なので、`users` 側の `created_at` / `updated_at` と突き合わせる |

**まとめ**: 受け皿が無い列 7 / **高 1 件**

### `user_nationality_info` → なし

`user_nationality_info` (11列) ／ ローカルデータ数 8,478 / C

**該当テーブルなし。** 国籍と海外住所。

| 旧カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|:--:|---|---|
| `nationality` / `country` / `foreign_zip_code` / `foreign_city_name` / `foreign_address` ほか | カラム | 中 | **国籍・海外住所を入れる列が無い**（11列）。同じ内容が `payment_application` にも重複して存在する（課金（未コミット） K02 参照） | A12 の `user_addresses` に `country` / `nationality` と海外住所3列を持たせ、`kind='foreign'` の行で移す（`nationality` / `country` は `country_master` で国名に展開。`*_another` があればそちらを使う）。`language_code` は `users.language_code`（A22）。**`user_id` をキーに8列を移し、`regist_date` / `update_date` は移さない**。`payment_application` 側と重複するので、どちらを正とするかを課金（K02）と揃える |

**まとめ**: 受け皿が無い列 11 / 高 0 件

### なし → `external_user_links`

`external_user_links` (8列)

**旧に対応テーブルなし。** lw2 ↔ 新のユーザー対応表で、既存のブリッジ（`external_user_import_service.go`）が作る。移行の正本になる。**新環境は空から始まる**ので、`tenants` の行を作ったあとにブリッジを流す順序になる。

> **ブリッジは `users.id` をランダム ULID で採番する**（`internal/service/external_user_import_service.go:177` の `ulid.Make()`）。旧 `user_id` から ID を逆算することはできないので、**会員の突き合わせはこの表の `UNIQUE (tenant_id, external_system, external_id)` だけが担う。** 移行ツール側が同じ会員を別採番で作ると二重登録になる（[README](../README.md) の横断的な問題 §3）。

| 旧カラム | 新カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|---|:--:|---|---|
| `user.user_id` | `external_id` + `external_system` + `UNIQUE (tenant_id, external_system, external_id)` | **性質** | **高** | **`external_system` の値が資料間で `lw2` と `kiracari` に割れている。** ETL設計 §3-2/§5-1 は `lw2`、列コメントと `external_user_link_repo_integration_test.go:14` は `kiracari`。**食い違うと同じ会員が二重登録される** | **移行ツールは `lw2` 固定で入れる**（`users.EXTERNAL_SYSTEM`）。ブリッジ・テストの側も `lw2` に揃っているかを確かめる |

---

## U2 会員の一意ID

内訳: [breakdown.md](breakdown.md) の同名の節

### `user_personal_no` → なし

`user_personal_no` (6列) ／ ローカルデータ数 53,568 / C

**該当テーブルなし。**

> **`personal_no` はマイナンバーではなく、会員に振る一意の ID**（運用担当に確認済み）。PDF のデータ種名「マイナンバー」が実体と合っていない。スキーマ側もそれを裏付けていて、`int(11)` は signed int の最大が 2,147,483,647（10桁）なので**12桁のマイナンバーはそもそも格納できない**。列コメントも「登録番号」「個別番号」（[data-type-findings.md](../data-type-findings.md) §3）。

| 旧カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|:--:|---|---|
| `personal_no` int(11) / `regist_no` int(11) | **テーブル** | **中** | **会員の一意 ID が落ちる。** 新環境で会員を外部から指すキーは `external_user_links.external_id`（= lw2 の `user_id`）であって `personal_no` ではない。**会員向けの画面・帳票・外部連携でこの番号を見せていたなら、移行後に同じ番号を提示できなくなる。** 用途を運用に確認し、必要なら `external_user_links` を種別違い（`external_system='lw2_personal_no'` など）でもう1行持つか、CSV で運営に渡す | `personal_no` は `users.member_no` を追加して移す（→ [追加一覧](#新環境に追加するテーブルカラム) A12）。**`regist_no` は現状は移していない**（実装が無い。2026-10-02 の確認。ステージングは 3,155名全員に値がある）。外部連携のキーは従来どおり `external_user_links.external_id`（= lw2 の `user_id`）を使う |
| `scout_display_type` | 性質 | 中 | スカウト画面での名前表示設定。**就職支援（S03）側の設定がこのテーブルに入っている**ので、`personal_no` がスカウト時に実名の代わりに出す匿名 ID だった可能性がある | 就職支援（S03 スカウト）側の受け皿に移す。**用途確認は `personal_no` と併せて行う**（就職支援（未コミット） を参照） |

**まとめ**: 受け皿が無い列 6 / 高 0 件。**機微情報ではないので廃棄方針の議論は不要**

---

## U3 認証情報・セキュリティ

内訳: [breakdown.md](breakdown.md) の同名の節

### `password_reminder` → なし

`password_reminder` (6列) ／ ローカルデータ数 5,029 / B

**該当テーブルなし。** パスワード再発行の一時トークン（`reminder_id` + `login_id` + `mail_add`）。一時データなので移行不要。

| 旧カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|:--:|---|---|
| テーブル全体 | カラム | 低 | パスワード再発行の一時トークン（`reminder_id` + `login_id` + `mail_add`）。**発行中のトークンで、移した瞬間に意味を失う**。パスワード本体の移行は [`user` → `users`](#user--users) の `password` 列を参照 | **例外: 移行しない。** 発行中の一時トークンで、cutover 後は新環境が発行し直す |

**まとめ**: 受け皿が無い列 6 / 高 0 件

### `twostepverification` → なし

`twostepverification` (5列) ／ ローカルデータ数 55 / C

**該当テーブルなし。**

| 旧カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|:--:|---|---|
| `verification_code` int(11) / `error_count` / `result` | **性質** | **高** | **「二要素認証の設定」ではなく「現在発行中の認証コード」**で、コードを平文で保持している。さらに**新環境に 2FA 機能そのものが無い** — `user_passkeys` はパスキーであって 2FA ではなく、`auth_outcomes` の `mfa_failed` だけが宙に浮いている | `user_two_factor_secrets` を新設し `auth_methods` に `totp` を追加する（→ [追加一覧](#新環境に追加するテーブルカラム) A15）。**受け皿を作るだけで、移す行は無い** — 持っているのは発行中のコード（平文）だけで、移した時点で無効。移行ツールでは[計画](schema-additions.md#計画移行では使わない-2-件)に置き、必須にしない |

**まとめ**: 受け皿が無い列 5 / **高 1 件**

### `twostepverification_log` → なし

`twostepverification_log` (6列) ／ ローカルデータ数 192 / A

**該当テーブルなし。** 二段階認証の試行ログ。

| 旧カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|:--:|---|---|
| `input_code` + `correct_code` | 性質 | 中 | **正解コードを平文でログに残している。** 移すと平文の認証コードが新環境に持ち込まれる | **例外: 移行しない。** **純ログ**であり、かつ正解コードの平文を含む。**抽出クエリでこの2列を SELECT しない** |

**まとめ**: 受け皿が無い列 6 / 高 0 件

---

## U4 ログイン履歴

内訳: [breakdown.md](breakdown.md) の同名の節

### `user_login_log` → `login_history`

`user_login_log` (13列) → `login_history` (8列) ／ ETL段 — ／ ローカルデータ数 1,326,645 / **A**

そのまま対応: 1列（`tenant_id`）

> **例外: 移行しない（純ログ）。** 棚卸しの A 区分（純ログ）は移行対象外とする方針が決まったため、受け皿（`login_history`）はあるが移さない。**新環境の `login_history` は cutover 後の認証から記録を始める。**
>
> 以下の表は**受け皿の構造上の問題**を記録として残すもので、移行作業としては発生しない。ただし **`login_history.user_id` が NOT NULL + FK で、失敗ログイン（`auth_outcomes` の `user_not_found`）を記録できない**のは**新環境の運用でそのまま効く問題**なので、移行とは切り離して直す必要がある。

| 旧カラム | 新カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|---|:--:|---|---|
| `user_id` int(11) **NULL可** | `user_id` char(26) **NOT NULL** + FK → `users` | **型** | **高** | **ログイン失敗でユーザーが特定できない行が1行も入らない。** `auth_outcomes` に `user_not_found` があるのに受け皿が無いという矛盾 | 移行では対応不要（ログを移さないため）。ただし**新環境側の問題として `user_id` を NULL 可にする**（→ [追加一覧](#新環境に追加するテーブルカラム) A16）。`auth_outcomes` に `user_not_found` がある以上、**失敗ログを記録できない設計は cutover 後に効く** |
| `input_password` varchar(200) | — | **性質** | **高** | **入力パスワードを保存している列。** 新に受け皿が無いのは正しい。**移行してはならず、抽出クエリでも SELECT しないこと** | **例外: 移行しない。** **抽出クエリでこの列を SELECT しない**ようにし、レビューで確認する |
| `user_login_result` tinyint(4) | `outcome` varchar(32) + FK → `auth_outcomes` | 性質 | 中 | 8値との対応表が要る（[なし → `auth_outcomes`](#なし--auth_outcomes) を参照） | M3 `auth_outcomes` で作る対応表を使って変換する |
| `web_user_agent` text | `user_agent` varchar(512) NOT NULL DEFAULT '' | 型 | 中 | **text → varchar(512) で切り捨て** | 抽出時に512文字超の件数を検査し、切り捨てる方針を決める |
| `ip_address` varchar(20) NULL可 | `ip_address` varchar(45) NOT NULL | 型 | 低 | 桁は拡大（IPv6 対応）。NULL は '' 補完 | ETL で NULL を空文字に補完する |
| `user_login_time` datetime | `created_at` **timestamp** | 型 | 中 | **`timestamp` 列なのでセッションTZで UTC 変換される。** JST naive を素で書くと9時間ずれる | ETL で JST naive → UTC に変換してから書く。`timestamp` 列であることを列ごとに判定する仕組みに載せる |
| `input_login_id` / `user_logout_time` / `session_id` / `site_type_id` / `recent_access_time` | — | カラム | 低 | **5列とも入れる列が無い。** ログアウト時刻・滞在時間・アクセス元の種別が追えなくなる | 移行では対応不要（ログを移さないため）。**新環境で滞在時間やセッションを追う要件があるなら** `login_history` に5列を追加する（→ [追加一覧](#新環境に追加するテーブルカラム) A16） |
| — | `method` varchar(32) NOT NULL DEFAULT `password` | カラム | 低 | 旧に対応列なし。既定でよい | 既定値に任せる。対応不要 |

**まとめ**: 受け皿が無い列 6 / 変換規則が要る列 4 / **高 2 件**

### `user_login_log_monthly` → なし

`user_login_log_monthly` (5列) ／ ローカルデータ数 146,702 / **A**

**該当テーブルなし。** `login_year` / `login_month` / `site_type_id` / `login_count` の月次集計。

| 旧カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|:--:|---|---|
| テーブル全体 | カラム | 低 | 新は集計を持たず `login_history` から都度計算する | **例外: 追加しない。** 月次集計は `login_history` から都度計算できる |

**まとめ**: 受け皿が無い列 5 / 高 0 件

### `user_login_chk_log` → なし

`user_login_chk_log` (9列) ／ ローカルデータ数 - / -

**該当テーブルなし。** ローカルデータ数が `-` なのは **2026-07-28 ダンプ以降に追加されたテーブル**で実測値が無いため。**ステージングの lw2 にも存在しない。**

| 旧カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|:--:|---|---|
| `login_chk` / `entry_date` / `limit_date` / `valid_chk` / `effective_date` / `batch_date` | 性質 | 中 | **日次バッチ（`UserLoginChkLogBatch`）が作るログ。** `user.entry_date` / `limit_date` / `valid_chk` の状態が前回記録から変わったときだけ1行追加する。現在値は `user` 側にあり、ここにあるのは過去の変遷のみ | **移行しない**（[対象外 B](#移行の対象外移行できないもの--移行しないもの)）。**ステージングの lw2 に存在しない** — `database/20230821_cdss.sql` に DDL はあるが、ステージングの DB には適用されていない。**受け皿も作らない**（当初 A17 として `user_login_periods` を新設したが、移す行が無く新環境に読む実装も無いため取り消した） |

**まとめ**: 受け皿が無い列 9 / 高 0 件

---

## U5 所属・属性の割当

内訳: [breakdown.md](breakdown.md) の同名の節

> 構造は単純な中間表なので**技術的な移行の難しさは無く、純粋に受け皿が無いことだけが問題**。A10 の `tenant_group_members` を追加すればそのまま移せる。

### `user_group` → なし

`user_group` (3列) ／ ローカルデータ数 10,492 / C

**該当テーブルなし。** `group_id` + `user_id` + `regist_date`。

| 旧カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|:--:|---|---|
| テーブル全体 | **テーブル** | **高** | **会員のグループ割当が丸ごと落ちる。** M5 でグループ定義も落ちるため連鎖 | A10 の `tenant_group_members` に移す |

**まとめ**: 受け皿が無い列 3 / **高 1 件**

### `user_attribute` → なし

`user_attribute` (3列) ／ ローカルデータ数 48,600 / C

**該当テーブルなし。** `attribute_id` + `user_id` + `regist_date`。

| 旧カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|:--:|---|---|
| テーブル全体 | **テーブル** | **高** | **会員の属性割当が丸ごと落ちる。** 基盤の中で `user` の次にローカルデータ数が多い | **新の `user_tag_assignments` に移す**（A11。`user_attribute_values`）。手動・自動の区別が旧に無いので `assigned_by` / `rule_id` は NULL。削除済みの属性への割当も移す |

**まとめ**: 受け皿が無い列 3 / **高 1 件**

---

## U6 権限・担当範囲の割当

内訳: [breakdown.md](breakdown.md) の同名の節

### `system_admin_role` → なし

`system_admin_role` (3列) ／ ローカルデータ数 45 / C

**該当テーブルなし。** `tenant_id` + `user_id` + `name` で、**ロールの定義ではなく特定ユーザーへの権限割当**。

| 旧カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|:--:|---|---|
| `user_id` + `name` | 性質 | 中 | 新は `platform_admin` 固定で、**ETL設計 §5-1 が「`platform_admin` は絶対に付けない」としているため、この45名の権限は移行先が無い** | **現状は移していない**（`system_admin_role` を読む実装が無い。2026-10-02 の確認）。ステージングの対象テナント（`tenant_id=10`）は0行。`role_id=1` の会員は `users.role='system_admin'` で入るが、それはこの表とは別。**`platform_admin` は付けない** |

**まとめ**: 受け皿が無い列 3 / 高 0 件

### `instructor_set_lesson` → なし

`instructor_set_lesson` (3列) ／ ローカルデータ数 118 / C

**該当テーブルなし。** 講師の担当講座。

| 旧カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|:--:|---|---|
| `user_id` + `lesson_id` | **テーブル** | **高** | **講師の担当範囲が落ちる。** 新環境の講師紐付けは `courses.instructor_id`（コース1本に講師1人）だけで、**講師が複数コースを担当する構造を表現できない**。なお `courses.instructor_id` は NOT NULL なのに lw2 に講座単位の講師が無いため、**落ちる側と足りない側が同時に起きている**（オンデマンド（未コミット） O01 参照） | `instructor_assignments` を新設して担当講座を移す（→ [追加一覧](#新環境に追加するテーブルカラム) A18）。**`scope='course'` の `target_id` は NULL のまま**で、旧 `lesson_id` を `legacy_target_id` に残す。**講座の移行後に `target_id` を埋める Step は現状は無い**（2026-10-02 の確認）。**基盤で先にテーブルを作って移し**、`courses.instructor_id` の 1:1 見直しはオンデマンド O01 と合わせて行う |

**まとめ**: 受け皿が無い列 3 / **高 1 件**

### `instructor_set_group` → なし

`instructor_set_group` (3列) ／ ローカルデータ数 19 / C

**該当テーブルなし。** 講師の担当グループ。

| 旧カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|:--:|---|---|
| `user_id` + `group_id` | テーブル | 中 | **グループ単位の担当範囲が落ちる。** M5 でグループ定義も落ちるため連鎖。詳細は [`instructor_set_lesson` → なし](#instructor_set_lesson--なし) を参照 | A18 の `instructor_assignments` に `scope='group'` で移す（グループ定義は A10） |

**まとめ**: 受け皿が無い列 3 / 高 0 件

### `instructor_set_attribute` → なし

`instructor_set_attribute` (3列) ／ ローカルデータ数 11 / C

**該当テーブルなし。** 講師の担当属性。

| 旧カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|:--:|---|---|
| `user_id` + `attribute_id` | テーブル | 中 | **属性単位の担当範囲が落ちる。** M5 で属性定義も落ちるため連鎖。詳細は [`instructor_set_lesson` → なし](#instructor_set_lesson--なし) を参照 | A18 の `instructor_assignments` に `scope='attribute'` で移す（属性定義は A11） |

**まとめ**: 受け皿が無い列 3 / 高 0 件

---

## U7 画面状態・個人設定

内訳: [breakdown.md](breakdown.md) の同名の節

### `edit_form_data` → なし

`edit_form_data` (8列) ／ ローカルデータ数 4,752 / B

**該当テーブルなし。** `user_id` + `display_id` + フォーム/検索条件/グリッド状態で、**会員ごとの画面状態**。

| 旧カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|:--:|---|---|
| `display_id` / `form_data` / `search_params` / `grid_data` / `grid_checks` / `search_key` | カラム | 低 | 入力途中のフォーム・検索条件・一覧の並びを入れる列が無い。**いずれも画面を開き直せば作り直される UI の一時状態** | **例外: 移行しない。** 入力途中のフォームや一覧の並びで、cutover 後に作り直される UI の一時状態 |

**まとめ**: 受け皿が無い列 8 / 高 0 件

### なし → `user_preferences`

`user_preferences` (6列, 設定)

**旧に対応テーブルなし。** ユーザーごとの表示設定（1テナント × 1ユーザーで1行、`preferences` json）。lw2 の `edit_form_data` は画面状態であって設定ではないため移行元にならない。空で始まる。

---

## 新環境に追加するテーブル・カラム

**受け皿が無いものは、原則として新環境に追加して受ける。** 「移行しない」は例外で、その都度理由を書く（下の[移行の対象外](#移行の対象外移行できないもの--移行しないもの)）。

以下は**追加案**で、旧環境の構造をそのまま持ってくるのではなく、新環境の作り（ルックアップ表・`tenant_id` 必須・ULID 主キー）に合わせて書き直したもの。**列名と粒度は school-launcher 側の設計レビューで確定する。**

> **migration に落とした形は [マイグレーション対象](schema-additions.md)。** 当てる順序・DDL・ロールバックの注意はそちらにある。

> **DDL を足すだけでは機能しない。** どの項目にも「変更が必要な機能」を併記した。バックエンドは最低でも **構造体（`internal/domain/`）→ repository の SELECT / INSERT / UPDATE → service → DTO（`internal/dto/`）→ handler** の5層、フロントは **型定義（`src/types/`）→ API クライアント → 画面** を触ることになる。以下では**その定型部分は省き、機能として決めが要るところだけ**を挙げている。

### M1 テナント基盤

| # | 追加するもの | 旧環境の対応 | 変更が必要な機能 |
|---|---|---|---|
| **A1** | `tenants.short_name` VARCHAR(64) NULL | `tenant.tenent_name_short`（綴り誤りは踏襲しない） | ・略称をどこに出すか（ヘッダー / 証明書 / メール差出人）を決める<br>・テナント設定画面の入力欄 |
| **A2** | `tenants.language_code` VARCHAR(5) NOT NULL DEFAULT 'ja' | `tenant.language_code` | ・`btoc-frontend/src/i18n/request.ts` の判定を「cookie → テナント既定 → `defaultLocale`」に変更<br>・テナントの既定言語をフロントへ渡す経路<br>・`ja`/`en` 以外なら `src/messages/<locale>.json` の追加 |
| **A3** | `tenants.settings` に `service` / `features` キー | `site.service_name` / `description` / `service_start_date` / `service_end_date` / 機能フラグ4種 | ・`branding` と同じ名前空間方式でパーサを追加<br>・提供期間を使うなら期限切れ時の挙動を決める<br>・**ランキング / テスト分析は機能自体が無い**ので、フラグが ON なら機能追加の要否から決める |
| **A4** | `tenant_limits`（`tenant_id` PK + `max_users` / `max_learners` / `max_user_csv_rows` / `max_enrollments` / `max_enrollment_csv_rows`） | `tenant_limit_value` の5列 | ・会員登録時の上限チェック<br>・CSV 一括登録の件数チェック（登録前に行数で弾く）<br>・受講登録時のチェック<br>・管理画面の上限表示と超過時のメッセージ<br>・`platform_plans` の `max_learners` / `max_courses` と**どちらが優先か**を決める |

### M2 権限・ロール定義

| # | 追加するもの | 旧環境の対応 | 変更が必要な機能 |
|---|---|---|---|
| **A5** | `user_roles` に `system_admin` / `facility_manager` / `company_manager` / `group_manager` / `supporter` の5行を追加（`name_ja` / `sort_order` は `translate_master` と `role_index` から移す。`facility_manager` / `supporter` は削除済みで `active=FALSE`） | `role_master` の8ロールのうち、新環境に対応先が無い5つ | ・`internal/domain/user.go` のロール定数と `enum_validators.go` の `validUserRoles`（現状4値の許可リスト）<br>・`IsRoleInstructorOrAbove` などの判定関数と認可ミドルウェアの判定表<br>・`btoc-frontend/src/types/tenant.ts` の `role` ユニオン型とロール表示<br>・**ブリッジの DTO（`internal/dto/requests_external_user.go`）の `Role` は `oneof=learner instructor tenant_admin` で検証している** — 追加したロールはこのままでは弾かれる<br>・各ロールに何を許すかの線引き（求人企業は就職支援、グループ管理者は A10 のグループ範囲）
| **A19** | `users.is_career_counselor` BOOLEAN NOT NULL DEFAULT FALSE | `user.career_counselor_chk`（`role_id=6` に付く追加フラグ） | ・キャリアカウンセラーが見られる範囲（就職支援 S06 の面談と揃える）<br>・会員編集画面のチェックボックス<br>・**ロールに畳まない**（畳むとグループ管理者の権限が消える）

### M3 認証・ログイン設定

| # | 追加するもの | 旧環境の対応 | 変更が必要な機能 |
|---|---|---|---|
| **A6** | `tenant_sso_configs`（`tenant_id` + `provider` + `metadata` JSON + `active`）＋ `auth_methods` に `saml` | `sso_config`（`sso_type` / `sso_parameter`） | ・ログイン画面に SSO の導線を出す<br>・SAML の認証開始とコールバック<br>・IdP メタデータの登録画面<br>・`auth_outcomes` への結果記録 |
| **A7** | `auth_methods` に `facebook` / `twitter` / `instagram`、`tenant_secret_kinds` に `facebook_client_id` / `facebook_client_secret` / `twitter_client_id` / `twitter_client_secret` / `instagram_client_id` / `instagram_client_secret` と `linkpreview_api_key` | `sns_setting` の6列、`site.linkpreview_api_key` | ・OAuth の開始・コールバック（Google / LINE と同じ経路に相乗り）<br>・ログイン画面のボタン<br>・**移行後、SNS 側の管理画面でコールバック URL を新環境のものに修正する**（データを移しただけでは認証が通らない）<br>・シークレットの**保管と表示のマスク**（`tenant_secrets` は `is_sensitive=TRUE`） |
| **A8** | `tenant_login_windows`（`tenant_id` + `day_of_week` + `start_time` + `end_time`） | `login_limit_*` の5列 | ・ログイン時の時間帯判定<br>・拒否時のメッセージ<br>・管理画面の設定 UI<br>**recademy はローカルデータ数0で移行するデータが無い**ため、優先度は低い |

### M4 会員項目・状態の定義

| # | 追加するもの | 旧環境の対応 | 変更が必要な機能 |
|---|---|---|---|
| **A9** | `tenant_profile_items`（項目定義 + `field_code` + `default_value` + 表示 / 編集 / 必須 / 公開のフラグ）<br>`tenant_profile_item_labels`（`locale` + `label` + `title` + `memo`）<br>`tenant_profile_item_categories`<br>`user_profile_values`（会員ごとの値。**旧 `item_type=1` の自由記述だけがここに入る**。`item_type=0` の値は `users` の対応列＝ A12 / A13 で受ける） | `profile_item`（20項目）/ `profile_item_label` / `profile_item_cate`（5行）/ `profile_item_default` | ・プロフィール画面の項目描画（定義から動的に作る）<br>・会員登録フォームの項目出し分け<br>・表示 / 編集 / 必須 / 他ユーザーへの公開の4制御<br>・会員 CSV の入出力（列が可変になる）<br>・会員検索の絞り込み条件<br>・**既存の `settings.profile_fields`（`birth_year` / `birth_month_day` / `phone` の3項目固定）との統合**（二重管理にしない） |

### M5 組織・属性の定義

| # | 追加するもの | 旧環境の対応 | 変更が必要な機能 |
|---|---|---|---|
| **A10** | `tenant_groups`（`parent_id` で階層。`depth` も持つ）＋ `tenant_group_members` | `group` / `user_group`。**`group_structure` は派生データなので移行しない** | ・グループ管理画面（作成・階層の並べ替え）<br>・会員一覧の絞り込み<br>・**配下グループの絞り込み**（lw2 は閉包テーブルで引いていた。新環境は再帰 CTE か同等の仕組みが要る）<br>・講師の担当範囲（A18）<br>・お知らせ / クーポンの配信対象指定
| **A11** | ~~`tenant_attributes` ＋ `user_attribute_values` ＋ `attribute_required_courses`~~ → **新の `user_tags` ＋ `user_tag_assignments` に一本化**（2026-09-30。旧の「属性」が新の「タグ」。削除済みの属性とその割当も移す（`user_tags.deleted_at`。2026-10-01）。`attribute_lesson` は旧でも講座を結んでいないので移さない。`attribute.kiracari_user_chk` はタグに受け皿が無い） | `attribute` / `user_attribute` / `attribute_lesson` | ・属性管理画面<br>・会員の属性編集と一括付与<br>・**属性による必須講座の自動割当**（受講登録 J01 と揃える）<br>・会員一覧・集計の絞り込み |

### U1〜U4 会員データ

| # | 追加するもの | 旧環境の対応 | 変更が必要な機能 |
|---|---|---|---|
| **A12** | `users.name_last` / `name_first` / `name_kana_last` / `name_kana_first` / `member_no`<br>`user_addresses`（`kind`（`primary`/`secondary`）+ `postal_code` + `prefecture` + `city` + `street`（番地・建物名）+ `country` / `nationality`、1会員2組） | `user.name_sei` / `name_mei` / `kana_sei` / `kana_mei`、`user_personal_no.personal_no`（`regist_no` は現状は移していない）、住所2組（`zip_code` / `pref_id` / `city_name` / `address` ＋ 同 `*2`）、国籍・海外住所 | ・**会員登録フォームとプロフィール編集を姓/名の2欄にする**（現状は `name` 1欄）<br>・**住所入力を4項目に分ける**（郵便番号 / 都道府県は選択式 / 市区町村 / 番地・建物名）。郵便番号からの住所補完を入れるかを決める<br>・`users.name` を分割列から生成する扱いに変え、二重管理にしない<br>・**ブリッジの DTO（`internal/dto/requests_external_user.go` の `Name`）も姓/名に分ける** — 現状は結合済みの1文字列を受けており、**ブリッジ経由で作られた行は後から分割できない**<br>・会員番号の表示・検索（会員に見せていた番号かを確認する）<br>・領収書の宛先と郵送物の送付先<br>・会員 CSV の列（lw2 は姓/名・住所4項目×2組がそれぞれ独立した列）
| **A13** | `user_field_visibility`（`user_id` + `field_code` + `visible`） | `user.*_open_chk` 6列（`field_code` は `profile` / `name` / `address` / `birthday` / `diary` / `lesson`）。`user_attached_info.personal_record_chk`（`personal_record`）は**現状は移していない**（実装が無い。2026-10-02 の確認） | ・プロフィールの他ユーザーへの公開制御<br>・掲示板 / コミュニティでの表示名・属性の出し分け<br>・会員の設定画面（8項目のまま出す）
| **A14** | `users.is_lockout` / `failed_login_started_at` / `failed_login_count` / `last_login_at` / `last_access_at` / `total_login_count` | `user.is_lockout` / `start_date_failing_login` / `number_of_failing_login` / `recent_login_date` / `recent_access_time` / `total_login_count` | ・ログイン失敗時のロックアウト判定としきい値（lw2 は開始日時と連続失敗回数の2本立て）<br>・管理画面からのロック解除<br>・最終ログイン / 最終アクセスの表示と休眠会員の抽出<br>・`total_login_count` の加算箇所（ログイン成功時）
| **A22** | `users.language_code` | `user_nationality_info.language_code`（ステージング実測 `ja` 133名 / `th` 1名） | ・**言語の判定を「cookie → 会員の既定 → テナントの既定（A2）→ `defaultLocale`」に直す**（`btoc-frontend/src/i18n/request.ts`）<br>・会員値をフロントに渡す経路（バックエンドの構造体 / repo / DTO / フロント型の4か所）<br>・プロフィール編集での言語選択 |
| **A23** | `tenant_field_defaults`（`tenant_id` + `field_code` + `default_value`） | `user_item_default`（`item_name` は `profile_item` ではなく **`user` の列名**） | ・会員登録時に既定値を当てる処理<br>・テナント管理画面での既定値設定<br>・**`tenant_profile_items.default_value` と混同しない**（あちらはプロフィール項目の既定値） |
| **A24** | `users.user_id` ＋ `UNIQUE (tenant_id, user_id)`、`tenants.tenant_id` ＋ `UNIQUE` | 旧 `user.user_id` / `tenant.tenant_id` | ・**外部のバッジシステムを引き続き参照する**（`BadgeApi` は `/tenant/{旧テナントID}/user/{旧会員ID}/badges`。バッジキーも `LESSON_{旧 lesson_id}_COMPLETION`）。**これが無いと「誰のバッジか」を新環境から引けない**<br>・移行後の問い合わせ調査で「旧 ID からこの会員を探す」<br>・`courses.legacy_lesson_id` / `lessons.unit_id` はオンデマンドで追加済みだが、**会員とテナントには無かった** |
| **A15** | `user_two_factor_secrets` ＋ `auth_methods` に `totp` | `twostepverification`（ステージング実測 18行。**受け皿を作るだけで、移す行は無い**） | ・2FA の登録・検証フロー<br>・ログイン後のチャレンジ画面<br>・リカバリコードの発行と再設定<br>・テナント単位で 2FA を必須にするかの設定 |
| **A16** | `login_history` に `input_login_id` / `logged_out_at` / `session_id` / `site_type` / `last_access_at` を追加、**`user_id` を NULL 可に**<br>**※ 移行のためではなく、新環境の運用のための改善** | `user_login_log` の該当列（**ログは移行しないので、データは入らない**） | ・**存在しない ID でのログイン試行を記録できるようにする**（現状は `user_id` NOT NULL + FK で記録できず、`auth_outcomes` の `user_not_found` が使えない）<br>・失敗ログを会員に紐付けずに一覧・集計する画面<br>・滞在時間の集計（ログイン〜ログアウト）<br>・セッション追跡とログアウト記録

| **A20** | `users` への列追加: `login_id` / `mobile_email` / `mobile_phone` / `nickname` / `gender` / `blood_type` / `self_introduction` / `login_start_date` / `login_end_date` / `admin_memo` / `external_data` / `password_changed_at` / `is_valid` / `is_new` | `user` の対応する各列（[全列の行き先](#全列の行き先)を参照） | ・**`login_id` でのログイン**（新はメールのみ。lw2 は `utf8_bin` で大文字小文字を区別する）<br>・携帯メール / 携帯電話の入力欄と、通知の宛先切り替え（lw2 は PC / 携帯で通知先を分けている）<br>・ログイン可能期間（`login_start_date` / `login_end_date`）の判定と、期限切れ時の挙動<br>・運営メモ（`admin_memo`）を出す管理画面<br>・`external_data`（連携用フィールド）の用途確認と受け渡し先<br>・会員プロフィールの表示項目（ニックネーム / 性別 / 血液型 / 自己PR） |

| **A21** | `email_kinds` に `announcement` / `scout` / `footprint` / `bbs_comment` を追加<br>`notification_optouts` に `channel`（`pc` / `mobile`）を追加し、UNIQUE を `(tenant_id, user_id, kind, channel)` に | `user.sendmail_pc_chk` / `sendmail_mobile_chk` / `sendmail_scout_chk` / `notify_footprint_pc_chk` / `notify_footprint_mobile_chk`。`sendmail_bbs_comment_pc_chk` / `_mobile_chk` は**現状は移していない**（実装が無い。2026-10-02 の確認） | ・**PC と携帯で宛先を分けて配信する**処理（A20 の `mobile_email` と対。現状は1宛先1種別）<br>・お知らせ / スカウト / 足あと / 掲示板コメントの通知を送る箇所で optout を見る<br>・会員の通知設定画面（種別 × PC / 携帯のマトリクス）<br>・**極性の反転**（lw2 は「受け取る」、新は「受け取らない」） |

### U6 権限・担当範囲の割当

| # | 追加するもの | 旧環境の対応 | 変更が必要な機能 |
|---|---|---|---|
| **A18** | `instructor_assignments`（`tenant_id` + `user_id` + `scope` = `course` / `group` / `attribute` + `target_id`）<br>あわせて `courses.instructor_id`（コース1本に講師1人）の見直し | `instructor_set_lesson` / `instructor_set_group` / `instructor_set_attribute`。**`scope='course'` の `target_id` は NULL のまま**（埋める Step は現状は無い） | ・講師が見られる会員・コースの絞り込み<br>・講師一覧と担当一覧の画面<br>・コース編集権限の判定（`courses.instructor_id` との二重管理を避ける）<br>・**オンデマンド O01 の `courses.instructor_id` NOT NULL 問題**と同時に設計する |

### 移行の対象外（移行できないもの / 移行しないもの）

**いずれも「受け皿が無いから落とす」ではない。** 理由の性質で2つに分かれる。

#### A. 移行できないもの

**移そうとしても成立しない。** 値が新環境で意味を持たないか、持ち出してはいけないもの。

| 対象 | なぜ移行できないか |
|---|---|
| `site.db_server` / `user_id` / `password` / `database` | **lw2 自身の DB への接続情報**で、新環境は別サーバー・別 DB。**移しても接続先が違って機能しない。** 加えて平文で保持されているため、**抽出 → 中間ファイル → 再投入という経路に乗せること自体が漏洩面を増やす**。新環境の接続情報は `tenant_secrets`（`kind='db_dsn'`）に運用で登録するもので、旧環境から移すものではない。**抽出クエリで SELECT しない** |
| `application_config.special_pass_word` | **平文の認証情報**（2026-09-30 にテナントの設定を仕分けたときに確認）。**抽出クエリで SELECT しない**（`tenant.APP_CONFIG_COLUMNS` に含めない） |
| `application_config.kanri_db_name` | **lw2 自身の接続先 DB 名。** `site` の接続情報と同じく、新環境では意味を持たない。**抽出クエリで SELECT しない** |
| `user_login_log.input_password` | **会員が入力したパスワードの平文。** 新環境に保存してよい場所が無く、作ってもいけない。**抽出クエリで SELECT しない** |
| `twostepverification_log` の `input_code` / `correct_code` | **認証コードの平文ログ。** 同上。**抽出クエリで SELECT しない** |
| `twostepverification.verification_code` | **発行中の認証コード**で、有効期限つきの一時値。**移した時点ですでに無効**。機能は A15 で追加する |
| `user_auth_token` / `password_reminder` 全体 | **発行中の一時トークン。** 移しても cutover 後には使えない（新環境が発行し直す） |

#### B. 方針として移行しないもの

**移せるが、移さないと決めたもの。**

| 対象 | 理由 |
|---|---|
| `user_login_log` 全体 | **純ログ**（1,326,645行）。受け皿（`login_history`）はあるが移さず、**cutover 後の認証から記録を始める** |
| `user_login_chk_log` 全体 | **日次バッチが作るログ**（`UserLoginChkLogBatch`）。ログイン可否の状態変化を記録するもので、**ステージングの lw2 には存在しない**（`20230821_cdss.sql` に DDL はあるが未適用）。受け皿（`user_login_periods`）も**作らない** — 移す行が無く、新環境に読む実装も無いため |
| `user_login_log_monthly` 全体 | **純ログの月次集計。** `login_history` から都度計算できる |
| `twostepverification_log` 全体 | **純ログ**（加えて上記 A のとおり平文の認証コードを含む） |
| `attribute_lesson` 全体 | **旧でも講座を結んでいない**（作成時に `attribute_id` だけの行を作る）。属性はタグに一本化したので受け皿も使わない（A11。2026-09-30） |
| `group_structure` 全体 | **派生データ**（1,313行）。`group.parent_group_id` から作り直される閉包テーブルで、lw2 自身がグループの作成・削除のたびに全消し＋再生成している |
| `edit_form_data` 全体 | **旧環境自身が3日で消す**（`EditFormDataModel::create()` が毎回 `DELETE FROM edit_form_data WHERE regist_date <= DATE_ADD(NOW(), INTERVAL -3 DAY)` を実行）。中身は管理画面の入力途中と **`onetime_token`（一回限りのトークン）** で、移した時点で無効。画面を開き直せば作り直される。**ステージング実測1行** |
| `user.user_img_file_name` / `user_img_file_name1` | **プロフィール画像は移行対象外**（運営の判断）。`avatar_url` の列は使うが空で始め、会員が登録し直す |
| `role_id` が NULL の会員 | **ロールが決まらないため移せない**（`users.role` は NOT NULL ＋ `user_roles(code)` への FK）。既定値に倒すと**権限が静かに変わる**ので倒さない。ステージング（2026-09-18 取得）の該当は `user_id=911` の1名で、`zentai001` を `user_id=483` と共有する重複アカウント。**受講0件・グループ0件・属性0件・一度もログインなし**、メールも57名が共有する値で、移して困るデータが無い（2026-09-22 決定）。**本番ダンプでは該当者を取り直し、実データを持つ会員が含まれていないかを確認する** |


#### 現状は移していないもの（実装が無い）

**決定ではなく、移行ツールに実装が無いために移っていないもの**（2026-10-02 の確認）。上の A / B とは性質が違い、移すかどうかの判断も済んでいない。

| 対象 | 状態 | ステージング（`tenant_id=10`） |
|---|---|---|
| `user_attached_info.personal_record_chk` | A13 の `user_field_visibility`（`personal_record`）で受ける想定だったが、Step は `user` の6列しか読まない | 87名に値あり |
| `user_attached_info.line_entry_chk` | `line_links` の Step が参照しない | — |
| `user.sendmail_bbs_comment_pc_chk` / `_mobile_chk` | `notification_optouts` の Step が読む5列に入っていない | 全員に値あり（ほぼ全員が `0`） |
| `user_personal_no.regist_no` | `personal_no` だけを `users.member_no` に入れている | 3,155名全員に値あり |
| `system_admin_role` | 読む実装が無い | 0行 |
| `attribute.kiracari_user_chk` | `user_tags` に受け皿が無い | 7件中1件が `1` |
| `instructor_assignments.target_id`（`scope='course'`） | NULL のまま。講座の移行後に埋める Step が無い（`legacy_target_id` に旧 `lesson_id` は残る） | — |

---

## 投入順序（この区分の実行計画）

**新環境に入っているのは migration のシード値だけ**で、`tenants` / `users` / `external_user_links` はいずれも空から始まる。移行ツールのフェーズは2つ（`migrator/phases/registry.py`）。

```
[migration]      M1 tenant_statuses / tenant_db_types / tenant_secret_kinds   ← シード（投入済み）
                 M2 user_roles / M3 auth_methods / auth_outcomes / M4 user_statuses
                    ↓
[foundation.1]   マスター
                 不足値: user_roles に5ロール / tenant_statuses に deleted /
                         auth_methods に SNS・SAML・TOTP / email_kinds に通知種別
                 ← いずれも `tenant_id` を持たないグローバルマスタ。FK の参照先を先にそろえる
                 tenants の1行（recademy）← ここで採番した `tenants.id` が全テーブルの `tenant_id` になる
                 テナント設定: tenant_limits / tenant_field_defaults / tenant_secrets /
                               tenant_profile_item_categories → tenant_profile_items → *_labels
                 定義: tenant_groups / user_tags / tenant_sso_configs / tenant_login_windows
                    ↓
[foundation.2]   ユーザ
                 users → external_user_links
                 user_addresses / user_profile_values / user_field_visibility / notification_optouts
                 tenant_group_members / user_tag_assignments / instructor_assignments
                    ↓
[support.1]      line_links（LINE。区分はサポート機能）
```

**U4 `login_history` と U7 `user_preferences` は図に現れない。** ログは移行せず cutover 後の認証から記録を始め、個人設定は旧に対応データが無い。

---

## テナントの設定（2026-09-30 に仕分け）

どの区分にも仕分けていなかったテナントの設定6表を、基盤として `tenants.settings` に入れる（新に対応する列が無いため）。

| 旧 | `tenants.settings` のキー | 備考 |
|---|---|---|
| `application_config` | `lw2_config` | 秘密の値は入れない。LINE のチャネルシークレット・アクセストークンは `tenant_secrets`（`line_channel_secret` / `line_channel_access_token`）。`special_pass_word` / `kanri_db_name` は移行できないもの（上の「移行の対象外 A」） |
| `account_setting` | `lw2_account` | パスワードの規則・ロックアウト（新は読まない。features F01 / F02） |
| `login_setting` | `lw2_login` | ログイン画面の文言・ログイン後のお知らせ |
| `registration_setting` | `lw2_registration` | 会員登録画面の文言・画像 |
| `top_parts_setting` | `lw2_top_parts` | トップページの部品の並び |
| `function_default_tenant` / `function_admin_tenant` / `function_admin_role` | `lw2_functions` | メニューと管理画面の機能ごとの権限 |

