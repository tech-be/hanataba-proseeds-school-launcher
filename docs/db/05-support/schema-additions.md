# サポート機能 — マイグレーション対象

[突き合わせ](review.md#新環境に追加するテーブルカラム) の追加一覧を、**school-launcher に当てる migration の単位**に落としたもの。

- **当てる先**: `school-launcher/btoc-backend/db/migrations/`（goose 形式。雛形は `make migrate-create`）
- **実物**: **まだ無い。** `20260924…_lw2_support_additions.sql` として1本にまとめる
- **当てる時期**: **移行直前**（[migration-spec](migration-spec.md) のフェーズ0）
- **確認**: `python -m migrator doctor` — この区分が未適用なら `[TODO]` で出る

> **いまはファイル（5-5）ぶんだけ。** LINE 友だち紐付け（5-1）は**既存の `line_links` で足りる**ため
> 追加が無い。クーポン（5-2）・お知らせ（5-3）・問い合わせ（5-4）・就業支援（5-6）・
> コミュニティ（5-7）は移行ツールが未実装で、追加が必要かどうかも決まっていない。

> **基盤（1）とコンテンツ（2）が先。** 公開対象が基盤の `tenant_groups` と
> コンテンツの `lessons` を参照する。

## 2種類ある

| 区別 | 意味 | 欠けているとどうなるか |
|---|---|---|
| **必須** | Step が**実際に書き込む先** | `common.0` で止まる。移行できない |
| **計画** | **移行では使わない**もの | 止まらない。`doctor` が `[TODO]` で出す |

**この区分に「計画」はない。**

ツール側の定義は `migrator/steps/schema.py` の `SUPPORT_SCHEMA`（2件）。**この表とコードは一致させること。**

---

## 1. 教材・ライブラリの公開対象

**必須。**

**lw2 の教材は2系統ある。**

- `drive`（実測3件）… テナント共通の資料フォルダ。**中身のファイルは DB に無く**、ディスク上の
  `dir_name` 配下にある。DB から作れるのは**フォルダだけ**
- `unit_attached_file` … ユニットに添付した資料。**フォルダという概念が無い**

新環境は `library_folders` → `library_materials` の2段で `folder_id` が NOT NULL。
ユニット添付には親フォルダが無いので、**移行用のフォルダを1つ作ってそこに入れ**、
本来の結びつき（どのユニットの資料か）は `library_material_lesson_targets` で持つ。

```sql
CREATE TABLE library_material_lesson_targets (
    id          CHAR(26) NOT NULL PRIMARY KEY,
    tenant_id   CHAR(26) NOT NULL,
    material_id CHAR(26) NOT NULL,
    lesson_id   CHAR(26) NOT NULL,          -- 旧 unit_attached_file.unit_id
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_library_material_lesson (material_id, lesson_id),
    CONSTRAINT fk_lib_mat_lesson_tenant   FOREIGN KEY (tenant_id)   REFERENCES tenants(id),
    CONSTRAINT fk_lib_mat_lesson_material FOREIGN KEY (material_id) REFERENCES library_materials(id) ON DELETE CASCADE,
    CONSTRAINT fk_lib_mat_lesson_lesson   FOREIGN KEY (lesson_id)   REFERENCES lessons(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE library_folder_group_targets (
    id        CHAR(26) NOT NULL PRIMARY KEY,
    tenant_id CHAR(26) NOT NULL,
    folder_id CHAR(26) NOT NULL,
    group_id  CHAR(26) NOT NULL,            -- 基盤 A10 の tenant_groups
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_library_folder_group (folder_id, group_id),
    CONSTRAINT fk_lib_folder_group_tenant FOREIGN KEY (tenant_id) REFERENCES tenants(id),
    CONSTRAINT fk_lib_folder_group_folder FOREIGN KEY (folder_id) REFERENCES library_folders(id) ON DELETE CASCADE,
    CONSTRAINT fk_lib_folder_group_group  FOREIGN KEY (group_id)  REFERENCES tenant_groups(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

> **ユーザー単位に展開しない。** 旧はグループ単位で公開範囲を決めており、
> **展開すると後から会員をグループに足しても自動で公開されない**。軸を保つ。

> **`library_folders.created_at` のように既定値がある列も、Step が書くなら NOT NULL 検査の対象**にする。
> 既定値があるからと素通りさせると、dry-run を通って**実 INSERT で初めて落ちる**。

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
| 5-6 就業支援 | 同上。求人・面談・スキルチェック |
| 5-7 コミュニティ | 同上。掲示板・SNS 共有・足あと |
