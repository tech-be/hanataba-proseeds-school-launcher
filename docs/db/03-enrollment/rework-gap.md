# 受講 — 移行仕様と今の移行ツールの差分

移行の見直しの手順 4（[進捗](../rework-progress.md)）。[移行仕様の 0 章](migration-spec.md#0-見直し2026-10-26-決定)（決定は 0-2）と、今の移行ツール・文書・school-launcher との差分。手順 5 でこの順に直す。

**school-launcher の migration は要らない。** 使う列（`lesson_progress.updated_at`、`learning_path_enrollment_courses.prev_*`、`certificate_settings.serial_format`、`submissions.status` / `submission_feedbacks.result` の値）は `584026af` にすべてある。

## 1. 移行ツール（`migrator/steps/`）

| # | 直すもの | 直す先 | 今 | 直したあと |
|---|---|---|---|---|
| G1 | 修了日（Q1） | `enrollment/rights.py` `_fold` | `completed_at = NULL` | 削除されていない受講の行（`ull.del_chk = 0`）の `lesson_complete_date` を入れる。時刻は同じ日の最後のユニットの完了日時、無ければその日の 0 時（JST）。同じ (会員, 講座) に受講の行が複数あれば最も新しい修了日 |
| G2 | 直接付与もある組の LPEC（Q3） | `enrollment/learning_paths.py` `LearningPathEnrollmentCoursesStep` | `prev_recorded = FALSE` | 同じ (会員, 講座) に商品なしの生きている権限があれば、`prev_recorded = TRUE`、`prev_status` / `prev_expires_at` に直接付与だけを畳んだ状態と期限（`rights.fold_period` を流用）。263 組 |
| G3 | 最終学習日時（Q4） | `enrollment/progress.py` | 指定なし（移行した日時） | `updated_at = GREATEST(update_date, complete_date)` |
| G4 | 削除済みの受講の行の下の記録（Q5・Q12） | `enrollment/progress.py` `extract` / `transform` | `lesson_progress` に入れる（新で完了に数えられる） | 入れずに一覧に出す（理由「受け皿なし」。新は `deleted_at` を読まない）。(会員, ユニット) の重複は生きている受講の行を優先する。**アンケートの回答がある記録は残す**（2 件） |
| G5 | 削除済みのユニットの記録の `deleted_at`（Q5） | `enrollment/progress.py` | `ulu.update_date` | `unit.update_date`（ユニットを削除した日時） |
| G6 | 修了証の番号の文字列と書式（Q7） | `enrollment/certificates.py` `CertificatesStep`・`CertificateSettingsStep` | `serial_text` = 数字だけ、`serial_format` は既定の `padded` | `serial_text` = `No.` ＋発行日（JST、`YYYYMMDD`）＋番号、`certificate_settings.serial_format = 'date_prefixed'` |
| G7 | 課題の提出の状態（Q10） | `enrollment/results.py` `SubmissionsStep` | `reviewed` / `submitted` | 旧の `ulu.progress_status`（課題）から: 評価待 → `submitted`、公開待 → `under_review`、評価済 → `graded`、再提出 → `returned`。同じユニットの古い提出で評価済みのものは `returned`。評価日時があるのに評価待のままの最新の提出は `graded`（手順 5 で見つけた旧データ 1 件） |
| G8 | 添削の結果（Q10） | `enrollment/results.py` `SubmissionFeedbacksStep` | `reviewed` | 評価済＋修了（`learning_status = 1`）→ `pass`、評価済＋学習中 → `fail`、再提出 → `needs_resubmission`。古い提出の添削は `needs_resubmission` |
| G9 | 開催側の中止の予約（Q13） | `billing/tickets.py` `_status` | `host_canceled` | `canceled`（`settings.stop_chk = 1` は今のまま残す）。席を解放する扱いは変わらない |

## 2. 補正データ（`fixups/`）

| # | 直すもの | 中身 |
|---|---|---|
| F1 | 合格点の丸め（Q9。02 の Q9 を変える） | `fixups/content.py` `pass_percent` を `ceil` から `floor` に。`fixups text` を流し直して、`overrides.csv` の合格点の行（70 件）を入れ替える |

## 3. 確認（`verify`）

| # | 中身 |
|---|---|
| V1 | `spec_checks` に `enrollment_spec` を足す: E-01〜E-05、P-01、R-01〜R-03、C-01〜C-03、Q-01・Q-02、A-01・A-02、S-01〜S-03。E-02 は「旧の修了日がある組に `completed_at` がある」、Q-02 は食い違いを例外として件数で出す（6 件を期待）、E-03 は例外の件数を出す（14 件） |
| V2 | `spec_checks` に `billing_spec`（V-01・V-02）を足す。billing を流せるようになるまでは飛ばす（理由を出す） |
| V3 | `legacy_checks` の受講の突き合わせを直す: 学習の記録の対象（G4 で除いた行を数えない）、課題の状態（G7・G8）、予約の状態（G9。今は `host_canceled` を期待している）、修了証の `serial_text`（G6） |

## 4. 単体テスト（`tests/`）

| # | 中身 |
|---|---|
| T1 | G1〜G9 の変換と一覧に出す行 |
| T2 | F1（`tests/test_fixups_content.py` の丸めの期待値） |
| T3 | V1〜V3。`tests/test_live_content.py` の `host_canceled` の期待を直す |

## 5. E2E

| # | 中身 |
|---|---|
| E1 | `e2e/enrollment.spec.ts`（新規）: E-06・E-07・P-02・P-03・R-04・C-04・C-05・Q-03・A-03・A-04・S-04。V-03 は billing を流せるまで保留。テスト用の会員に、修了した会員・課題を提出した会員・アンケートに回答した会員を足す（`prepare_e2e_users.py`） |

## 6. 文書

| # | 中身 |
|---|---|
| D1 | `migration-spec.md` の 1〜3 章、`review.md`、`breakdown.md`（修了日・学習の記録・課題の状態・修了証の番号・予約の状態） |
| D2 | `../02-content/migration-spec.md` の Q9 と `fixups/content.py` の説明（`floor` に変えた理由: 満点 100 点以下なら旧の判定を保てる） |
| D3 | `../not-migrated-summary.md`（G4 で増える行） |
| D4 | `../open-questions.md` に、修了証の無い修了者 14 件が新しい番号になることを載せる（Q8） |
