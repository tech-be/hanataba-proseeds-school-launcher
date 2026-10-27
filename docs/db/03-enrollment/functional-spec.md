# 受講 — 新システムの機能仕様（移したデータの見え方）

移行の見直しの手順 1（[進捗](../rework-progress.md)）。**新システムが受講のデータ（受講登録・コースの受講・学習の記録・修了証・テストの結果・課題の提出と添削・アンケートの回答・ライブの予約）をどう読み書きするか**を、移したデータがどう見えるかの観点で書き出したもの。手順 2 のテスト仕様書と手順 3 の移行仕様の材料にする。

- **基準**: school-launcher `hanataba_dev` の `584026af`（2026-10-24）＋ 作業ブランチの変更（アンケートの `deleted_at` など）。コードを読んで調べた（動かしてはいない）。
- **コードの場所**は school-launcher の `btoc-backend/` からの相対パス。`internal/` と `db/migrations/`（`MIG/`）。
- **未確認**は推論だけのもの。
- **時刻はすべて UTC で読む**（接続で `time_zone='+00:00'`）。旧の JST の値は UTC に直して入れる。

## 0. 移し方に効く点（先に）

| # | 内容 | 場所 |
|---|---|---|
| 0-1 | **受講できるのは `status = 'active' AND (expires_at IS NULL OR now < expires_at)`。** 期限は「受講できなくなる時刻」（最終日の翌日 0 時 JST を UTC で）。画面のマイ講座は status だけを見るので、期限切れでも active なら一覧に出て、開くと 403。期限切れのバッチ（24 時間ごと）が来るまでそのまま | `internal/domain/enrollment.go:75-87`、`cmd/worker/main.go:1779-1830` |
| 0-2 | **`enrollments.completed_at` を書くのは「初めてレッスンを完了したとき」のイベントだけ。** 移したあとは二度と立たないので、移行で入れないと受講順番の鍵が開かず、インサイトも「学習中」のまま | `internal/server/wire_events_domain.go:65-74`、`internal/service/course_order_gate.go:131` |
| 0-3 | **修了証の連番（`certificate_settings.serial_next`）が発行済みの最大以下だと、次の自動発行が UNIQUE で失敗する**（ログに出るだけ） | `internal/certificate/repository/certificate_settings_repo.go:67-92` |
| 0-4 | **修了しているのに修了証の行が無いと、受講者が PDF を取った時点で新しい番号が採番される。** 講座の方針（`course_certificate_policies`）の行が無ければ「発行する」扱い | `internal/service/certificate_service.go:96` |
| 0-5 | **`lesson_progress.updated_at` が最終学習日。** 指定せずに入れると全員の最終学習日が移行日になり、3〜30 日後に学習のリマインドが一斉に届く | `internal/repository/learner_analytics_repo.go:151-205` |
| 0-6 | 受講順番は `via_learning_path = TRUE` の受講登録だけに効く。TRUE なら有効なコースの受講（LPE）と前の講座の `completed_at` が要る | `course_order_gate.go:79-149` |
| 0-7 | **テストの合否・正誤は、今の合格点・正解で毎回計算し直す。** 旧の判定を入れた列（`quiz_attempts.passed`・`quiz_answers.is_correct`）は読まれない。状態（`status`）で絞らないので、途中の受験も「0% 不合格」で履歴に出る | `internal/quiz/repository/quiz_repo.go:335-341, 517-540` |
| 0-8 | **アンケートの回答済みの判定は `survey_submission_log` だけ。** 回答を移しても記録が無いと二重に回答できる。回答の送信でレッスンが完了するので、移した回答とは別に学習の記録（`lesson_progress`）も要る | `internal/survey/repository/response_repo.go:85-93` |
| 0-9 | アンケートの集計は、削除済み・中断中・お知らせ向けの回答も数える（`deleted_at` / `suspended` / `entity_type` を見ない） | `internal/survey/service/survey_service.go:191-282` |
| 0-10 | **ライブの予約の状態 `host_canceled` を Go・画面が知らない**（ラベルが空、同じ回を予約し直すと 500、出欠も付けられる） | `internal/live/domain/live.go` |
| 0-11 | **未来の予約で `reminded_at` が NULL だと、切り替え後にリマインドが送られる。** 予約で消費したチケットの記録が無いと、キャンセルしてもチケットは返らない | `internal/live/repository/reservation_repo.go:139-157` |
| 0-12 | 課題の添削のファイルのキーが `tenants/{tid}/feedback/{submissionId}/` の配下でないと、運営が採点し直せない（画面が既存のキーをそのまま送り返し、サーバーで 400）。添削・提出の複数ファイル（`*_files`）は画面に出ない | `internal/assignment/service/grading_service.go` |
| 0-13 | 課題の提出の状態は submitted / under_review / graded / returned、添削の結果は pass / fail / needs_resubmission（どちらも DB の制約は無い）。旧で採点済みは graded / returned でないと、採点待ちの一覧に入る | `internal/assignment/domain/assignment.go:31-43` |
| 0-14 | 修了証の PDF は「有効な受講登録があり、今も修了している」ときだけ取れる（期限切れの受講者は過去の修了証も取れない。一覧には出る） | `internal/service/certificate_service.go:61-73` |

## 1. 受講登録（`enrollments`）

| 列 | 扱い |
|---|---|
| （テナント, 会員, 講座） | UNIQUE。1 人 1 講座 1 行 |
| `status` | active / expired / refunded / revoked（外部キー）。アプリが書くのは active / expired / refunded |
| `source` | purchase / subscription / free / admin / marketplace。お知らせ・クーポンの「購入者」は purchase / subscription |
| `via_learning_path` | 受講順番・期限の同期・リモートPC の判定 |
| `enrolled_at` | ドリップの起点・修了証の期間の始まり・リテンション |
| `expires_at` | NULL は無期限（0-1） |
| `completed_at` | 0-2。完了の方向にしか更新しない |
| `settings` | **読まれない** |

**画面**: マイ講座（`GET /enrollments/details?limit=50`。画面で `status === 'active'` だけ残す。**1 回 50 件まで**）、ホーム、講座ごとの期限（有効な LPE の最も遅い期限、無ければ受講登録の期限）、コースの鍵、修了証。

**受講できるかの判定**（0-1）: レッスンの一覧（受講できなければ説明を隠す）・動画・進捗の更新（ドリップと受講順番も）・テスト・メモ・課題・アンケート・AI チャット・ディスカッション。無料公開（`is_preview`）のレッスンは受講登録なしで開ける。

**受講順番**（0-6）: 有効な LPE のどれかが順番なし、または並びで前の講座がすべて `completed_at` ありなら開く。

**管理者が受講登録を直接編集する API は無い**（コースの割り当て・取り消し、名簿の取り込み、タグの自動付与、返金、解約だけ）。

## 2. コースの受講（`learning_path_enrollments` / `learning_path_enrollment_courses`）

- LPE: source は purchase / free / admin、status は active / refunded / revoked（CHECK）。期限切れの状態は無く `expires_at` で判定。同じ会員 × コースで複数行を持てる。
- LPEC: 取り消しのときだけ読む（受講できるかの判定には使わない。判定は今の `learning_path_courses`）。**`prev_recorded = TRUE` で `prev_status` が NULL だと取り消しで失敗する**（推論）。
- 受講登録との期限の同期は `via_learning_path` で変わる（コース由来の行は期限を合わせ、そうでない行は延ばすだけ）。

## 3. 学習の記録（`lesson_progress`）

- UNIQUE（テナント, 会員, レッスン）。外部キーは lessons（削除したレッスンの行が無いと入れられない）。
- 真のデータは `last_position`（秒）と `completed_at` だけ。進捗率は読むときに計算（完了なら 100、動画なら `last_position ÷ video_duration`）。
- **`updated_at` が最終学習日**（0-5）。`progress_status` / `settings` / `deleted_at` は**読まれない**（`deleted_at` を立てても数えられる）。
- 一度入れた `completed_at` は戻らない。

## 4. 修了と修了証

| 表 | 扱い |
|---|---|
| `certificates` | UNIQUE（テナント, 会員, 講座）・（テナント, `serial_no`）。`serial_text` は発行時に固定。`revoked_at` が NULL なら有効。`period_start` / `period_end` / 金額は詳細のレイアウトに出る |
| `certificate_settings` | テナントに 1 行。`serial_next`（0-3）・番号の書式（padded / date_prefixed。旧は date_prefixed）・自動発行 |
| `course_certificate_policies` | 行が無ければ発行する。`issue = FALSE` は自動も手動も拒否 |
| `certificate_events` | 管理画面の履歴に出る |

- 修了: 公開中のレッスンがすべて完了（と修了テストの合格）。発行は修了のイベントで自動、または PDF を取ったとき（0-4）、または運営の手動。
- 公開の照会 `GET /certificates/verify/:serial` は**整数の `serial_no`** で引く。

## 5. テストの結果（`quiz_attempts` / `quiz_answers` / `quiz_answer_selected_options`）

| 列 | 扱い |
|---|---|
| `quiz_attempts.score` / `max_score` | 表示（`score × 100 ÷ max_score`） |
| 合否 | **今の合格点で計算**（0-7）。`passed` 列は読まれない |
| `status` | 絞り込みに使わない（途中・中断も履歴に出る） |
| `started_at` | NOT NULL。並び順 |
| `completed_at` | CSV の受験日時 |
| 回答の正誤 | **今の選択肢・配点で計算**。`is_correct` 列は採点に使われない（壊れている `achievement_repo` だけが読む） |
| `quiz_answer_selected_options` | PK（回答, 選択肢）。選択肢を消すと CASCADE で消える |

- 受講者: レッスンのテストのタブで最新 5 件。管理者: CSV（受験の一覧の画面は無い）。修了テストの合格は全受験のどれかが合格なら合格。
- 外部キー: 受験 → テスト、回答 → 設問は RESTRICT（移さないテスト・設問への受験・回答は入らない）。

## 6. 課題の提出と添削（`submissions` / `submission_feedbacks` / `submission_feedback_files`）

| 列 | 扱い |
|---|---|
| `submissions.status` | 0-13。submitted / under_review は採点待ちの一覧（テナント全体）に入る |
| `submissions.submitted_at` | NOT NULL（未提出は入らない） |
| `submissions.object_key` | presigned で開く（オブジェクトが無いとリンク切れ）。**受講者は自分の提出ファイルを開けない**（本文だけ） |
| `submission_feedbacks` | UNIQUE（提出）。`reviewer_id` / `body` / `result` NOT NULL。`score` 0〜100 |
| `submission_feedbacks.object_key` | 0-12 |
| `submission_files` / `submission_feedback_files` / `submissions.score` / `settings` / `question_comments` | **読まれない** |

- 受講者に添削が見えるのは graded / returned のとき。

## 7. アンケートの回答（`survey_responses` / `survey_answers` / `survey_answer_selected_options` / `survey_submission_log`）

- `survey_answers` は UNIQUE（回答, 設問）。選択肢は PK（回答, 選択肢）。設問・選択肢への外部キーは RESTRICT。
- `survey_submission_log` は PK（テナント, レッスン, 会員）（0-8）。
- 集計（0-9）・CSV（匿名の設定なら「匿名」、会員がいなければ「（削除済み）」）。**回答が 1 件でもあると設問を変更できない。**
- `survey_responses.entity_type` / `entity_id` / `suspended` / `deleted_at` は**読まれない**。

## 8. ライブの予約（`live_reservations`）

| 列 | 扱い |
|---|---|
| （開催回, 会員） | UNIQUE。キャンセル後の再予約は同じ行 |
| `status` | reserved（席を使う）/ canceled / attended / no_show / host_canceled（0-10） |
| `reserved_at` | NOT NULL |
| `reminded_at` | 0-11 |
| `canceled_at` / `attended_at` | 表示 |
| `verification_key` / `settings` | **読まれない** |

- 自分の予約（`/my-live-reservations`）・名簿・出欠・リマインド（24 時間以内に始まる `reserved` で `reminded_at IS NULL`）・チケットの返却（消費の記録が要る。0-11）。

## 9. 新システムの E2E（参考）

03（受講）・07（学習の流れ）・10・16（修了と修了証）・34（テスト）・51・52・60（修了証の台帳・書式・方針）・64（課題の提出と添削）・66（アンケート）・67・68（ライブの予約・チケット）・76〜80（コースの申込・期限・割り当て・進捗）。どれも demo の seed が前提。

## 10. まだ調べていないこと

- 今の移行ツールがどう移しているか（期限の時刻・`completed_at`・`updated_at`・修了証の連番・回答済みの記録・リマインドの記録・添削のキーなど）と旧のデータの実態は、手順 2・3 で突き合わせる。
