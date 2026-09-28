# コンテンツ — マイグレーション対象

[突き合わせ](review.md#新環境に追加するテーブルカラム) の追加一覧（A1〜A27）を、**school-launcher に当てる migration の単位**に落としたもの。

- **当てる先**: `school-launcher/btoc-backend/db/migrations/`（goose 形式。雛形は `make migrate-create`）
- **実物**: `20260924022810_lw2_content_additions.sql` — **この区分の追加は1本にまとまっている**
- **当てる時期**: **移行直前**（[migration-spec](migration-spec.md) のフェーズ0）
- **確認**: `python -m migrator doctor` / `python -m migrator run --phase common.0`

> **区分をまたぐ DDL は入れない。** 受講の実績（`quiz_attempts` / `submissions` / `survey_responses`）、
> チケット、予約、ライブラリの公開対象は、それぞれ
> [03-enrollment](../03-enrollment/schema-additions.md) / [04-billing](../04-billing/schema-additions.md) /
> [05-support](../05-support/schema-additions.md) が持つ。
> **1本のマイグレーションに複数の区分を混ぜると、区分ごとに流し直せなくなる。**

> **基盤（[01-foundation/schema-additions.md](../01-foundation/schema-additions.md)）が先。**
> ライブの公開範囲（A24）が基盤で作る `tenant_groups` を参照する。

## 2種類ある

| 区別 | 意味 | 欠けているとどうなるか |
|---|---|---|
| **必須** | Step が**実際に書き込む先** | `common.0` で止まる。移行できない |
| **計画** | **移行では使わない**もの | 止まらない。`doctor` が `[TODO]` で出す |

**この区分に「計画」はない。** 追加はすべて移行で書き込む先。

> **新環境の制約は緩めない**（2026-09-23 決定）。旧データが入らない箇所は、
> **制約を外すのではなく、当たった行が移らないことを受け入れる**。
> このため当初案にあった `MODIFY COLUMN ... NULL` はすべて取り下げた。
>
> **migration の実装は school-launcher 側で行う。** ここに書くのは当てる内容と順序で、
> ファイルの作成・適用は school-launcher のリポジトリの作業。

ツール側の定義は `migrator/steps/schema.py` の `CONTENT_SCHEMA`（53件）。**この表とコードは一致させること。**
書き漏らすと `common.0` の存在確認を素通りして、**実 INSERT で初めて落ちる**。

---

## 適用順

FK の参照先を先に作る。**1本のファイルの中で、この順に並べてある。**

```
1  ルックアップへの値追加（INSERT のみ）   ← courses / lessons / quiz / survey の FK 先
2  courses / course_categories への列追加
3  courses / lessons の legacy_id          ← 子データが旧 ID で親を指すため
4  course_tags                             ← courses を参照
5  lessons / video_lessons への列追加、前提条件
6  テスト定義（問題バンク・出題条件）      ← quizzes / lessons を参照
7  課題の配布資料
8  アンケートのページと設問
9  ライブ講座の定義                        ← lessons / tenant_groups を参照
```

**Down は逆順。** `survey_questions.prompt` の `TEXT → VARCHAR(500)` だけは**縮小方向**で、
500文字を超える行があると巻き戻せない（ファイル内にコメントで明記してある）。

---

## 1. ルックアップへの値追加（A3 / A7 / A12 / A20）

**必須。** DDL ではなく **INSERT のみ**。`courses` / `lessons` / `quiz_questions` /
`survey_questions` が参照する FK 先なので、これらを使う行より先に入れる。

| 表 | 足す値 | 無いとどうなるか |
|---|---|---|
| `content_statuses` | `deleted` | 削除済みの講座・ユニットが `archived` に畳まれ、**運営が意図して非公開にしたものと区別できなくなる** |
| `lesson_types` | `quiz` / `assignment` / `document`（講座資料）/ `discussion` / `skill_check` | **テスト・課題・資料が全部 `text` に畳まれる**。ディスカッション・スキル診断のユニットが入らない。**`discussion` / `skill_check` は `20260928072918` で足す**（この区分の migration は適用済みのため） |
| `quiz_question_types` | `free_text`（記述式） | 記述式の設問が入らない。**`text_free` ではない**（設問の変換が `free_text` を書く）。この区分の migration は `text_free` を入れていたが、school-launcher の `20260924080050` が `free_text` に一本化した |
| `survey_question_kinds` | `file_upload` | ファイル添付設問が入らない |

`sort_order` は既存と重ならない値にしてある（`lesson_types` は video(10)/live(20)/text(30)/survey(40) が
埋まっているので 50 以降）。`content_statuses.deleted` は **`is_editable` を明示的に FALSE** にしている —
既定が TRUE なので、指定しないと「削除済みなのに編集できる」状態になる。

**Down は参照が無いときだけ消す。** `172_tenant_lesson_quiz_lookup.sql` の Down が
`lessons.type` / `quiz_questions.type` を ENUM に戻すため、**ここで足した値を使う行が1件でもあると
172 まで巻き戻せない。**

---

## 2. `courses` / `course_categories` への列追加（A1 / A3）

**必須。**

| 追加する列 | 旧の対応 |
|---|---|
| `courses.allowed_ip_address` TEXT NULL | `lesson.allowed_ip_address` |
| `courses.is_used` BOOLEAN NOT NULL DEFAULT TRUE | `lesson_is_used`。**`status` と別の軸**で、畳むと区別が消える |
| `courses.settings` JSON NULL | `lesson` の機能フラグ12列 ＋ `lesson_system`。列を12本増やすより JSON 1本で受ける |
| `course_categories.image_url` VARCHAR(512) NULL | `lesson_cate_img_file_name`。**`icon`（アイコン識別子）とは意味が違う** |
| `course_categories.created_by` CHAR(26) NULL | `regist_user_id` |

> **`course_categories` は `tenant_id` を持たないグローバルマスタ**（`code` が主キー）。
> テナントを増やすとカテゴリ名が衝突するが、recademy 単体では実害が無いので今回は構造を変えない。

---

## 3. `courses` / `lessons` の `legacy_id`（A27）

**必須。** **これが無いと dry-run が途中で止まる** — 子データが旧 ID で親を指しているため。

```sql
ALTER TABLE courses
    ADD COLUMN legacy_id INT NULL,
    ADD UNIQUE KEY uk_courses_legacy (tenant_id, legacy_id);
ALTER TABLE lessons
    ADD COLUMN legacy_id INT NULL,
    ADD UNIQUE KEY uk_lessons_legacy (tenant_id, legacy_id);
```

NULL 可にしているのは、**移行で作られた行だけが旧 ID を持つ**ため。MySQL の UNIQUE は
NULL を重複扱いしないので、NULL の行がいくつ並んでも問題ない。

**ライブ由来の `lessons` は NULL のまま。** 旧 ID は `live_lessons.legacy_id`（A22）が持つ。

---

## 4. `course_tags` / `course_tag_links`（A2）

**必須。** 旧 `lesson_tag`（19行）/ `lesson_lesson_tag`（39行、対象テナント分）。
新環境にタグの概念が無く、`category`（1講座1件）では代用できない — タグは1講座に複数付く。

`course_tags.legacy_id` は、旧 ID で親を指す割当を移行時に引くため。
`course_tag_links` は `(tag_id, course_id)` が UNIQUE。

> **`course_tags` は `tenants` を NO ACTION で参照する。** デモデータの掃除
> （`cmd/seed` の `cleanupDemoData`）に**明示的に列挙が要る**（`make check-seed-cleanup` が見る）。

---

## 5. `lessons` / `video_lessons` への列追加と前提条件（A4 / A5 / A15）

**必須。**

新環境は公開タイミングを `drip_delay_days`（相対日数）しか持たない。lw2 は**絶対日時の開閉**も
持っているので、そのままでは「この日から公開」が再現できない。

| 追加する列 | 旧の対応 |
|---|---|
| `lessons.open_at` / `close_at` DATETIME(3) NULL | `unit.open_datetime` / `close_datetime` |
| `lessons.close_after_days` INT NULL | `close_day_from_lesson_start_date` |
| `lessons.drip_delay_basis` VARCHAR(16) NOT NULL DEFAULT 'enrollment' | `open_day` / `payment_open_day`。**2列を1列に畳むと起点が消える** |
| `lessons.complete_message` / `search_keyword` TEXT NULL、`duration_min` INT NULL、`settings` JSON NULL | 修了時メッセージ・検索キーワード・想定学習時間・開閉と有料属性ほか |
| `video_lessons.complete_type` VARCHAR(32) NULL | `lecture_complete_type` / `pmovie_complete_type`。**無いと移行後に修了状態がずれる** |
| `video_lessons.skip_prevention` BOOLEAN NOT NULL DEFAULT FALSE | `skip_prevention_setting`（早送り禁止） |
| `video_lessons.settings` JSON NULL | 続きから再生・プラグイン連携 |

`lesson_preconditions`（`lesson_id` / `required_lesson_id`、UNIQUE）は旧 `unit_precondition`（37行）。

> **テーブルだけでは効かない。** 受講画面の進行制御が実装されるまでは
> **全ユニットが最初から受講できる**状態になる。

> **`lesson_exemptions` は作らない。** 旧 `unit_exemption`（1行）は
> `(unit_id, exemption_unit_id, exemption_score)` という**規則**で、会員ごとの免除表では受けられない。
> 前提条件側の拡張として設計し直す（→ [対象外 A](review.md#a-移行できないもの)）。

---

## 6. テスト定義 — 共有問題バンクと出題条件（A6 / A7 / A8）

**必須。** lw2 の `question` は**テスト非依存の共有問題バンク**で、`test_sub` が
「このカテゴリ・この難易度から N 問出す」という**出題条件**を持つ。
新環境の「クイズに属する固定リスト（`quiz_questions`）」では表現できない。

> **アプリはまだ問題バンクと出題条件を読まない。ランダム出題はスキーマだけ先に置いてある**
> （2026-09-28 決定）。cutover 前に「作る」か「固定リストに展開する」かを決める
> （→ [確認事項 C6](../open-questions.md)）。

| 追加するもの | 旧の対応 |
|---|---|
| ~~`quiz_question_categories`~~ → **`quiz_question_labels.legacy_id`** | `question_cate`（124行）。**管理者が作るラベルと同じ表に統合した**（school-launcher `20260928082433`、2026-09-28 決定） |
| `quiz_question_banks` | `question`（3,880行）。テストに属さない |
| `quiz_question_rules` | `test_sub`（285行）。カテゴリ・難易度・出題数 |
| `quiz_questions.bank_id`（＋FK）/ `image_url` / `name` / `hint` / `required` | **移した設問には `bank_id` が必ず入る**（旧の固定出題も問題バンクを指すため）。NULL になるのは新環境で作ったテストだけ |
| `quiz_options.image_url` | |
| `quizzes.max_attempts` / `suspend_enabled` / `display_settings` | `test.exam_max_number` / `suspended_chk` / 表示設定6列 |

> **`quizzes` の UNIQUE `(tenant_id, lesson_id)` は外さない**（制約を緩めない方針）。
> 複数テストを持つユニットがあれば2件目以降は移らないので、抽出時に件数を数える。
>
> **`quiz_options.body` は VARCHAR(1000) のまま。** 旧 `selection1..20` は TEXT だが、
> 1000文字超が見つかった時点で TEXT に広げる migration を足す（切り捨てない）。

> **`quiz_question_banks` は `tenants` を NO ACTION で参照する。** `cleanupDemoData` に**設問より後**で列挙が要る。
> 分類（`quiz_question_labels`）は `tenants` の CASCADE で消えるので列挙しない。

> **labels は `(tenant_id, name)` が一意。** 同じテナントに自テナントと共有（旧 `tenant_id = 0`）の
> 分類が入るので名前が重なる（ステージングで 28 組、共有内でも `ITパスポート` が 8 件）。
> **そのまま入れるとカテゴリ 35 件・問題バンク 546 件・固定出題の設問 407 問が連鎖して移らない**ので、
> 移行ツールが名前に「（共有）」「（2）」などを付けて区別する（2026-09-28 決定）。旧の ID は `legacy_id` に残る。

---

## 7. 課題の配布資料（A13）

**必須。** 旧は配布ファイルを5本まで列で持っていた（`report_disp_file_name1-5`）。
列のままだと「3本目だけ消す」が表現しづらいので `assignment_materials` に行として展開する。

あわせて `assignments.due_after_days` / `video_url` / `settings` を足す。

> **提出側は受講（3）の担当。** `submission_files` / `submissions.score` /
> `submission_feedbacks.question_comments` はここには入れない。

---

## 8. アンケートのページと設問（A12）

**必須。** ページ番号を設問側に持たせると「ページだけ並べ替える」ができないので `survey_pages` に切る。

```sql
UNIQUE KEY uk_survey_pages (tenant_id, lesson_id, legacy_id)
```

> **`lesson_id` を含めた理由。** 旧 `enquete` はユニットに属さず、**同じアンケートを複数のユニットが
> 参照できる**（実測7件）。`survey_lessons` は `lesson_id` が主キーなのでユニットごとに複製するしかなく、
> 同じ `legacy_id` がレッスンの数だけ現れる。**テナント単位の UNIQUE だと 89行中 60行が入らない。**

あわせて `survey_lessons.name`、`survey_questions.page_id`（＋FK）/ `image_url`、
`survey_question_options.image_url` を足し、**`survey_questions.prompt` を VARCHAR(500) → TEXT** に広げる
（旧の設問文が切り捨てられるため）。

> **`survey_lessons.lesson_id` は PK のまま**（制約を緩めない方針）。同じ `enquete` を複数ユニットが
> 参照していた場合、2件目以降は移らない。事前検査で件数を数える。
>
> **回答側は受講（3）の担当。** `survey_responses.entity_type` / `entity_id` / `suspended` は入れない。

---

## 9. ライブ講座の定義（A22 / A23 / A24 / A25 / A26）

**必須。**

| 追加するもの | 旧の対応 |
|---|---|
| `live_lessons.legacy_id` ＋ UNIQUE `uk_live_lessons_legacy` / `settings` JSON NULL | `live_lesson`（18件） |
| `live_lesson_categories` / `live_lesson_category_links` | `live_lesson_cate`（5件）/ `live_lesson_lesson_cate`（6件） |
| `live_lesson_group_targets` | `live_lesson_group`（実測0件） |
| `live_lesson_occurrences.deleted_at` / `remind_enabled` / `settings` ＋ `idx_llo_deleted` | `live_lesson_date.del_chk` / `mail_send_chk` / `date_type` |
| `live_lesson_recurrence_rules` / `_details` / `_exclusions` | `live_lesson_date_setting`（86件）/ `_detail`（93件）/ `live_lesson_exclusion_date`（18件） |

> **`lessons.legacy_id` には入れない。** その列はオンデマンドが `unit.unit_id` で使っており
> （`uk_lessons_legacy`）、**ライブとユニットは別の採番系なので必ず衝突する**（実測18件中11件）。
> ライブの行は `lessons.legacy_id` を NULL のままにする。

> **`live_lesson_categories` は `tenants` を RESTRICT で参照する。**
> `cleanupDemoData` に `lessons` より前で列挙が要る。

> **連日設定は開催回と対。** 生成済みの開催回は `live_lesson_occurrences` に実体化しているので
> 無くても過去の予約は移せるが、**無いと cutover 後に開催回を増やせなくなる**。
> 除外日も対で、片方だけ移すと意味が変わる。

---

## 計画（移行では使わない）

**なし。** この区分の追加はすべて移行で書き込む先。

---

## 取り下げた追加

| 追加案 | 取り下げた理由 |
|---|---|
| `lesson_exemptions` | 旧 `unit_exemption` は**規則**（`exemption_unit_id` ＋ `exemption_score`）で、会員ごとの免除表では**何行入れればよいかが決まらない**。前提条件（A15）側の拡張として設計し直す |
| ライブ専用のアクセス制御表 | 旧 `live_lesson_limit_item` の役割は、受講（3）で `payment_item_lesson_authority` → `enrollments` に写る。**受け皿を作らず、ライブをその商品が売っている講座の配下に置く** |
