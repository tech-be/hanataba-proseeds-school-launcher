# 基盤 — マイグレーション対象

[突き合わせ](review.md#新環境に追加するテーブルカラム) の追加一覧（A1〜A21）を、**school-launcher に当てる migration の単位**に落としたもの。

- **当てる先**: `school-launcher/btoc-backend/db/migrations/`（goose 形式。雛形は `make migrate-create`）
- **当てた日**: 2026-09-22。下の M1〜M9 は**適用済みの DDL**で、school-launcher の実ファイルと一致する
- **確認**: `python -m migrator doctor` / `python -m migrator run --phase common.0`

> **ここに載っているのは案ではなく、当たったもの。** 最初の版は「DDL は案」と断っていたが、
> school-launcher の実スキーマと突き合わせた結果いくつか直している（lookup の必須列、
> `sort_order` の重複、goose の Up / Down 節）。直した点は各 M の末尾に書いた。

## 2種類ある

| 区別 | 意味 | 欠けているとどうなるか |
|---|---|---|
| **必須** | Step が**実際に書き込む先**。**48 件** | `common.0` で止まる。移行できない |
| **計画** | **移行では使わない**もの。**4 件** | 止まらない。`doctor` が残作業として出す |

> **「計画」は先送りではない。** 移行で使うものはすべて必須に入れてある。
> いま計画に残っているのは **A16（`login_history` の列追加）と A15（2FA の受け皿）**で、
> これは**純ログを移行しない**と決めたため移行では使わず、cutover 後の運用のための改善になる。

ツール側の定義は `migrator/steps/schema.py` の `REQUIRED_SCHEMA` / `PLANNED_SCHEMA`。
**この表とコードは一致させること**（片方だけ直すと、移行の途中で INSERT が落ちる）。

---

## 適用順

FK の参照先を先に作る。**この順で1ファイルずつ当てる。** 括弧内が school-launcher の実ファイル。

```
M1  tenants への列追加          20260922070746_add_tenant_short_name_and_language.sql
M2  ルックアップへの値追加      20260922070747_add_lw2_lookup_values.sql
M3  テナントに紐づく新テーブル  20260922070748_create_tenant_limits_and_profile_items.sql
M4  users への列追加            20260922070749_add_lw2_columns_to_users.sql
M5  users に紐づく新テーブル    20260922070750_create_user_addresses_and_profile_values.sql
M6  既存テーブルの変更          20260922070751_add_channel_to_notification_optouts.sql
M7  グループ・属性              20260922070752_create_tenant_groups_and_attributes.sql
M8  会員に紐づく残り            20260922070753_create_user_visibility_and_assignments.sql
M9  認証まわり                  20260922070754_create_sso_login_windows_and_two_factor.sql
M12 ロールを旧システムに揃える  20260928072918_align_lw2_roles_and_lesson_types.sql
```

当て方（btoc-backend を起動していなくても当てられる）:

```bash
docker compose run --rm migrate                                        # learningware
docker compose run --rm -e LW_DATABASE_NAME=learningware_test migrate  # テスト用 DB
```

---

## M1. `tenants` への列追加（A1 / A2）

**必須。** 旧 `tenant` の略称と言語を受ける。

```sql
-- +goose Up
ALTER TABLE tenants
    ADD COLUMN short_name    VARCHAR(64) NULL                  AFTER name,
    ADD COLUMN language_code VARCHAR(5)  NOT NULL DEFAULT 'ja' AFTER short_name;

-- +goose Down
ALTER TABLE tenants
    DROP COLUMN short_name,
    DROP COLUMN language_code;
```

| 列 | 旧の対応 | 備考 |
|---|---|---|
| `short_name` | `tenant.tenent_name_short` varchar(20) | **旧の綴り誤り（`tenent`）は踏襲しない** |
| `language_code` | `tenant.language_code` char(2) | 効かせるにはフロントの i18n 判定を変える（A2） |

---

## M2. ルックアップへの値追加（A5 / A7 / A15 / A21 / `deleted`）

**必須。** DDL ではなく **INSERT**。`tenants` / `users` / `notification_optouts` / `tenant_secrets` の
FK 先なので、これらを使う行より先に入れる。

```sql
-- +goose Up
INSERT IGNORE INTO tenant_statuses (code, name_ja, is_operational, is_trial, sort_order, is_system) VALUES
    ('deleted', '削除済み', FALSE, FALSE, 40, TRUE);

INSERT IGNORE INTO user_roles (code, name_ja, is_admin, is_instructor, sort_order, is_system) VALUES
    ('system_admin',    'システム管理者', TRUE,  TRUE,  5,  TRUE),
    ('group_manager',   'グループ管理者', FALSE, FALSE, 50, TRUE),
    ('company_manager', '求人企業',       FALSE, FALSE, 60, TRUE),
    ('supporter',       'サポーター',     FALSE, FALSE, 70, TRUE);

INSERT IGNORE INTO auth_methods (code, name_ja, is_external, requires_password, sort_order, is_system) VALUES
    ('saml',      'SAML SSO',          TRUE,  FALSE, 60,  TRUE),
    ('facebook',  'Facebook',          TRUE,  FALSE, 70,  TRUE),
    ('twitter',   'X (Twitter)',       TRUE,  FALSE, 80,  TRUE),
    ('instagram', 'Instagram',         TRUE,  FALSE, 90,  TRUE),
    ('totp',      '二要素認証 (TOTP)', FALSE, FALSE, 100, TRUE);

INSERT IGNORE INTO email_kinds (code, name_ja, user_optional, sort_order, is_system) VALUES
    ('announcement', 'アナウンス・お知らせ', TRUE, 300, TRUE),
    ('scout',        'スカウト',             TRUE, 310, TRUE),
    ('footprint',    '足あと',               TRUE, 320, TRUE),
    ('bbs_comment',  '掲示板コメント',       TRUE, 330, TRUE);

INSERT IGNORE INTO tenant_secret_kinds (code, name_ja, is_sensitive, sort_order, is_system) VALUES
    ('linkpreview_api_key', 'リンクプレビュー API キー', TRUE, 100, TRUE);

-- +goose Down
-- 参照されている行は FK で消せないので、参照が無いときだけ消す。
-- ただし tenant_statuses の 'deleted' だけは必ず消す（下記）。
```

> **ロールの値はこのあと M12 で旧システムに揃える。** ここで入れる並び順・`is_instructor` は
> 当初の値で、M2 は既にマージ・適用済みのため書き換えずに残してある（→ [M12](#m12-ロールを旧システムに揃える)）。

**ロールバックの注意.** `172_tenant_lesson_quiz_lookup.sql` の Down は `tenants.status` を
`ENUM('active','suspended','trial')` に戻すため、**`deleted` の行や `deleted` のテナントが
1件でもあると 172 まで巻き戻せない**。この migration の Down で先に消す。

**当てるときに直した点（案のままでは動かなかったもの）:**

| 直した点 | 理由 |
|---|---|
| `auth_methods` / `email_kinds` / `tenant_secret_kinds` の `is_system` の値を補った | 案は列 4 個に対し値 3 個で、`Column count doesn't match` で落ちる |
| `auth_methods` に `is_external` / `requires_password` を指定 | 実表にある NOT NULL 列。既定のままだと SAML や SNS が「外部 IdP でない」ことになる |
| `email_kinds` に `user_optional = TRUE` を指定 | 実表にある NOT NULL 列。既定 FALSE だと受講者が受信を止められない種別になる |
| `email_kinds` の `sort_order` を 200/210/220/230 → **300/310/320/330** | 既存の `enrollment_confirm`(200) / `payment_receipt`(210) / `lesson_reminder`(220) / `quiz_result`(230) と重複し、画面の並びが不定になる（移行ツールの値も 300 番台に揃えた） |
| `INSERT` → `INSERT IGNORE`、Down を `NOT EXISTS` 付きに | 部分適用・再適用で止まらないようにする（school-launcher の既存 migration と同じ手筋） |

---

## M3. テナントに紐づく新テーブル（A4 / A9）

**必須。** いずれも `tenant_id` を持ち、`tenants(id)` を参照する。

### `tenant_limits`（A4 ← `tenant_limit_value`）

```sql
CREATE TABLE tenant_limits (
    tenant_id               CHAR(26) NOT NULL PRIMARY KEY,
    max_users               INT NULL,
    max_learners            INT NULL,
    max_user_csv_rows       INT NULL,
    max_enrollments         INT NULL,
    max_enrollment_csv_rows INT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_tenant_limits_tenant FOREIGN KEY (tenant_id) REFERENCES tenants(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT = '[テナントごとの利用上限] NULL = 無制限。旧 tenant_limit_value を受ける。';
```

| 列 | 旧の対応 |
|---|---|
| `max_users` / `max_learners` | `user_value` / `student_value` |
| `max_user_csv_rows` | `user_csv_value` |
| `max_enrollments` / `max_enrollment_csv_rows` | `user_learning_lesson_value` / `..._csv_value` |

> **NULL = 無制限**として扱う。`platform_plans` の `max_learners` とどちらが優先かは運用で決める。

### `tenant_profile_item_categories` / `tenant_profile_items` / `tenant_profile_item_labels`（A9 ← `profile_cate` / `profile_item` / `profile_item_label`）

```sql
CREATE TABLE tenant_profile_item_categories (
    id         CHAR(26) NOT NULL PRIMARY KEY,
    tenant_id  CHAR(26) NOT NULL,
    legacy_id  INT NULL,               -- 旧 profile_cate.profile_cate_id
    name       VARCHAR(100) NOT NULL,
    sort_order INT NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_profile_item_categories (tenant_id, legacy_id),
    CONSTRAINT fk_profile_item_categories_tenant FOREIGN KEY (tenant_id) REFERENCES tenants(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT = '[プロフィール項目の分類] 旧 profile_cate。項目を画面上でまとめる単位。';

CREATE TABLE tenant_profile_items (
    id             CHAR(26) NOT NULL PRIMARY KEY,
    tenant_id      CHAR(26) NOT NULL,
    item_type      TINYINT  NOT NULL,   -- 0=user の既存列 / 1=自由記述
    item_no        TINYINT  NOT NULL,
    field_code     VARCHAR(100) NULL,   -- 旧 profile_item.field_name（値の在処）
    category_id    CHAR(26) NULL,
    default_value  VARCHAR(255) NULL,   -- 旧 user_item_default.value
    show_flag      BOOLEAN NOT NULL DEFAULT TRUE,
    edit_flag      BOOLEAN NOT NULL DEFAULT TRUE,
    required_flag  BOOLEAN NOT NULL DEFAULT FALSE,
    open_flag      BOOLEAN NOT NULL DEFAULT FALSE,
    multiline_flag BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_tenant_profile_items (tenant_id, item_type, item_no),
    CONSTRAINT fk_profile_items_tenant   FOREIGN KEY (tenant_id)   REFERENCES tenants(id),
    CONSTRAINT fk_profile_items_category FOREIGN KEY (category_id) REFERENCES tenant_profile_item_categories(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT = '[プロフィール項目の定義] 旧 profile_item。値ではなく表示・編集・必須の制御。';

CREATE TABLE tenant_profile_item_labels (
    id        CHAR(26) NOT NULL PRIMARY KEY,
    tenant_id CHAR(26) NOT NULL,
    item_id   CHAR(26) NOT NULL,
    locale    VARCHAR(5) NOT NULL,      -- 旧 profile_item_label.language
    label     VARCHAR(100) NULL,        -- 旧 title
    memo      TEXT NULL,
    memo_free TEXT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_profile_item_labels (item_id, locale),
    CONSTRAINT fk_profile_item_labels_tenant FOREIGN KEY (tenant_id) REFERENCES tenants(id),
    CONSTRAINT fk_profile_item_labels_item   FOREIGN KEY (item_id)   REFERENCES tenant_profile_items(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT = '[プロフィール項目の表示名] 旧 profile_item_label。言語ごとのラベルと説明。';
```

> **`profile_item` は値ではなく画面制御の定義**で、`field_code` が値の在処（`user` の列名）を指す。
> 値は `item_type=0` なら `users` の対応列、`item_type=1` なら `user_profile_values`（M5）。
>
> **既存の `settings.profile_fields`（`birth_year` / `birth_month_day` / `phone` の3項目固定）と
> 二重管理にしない。** どちらを正とするかを決めてから実装する。

---

## M4. `users` への列追加（A12 / A14 / A19 / A20）

**必須。** **複数列を1列に畳まない**ための追加。

```sql
-- +goose Up
ALTER TABLE users
    -- A12 氏名（分割のまま持ち、name は分割列から生成する）
    ADD COLUMN name_last           VARCHAR(100) NULL AFTER name,
    ADD COLUMN name_first          VARCHAR(100) NULL AFTER name_last,
    ADD COLUMN name_kana_last      VARCHAR(100) NULL AFTER name_first,
    ADD COLUMN name_kana_first     VARCHAR(100) NULL AFTER name_kana_last,
    ADD COLUMN member_no           INT          NULL AFTER name_kana_first,
    -- A20 ログイン識別子・連絡先・プロフィール
    ADD COLUMN login_id            VARCHAR(100) COLLATE utf8mb4_bin NULL AFTER email,
    ADD COLUMN mobile_email        VARCHAR(255) NULL AFTER login_id,
    ADD COLUMN mobile_phone        VARCHAR(50)  NULL AFTER phone,
    ADD COLUMN nickname            VARCHAR(100) NULL,
    ADD COLUMN gender              TINYINT      NULL,
    ADD COLUMN blood_type          TINYINT      NULL,
    ADD COLUMN self_introduction   TEXT         NULL,
    ADD COLUMN admin_memo          TEXT         NULL,
    ADD COLUMN external_data       TEXT         NULL,
    -- A20 ログイン可能期間（status に畳まない）
    ADD COLUMN login_start_date    DATE         NULL,
    ADD COLUMN login_end_date      DATE         NULL,
    ADD COLUMN is_valid            BOOLEAN      NOT NULL DEFAULT TRUE,
    ADD COLUMN is_new              BOOLEAN      NOT NULL DEFAULT FALSE,
    ADD COLUMN password_changed_at DATE         NULL,
    -- A14 ロックアウトと最終ログイン（3列+3列を同じ粒度で）
    ADD COLUMN is_lockout              BOOLEAN     NOT NULL DEFAULT FALSE,
    ADD COLUMN failed_login_started_at DATETIME(3) NULL,
    ADD COLUMN failed_login_count      INT         NOT NULL DEFAULT 0,
    ADD COLUMN last_login_at           DATETIME(3) NULL,
    ADD COLUMN last_access_at          DATETIME(3) NULL,
    ADD COLUMN total_login_count       INT         NOT NULL DEFAULT 0,
    -- A19 キャリアカウンセラー（ロールではなくフラグ）
    ADD COLUMN is_career_counselor     BOOLEAN     NOT NULL DEFAULT FALSE,
    ADD UNIQUE KEY uk_users_login_id  (tenant_id, login_id),
    ADD UNIQUE KEY uk_users_member_no (tenant_id, member_no);

-- +goose Down
-- 追加した 24 列と UNIQUE 2 本を落とす（追加の逆順）。
```

| 追加列 | 旧の対応 | 畳まない理由 |
|---|---|---|
| `name_last` / `name_first` | `name_sei` / `name_mei` | 入力フォームと CSV が姓/名の2欄 |
| `mobile_phone` | `mobile_tel` | 固定電話と携帯は別のもの |
| `mobile_email` | `mobile_mail_add` | 通知の宛先を PC / 携帯で分けている（A21 と対） |
| `login_start_date` / `login_end_date` | `entry_date` / `limit_date` | `status` に畳むと期限判定ができない |
| `is_valid` | `valid_chk` | `del_chk` と2フラグあり、`status` 1列では組み合わせが消える |
| `login_id` | `login_id` | 新はメールのみ。**`utf8mb4_bin`** で大文字小文字を区別する（旧と同じ） |
| `total_login_count` ほか | 同名列 | 集計だが lw2 が列として持っているので同じ粒度で受ける |

> **`birth_year` / `birth_month` / `birth_day` と `phone` は既存**（`20260728032443_add_profile_fields_to_users.sql`）。
> 誕生日は**3列のまま**で `birthday` date には畳まない。
>
> **`is_career_counselor` も必須。** 最初の版は「必須（`is_career_counselor` を除く）」と書いていたが、
> `REQUIRED_SCHEMA` には最初から入っており、`doctor` は欠けていれば止める。実態に合わせて必須に統一した。
>
> `login_id` と `member_no` はどちらも NULL 可。MySQL の UNIQUE は NULL を重複扱いしないので、
> これらを持たない会員が並存できる。

---

## M5. `users` に紐づく新テーブル（A9 / A12）

**必須。**

```sql
CREATE TABLE user_addresses (
    id          CHAR(26) NOT NULL PRIMARY KEY,
    tenant_id   CHAR(26) NOT NULL,
    user_id     CHAR(26) NOT NULL,
    kind        VARCHAR(16) NOT NULL,      -- primary / secondary（旧の住所1 / 住所2）
    postal_code VARCHAR(16)  NULL,
    prefecture  VARCHAR(10)  NULL,         -- 旧 pref_id（コード）を名称に展開して入れる
    city        VARCHAR(100) NULL,
    street      TEXT NULL,                 -- 旧「以下住所」= 番地・建物名
    country     VARCHAR(64)  NULL,         -- 旧 user_nationality_info
    nationality VARCHAR(64)  NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_user_addresses (user_id, kind),
    CONSTRAINT fk_user_addresses_tenant FOREIGN KEY (tenant_id) REFERENCES tenants(id),
    CONSTRAINT fk_user_addresses_user   FOREIGN KEY (user_id)   REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT = '[会員の住所] kind で 1 件目 / 2 件目を分ける。旧 user の住所 2 組を行に展開したもの。';

CREATE TABLE user_profile_values (
    id        CHAR(26) NOT NULL PRIMARY KEY,
    tenant_id CHAR(26) NOT NULL,
    user_id   CHAR(26) NOT NULL,
    item_id   CHAR(26) NOT NULL,
    value     VARCHAR(255) NULL,           -- 旧 user.user_profile1〜20
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_user_profile_values (user_id, item_id),
    CONSTRAINT fk_user_profile_values_tenant FOREIGN KEY (tenant_id) REFERENCES tenants(id),
    CONSTRAINT fk_user_profile_values_user   FOREIGN KEY (user_id)   REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_user_profile_values_item   FOREIGN KEY (item_id)   REFERENCES tenant_profile_items(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT = '[会員のプロフィール自由記述] item_type=1 の項目の値。旧 user.user_profile1〜20 を行に展開。';
```

> **`user_profile_values` に入るのは `item_type=1` の自由記述だけ。** `item_type=0` の値は
> `users` の対応列（M4）で受ける。
>
> `prefecture` は旧 `pref_id`（コード）を**名称に展開して**入れる。新環境に都道府県の lookup が無く、
> 移行のためだけに足すと master data 規約（`is_system` / `active` / `deprecated_at`）を背負うため。

---

## M6. `notification_optouts` の変更（A21）

**必須。** PC / 携帯を分けるため `channel` を足し、UNIQUE を張り直す。

```sql
-- +goose Up
ALTER TABLE notification_optouts
    ADD COLUMN channel VARCHAR(16) NOT NULL DEFAULT 'pc' AFTER kind,
    DROP INDEX uk_notification_optouts,
    ADD UNIQUE KEY uk_notification_optouts (tenant_id, user_id, kind, channel);

-- +goose Down
-- UNIQUE を戻す前に (tenant_id, user_id, kind) ごとに 1 行へ畳む（下記）。
DELETE FROM notification_optouts
WHERE id NOT IN (
    SELECT id FROM (
        SELECT MIN(id) AS id FROM notification_optouts GROUP BY tenant_id, user_id, kind
    ) keep
);

ALTER TABLE notification_optouts
    DROP INDEX uk_notification_optouts,
    ADD UNIQUE KEY uk_notification_optouts (tenant_id, user_id, kind),
    DROP COLUMN channel;
```

> **Down は既存行に注意。** 同じ `(tenant_id, user_id, kind)` が `pc` / `mobile` の2行に
> 分かれていると、UNIQUE を戻す時点で重複して失敗する。当てた版では Down の中で先に畳んでいる。
> どの行が残るかは問わない — `channel` 列ごと落とすので、残る列の値は `id` と `created_at` 以外同じ。

---

## M7. グループ・属性（A10 / A11）

**必須。** 旧 `group` / `attribute` の定義と、会員への割当。

```sql
CREATE TABLE tenant_groups (
    id         CHAR(26) NOT NULL PRIMARY KEY,
    tenant_id  CHAR(26) NOT NULL,
    legacy_id  INT NOT NULL,                -- 旧 group.group_id（割当の突き合わせに使う）
    parent_id  CHAR(26) NULL,               -- 旧 parent_group_id。**階層の正本はこれ**
    depth      INT NOT NULL DEFAULT 0,      -- 旧 hierarchy
    code       VARCHAR(50)  NULL,           -- 旧 group_code
    name       VARCHAR(100) NOT NULL,       -- 旧 group_name
    memo       TEXT NULL,
    sort_order INT NOT NULL DEFAULT 0,      -- 旧 sort_no
    deleted_at DATETIME(3) NULL,            -- 旧 del_chk=1
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_tenant_groups_legacy (tenant_id, legacy_id),
    CONSTRAINT fk_tenant_groups_tenant FOREIGN KEY (tenant_id) REFERENCES tenants(id),
    CONSTRAINT fk_tenant_groups_parent FOREIGN KEY (parent_id) REFERENCES tenant_groups(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT = '[会員のグループ] 旧 group。parent_id が階層の正本で、group_structure は作らない。';

CREATE TABLE tenant_group_members (
    id        CHAR(26) NOT NULL PRIMARY KEY,
    tenant_id CHAR(26) NOT NULL,
    group_id  CHAR(26) NOT NULL,
    user_id   CHAR(26) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_tenant_group_members (group_id, user_id),
    CONSTRAINT fk_group_members_tenant FOREIGN KEY (tenant_id) REFERENCES tenants(id),
    CONSTRAINT fk_group_members_group  FOREIGN KEY (group_id)  REFERENCES tenant_groups(id) ON DELETE CASCADE,
    CONSTRAINT fk_group_members_user   FOREIGN KEY (user_id)   REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT = '[グループへの会員割当] 旧 user_group。';

CREATE TABLE tenant_attributes (
    id         CHAR(26) NOT NULL PRIMARY KEY,
    tenant_id  CHAR(26) NOT NULL,
    legacy_id  INT NOT NULL,
    code       VARCHAR(50)  NULL,
    name       VARCHAR(100) NOT NULL,
    memo       TEXT NULL,
    sort_order INT NOT NULL DEFAULT 0,
    deleted_at DATETIME(3) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_tenant_attributes_legacy (tenant_id, legacy_id),
    CONSTRAINT fk_tenant_attributes_tenant FOREIGN KEY (tenant_id) REFERENCES tenants(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT = '[会員の属性] 旧 attribute。グループと違い階層を持たない横断のタグ。';

CREATE TABLE user_attribute_values (
    id           CHAR(26) NOT NULL PRIMARY KEY,
    tenant_id    CHAR(26) NOT NULL,
    attribute_id CHAR(26) NOT NULL,
    user_id      CHAR(26) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_user_attribute_values (attribute_id, user_id),
    CONSTRAINT fk_user_attribute_values_tenant    FOREIGN KEY (tenant_id)    REFERENCES tenants(id),
    CONSTRAINT fk_user_attribute_values_attribute FOREIGN KEY (attribute_id) REFERENCES tenant_attributes(id) ON DELETE CASCADE,
    CONSTRAINT fk_user_attribute_values_user      FOREIGN KEY (user_id)      REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT = '[属性への会員割当] 旧 user_attribute。';

CREATE TABLE attribute_required_courses (
    id               CHAR(26) NOT NULL PRIMARY KEY,
    tenant_id        CHAR(26) NOT NULL,
    attribute_id     CHAR(26) NOT NULL,
    course_id        CHAR(26) NULL,     -- オンデマンド移行後に埋める
    legacy_lesson_id INT NOT NULL,      -- 旧 attribute_lesson.lesson_id
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_attribute_required_courses (attribute_id, legacy_lesson_id),
    CONSTRAINT fk_attr_required_tenant    FOREIGN KEY (tenant_id)    REFERENCES tenants(id),
    CONSTRAINT fk_attr_required_attribute FOREIGN KEY (attribute_id) REFERENCES tenant_attributes(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT = '[属性ごとの受講必須講座] 旧 attribute_lesson。course_id は講座移行後に埋める (FK 無し)。';
```

> **`legacy_id` を持たせる理由。** 割当（`user_group` / `user_attribute` / `attribute_lesson`）は
> 旧 ID で親を指しているので、移行時に**旧 ID → 新 ULID** を引けるようにしておく。
> 決定論 ULID でも引けるが、**cutover 後に人が突き合わせるときに要る。**
>
> **`attribute_required_courses.course_id` は NULL で始まる。** 講座（オンデマンド）が未移行のため。
> **FK も張らない**（張ると移行できない）。オンデマンド移行後に `legacy_lesson_id` を使って埋める。
>
> **`group_structure` は作らない。** `parent_id` から再構築できる派生データ。
>
> **`tenant_groups` は自己参照 FK を持つ。** テナント単位でまとめて消すときは
> `ORDER BY depth DESC`（深い方から）でないと FK 違反になる。school-launcher の
> `cmd/seed` はそのように消している。

---

## M8. 会員に紐づく残り（A13 / A18）

**必須。**

```sql
CREATE TABLE user_field_visibility (
    id         CHAR(26) NOT NULL PRIMARY KEY,
    tenant_id  CHAR(26) NOT NULL,
    user_id    CHAR(26) NOT NULL,
    field_code VARCHAR(50) NOT NULL,   -- 旧 *_open_chk の列名をそのまま使う
    visible    BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_user_field_visibility (user_id, field_code),
    CONSTRAINT fk_user_field_visibility_tenant FOREIGN KEY (tenant_id) REFERENCES tenants(id),
    CONSTRAINT fk_user_field_visibility_user   FOREIGN KEY (user_id)   REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT = '[会員が他人に見せる項目] 旧 user.*_open_chk を行に展開したもの。';


CREATE TABLE instructor_assignments (
    id               CHAR(26) NOT NULL PRIMARY KEY,
    tenant_id        CHAR(26) NOT NULL,
    user_id          CHAR(26) NOT NULL,
    scope            VARCHAR(16) NOT NULL,  -- course / group / attribute
    target_id        CHAR(26) NULL,         -- group / attribute は移行時に埋まる
    legacy_target_id INT NOT NULL,          -- course は講座移行後に target_id を埋める
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_instructor_assignments (user_id, scope, legacy_target_id),
    CONSTRAINT fk_instructor_assignments_tenant FOREIGN KEY (tenant_id) REFERENCES tenants(id),
    CONSTRAINT fk_instructor_assignments_user   FOREIGN KEY (user_id)   REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT = '[講師・担当者の担当範囲] scope=course/group/attribute。course は講座移行後に target_id を埋める。';
```

| `field_code` | 旧の列 |
|---|---|
| `profile` / `name` / `address` / `birthday` / `diary` / `lesson` | `profile_open_chk` / `name_open_chk` / `address_open_chk` / `birthday_open_chk` / `diary_open_chk` / `lesson_open_chk` |
| `personal_record` | `user_attached_info.personal_record_chk` |

> **`instructor_assignments.scope='course'` は `target_id` が NULL で始まる。** 講座が未移行のため。
> `legacy_target_id`（旧 `lesson_id`）を持っておき、オンデマンド移行後に埋める。
> **`courses.instructor_id` の 1:1 見直しはオンデマンド O01 と同時**に行う。

---

## M9. 認証まわり（A6 / A8 / A15）

**SSO とログイン時間制限（A6 / A8）は必須**（`config.sso` / `config.login_windows` が行を入れる。
ステージングでは旧データが0件だったが、**あれば入る**）。

**2FA（A15 `user_two_factor_secrets`）は計画。** 旧 `twostepverification` が持つのは
**発行中の確認コードだけで、秘密鍵ではない**（`user_id` / `verification_code` / `error_count` /
`result` / `regist_date` の5列、ステージングで18行）。移した時点で無効になるため
[移行の対象外](review.md#移行の対象外移行できないもの--移行しないもの)に入っており、
**移す行が無い**。受け皿は作るが、Step は書き込まない。

```sql
CREATE TABLE tenant_sso_configs (
    id         CHAR(26) NOT NULL PRIMARY KEY,
    tenant_id  CHAR(26) NOT NULL,
    provider   VARCHAR(32) NOT NULL,   -- auth_methods.code（saml など）
    metadata   JSON NULL,              -- 旧 sso_parameter（IdP ごとに形が違う）
    active     BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_tenant_sso_configs (tenant_id, provider),
    CONSTRAINT fk_tenant_sso_configs_tenant   FOREIGN KEY (tenant_id) REFERENCES tenants(id),
    CONSTRAINT fk_tenant_sso_configs_provider FOREIGN KEY (provider)  REFERENCES auth_methods(code) ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT = '[テナントの SSO 設定] 旧 sso_parameter。metadata は IdP ごとに形が違うので JSON。';

CREATE TABLE tenant_login_windows (
    id          CHAR(26) NOT NULL PRIMARY KEY,
    tenant_id   CHAR(26) NOT NULL,
    day_of_week TINYINT NOT NULL,      -- 旧 youbi_type
    limit_type  TINYINT NOT NULL DEFAULT 0,
    start_time  TIME NULL,
    end_time    TIME NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY ix_tenant_login_windows (tenant_id, day_of_week),
    CONSTRAINT fk_tenant_login_windows_tenant FOREIGN KEY (tenant_id) REFERENCES tenants(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT = '[ログインできる曜日・時間帯] 旧 login_limit_time。移行時は空で、運営が cutover 後に設定する。';

CREATE TABLE user_two_factor_secrets (
    id           CHAR(26) NOT NULL PRIMARY KEY,
    tenant_id    CHAR(26) NOT NULL,
    user_id      CHAR(26) NOT NULL,
    secret       VARBINARY(255) NOT NULL,
    confirmed_at DATETIME(3) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_user_two_factor_secrets (user_id),
    CONSTRAINT fk_user_2fa_tenant FOREIGN KEY (tenant_id) REFERENCES tenants(id),
    CONSTRAINT fk_user_2fa_user   FOREIGN KEY (user_id)   REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT = '[二要素認証 (TOTP) の秘密鍵] 移行データ無し。confirmed_at が NULL の間は設定途中。';
```

> **`user_two_factor_secrets` は空で始まる。** 旧 `twostepverification` が持っているのは
> **発行中の認証コード（平文）**で、設定そのものではない。移行データは無い。
>
> **`tenant_login_windows` も空で始まる**（recademy はローカルデータ数0）。cutover 後に運営が設定する。
>
> `tenant_sso_configs.provider` は `auth_methods(code)` を参照するので、**M2 を先に当てる**
> （`saml` の行が無いと FK が張れない）。

---

## M10. 会員の言語・テナント既定値（A22 / A23）

**必須。** **移行ツールを実装して初めて分かった不足分。** A1〜A21 を作った時点では

- `user_nationality_info` を「国籍・海外住所」として A12 に入れたが、**同じ表の `language_code` が拾われていなかった**
- `user_item_default` は A9 の `tenant_profile_items.default_value` で受ける想定だったが、
  実データの `item_name` は `profile_item` ではなく **`user` の列名**（`profile_open_chk`）を指しており載らない

```sql
-- +goose Up
ALTER TABLE users
    ADD COLUMN language_code VARCHAR(5) NULL COMMENT '会員の既定言語 (旧 user_nationality_info.language_code)'
    AFTER nickname;

CREATE TABLE tenant_field_defaults (
    id            CHAR(26) NOT NULL PRIMARY KEY,
    tenant_id     CHAR(26) NOT NULL,
    field_code    VARCHAR(100) NOT NULL,   -- 旧 user_item_default.item_name（`user` の列名）
    default_value VARCHAR(100) NOT NULL,
    created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_tenant_field_defaults (tenant_id, field_code),
    CONSTRAINT fk_tenant_field_defaults_tenant FOREIGN KEY (tenant_id) REFERENCES tenants(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT = '[テナント単位の会員列の既定値] 旧 user_item_default。会員登録時の初期値。';

-- +goose Down
DROP TABLE IF EXISTS tenant_field_defaults;
ALTER TABLE users DROP COLUMN language_code;
```

| 列 | 旧の対応 | 備考 |
|---|---|---|
| `users.language_code` | `user_nationality_info.language_code` char(8) | **列にする。** 会員1人に1つの値で、新環境は会員の属性（`gender` / `blood_type`）を `users` に置いている。同じ表の住所部分は `user_addresses` に移してあるので、ここだけ表を増やさない。空文字は NULL（未設定）。ステージング実測 `ja` 133名 / `th` 1名 |
| `tenant_field_defaults` | `user_item_default`（`tenant_id` + `item_name` + `value`） | **旧の構造をそのまま持つ。** `tenant_profile_items.default_value` とは別物で、畳むと新規登録時にどちらを見るか分からなくなる |

> **`language_code` は列を足しただけでは効かない。** 言語の決まり方を
> 「cookie → 会員の既定 → テナントの既定（A2）→ `defaultLocale`」にするため、
> `btoc-frontend/src/i18n/request.ts` の判定と、会員値をフロントに渡す経路が要る。

適用済みの migration: `20260922070755_add_user_language_and_tenant_field_defaults.sql`

---

## M11. 会員・テナントの旧 ID（A24）

**必須。** 2026-09-24 追加。

```sql
-- +goose Up
ALTER TABLE users
    ADD COLUMN legacy_id INT NULL COMMENT '旧 user.user_id (移行で作られた行のみ)',
    ADD UNIQUE KEY uk_users_legacy (tenant_id, legacy_id);

ALTER TABLE tenants
    ADD COLUMN legacy_id INT NULL COMMENT '旧 tenant.tenant_id (移行で作られた行のみ)',
    ADD UNIQUE KEY uk_tenants_legacy (legacy_id);

-- +goose Down
ALTER TABLE users DROP INDEX uk_users_legacy, DROP COLUMN legacy_id;
ALTER TABLE tenants DROP INDEX uk_tenants_legacy, DROP COLUMN legacy_id;
```

> **外部のバッジシステムが lw2 の ID で付与実績を持っている。**
> `BadgeApi` は `/tenant/{lw2 の tenant_id}/user/{lw2 の user_id}/badges` を叩き、
> バッジキーも `LESSON_{lw2 の lesson_id}_COMPLETION` の形。
> `courses.legacy_id` / `lessons.legacy_id` は[コンテンツ](../02-content/schema-additions.md)で足したが、
> **会員とテナントには無く、このままでは「誰のバッジか」を引けない**。
>
> **バッジ以外にも効く。** 移行後の問い合わせ調査は「旧 ID でこの会員を探す」から始まることが多い。

---

## 計画（移行では使わない 2 件）

| 追加するもの | A番号 | なぜ移行で使わないか |
|---|---|---|
| `user_two_factor_secrets`（M9） | A15 | 旧 `twostepverification` は**発行中の確認コードだけ**を持ち、移した時点で無効。**移す行が無い**ので、受け皿を作るだけ |
| `login_history` に `input_login_id` / `logged_out_at` / `session_id` / `site_type` / `last_access_at`、**`user_id` の NULL 化** | A16 | **純ログは移行しない**ので、移行ではこの表に1行も入れない。ただし `auth_outcomes` に `user_not_found` があるのに `user_id` が NOT NULL + FK で**失敗ログインを記録できない**のは、cutover 後の運用でそのまま効く問題 |

> **`doctor` が見ているのは上のうち 3 列だけ**（`input_login_id` / `logged_out_at` / `session_id` =
> `PLANNED_SCHEMA`）。`site_type` / `last_access_at` と **`user_id` の NULL 化は機械では検出されない** —
> NULL 化は列の有無では分からず、既存の認証経路にも影響するため、school-launcher 側の設計レビューを
> 通してから入れる。A16 を実施するときは `PLANNED_SCHEMA` も合わせて直すこと。

---

## 確認

```bash
python -m migrator doctor             # 必須 / 計画それぞれの未適用件数
python -m migrator run --phase common.0   # 必須が1件でも欠けていれば停止
```

`doctor` の出力（適用後）:

```
[OK  ] 追加スキーマ（移行に必須 48 件）: すべて入っている
[TODO] 追加スキーマ（移行では使わない）: 3 件未適用: login_history.input_login_id,
       login_history.logged_out_at, login_history.session_id。移行は止まらないが、
       cutover 後に失敗ログインを記録できない
```

計画のうち**未適用のものだけ**が `TODO` で出る（`OK` とは混ぜない）。`user_two_factor_secrets` は
適用済みのため出ない。

移行ツールを動かさずに school-launcher 側だけで確かめるなら、`REQUIRED_SCHEMA` の 48 組を
`information_schema` に当てる（`doctor` と同じ判定で、legacy DB への接続が要らない）。

### school-launcher 側で表を足したときの注意

`tenants` を参照する表を追加したら、**`btoc-backend/cmd/seed` の `cleanupDemoData` にも足す**。
載せ忘れると 2 回目以降の `make seed` が FK で落ち、`make e2e` は e2e-seed の段で丸ごと止まる。
`make check-seed-cleanup`（CI でも走る C9）がこれを機械的に検出する。

今回の M3 / M5 / M7 / M8 / M9 で足した 17 表もすべて登録済み。`tenant_groups` だけは自己参照 FK が
あるため `ORDER BY depth DESC` で消している。

---

## M12. ロールを旧システムに揃える

**必須。** `20260928072918_align_lw2_roles_and_lesson_types.sql`（2026-09-28 決定）。
M2 は既にマージ・適用済みで、goose は適用済みのバージョンを再実行しないため、**M2 を書き換えずに
UPDATE で直す**。同じ migration で `lesson_types` の `discussion` / `skill_check` も足す（→ [コンテンツの追加](../02-content/schema-additions.md)）。

| ロール | 表示名 | `is_instructor` | 並び順 | 状態 |
|---|---|:--:|---:|---|
| `system_admin` | システム管理者 | FALSE | 1 | 有効 |
| `facility_manager` | 運営管理者 | FALSE | 3 | **削除済み**（新規に足す） |
| `group_manager` | グループ管理者 | FALSE | 4 | 有効 |
| `supporter` | サポーター | FALSE | 4 | **削除済み** |
| `company_manager` | 求人企業 | FALSE | 6 | 有効 |

- 表示名は旧 `translate_master`（`master_type='role'`, `language_code='ja'`）、並び順は旧 `role_master.role_index` をそのまま使う
- **移行ツールは既にある行を上書きしない**ので、この migration の値が移行後の値になる。
  移行ツールの `UserRolesStep` も旧データから同じ値を作っており、`verify` で一致を確かめる
- 旧で削除済み（`del_chk = 1`）の `facility_manager`（role_id 3）と `supporter`（role_id 8）は、**移行するが削除済み**（`active = FALSE`）で入れる
- 並び順 1〜6 は seed のロール（10〜90）より前に並ぶ。seed のロールは全テナント共通なので変えない
- Down は M2 の値に戻し、`facility_manager` は参照が無いときだけ消す
