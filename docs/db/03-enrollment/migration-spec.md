# 受講 — 移行仕様

区分 **3 受講**（受講権限 / 学習履歴 / テスト結果 / 課題提出 / アンケート回答 / ライブ予約 / 修了証）を
移行ツールでどう流すか。共通の方針は [migration-spec.md](../../migration-spec.md)、
突き合わせは [review.md](review.md)、追加するスキーマは [schema-additions.md](schema-additions.md)。

> **コンテンツ（2）が先。** 実績は定義に紐づく（`quiz_attempts.quiz_id` /
> `submissions.assignment_id` / `survey_responses.lesson_id` / `live_reservations.occurrence_id`）。

---

## 0. 見直し（2026-10-26 決定）

移行の見直しの手順 3（[進捗](../rework-progress.md)）。[テスト仕様書](test-spec.md)のケースが通るように、旧のデータ（ステージング `tenant_id = 10`）を確かめて移し方を決める。1 章以降は、決まったあと手順 5 で直す。

### 0-1. 旧のデータで分かったこと

| ケース | 分かったこと |
|---|---|
| E-02 修了日 | 旧の講座の修了は `user_learning_lesson.lesson_complete_date`（DATE）。削除されていない受講の行（`ull.del_chk = 0`）で修了日がある組は **90**。新の規則（公開中のレッスンをすべて完了）で計算すると **45**。差の 29 件はすべて資料（種別 6）を含む講座（旧は資料を修了に数えない）。権限の無い無料講座の修了 155 件は、受講登録の受け皿が無い（D3） |
| E-03 | 修了日が受講開始より前のものが **14 件**（権限を後から付け直したため） |
| E-04・P-01 | 有効（`active`）な受講登録 169 件は、すべて有効な LPE がある。LPE の値は新の CHECK の範囲内。コースと**直接付与の両方**を持つ組が **263**（新でコースを取り消すと受講登録ごと取り消される。`learning_path_enrollment_repo.go:190-202`）。`revoked` なのに有効な LPE がある組が 1 |
| R-01 | 旧の `ulu.update_date` は完了だけを書く処理で更新されず、`update_date < complete_date` の行が **3,172** |
| R-02 | 旧の削除は 2 種類。ユニットの削除（`ulu.del_chk = 1`、190 行）と、管理者による受講の記録の削除（`ull.del_chk = 1`。下のユニットの行は `del_chk = 0` のまま）。後者の **1,912 行（うち完了 1,452）**を今は生きた記録として入れていて、新で完了に数えられる |
| R-04 | 資料のレッスンは新では進捗の分母に入る（02 の Q3 で受け入れ済み）。旧の進捗率とは合わない |
| C-01 | 採番 `certificate_no` = 7、発行済み 3 件（番号 4〜6）。通る |
| C-02 | 旧の表示は `'No.' . date('Ymd') . 番号`。日付は**表示した日**で、旧の「番号の文字列」は一つに決まらない。今は数字だけを入れている |
| C-03 | 移す講座 325 件のうち修了証を出さない 303 件に `issue = FALSE` がある。通る。修了証を出す講座の修了者で修了証が無い **14 件**は、新で PDF を取ると 7 以降の番号が付く |
| Q-01 | 受験 371 件、移る 338 件。開始時刻なし・得点 > 満点・満点 0 はいずれも 0。通る |
| Q-02 | 新の合否は受験ごとの得点・満点と、今の合格点（割合）で計算する。旧の `test_pass` と比べると、02 の Q9（`ceil`）では **10 件**食い違う（丸め 5・受験後に合格点が変わった 4・旧でも合格できない 1）。`floor` なら **6 件** |
| A-01〜A-03 | 旧の状態は `ulu.progress_status`（1 未提出 / 2 評価待 / 3 評価済 / 4 再提出 / 5 公開待）。合否の列は無く、評価者が `learning_status` を修了 / 学習中で付ける。最新の提出の内訳: 評価待 183・評価済＋修了 25・評価済＋学習中 8・再提出 8・公開待 0。課題の定義が無くて移らない提出 69 |
| A-04 | 添削のファイル 5 件。今は `object_key` NULL、ファイル名は `submission_feedback_files` |
| S-02・S-03 | 生きている回答 85 件は、すべて回答したユニットが完了。R-02 で削除済みの受講の行の記録を除くと、**2 件**で完了の記録が無くなる。S-03 は影響なし |
| V-01 | 予約 32 件、未来の予約 0。開催側の中止（`stop_chk = 1`）2 件はどちらも削除済みの回で、02 の Q14 で回を移さないため移らない。ステージングで `host_canceled` になる行は 0 |

### 0-2. 決めたこと（2026-10-26。すべて推奨で決定）

| # | ケース | 案 | 推奨 |
|---|---|---|---|
| Q1 | E-02 修了日 | (a) 削除されていない受講の行の `lesson_complete_date` を `completed_at` に入れる（90 件）。時刻は同じ日の最後のユニット完了日時、無ければその日の 0 時（JST）<br>(b) ユニットの完了から計算する（45 件） | **(a)**。旧の画面と修了証は修了日で判定していた。テストは「旧の修了日がある組に `completed_at` がある」に読み替え、新の規則との差（資料）を文書に書く |
| Q2 | E-03 | (a) そのまま入れ、14 件を例外として記録する<br>(b) `fixups` で受講開始日に合わせる | **(a)**（値を作り替えない） |
| Q3 | E-04・P-01 | (a) 直接付与もある 263 組は、LPEC に `prev_recorded = TRUE` と直接付与だけを畳んだ状態・期限を入れる<br>(b) 今のまま | **(a)**。コースを取り消しても旧と同じく直接付与の受講が残る。`revoked` で有効な LPE がある 1 件は手順 6 で個別に確かめる |
| Q4 | R-01 | `updated_at = GREATEST(update_date, complete_date)` | 推奨 |
| Q5 | R-02 | (a) 削除済みの受講の行の下の記録（1,912 行）は入れず、理由を付けて `not-migrated.csv` に出す（新は `deleted_at` を読まない＝制約の衝突として扱う）。(会員, ユニット) の重複は生きている行を優先する<br>(b) 今のまま入れる | **(a)**。ただし**アンケートの回答がある記録は残す**（Q12）。削除済みのユニットの記録（190 行）は `deleted_at` 付きで入れる（値は `unit.update_date`） |
| Q6 | R-04 | テストの期待値を「資料を除いて旧と一致」にする | 推奨 |
| Q7 | C-02 | (a) `serial_text` = `No.` ＋発行日（JST、`YYYYMMDD`）＋番号（新の `date_prefixed` の書式）<br>(b) 数字だけ（今のまま） | **(a)**。旧の画面とは日付が一致しないことがある（表示した日で出していた）と文書に書く |
| Q8 | C-03 | 今のまま。修了証の無い修了者 14 件は、PDF を取ると新しい番号になる | 推奨（運営に伝える。`open-questions.md` に載せる） |
| Q9 | Q-02 | (a) 02 の Q9 の式を `floor` に変える（食い違い 10 → 6）<br>(b) `ceil` のまま | **(a)**（02 に差し戻す）。残る 6 件は旧の合否を `passed` 列に残し、例外として記録する |
| Q10 | A-01〜A-03 | 提出の状態: 評価待 → `submitted`、公開待 → `under_review`、評価済 → `graded`、再提出 → `returned`、古い提出で評価済み → `returned`<br>添削の結果: 評価済＋修了 → `pass`、評価済＋学習中 → `fail`、再提出 → `needs_resubmission` | 推奨。提出だけで修了にする設定の 141 件は旧でも評価待なので `submitted`。課題が無くて移らない 69 件は今のまま一覧に出す |
| Q11 | A-04 | 添削の `object_key` は NULL のまま。ファイル 5 件は L9（ファイルの移送）で置く | 推奨（NULL で画面が落ちないかは手順 6 の E2E で確かめる） |
| Q12 | S-02 | 回答がある (会員, ユニット) の記録は、Q5 の例外として残す（2 件） | 推奨 |
| Q13 | V-01 | (a) 中止は `canceled` にし、`settings.stop_chk = 1` で区別する<br>(b) 新に `host_canceled` を足す | **(a)**（新のアプリは直さない）。ステージングは 0 件。本番の件数は数える |

### 0-3. 暫定対応の本番案

| 暫定対応 | 今 | 本番の案 |
|---|---|---|
| 添削者が分からない添削を代理講師に倒す（`enrollment/results.py`） | 代理講師 | 今のまま（02 の代理講師の本番案に従う） |
| 権限の無い無料講座の修了 155 件 | 移さない（受講登録が無い） | 運営の回答待ち（`open-questions.md` D3。② なら受講登録と一緒に修了日も入れる） |

**確かめていないこと**: 新のアプリを動かしての確認（手順 6）、本番のデータでの件数、新の「公開中のレッスン」の判定に資料を含めるか（02 の Q3 の前提に従った）。

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
| **コースの購入・割り当てを移す** | school-launcher はコース（`learning_paths`）＝旧の販売商品とし、購入・割り当てを `learning_path_enrollments` に1行ずつ持つようになった（`20261012014810` / `20261019004848` / `20261019042710`）。**旧の購入・付与（`authority_key`。会員1人・商品1つ）を1行にする**（ステージング 2,351 件）。渡した講座は `learning_path_enrollment_courses`。商品を経ない権限（`item_id` が NULL）はコースの購入にならない。**流すのは課金の `billing.2`（決済の後）**。`payment_id` が決済を指すため | 2026-10-22 |
| 取り消された購入・付与の状態 | 全行が `del_chk = 1`、または自動継続が全部解約済みのものは、**申込を経たもの（購入・無料）は `refunded`、管理者の付与は `revoked`**。旧に返金の概念は無いが、新は `revoked` を管理者の取り消しに限っている。期限切れは状態にしない（新は `expires_at` で判定する） | 2026-10-22 |
| **自動継続（月額）も期限で切る** | 未解約の自動継続も、受講登録・コースの購入の `expires_at` に旧の `authority_end_date`（いま払っている1か月の終わり）を入れる。**無期限にしない。** 旧の受講可否は `authority_end_date >= 今日`（`LessonModel::1363`）で、自動継続の期限は毎日のバッチ（`AuthorityCheckBatch`）が1か月ずつ延ばしている。無期限にすると、cutover 後に継続課金を止めても受講が止まらない（[sync-issues B6](../school-launcher-sync-issues.md)）。**本番は、旧のバッチが動いた後のダンプで流す**（古いダンプでは、未解約でも期限切れで入る） | 2026-10-23 |
| 商品を経た受講登録は `via_learning_path` | 商品に紐づく権限を含む組の `enrollments.via_learning_path` を TRUE にする（`20261012174140`）。新はこの受講登録に講座ごとのリモートPC 対象を効かせず、コースの購入の `remote_pc_enabled`（旧の権限の `remote_chk`）とコースの設定（旧の商品の `remote_chk`）で決める。**旧の判定（権限 AND 商品）と同じになる** | 2026-10-22 |
| **バッジは移行対象外** | 定義（`badge_item`）も付与実績（外部のバッジシステム）も移さない。`badge_item` は `EXCLUDED_TABLES` に載せ、読もうとすると止まる（→ [対象外](../06-out-of-scope/breakdown.md#決定で対象外にしたもの)） | 2026-09-28 |

### 1-4. 本番ダンプ受領後に確認すること

- **振替予約**（`live_lesson_reserve.change_reserve_id` / `base_reserve_id`）。ステージング実測0件。値は `live_reservations.settings` に残している。**多ければ列を足すかを決める**
- **受講権限の重複の実態**。ステージングは 6,966行 → 4,289組（2,677行が重複）。本番で桁が変わるなら畳み方を再検討する
- **`user_learning_unit` の重複**（ステージング 153組 495行。新しい1行を残し、342行は一覧に出さずに捨てる）と `suspend_data` の形式（実測 4,630件）

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
| `badge_item` | 62 | **61** | 移さない（対象外） |

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
             user（全会員）                → enrollments（ライブの受け皿講座。lw2 に元データ無し）
enrollment.2 学習履歴        user_learning_unit            → lesson_progress
enrollment.3 テスト結果      user_learning_test            → quiz_attempts → quiz_answers
                                                           → quiz_answer_selected_options
enrollment.4 課題提出        user_learning_report          → submissions → submission_feedbacks
                                                           → submission_feedback_files（添削のファイル）
enrollment.5 アンケート回答  enquete_answer                → survey_responses → survey_answers
                                                           → survey_answer_selected_options
                                                           → survey_submission_log（回答済み）
enrollment.6 ライブ予約      live_lesson_reserve           → live_reservations
             live_lesson_review                            → live_lesson_reviews
enrollment.7 修了証          lesson.certificate_id         → course_certificate_policies
             config_certificate + certificate_no → certificate_settings（serial_next）
             user_certificate                              → certificates → certificate_events
                ↓
[課金 billing.2 の決済の後に流す、受講のデータ]
             payment_item_lesson_authority（商品あり。authority_key ごと）
                                                           → learning_path_enrollments → learning_path_enrollment_courses
```

> **コースの購入・割り当ては受講のデータだが、課金の `billing.2` で流す**（2026-10-22）。`learning_path_enrollments.payment_id` が
> 決済（`payments`）への外部キーで、決済は `billing.2` で入る。コース（`learning_paths`）はコンテンツの `content.5` で入っている。

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
`submission_files`**（2026-09-30 からは `submission_feedback_files` も）を足すこと。`tenants` を参照するので `make check-seed-cleanup` が要求する。

---

## 3. データ移行仕様

### 3.1 抽出（extract）

**`tenant_id` を持たない表が多い。** 親と join して絞る — 落とすと他テナントの行を拾う。

| 旧テーブル | 絞り込みの経路 |
|---|---|
| `payment_item_lesson_authority` | `user.tenant_id`。`payment_item` / `payment_application` は LEFT JOIN で添える（商品で絞ると `item_id` が NULL の付与が落ちる） |
| `user_learning_unit` | `user_learning_lesson` → `user.tenant_id`（`fetch_joined(via=...)`。講座側で絞ると共有講座を通じて他テナントの会員を拾う） |
| `user_learning_lesson` | `user.tenant_id` |
| `user_learning_test` / `user_learning_test_sub` / `user_learning_report` | `user_learning_unit` → `user_learning_lesson` → `user.tenant_id` |
| `enquete_answer` | `enquete.tenant_id`（共有アンケートを含む）。会員は `entity_id` → `user_learning_unit` から引く（お知らせ・レポートへの回答は移していないので引かない） |
| `live_lesson_reserve` | 自身の `tenant_id`。開催回（`live_lesson_date`）が引けない行は一覧に出す |
| `user_certificate` | `user.tenant_id` |

### 3.2 変換（transform）

**受講権限（3-1）**

- **母集合は `payment_item_lesson_authority`。** 権限が要るのは 235講座中 71件で、残りは無料講座
- **lw2 の解決規則に従う。** `LessonModel::1804` が `GROUP BY user_id, lesson_id` で畳み、
  期限は `MAX(authority_end_date)` を取っている。**独自に決めない**
- `status` は次の順で決める（`enrollment_statuses` に `canceled` という値は無い）
  - 畳んだ行が**すべて `del_chk = 1`** → `revoked`
  - 自動継続の商品で**すべて解約済み** → `revoked`
  - 期限（`MAX(authority_end_date)`）が過去 → `expired`、それ以外 → `active`。
    **自動継続の未解約も同じ**（2026-10-23。旧の毎日のバッチが期限を1か月ずつ延ばしているので、
    期限には「いま払っている1か月の終わり」が入っている。以前は無期限にしていた）
- **`cancel_chk` は使わない** — 名前に反して取り消しではなく、毎月の自動延長の対象から外す印
  （買い切りなどは作成時から 1、自動継続は解約後にバッチの `updateCancelChk` が 1 にする）。受講できるかは期限で決まる
- `source` は、畳んだ行のどれかが**商品に紐づけば `purchase`**、どれも紐づかなければ **`admin`**
  （`item_id` が NULL の付与。`purchase` にすると売上集計に乗る）。`manual` という値は存在しない
- `no_limit_chk = 1` が1行でもあれば `expires_at = NULL`。`settings` には畳んだ結果の `unlimited`（真偽値）だけを残す。
  **旧の `no_limit_chk` / `payment_no_limit_chk` / `payment_authority_end_date` の値そのものは現状は残していない**
  （`payment_*` の2列は読むが書かない。実装が無い。2026-10-02 の確認）。自動継続（未解約）の組は
  `settings.subscription = true`（cutover 後に延長・取り消しの対象を探すのに使う）。`edit_date` / `edit_user` は読んでいない
- `completed_at` は**旧の講座の修了日**（削除されていない `user_learning_lesson` の `lesson_complete_date`。0-2 Q1）。
  時刻は同じ日の最後のユニットの完了日時、無ければその日の 0 時（JST）。受講開始より前の修了日（ステージング 15 件）も
  作り替えない（Q2）。受講登録の無い無料講座の修了（146 組）は受け皿が無い（`open-questions.md` D3）
- `provider_payment_id` は、畳んだ行のうち決済として移す申込の最も新しいものの決済 ID（課金 04 の暫定の規則 P10）。`subscription_id` は NULL
- **ライブの受け皿講座には全会員を受講登録する**（`enrollment.live_host_enrollments`、2026-09-24 決定）。
  lw2 に元データが無い行で、`user` の全行（ステージング 3,155名。削除済みの会員 503名を含む）を
  `source = 'admin'` / `status = 'active'` / 期限なしで入れる。受け皿講座を作らないテナントでは作らない
- **期限切れはそのまま移す。** ステージングで移した 4,286組のうち 3,713組が期限切れ（ほかに active 199組 / revoked 374組。2026-10-23 の判定）だが、旧環境でも開けない。**期限を延ばさない**。
  期限切れのうち 323組は未解約の自動継続で、ステージングのダンプ（2026-09-18 取得）で旧のバッチが止まっていたため。
  うち 228組は申込の無い自動継続の権限で、期限が 2022-11 のまま延長されておらず、旧でも開けない（以前は無期限で入れていた）

**学習履歴（3-2）**

- `completed_at` は **`learning_status = 1` のときだけ** `complete_date` を入れる
  （実測で両者は完全に一致する）
- `updated_at` は旧の最終学習日時 **`GREATEST(update_date, complete_date)`**（完了だけを書く処理は `update_date` を
  更新しない。0-2 Q4）
- **管理者が削除した受講の記録（`user_learning_lesson.del_chk = 1`）の下の行は移さない**（理由「受け皿なし」で一覧に出す。
  新は `deleted_at` を読まず完了に数える。ステージング 2,239 行）。**アンケートの回答がある行だけは残す**（2 行。0-2 Q5・Q12）
- ユニットの削除（`user_learning_unit.del_chk = 1`）の行は `deleted_at` 付きで入れる。値は `unit.update_date`
  （ユニットを削除した日時）
- `progress_status` は**ユニット種別と対にして残す**（例: `quiz:2`）。
  種別ごとに同じ数値の意味が違うため、値だけでは復元できない
- **`last_position` は常に NULL。** `suspend_data` は `settings` に原文で残す（動画の再生位置として解釈することはしていない）
- **(会員, ユニット) の重複は、削除されていない受講の行を優先し、`update_date`（無ければ `complete_date`）の新しい1行だけを残す。**
  残りは一覧に出さずに捨てる（ステージング 153組 495行 → 342行）

**課題の提出・添削（3-4）**（0-2 Q10）

- 提出の状態は旧の課題の状態（`user_learning_unit.progress_status`。学習の行に 1 つだけで、最新の提出のもの）から:
  評価待 → `submitted`、公開待 → `under_review`、評価済 → `graded`、再提出 → `returned`。
  同じユニットの古い提出は、評価済みなら `returned`、評価されていなければ `submitted`。
  **評価した日時があるのに評価待のままの最新の提出**（2017 年の旧データ。ステージング 1 件）は `graded`
- 添削の結果: 評価済＋修了（`learning_status = 1`）→ `pass`、評価済＋学習中 → `fail`、再提出・古い提出 → `needs_resubmission`
- 添削の `object_key` は NULL。添削のファイルは `submission_feedback_files` に旧のファイル名で入れる（L9 で置く。Q11）

**修了証（3-7）**（0-2 Q7）

- `serial_text` は **`No.` ＋発行日（JST、`YYYYMMDD`）＋番号**（例 `No.202511106`）。`certificate_settings.serial_format = 'date_prefixed'`。
  旧の画面は表示した日の日付で出していたので、旧の画面とは日付が合わないことがある

**ライブの予約（課金 billing の `ReservationsStep`）**（0-2 Q13）

- 開催側の中止（`stop_chk = 1`）は **`canceled`**。`settings.stop_chk = 1` で受講者のキャンセルと区別する（新の画面は `host_canceled` を扱えない）

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

#### 一覧に出ずに移らない行

`out/not-migrated.csv` には出ないが、移行ツールが黙って飛ばす行がある（2026-10-02 の確認）。

| 対象 | 扱い | ステージング |
|---|---|---:|
| `user_learning_unit` の重複（同じ会員・同じユニット） | 新しい1行だけを残す | 342行 |
| `user_learning_report` のうち、`user_learning_unit` / `user_learning_lesson` が引けない行 | 提出を作らない | — |
| `enquete_answer.answer` の JSON が壊れている行、`answer_<数字>` 以外のキー、設問が引けないキー | 設問別回答を作らない | — |
| `enquete_answer` のうち `entity_type_id` が 1（お知らせ）/ 3（レポート）の行 | 回答を作らない（受け皿が無い。`survey_responses.lesson_id` が NOT NULL。2026-10-02 に受け皿 `survey_entity_responses` を検討したが取り下げた） | 226件（このテナントの会員の回答。お知らせ 3 / レポート 223。レポートのうち 149件はこのテナントのアンケート、74件は共有のアンケート） |
| `user_certificate` のうち `certificate_type = 2`（商品単位） | 移さない | 0件 |
| `user_certificate` のうち `user_learning_lesson` が引けない行 | 移さない（ログに警告だけ出す） | 0件 |

**2026-10-02 から一覧に出すようにしたもの**（以前はこの表に載っていた）:

- `user_learning_test_sub` のうち、移らない受験にぶら下がる回答（「旧データの不整合」。ステージング 60件）と、出題条件（`test_sub_type_id = 2`）の問題・固定出題から一意に引けない問題の回答（「受け皿なし」。50件）は **`out/not-migrated.csv` に出す**。4,922件中 4,812件を移し、110件を一覧に出す

**削除済みの受験・提出は区別せずに移す。** `user_learning_test.del_chk` / `user_learning_report.del_chk` は使っておらず、
`quiz_attempts` / `submissions` に削除の印を書いていない（ステージングはどちらも0件）。

**コースの購入・割り当て（billing.2 で流す）**

- **1回の購入・付与 = 旧の `authority_key`**（会員1人・商品1つ。ステージング 2,351 件。キーの無い行は (会員, 商品, 申込) で代える）
- `source`: 申込なし → `admin`（管理者が商品単位で付与した権限）、申込が無料（`payment_type` 0 / 4）だけ → `free`、それ以外 → `purchase`
- `payment_id`: **決済として移した申込だけ**結ぶ（課金 04 の P3 / P4。無料・チケット払い・支払い不要は決済にならない）
- 期間（`enrolled_at` / `expires_at`）は受講登録と同じ規則（`rights.fold_period`）。ただし列は `datetime(3)` なので UTC を明示して書く。`TIMESTAMP` の上限を超える期限は、受講登録とそろえて無期限（NULL）にする
- `status`: 取り消し（全行 `del_chk = 1`・自動継続の全解約）は 購入・無料 → `refunded`、付与 → `revoked`。それ以外は `active`
- `remote_pc_enabled`: 生きている権限の行のどれかが `remote_chk = 1`
- 渡した講座（`learning_path_enrollment_courses`）: **削除済みの権限の講座も入れる**（取り消しは状態で表す）。**同じ (会員, 講座) に商品を経ない生きている権限（直接付与）があれば `prev_recorded = TRUE`**、`prev_status` / `prev_expires_at` に直接付与だけを畳んだ状態と期限（0-2 Q3。コースを取り消しても直接付与の受講が残る）。ほかは既定（`prev_recorded = FALSE`）

### 3.5 検証

- `verify --section enrollment` が OK になること。**移行元から作り直した行と全列で突き合わせる**ので、
  決定論 ULID の照合（`enrollments` は畳んだ組）もここに含まれる
- コースの購入・割り当ては課金の照合（`verify --section billing`）で見る: 旧の購入・付与ごとの漏れ・紛れ、コース・種類・取り消しの状態、渡した講座
- `enrollments.via_learning_path` が、商品を経た権限を含む組だけ TRUE であること（`verify --section enrollment`）
- 受講登録・コースの購入の期限が、旧の `authority_end_date` の最大値（日本時間の日付。自動継続も同じ。無期限の印か 2038-01-19 以降は NULL）と一致すること。
  未解約の自動継続で、移した時点で期限切れのものの件数を「（参考）」として出す（NG にしない）。**本番では 0 件に近いことを確かめる**（多ければダンプが古い）
- 再実行で 0 行（冪等）
- `enrollments.status` の期限切れ判定は実行時刻に依存する。**`run` の直後に `verify` を流す**
- `out/not-migrated.csv` の件数と理由が、1-1 で決めた内容と矛盾しないこと

---

## 未確定として残っているもの

- **無料講座の受講登録**（→ [確認事項](../open-questions.md)）。**3-1 の Step は権限側だけで書ける**ので着手は止まらない
- **講義の `progress_status` の意味**（定数ファイルに定義が無い）
- `certificates.product_id` は課金（4）の移行後に埋める（現状は移行ツールが書かない）
