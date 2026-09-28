# 受講 — 移行仕様

区分 **3 受講**（受講権限 / 学習履歴 / テスト結果 / 課題提出 / アンケート回答 / ライブ予約 / 修了証・バッジ）を
移行ツールでどう流すか。共通の方針は [migration-spec.md](../../migration-spec.md)、
突き合わせは [review.md](review.md)、追加するスキーマは [schema-additions.md](schema-additions.md)。

> **コンテンツ（2）が先。** 実績は定義に紐づく（`quiz_attempts.quiz_id` /
> `submissions.assignment_id` / `survey_responses.lesson_id` / `live_reservations.occurrence_id`）。

> **この区分のマイグレーションはまだ無い。** `doctor` が `[TODO]` で出るのが現在の正しい状態で、
> `run --section enrollment` は `common.0` で止まる。

---

## 1. 前提

### 1-1. 運営への確認事項

**この区分の分も含めて [open-questions.md](../open-questions.md) に1枚でまとめてある。**
同じ話を2か所に置かない。

### 1-2. 制約による不整合

**[constraint-violations.md](../constraint-violations.md) にまとめてある。**
NOT NULL / UNIQUE / CHECK に当たるものと、参照先が物理削除されているものを分けて持つ。

### 1-3. 決定済み（再確認だけ）

| 決めたこと | 内容 | 決めた日 |
|---|---|---|
| **`enrollments` の母集合は受講権限**（4,289組） | 学習実績（33,912組）は母集合にしない。差の大半は無料講座で、旧環境でも権限行を持たないのが正常。**最終的に全区分を移行すれば正しい状態になる** | 2026-09-24 |
| チケットの消費履歴は移さない | キャンセルに要るのは「誰が予約したか」と「何枚使うか」だけ。**台帳の行は予約から組み立てて作る** | 2026-09-24 |
| 欠席も消費済みとして数える | `occupies_seat = 1`。除くと台帳が0行になる | 2026-09-24 |
| バッジは外部システムを使い続ける | 付与実績は lw2 の DB に無い（`BadgeApi` 経由）。**新環境が旧 ID を持っていれば参照を続けられる**（`users.legacy_id` / `tenants.legacy_id` を追加済み） | 2026-09-24 |

### 1-4. 本番ダンプ受領後に確認すること

- **振替予約**（`live_lesson_reserve.change_reserve_id` / `base_reserve_id`）。ステージング実測0件。**あれば `live_reservations` に列を足す**
- **受講権限の重複の実態**。ステージングは 6,966行 → 4,289組（2,677行が重複）。本番で桁が変わるなら畳み方を再検討する
- **`user_learning_unit` の重複**（実測 76件）と `suspend_data` の形式（実測 3,147件）

### 1-5. ステージングダンプでの実測（2026-09-18 取得）

| 旧テーブル | 全テナント | ReCADemy | 備考 |
|---|---:|---:|---|
| `payment_item_lesson_authority` | 7,462 | **6,966**（4,289組） | **`user` 経由で絞る。** `payment_item` で絞ると `item_id` が NULL の 3,282行が落ちる |
| `payment_item_lesson_authority_log` | 121,199 | — | 移さない |
| `user_learning_lesson` | 35,532 | **34,510**（33,912組） | 修了済 258 / 削除 7,123 |
| `user_learning_unit` | 19,009 | **13,008** | 削除 198 |
| `user_learning_unit_log` | 33,998 | — | 移さない |
| `user_learning_test` | 799 | **371** | |
| `user_learning_test_sub` | 8,462 | **4,922** | |
| `user_learning_report` | 303 | **228** | |
| `enquete_answer` | 388 | **232** | `enquete` と join して絞る。ユニット 80 / レポート 149 / お知らせ 3 |
| `live_lesson_reserve` | 32 | **32** | |
| `config_certificate` | 0 | **0** | 設定は未登録 |
| `certificate_no` | 1 | **1** | 次番号 7。**`serial_next` に引き継ぐ** |
| `user_certificate` | 3 | **3** | `entity_id` は `user_learning_lesson_id` |
| `badge_item` | 62 | **61** | |

---

## 2. データ登録順

新環境は実 FK を持つため順序が強制される。

```
[前提]       区分1 基盤（users / tenant_groups）
             区分2 コンテンツ（courses / lessons / quizzes / assignments / survey_* / live_*）
                ↓
[migration]  A8 enrollments.settings
             A9 lesson_progress.progress_status / settings / deleted_at
             A1〜A7（テスト結果・課題提出・アンケート回答・ライブ予約・修了証）
                ↓
enrollment.1 受講権限        payment_item_lesson_authority → enrollments
enrollment.2 学習履歴        user_learning_unit            → lesson_progress
enrollment.3 テスト結果      user_learning_test            → quiz_attempts → quiz_answers
                                                           → quiz_answer_selected_options
enrollment.4 課題提出        user_learning_report          → submissions → submission_files
                                                           → submission_feedbacks
enrollment.5 アンケート回答  enquete_answer                → survey_responses → survey_answers
                                                           → survey_answer_selected_options
enrollment.6 ライブ予約      live_lesson_reserve           → live_reservations
             live_lesson_review                            → live_lesson_reviews
enrollment.7 修了証・バッジ  config_certificate            → certificate_settings
             user_certificate                              → certificates → certificate_events
```

**3-1 と 3-2 は互いに依存しない。** `lesson_progress` は `enrollments` を参照しないので、
母集合が決まる前でも 3-2 だけ先に流せる。

### 2-2. 実行手順

```bash
# 1. スキーマを当てる（school-launcher 側）
cd ../../proseeds/school-launcher
make migrate-create NAME=lw2_enrollment_additions   # A1〜A9 を1本に
make check-migrations && make check-seed-cleanup
make reseed

# 2. 前提の区分を入れる
cd -
.venv/bin/python -m migrator run --section foundation
.venv/bin/python -m migrator run --section content --skip-preflight

# 3. 受講を流す
.venv/bin/python -m migrator run --dry-run --section enrollment --skip-preflight
.venv/bin/python -m migrator run --section enrollment --skip-preflight
.venv/bin/python -m migrator verify
```

`cleanupDemoData`（`btoc-backend/cmd/seed/main.go`）に **`live_lesson_reviews` と
`submission_files`** を足すこと。`tenants` を参照するので `make check-seed-cleanup` が要求する。

---

## 3. データ移行仕様

### 3.1 抽出（extract）

**`tenant_id` を持たない表が多い。** 親と join して絞る — 落とすと他テナントの行を拾う。

| 旧テーブル | 絞り込みの経路 |
|---|---|
| `payment_item_lesson_authority` | `payment_item.tenant_id` |
| `user_learning_unit` | `user_learning_lesson` → `lesson.tenant_id`（`fetch_joined(via=...)`） |
| `user_learning_lesson` | `lesson.tenant_id` |
| `enquete_answer` | `enquete` → `unit` → `lesson.tenant_id` |
| `live_lesson_reserve` | `live_lesson_date` → `live_lesson.tenant_id` |

### 3.2 変換（transform）

**受講権限（3-1）**

- **母集合は `payment_item_lesson_authority`。** 権限が要るのは 235講座中 71件で、残りは無料講座
- **lw2 の解決規則に従う。** `LessonModel::1804` が `GROUP BY user_id, lesson_id` で畳み、
  期限は `MAX(authority_end_date)` を取っている。**独自に決めない**
- `status` は **`del_chk`** で決める（`1` → `canceled` / `0` → `active`）。
  **`cancel_chk` は使わない** — 名前に反してキャンセルフラグではなく、
  `PaymentAuthorityModel` の INSERT 5か所で定数が入るだけで UPDATE されない
- `source` は **`purchase`**（`manual` という値は存在しない）
- `no_limit_chk = 1` なら `expires_at = NULL`。元の値は `settings` に残す
- **期限切れはそのまま移す。** 実測で 1,874組中 1,603組（86%）が失効済みだが、旧環境でも開けない。**期限を延ばさない**

**学習履歴（3-2）**

- `completed_at` は **`learning_status = 1` のときだけ** `complete_date` を入れる
  （実測で両者は完全に一致する）
- `progress_status` は**ユニット種別と対にして残す**（例: `quiz:2`）。
  種別ごとに同じ数値の意味が違うため、値だけでは復元できない
- `suspend_data` は動画の再生位置として解釈できるときだけ `last_position` に入れ、
  それ以外は `settings` に原文で残す

**ID の採番**は共通仕様どおり `ulid.for_row(旧テーブル名, 旧キー)`。
畳んだ行（受講権限）は **`(user_id, lesson_id)` の組をキーにする** — 行 ID では畳めない。

### 3.3 投入（load）

`insert_many` は自然キーが既にある行を飛ばす（冪等）。自然キーは
`enrollments` が `(tenant_id, user_id, course_id)`、`lesson_progress` が `(tenant_id, user_id, lesson_id)`。

### 3.4 移行の対象外

[review.md の対象外](review.md#移行の対象外移行できないもの--移行しないもの) を参照。
この区分で量が大きいのは次の3つ。

| 対象 | 行数 | 理由 |
|---|---:|---|
| `payment_item_lesson_authority_log` | 121,199 | 純ログ |
| `user_learning_unit_log` | 33,998 | 純ログ |
| テスト中断・再開の3テーブル | 約300万 | 受験中の作業データ（採点時に本体へコピーされる） |

### 3.5 検証

- `verify --section enrollment` が OK になること。**移行元から作り直した行と全列で突き合わせる**ので、
  決定論 ULID の照合（`enrollments` は畳んだ組）もここに含まれる
- 再実行で 0 行（冪等）
- `enrollments.status` の期限切れ判定は実行時刻に依存する。**`run` の直後に `verify` を流す**
- `out/not-migrated.csv` の件数と理由が、1-1 で決めた内容と矛盾しないこと

---

## 未確定として残っているもの

- **無料講座の受講登録**（→ [確認事項](../open-questions.md)）。**3-1 の Step は権限側だけで書ける**ので着手は止まらない
- **講義の `progress_status` の意味**（定数ファイルに定義が無い）
- **バッジの付与実績は移せない。** lw2 の DB に無く、外部のバッジシステムが持つ
  （`BadgeApi`）。**定義（`badge_item`）は A11 の `badge_definitions` に移す**
- `certificates.product_id` は課金（4）の移行後に埋める
