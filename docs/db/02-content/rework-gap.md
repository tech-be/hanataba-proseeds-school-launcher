# コンテンツ — 移行仕様と今の移行ツールの差分

移行の見直しの手順 4（[進捗](../rework-progress.md)）。[移行仕様の 0 章](migration-spec.md#0-見直し2026-10-26-決定)（決定は 0-3）と、今の移行ツール・文書・school-launcher との差分。手順 5 でこの順に直す。

## 1. 移行ツール（`migrator/steps/content/`）

| # | 直すもの | 直す先 | 今 | 直したあと |
|---|---|---|---|---|
| G1 | 削除済みの講座・コース・課題の状態（Q1） | `courses.py` `_status_of`、`learning_paths.py` `_status`、`assignments.py` | `deleted` | `archived`。ライブ講座（`live_courses.py`）も同じ規則か確かめる |
| G2 | レッスンの種別（Q2） | `lessons.py` `UNIT_TYPES` | `quiz` / `assignment` / `document` / `discussion` / `skill_check` | `text`。旧の種別は `lessons.settings.legacy_unit_type` に残す。`CONTENT_NOT_YET_MIGRATED` の数え方も直す |
| G3 | 動画ではない storage の行（Q6） | `lessons.py` の講義の Step・`video_lessons` の Step | `video` ＋ `video_lessons`（`storage` に旧の URL） | 旧サーバーの HTML 教材・PDF・相対パス・p-movie のプレーヤーの URL などは **`text` にし、本文（`description`）に URL を載せる**。`video_lessons` は作らない。p-movie のトークン・YouTube は今のまま |
| G4 | 並び（Q4） | `lessons.py`（講座の中の採番） | 旧の `sort_no` のまま | 講座の中で「章 → `sort_no` → 旧 ID」の通し番号 |
| G5 | 削除済みの章（Q5） | `lessons.py` `ChaptersStep` | `deleted_at` 付きで入れる | 移さない（理由「移行対象外」で一覧に出す） |
| G6 | 無料公開（Q17） | `lessons.py` | `is_preview = FALSE` | `payment_unit = 0` なら `TRUE` |
| G7 | 設問が 0 件になるテスト（Q8） | `quizzes.py` | `quizzes` に入れる（設問 0 件） | 出題条件なし・テスト以外のユニットのテスト・問題の無い固定出題は**移さない**（一覧に出す） |
| G8 | カテゴリからのランダム出題（Q8） | `quizzes.py` | 出題条件（`quiz_question_rules`）だけ | **候補の問題をすべて `quiz_questions` に展開する**（出題条件・問題バンクも今どおり残す） |
| G9 | 出題数（Q10） | `quizzes.py` | 固定の設問をすべて入れる | 固定出題（type 0）は先頭の N 問だけ。ランダム出題（type 1）は全問 |
| G10 | 採点できない設問（Q11） | `quizzes.py` | 入れる | 選択肢 0 件の単一選択・正解の番号が範囲外は**移さない**（一覧に出す） |
| G11 | 配点の `or 1`（値の作り替え） | `quizzes.py` | 0 を 1 に変える | 旧の値のまま（該当 0 件） |
| G12 | アンケートの並び（Q13） | `surveys.py` | ページの中の `sort_no` | ページの順 → `sort_no` → ID の通し番号 |
| G13 | 削除済みの開催回（Q14） | `live_lessons.py` | `deleted_at` 付きで入れる | 移さない（一覧に出す）。その回の予約（受講の区分 03）も連鎖して一覧に出る |
| G14 | 講座のカテゴリ（Q16） | `courses.py` | 全体の `course_categories` に `lw2-…` のコードを作って `courses.category` に入れる | `courses.category` は NULL。`lw2-…` のコードは作らない。テナントのカテゴリ（`course_category_links`）は今のまま |
| G15 | テストの題（0-4。2026-10-26 に追加） | `quizzes.py` `QuizzesStep` | 空文字 | ユニット名（`unit.title` の前後の空白を除いたもの） |

## 2. 補正データ（`fixups/`）

| # | 直すもの | 中身 |
|---|---|---|
| F1 | 合格点（Q9） | `test.pass_score`（点）を割合に直す提案: `floor(合格点 × 100 ÷ 旧の満点)`（03 の Q9 で `ceil` から変えた）。満点は出題条件ごとに `min(N, 問題数) × 配点` の合計（G9 の出題数で数える）。旧でも合格できない（合格点 > 満点）ものは提案せず空欄 |
| F2 | 問題文・解説の HTML（Q12） | `question.question_text` / `answer_explanation` のプレーンテキスト化を提案（05 の `fixups text` を広げる）。`<img>` は画像の移送（L9）と一緒に決めるので、今は画像のタグを除いた文にする |
| F3 | アンケート（Q13） | 必須の添付の設問を任意にする提案、選択肢の重複に「（2）」などで区別を付ける提案 |
| F4 | コース（Q15） | 公開中で公開する講座が無いコースを無効にする提案、期間が 120 か月を超えるものを無期限にする提案 |
| F5 | 補正データの対象の表を広げる | `migrator/overrides.py` の `KEY_COLUMNS` に `test` / `question` / `enquete_question` / `payment_item` を足す |

## 3. 確認（`verify`）

| # | 中身 |
|---|---|
| V1 | `spec_checks` に 02 のデータの確認（C-01〜C-05・L-01〜L-05・V-01・V-02・Q-01〜Q-04・A-01・S-01・S-02・LV-01〜LV-04・P-01・P-02・P-04）を足す。V-01（動画の URL）・V-02（尺）は p-movie の規則が決まるまで NG のまま（理由を出す） |
| V2 | `legacy_checks` の 02 の突き合わせを、今回の変更（状態・種別・並び・出題数・移さない行）に合わせる |

## 4. 単体テスト（`tests/`）

| # | 中身 |
|---|---|
| T1 | G1〜G14 の変換と一覧に出す行 |
| T2 | F1〜F5 の提案（合格点の計算、HTML、アンケート、コース） |
| T3 | V1・V2 |

## 5. E2E

| # | 中身 |
|---|---|
| E1 | `e2e/content.spec.ts`（新規）: C-06・C-07・L-06〜L-08・V-03・Q-05・Q-06・A-02・S-03・LV-05・LV-06・P-03。テスト用の会員に、移した講座の受講登録のある会員を足す（`prepare_e2e_users.py`） |

## 6. 文書

| # | 中身 |
|---|---|
| D1 | `migration-spec.md` の 1〜3 章、`review.md` の合格点（「そのまま移す」は誤り）、`breakdown.md` |
| D2 | `../not-migrated-summary.md`（移さない行の件数） |
| D3 | `../open-questions.md` に運営への確認（p-movie の URL の規則、完了の条件が変わること、カテゴリの対応表） |
| D4 | `../school-launcher-sync-issues.md`（B1 動画・B3 カテゴリの現状） |

## 7. 受講の区分（03）への影響

テスト・開催回・章を移さなくなるので、それを指す受講の記録（テストの受験・解答、開催回の予約、学習の記録）は外部キーで連鎖して一覧に出る。件数は手順 6 で確かめ、03 の見直しでも扱う。

## 8. 手順 5 の順番

1. G1・G2・G5・G6・G14（講座とレッスンの変換）→ T1
2. G4・G12（並び）→ T1
3. G3（動画ではない行）→ T1
4. G7〜G11（テスト）→ T1
5. G13（開催回）→ T1
6. F1〜F5 → T2
7. V1・V2 → T3
8. E1
9. D1〜D4
