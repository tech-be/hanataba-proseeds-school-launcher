# 受講 — 機能の差分

受講のデータ（受講権限・進捗・受験結果・提出・回答・予約・修了証）を**使う機能**を1つずつ挙げ、新旧でどう違うかを書く。
書き方の約束（判定・差分の種類・深刻度・対応の書き方）は [ひな形](../00-template/features.md) を参照。

- **調査時点:** 2026-09-30
  - 旧: `learningware-kiracari`
  - 新: `school-launcher` の `feat/lw2-billing-schema`（`hanataba_dev` に lw2 移行のスキーマを足したもの。アプリのコードは `hanataba_dev` と同じ）
- **根拠の場所の書き方:**
  - 旧は `learningware-kiracari/application/` からの相対パス。
  - 新は `btoc-backend/` / `btoc-frontend/` からのパス。
- データの受け皿（A1〜A10）は [突き合わせ](review.md#新環境に追加するテーブルカラム) を参照。**この文書は「受け皿に入れたデータを新の機能が読んでいるか」を見る**
- 件数はステージングの移行データ（2026-09-30 の実行）で数えた参考値

> **要点。** 受講で足した受け皿（A1〜A10）のうち、新の機能が読むのは `quiz_answers.is_correct`（成果レポート）の1か所だけ。
> 旧の受講者に直接効くものは次の3つ。
>
> - **取り消し・期限切れの受講があると、同じ講座を買い直せない・受講登録し直せない**（F01。取り消し374件・期限切れ3,381件）
> - **旧で削除した進捗を、新は進捗・修了・分析に数える**（F02。184行、うち完了92行）
> - **管理者が受講を1件ずつ付与・取り消し・期間変更できない**（F01）

> **移行ツール側の誤りも2つ見つかった（2026-09-30 に直した）。**
>
> - **F04:** 旧 `user_learning_report.eval_*_file_name1〜5` は**添削者が付けたファイル**だった（`modules/admin-lesson/controllers/ReportController.php` の `evaluationAction()` で書き、受講者の画面では添削のコメントの下に出す。評価の公開待ちの間は見せない）。移行ツールは「列名は eval_* だが受講者の提出」として `submission_files` に移しており、**移し先が逆**だった。いまは添削に付けたファイルとして `submission_feedback_files`（新設）に移す。
> - **F05:** 新は「回答済みか」を `survey_submission_log` だけで判断するが、移行ツールはこの記録を作っていなかった（旧で回答済みの会員がもう一度回答できた）。いまは途中保存でない回答から作る。

---

## 機能の一覧

| ID | 機能 | 利用者 | データ種 | 判定 | 差分（高 / 中 / 低） | 未決 |
|---|---|---|---|:--:|:--:|--:|
| F01 | 受講登録と受講中の講座 | 受講者・管理者 | J01 / O24 | △ | 2 / 2 / 0 | 2 |
| F02 | 学習の進捗と修了 | 受講者 | J02 / J03 | △ | 1 / 2 / 1 | 0 |
| F03 | テストの受験結果 | 受講者・講師 | O09 / O10 | △ | 0 / 3 / 1 | 1 |
| F04 | 課題の提出と添削 | 受講者・講師 | O18 / O19 | △ | 1 / 3 / 1 | 3 |
| F05 | アンケートの回答 | 受講者・管理者 | O14 / O16 / O17 | △ | 1 / 1 / 0 | 1 |
| F06 | ライブの予約・出欠 | 受講者・講師 | L03 / L04 | △ | 0 / 2 / 1 | 1 |
| F07 | ライブのレビュー | 受講者・管理者 | L08 | X | 0 / 1 / 0 | 1 |
| F08 | 修了証 | 受講者・管理者 | O25 / O26 | △ | 0 / 2 / 1 | 3 |
| F09 | 自動割当 | — | J04 / J05 / J06 | △ | 0 / 2 / 1 | 1 |
| F10 | 管理者による受講状況の確認 | 管理者 | J01 / J02 | △ | 0 / 2 / 0 | 2 |

---

## 各機能

### F01 受講登録と受講中の講座

利用者: 受講者・管理者 ／ データ種: J01 受講権限、O24 受講期限・延長 ／ 判定: **△ 差分あり**

- 旧: 受講の判定は `models/LessonModel.class.php` の `_buildSql()`（`lesson_start_date` 〜 `lesson_end_date` の間だけ開ける。終了日が NULL なら無期限）、有料ユニットは `PaymentAuthorityModel::checkAuthorityIdByUserId()`。自動延長は `batch/AuthorityCheckBatch.class.php`。管理画面は `modules/admin-user/controllers/UserController.php`（会員ごとの付与・取り消し）と `modules/admin-lesson/controllers/AuthorityController.php`（期間の一括変更）
- 新: `internal/service/enrollment_check.go` の `VerifyEnrollment`（`status = 'active'` かつ `expires_at` が NULL か未来）、期限切れは worker の `runEnrollmentExpiryBatch`。管理者は CSV の一括登録（`POST /tenant/learners/import`）だけ

#### 参照データ

| データ | 旧（テーブル.列） | 新（テーブル.列） | 旧で使う | 新で使う | 差分 |
|---|---|---|:--:|:--:|---|
| 受講期間 | `user_learning_lesson.lesson_start_date` / `lesson_end_date` | `enrollments.enrolled_at` / `expires_at` | ◯ | ◯ | どちらも「終了日が無ければ無期限」 |
| 取り消し | `payment_item_lesson_authority.del_chk` | `enrollments.status = 'revoked'` | ◯ | △ | 新は `active` 以外を開かせないので効く。ただし買い直しも止まる |
| 権限の設定 | `payment_item_lesson_authority` の `cancel_chk` / `no_limit_chk` / `remote_chk` など | `enrollments.settings` | ◯ | — | 新は読まない。`no_limit_chk` は畳んだ `unlimited` だけを残す（`payment_no_limit_chk` / `payment_authority_end_date` は移していない） |
| 有料ユニット | `unit.payment_unit` ＋ `payment_item_lesson_authority` | — | ◯ | — | 新は講座単位でしか開閉しない |

#### 差分

| 種類 | 深刻度 | 内容 | 対応 |
|---|:--:|---|---|
| 振る舞い | 高 | **取り消し・期限切れ・返金の受講があると、同じ講座を買い直せない**（決済の前の確認が「受講登録済み」で 409 を返す）。無料講座も、古い行を返すだけで受講中に戻らない | 新で、`active` でない受講がある講座の買い直し・受講登録を受け付ける |
| 機能 | 高 | 管理者が受講を1件ずつ付与・取り消し・期間変更できない。旧は会員ごと・講座ごとに付与・取り消し・期間の一括変更（無期限を含む）ができた | 新で受講の管理画面を実装する |
| 機能 | 中 | 継続課金の受講を毎月自動で延長する仕組み（旧はバッチが1か月ずつ延ばす）が新に無い | 未決: [D4](../open-questions.md#d-cutover-の運用で決めておきたいこと) の回答で決める |
| 機能 | 中 | 講座の中の一部のユニットだけを有料にする（購入するまで鍵をかける）仕組みが新に無い | 未決: 運営に使っているかを確認する（[E28](../open-questions.md#e-切り替え後の機能で決めておきたいこと)） |

### F02 学習の進捗と修了

利用者: 受講者 ／ データ種: J02 ユニット進捗、J03 中断データ ／ 判定: **△ 差分あり**

- 旧: 完了は `models/ApiLessonModel.class.php` の `setUserUnitStatus()`、講座の修了は `_updateUserLearningCompleteDate()`（見出し以外の全ユニットが完了）。種別ごとの状態は `constants/UserLearningConstants.php`
- 新: `internal/service/progress_service.go` の `UpdateLessonProgress` / `GetCourseProgress`、修了の判定は `internal/domain/completion_policy.go`（公開中の全レッスンが完了＋最終テストに合格）

#### 参照データ

| データ | 旧（テーブル.列） | 新（テーブル.列） | 旧で使う | 新で使う | 差分 |
|---|---|---|:--:|:--:|---|
| 完了 | `user_learning_unit.learning_status` / `complete_date` | `lesson_progress.completed_at` | ◯ | ◯ | — |
| 削除 | `user_learning_unit.del_chk` | `lesson_progress.deleted_at` | ◯ | — | **新は削除済みも数える** |
| 種別ごとの状態 | `user_learning_unit.progress_status`（課題なら 未提出 / 評価待ち / 評価済み / 再提出 / 公開待ち） | `lesson_progress.progress_status` | ◯ | — | 新は読まない |
| 中断データ | `user_learning_unit.suspend_data` | `lesson_progress.settings` | ◯ | — | 新は動画の再生位置（`last_position`）で再開する |

#### 差分

| 種類 | 深刻度 | 内容 | 対応 |
|---|:--:|---|---|
| 振る舞い | 高 | **旧で削除した進捗を、新は進捗率・修了・分析に数える**（`deleted_at` で絞っていない。ステージングで184行、うち完了92行） | 新で進捗を読むところに `deleted_at IS NULL` を足す（A9） |
| 参照データ | 中 | 課題の「評価待ち」「再提出」などの種別ごとの状態が、受講画面に出ない | 新で種別ごとの状態を出す（A9） |
| 振る舞い | 中 | 修了の条件が違う。旧は「見出し以外の全ユニットが完了」、新は「公開中の全レッスンが完了＋最終テストに合格」。免除（02 F05）も新には無い | 新で免除を実装するときに、修了の判定もあわせて見直す |
| 機能 | 低 | 教材の中断データ（`suspend_data`）から再開できない | 対応不要。動画は新の再生位置で再開できる |

### F03 テストの受験結果

利用者: 受講者・講師 ／ データ種: O09 テスト受験、O10 設問別回答 ／ 判定: **△ 差分あり**

- 旧: 採点は `models/UserLearningLessonModel.class.php` の `setUserLearningMark()`、結果画面は `modules/default/views/scripts/lesson/test-complete.phtml`（最新の受験）、履歴は `LessonController::testResultAction()`、管理画面は `modules/admin-lesson/controllers/HistTestController.php`（初回・最終・最高点・回数の CSV）
- 新: `internal/quiz/service/quiz_attempt_service.go`、画面 `components/lesson/quiz-idle-view.tsx`（最高点と直近5件）、管理者の CSV は `quiz_export_service.go`（点・満点・合否・日時）

#### 参照データ

| データ | 旧（テーブル.列） | 新（テーブル.列） | 旧で使う | 新で使う | 差分 |
|---|---|---|:--:|:--:|---|
| 合否 | `user_learning_test.test_pass` | `quiz_attempts.passed` | ◯ | — | 新は読むたびに今の合格点で計算し直す |
| 受験時間 | `test_start_time` / `test_end_time` | `quiz_attempts.duration_sec` | ◯ | — | 新は読まない |
| 設問ごとの正誤 | `user_learning_test_sub.question_pass` | `quiz_answers.is_correct` | ◯ | △ | 成果レポートだけが読む。解答の画面は今の正解で計算し直す |
| 選択肢の並び | `user_learning_test_sub.option_order` | `quiz_answers.option_order` | ◯ | — | 新は読まない |

#### 差分

| 種類 | 深刻度 | 内容 | 対応 |
|---|:--:|---|---|
| 振る舞い | 中 | 合否と正誤を、今の合格点・今の正解で計算し直す。切り替え後に合格点や正解を直すと、**旧の受験結果の合否が変わる** | 新で、移した受験は `passed` / `is_correct` を読む |
| 参照データ | 中 | 成果レポート（`achievement_repo.go`）は `quiz_answers.is_correct` を読むが、新で受けた解答はこの列が NULL で、**不正解として数えられる** | 新で解答を保存するときに `is_correct` を書く（移行とは別の新システムの不具合） |
| 機能 | 中 | 管理者の結果 CSV が、旧（初回・最終・最高点・受験回数、設問ごとの解答）より少ない | 未決: 新の CSV に載せる列を運営と決める（[E29](../open-questions.md#e-切り替え後の機能で決めておきたいこと)） |
| 画面 | 低 | 受験時間が出ない | 新で `duration_sec` を出す（A1） |

### F04 課題の提出と添削

利用者: 受講者・講師 ／ データ種: O18 課題、O19 提出ファイル ／ 判定: **△ 差分あり**

- 旧: 受講者の回答は課題用のアンケート（`enquete_answer`、種別3）で出す（`modules/default/controllers/EnqueteController.php`）。添削は `modules/admin-lesson/controllers/ReportController.php` の `evaluationAction()` / `completeAction()`、CSV での一括添削は `workingAction()`
- 新: `internal/assignment/service/submission_service.go` / `grading_service.go`、画面 `courses/[courseId]/assignments/*`、`admin/assignments/grading/*`

#### 参照データ

| データ | 旧（テーブル.列） | 新（テーブル.列） | 旧で使う | 新で使う | 差分 |
|---|---|---|:--:|:--:|---|
| 受講者の回答 | `enquete_answer`（種別3） | — | ◯ | — | [C4](../open-questions.md#c-新環境の制約が意図的かの確認) |
| 添削者の添付ファイル | `user_learning_report.eval_*_file_name1〜5` | `submission_feedback_files`（新設） | ◯ | — | 新は読まない（2026-09-30 に移し先を直した） |
| 点数 | `user_learning_report.score` | `submissions.score` | ◯ | — | 新は添削の点数だけを読む |
| 設問ごとのコメント | `user_learning_report.report_question_comment` | `submission_feedbacks.question_comments` | ◯ | — | 新は読まない |

#### 差分

| 種類 | 深刻度 | 内容 | 対応 |
|---|:--:|---|---|
| 参照データ | 中 | 添削者の添付ファイルが、添削のコメントの下に出ない（`submission_feedback_files` を新が読まない）。**移行ツールの取り違えは 2026-09-30 に直した** | 新で添削の添付を出す（A3） |
| 機能 | 高 | 課題の設問形式（設問ごとの回答）が新に無い | 未決: [C4](../open-questions.md#c-新環境の制約が意図的かの確認) の回答で決める |
| 参照データ | 中 | 設問ごとの添削コメントと、移した点数（添削の行が無い提出の点数）が出ない | 新で `question_comments` / `submissions.score` を読む（A3） |
| 機能 | 中 | 「評価の公開待ち」（評価を書いてから受講者に見せるまで止める）が新に無い | 未決: 運営に使っているかを確認する（[E30](../open-questions.md#e-切り替え後の機能で決めておきたいこと)） |
| 機能 | 低 | CSV での一括添削が新に無い | 未決: 運営に使っているかを確認する（[E31](../open-questions.md#e-切り替え後の機能で決めておきたいこと)） |

### F05 アンケートの回答

利用者: 受講者（回答）・管理者（集計）／ データ種: O14 ユニットアンケート、O16 お知らせ添付、O17 レポート添付 ／ 判定: **△ 差分あり**

- 旧: 回答は `models/EnqueteModel.class.php` の `createEnqueteAnswer()`（途中保存は `suspended_chk=1`）、集計は `modules/admin-lesson/controllers/HistEnqueteSummaryController.php`
- 新: `internal/survey/service/response_service.go`、回答済みかは `response_repo.go` の `HasSubmitted`（`survey_submission_log` を見る）、集計と CSV はレッスン単位

#### 参照データ

| データ | 旧（テーブル.列） | 新（テーブル.列） | 旧で使う | 新で使う | 差分 |
|---|---|---|:--:|:--:|---|
| 回答 | `enquete_answer.answer` | `survey_responses` / `survey_answers` | ◯ | ◯ | — |
| 回答済み | `enquete_answer` の有無 | `survey_submission_log` | ◯ | ◯ | —（2026-09-30 に移すようにした） |
| 何への回答か | `enquete_answer.entity_type_id`（お知らせ / ユニット / 課題） | `survey_responses.entity_type` / `entity_id` | ◯ | — | 新は読まない |
| 途中保存 | `enquete_answer.suspended_chk` | `survey_responses.suspended` | ◯ | — | 新は読まない |

#### 差分

| 種類 | 深刻度 | 内容 | 対応 |
|---|:--:|---|---|
| 振る舞い | — | **（対応済み）旧で回答済みの会員が、もう一度回答できた。** 移行ツールが `survey_submission_log` を作っていなかった | 2026-09-30 に移行ツールを直した。途中保存でない回答から、ユニットと会員の組ごとに最初の回答日時で1行作る（ステージングで81行） |
| 振る舞い | 中 | 途中保存の回答が、回答済みとして集計に混ざる | 新で集計から `suspended` を外す（A4） |
| 機能 | 高 | お知らせに付いたアンケートの回答が新で見えない | 未決: [C5](../open-questions.md#c-新環境の制約が意図的かの確認) の回答で決める |

### F06 ライブの予約・出欠

利用者: 受講者・講師 ／ データ種: L03 予約・出欠、L04 リマインド ／ 判定: **△ 差分あり**

- 旧: `models/LiveLessonModel.class.php`（予約 `createLiveLessonReserve()`、取り消し `updateCancelChk()`、開催の変更で止める `updateStopChk()`、出席 `updateAttendance()`）。受講者が参加 URL を開くと出席になる（`LiveLessonController::lessonUrlAction()`）
- 新: `internal/live/service/reservation_service.go`、出欠は講師が付ける（`POST .../attendance`）、管理画面 `attendance-roster.tsx`

#### 参照データ

| データ | 旧（テーブル.列） | 新（テーブル.列） | 旧で使う | 新で使う | 差分 |
|---|---|---|:--:|:--:|---|
| 予約の状態 | `live_lesson_reserve.cancel_chk` / `attendance_chk` / `stop_chk` | `live_reservations.status` | ◯ | △ | 新のコードは `host_canceled`（旧 `stop_chk`）を知らない |
| 参加の確認キー | `live_lesson_reserve.verification_key` | `live_reservations.verification_key` | ◯ | — | 新は読まない |
| 最終アクセス | `live_lesson_reserve.recent_access_date` | `live_reservations.settings` | ◯ | — | 新は読まない |

#### 差分

| 種類 | 深刻度 | 内容 | 対応 |
|---|:--:|---|---|
| 振る舞い | 中 | 旧で開催の変更により止められた予約（`host_canceled`、ステージング2件）が、管理画面で状態が空欄になり、予約し直せない。出欠は付けられてしまう。旧は受講者が別の回に振り替えられた | 新で `host_canceled` を扱う（A5） |
| 振る舞い | 中 | 旧は受講者が参加 URL を開くと自動で出席になった。新は講師が出欠を付ける | 未決: 運営に、出席を自動で記録する必要があるかを確認する（[E32](../open-questions.md#e-切り替え後の機能で決めておきたいこと)） |
| 振る舞い | 低 | 旧のキャンセル期限は画面でボタンを隠すだけだった。新はサーバーでも止める | 対応不要。新の方が正しい |

### F07 ライブのレビュー

利用者: 受講者（書く）・管理者（返信）／ データ種: L08 ライブレビュー ／ 判定: **X 新に無い**

- 旧: `modules/default/controllers/LiveLessonController.php`（出席した予約があるときだけ書ける）、表示はライブの詳細・講師の詳細・公開ページ、管理は `modules/admin/controllers/LiveLessonReviewController.php`
- 新: 無い（講座単位の `course_reviews` だけ。`live_lesson_reviews` は受け皿だけ）

#### 差分

| 種類 | 深刻度 | 内容 | 対応 |
|---|:--:|---|---|
| 機能 | 中 | ライブのレビュー（星・本文、管理者の返信）が新に無い。移したレビュー（ステージング3件）は見えない | 未決: 運営に使っているかを確認する（[E33](../open-questions.md#e-切り替え後の機能で決めておきたいこと)） |

### F08 修了証

利用者: 受講者・管理者 ／ データ種: O25 講座単位、O26 商品単位 ／ 判定: **△ 差分あり**

- 旧: `modules/default/controllers/LessonController.php` の `certificateAction()`（講座単位と商品単位。HTML のひな形を画面に出して印刷する）、番号は `certificate_no` のテナント連番に `No.` ＋ 日付を付ける
- 新: `internal/service/certificate_service.go`（講座の修了で自動発行、PDF）、検証 `GET /certificates/verify/:serial`

#### 参照データ

| データ | 旧（テーブル.列） | 新（テーブル.列） | 旧で使う | 新で使う | 差分 |
|---|---|---|:--:|:--:|---|
| 講座単位の修了証 | `user_certificate`（種別1） | `certificates` | ◯ | ◯ | — |
| 商品単位の修了証 | `user_certificate`（種別2） | —（`certificates.product_id` は足したが書かない） | ◯ | — | **移していない**（`certificates.course_id` が NOT NULL。ステージング0件） |
| 講座ごとの発行方針 | `lesson.certificate_id`（ひな形の有無） | `course_certificate_policies.issue` | ◯ | ◯ | 移した全講座に行を入れる（行が無いと新は発行する） |

#### 差分

| 種類 | 深刻度 | 内容 | 対応 |
|---|:--:|---|---|
| 機能 | 中 | 商品単位（複数の講座をまとめた商品）の修了証が新に無い | 未決: 運営に使っているかを確認する（[E34](../open-questions.md#e-切り替え後の機能で決めておきたいこと)） |
| 振る舞い | 中 | 新は受講が有効でないと修了証の PDF を出せない。受講が期限切れ・取り消しになった修了者は、修了証を出し直せない | 未決: 期限切れのあとも修了証を出せるようにするかを運営と決める（[E35](../open-questions.md#e-切り替え後の機能で決めておきたいこと)） |
| 画面 | 低 | 旧は HTML を印刷、新は PDF。番号の書式も変わる（旧は `No.` ＋ 日付 ＋ 連番） | 未決: 運営に、再発行で書式が変わってよいかを確認する（[E36](../open-questions.md#e-切り替え後の機能で決めておきたいこと)） |

### F09 自動割当

利用者: —（登録・購入のたびに動く）／ データ種: J04 購入時自動割当、J05 属性・グループ条件、J06 求人 ／ 判定: **△ 差分あり**（2026-09-30 に新の自動付与ルールへ移すようにした）

- 旧: 規則は `modules/admin/controllers/ConfigAutoassignController.php`、割当は `models/AssignModel.class.php`（講座・お知らせ・クーポン・求人。条件はグループ・属性・購入した商品・ログインの可否）
- 新: タグの自動付与ルール（`tag_auto_assign_rules` ほか。購入か会員登録で発動し、講座・クーポン・お知らせを付与する）

#### 参照データ

| データ | 旧（テーブル.列） | 新（テーブル.列） | 旧で使う | 新で使う | 差分 |
|---|---|---|:--:|:--:|---|
| ルール | `assign` | `tag_auto_assign_rules`（`assign_id`） | ◯ | ◯ | 名前は「旧 自動割当 #ID」 |
| きっかけの商品 | `assign_payment_item` | `…_rule_triggers.plan_id` / `course_id` / `item_id` | ◯ | ◯ | 全行移す（2026-10-01）。講座の商品 → `plan_id`、レッスン → `course_id`、それ以外の商品は旧の `item_id` だけ |
| 条件の属性 | `assign_attribute` | `…_rule_conditions`（タグ） | ◯ | ◯ | — |
| 条件のグループ | `assign_group` | `tag_auto_assign_rule_group_conditions`（2026-10-01） | ◯ | — | 移しているが新は読まない。グループで絞ったルールも全員に効く（ステージングは0件） |
| 付与するもの | `assign_item` | `…_rule_grants` | ◯ | ◯ | お知らせ・クーポンは 05 で移す予定の ID を先に入れている |
| 付与の記録 | `assign_log` | `tag_auto_assign_logs` | ◯ | ◯ | 付与の行が消えた記録は移せない（下） |

#### 差分

| 種類 | 深刻度 | 内容 | 対応 |
|---|:--:|---|---|
| 振る舞い | 中 | 旧は登録・購入・会員の編集のたびに動いた。新は「購入」か「会員登録」のどちらかで発動する | 未決: [E13](../open-questions.md#e-切り替え後の機能で決めておきたいこと)（発動のきっかけの暫定の規則）の回答で決める |
| 参照データ | 中 | お知らせ・クーポンを付与するルールは、05（お知らせ・クーポン）を移すまで付与先が無い | 05 のお知らせ・クーポンを移すときに、同じ ID で入れる |
| 参照データ | 低 | 旧はルールを編集するたびに付与の行を作り直すので、古い記録（ステージング 4,908件中 3,907件）は何を付与したかが残っていない | 対応不要。一覧に出している |

### F10 管理者による受講状況の確認

利用者: 管理者 ／ データ種: J01 受講権限、J02 ユニット進捗 ／ 判定: **△ 差分あり**

- 旧: `modules/admin-lesson/controllers/HistUserLearningLessonController.php` ほか（受講状況・ユニット別・進捗率・学習時間の一覧と CSV。検索した受講者にお知らせ・メールを送る導線）。自動のフォローメールは `batch/FollowmailSendBatch`、ユニットの公開通知は `UnitStartMailBatch`、延長の通知は `ExtensionMailBatch`
- 新: `routes_tenant_admin.go` の分析（講座の分析・成果レポート・つまずき・受講者一覧と CSV・メール送信）、休眠会員へのリテンションメール（`internal/retention`）

#### 差分

| 種類 | 深刻度 | 内容 | 対応 |
|---|:--:|---|---|
| 振る舞い | 中 | 新の分析は受講中（`active`）の受講だけを数える。期限切れ・取り消しの受講者の進捗や修了は出ない | 未決: 期限切れの受講者も分析に出すかを運営と決める（[E37](../open-questions.md#e-切り替え後の機能で決めておきたいこと)） |
| 機能 | 中 | 旧のフォローメール（受講開始・終了から N 日、ユニットの完了状況で送る）、ユニットの公開通知、延長の通知が新に無い。新は休眠会員へのメールだけ | 未決: 運営に使っているかを確認する（[E38](../open-questions.md#e-切り替え後の機能で決めておきたいこと)） |

---

## 移したが新で読まれないデータ

各機能の「参照データ」で**新で使う が `—`** の行を集めたもの。

| 新テーブル.列 | 旧 | 旧で使っていた機能 | 対応 |
|---|---|---|---|
| `enrollments.settings` | `payment_item_lesson_authority` の各フラグ | F01 受講 | 新で必要なものを読む |
| `lesson_progress.deleted_at` | `user_learning_unit.del_chk` | F02 進捗 | 新で絞り込みに使う（A9） |
| `lesson_progress.progress_status` / `settings` | `user_learning_unit` の各列 | F02 進捗 | 新で実装する（A9） |
| `quiz_attempts.passed` / `duration_sec` | `user_learning_test` の各列 | F03 受験結果 | 新で読む（A1） |
| `quiz_answers.option_order` / `sort_no` / `pre_question_pass` | `user_learning_test_sub` の各列 | F03 受験結果 | 新で読む（A2） |
| `submission_feedback_files` | `user_learning_report.eval_*_file_name1〜5` | F04 添削 | 新で添削の添付を出す（移行ツールは 2026-09-30 に直した） |
| `submissions.score` / `settings`、`submission_feedbacks.question_comments` | `user_learning_report` の各列 | F04 添削 | 新で読む（A3） |
| `survey_responses.entity_type` / `entity_id` / `suspended` | `enquete_answer` の各列 | F05 回答 | 新で読む（A4） |
| `live_reservations.verification_key` / `settings`、状態 `host_canceled` | `live_lesson_reserve` の各列 | F06 予約 | 新で扱う（A5） |
| `certificates.product_id` | `user_certificate`（種別2） | F08 修了証 | 未決（F08） |
| `live_lesson_reviews` | `live_lesson_review` | F07 レビュー | 未決（F07） |

---

## 集計

| 判定 | 件数 |
|---|--:|
| ◯ 同等 | 0 |
| △ 差分あり | 9 |
| X 新に無い | 1 |
| 新のみ | 0 |
| **合計** | **10** |

| 差分の種類 | 高 | 中 | 低 | 未決 |
|---|--:|--:|--:|--:|
| 機能 | 3 | 7 | 2 | 10 |
| 参照データ | 0 | 5 | 1 | 0 |
| 振る舞い | 2 | 8 | 1 | 4 |
| 権限 | 0 | 0 | 0 | 0 |
| 画面 | 0 | 0 | 2 | 1 |
| **合計** | **5** | **20** | **6** | **15** |
