# サポート機能 — マイグレーション対象

[突き合わせ](review.md#新環境に追加するテーブルカラム) の追加一覧を、**school-launcher に当てる migration の単位**に落としたもの。

- **当てる先**: `school-launcher/btoc-backend/db/migrations/`（goose 形式。雛形は `make migrate-create`）
- **実物**: `20260930052453_lw2_support_additions.sql`（school-launcher の `feat/lw2-support-schema` の上で未追跡。2026-10-02 時点）。
  1 と 2 の表をまとめて足す。**受講（3）の `submission_feedback_files` も同じ migration に入れてある**
  （[受講 schema-additions 2](../03-enrollment/schema-additions.md#2-課題提出の新テーブルと列追加)）
- **あわせて当てる**: **`20261001085757_lw2_keep_deleted_rows.sql`**（2026-10-01。`feat/lw2-support-schema` の上で未追跡） の `admin_notes.deleted_at`（下の 3）
- **当てる時期**: **移行直前**（[migration-spec](migration-spec.md) のフェーズ0）
- **確認**: `python -m migrator doctor` — この区分が未適用なら `[TODO]` で出る

> **いまはファイル（5-5）と、2026-09-30 に仕分けた旧テーブル（5-6 フォロー・5-7 分類・5-8 利用料の集計）のぶん。**
> LINE 友だち紐付け（5-1）は**既存の `line_links` で足りる**ため追加が無い。助言メモ（5-6）は既存の `admin_notes` に寄せ、
> 「最後に直した人」の列（`updated_by`）だけ足す。
> クーポン（5-2）・お知らせ（5-3）・問い合わせ（5-4）・求人と面談（5-6）・掲示板（5-7）は移行ツールが未実装で、
> 追加が必要かどうかも決まっていない。

> **基盤（1）とコンテンツ（2）が先。** 公開対象が基盤の `tenant_groups` と
> コンテンツの `lessons` を参照する。

## 2種類ある

| 区別 | 意味 | 欠けているとどうなるか |
|---|---|---|
| **必須** | Step が**実際に書き込む先** | `common.0` で止まる。移行できない |
| **計画** | **移行では使わない**もの | 止まらない。`doctor` が `[TODO]` で出す |

**この区分に「計画」はない。**

ツール側の定義は `migrator/steps/schema.py` の `SUPPORT_SCHEMA`（11件。`admin_notes.updated_by` / `deleted_at` を含む）。**この表とコードは一致させること。**

---

## 1. 教材・ライブラリの公開対象

**必須。**

**lw2 の教材は3系統ある。**

- `drive`（実測3件）… テナント共通の資料フォルダ。**中身のファイルは DB に無く**、ディスク上の
  `dir_name` 配下にある。DB から作れるのは**フォルダだけ**
- `unit_attached_file` … 講座資料のユニットに添付した資料。資料ごとに見せるグループ・属性を指定できる
- `lesson_attached_file` … 講座に直接添付した資料（全環境で0行）

新環境は `library_folders` → `library_materials` の2段で、**公開先はフォルダ単位**（`audience_type`）だけ。
移行では添付資料を講座ごとのフォルダに入れて「その講座の受講者に公開」にし（既存の `library_folder_course_targets`）、
**新に機能の無い公開範囲は次の4表に残す**。新に同じ機能を作れば、表を読むだけで旧と同じ範囲になる。

| 表 | 旧 | 機能ができるまでの扱い |
|---|---|---|
| `library_material_lesson_targets` | `unit_attached_file.unit_id` | 資料は講座のフォルダから見える |
| `library_folder_group_targets` | `drive_group` | フォルダの公開先を「対象者なし」（`specific_users`） |
| `library_material_group_targets`（2026-10-01） | `*_attached_file_group` | 資料を非公開 |
| `library_material_tag_targets`（2026-10-01） | `*_attached_file_attribute`（属性はタグ） | 資料を非公開 |

```sql
CREATE TABLE library_material_lesson_targets (
    id          CHAR(26) NOT NULL PRIMARY KEY,
    tenant_id   CHAR(26) NOT NULL,
    material_id CHAR(26) NOT NULL,
    lesson_id   CHAR(26) NOT NULL,          -- 旧 unit_attached_file.unit_id
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_library_material_lesson (material_id, lesson_id),
    -- FK: tenants / library_materials (CASCADE) / lessons (CASCADE)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE library_folder_group_targets (
    id        CHAR(26) NOT NULL PRIMARY KEY,
    tenant_id CHAR(26) NOT NULL,
    folder_id CHAR(26) NOT NULL,
    group_id  CHAR(26) NOT NULL,            -- 基盤 A10 の tenant_groups
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_library_folder_group (folder_id, group_id),
    -- FK: tenants / library_folders (CASCADE) / tenant_groups (CASCADE)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE library_material_group_targets (
    id          CHAR(26) NOT NULL PRIMARY KEY,
    tenant_id   CHAR(26) NOT NULL,
    material_id CHAR(26) NOT NULL,
    group_id    CHAR(26) NOT NULL,          -- tenant_groups
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_library_material_group (material_id, group_id),
    -- FK: tenants / library_materials (CASCADE) / tenant_groups (CASCADE)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE library_material_tag_targets (
    id          CHAR(26) NOT NULL PRIMARY KEY,
    tenant_id   CHAR(26) NOT NULL,
    material_id CHAR(26) NOT NULL,
    tag_id      CHAR(26) NOT NULL,          -- user_tags（旧の属性）
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_library_material_tag (material_id, tag_id),
    -- FK: tenants / library_materials (CASCADE) / user_tags (CASCADE)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

正確な DDL は school-launcher の `20260930052453_lw2_support_additions.sql`。

> **ユーザー単位に展開しない。** 旧はグループ単位で公開範囲を決めており、
> **展開すると後から会員をグループに足しても自動で公開されない**。軸を保つ。

> **旧より広く見せない。** 公開先の機能が無いからといって「全員に公開」にしない。
> 狭める（非公開・対象者なし）のは、見せるべき人に見えないだけで、見せてはいけない人には見えない。

---

## 2. その他の旧テーブルの受け皿（2026-09-30）

どの区分にも仕分けていなかった旧テーブルを 05 として移すための受け皿。school-launcher の
`20260930052453_lw2_support_additions.sql`（上の1の2表も同じ migration で足した）。旧 ID の列は旧列名で NULL 可。

| 旧 | 新 | 備考 |
|---|---|---|
| `personal_record_advice` | 既存の `admin_notes` ＋ `updated_by` を追加 | 助言メモ。対象の会員・書いた人・本文。**最後に直した人（旧 `update_user_id`）を入れる列が無いので `admin_notes.updated_by`（NULL 可、`users` への FK、`ON DELETE SET NULL`）を足した**。削除済みも移す（`admin_notes.deleted_at`。2026-10-01） |
| `follow` | `scout_follows`（新設） | 求人企業による受講者のフォロー。`follow_id` |
| `community_cate` | `community_categories`（新設） | コミュニティの分類。`community_cate_id`、グループ 0 は NULL |
| `config_closing_date` | `tenant_usage_settings`（新設） | 利用料の締め日 |
| `accounting_user` | `tenant_usage_snapshots`（新設） | 月次の会員数の集計。`(tenant_id, batch_date)` で一意 |
| `accounting_user_detail` | `tenant_usage_snapshot_users`（新設） | 集計した時点の会員の写し。旧の会員 ID は `legacy_user_id`（新の `user_id` と別物なので `legacy_` を付ける）。移行先に会員がいれば `user_id` を入れる |

> **`calc_param`（模試の集計条件）は保留。** 中身は 06 対象外の模試のもので、模試と一緒に E63 の回答で決める。

---

## 3. 削除済みの助言メモも移すための列（2026-10-01）

**必須。** `20261001085757_lw2_keep_deleted_rows.sql`。

```sql
ALTER TABLE admin_notes
    ADD COLUMN deleted_at DATETIME(3) NULL AFTER body;   -- 旧 personal_record_advice.del_chk = 1
```

> 新のアプリは `deleted_at` をまだ読まない。

---

## 取り下げた追加

| 追加案 | 取り下げた理由 |
|---|---|
| `library_folder_attribute_targets`（属性単位の公開） | **旧に対応するデータが無い。** `drive` に属性の列は無く、`drive_attribute` に相当するテーブルも lw2 に存在しない。**グループ単位（`drive_group`）だけが実在する**（実測0行だが表はある）。属性で公開範囲を切る運用が本番で見つかったときに足す |

---

## 計画（移行では使わない）

**なし。**

---

## まだ決まっていないもの

| 項目 | 状況 |
|---|---|
| 5-1 LINE 友だち紐付け | **追加なし。** 既存の `line_links` で足りる（移行ツール実装済み） |
| 5-2 クーポン | 移行ツール未実装。受け皿の要否は未確認 |
| 5-3 お知らせ | 同上。メールテンプレート・Web Push を含む |
| 5-4 問い合わせ | 同上。個別メッセージを含む |
| 5-6 就業支援 | 助言メモ（既存の `admin_notes`）とフォロー（`scout_follows`）は済み。求人・面談・スキルチェックは移行ツール未実装で、受け皿の要否は未確認 |
| 5-7 コミュニティ | 分類（`community_categories`）は済み。掲示板・SNS 共有・足あとは移行ツール未実装で、受け皿の要否は未確認 |
| `calc_param` | 保留。模試と一緒に [E63](../open-questions.md#e-切り替え後の機能で決めておきたいこと) の回答で決める |
