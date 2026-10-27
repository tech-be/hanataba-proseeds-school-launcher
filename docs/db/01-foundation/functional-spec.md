# 基盤 — 新システムの機能仕様（移したデータの見え方）

移行の見直しの手順 1（[進捗](../rework-progress.md)）。**新システムが、基盤のデータをどう読み書きするか**を、移したデータがどう見えるかの観点で書き出したもの。
手順 2 のテスト仕様書（`test-spec.md`）と、手順 3 の移行仕様の材料にする。

- **基準**: school-launcher `hanataba_dev` の `584026af`（2026-10-24）。コードは git から読んだ（`git show 584026af:<path>`）。
- **コードの場所**は、school-launcher のリポジトリからの相対パス。`btoc-backend/internal/` は `internal/`、`btoc-frontend/src/` は `frontend/` と略す。
- **未確認**と書いたものは、コードから推論しただけで、動かして確かめていない。

## 0. 新システムが使っていない表・列

基盤で移している表・列のうち、次のものは新アプリのコード（`internal/`・`libs/`・`frontend/`・career-backend）から一度も読み書きされていない。migration・seed・文書にだけ出てくる（git grep で確認）。
**移しても、新アプリの動きには効かない。**

| 表・列 | 旧での意味 | 新での扱い |
|---|---|---|
| `users.is_valid` / `login_start_date` / `login_end_date` | 有効・無効、ログインできる期間 | ログインを止めない。止めるのは `users.status` だけ |
| `users.is_lockout` / `failed_login_count` / `failed_login_started_at` | ロックアウト | ログインを止めない。新のロックアウトは Redis（メール＋IP ごとに 10 秒 3 回、10 回で 15 分。`libs/auth/authlimit/limiter.go`） |
| `users.last_login_at` / `total_login_count` / `password_changed_at` / `is_new` | ログインの記録など | 読まない |
| `users.is_career_counselor` | キャリアカウンセラー | 読まない |
| `users.member_no` | 会員番号（2026-10-22 から書いていない） | 読まない |
| `users.name_last` / `name_first` | 姓・名 | 読まない。表示名は `users.name` だけ |
| `users.mobile_phone` / `mobile_email` / `language_code` / `self_introduction` / `blood_type` / `admin_memo` | 携帯・言語・自己紹介・血液型・運営メモ | 読まない。メールの宛先は `users.email` だけ |
| `users.user_id`（旧 ID） | — | 読まない |
| `tenants.short_name` / `language_code` | 略称・既定の言語 | 読まない。画面の言語は cookie `locale` だけで決まる（`frontend/i18n/request.ts:10-20`） |
| `tenants.settings` の `service` / `features` / `lw2_*` | 旧の運用値・機能フラグ・設定 | 読まない |
| `tenant_limits` | 会員数などの上限 | 読まない。上限を確かめる処理が無い |
| `tenant_field_defaults` | 登録時の既定値 | 読まない |
| `tenant_profile_item_categories`、`tenant_profile_items.category_id` / `default_value`、`tenant_profile_item_labels.memo_free` | プロフィール項目の分類など | 読まない |
| `tenant_profile_items` の `item_type = 0`（固定項目） | 固定項目の表示・必須の設定 | 読まない。**固定項目の設定は `tenants.settings.profile_fields`** にある（4-2） |
| `user_field_visibility` | 公開範囲 | 読まない。扱う画面が無い |
| `tenant_login_windows` | ログインできる曜日・時間帯 | 読まない |
| `tenant_sso_configs` | SSO の設定 | 読まない |
| `tenant_secrets` の `facebook_` / `twitter_` / `instagram_` の client id・secret、`linkpreview_api_key` | SNS ログイン・リンクのプレビュー | 読まない。Google ログインは環境設定の値を使う |
| `scout_display_types` | スカウトの表示名の種類 | 外部キー先としてだけ存在。選択肢はコードに直書き |
| `tenant_groups`（階層の `parent_id` / `depth`） | グループの階層 | 階層は読まない（5-3 の CSV で直接の所属だけ） |
| `instructor_assignments` | 講師の担当範囲 | 読まない。講師はロールだけで判定され、テナントのすべての講座を扱える |
| `user_roles` の `system_admin` / `group_manager` / `company_manager` / `supporter` / `facility_manager` | 旧のロール | 判定に出てこない（3-6） |

## 1. テナント

### 1-1. テナントの解決

- **利用者**: 全員（システムの処理）
- **読む**: `tenants WHERE slug=?`（または `id=?`・`custom_domain=?`）。解決の順は `X-Tenant-Slug` ヘッダ → Host のサブドメイン（`<slug>.<ベースドメイン>`）→ 独自ドメイン。Redis に 5 分キャッシュする。
  - **`tenants.status` では絞らない。** suspended・deleted のテナントもそのまま動く。
  - 認証済みの API は、JWT の `tenant_id` と解決したテナントを比べ、違えば 403。
  - フロントは Host のサブドメインから slug を取る（`www`・`admin` は除く）。
- **コード**: `internal/tenant/resolver.go:29-81`、`internal/middleware/tenant.go:20-47`、`internal/middleware/tenant_match.go:14-31`、`frontend/middleware.ts:5-34`
- **移したデータが満たすべきこと**: `slug` は一意で、英小文字・数字・ハイフンの 3〜63 字（`www`・`admin` は不可）。`status` は `tenant_statuses` にある値（アプリが遷移を許すのは active / suspended / trial）。

### 1-2. テナントの一般設定・運営によるテナントの管理

- **利用者**: テナント管理者、platform_admin
- **画面・API**: `/admin/settings` の「一般設定」、`GET/PATCH /api/v1/tenant/settings`、`/api/v1/platform/tenants`
- **読む**: `tenants` の `id, slug, name, db_type, plan_id, settings, custom_domain, status, created_at, updated_at`
- **書く**: `name`・`status`・`settings`。**画面は `branding` 以外の `settings` を JSON の文字列のまま編集させ、丸ごと置き換える**（キーを消せば消える）。テナント管理者の経路では status を無視する。
- **コード**: `internal/handler/tenant_handler.go:89-120`、`internal/service/tenant_service.go:190-221`、`frontend/app/(tenant)/admin/settings/_components/general-settings.tsx:27-78`
- **移したデータが満たすべきこと**: `settings` は有効な JSON オブジェクト。`name` は 1〜255 字（メールの差し込みにも使う）。

### 1-3. `tenants.settings` のキー

新アプリが読むキーは次のとおり。保存はキーごとに読んで差し替える（merge）。

| キー | 中身 | 無い・壊れているとき | コード |
|---|---|---|---|
| `line` | `enabled`, `official_account_id`, `add_friend_message`, `notification_kinds[]`, `login_channel_id` | 無効 | `internal/line/domain/line.go:27-48,122-151` |
| `profile_fields` | `{"fields":{<key>:{enabled,required,at_signup}}}`（固定項目の設定） | 既定値で補う。知らないキーは捨てる | `internal/domain/profile_fields.go:345-423` |
| `branding` | `logo_url`・`favicon_url`（ストレージのキー）、`primary_color`、`accent_color`、`footer_text`、`hero_title`、`hero_subtitle` | 空 | `internal/handler/tenant_handler.go:249-286` |
| `payment` | `methods[]`, `konbini_expires_after_days`, `bank_account_info` | 既定の支払い方法 | `internal/commerce/domain/payment_methods.go:120-193` |
| `referral` | 紹介の報酬など | 無効 | `internal/referral/domain/referral_config.go:16-60` |
| `community` | `auto_create_course_channel` | false | `internal/community/domain/community_config.go:11-19` |
| `application_form` | 申込フォームの表示項目 | 既定値 | `internal/learning/domain/application_form_config.go:13-61` |
| `help_chat_rollout` | `percent`, `allow_user_ids[]` | 0% | `internal/domain/help_chat_rollout.go:22-44` |
| `top_catalog` | `categories[]`, `order[]`, `banners[]` | 空 | `internal/repository/catalog_repo.go:14-36,128` |

### 1-4. ブランディング（ランディングページ）

- **利用者**: 未ログインの訪問者（表示）、テナント管理者（編集）
- **画面・API**: `GET /api/v1/branding`（認証なし）、`PATCH /api/v1/tenant/branding`、`/` のヒーロー
- **読む**: `settings.branding` と `tenants.name`。ロゴ等はストレージのキーから 24 時間有効の署名つき URL を作る。`hero_title` が空なら既定の文言。
- **コード**: `internal/handler/tenant_handler.go:289-375,856-901`
- **移したデータが満たすべきこと**: 色は hex、footer 500 字・hero_title 100 字・hero_subtitle 300 字以内。`logo_url` / `favicon_url` は URL ではなくストレージのキー。

## 2. 認証

### 2-1. ログイン（メールまたはログイン ID ＋ パスワード）

- **利用者**: 全会員
- **画面・API**: `/login`（欄は「メールアドレスまたはログインID」）、`POST /api/v1/auth/login`（`{email, password}`。`email` にログイン ID も入る）
- **読む**:
  1. 入力を trim・小文字化して `users WHERE tenant_id=? AND email=?`（`email` は `utf8mb4_unicode_ci`）
  2. 無ければ入力を**そのまま**（trim なし）`users WHERE tenant_id=? AND login_id=?`（`login_id` は `utf8mb4_bin`。大文字小文字を区別）
  3. 判定の順: 該当なし → 401／`status='pending'` → 401（`email_not_verified`）／bcrypt の照合に失敗 → 401／`status != 'active'` → 401「このアカウントは現在利用できません」
- **書く**: `login_history`（失敗は `invalid_password` / `account_inactive`。会員が見つからないときは記録しない）
- **コード**: `internal/handler/auth_handler.go:145-180`、`internal/service/auth_service.go:470-534`、`internal/repository/user_repo.go:108-120`
- **移したデータが満たすべきこと**:
  - `password_hash` は Go の `x/crypto/bcrypt` で照合できる bcrypt（新が作るのは `$2a$`・コスト 10。`libs/auth/password.go:20-31`）。空ならパスワードでログインできない。
  - `status` は active / inactive / pending / deleted のどれか（ログインできるのは active だけ）。
  - `email` はテナント内で大文字小文字を無視して一意。メールが無い会員は空文字ではなく NULL。
  - `login_id` はテナント内で一意、空白・制御文字を含まない。**メールの無い会員は `login_id` が無いとログインできない。**
  - ある会員の `login_id` が別の会員のメールと同じ文字列だと、メールの持ち主が当たる。

### 2-2. パスワードの変更の強制（`must_change_password`）

- **利用者**: 移した会員
- **画面・API**: ログインの応答の `user.must_change_password` が true なら `/change-password` へ遷移（`frontend/app/(auth)/login/page.tsx:90-101`、`frontend/app/(tenant)/layout.tsx:153-158`）。`POST /api/v1/auth/change-password`
- **書く**: `password_hash`、`must_change_password = FALSE`（`internal/repository/user_repo.go:279-289`）
- **新しいパスワードの基準**: 10 字以上・72 バイト以内、前後の空白不可、英字と数字が必須、弱いパスワード 15 個は不可（`libs/auth/password.go:85-119`）
- **強制するのは画面だけ。** API はパスワードを変える前でも使える。
- **参考**: `cmd/import-passwords` が、旧の 3DES を復号して bcrypt にし、`must_change_password = TRUE` にする（`btoc-backend/cmd/import-passwords/main.go:281-322`）。

### 2-3. 会員の自己登録

- **画面・API**: `/register` → `/verify-email`、`POST /auth/register`・`/auth/verify-email`・`/auth/check-email`
- **読む**: `GetByEmail`。既存の会員が pending なら確認メールを再送、それ以外（active / inactive / deleted）は 409「既に登録されています」
- **書く**: `users`（learner・pending・パスワード空）。確認でパスワードを入れて active にする。登録で聞く項目は `settings.profile_fields` の設定どおり。
- **コード**: `internal/service/auth_service.go:204-431`、`internal/repository/user_repo.go:160-188`
- **移したデータが満たすべきこと**: **退会した会員のメールが元のまま残っていると、そのアドレスで登録できない**（409）。新の退会処理は `deleted_<ULID>@anonymized.invalid` に書き換える（5-4）。

### 2-4. パスワードの再設定

- **画面・API**: `/forgot-password` → メールのリンク `/reset-password`
- **読む**: `GetByEmail`。**`status='active'` の会員だけ**が対象。トークンは 15 分。
- **書く**: `password_hash`、`must_change_password = FALSE`、全セッションを失効
- **コード**: `internal/service/auth_service.go:896-1051`
- **移したデータが満たすべきこと**: メールが NULL の会員（ログイン ID だけ）は使えない。

### 2-5. LINE ログインと LINE の連携

- **利用者**: 受講者、未ログインの訪問者
- **画面・API**: `/login`・`/register` の LINE ボタン（`GET /auth/line/status` が available のときだけ出る）、`GET /auth/line`、`GET /api/v1/auth/line/callback`、`/settings` の LINE の連携
- **読む**:
  - 使えるのは `settings.line.enabled = true` で、`settings.line.login_channel_id` と `tenant_secrets`（`line_login_channel_secret`）の**両方**があるときだけ（`internal/line/domain/line.go:78-86`）。全テナント共通の値は無い。
  - 会員は `users WHERE tenant_id AND oauth_provider='line' AND oauth_provider_id=?` で探す。無くて同じメールの会員がいれば 409、どちらも無ければ新規作成。`status` が active でなければ 401。
- **書く**: 新規の会員（メールが無ければ `line_<id>@placeholder.invalid`）、連携は `line_links`
- **コード**: `internal/handler/oauth_line_handler.go:53-216`、`internal/service/auth_service.go:546-640`、`internal/line/service/line_service.go:99-219`
- **移したデータが満たすべきこと**: 旧で LINE ログインしていた会員を LINE で識別させるには、`users.oauth_provider='line'` と、新のログインチャネルのプロバイダーで発行される LINE の userId（`oauth_provider_id`）が要る。

### 2-6. 旧システムからの SSO と外部 ID の対応表

- **利用者**: 旧システム（内部トークンで呼ぶ）
- **API**: `POST /internal/tenants/:tenantId/users/import`、`POST /internal/tenants/:tenantId/sso/tickets`、`POST /api/v1/auth/ticket`
- **読み書き**: `external_user_links`（(テナント, システム, 外部 ID) と (テナント, システム, 会員) の両方で一意）。取り込みは、未登録の会員を作り、紐付いた会員の name / status / role / email を同期する（role は tenant_admin / instructor 以外を learner、status は inactive / deleted 以外を active にする）。チケットは 60 秒・1 回限りで、active の会員だけ。
- **コード**: `internal/service/external_user_import_service.go:56-410`、`internal/server/routes_internal.go:42-48`
- **移したデータが満たすべきこと**: `external_system` は 32 字・`external_id` は 64 字以内、`user_id` は users にあること。

### 2-7. その他の認証の経路

- トークンの更新: 会員を読み直し、active でなければ 401（`internal/service/auth_service.go:737-810`）
- パスキー: active を確かめる（`internal/service/passkey_service.go:263`）
- 運営のセルフサインアップ: `POST /api/v1/signup` でテナントと tenant_admin を作る

## 3. 会員の管理（運営）

### 3-1. 会員の一覧・検索・CSV

- **利用者**: テナント管理者・platform_admin（講師は 403）
- **画面・API**: `/admin/users`（見出し「ユーザー管理」、「N 名」）、`GET /api/v1/tenant/users?role=&status=&limit=&offset=`（limit は 100 まで）
- **読む**: `users WHERE tenant_id=? [AND role=?] [AND status=?] ORDER BY created_at DESC`。**削除済みの会員も除かずに並べる。**
- **画面**: 列は名前・メール・ロール（選択）・ステータス（選択）・登録日。検索は取得した 1 ページの中だけ。ロールの選択肢は learner / instructor / tenant_admin、ステータスは active / inactive / pending。CSV は表示中のページだけ。
- **コード**: `internal/repository/user_repo.go:128-146,315-327`、`frontend/app/(tenant)/admin/users/page.tsx`
- **移したデータが満たすべきこと**: 4 つ以外のロール・`deleted` は選択肢に無い値として出る。ログイン ID は一覧に出ない（詳細だけ）。

### 3-2. 会員の詳細・ロール / ステータス / ログイン ID の変更

- **画面**: 詳細のドロワー（メール・ロール・ステータス・ログイン ID・登録日・更新日・ID）、詳細ページ `/admin/users/:id`（住所・独自項目・通知設定・スカウトの表示名）
- **書く**: `PATCH /tenant/users/:id/role`（tenant_admin / instructor / learner のどれか。deleted の会員は変えられない）、`/status`（active / inactive / pending。deleted からは戻せない）、`/login-id`（重複は 409）
- **画面に出ないもの**: フリガナ・ニックネーム・性別・生年月日・電話は運営の画面に出ず、運営からは変えられない。
- **コード**: `internal/service/user_service.go:169-280`、`frontend/components/admin/user-detail-drawer.tsx`、`frontend/app/(tenant)/admin/users/[userId]/page.tsx:26-118`

### 3-3. 会員の追加と CSV の一括取り込み

- **画面・API**: `/admin/users/new`（メール・ログイン ID・名前・ロール）、`/admin/users/import`（CSV `email,name,login_id`、1,000 行まで）
- **書く**: 新しい会員は active・ランダムのパスワードで作り、招待メールを送る。**CSV に既にいる会員は作り直さず、ログイン ID だけを CSV の値に合わせる。**
- **コード**: `internal/service/user_provisioning.go:93-163`、`internal/service/roster_import_service.go:100-260`

### 3-4. ロールで決まる画面・API

- **判定**: `RequireRole` が JWT のロールの文字列と完全一致で比べる（`internal/middleware/auth.go:85-100`）。管理系は platform_admin / tenant_admin、講師系は加えて instructor（`internal/server/routes.go:37-41`）。管理画面に入れるのは tenant_admin / platform_admin / instructor（`frontend/lib/roles.ts`）。
- **旧のロール**（system_admin / group_manager / company_manager / supporter / facility_manager）: `user_roles` に行があるだけで、判定に出てこない。**その会員は管理画面にも管理 API にも入れず、受講者と同じ扱いになる**（ログインと受講者向けの API は使えるはず。未確認）。`user_roles.is_admin` / `is_instructor` も読まない。
- **`user_roles.name_ja`**: 受講者のコース別進捗の CSV でだけ読む（`internal/repository/learner_analytics_repo.go:560-580`）
- **移したデータが満たすべきこと**: `users.role` は `user_roles.code` にある値（外部キー）。

## 4. 会員のプロフィール

### 4-1. 本人のプロフィール編集（`/settings`）

- **利用者**: 受講者本人
- **画面・API**: `/settings` のプロフィール、`GET/PATCH /api/v1/me/profile`
- **読む**: `users` の `name, email, birth_year/month/day, phone, name_kana_last/first, nickname, gender, avatar_url` と `user_addresses`。表示と必須は `settings.profile_fields` で決める。
- **書く**: 上の列（変えた項目だけ）
- **値の検証**: name は空不可・255 字。生年は 1900 年以上で 13 歳以上。月日は実在する日付。phone は数字 9〜15 桁。gender は 1（男性）/ 2（女性）。
- **コード**: `internal/service/user_service.go:51-113,283-342`、`internal/domain/user.go:136-277`
- **移したデータが満たすべきこと**: `gender` は 1・2・NULL のどれか。`birth_*` は上の範囲（外れた値も表示はされるが、本人がその項目を変えて保存すると 400）。`name` は空でない。**表示名は `users.name` だけ**なので、姓・名から組み立てて入れておく。
- **補足**: 登録直後のプロフィール入力（`/profile-setup`）は、移した会員は通らない。

### 4-2. プロフィール項目の設定（運営）

- **画面・API**: `/admin/settings` の「入力項目」、`GET/PUT /api/v1/tenant/profile-fields`
- **固定項目**: **保存先は `tenants.settings.profile_fields`**（`tenant_profile_items` の `item_type = 0` ではない）。項目は name, name_kana, nickname, email, gender, address, birth_year, birth_month_day, phone, career_*。name・email は表示・必須で固定。
- **独自項目**: `tenant_profile_items i LEFT JOIN tenant_profile_item_labels l ON l.item_id=i.id AND l.locale='ja' WHERE i.tenant_id=? AND i.item_type=1 ORDER BY i.item_no`。**ラベルは `locale='ja'` だけを読む。** 保存は 1 トランザクションで、送った順に `item_no` を振り直す。一覧から外した項目は消さずに使わない状態にする。行は 1000 件まで。
- **検証**: 名前は空不可・100 字、注記は 500 字。表示しない項目は必須・公開・複数行を落とす。
- **コード**: `internal/handler/tenant_handler.go:937-1162`、`internal/domain/profile_fields.go:94-547`、`internal/repository/tenant_profile_item_repo.go:28-201`
- **移したデータが満たすべきこと**: 独自項目は `item_type = 1` で、すべてに `locale='ja'` の空でないラベル（100 字以内）を付ける。**守らないと、この画面の保存全体が 400 になる。** 旧の固定項目の設定を効かせるなら `settings.profile_fields` に入れる。`open_flag` は保存するだけで、読む処理は無い。

### 4-3. 独自項目の値（本人と運営）

- **画面・API**: 本人 `GET/PUT /api/v1/profile-values`（`/settings`）、運営 `GET/PUT /api/v1/tenant/users/:id/profile-values`（`/admin/users/:id`）
- **読む**: 項目は 4-2 と同じ。値は `user_profile_values WHERE tenant_id=? AND user_id=?`。本人には表示しない項目を見せない。
- **書く**: 空文字は行を消す。本人は表示・編集できる項目だけ。複数行でない項目は改行を空白にする。255 字以内。
- **コード**: `internal/service/user_profile_value_service.go:91-161`、`internal/repository/user_profile_value_repo.go:26-93`
- **移したデータが満たすべきこと**: `item_id` は同じテナントの `item_type = 1` の項目。`value` は 255 字以内。空文字の行は作らない（未入力は行が無いこと）。

### 4-4. 住所

- **画面・API**: 本人 `PATCH /me/profile` の addresses、運営 `PATCH /tenant/users/:id/addresses`
- **読む**: `user_addresses WHERE tenant_id AND user_id ORDER BY kind`。kind は primary / secondary / foreign。
- **画面**: primary / secondary は郵便番号・都道府県・市区町村・番地、foreign は国・国籍・郵便番号・市区町村・番地。
- **コード**: `internal/domain/user_address.go:18-131`、`internal/repository/user_address_repo.go:24-64`、`frontend/components/profile/address-fields.tsx:88-187`
- **移したデータが満たすべきこと**: kind は 3 つのどれかで (会員, kind) は一意。上限は郵便番号 16・都道府県 10・市区町村 100・番地 400・国 64・国籍 64 字。primary / secondary の国・国籍と、foreign の都道府県は画面に出ない。

### 4-5. 通知の受け取り設定

- **画面・API**: `/settings` の「通知」、`/admin/users/:id`、`GET/PUT /api/v1/notification-preferences`（運営は `/tenant/users/:id/notification-preferences`）
- **読む**: 選択肢は `email_kinds WHERE user_optional=TRUE AND active=TRUE AND deprecated_at IS NULL`（learning_reminder, live_reservation_reminder, retention_reminder, weekly_report, referral_reward, announcement_published, announcement, scout, footprint, bbs_comment）。状態は `notification_optouts WHERE tenant_id AND user_id` の `kind`。
  - **`channel`（pc / mobile）はどこでも見ない。** 行が 1 つでもあれば、その種類のメールも LINE も止まる。
  - 送る前の判定（`IsOptedOut`）は `user_optional` を見ない。
- **書く**: 保存は置き換え。**channel に関係なく全行を消し、`channel='pc'` で入れ直す。**
- **コード**: `internal/notification/repository/preference_repo.go:22-168`、`internal/service/email_service.go:252-258`
- **移したデータが満たすべきこと**: `kind` は `user_optional = TRUE` の種類だけ（password_reset などが入ると、そのメールが止まり画面から解除できない）。**`channel='mobile'` の行も PC のメールと LINE を止める。**

### 4-6. スカウトの表示名と個別番号

- **画面・API**: `/settings` の「通知」、`/admin/users/:id`、`GET/PUT /api/v1/scout-display`（運営は `/tenant/users/:id/scout-display`）
- **読む**: `user_personal_numbers WHERE tenant_id AND user_id`。**行が無ければ開いた時点で採番する**（`MAX(regist_no)+1`、`personal_no` はその数字の文字列、表示は name）。
- **書く**: `scout_display_type`
- **使い道**: 設定を保存するだけで、表示名として使う処理はまだ無い。
- **コード**: `internal/repository/user_personal_number_repo.go:47-152`、`internal/domain/scout_display.go:13-62`
- **移したデータが満たすべきこと**: `personal_no` はテナント内で一意・32 字以内。`regist_no` はテナント内で一意の整数（新しい会員は最大＋1）。`scout_display_type` は name / nickname / personal_no。旧の `personal_no` と `regist_no` の大小が逆転していると、新しい採番が既存の `personal_no` と重なりうる（やり直しで避ける。未確認）。

### 4-7. LINE の設定（運営）と LINE への通知

- **画面・API**: `/admin/line`、`GET/PUT /api/v1/tenant/line-settings`
- **読む**: `settings.line`。シークレット（`line_channel_secret` / `line_channel_access_token` / `line_login_channel_secret`）は設定済みかどうかだけを返す。選べる通知の種類は、`email_kinds` の有効なもののうち、コードの対応表（welcome, learning_reminder, payment_succeeded, payment_failed, subscription_created, subscription_canceled, live_reservation_confirmed, live_reservation_reminder, referral_reward, retention_reminder, announcement_published）にあるものだけ。
- **書く**: `settings.line`、`tenant_secrets`（空文字は「変えない」）
- **検証**: ON にするには、公式アカウント ID・ログインチャネルの ID・ログインチャネルのシークレット・アクセストークンの 4 つが要る。ログインチャネルの ID は数字 20 桁以内。
- **通知**: `settings.line.enabled` が true、`notification_kinds` にその種類があり、`line_links` があって友だちで、アクセストークンがあるときだけ LINE に送る。その前に 4-5 の受け取り設定が効く。
- **コード**: `internal/line/handler/admin_handler.go:91-181`、`internal/line/service/admin.go:47-196`、`internal/line/service/line_service.go:258-316`
- **移したデータが満たすべきこと**: **`notification_kinds` には対応表の値だけを入れる。** 画面は保存済みの値をそのまま送り返すので、対応表に無い値があると、**運営は LINE の設定を一切保存できない**（400）。`official_account_id` は「@」で始まる。

### 4-8. プライバシー・退会

- **画面・API**: `/settings` の「プライバシー」、`GET /api/v1/me/export`、`POST /api/v1/me/delete-account`
- **退会の書き込み**: メールを `deleted_<ULID>@anonymized.invalid`、ログイン ID とパスワードを空、名前を「削除済みユーザー」、フリガナ・ニックネーム・性別・生年月日・電話・アバター・oauth を NULL、`status='deleted'`、`anonymized_at`。住所・独自項目の値・個別番号・通知の設定と、旧から移した列（携帯のメールなど）は残る。
- **コード**: `internal/service/privacy_service.go:54-140`、`internal/repository/user_repo.go:297-313`
- **移したデータが満たすべきこと**: 退会した会員は `status='deleted'`・`login_id` NULL。メールは NULL か匿名化したもの（実在のアドレスが残ると再登録できない。2-3）。

### 4-9. オンボーディングのウィザード

- 受講者のホームと `/courses` に出る。**表示するかはブラウザの localStorage（`onboarding-completed:<userId>`）だけで決まり、DB は見ない。** 移した受講者には、各ブラウザでの初回ログイン時に必ず出る。
- **コード**: `frontend/hooks/use-onboarding.ts:19-36`

## 5. 組織

### 5-1. タグの管理

- **利用者**: テナント管理者・platform_admin（講師は 403）
- **画面・API**: `/admin/tags`、`GET/POST /api/v1/tenant/tags`、`PATCH/DELETE /api/v1/tenant/tags/:id`
- **読む**: `user_tags WHERE tenant_id=? ORDER BY sort_order, name, id`。**`deleted_at` は読まない。** 移した削除済みのタグも、一覧・選択肢・条件の候補に出る。
- **書く**: 追加・名前の変更・物理削除（会員への割当と自動割当の条件も外部キーで消える）。自動割当の条件で使われていれば削除は 409。
- **コード**: `internal/repository/user_tag_repo.go:21-105`、`internal/service/user_tag_service.go:61-112`
- **移したデータが満たすべきこと**: `(tenant_id, name)` が一意（**削除済みのタグも同じ一意制約にかかる**）。名前 100 字・メモ 200 字以内。

### 5-2. 会員へのタグの付け外し

- **画面・API**: 会員の詳細のドロワーのタグ欄（**ロールが learner の会員だけ**）、`GET/POST /api/v1/tenant/users/:userId/tags`、`DELETE .../tags/:tagId`
- **読む**: `user_tag_assignments a JOIN user_tags t ON t.id=a.tag_id AND t.tenant_id=a.tenant_id WHERE a.tenant_id=? AND a.user_id=?`。削除済みのタグの割当も出る。`rule_id` があれば「自動」の印。
- **コード**: `internal/repository/user_tag_assignment_repo.go:23-79`、`frontend/components/admin/user-tags-section.tsx`
- **移したデータが満たすべきこと**: 割当とタグの `tenant_id` が一致。(会員, タグ) が一意。

### 5-3. 受講者のコース別進捗の CSV（グループ名・グループコード・属性名）

- **画面・API**: `/admin/users/:id/insights` の「CSV で保存」、`GET /api/v1/tenant/analytics/learners/:userId/learning-paths/export`
- **読む**: グループは `tenant_group_members JOIN tenant_groups ON ... AND g.deleted_at IS NULL`（名前とコードをつなぐ。階層は読まない）。**属性名は `user_tags` ではなく `tenant_attributes`（`deleted_at IS NULL`）と `user_attribute_values`。** ユーザー種別は `user_roles.name_ja`。
- **コード**: `internal/repository/learner_analytics_repo.go:558-588`、`internal/service/learner_path_progress.go:26-29,150-190`
- **移したデータが満たすべきこと**: 削除済みのグループは `deleted_at` を入れれば CSV に出ない。属性名を出すには `tenant_attributes` / `user_attribute_values` に入っていること。
- **新アプリに無いもの**: グループの管理画面、グループ管理者による絞り込み、会員の一覧のタグ・グループでの絞り込み。

### 5-4. タグの自動付与のルール（受講・課金で使う）

- タグは自動付与のルールの条件（`tag_auto_assign_rule_conditions`）で使われる。会員のタグの判定もタグの `deleted_at` を見ないので、**削除済みのタグを持つ会員も条件に当たる**。自動付与は `user_tag_assignments` には書かない（`rule_id` 付きの割当は移したデータにだけある）。詳しくは区分 04 で扱う。
- **コード**: `internal/service/tag_auto_assign_service.go`、`internal/repository/tag_auto_assign_rule_repo.go:44-216`

## 6. 新システムの E2E（参考）

共通の前提（`e2e/helpers.ts`）: ホストは `http://demo.localhost:3000`（テナント `demo`）。パスワードは `password123`。シードの会員（`learner1@demo.local`・`admin@demo.local`・`instructor@demo.local`・`platform@neo-lw.local` など）はログイン ID を持たず、すべて active。`login()` は `/login` の `#email`・`#password` に入れて送信し、429 は 5 回まで押し直す。`apiLogin()` は `POST /api/v1/auth/login` に `X-Tenant-Slug` を付ける。

| ファイル | 確かめていること |
|---|---|
| 01-learner-login | 受講者が画面でログインするとトップに着き、ユーザーメニューが出る |
| 06-admin-users | 会員の一覧（見出し・メール・「N 名」・ロールの選択）、会員の追加、既存のメールでの追加は拒否 |
| 24-user-registration | 登録画面の欄と検証、登録済みメールの判定、LINE ボタンの出し分け、確認メールからのパスワード設定 |
| 61-instructor-role | 講師が使える画面・API と、使えない API（会員一覧など 403）。担当範囲による制限は確かめていない |
| 62-platform-admin | platform_admin のテナントの一覧・作成・改名、他のロールでは 401/403 |
| 65-signup-password-reset | 運営のセルフサインアップ、名簿 CSV で作った受講者のパスワード再設定（mailpit） |
| 38-multi-tenant-isolation | テナントごとのログイン、テナントをまたいだ読み取りができないこと |
| 13-privacy-settings | プライバシーの画面（書き出し・同意・退会の確認） |
| 21-onboarding-wizard | ウィザードの表示と、完了・スキップ後に出ないこと |
| 22-settings | 表示名の変更、パスワード変更の検証、通知のスイッチが保存されること |
| 72-line-settings | LINE の設定の保存・読み戻し・検証、選べる通知の種類、LINE ログインの出し分け |
| 78-admin-member-notification-scout | 運営と本人の通知設定・スカウトの表示名・個別番号 |
| 79-admin-profile-fields-values | 独自項目の追加・入力・運営の編集・255 字の上限 |
| 85-profile-field-settings-ui | 固定項目の必須・住所を使わない設定・登録時に聞く項目 |
| 12-landing-page-branding | ブランディングの保存と既定の文言 |
| 78-learner-path-progress（一部） | コース別進捗の CSV のヘッダとユーザー種別 |

**E2E が確かめていないこと**（テスト仕様書で補う）: ログイン ID でのログイン、パスワードの変更の強制の画面遷移、無効・削除済みの会員のログイン拒否、LINE ログインの実際の通し、タグの管理画面。

## 7. 未確認

- bcrypt の `$2y$` / `$2b$` を受けるか（リポジトリ内に確かめるコードが無い）
- `login_id`（`utf8mb4_bin`）の末尾の空白の扱い
- 旧のロールの会員の実際の動き（コードからの推論だけ）
- `tenants.status='deleted'` を運営のテナント管理がどう扱うか
- 個別番号の採番が、旧の番号と重なったときの動き
- 自動付与のルールを更新したとき、グループの条件（`tag_auto_assign_rule_group_conditions`）が消えるか
