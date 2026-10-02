# 基盤 — 機能の差分

基盤のデータ（テナント・会員・ロール・認証）を**使う機能**を1つずつ挙げ、新旧でどう違うかを書く。
書き方の約束（判定・差分の種類・深刻度・対応の書き方）は [ひな形](../00-template/features.md) を参照。

- **調査時点:** 2026-09-29
  - 旧: `learningware-kiracari`
  - 新: `school-launcher` の `hanataba_dev`（`feat/lw2-billing-schema` と同じ地点）
- **根拠の場所の書き方:**
  - 旧は `learningware-kiracari/` からの相対パス。
  - 新は `btoc-backend/` / `btoc-frontend/` からのパス。
- データの受け皿（A1〜A24）は [突き合わせ](review.md#新環境に追加するテーブルカラム) を参照。**この文書は「受け皿に入れたデータを新の機能が読んでいるか」を見る**

> **要点。** 基盤で足した受け皿（A1〜A24）は、**`user_addresses` を除いて新の機能から1つも読まれていない。**（2026-09-30: 属性は新のタグ `user_tags` に移すようにしたので、属性は新で読まれる）
> データは移っているが、旧で効いていた制限（ログイン期間・ロックアウト・無効フラグ）、表示（会員番号・姓名の分割・公開設定）、権限（8ロール・講師の担当範囲・グループ）は、**新の機能を直さない限り切り替えと同時に消える。**
> とくに次の3つは、**旧で止めていたことが新ではできてしまう**。
>
> - ログインの制限が効かない（F01）
> - 旧ロールの会員が受講者として入れる（F08）
> - 通知設定を保存すると携帯の設定が消える（F13）

---

## 機能の一覧

| ID | 機能 | 利用者 | データ種 | 判定 | 差分（高 / 中 / 低） | 未決 |
|---|---|---|---|:--:|:--:|--:|
| F01 | ログイン | 全員 | B02 / B03 / B04 / B05 | △ | 2 / 4 / 2 | 3 |
| F02 | パスワードの再設定・変更 | 全員 | B05 | △ | 1 / 1 / 2 | 1 |
| F03 | SSO・SNS ログイン | 全員 | B10 | △ | 1 / 1 / 0 | 2 |
| F04 | 二要素認証 | 全員 | B12 | X | 0 / 1 / 0 | 1 |
| F05 | ログイン履歴 | 管理者・受講者 | B09 | △ | 0 / 2 / 2 | 0 |
| F06 | 会員の管理（管理画面） | 管理者 | B06 | △ | 1 / 4 / 1 | 2 |
| F07 | プロフィール（会員自身） | 受講者 | B06 | △ | 0 / 4 / 2 | 0 |
| F08 | ロールと権限 | 管理者・講師 | B02 | △ | 1 / 2 / 1 | 2 |
| F09 | グループ | 管理者 | B07 | X | 0 / 1 / 0 | 1 |
| F10 | 属性（タグ）と自動割当 | 管理者 | B08 | △ | 0 / 1 / 1 | 1 |
| F11 | 会員の一意 ID（会員番号） | 管理者・受講者 | B11 | X | 0 / 1 / 0 | 0 |
| F12 | テナントの設定 | 管理者 | B01 | △ | 0 / 1 / 2 | 0 |
| F13 | 通知の受信設定 | 受講者 | B06 | △ | 1 / 2 / 0 | 2 |
| F14 | 外部システムとの連携 | — | B01 / B06 | △ | 0 / 1 / 1 | 2 |

---

## 各機能

### F01 ログイン

利用者: 全員 ／ データ種: B02 ロール、B03 メールログイン、B04 login_id ログイン、B05 パスワード ／ 判定: **△ 差分あり**

- 旧: `application/models/AuthModel.class.php` の `login()`（123行〜）/ `_findUserMainByLoginIdAndPassword()`、`application/modules/default/controllers/LoginController.php` の `_lockout()` / `_auth()`、時間帯の制限は `library/AbstractController.class.php` の `_chkLoginLimit()`
- 新: `POST /api/v1/auth/login` → `btoc-backend/internal/service/auth_service.go` の `Login` ／ 画面 `https://<slug>.<ドメイン>/login`（`btoc-frontend/src/app/(auth)/login/page.tsx`）

#### 参照データ

| データ | 旧（テーブル.列） | 新（テーブル.列） | 旧で使う | 新で使う | 差分 |
|---|---|---|:--:|:--:|---|
| ログイン ID | `user.login_id` | `users.login_id` | ◯ | — | 新はメールアドレスでログインする |
| メールアドレス | `user.mail_add` | `users.email` | — | ◯ | 旧はログインに使っていない |
| パスワード | `user.password`（3DES） | `users.password_hash`（bcrypt） | ◯ | ◯ | 移行時に入れ替え済み |
| 削除・状態 | `user.del_chk` | `users.status` | ◯ | ◯ | 新は `active` だけを通す |
| 有効フラグ | `user.valid_chk` | `users.is_valid` | ◯ | — | 新は読まない |
| ログイン期間 | `user.entry_date` / `user.limit_date` | `users.login_start_date` / `users.login_end_date` | ◯ | — | 新は読まない |
| ロックアウト | `user.is_lockout` / `start_date_failing_login` / `number_of_failing_login` | `users.is_lockout` / `failed_login_started_at` / `failed_login_count` | ◯ | — | 新は読まない。書きもしない |
| 最終ログイン・回数 | `user.recent_login_date` / `total_login_count` | `users.last_login_at` / `total_login_count` | ◯ | — | 新は更新しない |
| ログインの時間帯 | `login_limit` | `tenant_login_windows` | ◯ | — | 新は読まない（recademy は0件） |
| 同時接続数の上限 | `application_config.login_limit_count` | — | ◯ | — | 受け皿も機能も無い |
| 接続元 IP の制限 | `application_config.allowed_ip` | — | ◯ | — | 受け皿も機能も無い |

#### 差分

| 種類 | 深刻度 | 内容 | 対応 |
|---|:--:|---|---|
| 参照データ | 高 | 旧は `login_id` でログインし、新はメールアドレスでログインする。会員が入力するものが変わる | 未決: 新でログイン ID でもログインできるようにするか、メールアドレスに切り替えると会員に案内するかを決める（[E1](../open-questions.md#e-切り替え後の機能で決めておきたいこと)） |
| 振る舞い | 高 | 新は `status = 'active'` とパスワードしか見ない。旧で無効・ログイン期間外・ロックアウト中だった会員もログインできる | 新でログイン時に `is_valid` / `login_start_date` / `login_end_date` / `is_lockout` を読む |
| 振る舞い | 中 | 旧のロックアウトはテナント設定（`account_setting` の `lockout_period` / `lockout_limit`）で会員ごとに持つ。新は Redis で15分止めるだけで、管理画面から解除もできない | 未決: 会員ごとのロックアウトを新で持つか、Redis の一時停止で足りるかを決める（[E2](../open-questions.md#e-切り替え後の機能で決めておきたいこと)） |
| 機能 | 中 | 旧にあった同時接続数の制限（直近1時間にアクセスした会員数で判定）が新に無い | 未決: 運営に使っているかを確認する（[E3](../open-questions.md#e-切り替え後の機能で決めておきたいこと)） |
| 機能 | 中 | 旧にあった接続元 IP の制限（`allowed_ip`）が新に無い | 運営に使っているかを確認する |
| 振る舞い | 中 | 新はログインしても最終ログイン日時・ログイン回数を更新しない。移した値が切り替え時点で止まる | 新でログイン成功時に `last_login_at` / `total_login_count` を更新する |
| 機能 | 低 | 旧にあったログインの時間帯制限（受講者だけ）が新に無い | 対応不要。recademy は設定が0件 |
| 機能 | 低 | 旧の「ログイン状態を保持」（ログイン ID とパスワードを暗号化して cookie に30日）と URL での自動ログイン（`?l=&p=`）が新に無い | 対応不要。パスワードを cookie や URL に載せる方式で、新に持ち込まない |

### F02 パスワードの再設定・変更

利用者: 全員 ／ データ種: B05 パスワード ／ 判定: **△ 差分あり**

- 旧: 再設定は `application/modules/default/controllers/ReminderController.php` と `LoginController.php` の `authenticationAction()`。変更の強制は `_initForced()` / `forcedAction()`。規則はテナント設定 `account_setting`
- 新: `POST /api/v1/auth/forgot-password` / `reset-password` → `auth_service.go` の `issuePasswordSetupToken` / `ResetPassword` ／ 画面 `/forgot-password`、`/reset-password`、`/settings`

#### 参照データ

| データ | 旧（テーブル.列） | 新（テーブル.列） | 旧で使う | 新で使う | 差分 |
|---|---|---|:--:|:--:|---|
| 最終変更日 | `user.password_change_date` | `users.password_changed_at` | ◯ | — | 新は読まない。書きもしない |
| 再設定の受付 | `password_reminder` | Redis のトークン | ◯ | ◯ | 移さない（発行中の一時値） |
| 送り先 | `user.mail_add` / `mobile_mail_add` | `users.email` | ◯ | ◯ | 旧は携帯メールにも送れた |

#### 差分

| 種類 | 深刻度 | 内容 | 対応 |
|---|:--:|---|---|
| 機能 | 高 | **ログイン中のパスワード変更ができない。** 画面（`btoc-frontend/src/app/(tenant)/settings/page.tsx`）は `PUT /api/v1/users/me/password` を呼ぶが、バックエンドにこの API が無い | 新でパスワード変更の API を実装する |
| 機能 | 中 | 旧のパスワード規則（英大文字・小文字・数字・記号・最小文字数・ID と同じは不可）、有効期限、初回ログイン時の変更の強制が新に無い。新は8文字以上だけ | 未決: 運営に旧の規則を引き継ぐかを確認する（[E4](../open-questions.md#e-切り替え後の機能で決めておきたいこと)） |
| 振る舞い | 低 | 再設定の入力が「ログイン ID ＋メールアドレス」から「メールアドレス」だけになる。リンクの有効期限は30分から15分になる | 対応不要。F01 のログイン ID の扱いが決まれば案内に含める |
| 振る舞い | 低 | 旧は再設定のリンクを開くと元のパスワードのままログインさせていた。新は新しいパスワードを設定させる | 対応不要。新の方式の方が安全 |

### F03 SSO・SNS ログイン

利用者: 全員 ／ データ種: B10 SSO ／ 判定: **△ 差分あり**（Google / LINE / パスキーはある。SAML / Facebook / X は無い）

- 旧: SAML は `application/modules/default/controllers/SsoController.php`（設定は `sso_config`、画面は `admin/SsoConfigController`）。SNS は `LoginController.php` の Facebook / Twitter の分岐（設定は `sns_setting`）
- 新: `routes_auth.go` の Google / LINE、`routes_passkey.go` のパスキー、`auth_service.go`

#### 参照データ

| データ | 旧（テーブル.列） | 新（テーブル.列） | 旧で使う | 新で使う | 差分 |
|---|---|---|:--:|:--:|---|
| SAML の設定 | `sso_config.sso_type` / `sso_parameter` | `tenant_sso_configs` | ◯ | — | 新は読まない |
| SNS の鍵 | `sns_setting` の `facebook_*` / `twitter_*` / `instagram_*` | `tenant_secrets`（`facebook_*` など） | ◯ | — | 新は読まない。Instagram は旧でも無効化されていた |

#### 差分

| 種類 | 深刻度 | 内容 | 対応 |
|---|:--:|---|---|
| 機能 | 高 | 新に SAML の SSO が無い。旧で SSO を有効にしていたテナントは、会員が IdP 経由でログインできなくなる（旧は SSO のとき、フォームでは管理者だけがログインできた） | 未決: recademy が SSO を有効にしているか（`sso_config.sso_type`）を確認し、使っていれば新で実装する（[E5](../open-questions.md#e-切り替え後の機能で決めておきたいこと)） |
| 機能 | 中 | 新に Facebook / X のログインが無い | 未決: 運営に使っているかを確認する（[E6](../open-questions.md#e-切り替え後の機能で決めておきたいこと)） |

### F04 二要素認証

利用者: 全員（テナント設定で受講者だけにもできる）／ データ種: B12 二要素認証 ／ 判定: **X 新に無い**

- 旧: `LoginController.php` の `_initTwoStep()` / `twostepAction()`、管理画面 `admin/TwoStepVerificationController.php`。設定は `application_config.twostep_*`
- 新: 無い（`user_two_factor_secrets` は受け皿だけ）

#### 差分

| 種類 | 深刻度 | 内容 | 対応 |
|---|:--:|---|---|
| 機能 | 中 | 旧はメールで7桁のコードを送り、3回間違えるとログアウトさせていた。新に二要素認証が無い（パスキーはあるが二要素ではない） | 未決: recademy が有効にしているか（`application_config.twostep_chk`）を確認し、使っていれば新で実装する（[E7](../open-questions.md#e-切り替え後の機能で決めておきたいこと)） |

### F05 ログイン履歴

利用者: 管理者（一覧・CSV）・受講者（ログインカレンダー）／ データ種: B09 ログイン履歴 ／ 判定: **△ 差分あり**

- 旧: 管理画面 `application/modules/admin-user/controllers/LoginLogController.php`、月別回数は `UserController::_outputCsvLoginMonthly()`、受講者のログインカレンダーは `LoginCalendarModel`
- 新: `auth_service.go` が `login_history` に書く。API は `GET /tenant/login-history`（本人）/ `GET /tenant/users/:id/login-history`（管理者）

#### 参照データ

| データ | 旧（テーブル.列） | 新（テーブル.列） | 旧で使う | 新で使う | 差分 |
|---|---|---|:--:|:--:|---|
| ログインの記録 | `user_login_log` | `login_history` | ◯ | ◯ | 移さない（純ログ）。新は切り替え後から記録する |
| 入力されたログイン ID など | `user_login_log.input_login_id` / `session_id` / ログアウト時刻 | —（A16 は未適用） | ◯ | — | 受け皿も無い |
| 月別のログイン回数 | `user_login_log_monthly` | — | ◯ | — | 移さない（集計） |

#### 差分

| 種類 | 深刻度 | 内容 | 対応 |
|---|:--:|---|---|
| 画面 | 中 | 新にログイン履歴の画面が無い（API はあるが呼ぶ画面が無い）。旧は管理画面で期間・ログイン ID・IP・結果で絞り込み、CSV に出せた | 新で管理画面のログイン履歴を実装する |
| 機能 | 中 | 旧の月別ログイン回数（会員一覧・CSV）と受講者のログインカレンダーが新に無い | 新で `login_history` から集計して出す |
| 参照データ | 低 | 新は存在しない ID でのログイン試行を記録できない（`user_id` が必須）。失敗の理由（期間外・ロック）も持たない | 新で `login_history` を広げる（A16） |
| 振る舞い | 低 | 切り替え前のログイン履歴は新で見えない | 対応不要。純ログとして移さない方針 |

### F06 会員の管理（管理画面）

利用者: 管理者 ／ データ種: B06 会員プロフィール ／ 判定: **△ 差分あり**

- 旧: `application/modules/admin-user/controllers/UserController.php`（検索は `UserModel::_buildSql()`、CSV の列は `_getKeysForUser()`）、上限は `tenant_limit_value`
- 新: `routes_tenant_admin.go` の `GET/POST /tenant/users`、`PATCH /users/:id/role` / `status`、`POST /learners/import`（`service/roster_import_service.go`）／ 画面 `admin/users`

#### 参照データ

| データ | 旧（テーブル.列） | 新（テーブル.列） | 旧で使う | 新で使う | 差分 |
|---|---|---|:--:|:--:|---|
| 氏名・メール・ロール・状態 | `user` | `users.name` / `email` / `role` / `status` | ◯ | ◯ | 新で編集できるのはロールと状態だけ |
| 運営メモ | `user.user_memo` | `users.admin_memo` | ◯ | — | 新は読まない |
| 人数の上限 | `tenant_limit_value` | `tenant_limits` | ◯ | — | 新は読まない（`platform_plans.max_learners` も未使用） |
| 登録時の既定値 | `user_item_default` | `tenant_field_defaults` | ◯ | — | 新は読まない |
| 会員番号 | `user_personal_no.personal_no` | `users.member_no` | ◯ | — | F11 |

#### 差分

| 種類 | 深刻度 | 内容 | 対応 |
|---|:--:|---|---|
| 機能 | 高 | 管理者が会員の氏名・メールアドレス・ログイン期間・有効フラグなどを編集できない。新で変えられるのはロールと状態だけ | 新で会員の編集画面を実装する |
| 機能 | 中 | 検索がロールと状態だけ。旧は氏名・カナ・ログイン ID・メール・グループ・属性・ログイン可否・最終ログイン・運営メモ・会員番号で絞り込めた | 新で会員検索の条件を実装する |
| 機能 | 中 | CSV 一括登録の列がメールアドレスと氏名だけ。旧は姓名・住所・電話・ロール・グループ・属性・通知設定・プロフィール項目など約50列 | 未決: 新の CSV に載せる列を運営と決める（[E8](../open-questions.md#e-切り替え後の機能で決めておきたいこと)） |
| 機能 | 中 | 人数の上限（会員数・受講者数・CSV の行数）を新は見ない | 未決: `tenant_limits` と `platform_plans` のどちらで制限するかを決める（[E9](../open-questions.md#e-切り替え後の機能で決めておきたいこと)） |
| 機能 | 中 | 旧のロック解除・有効フラグの一括変更が新に無い | 新で実装する（F01 のロックアウトの扱いと合わせる） |
| 参照データ | 低 | 運営メモ・登録時の既定値（`profile_open_chk` の1件だけ）を新は読まない | 新で会員の編集画面に運営メモを出す |

### F07 プロフィール（会員自身）

利用者: 受講者 ／ データ種: B06 会員プロフィール ／ 判定: **△ 差分あり**

- 旧: `application/modules/default/controllers/ProfileController.php`（編集・公開設定）、項目の定義は `ProfileItemModel`
- 新: `GET/PATCH /api/v1/me/profile` → `service/user_service.go` ／ 画面 `/settings`。言語は `btoc-frontend/src/i18n/request.ts`

#### 参照データ

| データ | 旧（テーブル.列） | 新（テーブル.列） | 旧で使う | 新で使う | 差分 |
|---|---|---|:--:|:--:|---|
| 氏名 | `user.name_sei` / `name_mei` / `kana_sei` / `kana_mei` | `users.name_last` / `name_first` / `name_kana_*` | ◯ | — | 新は結合した `users.name` 1欄だけを読む |
| 住所 | `user` の住所2組・海外住所 | `user_addresses` | ◯ | ◯ | 新も読む |
| 生年月日・電話 | `user.birth_date` / `tel` | `users.birth_*` / `phone` | ◯ | ◯ | — |
| その他の項目 | `user.nick_name` / `sex_type` / `blood_type` / `self_introduction` / `mobile_tel` | `users.nickname` / `gender` / `blood_type` / `self_introduction` / `mobile_phone` | ◯ | — | 新は読まない |
| 項目の定義 | `profile_item` / `profile_item_label` / `profile_cate` | `tenant_profile_items` など | ◯ | — | 新は読まない（新は `settings.profile_fields` の3項目だけ） |
| 自由記述の項目 | `user.user_profile1〜20` | `user_profile_values` | ◯ | — | 新は読まない |
| 公開設定 | `user.*_open_chk`、`user_attached_info.personal_record_chk` | `user_field_visibility` | ◯ | — | 新は読まない。**`personal_record_chk` は現状は移していない**（実装が無い。2026-10-02 の確認） |
| 言語 | `user_nationality_info.language_code`、`tenant.language_code` | `users.language_code`、`tenants.language_code` | ◯ | — | 新は cookie だけで決める |

#### 差分

| 種類 | 深刻度 | 内容 | 対応 |
|---|:--:|---|---|
| 参照データ | 中 | 姓・名・カナが1欄の氏名になり、カナが見えなくなる | 新でプロフィールを姓名の分割とカナに対応させる（A12） |
| 機能 | 中 | テナントが定義したプロフィール項目（20項目。表示・編集・必須・公開の制御）が新に無い | 新でプロフィール項目を実装する（A9） |
| 機能 | 中 | 他の会員への公開設定（プロフィール・受講講座・誕生日など）が新に無い。旧は `profile_open_chk` で会員一覧に出すかを絞っていた | 新で公開設定を実装する（A13） |
| 振る舞い | 中 | 表示言語を会員・テナントの設定から決めない。タイ語の会員（ステージング1名）も日本語で表示される | 新で言語の判定を「cookie → 会員 → テナント → 既定」にする（A2 / A22） |
| 参照データ | 低 | ニックネーム・性別・血液型・自己紹介・携帯電話が見えない | 新でプロフィールの表示項目を足す（A20） |
| 振る舞い | 低 | 旧は初めてログインした受講者をプロフィール編集へ誘導していた（`new_user_chk`）。新は誘導しない | 対応不要。`users.is_new` は残してある |

### F08 ロールと権限

利用者: 管理者・講師 ／ データ種: B02 ロール ／ 判定: **△ 差分あり**

- 旧: `application/models/AuthModel.class.php` の `findAuthByUserId()` / `isReadForAdminUrl()`（機能ごとの権限表 `function_admin_*`）、講師の担当範囲は `library/SqlUtil.class.php`
- 新: `btoc-backend/internal/domain/user.go` のロール定数、`internal/middleware/auth.go` の `RequireRole`、フロントは `btoc-frontend/src/lib/roles.ts`

#### 参照データ

| データ | 旧（テーブル.列） | 新（テーブル.列） | 旧で使う | 新で使う | 差分 |
|---|---|---|:--:|:--:|---|
| ロール | `user.role_id`（8種） | `users.role` / `user_roles` | ◯ | ◯ | 新のコードが扱うのは4種だけ |
| キャリアカウンセラー | `user_attached_info.career_counselor_chk` | `users.is_career_counselor` | ◯ | — | 新は読まない |
| 講師の担当範囲 | `instructor_set_lesson` / `_group` / `_attribute` | `instructor_assignments` | ◯ | — | 新は読まない |

#### 差分

| 種類 | 深刻度 | 内容 | 対応 |
|---|:--:|---|---|
| 権限 | 高 | 新のコードが扱うロールは `platform_admin` / `tenant_admin` / `instructor` / `learner` の4つ。旧のシステム管理者・運営管理者・企業担当者・グループ管理者・サポーターで移した会員は、ログインはできるが全ての権限判定で落ち、**受講者と同じ扱い**になる。管理画面でもこのロールを選べない | 未決: 旧ロールごとに新で何を許すかを決め、新の権限判定に足す（A5）（[E10](../open-questions.md#e-切り替え後の機能で決めておきたいこと)） |
| 権限 | 中 | 講師の担当範囲（講座・グループ・属性）が新に無い。新の講師はテナント全体を見られる | 新で講師の担当範囲を実装する（A18） |
| 権限 | 中 | 旧の機能ごとの権限表（会員・ロール・テナント単位で管理画面の機能を ON/OFF）が新に無い | 未決: 運営に使っているかを確認する（[E11](../open-questions.md#e-切り替え後の機能で決めておきたいこと)） |
| 参照データ | 低 | キャリアカウンセラーのフラグ（グループ管理者に面談を開かせる）を新は読まない | 新で就職支援の面談と一緒に実装する |

### F09 グループ

利用者: 管理者（グループ管理者はグループの範囲だけ）／ データ種: B07 グループ ／ 判定: **X 新に無い**

- 旧: `application/modules/admin-user/controllers/GroupController.php`、`GroupModel`。グループ管理者の範囲は `SqlUtil::getLimitGroup()`（配下のグループまで含む）
- 新: 無い（`tenant_groups` / `tenant_group_members` は受け皿だけ）

#### 差分

| 種類 | 深刻度 | 内容 | 対応 |
|---|:--:|---|---|
| 機能 | 中 | 階層つきのグループと所属が新に無い。旧はグループをグループ管理者の範囲、会員一覧の絞り込み、お知らせ・メール・アンケートの配信先に使っていた | 未決: グループを新で実装するか、どの用途から実装するかを決める（A10）（[E12](../open-questions.md#e-切り替え後の機能で決めておきたいこと)） |

### F10 属性（タグ）と自動割当

利用者: 管理者 ／ データ種: B08 属性 ／ 判定: **△ 差分あり**（2026-09-30 に新のタグ・自動付与ルールへ移すようにした）

- 旧: `application/modules/admin-user/controllers/AttributeController.php`、自動割当は `admin/ConfigAutoassignController` と `UserController::_autoAssign()`
- 新: 受講者のタグ（`user_tags` / `user_tag_assignments`）と、購入・会員登録で動く自動付与ルール（`tag_auto_assign_*`）。**旧の「属性」が新の「タグ」**

#### 参照データ

| データ | 旧（テーブル.列） | 新（テーブル.列） | 旧で使う | 新で使う | 差分 |
|---|---|---|:--:|:--:|---|
| 属性 | `attribute` | `user_tags`（`attribute_id`） | ◯ | ◯ | 削除済みも移す（`user_tags.deleted_at` を足した。2026-10-01。新のアプリはまだ読まない）。`kiracari_user_chk` の受け皿は無い |
| 会員の属性 | `user_attribute` | `user_tag_assignments` | ◯ | ◯ | 削除済みの属性の割当も移す（2026-10-01） |
| 自動割当 | `assign` ほか | `tag_auto_assign_*` | ◯ | ◯ | 03 F09 |
| 属性の必須講座 | `attribute_lesson` | — | — | — | 旧でも講座を結んでいない。移さない |

#### 差分

| 種類 | 深刻度 | 内容 | 対応 |
|---|:--:|---|---|
| 振る舞い | 中 | 旧の自動割当は会員の登録・購入・編集のたびに動いた。新のルールは「購入」か「会員登録」のどちらかで発動する | 未決: 移したルールの発動のきっかけ（暫定の規則 P15）でよいかを運営と決める（[E13](../open-questions.md#e-切り替え後の機能で決めておきたいこと)） |
| 参照データ | 低 | 削除済みの属性（1件）とその割当（2,550件）も移す（`user_tags.deleted_at`。2026-10-01）。**新のアプリは `deleted_at` を読まないので、削除済みのタグが一覧と会員に出る** | 新でタグの一覧・割当から `deleted_at` の行を除く |

### F11 会員の一意 ID（会員番号）

利用者: 管理者・受講者 ／ データ種: B11 マイナンバー（実体は会員の一意 ID）／ 判定: **X 新に無い**

- 旧: `UserModel` が会員の作成時に `personal_no` を振る。管理画面の会員一覧・詳細・スカウト、受講者自身のプロフィールに出し、検索・CSV にも使う
- 新: 無い（`users.member_no` に移してあるが、表示も検索もしない）

#### 差分

| 種類 | 深刻度 | 内容 | 対応 |
|---|:--:|---|---|
| 機能 | 中 | 会員番号が新のどこにも出ない。旧は受講者自身にも見せていたので、問い合わせで番号を伝える運用があれば困る | 新で会員番号を管理画面とプロフィールに出し、検索できるようにする |

### F12 テナントの設定

利用者: 管理者 ／ データ種: B01 テナント ／ 判定: **△ 差分あり**

- 旧: `tenant`（`tenant_name` をメールの `{SERVICE_NAME}` に使う）、機能の ON/OFF は `application_config`
- 新: `GET/PATCH /tenant/settings` → `service/tenant_service.go` ／ 画面 `admin/settings`

#### 参照データ

| データ | 旧（テーブル.列） | 新（テーブル.列） | 旧で使う | 新で使う | 差分 |
|---|---|---|:--:|:--:|---|
| 名称 | `tenant.tenant_name` | `tenants.name` | ◯ | ◯ | — |
| 略称 | `tenant.tenent_name_short` | `tenants.short_name` | — | — | 旧でも読んでいない |
| 言語 | `tenant.language_code` | `tenants.language_code` | ◯ | — | F07 |
| サービス名・提供期間・機能フラグ | `site` | `tenants.settings` の `service` / `features` | — | — | 旧でも読んでいない。新の設定画面では JSON のまま見える |
| 状態 | `tenant.del_chk` | `tenants.status` | ◯ | ◯ | 新のコードは `deleted` を知らない |

#### 差分

| 種類 | 深刻度 | 内容 | 対応 |
|---|:--:|---|---|
| 振る舞い | 中 | 新のコードは状態 `deleted` を知らず、`deleted` のテナントは検証で落ちる | 新のテナントの状態に `deleted` を足す。recademy は `active` なので移行には効かない |
| 参照データ | 低 | 略称とサービス名・提供期間・機能フラグは新で読まない | 対応不要。旧でも読んでいない |
| 画面 | 低 | 移した `settings` のキー（`service` / `features` / `legacy_site_id` など）が設定画面の JSON 欄にそのまま見える | 対応不要。保存しても消えない |

### F13 通知の受信設定

利用者: 受講者 ／ データ種: B06 会員プロフィール ／ 判定: **△ 差分あり**

- 旧: `application/models/MailModel.class.php` の `createSendMail()`（`sendmail_pc_chk` / `sendmail_mobile_chk` で宛先を絞る）、送信バッチは PC はメール、携帯は携帯メールに送る
- 新: `GET/PUT /api/v1/notification-preferences` → `btoc-backend/internal/notification/repository/preference_repo.go`

#### 参照データ

| データ | 旧（テーブル.列） | 新（テーブル.列） | 旧で使う | 新で使う | 差分 |
|---|---|---|:--:|:--:|---|
| 受け取らない種別 | `user.sendmail_*_chk`（受け取る） | `notification_optouts.kind` | ◯ | ◯ | 極性が逆（移行時に反転済み） |
| PC / 携帯 | `sendmail_pc_chk` / `sendmail_mobile_chk` | `notification_optouts.channel` | ◯ | — | 新は読まない |
| 携帯メール | `user.mobile_mail_add` | `users.mobile_email` | ◯ | — | 新は読まない |
| 通知の種別 | お知らせ・スカウト・足あと・掲示板コメント | `email_kinds` の `announcement` / `scout` / `footprint` / `bbs_comment` | ◯ | △ | 設定画面には出るが、送る処理が無い |

#### 差分

| 種類 | 深刻度 | 内容 | 対応 |
|---|:--:|---|---|
| 振る舞い | 高 | **会員が通知設定を保存すると、移した携帯の設定が消える**（全行を消して `channel` 無しで入れ直す）。また `channel` を見ないので、**携帯だけ止めていた会員は PC のメールも止まる** | 新で `notification_optouts` の読み書きに `channel` を入れる（A21） |
| 機能 | 中 | 携帯メールへの配信が新に無い | 未決: 運営に携帯メールへの配信を続けるかを確認する（[E14](../open-questions.md#e-切り替え後の機能で決めておきたいこと)） |
| 画面 | 中 | お知らせ・スカウト・足あと・掲示板コメントが設定画面に出るが、新にその通知を送る処理が無く、切り替えても何も変わらない | 未決: 送る処理を作るまで設定画面から隠すかを決める（[E15](../open-questions.md#e-切り替え後の機能で決めておきたいこと)） |

### F14 外部システムとの連携

利用者: —（システム間）／ データ種: B01 テナント、B06 会員プロフィール ／ 判定: **△ 差分あり**

- 旧: `library/BadgeApi.class.php`（`/tenant/{旧テナント ID}/user/{旧会員 ID}/...`、ログインのたびに呼ぶ）、`user.system_data` は `api/SbiController.php`（外部の動画プレーヤー）と `KddiCsvImportBatch`
- 新: ブリッジ `routes_internal.go` の `/internal/tenants/:id/users/import` → `service/external_user_import_service.go`（`external_user_links` を使う）

#### 参照データ

| データ | 旧（テーブル.列） | 新（テーブル.列） | 旧で使う | 新で使う | 差分 |
|---|---|---|:--:|:--:|---|
| 旧 ID | `tenant.tenant_id` / `user.user_id` | `tenants.tenant_id` / `users.user_id` | ◯ | — | 新は読まない |
| 外部連携の ID | — | `external_user_links.external_id` | — | ◯ | 新のブリッジが使う |
| 連携用の値 | `user.system_data` | `users.external_data` | ◯ | — | 新は読まない |

#### 差分

| 種類 | 深刻度 | 内容 | 対応 |
|---|:--:|---|---|
| 機能 | 中 | 旧はログインのたびにバッジシステムを呼んでいた（連続ログイン・ログイン回数のバッジ）。新は呼ばない | 未決: バッジは移行対象外になったので、新からバッジシステムを呼ぶかを運営と決める（[E16](../open-questions.md#e-切り替え後の機能で決めておきたいこと)） |
| 参照データ | 低 | `users.external_data` を新は読まない。旧では外部の動画プレーヤーの二重再生防止と KDDI の取込に使っていた | 未決: recademy で使っているかを確認する（[E17](../open-questions.md#e-切り替え後の機能で決めておきたいこと)） |

---

## 移したが新で読まれないデータ

各機能の「参照データ」で**新で使う が `—`** の行を集めたもの。**受け皿を足したのに、どの機能も読んでいない。** 旧でも使っていなかったもの（略称・`site` の値）は除いた。

| 新テーブル.列 | 旧 | 旧で使っていた機能 | 対応 |
|---|---|---|---|
| `users.login_id` | `user.login_id` | F01 ログイン、F02 再設定 | 未決（F01） |
| `users.is_valid` | `user.valid_chk` | F01 ログイン、F06 会員管理 | 新でログイン時に読む |
| `users.login_start_date` / `login_end_date` | `user.entry_date` / `limit_date` | F01 ログイン、F06 会員管理 | 新でログイン時に読む |
| `users.is_lockout` / `failed_login_started_at` / `failed_login_count` | `user.is_lockout` など | F01 ログイン、F06 ロック解除 | 未決（F01） |
| `users.last_login_at` / `total_login_count` / `last_access_at` | `user.recent_login_date` など | F01 ログイン、F06 検索 | 新でログイン時に更新する |
| `tenant_login_windows` | `login_limit` | F01 ログイン | 対応不要（0件） |
| `users.password_changed_at` | `user.password_change_date` | F02 変更の強制 | 未決（F02） |
| `tenant_sso_configs` | `sso_config` | F03 SAML | 未決（F03） |
| `tenant_secrets`（`facebook_*` / `twitter_*` / `instagram_*`） | `sns_setting` | F03 SNS ログイン | 未決（F03） |
| `users.admin_memo` | `user.user_memo` | F06 会員管理 | 新で編集画面に出す |
| `tenant_limits` | `tenant_limit_value` | F06 上限 | 未決（F06） |
| `tenant_field_defaults` | `user_item_default` | F06 登録時の既定値 | 新で会員登録時に当てる |
| `users.name_last` / `name_first` / `name_kana_last` / `name_kana_first` | `user.name_sei` など | F07 プロフィール | 新で実装する（A12） |
| `users.nickname` / `gender` / `blood_type` / `self_introduction` / `mobile_phone` | `user` の各列 | F07 プロフィール | 新で表示項目を足す |
| `tenant_profile_items` / `_labels` / `_categories`、`user_profile_values` | `profile_item` など、`user.user_profile1〜20` | F07 プロフィール | 新で実装する（A9） |
| `user_field_visibility` | `user.*_open_chk` など | F07 公開設定 | 新で実装する（A13） |
| `users.language_code`、`tenants.language_code` | `user_nationality_info.language_code`、`tenant.language_code` | F07 表示言語 | 新で言語の判定に使う |
| `user_roles` の旧ロール4つ、`users.is_career_counselor` | `role_master`、`career_counselor_chk` | F08 権限 | 未決（F08） |
| `instructor_assignments` | `instructor_set_*` | F08 講師の担当範囲 | 新で実装する（A18） |
| `tenant_groups` / `tenant_group_members` | `group` / `user_group` | F09 グループ | 未決（F09） |
| `users.member_no` | `user_personal_no.personal_no` | F11 会員番号 | 新で表示・検索する |
| `notification_optouts.channel` | `sendmail_pc_chk` / `sendmail_mobile_chk` | F13 通知 | 新で読み書きする |
| `users.mobile_email` | `user.mobile_mail_add` | F02 再設定、F13 通知 | 未決（F13） |
| `users.user_id`、`tenants.tenant_id` | `user.user_id`、`tenant.tenant_id` | F14 バッジ | 未決（F14） |
| `users.external_data` | `user.system_data` | F14 外部連携 | 未決（F14） |

> **`user_addresses` だけは新の機能（プロフィールと管理画面の住所）が読んでいる。** 基盤で足した受け皿のうち、切り替え後にそのまま効くのはこれだけ。

---

## 集計

| 判定 | 件数 |
|---|--:|
| ◯ 同等 | 0 |
| △ 差分あり | 11 |
| X 新に無い | 3 |
| 新のみ | 0 |
| **合計** | **14** |

| 差分の種類 | 高 | 中 | 低 | 未決 |
|---|--:|--:|--:|--:|
| 機能 | 3 | 16 | 2 | 10 |
| 参照データ | 1 | 1 | 7 | 2 |
| 振る舞い | 2 | 5 | 4 | 2 |
| 権限 | 1 | 2 | 0 | 2 |
| 画面 | 0 | 2 | 1 | 1 |
| **合計** | **7** | **26** | **14** | **17** |
