# 受講 — マイグレーション対象

[突き合わせ](review.md#新環境に追加するテーブルカラム) の追加一覧を、**school-launcher に当てる migration の単位**に落としたもの。

- **当てる先**: `school-launcher/btoc-backend/db/migrations/`（goose 形式。雛形は `make migrate-create`）
- **実物**: `20260924054151_lw2_enrollment_additions.sql`（ブランチ `feat/lw2-enrollment-schema`）
- **当てる時期**: **移行直前**（[migration-spec](migration-spec.md) のフェーズ0）
- **確認**: `python -m migrator doctor` — この区分が未適用なら `[TODO]` で出る

> **適用済み。** `doctor` の TODO は billing / support だけになる。

> **コンテンツ（2）が先。** `quiz_attempts` / `submissions` / `survey_responses` の親
> （`quizzes` / `assignments` / `survey_lessons`）はコンテンツで作る。

## 2種類ある

| 区別 | 意味 | 欠けているとどうなるか |
|---|---|---|
| **必須** | Step が**実際に書き込む先** | `common.0` で止まる。移行できない |
| **計画** | **移行では使わない**もの | 止まらない。`doctor` が `[TODO]` で出す |

**この区分に「計画」はない。**

> **新環境の制約は緩めない**（2026-09-23 決定）。旧データが入らない箇所は、
> **制約を外すのではなく、当たった行が移らないことを受け入れる**。

ツール側の定義は `migrator/steps/schema.py` の `ENROLLMENT_SCHEMA`（20件）。**この表とコードは一致させること。**

---

## 適用順

```
0  受講権限・学習履歴への列追加  ← enrollments / lesson_progress
1  テスト結果への列追加        ← quiz_attempts / quiz_answers（コンテンツの quizzes を参照）
2  課題提出の新テーブルと列    ← submissions / submission_feedbacks
3  アンケート回答への列追加    ← survey_responses
4  ライブ予約への列追加        ← live_reservations
5  ライブレビュー              ← lessons / users を参照
6  修了証・バッジへの列追加
```

---

## 0. 受講権限・学習履歴への列追加（A8 / A9 / A10）

**必須。**

```sql
-- 権限の取り消し (A10)。旧 payment_item_lesson_authority.del_chk = 1 を受ける。
-- **既存の3値では表せない。** expired は期間の満了、refunded は返金で、
-- どちらも「運営が権限を取り下げた」とは別の軸。実測 828 行 (畳んで 273 組)。
INSERT IGNORE INTO enrollment_statuses
    (code, name_ja, is_active, is_terminal, sort_order, is_system) VALUES
    ('revoked', '取り消し', FALSE, TRUE, 40, TRUE);

-- 旧 payment_item_lesson_authority の、新環境に対応列が無いもの
ALTER TABLE enrollments
    ADD COLUMN settings JSON NULL;   -- cancel_chk / no_limit_chk / remote_chk / item_id ほか

-- 旧 user_learning_unit の、新環境に対応列が無いもの
ALTER TABLE lesson_progress
    ADD COLUMN progress_status VARCHAR(32) NULL,   -- 旧 progress_status（種別と対で持つ）
    ADD COLUMN settings        JSON        NULL,   -- 旧 suspend_data ほか
    ADD COLUMN deleted_at      DATETIME(3) NULL;   -- 旧 del_chk = 1
```

> **`cancel_chk` を `status = 'canceled'` に写さない。** 名前に反してキャンセルフラグではない。
> `PaymentAuthorityModel` の INSERT 5か所すべてが**作成時に定数を書き込んでおり、
> UPDATE する箇所が存在しない**。実測の 1=3,064 / 0=620 は購入経路の違いを表す。
> **実質の取り消しは `del_chk`**（実測 828件）。

> **無期限は `expires_at = NULL` で表す。** ただし「無期限」と「未設定」が区別できなくなるので、
> 旧 `no_limit_chk` / `payment_no_limit_chk`（各 110件）は `settings` に残す。

> **`progress_status` はユニット種別ごとに意味が変わる。** `unit_learning_progress_master` が
> `(progress_id, unit_type_id)` で引く作りで、同じ `2` がテストなら「受験中」、
> アンケートなら「回答済」、レポートなら「評価待」、集合研修なら「出席希望」
> （`Application_Constants_UserLearningConstants`）。**値だけを移すと意味が消えるので、
> 種別と対にして持つ。** 講義（`unit_type_id = 1`）の値は**定数ファイルに定義が無い**ので、
> 意味が決まるまで畳まない（→ [確認事項](../open-questions.md)）。

> **`suspend_data` を `last_position` にそのまま入れない。** 旧は SCORM の中断データ
> （実測 3,147件）で、新の `last_position` は動画の再生位置を想定した列。形式が違う。

> **`expires_at` は `TIMESTAMP`（上限 2038-01-19）。** 旧は無期限を100年後の日付で表しており
> （実測 最大 2126-09-16、2038超が 151件）、**そのまま入れると実 INSERT で
> `Incorrect datetime value` になる**。無期限（NULL）に寄せ、元の日付を `settings` に残す。
> 事前検査にも `TIMESTAMP` の範囲チェックを足してある（`_datetime_range`）。

> **母集合は購入による受講権限**（2,246組、2026-09-24 決定）。学習実績（23,956組）との差は
> 93% が無料講座で、旧環境でも権限行を持たないのが正常。

---

## 1. テスト結果への列追加

**必須。**

```sql
ALTER TABLE quiz_attempts
    ADD COLUMN passed       BOOLEAN NULL,      -- 旧 user_learning_test.test_pass（当時の合否）
    ADD COLUMN duration_sec INT     NULL;      -- 旧 test_time

ALTER TABLE quiz_answers
    ADD COLUMN is_correct        BOOLEAN     NULL,  -- 旧 question_pass（当時の正誤）
    ADD COLUMN option_order      VARCHAR(64) NULL,  -- 旧 option_order（選択肢の表示順）
    ADD COLUMN sort_no           INT         NULL,
    ADD COLUMN pre_question_pass BOOLEAN     NULL;
```

> **`passed` と `is_correct` は「当時の判定結果」。** 新環境は `score >= passing_score` /
> `quiz_options.is_correct` から都度計算するが、**採点基準を後から変えると過去の結果が変わる**。
> 表示は移行した値を優先する。

> **受験の終了判定は `test_end_time` で見る。** `user_learning_test.finished_chk` は
> **lw2 が一度も書いていない**（実際のフラグは `user_learning_test_update` 側）。
> これを終了フラグとして読むと**全件が「中断」として入る**。

> **中断・再開の3テーブル（計300万行）に受け皿は要らない。** 採点処理の実装で
> **「受験中の作業データ」**と確定した（採点時に `user_learning_test` へコピーされる）。
> **cutover 時点で中断中の受験だけが失われる**ので、件数を確認して合意を取る。

---

## 2. 課題提出の新テーブルと列追加

**必須。** 旧は提出ファイルを5本まで列で持っていた（`eval_disp_file_name1-5`）。行に展開する。

```sql
CREATE TABLE submission_files (
    id            CHAR(26) NOT NULL PRIMARY KEY,
    tenant_id     CHAR(26) NOT NULL,
    submission_id CHAR(26) NOT NULL,
    sort_order    INT NOT NULL DEFAULT 0,        -- 旧 1..5
    file_name     VARCHAR(300) NOT NULL,         -- 旧 eval_disp_file_nameN
    object_key    VARCHAR(512) NOT NULL,         -- 旧 eval_save_file_nameN
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_submission_files (submission_id, sort_order),
    CONSTRAINT fk_submission_files_tenant     FOREIGN KEY (tenant_id)     REFERENCES tenants(id),
    CONSTRAINT fk_submission_files_submission FOREIGN KEY (submission_id) REFERENCES submissions(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

ALTER TABLE submissions
    ADD COLUMN score    INT  NULL,   -- 添削が無い提出のスコア
    ADD COLUMN settings JSON NULL;   -- 旧 send_PC_chk / send_mobile_chk

ALTER TABLE submission_feedbacks
    ADD COLUMN question_comments JSON NULL;   -- 設問ごとの添削（旧 report_question_comment）
```

> **`submissions.object_key` は残す。** 1本目を既存列に入れたまま `submission_files` にも
> 同じ行を作るか、`submission_files` に一本化するかは実装時に決める（**二重管理にしない**）。
> 実測で2本目以降を使う提出は 4,963件中 2件。

> **`submissions.submitted_at` の NOT NULL は外さない**（緩めない方針）。
> 未提出（旧 `submit_date` が NULL）の課題は移らない。件数を確認して合意を取る。
> **`created_at` のように既定値がある列も、Step が書くなら NOT NULL 検査の対象**にすること
> （既定値があるからと素通りさせると、実 INSERT で初めて落ちる）。

> **配布資料（`assignment_materials`）はコンテンツ（2）の担当。**

---

## 3. アンケート回答への列追加

**必須。** **これが無いと回答の 47% が落ちる。**

```sql
ALTER TABLE survey_responses
    ADD COLUMN entity_type VARCHAR(16) NOT NULL DEFAULT 'lesson',  -- lesson / news / report
    ADD COLUMN entity_id   CHAR(26) NULL,
    ADD COLUMN suspended   BOOLEAN  NOT NULL DEFAULT FALSE;
```

旧 `enquete_answer.entity_type_id` は 1=お知らせ（545件）/ 2=ユニット / 3=レポート（611件）を指すが、
**新環境はユニットに紐づく回答しか受けられない**。

> **設問・ページ側（`survey_pages` ほか）はコンテンツ（2）の担当。**

---

## 4. ライブ予約への列追加

**必須。**

```sql
ALTER TABLE live_reservations
    ADD COLUMN verification_key VARCHAR(200) NULL,   -- 旧 live_lesson_reserve.verification_key
    ADD COLUMN settings         JSON         NULL;   -- 旧 3フラグ・recent_access_date
```

| 列 | 旧の対応 | 備考 |
|---|---|---|
| `verification_key` | `verification_key` varchar(200) NOT NULL | **出席確認に使う照合値**（QR・コード入力）。実測は全件32文字。**パスワードや認証コードの平文ではないので読んでよい** |
| `settings` | `cancel_chk` / `attendance_chk` / `stop_chk` / `recent_access_date` | **`status` に畳んだ元の値を残す。** 3フラグの組み合わせは `status` の4〜5値では表しきれない |

あわせて `live_reservation_statuses` に **`host_canceled`** を足す（主催側の中止。`status` の FK 先）。

> **`uk_lr_occurrence_user` は外さない。** 旧の重複（実測4組8行）は
> **どれを残すかを運営が決める**（[migration-spec](migration-spec.md) の確認事項）。
>
> **`change_reserve_id` / `base_reserve_id`（振替予約）の列は足していない。** 実測0件。
> **本番で出たらここに足す。**

---

## 5. ライブレビュー

**必須。** 旧 `live_lesson_review`（実測3件）。

**`course_reviews` はコース単位**なので、受け皿 course に付けると**全ライブのレビューが1つの course に混ざる**。
ライブ単位の表を足す。

```sql
CREATE TABLE live_lesson_reviews (
    id                    CHAR(26)     NOT NULL PRIMARY KEY,
    tenant_id             CHAR(26)     NOT NULL,
    lesson_id             CHAR(26)     NOT NULL,
    user_id               CHAR(26)     NOT NULL,
    legacy_id             INT          NOT NULL,   -- 旧 live_lesson_review_id
    title                 VARCHAR(100) NULL,
    body                  TEXT         NULL,
    star_rating           INT          NULL,
    admin_comment_user_id CHAR(26)     NULL,
    admin_comment         TEXT         NULL,
    admin_commented_at    DATETIME(3)  NULL,
    deleted_at            DATETIME(3)  NULL,
    created_at            DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at            DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    UNIQUE KEY uk_llr_legacy (tenant_id, legacy_id),
    KEY idx_llr_lesson (tenant_id, lesson_id),
    CONSTRAINT fk_llr_lesson FOREIGN KEY (lesson_id) REFERENCES lessons (id) ON DELETE CASCADE,
    CONSTRAINT fk_llr_user   FOREIGN KEY (user_id)   REFERENCES users (id) ON DELETE CASCADE,
    CONSTRAINT fk_llr_tenant FOREIGN KEY (tenant_id) REFERENCES tenants (id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

> **`tenants` を RESTRICT で参照する。** `cmd/seed` の `cleanupDemoData` に列挙が要る
> （`make check-seed-cleanup` が見る）。

---

## 6. 修了証・バッジへの列追加

**必須。**

```sql
-- **NOT NULL は外さない**（緩めない方針）。商品単位の修了証は移らない。
ALTER TABLE certificates
    ADD COLUMN product_id CHAR(26) NULL;            -- 旧 payment_item（課金 K01 の移行後に埋める）

-- **NOT NULL は外さない**（緩めない方針）。講座以外を指すバッジは移らない。
ALTER TABLE digital_badges
    ADD COLUMN reference_badge_id CHAR(26) NULL,    -- 旧 badge_item.reference_item_id
    ADD CONSTRAINT fk_digital_badges_reference FOREIGN KEY (reference_badge_id) REFERENCES digital_badges(id);
```

> **`product_id` に FK は張らない。** 課金（K01 商品、`payment_item` 301行）が未移行のため。移行後に埋める。

> **`digital_badges` 本体を移す Step がまだ無い。** 旧 `badge_item` は 61行あり、
> **移行の原則では移す対象**。`reference_badge_id` だけ足しても入れる行が無いので、
> **Step と合わせて作る**（→ [残作業](migration-spec.md)）。

> **`certificates.issuer_name` は NOT NULL。** 発行時点の値を凍結する列なので、
> **移行時に必ず値を決める**（設定が NULL なら `tenants.name` を入れる、など）。
> テナント設定側の `certificate_settings.issuer_name` は NULL 可。
> **同じ列名で NULL 可と NOT NULL が混在しているので取り違えないこと。**

---

## 計画（移行では使わない）

**なし。**
