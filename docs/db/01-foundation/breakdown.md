# 基盤テーブルの内訳 — マスター系 / ユーザー系

[データ種別対照表](../data-type-mapping.md) で **基盤**区分に分類した **旧32件 / 新13件**を、データの持ち主で切り直したもの。テナント・権限・会員・認証・ログイン履歴が1区分に同居していて粒度が粗いため、**マスター系（定義・設定側）** と **ユーザー系（会員個人に紐づく実データ）** の2つに大分類し、さらに意味ごとの中分類を付けた。

移行ツールの**投入順序を決めるための一覧**として使う。新環境は実 FK を持つため、マスター系が入っていないとユーザー系は1行も入らない。

- 全件の逆引き: [旧環境](../legacy-table-coverage.md) / [新環境](../new-table-coverage.md)
- 基盤のカラム突き合わせ: [review/01-foundation.md](review.md)

## 大分類の定義

| 大分類 | 定義 | 旧 | 新 |
|---|---|---:|---:|
| **マスター系** | テナントが持つ**定義・設定**。会員が1人もいなくても存在する | 15 | 9 |
| **ユーザー系** | **会員個人に紐づく実データ**。会員が増えると行が増える | 17 | 4 |
| **合計** | | **32** | **13** |

**旧はユーザー系が多く（17:15）、新はマスター系が多い（9:4）。** 新環境が値の一覧をルックアップ表に外出しする設計（`*_statuses` / `*_kinds` / `*_methods`）を採っている一方、lw2 が会員に持たせていた情報の多くに受け皿が無いことの現れ。

## 中分類の一覧

| | 中分類 | 旧 | 新 |
|---|---|---:|---:|
| M1 | テナント基盤 | 3 | 5 |
| M2 | 権限・ロール定義 | 1 | 1 |
| M3 | 認証・ログイン設定 | 3 | 2 |
| M4 | 会員項目・状態の定義 | 4 | 1 |
| M5 | 組織・属性の定義 | 4 | **0** |
| U1 | 会員基本情報 | 3 | 2 |
| U2 | 会員の一意ID | 1 | **0** |
| U3 | 認証情報・セキュリティ | 3 | **0** |
| U4 | ログイン履歴 | 3 | 1 |
| U5 | 所属・属性の割当 | 2 | **0** |
| U6 | 権限・担当範囲の割当 | 4 | **0** |
| U7 | 画面状態・個人設定 | 1 | 1 |

> データ種の名称は表幅の都合で省略している（例: `B06 会員プロフィール` = 「会員プロフィール（氏名・生年・電話）」）。正式名は [data-type-mapping.md](../data-type-mapping.md) を参照。

> **「新テーブル」は実装済みの移行先**（`migrator/phases/registry.py` の `foundation.1`〜`5`）。
> 調査時点で `—`（受け皿なし）だったものは、[移行の原則](../00-template/review.md#移行の原則)に沿って
> **新環境に追加した**（DDL は [マイグレーション対象](schema-additions.md)）。
> `—` のまま残っているのは[移行の対象外](review.md#移行の対象外移行できないもの--移行しないもの)。
> 実装して初めて分かった不足分は下の「[実装して判明した追加](#実装して判明した追加a22--a23)」。
>
> **ローカルデータ数と A·B·C の定義は [README.md](../README.md#共通の列の意味) にまとめてある。** 要点だけ再掲すると、ローカルデータ数は**全73テナントの合計**で recademy 単体ではなく、`-` は 2026-07-28 ダンプ以降に追加されて実測値が無いもの。A=純ログ / B=要判断 / C=移行対象。

---

# マスター系（15 / 9）

## M1 テナント基盤

| 旧テーブル | 新テーブル | データ種 | lw2区分 | ローカルデータ数 | A·B·C | 説明 | 移行の注意 |
|---|---|---|---|---:|:--:|---|---|
| `tenant` | `tenants` | B01 テナント | データ | 64 | C | テナント基本。`tenant_code` → `slug`（UNIQUE） | 移行対象は `tenant_id = 12` (recademy) の1件のみ。**新環境はシード値のみで行が無いため、移行側で新規に作る。** `tenants.id` が全テーブルの `tenant_id` の基点になるので、**この区分で最初に投入する1行。** 略称と言語は**新環境に `short_name` / `language_code` を追加して受ける**（アプリ側の修正とセット） |
| `site` | `tenants.settings` / `tenant_secrets` | B01 テナント | データ | 1 | C | サイト基本。DB 接続情報・サービス名・機能フラグを持つ運用テーブル | サービス名・提供期間・機能フラグを `settings` に、`linkpreview_api_key` を `tenant_secrets` に移す（A3）。**DB 接続情報4列だけ対象外**（移しても機能せず、平文なので読み出さない） |
| `tenant_limit_value` | `tenant_limits` | B01 テナント | 設定 | 64 | C | ユーザー数・CSV一括登録などの上限値5種 | `tenant_limits` を新設して移す（A4） |
| — | `tenant_statuses` | B01 テナント | マスタ | — | — | `tenants.status` の値。`trial`/`active`/`suspended` | migration のシードで投入済み。recademy は `active` を明示（**列の既定値は `trial`**）。**`deleted` が無いので追加する**（新環境側の変更） |
| — | `tenant_db_types` | B01 テナント | マスタ | — | — | `tenants.db_type` の値。`shared`/`dedicated` | 旧に対応列なし。シードで投入済みで、recademy は `shared` |
| — | `tenant_secrets` | B01 テナント | データ | — | — | テナントごとの機密値（DB DSN・Webhook シークレット） | 旧に対応データなし。運用で登録する |
| — | `tenant_secret_kinds` | B01 テナント | マスタ | — | — | `tenant_secrets.kind` の値 | migration で投入 |

## M2 権限・ロール定義

| 旧テーブル | 新テーブル | データ種 | lw2区分 | ローカルデータ数 | A·B·C | 説明 | 移行の注意 |
|---|---|---|---|---:|:--:|---|---|
| `role_master` | `user_roles` | B02 ロール | マスタ | 8 | C | 権限の定義。旧は `role_id` + 権限名、新は `code` PK のマスタ | **テーブルごと移す。** `user_roles` は `name_ja` / `sort_order` を持つグローバルマスタで、シードは5行。**lw2 の8ロールのうち4つ（`system_admin` / `company_manager` / `group_manager` / `supporter`）を追加**したうえで `user.role_id` → `users.role` を1対1で移す。**`platform_admin` は絶対に付けない** |

## M3 認証・ログイン設定

| 旧テーブル | 新テーブル | データ種 | lw2区分 | ローカルデータ数 | A·B·C | 説明 | 移行の注意 |
|---|---|---|---|---:|:--:|---|---|
| `sso_config` | `tenant_sso_configs` | B10 SSO | 設定 | 1 | C | `tenant_id` + `sso_type` + `sso_parameter` の3列。IdP 設定 | **受け皿テーブルなし。** `docs/authentication.md` が「SAML SSO や Google / LINE OAuth は外部 IdP に委ねる」としており DB に設定を持たない。**この1件が B10 SSO を ◯→X に再判定した根拠** |
| `sns_setting` | — | B10 SSO | 設定 | 63 | C | SNS ログイン設定 | 受け皿なし。新の `auth_methods` に `google`/`line` はあるが設定値の置き場が無い |
| `login_limit` | `tenant_login_windows` | B09 ログイン履歴 | データ | 0 | B | 曜日・時間帯ごとのログイン制限 | `tenant_login_windows` を新設して移す（A8）。ステージング実測0行 |
| — | `auth_methods` | B09 ログイン履歴 | マスタ | — | — | `login_history.method` の値。`password`/`google`/`line`/`passkey`/`refresh` | migration で投入。旧に対応列が無いので既定 `password` |
| — | `auth_outcomes` | B09 ログイン履歴 | マスタ | — | — | `login_history.outcome` の値。8種 | **`user_login_log.user_login_result`（数値）との対応表が必要** |

## M4 会員項目・状態の定義

| 旧テーブル | 新テーブル | データ種 | lw2区分 | ローカルデータ数 | A·B·C | 説明 | 移行の注意 |
|---|---|---|---|---:|:--:|---|---|
| `profile_cate` | `tenant_profile_item_categories` | B06 会員プロフィール | マスタ | 5 | C | プロフィール項目のカテゴリ | 5行を recademy 用として移す（A9）。**項目より先に入れる** |
| `profile_item` | `tenant_profile_items` | B06 会員プロフィール | データ | 3,123 | C | **項目の定義**（`tenant_id` + 表示/編集/必須/公開の各フラグ）。会員データではないためマスターに置く | 項目定義を移す（A9）。`profile_cate_id=0` は分類なしで NULL |
| `profile_item_label` | `tenant_profile_item_labels` | B06 会員プロフィール | データ | 3,187 | C | 項目のラベル | `locale` 付きで移す（A9）。**親の項目が無いラベルは落とす**（実測1件） |
| `user_item_default` | `tenant_field_defaults` | B06 会員プロフィール | データ | 10 | C | `item_name` + `tenant_id` + `value`。**テナント単位の既定値**。名前に反して会員データではない | `tenant_field_defaults` を新設して**旧の構造のまま移す**（A23）。`tenant_profile_items.default_value` とは別物 |
| — | `user_statuses` | B06 会員プロフィール | マスタ | — | — | `users.status` の値。`active`/`inactive`/`pending`/`deleted` | `del_chk` / `valid_chk` / `entry_date` からの変換先 |

> **M4 の旧4件は受け皿を追加して移す**（A9）。`profile_cate` → `tenant_profile_item_categories`、`profile_item` → `tenant_profile_items`、`profile_item_label` → `tenant_profile_item_labels`、`user.user_profile1..20` の**値** → `user_profile_values`。**項目定義と値の両方を移す。**

## M5 組織・属性の定義

| 旧テーブル | 新テーブル | データ種 | lw2区分 | ローカルデータ数 | A·B·C | 説明 | 移行の注意 |
|---|---|---|---|---:|:--:|---|---|
| `group` | `tenant_groups` | B07 グループ | データ | 1,009 | C | グループの定義 | `parent_id` + `depth` で階層ごと移す（A10） |
| `group_structure` | — | B07 グループ | 中間 | 1,313 | C | `group_id` + `slave_group_id` の2列。**グループの階層定義**で会員には紐づかないためマスターに置く | **派生データなので移行しない。** `group.parent_group_id` が正本（対象外 B） |
| `attribute` | `tenant_attributes` | B08 属性 | データ | 427 | C | 属性の定義 | 属性定義を移す（A11） |
| `attribute_lesson` | `attribute_required_courses` | B08 属性 | データ | 332 | C | `lesson_id` + `attribute_id`。属性に必須講座を紐づける**定義** | `attribute_required_courses` を新設して移す（A11）。`course_id` は講座移行後に埋める |

> **M5 は新側が丸ごと0件。** グループ・属性は lw2 の配信対象の絞り込み（お知らせ・フォローメール・掲示板・自動割当）の土台なので、**ここが落ちると他区分の機能も連鎖して落ちる**（U05 / U11 / J05 など）。

---

# ユーザー系（17 / 4）

## U1 会員基本情報

| 旧テーブル | 新テーブル | データ種 | lw2区分 | ローカルデータ数 | A·B·C | 説明 | 移行の注意 |
|---|---|---|---|---:|:--:|---|---|
| `user` | `users` | B06 会員プロフィール | データ | 48,906 | C | **95列 → 17列。** 会員の本体 | **フリガナ・住所2組・カスタムプロフィール20項目・公開制限8列が落ちる。** `UNIQUE (tenant_id, email)` にメール欠損174名・重複23アドレス/56名が当たる |
| `user_attached_info` | `users.is_career_counselor` | B06 会員プロフィール | データ | 15,653 | C | ユーザー付属情報 | `career_counselor_chk` を列として移す（A19）。**ロールに畳まない** |
| `user_nationality_info` | `user_addresses`(kind=foreign) | B06 会員プロフィール | データ | 8,478 | C | ユーザー国籍情報 | 国籍・海外住所を `kind='foreign'` の行で移す（A12）。**コードは `country_master` で国名に展開**。`language_code` は `users.language_code` に移す（A22。実測 ja 133名 / th 1名） |
| — | `external_user_links` | B06 会員プロフィール | データ | — | — | lw2 ↔ 新のユーザー対応表。`UNIQUE (tenant_id, external_system, external_id)` | **`external_system` の値が資料間で `lw2` と `kiracari` に割れている。** 食い違うと同じ会員が二重登録される |

## U2 会員の一意ID

| 旧テーブル | 新テーブル | データ種 | lw2区分 | ローカルデータ数 | A·B·C | 説明 | 移行の注意 |
|---|---|---|---|---:|:--:|---|---|
| `user_personal_no` | `users.member_no` | B11 マイナンバー | データ | 53,568 | C | **会員に振る一意の ID**（運用担当に確認済み）。`personal_no` は `int(11)` で12桁のマイナンバーは格納できず、PDF のデータ種名が実体と合っていない | `personal_no` を列として移す（A12） |

## U3 認証情報・セキュリティ

| 旧テーブル | 新テーブル | データ種 | lw2区分 | ローカルデータ数 | A·B·C | 説明 | 移行の注意 |
|---|---|---|---|---:|:--:|---|---|
| `password_reminder` | — | B05 パスワード | データ | 5,029 | B | パスワード再発行のトークン | 受け皿なし。一時データなので移行不要 |
| `twostepverification` | `user_two_factor_secrets` | B12 二要素認証 | データ | 55 | C | 二段階認証の設定 | **受け皿を作るだけで、移す行は無い**（持っているのは発行中のコードのみ。対象外 A） |
| `twostepverification_log` | — | B12 二要素認証 | イベント・履歴 | 192 | A | 二段階認証のログ | 受け皿なし |

> **パスワード本体（`user.password`）は U1 の `user` に含まれる。** 3DES → bcrypt の再ハッシュが必要（ETL設計 §7）。

## U4 ログイン履歴

| 旧テーブル | 新テーブル | データ種 | lw2区分 | ローカルデータ数 | A·B·C | 説明 | 移行の注意 |
|---|---|---|---|---:|:--:|---|---|
| `user_login_log` | `login_history` | B09 ログイン履歴 | イベント・履歴 | 1,326,645 | **A** | ログイン試行の履歴 | **A区分（移行対象外）だが受け皿がある**ため線引きが未決。`user_id` が旧 NULL可・新 NOT NULL + FK なので**ログイン失敗行が1行も入らない**。`input_password`（入力パスワード）は移行してはいけない |
| `user_login_log_monthly` | — | B09 ログイン履歴 | イベント・履歴 | 146,702 | **A** | 月別集計 | 受け皿なし。新は集計を持たない |
| `user_login_chk_log` | — | B09 ログイン履歴 | イベント・履歴 | - | - | ログイン状態履歴 | ログイン有効期間の変更履歴を移す（A17）。**ステージングにはテーブルが無い** |

## U5 所属・属性の割当

| 旧テーブル | 新テーブル | データ種 | lw2区分 | ローカルデータ数 | A·B·C | 説明 | 移行の注意 |
|---|---|---|---|---:|:--:|---|---|
| `user_group` | `tenant_group_members` | B07 グループ | 中間 | 10,492 | C | 会員のグループ割当 | 会員のグループ割当を移す（A10） |
| `user_attribute` | `user_attribute_values` | B08 属性 | 中間 | 48,600 | C | 会員の属性割当 | 会員の属性割当を移す（A11）。**会員が存在しない行は移せない**（実測36件） |

## U6 権限・担当範囲の割当

| 旧テーブル | 新テーブル | データ種 | lw2区分 | ローカルデータ数 | A·B·C | 説明 | 移行の注意 |
|---|---|---|---|---:|:--:|---|---|
| `system_admin_role` | — | B02 ロール | 設定 | 45 | C | `tenant_id` + `user_id` + 権限種別名。**ロールの定義ではなく特定ユーザーへの割当**なのでユーザー系に置く | 受け皿なし。新は `platform_admin` 固定 |
| `instructor_set_lesson` | `instructor_assignments` | B02 ロール | 中間 | 118 | C | 講師の担当講座 | `scope='course'` で移す（A18）。`target_id` は講座移行後に埋める |
| `instructor_set_group` | `instructor_assignments` | B02 ロール | 中間 | 19 | C | 講師の担当グループ | `scope='group'` で移す（A18） |
| `instructor_set_attribute` | `instructor_assignments` | B02 ロール | 中間 | 11 | C | 講師の担当属性 | `scope='attribute'` で移す（A18） |

> **U6 は新側が丸ごと0件。** 講師が複数コースを担当する構造も、グループ・属性単位の担当範囲も表現できない（[review/01-foundation.md](review.md) B02 の「高」）。

## U7 画面状態・個人設定

| 旧テーブル | 新テーブル | データ種 | lw2区分 | ローカルデータ数 | A·B·C | 説明 | 移行の注意 |
|---|---|---|---|---:|:--:|---|---|
| `edit_form_data` | — | B06 会員プロフィール | データ | 4,752 | B | `user_id` + `display_id` + フォーム/検索条件/グリッド状態。**会員ごとの画面状態**でプロフィールではないため U1 と分けた | 受け皿なし。一時的な UI 状態なので移行不要 |
| — | `user_preferences` | B06 会員プロフィール | 設定 | — | — | ユーザーごとの表示設定（1テナント × 1ユーザー） | 旧に対応データなし |

---

## 投入順序

新環境は実 FK（マスターの `code` 列への `ON UPDATE CASCADE` を含む）を持つため、順序は強制される。

```
M1 テナント基盤      tenants ← tenant_statuses / tenant_db_types
  ↓
M2 権限定義          user_roles          ┐
M3 認証方式定義      auth_methods /      │ すべて migration で投入（ETL は書かない）
                     auth_outcomes       │
M4 会員状態定義      user_statuses       ┘
  ↓
U1 会員基本情報      users → external_user_links
  ↓
U7 個人設定          user_preferences
U4 ログイン履歴      login_history（移行するなら）
```

- **M1〜M4 はすべて migration で投入する**（ETL設計 §4 の L0「前提マスタの整備。ETL では書かない」）。**ETL ツールがこの区分で書くのは U1 / U4 / U7 の3テーブルだけ**
- **U1 の `users` は既存のブリッジ（`external_user_import_service.go`）が正本**。cutover 前夜にフル同期を流す

## 新側に受け皿が無い中分類

| 中分類 | 旧件数 | 落ちるもの |
|---|---:|---|
| M5 組織・属性の定義 | 4 | グループ・属性の定義と階層。**配信対象の絞り込みの土台**なので他区分に連鎖する |
| U2 会員の一意ID | 1 | 会員の一意 ID 53,568行。会員に見せていた番号なら移行後は提示できない |
| U3 認証情報・セキュリティ | 3 | 二段階認証の設定と履歴 |
| U5 所属・属性の割当 | 2 | 会員のグループ・属性割当 59,092行 |
| U6 権限・担当範囲の割当 | 4 | 講師の担当範囲とシステム管理者権限 |
| **計** | **14** | **基盤32件のうち 44% が新環境に置き場所を持たない** |

これに M1 の `site` / `tenant_limit_value`、M3 の `sso_config` / `sns_setting` / `login_limit`、M4 の4件、U1 の2件、U4 の2件、U7 の1件を足すと、**旧32件のうち新側に受け皿があるのは `tenant` / `role_master`（値のみ）/ `user` / `user_login_log` の4件だけ**になる。

---

## 実装して判明した追加（A22 / A23）

**移行ツールを実装して初めて分かった不足分。** どちらも調査時点の想定が外れていたもので、
[移行の原則](../00-template/review.md#移行の原則)に沿って**受け皿を追加した**（[M10](schema-additions.md#m10-会員の言語テナント既定値a22--a23)）。

| 旧 | 件数（ステージング実測） | なぜ抜けていたか | 追加した受け皿 |
|---|---:|---|---|
| `user_nationality_info.language_code` | `ja` 133名 / `th` 1名 | `user_nationality_info` は A12 で「国籍・海外住所」として受けたが、**同じ表の言語列が拾われていなかった** | `users.language_code`（A22） |
| `user_item_default` | 1件（`profile_open_chk`） | A9 の `tenant_profile_items.default_value` で受ける想定だったが、`item_name` は `profile_item` ではなく**`user` の列名**を指していた | `tenant_field_defaults`（A23） |
