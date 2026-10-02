# コンテンツ — 機能の差分

コンテンツのデータ（講座・ユニット・動画・テスト・課題・アンケート・ライブの定義）を**使う機能**を1つずつ挙げ、新旧でどう違うかを書く。
書き方の約束（判定・差分の種類・深刻度・対応の書き方）は [ひな形](../00-template/features.md) を参照。

- **調査時点:** 2026-09-29
  - 旧: `learningware-kiracari`
  - 新: `school-launcher` の `hanataba_dev`（`27741e2`）
- **根拠の場所の書き方:**
  - 旧は `learningware-kiracari/` からの相対パス。
  - 新は `btoc-backend/` / `btoc-frontend/` からのパス。
- データの受け皿（A1〜A27）は [突き合わせ](review.md#新環境に追加するテーブルカラム) を参照。**この文書は「受け皿に入れたデータを新の機能が読んでいるか」を見る**
- 受講の実績（受験結果・提出・回答・予約）は 03 受講で扱う。ここでは**定義が受講者にどう効くか**までを見る

> **要点。** コンテンツで足した受け皿（A1〜A27）は、**新の機能から1つも読まれていない。**
> 加えて、**旧で削除したものが受講者に見える**不具合が2つある。
>
> - 削除したユニットが講座の中に並ぶ（F03）
> - 削除した開催回がカレンダーに出て予約でき、リマインドも送られる（F11）
>
> 移した動画は**そのままでは再生できない**（F04）。テスト・課題・講座資料のユニットは**開いても本文が空**になる（F03）。
> 前提条件が効かないので、**全ユニットが最初から受講できる**（F05）。

> **移行ツール側の誤りも1つ見つかった（F11。2026-09-30 に直した）。** 旧の開催回の `mail_send_chk` は「リマインドを送る」ではなく**「送信済み」**の印
> （`LiveLessonModel.class.php` はリマインドの対象を `mail_send_chk = 0` で選び、送ったら更新する）。
> 移行ツールはこれを `live_lesson_occurrences.remind_enabled` に写しており、**意味が逆**になっていた。
> いまは送信済みの回の予約に `live_reservations.reminded_at` を入れ、`remind_enabled` は全回 TRUE にしている。

---

## 機能の一覧

| ID | 機能 | 利用者 | データ種 | 判定 | 差分（高 / 中 / 低） | 未決 |
|---|---|---|---|:--:|:--:|--:|
| F01 | 講座の一覧・詳細 | 受講者 | O01 / O02 / O03 | △ | 0 / 5 / 1 | 0 |
| F02 | 講座の管理 | 管理者・講師 | O01 | △ | 0 / 4 / 0 | 3 |
| F03 | ユニットの構成と受講画面 | 受講者 | O04 / O05 / O20 | △ | 2 / 1 / 2 | 0 |
| F04 | 動画の視聴 | 受講者 | O06 / O07 | △ | 1 / 3 / 0 | 2 |
| F05 | 受講の進行制御（前提条件・免除） | 受講者 | O22 / O23 | X | 1 / 1 / 0 | 1 |
| F06 | テストの受験 | 受講者 | O08 / O11 / O12 / O13 | △ | 1 / 4 / 1 | 2 |
| F07 | 問題の管理（問題バンク） | 管理者 | O08 | △ | 0 / 1 / 0 | 1 |
| F08 | 課題 | 受講者・講師 | O18 / O19 | △ | 1 / 2 / 1 | 1 |
| F09 | アンケート | 受講者・管理者 | O14 / O15 / O16 / O17 | △ | 2 / 1 / 1 | 2 |
| F10 | ライブの一覧・予約 | 受講者 | L01 | △ | 0 / 3 / 3 | 1 |
| F11 | ライブの開催回の管理 | 管理者・講師 | L02 / L04 | △ | 1 / 1 / 0 | 1 |
| F12 | リモート PC | 受講者・管理者 | O28 | 新のみ | 0 / 1 / 0 | 1 |

---

## 各機能

### F01 講座の一覧・詳細

利用者: 受講者 ／ データ種: O01 講座、O02 講座カテゴリ、O03 講座サムネ ／ 判定: **△ 差分あり**

- 旧: `application/modules/default/controllers/LessonController.php` の `listAction()` / `detailAction()`、絞り込みは `LessonModel::_buildSql()`
- 新: `GET /api/v1/courses` → `internal/repository/course_repo.go` の `ListPublished` / `internal/service/course_service.go` の `GetByID` ／ 画面 `/courses`、`/courses/[courseId]`

#### 参照データ

| データ | 旧（テーブル.列） | 新（テーブル.列） | 旧で使う | 新で使う | 差分 |
|---|---|---|:--:|:--:|---|
| 講座 | `lesson` | `courses` | ◯ | ◯ | — |
| 削除 | `lesson.del_chk` | `courses.status = 'deleted'` | ◯ | △ | 一覧には出ないが、詳細は URL で開ける |
| カテゴリ | `lesson_cate` | `course_categories` / `courses.category` | ◯ | — | 新の絞り込みは固定の9カテゴリ。表を読まない |
| カテゴリ画像 | `lesson_cate.lesson_cate_img_file_name` | `course_categories.image_url` | ◯ | — | 旧はトップページだけで使う |
| タグ | `lesson_tag` / `lesson_lesson_tag` | `course_tags` / `course_tag_links` | ◯ | — | 新は読まない |
| サムネイル | `lesson.lesson_img_file_name` | `courses.thumbnail_url` | ◯ | ◯ | 新は保存領域のキーとして読む |
| 進捗の表示方式 | `lesson.progress_display_chk` | `courses.settings` | ◯ | — | 新は読まない |

#### 差分

| 種類 | 深刻度 | 内容 | 対応 |
|---|:--:|---|---|
| 参照データ | 中 | カテゴリの絞り込みが固定の9カテゴリで、移したカテゴリが出ない | 新で `course_categories` を読んで絞り込みを作る |
| 機能 | 中 | タグで絞り込めない | 新でタグを実装する（A2） |
| 振る舞い | 中 | 旧で削除した講座も、URL を知っていれば詳細を開ける（受講登録は公開中しかできない） | 新で講座の詳細も状態を見る |
| 振る舞い | 中 | 旧の受講者の講座一覧は**受講登録した講座だけ**を商品ごとにまとめて出す。新は公開中の講座を全部並べ、未購入の講座には購入の導線を出す | 対応不要。新の「講座を1本ずつ売る」作りに合わせた違い。値段が未登録の講座の見え方は [C3](../open-questions.md#c-新環境の制約が意図的かの確認) で決まる |
| 参照データ | 中 | サムネイルは新の保存領域のキーとして読むので、旧のファイル名のままでは出ない | 画像ファイルを新の保存領域へ移す（移行の L9） |
| 参照データ | 低 | 進捗の表示方式（％ / 所要時間）の切り替えを読まない | 新で `courses.settings` を読む |

### F02 講座の管理

利用者: 管理者・講師 ／ データ種: O01 講座 ／ 判定: **△ 差分あり**

- 旧: `application/modules/admin-lesson/controllers/LessonController.php`（`editAction()` / `deleteAction()`）、`LessonModel::createLesson()` / `updatelesson()`
- 新: `POST /courses`、`PATCH /courses/:id`（`routes_course.go`）→ `course_repo.go` の `Create` / `Update` ／ 画面 `admin/courses`

#### 参照データ

| データ | 旧（テーブル.列） | 新（テーブル.列） | 旧で使う | 新で使う | 差分 |
|---|---|---|:--:|:--:|---|
| 接続元 IP の制限 | `lesson.allowed_ip_address` | `courses.allowed_ip_address` | ◯ | — | 旧もユニットへのリンクを隠すだけで、URL を直接開けば見られる |
| 利用中の講座 | `lesson_is_used` | `courses.is_used` | △ | — | 旧も管理画面の選択肢を絞るだけ。`lesson_is_used` に行がある講座を「利用中」として移す |
| 講座の設定 | `lesson` の表示方式・問い合わせ先・修了証・既定の受講期間など | `courses.settings`（一部） | ◯ | — | 新は読まない。**`settings` に入るのは機能フラグ7つ（デバイス別公開・進捗表示・弱点問題集・ランキング・SNS 共有・問い合わせの有無）だけ**で、表示方式（`disp_type_id` / `frame_*`）・問い合わせ先（`inquiry_address`）などは現状は移していない（実装が無い。2026-10-02 の確認） |
| 講師 | —（講座の講師は無い。`instructor_set_lesson` は講座管理者の担当範囲） | `courses.instructor_id`（必須） | — | ◯ | 移行では全講座に代理講師を入れている |
| 削除 | `lesson.del_chk` | `courses.status = 'deleted'` | ◯ | △ | 管理画面の一覧に出るが、状態を変えられない |

#### 差分

| 種類 | 深刻度 | 内容 | 対応 |
|---|:--:|---|---|
| 機能 | 中 | 接続元 IP で講座を絞る設定が新に無い。旧も部分一致の判定で、URL を直接開けば通れる作りだった | 未決: 運営に使っているかを確認する（[E18](../open-questions.md#e-切り替え後の機能で決めておきたいこと)） |
| 参照データ | 中 | 講座の表示方式（ポップアップ / フレーム）、問い合わせ先、修了証、既定の受講期間などの設定を新は読まない | 未決: 新で効かせる設定を運営と決める（[E19](../open-questions.md#e-切り替え後の機能で決めておきたいこと)） |
| 参照データ | 中 | 新は講座に講師1名が必須だが、旧は講座に講師を持たない。移行では全講座に代理講師を入れている | 未決: [C2](../open-questions.md#c-新環境の制約が意図的かの確認) / [B1](../open-questions.md#b-データ対応表の提供をお願いしたいもの) の回答で付け替える |
| 振る舞い | 中 | 旧で削除した講座は、新の管理画面の一覧に出るが、状態を変えられない（新に `deleted` からの遷移が無い） | 新で `deleted` の講座を管理画面から外す（A3） |

> **C2 の前提と食い違う。** C2 は「旧システムは1つの講座に講師を0〜3名紐づけられた」としているが、
> 旧のコードにも移行ツールにも、講座と講師を結ぶ表は見当たらない（`instructors.py` の注記も「lw2 には講座単位の講師が無い」）。
> 旧で講師を持つのはライブ（`live_lesson.lesson_instructor_id`、1名）だけ。**C2 の文面を見直す必要がある。**

### F03 ユニットの構成と受講画面

利用者: 受講者 ／ データ種: O04 講義ユニット、O05 見出しブロック、O20 講座資料ユニット ／ 判定: **△ 差分あり**

- 旧: `LessonController.php` の `detailAction()`（見出しのまとまりと公開期間の判定）、ユニットの種別は `admin-lesson/controllers/UnitController.php`
- 新: `GET /courses/:courseId/lessons` → `internal/service/lesson_service.go` の `ListForLearner` / `internal/repository/lesson_repo.go` の `ListByCourse` ／ 画面 `.../lessons/[lessonId]/_components/lesson-content-renderer.tsx`

#### 参照データ

| データ | 旧（テーブル.列） | 新（テーブル.列） | 旧で使う | 新で使う | 差分 |
|---|---|---|:--:|:--:|---|
| 削除 | `unit.del_chk` | `lessons.status = 'deleted'` | ◯ | — | **受講者向けの一覧は状態を見ない** |
| 種別 | `unit.unit_type_id` | `lessons.type` | ◯ | △ | 新の受講画面が描くのは動画・ライブ・テキスト・アンケートだけ |
| 見出し | `unit`（type=0） | `course_chapters`、`lessons.chapter_id` | ◯ | ◯ | 章として移し、後ろのユニットを章に所属させる（削除済みの見出しも `deleted_at` 付きで移す。新はまだ読まない） |
| 公開期間 | `unit.open_datetime` / `close_datetime` / `open_day` / `close_day_from_lesson_start_date` | `lessons.open_at` / `close_at` / `close_after_days` / `drip_delay_basis` | ◯ | — | 新は受講開始からの日数（`drip_delay_days`）で鍵を表示するだけ |
| 完了メッセージ | `unit.complete_message` | `lessons.complete_message` | ◯ | — | 新は読まない |
| 検索キーワード | `unit.search_keyword` | `lessons.search_keyword` | ◯ | — | 新は読まない |
| 所要時間 | `unit.unit_duration` | `lessons.duration_min` | ◯ | — | 新は読まない |

#### 差分

| 種類 | 深刻度 | 内容 | 対応 |
|---|:--:|---|---|
| 振る舞い | 高 | **旧で削除したユニットが、受講者の講座の中に並ぶ。** 移行は `status = 'deleted'` で入れているが、新の受講者向けの一覧（`ListByCourse`）は状態で絞らない（下書き・アーカイブも出る） | 新で受講者向けの一覧を公開中だけに絞る |
| 機能 | 高 | テスト・課題・講座資料のユニットを開くと本文が空になる。新の受講画面はこれらの種別を描かない（テストは別のタブ、課題は別の画面から開く） | 新で種別ごとの受講画面を出す（A20） |
| 振る舞い | 中 | ユニットの公開期間（開始・終了の日時、受講開始から N 日後に開く / 閉じる）が効かない。新は受講開始からの日数で鍵を表示するだけで、開くのは止めない | 新で公開期間を実装する（A4） |
| 画面 | 低 | 新は章（`course_chapters`）で見出しを持つ。旧の「折りたたみ」（`open_close_chk`）は章に列が無い | 対応不要。値はユニットの設定（`lessons.settings`）に残っている |
| 参照データ | 低 | 完了メッセージ・講座内の検索キーワード・所要時間を新は読まない | 新で実装する（A4） |

> **ディスカッション・スキル診断の種別は `hanataba_dev` にまだ無い。** PR #135（`20260928072918`）で足す。

### F04 動画の視聴

利用者: 受講者 ／ データ種: O06 講義動画、O07 動画字幕 ／ 判定: **△ 差分あり**

- 旧: `LessonController.php` の `frameAction()` / `framePmovieAction()`、完了の判定は同 1220行付近、早送り禁止は `UnitModel::isPriventSkip()`、字幕は `api/controllers/SubtitleController.php`
- 新: `internal/handler/upload_handler.go` の `serveVideoURL`、`btoc-frontend/src/hooks/use-video-progress.ts`、`components/video/video-player.tsx`

#### 参照データ

| データ | 旧（テーブル.列） | 新（テーブル.列） | 旧で使う | 新で使う | 差分 |
|---|---|---|:--:|:--:|---|
| 配信先 | `lecture.pmovie_token`、`lecture_path.pc_path` | `video_lessons.video_url` | ◯ | △ | **新は保存領域のキーとして読み、署名つき URL を作る** |
| スマートフォン用の配信先 | `lecture_path.smartphone_path` | — | — | — | 旧も受講者側では読まない |
| 完了の条件 | `lecture.lecture_complete_type` / `pmovie_complete_type` | `video_lessons.complete_type` | ◯ | — | 新は90%まで再生したら完了 |
| 早送り禁止 | `lecture.skip_prevention_setting` | `video_lessons.skip_prevention` | ◯ | — | 新は読まない |
| 字幕 | 字幕ファイル（API で配信） | — | ◯ | — | 受け皿も機能も無い |

#### 差分

| 種類 | 深刻度 | 内容 | 対応 |
|---|:--:|---|---|
| 参照データ | 高 | **移した動画が再生できない。** 移行は p-movie のトークンか旧の配信先（外部 URL・旧サーバーの相対パス。PDF の教材を含む）を入れているが、新はそれを新の保存領域のキーとして読む | 未決: p-movie を新の画面で再生できるようにするか、動画を新の保存領域へ移すかを決める（[E21](../open-questions.md#e-切り替え後の機能で決めておきたいこと)） |
| 振る舞い | 中 | 完了の条件が違う。旧は「開いたら」「最後のページまで」「プレーヤーが完了を知らせたら」から選べた。新は90%まで再生したら完了 | 新で `complete_type` を読む（A5） |
| 機能 | 中 | 早送り禁止が無い。新は90%の位置まで飛ばせば完了になる | 新で早送り禁止を実装する（A5） |
| 機能 | 中 | 字幕が無い | 未決: 運営に使っているかを確認する（[E22](../open-questions.md#e-切り替え後の機能で決めておきたいこと)） |

### F05 受講の進行制御（前提条件・免除）

利用者: 受講者 ／ データ種: O22 ユニット前提条件、O23 ユニット免除 ／ 判定: **X 新に無い**

- 旧: 前提条件は `ApiLessonModel::getUserPreconUnit()`（一覧で灰色にし、前後の移動で止める）。免除は `ApiLessonModel::checkUnitExemption()`（あるユニットを終える・テストで点を取ると、別のユニットを自動で完了にする）
- 新: 無い（`lesson_preconditions` は受け皿だけ）

#### 参照データ

| データ | 旧（テーブル.列） | 新（テーブル.列） | 旧で使う | 新で使う | 差分 |
|---|---|---|:--:|:--:|---|
| 前提条件 | `unit_precondition` | `lesson_preconditions` | ◯ | — | 新は読まない |
| 免除 | `unit_exemption` | — | ◯ | — | 受け皿を取り下げた（前提条件の拡張として設計し直す） |

#### 差分

| 種類 | 深刻度 | 内容 | 対応 |
|---|:--:|---|---|
| 機能 | 高 | **前提条件が効かず、全ユニットが最初から受講できる。** 旧は「このユニットを終えないと次に進めない」を、開始・提出・完了の段階つきで設定できた | 新で前提条件を実装する（A15） |
| 機能 | 中 | 免除（条件を満たすと別のユニットが自動で完了する）が新に無い | 未決: 運営に使っているかを確認する（ステージングは1件）（[E23](../open-questions.md#e-切り替え後の機能で決めておきたいこと)） |

### F06 テストの受験

利用者: 受講者 ／ データ種: O08 テスト定義、O11 自由記述、O12 中断・再開、O13 受験回数制限 ／ 判定: **△ 差分あり**

- 旧: `LessonController.php` の `testAction()` / `testConfirmAction()`、出題は `UserLearningLessonModel::setUserLearningTest()`、採点は `setUserLearningMark()`
- 新: `GET /lessons/:lessonId/quiz`、`POST /quizzes/:id/submit` → `internal/quiz/service/quiz_grading_service.go` の `SubmitQuiz` ／ 画面 `components/lesson/quiz-*.tsx`

#### 参照データ

| データ | 旧（テーブル.列） | 新（テーブル.列） | 旧で使う | 新で使う | 差分 |
|---|---|---|:--:|:--:|---|
| 出題の条件 | `test_sub`（固定 / 登録した問題からランダム / カテゴリ・難易度からランダム） | `quiz_question_rules` | ◯ | — | 新は登録した問題を順番どおり全部出す |
| 受験回数の上限 | `test.exam_max_number` | `quizzes.max_attempts` | ◯ | — | 新は読まない |
| 中断・再開 | `test.suspended_chk` | `quizzes.suspend_enabled` | ◯ | — | 新は読まない |
| 結果の見せ方 | `test.test_result_disp_chk` / `test_score_disp_chk` / `error_disp_chk` / `answer_disp_chk` / `comment_disp_chk`、1ページの問題数 | `quizzes.display_settings` | ◯ | — | 新は読まない |
| 問題・選択肢の画像 | `question.question_img_file_name` / `selection*_img_file_name` | `quiz_questions.image_url` / `quiz_options.image_url` | ◯ | — | 新は解説の画像だけを出す |
| ヒント・問題名 | `question.hint` / `question_name` | `quiz_questions.hint` / `name` | ◯ | — | 新は読まない |
| 合格点 | `test.pass_score` | `quizzes.passing_score` | ◯ | ◯ | — |
| 自由記述 | `question`（type=3） | `quiz_questions`（`free_text`） | ◯ | ◯ | どちらも正解の文字列との一致で採点する |

#### 差分

| 種類 | 深刻度 | 内容 | 対応 |
|---|:--:|---|---|
| 機能 | 高 | ランダム出題が無い。カテゴリから選ぶだけのテストは設問が0問になり、登録した問題から選ぶテストは全問が出る | 未決: [C6](../open-questions.md#c-新環境の制約が意図的かの確認) の回答で決める |
| 機能 | 中 | 受験回数の上限が無い | 新で受験回数の上限を実装する（A7） |
| 機能 | 中 | 中断・再開が無い | 新で中断・再開を実装する（A7） |
| 参照データ | 中 | 結果の見せ方（点数・正誤・正解・解説を見せるか）の設定を新は読まない | 新で `display_settings` を読む（A7） |
| 参照データ | 中 | 問題・選択肢の画像とヒントが出ない | 新で画像とヒントを出す（A7）。画像ファイルは新の保存領域へ移す |
| 機能 | 低 | 旧にあった「選択肢を受講者ごとに並べ替える」「間違えた問題だけを出し直す」が新に無い | 未決: 運営に使っているかを確認する（[E24](../open-questions.md#e-切り替え後の機能で決めておきたいこと)） |

### F07 問題の管理（問題バンク）

利用者: 管理者 ／ データ種: O08 テスト定義 ／ 判定: **△ 差分あり**

- 旧: `application/modules/admin-lesson/controllers/QuestionController.php`（一覧・編集・CSV 一括）、`QuestionCategoryController.php`
- 新: 問題のカテゴリ（ラベル）の管理は `/quizzes/question-categories`（`internal/quiz/repository/quiz_question_category_repo.go`）。問題バンクの画面は無い

#### 参照データ

| データ | 旧（テーブル.列） | 新（テーブル.列） | 旧で使う | 新で使う | 差分 |
|---|---|---|:--:|:--:|---|
| 問題のカテゴリ | `question_cate` | `quiz_question_labels` | ◯ | ◯ | 管理画面の「カテゴリ」として見え、編集できる |
| テストに属さない問題 | `question` | `quiz_question_banks` / `quiz_questions.bank_id` | ◯ | — | 新は読まない |

#### 差分

| 種類 | 深刻度 | 内容 | 対応 |
|---|:--:|---|---|
| 機能 | 中 | 問題バンク（テストに属さない問題の一覧・編集・CSV での一括登録）の画面が新に無い | 未決: [C6](../open-questions.md#c-新環境の制約が意図的かの確認) の回答に合わせて作るかを決める（ランダム出題を作るなら要る） |

### F08 課題

利用者: 受講者・講師 ／ データ種: O18 課題、O19 課題の提出ファイル ／ 判定: **△ 差分あり**

- 旧: `application/modules/default/controllers/ReportController.php`、解説は `LessonController.php` の `frameCommentaryAction()`、定義は `UnitModel::findReportByUnitId()`
- 新: `routes_assignment.go` → `internal/assignment/repository/assignment_repo.go` ／ 画面 `courses/[courseId]/assignments/*`、`admin/assignments/grading/*`

#### 参照データ

| データ | 旧（テーブル.列） | 新（テーブル.列） | 旧で使う | 新で使う | 差分 |
|---|---|---|:--:|:--:|---|
| 配布資料 | `report.report_disp_file_name1〜5` | `assignment_materials` | ◯ | — | 新は読まない |
| 提出期限 | `report.limit_Date` / `limit_Date_Num`（受講開始から N 日） | `assignments.due_at` / `due_after_days` | ◯ | △ | 新は固定の日時だけを持ち、期限で止めない（旧も表示だけ） |
| 提出後の解説 | `report_path`（解説ページ）/ `report_commentary_chk` / `report_pmovie_token`（解説動画） | —（`report_path` は現状は移していない）/ `assignments.settings` / `video_url` | ◯ | — | 新は読まない。**解説ページの配信先（`report_path`）は受け皿が無く、現状は移していない**（実装が無い。2026-10-02 の確認。ステージング144行、`pc_path` あり23行） |
| 設問 | `enquete`（課題用のアンケート） | — | ◯ | — | [C4](../open-questions.md#c-新環境の制約が意図的かの確認) |

#### 差分

| 種類 | 深刻度 | 内容 | 対応 |
|---|:--:|---|---|
| 機能 | 高 | 課題の設問形式（設問ごとの選択・記述・ファイル）が新に無い | 未決: [C4](../open-questions.md#c-新環境の制約が意図的かの確認) の回答で決める |
| 機能 | 中 | 配布資料をダウンロードできない | 新で配布資料を実装する（A13）。ファイルは新の保存領域へ移す |
| 機能 | 中 | 提出後に見せる解説（ページ・動画）が新に無い | 新で解説を実装する（A13） |
| 振る舞い | 低 | 期限を「受講開始から N 日」で持てない | 新で `due_after_days` を読む（A13） |

> **`report_path` は配布ファイルではない。** 旧のコードでは**提出後の解説ページ**（`commentary_path`）。配布ファイルは `report` 自身の `report_disp_file_name1〜5` で、`assignment_materials` に移している。[内訳](breakdown.md) / [突き合わせ](review.md) も 2026-10-02 にこの理解に直した。

### F09 アンケート

利用者: 受講者（回答）・管理者（作成）／ データ種: O14 ユニットアンケート、O15 ファイル添付設問、O16 お知らせ添付、O17 レポート添付 ／ 判定: **△ 差分あり**

- 旧: 管理は `application/modules/admin/controllers/EnqueteController.php`、回答は `application/modules/default/controllers/EnqueteController.php`
- 新: `routes_survey.go` → `internal/survey/repository/survey_repo.go` ／ 画面 `.../survey/_components/survey-editor.tsx`、`components/lesson/survey-lesson-content.tsx`

#### 参照データ

| データ | 旧（テーブル.列） | 新（テーブル.列） | 旧で使う | 新で使う | 差分 |
|---|---|---|:--:|:--:|---|
| ページ分け | `enquete_page` | `survey_pages` / `survey_questions.page_id` | ◯ | — | 新は読まない。**管理画面で保存し直すと消える** |
| 画像 | `enquete_question.question_img_file_name` / `selection*_img_file_name` | `survey_questions.image_url` / `survey_question_options.image_url` | ◯ | — | 同上 |
| アンケート名 | `enquete` | `survey_lessons.name` | ◯ | — | 新は読まない |
| ファイル添付の設問 | `enquete_question`（type=4。課題用だけ） | `survey_question_kinds`（`file_upload`） | ◯ | △ | 新は自由記述として出す |

#### 差分

| 種類 | 深刻度 | 内容 | 対応 |
|---|:--:|---|---|
| 振る舞い | 高 | **管理画面でアンケートを保存し直すと、移したページ分けと画像が消える**（新は設問を全部消して入れ直す） | 新で `page_id` / `image_url` を読み書きする（A12） |
| 機能 | 高 | お知らせに添付したアンケートが新に無い | 未決: [C5](../open-questions.md#c-新環境の制約が意図的かの確認) の回答で決める |
| 機能 | 中 | ページ分けと画像が回答画面に出ない | 新でページ分けと画像を実装する（A12） |
| 機能 | 低 | ファイル添付の設問が自由記述として出る（旧も課題用のアンケートだけの設問） | 未決: [C4](../open-questions.md#c-新環境の制約が意図的かの確認) の回答に合わせる |

### F10 ライブの一覧・予約

利用者: 受講者 ／ データ種: L01 ライブ定義 ／ 判定: **△ 差分あり**

- 旧: `application/modules/default/controllers/LiveLessonController.php`（カレンダー・詳細・予約）、表示の絞り込みは `LiveLessonModel` の 2240〜2375行
- 新: `GET /live/calendar` → `internal/live/service/reservation_service.go` の `ListCalendar` ／ 画面 `/live`、`/my-live-reservations`

#### 参照データ

| データ | 旧（テーブル.列） | 新（テーブル.列） | 旧で使う | 新で使う | 差分 |
|---|---|---|:--:|:--:|---|
| カテゴリ | `live_lesson_cate` / `live_lesson_lesson_cate` | `live_lesson_categories` / `_links` | ◯ | — | 新は読まない |
| 公開するグループ | `live_lesson_group` | `live_lesson_group_targets` | ◯ | — | ステージングは0件 |
| 予約できる人 | `live_lesson_limit_item`（商品を持っている人） | 講座の受講登録 | ◯ | ◯ | 移行の方針で講座の受講に置き換えた |
| 講師・説明・画像・配布ファイル・予約数の上限・公開ページ | `live_lesson` の各列 | `live_lessons.settings` | ◯ | — | 新は読まない |

#### 差分

| 種類 | 深刻度 | 内容 | 対応 |
|---|:--:|---|---|
| 機能 | 中 | カテゴリで絞り込めない | 新でライブのカテゴリを実装する（A23） |
| 機能 | 中 | 1人が同時に持てる予約数の上限が無い | 新で `live_lessons.settings` の上限を読む（A22） |
| 参照データ | 中 | ライブごとの講師、詳細の説明（HTML）、画像、配布ファイルが出ない | 新で `live_lessons.settings` を読む（A22） |
| 機能 | 低 | ログインしなくても見られるライブの公開ページが新に無い | 未決: 運営に使っているかを確認する（[E25](../open-questions.md#e-切り替え後の機能で決めておきたいこと)） |
| 機能 | 低 | グループで公開先を絞れない | 対応不要。ステージングは0件。本番ダンプで確かめる（A24） |
| 振る舞い | 低 | 予約できる人が「商品を持っている人」から「講座に受講登録した人」に変わる | 対応不要。移行の方針で置き換えた |

### F11 ライブの開催回の管理

利用者: 管理者・講師 ／ データ種: L02 開催日、L04 リマインド ／ 判定: **△ 差分あり**

- 旧: 開催回の生成は `admin/LiveLessonController::completeAction()` と日次の `batch/LiveLessonBatch.class.php`（`LiveLessonModel::findLiveLessonDateForSetting()`）。リマインドは同じバッチ
- 新: `routes_live.go` → `internal/live/service/occurrence_service.go`、カレンダーは `internal/live/repository/occurrence_repo.go` の `ListByPeriod`、リマインドは `reminder_batch_service.go`（毎時）

#### 参照データ

| データ | 旧（テーブル.列） | 新（テーブル.列） | 旧で使う | 新で使う | 差分 |
|---|---|---|:--:|:--:|---|
| 削除 | `live_lesson_date.del_chk` | `live_lesson_occurrences.deleted_at` | ◯ | — | **カレンダーもリマインドも読まない** |
| リマインドの送信済み | `live_lesson_date.mail_send_chk` | `live_reservations.reminded_at`（その回の予約ごと） | ◯ | ◯ | —（2026-09-30 に移し先を直した） |
| 繰り返しの設定 | `live_lesson_date_setting` / `_detail` / `live_lesson_exclusion_date` | `live_lesson_recurrence_rules` / `_details` / `_exclusions` | ◯ | — | 新に開催回を作る仕組みが無い |

#### 差分

| 種類 | 深刻度 | 内容 | 対応 |
|---|:--:|---|---|
| 振る舞い | 高 | **旧で削除した開催回がカレンダーに出て予約でき、リマインドも送られる。** 新は `canceled_at` しか見ない | 新でカレンダーとリマインドの抽出に `deleted_at IS NULL` を足す（A25） |
| 参照データ | — | **（対応済み）`mail_send_chk` の意味を取り違えて移していた。** 旧は「送信済み」の印だが、移行ツールは `remind_enabled`（送るか）に写していた | 2026-09-30 に移行ツールを直した。`mail_send_chk = 1` の回の予約に `reminded_at`（旧の開催回の更新日時）を入れる。ステージングで予約24件中8件 |
| 機能 | 中 | 繰り返しの設定（毎日・毎週・毎月・毎年、除外日）から開催回を作る仕組みが新に無い。生成済みの回は移っているが、切り替え後の回は作られない | 未決: 新で繰り返しを実装するか、切り替え前に先の分まで作っておくかを決める（A26）（[E26](../open-questions.md#e-切り替え後の機能で決めておきたいこと)） |

### F12 リモート PC

利用者: 受講者・管理者 ／ データ種: O28 リモート PC ／ 判定: **新のみ**

- 旧: 予約の機能は無い。`LessonController.php` の `remoteAction()` が一回限りのトークン（`remote_api_token`、10分）を作り、外部のシステムへ渡すだけ
- 新: `internal/remotepc/*`（30分枠の予約、同時5件まで、1時間前までキャンセル）／ 画面 `/remote-pc`、`admin/remote-pc`

#### 差分

| 種類 | 深刻度 | 内容 | 対応 |
|---|:--:|---|---|
| 機能 | 中 | 旧は外部のリモート PC のシステムへ引き渡すだけで、予約は外部で行っていた。新は新システムの中で予約する | 未決: 外部のシステムを使い続けるか、新の予約に切り替えるかを運営と決める（[E27](../open-questions.md#e-切り替え後の機能で決めておきたいこと)） |

---

## 移したが新で読まれないデータ

各機能の「参照データ」で**新で使う が `—`** の行を集めたもの。旧でも受講者に効いていなかったもの（`lesson_is_used`、`smartphone_path`）は除いた。

| 新テーブル.列 | 旧 | 旧で使っていた機能 | 対応 |
|---|---|---|---|
| `course_categories` | `lesson_cate` | F01 講座の一覧 | 新で絞り込みに使う。**`image_url` は L9 の移送前で、いまは NULL** |
| `course_tags` / `course_tag_links` | `lesson_tag` / `lesson_lesson_tag` | F01 講座の一覧 | 新で実装する（A2） |
| `courses.allowed_ip_address` | `lesson.allowed_ip_address` | F02 講座の管理 | 未決（F02） |
| `courses.settings` | `lesson` の設定の列 | F01 / F02 | 未決（F02） |
| `lessons.status = 'deleted'` | `unit.del_chk` | F03 受講画面 | 新で受講者向けの一覧を絞る |
| `lessons.open_at` / `close_at` / `close_after_days` / `drip_delay_basis` | `unit` の公開期間 | F03 受講画面 | 新で実装する（A4） |
| `lessons.complete_message` / `search_keyword` / `duration_min` | `unit` の各列 | F03 受講画面 | 新で実装する（A4） |
| `video_lessons.complete_type` / `skip_prevention` | `lecture` の各列 | F04 動画の視聴 | 新で実装する（A5） |
| `lesson_preconditions` | `unit_precondition` | F05 進行制御 | 新で実装する（A15） |
| `quiz_question_rules` | `test_sub` | F06 テストの受験 | 未決（C6） |
| `quizzes.max_attempts` / `suspend_enabled` / `display_settings` | `test` の各列 | F06 テストの受験 | 新で実装する（A7） |
| `quiz_questions.image_url` / `hint` / `name`、`quiz_options.image_url` | `question` の各列 | F06 テストの受験 | 新で実装する（A7） |
| `quiz_question_banks` / `quiz_questions.bank_id` | `question` | F07 問題の管理 | 未決（C6） |
| `assignment_materials` | `report.report_disp_file_name1〜5` | F08 課題 | 新で実装する（A13） |
| `assignments.due_after_days` / `video_url` / `settings` | `report` の各列 | F08 課題 | 新で実装する（A13） |
| `survey_pages` / `survey_questions.page_id` / `image_url`、`survey_question_options.image_url`、`survey_lessons.name` | `enquete_page`、`enquete_question` | F09 アンケート | 新で実装する（A12） |
| `live_lesson_categories` / `_links` | `live_lesson_cate` / `live_lesson_lesson_cate` | F10 ライブの一覧 | 新で実装する（A23） |
| `live_lesson_group_targets` | `live_lesson_group` | F10 ライブの一覧 | 対応不要（0件） |
| `live_lessons.settings` | `live_lesson` の各列 | F10 ライブの一覧 | 新で実装する（A22） |
| `live_lesson_occurrences.deleted_at` | `live_lesson_date.del_chk` | F11 開催回 | 新で抽出条件に足す（A25） |
| `live_lesson_occurrences.remind_enabled` | —（旧に開催回ごとの止め方は無い） | F11 リマインド | 対応不要（全回 TRUE で移す。`mail_send_chk` は `reminded_at` へ。2026-09-30 に直した） |
| `live_lesson_recurrence_rules` / `_details` / `_exclusions` | `live_lesson_date_setting` など | F11 開催回 | 未決（F11） |

> **`live_lessons.settings` と `video_lessons` の追加列は、管理画面で保存すると消えることがある。** 新はライブの予定日時と部屋、動画の URL が無い状態でユニットを保存すると、子の行（`live_lessons` / `video_lessons`）を消す（`lesson_repo.go`）。移した設定もそのとき一緒に消える。

---

## 集計

| 判定 | 件数 |
|---|--:|
| ◯ 同等 | 0 |
| △ 差分あり | 10 |
| X 新に無い | 1 |
| 新のみ | 1 |
| **合計** | **12** |

| 差分の種類 | 高 | 中 | 低 | 未決 |
|---|--:|--:|--:|--:|
| 機能 | 5 | 15 | 4 | 12 |
| 参照データ | 1 | 7 | 2 | 3 |
| 振る舞い | 3 | 5 | 2 | 0 |
| 権限 | 0 | 0 | 0 | 0 |
| 画面 | 0 | 0 | 1 | 0 |
| **合計** | **9** | **27** | **9** | **15** |
