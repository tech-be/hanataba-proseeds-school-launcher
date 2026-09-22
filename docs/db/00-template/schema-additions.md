# ＜区分名＞ — マイグレーション対象

> **これはひな形です。** `00-template/` ごと `NN-<区分名>/` にコピーして使ってください。
> **必要な区分だけ**作ります（新環境に足すものが無い区分では不要）。
> **このディレクトリは区分ではないので、README の区分一覧にも集計にも含めません。**

[突き合わせ](review.md#新環境に追加するテーブルカラム) の追加一覧（A1〜An）を、**school-launcher に当てる migration の単位**に落としたもの。

- **当てる先**: `school-launcher/btoc-backend/db/migrations/`（goose 形式。雛形は `make migrate-create`）
- **当てる時期**: **移行直前**（[migration-spec](migration-spec.md) のフェーズ0）
- **確認**: `python -m migrator doctor` / `python -m migrator run --phase common.0`

> **DDL は案。** 列名・型は school-launcher 側の設計レビューで確定する。ここに書くのは
> 「何が無いと移行が止まるか」と「旧のどの列を受けるか」であって、最終的なスキーマではない。

## 2種類ある

| 区別 | 意味 | 欠けているとどうなるか |
|---|---|---|
| **必須** | Step が**実際に書き込む先** | `common.0` で止まる。移行できない |
| **計画** | **移行では使わない**もの（新環境の運用のための改善） | 止まらない。`doctor` が `[TODO]` で出す |

> **「計画」を先送りの置き場にしない。** 移行で使うものは**すべて必須**に入れる。
> 「判断が未決だから計画に置く」とすると、**そのデータは移らないまま cutover を迎える**。
> 未決があるなら、計画に逃がさず [migration-spec](migration-spec.md) の 1-1 に上げて閉じること。

ツール側の定義は `migrator/steps/schema.py` の `REQUIRED_SCHEMA` / `PLANNED_SCHEMA`。
**この表とコードは一致させること**（片方だけ直すと、移行の途中で INSERT が落ちる）。

---

## 適用順

FK の参照先を先に作る。**この順で1ファイルずつ当てる。**

```
M1  既存テーブルへの列追加（他に依存しないもの）
M2  ルックアップへの値追加（INSERT のみ）      ← 他テーブルの FK 先
M3  親になる新テーブル
M4  子になる新テーブル
M5  既存テーブルの制約変更（UNIQUE / NOT NULL）
```

＜区分ごとに実際の並びに書き換える。**なぜその順かを1行添える**（「`X` の FK 先だから」など）＞

---

## M＜n＞. ＜まとめの単位＞（A＜番号＞）

**必須。** ＜何を受けるための追加か1行＞

```sql
-- +goose Up
＜DDL＞

-- +goose Down
＜元に戻す DDL＞
```

| 列 | 旧の対応 | 備考 |
|---|---|---|
| `＜新列＞` | `＜旧テーブル.旧列＞ ＜型＞` | ＜型が変わる / 名前を変える理由＞ |

> ＜設計上の判断があれば引用ブロックで。**なぜその形にしたか**を書く＞

---

## 書くときの決まり

### 新環境の作法に合わせる

| 項目 | 合わせるもの |
|---|---|
| 主キー | `CHAR(26)`（ULID）。旧の連番をそのまま主キーにしない |
| テナント | `tenant_id CHAR(26) NOT NULL` ＋ `tenants(id)` への FK |
| ルックアップ | `code VARCHAR(32)` を PK に、`name_ja` / `sort_order` / `is_system` / `active` / `deprecated_at` |
| 文字コード | `ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci` |
| 監査列 | `created_at` / `updated_at` は `TIMESTAMP` ＋ `DEFAULT CURRENT_TIMESTAMP` |

### `legacy_id` を持たせる基準

**子テーブルが旧 ID で親を指している場合は、親に `legacy_id` を持たせる。**
決定論 ULID でも引けるが、**cutover 後に人が突き合わせるときに要る**。

```sql
legacy_id INT NOT NULL,
UNIQUE KEY uk_＜テーブル＞_legacy (tenant_id, legacy_id),
```

### まだ移行していない区分を参照する列

**NULL で始め、FK を張らない。** 張ると移行できない。旧 ID を別列で持ち、その区分の移行後に埋める。

```sql
course_id        CHAR(26) NULL,   -- オンデマンド移行後に埋める
legacy_lesson_id INT NOT NULL,    -- 旧 ID。これを使って後から解決する
```

### 派生データは作らない

**元データから再構築できるものはテーブルにしない**（閉包テーブル、集計、キャッシュ）。
旧環境が持っていても、[移行の対象外](review.md)の B（方針として移行しないもの）に入れる。

### 削除状態は1本で持つ

`active` と `deleted_at` の**両方を持たない**（矛盾した行を作れてしまう）。
**日時1本**にし、`active` が要るなら `deleted_at IS NULL` から導出する。

### ロールバックを書く

**Down は必ず書く。** そのうえで、次の2つに当たらないか確かめる。

- **既存 migration の Down と干渉しないか** — ルックアップに値を足すと、
  その列を ENUM に戻す古い migration が巻き戻せなくなる。**この migration の Down で先に消す**
- **UNIQUE を張り替えていないか** — 列を足して UNIQUE を広げた場合、
  Down で戻すときに**既存行が重複して失敗する**。先に片方を消す手当てが要る

---

## 計画（移行では使わない ＜n＞ 件）

＜無ければ「なし」と書く＞

| 追加するもの | A番号 | なぜ移行で使わないか |
|---|---|---|
| `＜テーブル.列＞` | A＜番号＞ | ＜移行では書き込まない理由と、cutover 後に効く問題＞ |

---

## 確認

```bash
python -m migrator doctor                 # 必須 / 計画それぞれの未適用件数
python -m migrator run --phase common.0   # 必須が1件でも欠けていれば停止
```
