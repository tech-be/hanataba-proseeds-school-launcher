# コンテンツ — 新システムの機能仕様（移したデータの見え方）

移行の見直しの手順 1（[進捗](../rework-progress.md)）。**新システムがコンテンツのデータ（講座・章・レッスン・動画・テスト・課題・アンケート・ライブ・コース・カテゴリ）をどう読み書きするか**を、移したデータがどう見えるかの観点で書き出したもの。手順 2 のテスト仕様書と、手順 3 の移行仕様の材料にする。

- **基準**: school-launcher `hanataba_dev` の `584026af`（2026-10-24。2026-10-26 時点でも最新）。コードを読んで調べた（動かしてはいない）。
- **コードの場所**は school-launcher からの相対パス。`btoc-backend/internal/` は `internal/`、`btoc-backend/db/migrations/` は `MIG/`、`btoc-frontend/src/` は `frontend/` と略す。
- **未確認**は推論だけのもの。**確認済み**は移し方に効く点をコードで読み直したもの。

## 0. 移し方に効く点（先に）

| # | 内容 | 場所 |
|---|---|---|
| 0-1 | **アプリが扱えるレッスンの種別は `video` / `live` / `text` / `survey` の 4 つだけ。** lookup にある `quiz` / `assignment` / `document` / `discussion` / `skill_check` のレッスンは、受講画面に本文が出ず、運営がレッスンを編集すると 400（画面は `type` を毎回送り、`oneof=video live text survey` で弾く）。完了は講座詳細の「完了にする」だけ | `internal/dto/requests_course.go:41,52`、`frontend/.../lesson-content-renderer.tsx` |
| 0-2 | **問題バンク（`quiz_question_banks`）と出題条件（`quiz_question_rules`）を読む処理が無い。** テストは `quiz_questions` の固定の一覧だけで出題する（順番どおり。シャッフルも無い）。出題条件だけのテストは設問 0 件で受験できない | `internal/quiz/` |
| 0-3 | **繰り返しの設定（`live_lesson_recurrence_*`）・グループの公開（`live_lesson_group_targets`）・カテゴリ・商品の制限は読まれない。** 開催回は `live_lesson_occurrences` の実体だけ。予約できるのは「講座に受講登録している人」 | `internal/live/` |
| 0-4 | **開催回の `deleted_at` は読まれない。** 削除済みの回もカレンダー・予約・リマインドに出る。止めるのは `canceled_at` | `internal/live/repository/occurrence_repo.go:22-24` |
| 0-5 | **`live_lessons` の行は、`live_room_id` が空だとレッスンの編集で消える**（**確認済み**）。開催回・予約は `lessons` を参照しているので消えない（**確認済み**。`MIG/20260930013549`）。消えるのは `scheduled_at`（受講画面の「開始予定」）・`settings`・旧 ID。`live_room_id` を入れると「配信中」と表示される | `internal/repository/lesson_repo.go:188-201` |
| 0-6 | **講座の `status = 'deleted'` は受講者に見える**（除外は `<> 'archived'` だけ）。状態を変える PATCH も 400。削除済みの講座は `archived` | `internal/repository/course_repo.go:300-304`、`internal/domain/course.go:69-73` |
| 0-7 | レッスンの削除は `deleted_at`（どの API でも存在しない扱い）。`status = 'deleted'` は受講者からは隠れるが、管理画面に出て編集は 400 | `lesson_repo.go:49-75` |
| 0-8 | **動画の URL の形が合わないと再生できない。** `storage` は自前のバケットのキー、`pmovie` は許可したホストの `https://….m3u8`。旧の 40 文字のトークンや旧サーバーの URL は再生できず、`pmovie` は**タイトルを直すだけの保存も 400** になる | `internal/service/video_playback_service.go:37-75`、`frontend/lib/video-source.ts` |
| 0-9 | **`lesson_preconditions`（前提条件の鍵）は読まれない。** 講座の中のユニットは最初からすべて開く。効くのは `drip_delay_days`（受講登録から N 日後）とコースの `sequential` だけ | `git grep` 0 件 |
| 0-10 | テキストのレッスン本文・テストの問題文・解説は**プレーンテキスト（簡易 Markdown）で表示**。HTML はタグがそのまま見える | `frontend/components/lesson/text-lesson-content.tsx` |
| 0-11 | **`courses.thumbnail_url` はバケットのキー**（`tenants/{tid}/courses/{cid}/thumbnail/...`）。完全な URL を入れると講座詳細で壊れた URL になる | `internal/dto/responses_course.go:41-48` |
| 0-12 | `courses.category` は全テナント共通の `course_categories.code`（`/courses` の絞り込み。recademy は `settings.top_catalog.categories` の 6 件）。`/explore` はテナントの `tenant_course_categories` だけを見る（**2 系統**。sync-issues B3） | `internal/repository/catalog_repo.go:76-81` |
| 0-13 | 講座の `price` は NULL が新の約束事（価格はコースの `learning_paths.price`）。`courses.is_sample = TRUE` はスターターテンプレートとして一括削除の対象になる | `internal/service/lesson_service.go:283-289`、`internal/repository/sample_content_repo.go:44-50` |
| 0-14 | `learning_paths.access_period_value` が上限（日 3650・月 120）を超えると、コースの一覧の API 全体が 500 | `internal/learning/repository/learning_path_repo.go:32-73` |
| 0-15 | 公開の判定が API ごとに違う。`/catalog` は講座の `status = 'published'`、`/courses` の検索・コース詳細は `<> 'archived'`。講座の状態は `published` / `archived` だけにする | `catalog_repo.go:54-58` |

## 1. 講座・章・レッスン

### 1-1. 受講者の画面

| 画面 | API | 条件 |
|---|---|---|
| `/courses`（トップ） | `GET /catalog`、`/catalog/config` | 講座: `status = 'published'` かつ、公開中・一覧に出すコースに入っていること。カテゴリは `courses.category`。並びは `top_catalog.order`、次に作成の新しい順 |
| 検索 | `GET /courses?q=` | `status <> 'archived'` かつ、公開中のコースに入っていること（下書きも出る） |
| `/explore` | `GET /learning-paths/search`、`/course-categories` | コース: `status = 'published' AND listed`、アーカイブ以外の講座を 1 件以上含む。カテゴリは `course_category_links` → `tenant_course_categories`（有効で廃止でないもの） |
| 講座詳細 | `GET /courses/:id` | **状態を見ない**（ID が分かれば下書き・アーカイブも開ける） |
| レッスンの一覧 | `GET /courses/:courseId/lessons` | 受講者: `deleted_at IS NULL AND status = 'published'`。並びは「章なし → 章の sort_order → レッスンの sort_order → id」 |
| 章の見出し | `GET /courses/:courseId/chapters` | `deleted_at` を見ない（削除済みの章も出る） |
| コース詳細・申込 | `GET /learning-paths/:id`、`POST …/enroll` ほか | `status = 'published'`。講座が 1 件以上。アーカイブの講座は除く |

### 1-2. 種別ごとの受講画面

| type | 表示 | 完了 | 子の行 |
|---|---|---|---|
| video | 埋め込み（YouTube・Vimeo）か `<video>`（`.m3u8` は hls.js） | 最後まで再生で自動 | `video_lessons`（無ければ「動画はまだありません」） |
| live | 開始予定・参加ボタン | 手動 | `live_lessons`（無ければ「日程は未定」） |
| text | 本文（`lessons.description`） | スクロール 90% で自動 | なし |
| survey | アンケート | 回答で完了 | `survey_lessons` |
| quiz ほか | **本文なし**（バッジは英語のコード） | 「完了にする」だけ | テストは右パネルのタブ（`quizzes.lesson_id`） |

- **修了**: `deleted_at IS NULL AND status = 'published'` の全レッスンが完了（最終試験 `final_quiz_id` があればその合格も）。種別は区別しない。
- 進捗率: 動画は `last_position ÷ video_duration`（`video_duration` が NULL だと途中の進捗が 0%）、それ以外は完了の有無。
- 無料公開は `lessons.is_preview`。

### 1-3. 管理画面（保存が 400 になる条件）

| 操作 | 400 になる条件 |
|---|---|
| 講座の更新 | `status` が `draft` / `published` / `archived` 以外の講座の状態を変える、`difficulty` が 3 種以外、`access_days` が 0〜3650 の外 |
| レッスンの更新（画面は type・status・title・sort_order・drip を毎回送る） | `type` が 4 種以外、`status` が 3 種以外、`pmovie` の URL が許可したホストの `.m3u8` でない |
| 章 | 名前が 1〜255 字の外 |
| テナントのカテゴリ | 名前が 128 字を超える |
| コース | 価格が 0〜99,999,999 の外、期間が範囲外、archived の講座を足す |

### 1-4. 列

| 表.列 | 扱い |
|---|---|
| `courses.status` | 外部キー `content_statuses`。`deleted` は 0-6 |
| `courses.instructor_id` | NOT NULL・外部キー。講師はテナントのすべての講座を編集でき、この列で絞らない |
| `courses.price` / `access_days` | NULL（0-13） |
| `courses.legacy_lesson_id` / `is_used` / `allowed_ip_address` / `settings` | **読まれない** |
| `course_chapters.deleted_at` | **読まれない** |
| `lessons.type` / `status` / `deleted_at` / `is_preview` / `drip_delay_days` / `sort_order` / `chapter_id` | 上のとおり |
| `lessons.unit_id` | UNIQUE（テナント, 旧ユニット）。ライブの行は NULL |
| `lessons.open_at` / `close_at` / `close_after_days` / `drip_delay_basis` | **読まれない**（公開期間は効かない） |
| `video_lessons.video_source` | CHECK `storage` / `pmovie` / `youtube` / `vimeo` |
| `video_lessons.video_url` | 0-8 |
| `video_lessons.complete_type` / `skip_prevention` / `settings` | **読まれない**（早送りの禁止は効かない） |
| `course_tags` / `course_tag_links` | **画面にも API にも出ない** |
| `learning_paths` / `learning_path_courses` | 0-14、1-1 |

## 2. テスト（quiz）

| 区分 | 経路 | 条件 |
|---|---|---|
| 受講者の取得 | `GET /lessons/:lessonId/quiz` | レッスンが公開中・受講登録あり。`quizzes` → `quiz_questions`（sort_order）→ `quiz_options` |
| 受講者の提出 | `POST /quizzes/:id/submit` | サーバーで採点（選んだ集合と正解の集合が一致）。**時間の制限・受験回数・中断は効かない** |
| 管理 | `/quizzes`、`/quizzes/:quizId/questions` | テストはレッスン 1 件に 1 つ |

| 列 | 扱い |
|---|---|
| `quizzes.passing_score` | **割合（0〜100%）**。合否は `得点 × 100 ÷ 満点 >= passing_score` |
| `quizzes.time_limit_sec` | 表示だけ（制限は掛からない）。60 秒未満だと管理画面の保存が 400 |
| `quizzes.max_attempts` / `suspend_enabled` / `display_settings` | **読まれない** |
| `quiz_questions.body` | 必須。プレーンテキスト |
| `quiz_questions.type` | `single_choice` / `multiple_choice` / `free_text` |
| `quiz_questions.points` | 1 以上（0 だと編集で 400、満点 0 は常に不合格） |
| `quiz_questions.bank_id` / `name` / `hint` / `required` / `image_url`、`quiz_options.image_url`、`explanation_image_url`（画面に出ない） | **読まれない** |
| `quiz_options.body` | 1〜1000 字。記述式（free_text）は正解の候補（完全一致）。候補ごとに 1 行 |
| `quiz_question_banks` / `quiz_question_rules` | **読まれない**（0-2） |

- 設問を編集すると選択肢は作り直される（解答の記録の「選んだ選択肢」が消える）。解答の記録がある設問・テストの削除は外部キーで失敗する（未確認）。

## 3. 課題（assignment）

| 区分 | 経路 | 条件 |
|---|---|---|
| 受講者の一覧・詳細 | `GET /courses/:courseId/learner-assignments`、`/assignments/:id/detail` | `status = 'published'`。レッスンが無いか、削除されていないこと |
| 提出 | `POST /assignments/:id/submissions` | 受講登録あり。ファイルの種類が `allowed_types` に入っていること。**締切は効かない** |
| 管理 | `/assignments` | 画面は作成・公開・アーカイブ・削除だけ |

| 列 | 扱い |
|---|---|
| `assignments.allowed_types` | CSV。**空文字だと画面が落ちる** |
| `assignments.status` | `draft` / `published` / `archived` |
| `assignments.due_at` / `max_score` | 表示だけ |
| `assignments.lesson_id` | 画面は使わない（受講者は講座の課題の一覧から辿る） |
| `assignments.due_after_days` / `video_url` / `settings`、**`assignment_materials`（配布資料）** | **読まれない**（配布資料は画面に出ない） |

## 4. アンケート（survey）

| 区分 | 経路 | 条件 |
|---|---|---|
| 受講者 | `GET/POST /lessons/:lessonId/learner-survey` | レッスンが `survey`・公開中・受講登録あり。期間内。二重回答は `survey_submission_log` で止める。回答でレッスンが完了 |
| 管理 | `GET/PUT /lessons/:lessonId/survey` | PUT は全置換。回答があると設問は変えられない |

| 列 | 扱い |
|---|---|
| `survey_lessons.open_at` / `close_at` / `anonymous_allowed` | 読む |
| `survey_lessons.name`、**`survey_pages`**、`survey_questions.page_id` / `image_url` | **読まれない**（ページ分けは無視。表示は `sort_order, id` の順） |
| `survey_questions.kind` | `rating_5` / `rating_10` / `single_choice` / `multiple_choice` / `text_long`。**`file_upload` は入力欄が無く、必須だと送信できない** |
| `survey_questions.prompt` | 画面と API は 500 字まで（再保存で 400） |
| `survey_questions.max_length` | `text_long` だけ。NULL は 2000 |
| `survey_question_options.label` | 255 字。同じ設問で重複すると再保存で 400 |

## 5. ライブ

| 区分 | 経路 | 条件 |
|---|---|---|
| カレンダー `/live` | `GET /live/calendar` | 今から 60 日先まで。`canceled_at IS NULL`、レッスンが公開中（**受講登録は見ない**。全員に見える） |
| 予約 | `POST /live/occurrences/:id/reservations` | レッスンが公開中・**講座に受講登録あり**。受付の期間内・満席でない・中止でない。チケットの要件があれば消費 |
| 自分の予約 | `GET /live/my-reservations` | 中止の回も出る。参加は開始 15 分前から |
| キャンセル | `DELETE …/reservations` | `cancel_closes_at`（NULL なら開始まで） |
| 管理 | `/live/lessons/:lessonId/occurrences`、`/live/occurrences/:id` | 定員 < 予約数だと編集が 400。開始済み・中止の回は日時を変えられない |
| 期限の設定 | `/live/lessons/:lessonId/reservation-policy` | 行があると、未終了の全開催回の期限が再計算される |
| リマインド（worker） | 1 時間ごと | 24 時間以内に始まる `reserved` の予約で `reminded_at IS NULL`。**`remind_enabled` と `deleted_at` は見ない** |

| 列 | 扱い |
|---|---|
| `live_lesson_occurrences.starts_at` / `ends_at` | DATETIME(3)、UTC。CHECK `ends_at > starts_at` |
| `.capacity` | NULL は無制限。CHECK 1 以上 |
| `.reserve_opens_at` / `reserve_closes_at` / `cancel_closes_at` | NULL は制限なし |
| `.meeting_url` | 空だと参加ボタンが出ない |
| `.recording_url` / `recording_published` | 公開のときだけ受講者に出る |
| `.canceled_at` | カレンダー・リマインドから外す |
| `.deleted_at` / `remind_enabled` / `settings` | **読まれない**（0-4） |
| `live_lessons.scheduled_at` / `live_room_id` | 0-5 |
| `live_lessons.live_lesson_id` / `settings` | **読まれない** |
| `live_lesson_recurrence_*` / `exclusion_date_history` / `limit_item_history` / `group_targets` / `categories` / `category_links` | **読まれない**（0-3） |
| 予約の状態 `host_canceled` | lookup にはあるが、画面・再予約の処理が知らない（未確認） |

## 6. 新システムの E2E（参考）

03（受講登録とレッスン）・05（講座の作成）・07（学習の流れ）・13（コース）・27（カテゴリ）・30（講座の公開範囲）・34（テスト）・37（LiveKit）・39（講座とレッスンの管理）・59（無料公開のレッスン）・64（課題の提出）・66（アンケート）・67（ライブの予約と定員）・68（チケット）・75〜77（コースの販売・申込・受講の規則）・81（探す画面）・83（カテゴリの並べ替え）。どれも demo の seed が前提。

## 7. まだ調べていないこと

- 今の移行ツールがどう移しているか（種別・状態・動画の URL・設問の展開・開催回の削除の扱いなど）と旧のデータの実態は、手順 2・3 で突き合わせる。
- 予約の状態 `host_canceled` の画面での扱い。
