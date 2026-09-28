# 受講 — 突き合わせ

[受講の内訳](breakdown.md) の対応表と **1対1で対応**する。内訳の行それぞれに `###` 見出しが1つあり、
**順序も内訳と同じ**。ひな形は [00-template/review.md](../00-template/review.md)。

- 観点（テーブル / カラム / 型 / 性質）と深刻度（高 / 中 / 低）の定義は [README.md](../README.md#突き合わせの4つの観点)
- **「内容」は問題点だけ、「修正方法」はどう直すかだけ。** 修正方法が `未決:` で始まるものは**実装前に閉じるべき論点**
- 本文中の「ステージング実測」は 2026-09-18 のダンプで `tenant_id = 10`（ReCADemy）に絞った値

> **[移行の原則](../00-template/review.md#移行の原則)に従う。** 対象外のデータ以外はすべて移行し、
> 受け皿が無ければ追加し、元の構造を維持する。

---

## E1 受講権限

### `payment_item_lesson_authority` → `enrollments`

`payment_item_lesson_authority` (18列) → `enrollments` (11列) ／ ローカルデータ数 7,462 / C ／ ステージング実測 6,966件（4,289組）

講座の受講権限。**`user` 経由でテナントを絞る**（自身は `tenant_id` を持たない）。
**商品（`payment_item`）で絞ってはいけない** — `item_id` が NULL の付与が半分近くを占める（下表）。

| 旧カラム | 新カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|---|:--:|---|---|
| `(user_id, item_id, lesson_id)` | `(user_id, course_id)` | **性質** | **高** | **粒度が違う。** 旧は商品×講座で、同じ商品が複数講座を売り、同じ講座が複数商品から売られる。実測 3,684 行が 2,246 組に重なる | **lw2 自身の解決規則に従う。** `LessonModel::1804` の受講可否判定が `GROUP BY user_id, lesson_id` で畳み、期限は `MAX()` を取っている。**同じ規則で寄せる**（独自に決めない） |
| `cancel_chk` tinyint | — | **性質** | **高** | **名前に反してキャンセルフラグではない。** 全 INSERT 箇所（`PaymentAuthorityModel` の5か所）で**作成時に定数を書き込んでおり、UPDATE する箇所が存在しない**。実測 1=3,064 / 0=620 は「どの購入経路で作られたか」を表す | **`status = 'canceled'` に写さない。** 受講可否は `del_chk = 0` と期間で決まる。元の値は A8 の `settings` に残す |
| `payment_item.is_auto_extension` ＋ `payment_application.is_cancel` | `status` / `expires_at` | **性質** | **高** | **自動継続の権限は期限を見ない。** lw2 の判定は `PA.is_cancel IS NULL` だけで（`PaymentModel:383`）、`authority_end_date` が過去でも受講できる。**権限行だけを読むと、いま受講できている人を失効扱いにする**（実測 249組） | **商品のモードと申込の解約状態を一緒に読む。** 未解約の自動継続は `status = 'active'` / `expires_at = NULL`、全部解約済みなら `revoked`（`expired` ではない）。元の期限は A8 の `settings` に残す |
| `del_chk` | `status` | 性質 | 中 | **これが実質の取り消し。** 実測 828件（畳んで 273組） | `del_chk = 1` → `status = 'revoked'`。**`canceled` という値は無い**（`enrollment_statuses` は `active` / `expired` / `refunded` の3値だったので、A10 で `revoked` を足した） |
| `authority_start_date` | `enrolled_at` | 型 | 低 | 開始日。実測 NULL 0件 | そのまま移す |
| `authority_end_date` / `payment_authority_end_date` | `expires_at` **1列** | 性質 | 中 | **2つの期限が1列に畳まれる。** 実測はどちらも NULL 0件 | 受講期限は `authority_end_date`、決済側の期限は A8 の `settings` に残す。**畳んで捨てない** |
| `authority_end_date`（100年後） | `expires_at` **TIMESTAMP** | **性質** | **高** | **`TIMESTAMP` の上限は 2038-01-19。** 旧は無期限を100年後の日付で表しており（実測 最大 2126-09-16、2038超が 151件）、**そのまま入れると実 INSERT で `Incorrect datetime value` になる** | **無期限（NULL）に寄せ、元の日付を A8 の `settings` に残す。** 110件は `no_limit_chk` も立っているが、残り 41件は立っていない（最短でも 2049-12-01 で実質無期限） |
| `no_limit_chk` / `payment_no_limit_chk` | — | カラム | 中 | **無期限フラグ。** 実測それぞれ 110件。`expires_at` に NULL を入れるだけでは「無期限」と「未設定」が区別できない | A8 の `settings` に残す。**`expires_at` は無期限なら NULL** |
| `remote_chk` | — | カラム | 低 | リモート PC の利用可否（実測 39件）。リモート PC は [コンテンツ C4](../02-content/review.md#c4-リモート-pc) 側 | A8 の `settings` に残す |
| `item_id` | — | **性質** | **高** | **どの商品で買ったかが落ちる。** 新環境に商品の概念があるのは課金（4）で、`enrollments.provider_payment_id` は決済 ID であって商品ではない | A8 の `settings` に旧 `item_id` を残し、**課金（4）の移行後に紐付け直す** |
| `item_id` **NULL** | `source` | **性質** | **高** | **商品に紐づかない権限が 3,282行（2,306組、全体の47%）ある。** `authority_key` も `application_id` も空で、購入を経ずに直接入った付与。開始日・終了日は入っており、lw2 の受講可否判定（`LessonModel::1804`）は商品を見ないので**他と同じに扱われている** | **`payment_item` を INNER JOIN で絞ると丸ごと落ちる。** テナントの絞り込みは `user` 側で行い、商品は LEFT JOIN で添える。`source` は `admin`（管理者付与）にする |
| `application_id` | — | カラム | 低 | 申込との紐付け。実測 NULL 3,510 / 3,684（95%） | 同じく A8 の `settings` に残す |
| `authority_key` / `edit_date` / `edit_user` | — | カラム | 低 | 付与のキーと編集者 | A8 の `settings` に残す |
| — | `source` **NOT NULL** + FK | 性質 | 中 | 旧に対応する列が無い | **商品に紐づく行は `purchase`、紐づかない行は `admin`。** `manual` という値は存在しない（`purchase`/`subscription`/`free`/`admin`/`marketplace`）。ライブの受け皿講座も `admin` を使うので、**区別は `course_id` で行う** |
| — | `subscription_id` / `provider_payment_id` | カラム | 低 | 決済との紐付け | **課金（4）が未移行なので NULL**。移行後に埋める |

**まとめ**: 受け皿が無い列 8 / 変換規則が要る列 6 / **高 5 件**

> **「他テナントの講座を指す権限 807行」は誤りだったので取り下げる。** 参照先が `tenant_id = 0` の
> 行を別テナントのものと読み違えていた。**共有講座**（lw2 は講座をテナント間で共有できる）であって、
> このテナントが参照している以上、移すのが正しい。いまは
> [`SourceDatabase.shared_lessons`](../../../migrator/db/source.py) が拾う。

### `user_learning_lesson` → `enrollments`（母集合の判断）

`user_learning_lesson` (19列) → `enrollments` ／ ローカルデータ数 35,532 / C ／ ステージング実測 24,484件（23,956組）

会員が講座の学習を始めた時点で作られる記録。**受講権限とは別の表**で、桁が2つ違う。

| 旧カラム | 新カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|---|:--:|---|---|
| `(user_id, lesson_id)` | `(user_id, course_id)` | **性質** | **高** | **学習実績の大半は「無料講座」で、権限行を持たないのが旧環境でも正常。** `LessonModel::1363` の受講可否は「権限がある **OR** その講座が有料ユニットを持たない／表示中の商品で売られていない」の2分岐で、**実測 235講座のうち権限が要るのは 71件だけ**。権限なし×学習実績ありの 22,833組のうち 21,161組（93%）は無料講座で、旧環境でも権限行は無い | **母集合は権限側（`payment_item_lesson_authority`）。** 学習実績は `enrollments` の母集合にしない。ただし**無料講座 164件は新環境では `enrollments` が無いと開けない**ので、扱いを 1-1 で決める |
| `lesson_start_date` / `lesson_end_date` | `enrolled_at` / `expires_at` | 性質 | 中 | 学習の開始・終了で、権限の期間とは別物 | **使わない**（母集合は権限側）。無料講座ぶんを作る場合だけ `enrolled_at` に使う |
| `lesson_complete_date` | `completed_at` | 型 | 低 | 講座の修了日。実測 180件 | **母集合が権限側でもこの列は使う**（該当する組の `enrollments.completed_at` に入れる） |
| `finish_unit_num` / `finish_unit_percent` / `finish_unit_duration` | — | カラム | 中 | **講座単位の進捗率が落ちる。** 新環境は `lesson_progress`（ユニット単位）から都度計算する作り | 都度計算できるので**移さない**。ただし旧の値と一致しない可能性があるので、cutover 後に照合する |
| `total_learning_count` / `recent_learning_time` / `recent_learning_unit_id` | — | カラム | 低 | 学習回数・最終学習日時・最後に見たユニット | A9 の `lesson_progress` 側に最終学習日時の受け皿が無い。**`settings` を持たない表**なので、要るなら列を足す |
| `require_chk` / `skill_unit_tab_status` / `block_open_status` | — | カラム | 低 | 必須受講フラグ・タブ状態・ブロック開放状態 | **UI の状態**。移さない |
| `del_chk` | `status` | 性質 | 低 | 実測 4,250件（17%） | `canceled` に写す（母集合に採用する場合） |

**まとめ**: 受け皿が無い列 8 / 変換規則が要る列 3 / **高 1 件**

> **期限切れは正常な状態。** 権限 1,874組（削除除く）のうち **1,603組（86%）が `authority_end_date` 切れ**。
> 旧環境でもその講座は開けないので、`expires_at` をそのまま移すのが忠実。**期限を延ばさない。**

## E2 学習履歴

### `user_learning_unit` → `lesson_progress`

`user_learning_unit` (11列) → `lesson_progress` (8列) ／ ローカルデータ数 19,009 / C ／ ステージング実測 7,209件

ユニットごとの学習状況。**`user_learning_lesson` 経由でテナントを絞る**（自身は `tenant_id` を持たない）。

| 旧カラム | 新カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|---|:--:|---|---|
| `progress_status` tinyint | — | **性質** | **高** | **ユニット種別ごとに同じ数値が別の意味を持つ。** `unit_learning_progress_master` が `(progress_id, unit_type_id)` で引く作りで、`2` はテストなら「受験中」、アンケートなら「回答済」、レポートなら「評価待」、集合研修なら「出席希望」（`UserLearningConstants`）。**新環境に受け皿が無く、畳むと意味が消える** | **A9 で `lesson_progress.progress_status` と `settings` を追加する。** 旧の値と、そのときのユニット種別を対にして残す |
| `progress_status`（`unit_type_id = 1` 講義） | — | **性質** | **高** | **定数ファイルに定義が無い。** 実測は講義 6,083件のうち `2` が 4,946 / `1` が 1,137 で、**`learning_status` と相関しない**（4通りすべて出現） | **意味が確定するまで畳まない。** 値をそのまま A9 に残し、[確認事項](../open-questions.md)に上げる |
| `learning_status` tinyint | `completed_at` | 性質 | 低 | **修了フラグ。** 実測で `1` の 4,895件は `complete_date` がすべて非 NULL、`0` の 2,314件はすべて NULL で**完全に一致する** | `1` → `complete_date` を `completed_at` に入れる。`0` → NULL |
| `complete_date` | `completed_at` | 型 | 低 | 修了日時 | 上記のとおり |
| `score` | — | カラム | 低 | ユニットの得点。実測は 7,209件中 13件のみ | **テストの得点は E3 の `quiz_attempts.score` が持つ。** 重複するので移さない |
| `suspend_data` | `last_position` | 性質 | 中 | **SCORM の中断データ。** 実測 3,147件。新の `last_position` は動画の再生位置を想定した列で、形式が違う | **そのまま入れない。** 動画の再生位置として解釈できる場合だけ `last_position` に入れ、それ以外は A9 の `settings` に原文で残す |
| `del_chk` | — | カラム | 低 | 実測 147件 | **削除済みも移す**（[移行の原則](../00-template/review.md#移行の原則)の1）。A9 の `deleted_at` に写す |
| `(user_id, unit_id)` | UNIQUE | 性質 | 中 | 実測で 76件の重複がある（同じ会員・同じユニットに複数行） | **UNIQUE は緩めない。** どれを残すかを `update_date` の新しい順で決め、落ちた行を一覧に出す |
| `user_learning_unit_log` | — | 性質 | 低 | 進捗の更新履歴（19,009 → 33,998行） | **純ログとして移さない**（→ [対象外 B](#b-方針として移行しないもの)） |

**まとめ**: 受け皿が無い列 4 / 変換規則が要る列 4 / **高 2 件**

## E3 テスト受験

内訳: [breakdown.md](breakdown.md) の同名の節

### `user_learning_test` → `quiz_attempts`

`user_learning_test` (13列) → `quiz_attempts` (9列) ／ ETL段 L4 ／ ローカルデータ数 697,444 / C（**recademy 実測 1,128件**）

| 旧カラム | 新カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|---|:--:|---|---|
| `test_score` **tinyint(4)** / `sum_score` / `total_score` | `score` int / `max_score` int | **性質** | **高** | **3列のうちどれを使うかで点数が壊れる。** `test_score` は tinyint（最大127）、`sum_score` が実点数、`total_score` が満点。**`test_score` が百分率なら `max_score` と単位が合わない** | **実装で確定**（`UserLearningLessonModel::setUserLearningMark`）。
`sum_score` = **獲得点**（正解した設問の `question_score` の合計）→ `score`。
`total_score` = **満点**（出題された設問の `question_score` の合計）→ `max_score`。
`test_score` = `(獲得点 * 100) / 満点` の**百分率で、派生値**。合否も
`$testPass = ($myScore >= $passScore)` と**獲得点で判定**しており、百分率は使っていない。
**`test_score` は移行しない**（新環境で `score` / `max_score` から出せる） |
| `test_pass`（合否） | — | **カラム** | **高** | **合否を入れる列が無い。** 新は `score >= passing_score` で都度判定するため、**合格点を後から変えていた場合に過去の合格が不合格になる** | `quiz_attempts.passed` を追加し、**当時の判定結果をそのまま移す**（→ A1） |
| `user_learning_unit_id` | `user_id` + `quiz_id` | 性質 | 中 | 旧は中間テーブル経由、新は直結 | `user_learning_unit` を解決して user と quiz を引き当てる。**[受講](review.md) の進捗が先に入っている必要がある** |
| `finished_chk` | `status` | 性質 | 中 | 完了フラグ → 3値への振り分け規則が要る | `completed` / `abandoned` に振り分ける |
| `test_time`（受講時間） | — | カラム | 低 | 所要時間を入れる列が無い | A1 の `quiz_attempts.duration_sec` を追加して移す |
| `test_start_time` / `test_end_time` | `started_at` / `completed_at` **timestamp** | 型 | 中 | **`timestamp` 列なのでセッション TZ で UTC 変換される** | JST naive → UTC に変換してから書く（区分共通） |
| — | 業務的な一意キーなし | テーブル | 中 | **冪等性は決定論 ULID だけが担保**（ETL設計 §5-4） | 採番の入力（entity 名）を変えない。**変えると二重投入になる** |

**まとめ**: 受け皿が無い列 2 / 変換規則が要る列 5 / **高 2 件**

### なし → `quiz_attempt_statuses` / `quiz_attempt_event_kinds` / `quiz_attempt_events`

**旧に対応テーブルなし。** マスタ2件は migration で投入する。`quiz_attempt_events` は旧に対応データが無く、空で始める。

---

## E4 テスト設問別回答

内訳: [breakdown.md](breakdown.md) の同名の節

### `user_learning_test_sub` → `quiz_answers` / `quiz_answer_selected_options`

`user_learning_test_sub` (12列) ／ ETL段 L4 ／ ローカルデータ数 **10,705,972** / C

> **区分最大のテーブル。** 投入時間とバッチサイズを事前に見積もる。

| 旧カラム | 新カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|---|:--:|---|---|
| `question_answer` text | `quiz_answer_selected_options.option_id` | **性質** | **高** | **「どの選択肢を選んだか」を持つ専用列が旧に無い。** 候補は `question_answer` text のみで列コメントも空。**格納形式が分からないと変換規則が書けない** | **実装で確定**（`UserLearningLessonModel` 1302行ほか）。
**パイプ `|` 区切りの選択肢番号**で、正解列 `question.answer` と同じ形式。
採点は `explode('|', ...)` した集合同士を突き合わせており（記述式 `question_type_id=3` だけは
正解候補に含まれるかで判定）、実データも `2` / `4` / `1` のような番号だった。
**分割して `quiz_options` の並び順と突き合わせる** |
| `question_pass`（正誤） | — | **カラム** | **高** | **正誤の結果を入れる列が無い。** 新は `quiz_options.is_correct` から都度計算するため、**採点基準を後から変えると過去の正誤が変わる** | `quiz_answers.is_correct` を追加し、**当時の判定結果をそのまま移す**（→ A2） |
| `question_score`（配点） | `quiz_questions.points` | 性質 | 中 | 回答ごとの配点 → 問題ごとの配点へ。`test_sub.score_per_question` との整合が要る | [コンテンツ A8](../02-content/review.md#c5-テスト定義) の出題条件を移したうえで、条件ごとの配点と突き合わせる |
| `option_order`（選択肢の表示順） | — | カラム | 中 | **どの順で選択肢が出たかを入れる列が無い**ので、回答の再現ができない | A2 の `quiz_answers.option_order` を追加して移す |
| `sort_no` / `pre_question_pass` | — | カラム | 低 | 出題順・前回正誤を入れる列が無い | A2 にまとめて移す |

**まとめ**: 受け皿が無い列 4 / 変換規則が要る列 2 / **高 2 件**

---

## E5 テスト中断・再開

内訳: [breakdown.md](breakdown.md) の同名の節

### `user_learning_test_update` / `user_learning_test_sub_update` → なし

ローカルデータ数 815,895 / 2,212,972 / C

**該当テーブルなし。** 受験と回答の更新履歴。

| 旧カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|:--:|---|---|
| テーブル全体 | テーブル | 中 | **履歴ではなく「受験中の作業データ」だった。** `insertUserLearningTestUpdateData()` が採点時に `user_learning_test` / `user_learning_test_sub` へコピーしており（コメントも「ユーザーテスト実施中履歴」）、**過去の受験はすべて本テーブルに反映済み** | **例外: 移行しない**（受験中の一時データ）。ただし **cutover 時点で中断中の受験がある会員はデータを失う**ので、件数を確認し、あれば再受験してもらう合意を取る |

**まとめ**: 受け皿が無い列 — / 高 0 件

### `user_learning_test_suspend_data` → なし

`user_learning_test_suspend_data` ／ ローカルデータ数 326 / C

**該当テーブルなし。** 受験を中断したときの作業データ（中断時刻・累計受験時間・回答済み設問数）。

| 旧カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|:--:|---|---|
| テーブル全体 | テーブル | 中 | **`user_learning_test_update_id` を参照しており、上の2件と同じ「受験中のデータ」。** 中断時刻・累計受験時間・回答済み設問数を持つ（SCORM ではない） | **例外: 移行しない**（受験中の一時データ）。上の2件と同じ扱い |

**まとめ**: 受け皿が無い列 — / 高 0 件

---

## E6 課題提出・添削

内訳: [breakdown.md](breakdown.md) の同名の節

### `user_learning_report` → `submissions` / `submission_feedbacks`

`user_learning_report` (24列) ／ ETL段 L4 + L9 ／ ローカルデータ数 40,098 / C（**recademy 実測 4,963件**）

| 旧カラム | 新カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|---|:--:|---|---|
| `eval_save_file_name1..5` | `submissions.object_key` varchar(512) **1本** | **性質** | **高** | **5本 → 1本に畳むと、2本目以降の提出ファイルが消える**（実測で2本目以降を使う提出は4,963件中2件） | `submission_files` を新設し、**5本とも1行ずつ移す**（→ A3）。畳まない |
| `eval_disp_file_name1..5`（元ファイル名） | — | カラム | 中 | **アップロード時のファイル名を入れる列が無い**（`submission_feedbacks` にも無い） | A3 の `submission_files.file_name` に移す |
| `report_question_comment` | — | カラム | 中 | 設問ごとの添削コメントを入れる列が無い | A3 の `submission_feedbacks.question_comments`（json）に移す |
| `score` | `submission_feedbacks.score` | 性質 | 中 | **`submissions` ではなく添削側にあるため、添削が無い提出のスコアを持てない** | 添削が無い提出は `submission_feedbacks` を作らず、A3 で `submissions.score` を追加して移す |
| `submit_date` NULL可 | `submitted_at` datetime(3) **NOT NULL** | 型 | 中 | 未提出行を入れられない | **未提出行は移らない**（`submitted_at` の NOT NULL を外さない）。**「誰が提出していないか」は新環境に残らない**ので、件数を数えて規模を記録する |
| `evaluate_user_id` | `reviewer_id` **NOT NULL** | 型 | 中 | 評価者が未設定の行は `submission_feedbacks` を作れない | 評価者が NULL の行は添削行を作らない（提出だけ移す） |
| `user_report_evaltext` | `submission_feedbacks.body` | — | — | 対応あり | そのまま移す |
| `send_PC_chk` / `send_mobile_chk` | — | カラム | 低 | 通知設定を入れる列が無い | A3 の `submissions.settings` に移す |
| — | `submissions.body_text` | カラム | 低 | 旧は本文提出を持たない | 対応不要 |

**まとめ**: 受け皿が無い列 12 / 変換規則が要る列 6 / **高 1 件**

### なし → `submission_status_events`

**旧に対応データなし。** 提出状態の履歴で、空で始める。

---

## E7 アンケート回答

内訳: [breakdown.md](breakdown.md) の同名の節

### `enquete_answer` → `survey_responses` / `survey_answers` / `survey_answer_selected_options`

`enquete_answer` (10列) ／ ETL段 L4 ／ ローカルデータ数 388 / C（**recademy 単体では 232件**）

| 旧カラム | 新カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|---|:--:|---|---|
| `entity_type_id` 1/2/3 | — | **性質** | **高** | **2（ユニット）だけが移行でき、1（お知らせ 3件）と 3（レポート 149件）に受け皿が無い。** 232件中 152件（66%）が落ちる。**A4 の `entity_type` / `entity_id` を足しただけでは解決しない** — `survey_responses.lesson_id` が NOT NULL ＋ FK `survey_lessons` のままなので、ユニットに紐づかない回答は入る場所が無い | 下の「3種類は別物」を参照。**いまは type 2 だけ移している**（`entity_type = 'lesson'` 固定） |
| `enquete_type_id` = 3 | — | **性質** | **高** | **type 3 の149件はアンケートではなく「課題（レポート）の設問への回答」。** lw2 は課題の設問を `enquete` テーブルに持っており、`EnqueteModel:49` がアンケート一覧から `enquete_type_id != 3` で除外している。新環境の `submissions` は自由記述1本（`body_text` / `object_key`）で、**設問形式の課題を受ける器が無い** | 未決。**アンケート側に寄せるのではなく、課題側の受け皿を決める**（→ [確認事項](../open-questions.md)） |
| `answer` text (**JSON**) | `numeric_value` / `text_value` + 選択肢の中間表 | 性質 | 中 | JSON を展開する規則が要る（キーは `answer_<enquete_question_id>`） | ETL設計 §5-5 の規則で展開し、設問タイプごとに入れる列を変える |
| `enquete_reply_time` NULL可 | `survey_responses.submitted_at` **NOT NULL** | 型 | 中 | NULL 行を入れられない | **移らない**（[共通仕様 3.5.1](../../migration-spec.md#351-not-null--unique--外部キーに当たる行)）。代替値を入れるか許容するかは [移行仕様 1-1 #3](../open-questions.md) |
| `tenant_id` が無い | `survey_responses.tenant_id` NOT NULL | 性質 | 中 | **`enquete` と join しないとテナントが決まらない。** join を落とすと全73テナントが混ざる（棚卸しの 64,883件はこの誤り） | `enquete` と join して `tenant_id = 12` で絞る（区分共通の規則） |
| `suspended_chk` | — | カラム | 低 | 中断フラグを入れる列が無い | A4 の `survey_responses.suspended` を追加して移す |
| — | `anonymous_allowed` / `open_at` / `close_at` / `max_length` / `description` | カラム | 低 | 旧に対応なし | 既定値に任せる。対応不要 |

**まとめ**: 受け皿が無い列 1 / 変換規則が要る列 4 / **高 2 件**

#### `entity_type_id` の3種類は別物

**1つの表に3種類の回答が同居している。** 同じに扱えないので、行き先も別々になる。

| 旧 `entity_type_id` | `entity_id` が指す先 | 実測 | 新の行き先 | 状態 |
|---:|---|---:|---|---|
| 2 ユニット | `user_learning_unit_id` | 80件 | `survey_responses`（`lesson_id` = アンケートユニット） | **移行済み**（77件。残り3件は下の注記） |
| 3 レポート | `user_learning_report_id` | 149件 | 課題側（`submissions`）。**受け皿が無い** | 未決 |
| 1 お知らせ | `news_user_id` | 3件 | お知らせ側（[サポート機能](../05-support/review.md) O16）。**受け皿が無い** | 未決 |

> **type 2 の80件のうち3件は移らない。** 回答が記録している `enquete_id` を、
> そのユニットがもう参照していない（定義を差し替えた／ユニット自体がアンケートではない）。
> **旧データの不整合**なので移行ツールでは解決できない。

### なし → `survey_submission_log`

**旧に対応データなし。** 提出ログで、空で始める。

---

## E8 ライブ予約・出欠

内訳: [breakdown.md](breakdown.md#e8-ライブ予約出欠)

### `live_lesson_reserve` → `live_reservations`

`live_lesson_reserve` (16列) → `live_reservations` (11列) ／ ETL段 L5 ／ ローカルデータ数 18,041 / C ／ ステージング実測 32件

そのまま対応: 4列（`tenant_id`、`user_id`、`reserve_date`→`reserved_at`、`cancel_date`→`canceled_at`）

| 旧カラム | 新カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|---|:--:|---|---|
| （行の重複） | **UNIQUE `uk_lr_occurrence_user (occurrence_id, user_id)`** | **テーブル** | **高** | **旧は同じ会員が同じ開催回に複数行持てる**（キャンセル後の再予約）。ステージング実測で **32件中 4組8行**が重複し、**いずれも片方が `cancel_chk = 1`** | 未決: **どの行を残すか**を運営と決める。**ツールは重複した組をどれも移さない**（[共通仕様 3.5.1](../../migration-spec.md#351-not-null--unique--外部キーに当たる行)）ので、決めないとその会員の予約が丸ごと消える。**「キャンセルされていない最新の1行」を残すのが素直**だが、キャンセル履歴が失われる |
| `stop_chk`（中止フラグ） | `live_lesson_occurrences.canceled_at` | **性質** | **高** | **予約ではなく開催側の中止。** `live_reservations.status = 'canceled'` に入れると**受講者都合のキャンセルとして記録され、実績が誤る**。ステージング実測2件 | **予約から開催回へ持ち上げる。** `stop_chk = 1` の予約がある開催回の `canceled_at` を埋め、**予約側には「開催中止で不成立」を表す status を新設する**（→ A5）。`live_reservation_statuses` の既存4値では表現できない |
| `cancel_chk` + `attendance_chk` + `stop_chk` | `status` varchar(32) + FK | 性質 | 中 | **3フラグを1列に畳む。** 組み合わせによっては情報が落ちる（キャンセル済みかつ出席、など） | `stop_chk=1` → A5 の新値、`cancel_chk=1` → `canceled`、`attendance_chk=1` → `attended`、いずれでもない**過去の開催回** → `no_show`、**未来の開催回** → `reserved`。**元の3フラグは A5 の `settings` に残す**。ステージング実測は キャンセル10 / 中止2 / 出席3 |
| `verification_key` varchar(200) | — | カラム | 中 | **出席認証キーが落ちる**（QR・コード入力での出席確認）。ステージング実測は全件が32文字で埋まっている | A5 の `live_reservations.verification_key` を追加して移す。**認証コードの平文ではなく照合用のランダム値**なので、[抽出の禁止列](../../migration-spec.md)には当たらない |
| `recent_access_date` | — | カラム | 低 | 最終アクセス日時が落ちる | A5 の `settings` に移す |
| `change_reserve_id` / `base_reserve_id` | — | カラム | 低 | **振替予約の前後関係**が落ちる | **ステージング実測0件**。本番ダンプで件数を確認し、あれば A5 に列を足して移す |
| `reserve_date` datetime **NULL可** | `reserved_at` datetime(3) **NOT NULL** DEFAULT CURRENT_TIMESTAMP(3) | 型 | 中 | **NULL の行は既定値に落ちて「移行実行日時」が予約日時になる。** 黙って入ってしまうので検出しづらい | **NULL を明示的に検出して止める。** ステージング実測は0件。本番で出たら `regist_date` で代替するかを決める（→ [migration-spec 1-1](../open-questions.md)） |
| `attendance_date` | `attended_at` datetime(3) | — | — | 対応あり | JST naive → UTC |
| `live_lesson_date_id` | `occurrence_id` char(26) + FK | 性質 | 中 | 親の引き当て | [`live_lesson_date`](../02-content/../02-content/review.md#live_lesson_date--live_lesson_occurrences) で採番した ULID に読み替える。**削除済みの開催回にぶら下がる予約が3件**ある |
| — | `reminded_at` datetime(3) | **性質** | **高** | **旧に対応列が無く、NULL のまま移すと「未送信」になる。** ステージング実測では**予約のある開催回32件がすべて過去**なので、**cutover 直後に過去分のリマインドが再送される恐れがある** | 未決: **過去の開催回の予約は `reminded_at` を埋める**（cutover 日時か開催日時）。運営に「再送されないこと」を確認してもらう。詳細は [L04 リマインド](#l04-リマインド) |
| `regist_date` / `update_date` | `created_at` / `updated_at` | — | — | 対応あり | |

**まとめ**: 受け皿が無い列 4 / 変換規則が要る列 5 / **高 3 件**

#### L04 リマインド

**専用テーブルが旧にも新にも無い**ため、[データ種別対照表](../data-type-mapping.md) の L04 はここに含める。

| 旧 | 新 | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|---|:--:|---|---|
| メール送信ログ（`mail_send_user` ほか）＋ `live_lesson_date.mail_send_chk` | `live_reservations.reminded_at` / `email_send_logs` | **性質** | **高** | **粒度が違う。** 旧は送信ログに1通ずつ残るが、新は予約1行に「送信済み時刻」を1つ持つだけ。**過去の送信履歴を再生する先が無い** | `reminded_at` は**「移行時点で送信済みか」を表す真偽値としてしか使えない**と割り切る。送信ログそのものは運営区分（06、未コミット）の `email_send_logs` 側で扱う |

**まとめ**: 受け皿が無い列 — / **高 1 件**（上の `live_lesson_reserve` のまとめには含めない）

### `config_live_lesson` → `live_lesson_occurrences.cancel_closes_at`

`config_live_lesson` (7列) → 計算して `live_lesson_occurrences.cancel_closes_at` へ ／ ETL段 L5 ／ ローカルデータ数 64 / C ／ ステージング実測 1件（`tenant_id = 10`）

| 旧カラム | 新カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|---|:--:|---|---|
| `ticket_cancel_day` / `ticket_cancel_time` | `occurrences.cancel_closes_at` datetime(3) | 性質 | 中 | **テナント単位の設定 → 開催回ごとの絶対時刻へ展開する。** 設定を変えても過去の開催回に遡らない形になる | `starts_at − ticket_cancel_day 日 − ticket_cancel_time 時間` で計算する。**ステージングの実値は 1日 0時間**（ETL設計 §5-6 は14日前としているが、**それは別のデータセットの値**）。本番ダンプで取り直す |
| `ticket_cancel_chk` tinyint(1) | — | 性質 | 中 | **キャンセル自体の可否フラグ**が落ちる。`0` のとき `cancel_closes_at` に何を入れるかが決まらない | `ticket_cancel_chk = 0` なら **`cancel_closes_at` を `starts_at` と同値にする**（= 開催直前までキャンセル不可の表現にならない）か NULL にするかを決める。ステージングは `1` |
| `valid_chk` | — | カラム | 低 | ライブ機能そのものの有効フラグ | **テナント設定**なので基盤の `tenants.settings` に移す |

**まとめ**: 受け皿が無い列 2 / 変換規則が要る列 1 / 高 0 件

### なし → `live_reservation_statuses`

`live_reservation_statuses` (10列) ／ マスタ ／ シード済み4値

| 新カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|:--:|---|---|
| `code` | 性質 | 中 | **`reserved` / `canceled` / `attended` / `no_show` の4値しかなく、「開催側の中止で不成立になった予約」を表せない** | 値を1つ追加する（→ A5）。`occupies_seat = 0` / `is_terminal = 1` |

---

# チケット

## E9 修了証の設定（バッジは対象外）

内訳: [breakdown.md](breakdown.md) の同名の節

### `config_certificate` → `certificate_settings`

`config_certificate` (5列) → `certificate_settings` (12列) ／ ETL段 L7 ／ ローカルデータ数 3 / C

> **修了証も移行ツールで実装する。** `cmd/import-certificates/main.go`（Go）が同じことをしているが、**役割分担はせず、こちらで実装する**。既存ツールは対応表 CSV を入力に取る作りで参考になるが、**使わない**。**二重に投入しないよう、既存ツールを流さない運用にする。**

| 旧カラム | 新カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|---|:--:|---|---|
| `issuer_name` varchar(200) | `issuer_name` varchar(200) **NULL 可** | 性質 | 低 | 旧が NULL の行がある | **NULL のまま移す。** 新環境は `issuer_name` が NULL なら `tenants.name` を使う仕様（`20260728113418_add_certificate_ledger.sql` の列コメント）。**表示名がテナント名でよいかだけ運営に確認する** |
| — | `tax_rate_percent` decimal(5,2) **NOT NULL** | カラム | 中 | 旧 `config_certificate` に税率が無い | 課金の `tax` テーブル（K09）から取る。**期間別税率の問題（K09 の高）と同じ論点** |

**まとめ**: 受け皿が無い列 — / 変換規則が要る列 2 / 高 0 件

### `certificate` → `certificate_layouts`

`certificate` ／ ローカルデータ数 15 / C

| 旧カラム | 新カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|---|:--:|---|---|
| 任意 HTML のレイアウト | `certificate_layouts`（固定レイアウト） | 性質 | 中 | **任意 HTML のアップロードが新環境に無い**（実測で recademy は既定レイアウトのみ） | 既定レイアウトに寄せる。**recademy は既定のみなので実害は無い**が、独自 HTML を使っていたら運営に確認する |

**まとめ**: 受け皿が無い列 — / 高 0 件

### `certificate_no` → `certificate_serial_formats`

`certificate_no` ／ ローカルデータ数 10 / C

| 旧カラム | 新カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|---|:--:|---|---|
| `certificate_no`（次番号） | `certificate_settings.serial_next` | 性質 | 中 | **引き継がないと採番が衝突する**（ステージング実測は 7。発行済みは No.4〜6） | 旧の次番号をそのまま `serial_next` に入れる。**cutover 後に発行して重複しないことを確認する** |

> **`config_certificate` が空でも `certificate_no` だけあることがある。** ステージングがまさにそれで、
> 文面・発行者名の設定は 0 行、採番カウンタだけ 1 行。**設定行が無いからと `certificate_settings` を
> 作らないと、採番が 1 に戻って既存の証書と衝突する**ので、カウンタ側だけでも行を作る。

**まとめ**: 受け皿が無い列 — / 変換規則が要る列 1 / 高 0 件

### `badge_item` → なし（移行対象外）

`badge_item` (8列) ／ ローカルデータ数 91 / C

> **移行対象外**（2026-09-28 決定。→ [対象外](../06-out-of-scope/breakdown.md#決定で対象外にしたもの)）。以下は判断の前に調べた内容で、**移行はしない**。

`digital_badges` は**付与された1枚**を表す表（`user_id` / `course_id` / `issued_at` がいずれも NOT NULL）で、**定義は入らない**。バッジは定義と付与実績で置き場所が分かれる。

> **バッジの付与実績は lw2 の DB ではなく、外部のバッジシステムにある。**
> lw2 は `library/BadgeApi.class.php` で API を叩いており（接続先は `application.ini` の
> `api.badge.baseUrl`）、会員ごとの取得状況を読み書きする口が揃っている
> （`getBadges($tenantId, $userId, ...)` / `getBadgeUserIds()` / `updateUserBadge()` /
> `deleteUserBadge()` ほか）。**今回のダンプの範囲外**なので、移行するならそのシステムから
> 別途データを受け取る必要がある。

| 旧カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|:--:|---|---|
| **付与記録が lw2 の DB に無い** | **テーブル** | **高** | **付与実績は外部のバッジシステムにあり、lw2 の DB には存在しない。** `badge_item` は `(tenant_id, entity_id, item_type)` で**「この講座はバッジ対象か」を引くだけの定義**で（`ApiLessonModel::chkBadge`）、`user_id` を持つ表も付与行を書く処理も lw2 側には無い。**新環境の `digital_badges.user_id` NOT NULL に入れる値が、ダンプの中には無い** | **定義は移す**（`badge_item` → `digital_badges` の対象指定）。**付与実績は、バッジシステムからデータを受け取れるかを先に確認する**（[移行仕様 1-1](../open-questions.md)）。受け取れない場合にはじめて、修了実績からの再発行を検討する |
| `item_type` / `entity_id` | 性質 | 中 | **ポリモーフィック参照。** 旧 `lesson` は**講座**、`unit` は**ユニット**で、新環境では `courses` と `lessons` に分かれる（実測 49 / 12）。**新旧で名前が入れ替わっているので取り違えやすい** | A11 の `badge_definitions` に `course_id` / `lesson_id` を両方持たせ、**どちらか一方だけを埋める**（CHECK で担保） |
| `reference_item_id` | カラム | 中 | **外部のバッジシステムが払い出した ID。** `BadgeController:838` が `$badgeApi->putBadge()` の戻り値 `$json['ID']` をそのまま書いており、`BadgeItemModel:143` は `AS badge_id` で読み出している。**`badge_item` を指す自己参照ではない**（実測 4件の値 771〜774 は `badge_item` に存在しない）。**付与実績を外部から受け取るときの突き合わせキー** | A11 の `badge_definitions.external_badge_id`（INT、FK なし）に旧の値のまま移す。`digital_badges` 側にも同じ列を足す |

**まとめ**: 移行対象外（A11 は取り下げ）

### なし → `course_certificate_policies` / マスタ4件

**旧に対応テーブルなし。** 講座ごとの発行条件と、イベント種別・失効理由のマスタ。migration で投入する。旧に失効の概念が無いため、失効理由は移行では使わない。

---

## E10 修了証の発行（バッジは対象外）

内訳: [breakdown.md](breakdown.md) の同名の節

### `user_certificate` → `certificates`

`user_certificate` (8列) → `certificates` (20列) ／ ETL段 L7 ／ ローカルデータ数 3 / C（**recademy 実測 3件**）

> **`entity_id` は講座 ID ではない。** `certificate_type = 1` のとき中身は
> **`user_learning_lesson_id`**（`LessonController:3668` の `$entityId = $userLearningLessonId`）で、
> 講座を引くには `user_learning_lesson` をたどる。`lesson_id` と取り違えると
> `certificates.course_id` が参照先なしになり**全件落ちる**。`certificate_type = 2` のときは `item_id`。

| 旧カラム | 新カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|---|:--:|---|---|
| `certificate_type` = 2（商品単位） | — | **性質** | **高** | **`certificates.course_id` が NOT NULL なのでコース単位のみ。** 商品単位の修了証（O26）を作れない | **`course_id` は NULL 可にしない**（緩めない方針）。**商品単位の修了証は移らない**（ステージング0件。本番で件数を数える）。`product_id` の列だけは追加し、コース単位の修了証に商品を紐づけられるようにする（→ A6） |
| `certificate_no` | `serial_no` + `serial_text` varchar(64) **NOT NULL** | 性質 | 中 | `serial_text` が旧に無い | `certificate_settings` の `serial_prefix` / `serial_digits` / `serial_format` から組み立てる |
| — | `layout_code` **NOT NULL** + FK | カラム | 中 | 旧に対応なし | 既定レイアウトを入れる |
| — | `period_start` / `period_end` / `amount_excl_tax` / `amount_currency` / `subject_name` | カラム | 中 | 旧 `user_certificate` に無い | `enrollments` と `payments` から引いて埋める。**[受講](review.md) と [課金](../04-billing/review.md) が先に終わっている必要がある** |
| `revoked_at` / `revoked_by` / `revoke_reason_code` | — | カラム | 低 | 旧に失効の概念が無い | NULL でよい。対応不要 |

**まとめ**: 受け皿が無い列 — / 変換規則が要る列 4 / **高 1 件**

### なし → `certificate_events` / `digital_badges` / `digital_badge_events`

**旧に対応データなし**。`certificate_events` は空で始める。**バッジは移行対象外**なので、`digital_badges` / `digital_badge_events` も空で始める（[`badge_item` → なし](#badge_item--なし移行対象外)）。

---

---

## 新環境に追加するテーブル・カラム

**受け皿が無いものは、原則として新環境に追加して受ける。** 「移行しない」は例外で、その都度理由を書く。

> **migration に落とした形は [マイグレーション対象](schema-additions.md)。** 当てる順序・DDL・ロールバックの注意はそちらにある。

| # | 追加するもの | 旧環境の対応 | 変更が必要な機能 |
|---|---|---|---|
| **A1** | `quiz_attempts.passed` BOOLEAN NULL / `duration_sec` INT NULL | `user_learning_test.test_pass` / `test_time` | ・**当時の合否を表示に使う。** 新は `score >= passing_score` で都度判定するため、**合格点を後から変えると過去の合格が不合格になる**<br>・**終了判定は `test_end_time` で見る**。`finished_chk` は lw2 が一度も書いていない（全件が「中断」になる） |
| **A2** | `quiz_answers.is_correct` / `option_order` / `sort_no` / `pre_question_pass` | `question_pass` / `option_order` ほか | ・**当時の正誤を表示に使う**（採点基準を変えても過去が変わらないように）<br>・選択肢の表示順が無いと**回答の再現ができない** |
| **A3** | `submission_files`（提出ファイルを行に展開）/ `submissions.score` / `settings` / `submission_feedbacks.question_comments` | `eval_disp_file_name1..5` / `eval_save_file_name1..5` / `report_question_comment` | ・**5本 → 1本に畳むと2本目以降が消える**（実測 4,963件中2件）<br>・添削が無い提出のスコアを `submissions` 側で持つ<br>・設問ごとの添削コメントの表示 |
| **A4** | `survey_responses.entity_type` / `entity_id` / `suspended` | `enquete_answer.entity_type_id` 1/2/3 ＋ `suspended_chk` | ・中断状態を移す先<br>・**これだけでは type 1/3 は移せない**（`lesson_id` が NOT NULL）。行き先は受け皿の設計から決め直す |
| **A5** | `live_reservations.verification_key` / `settings` ／ `live_reservation_statuses` に `host_canceled` | `verification_key` / `cancel_chk` + `attendance_chk` + `stop_chk` + `recent_access_date` | ・出席確認（QR・コード入力）<br>・**`stop_chk`（開催側の中止）を `canceled` に入れない。** 受講者都合のキャンセルとして記録される<br>・**振替予約（`change_reserve_id`）は実測0件**。本番で出たら A5 に列を足す |
| ~~**A11**~~ | ~~`badge_definitions`（バッジの定義）~~ | `badge_item` | **取り下げ**（2026-09-28 バッジは移行対象外） |
| **A6** | `certificates.product_id` | `payment_item` | ・**`product_id` に FK は張らない**（課金 4-2 が未移行）。移行後に埋める<br>・課金（4-2）の移行後に埋める |
| **A7** | `live_lesson_reviews`（ライブ単位のレビュー） | `live_lesson_review`（実測3件） | ・**`course_reviews` はコース単位**なので、受け皿 course に付けると**全ライブのレビューが1つの course に混ざる**<br>・`tenants` を RESTRICT で参照するので `cleanupDemoData` に列挙が要る |
| **A8** | `enrollments.settings` JSON NULL | `payment_item_lesson_authority` の `cancel_chk` / `no_limit_chk` / `payment_no_limit_chk` / `remote_chk` / `item_id` / `application_id` / `authority_key` / `payment_authority_end_date` | ・**`cancel_chk` を `status` に写さない。** 名前に反してキャンセルフラグではなく、作成時に定数が入るだけで UPDATE されない<br>・**無期限（`no_limit_chk`）は `expires_at = NULL` で表す。** ただし「未設定」と区別が付かないので元の値を残す<br>・`item_id` は課金（4）の移行後に商品と紐付け直す<br>・**`TIMESTAMP` の上限を超えた期限**（2038超、151件）は無期限に寄せ、元の日付を `legacy_expires_at_beyond_timestamp` に残す |
| **A10** | `enrollment_statuses` に `revoked`（取り消し） | `payment_item_lesson_authority.del_chk = 1`（実測 828行 → 273組） | ・**既存の3値では表せない。** `expired` は期間の満了、`refunded` は返金で、どちらも「運営が権限を取り下げた」とは別の軸<br>・`is_terminal = 1`（期限が来て戻るものではない） |
| **A9** | `lesson_progress.progress_status` VARCHAR(32) NULL / `settings` JSON NULL / `deleted_at` DATETIME(3) NULL | `user_learning_unit` の `progress_status` / `suspend_data` / `del_chk` | ・**`progress_status` はユニット種別ごとに意味が変わる**ので、値と種別を対で残す（同じ `2` がテストなら「受験中」、アンケートなら「回答済」）<br>・**講義（`unit_type_id = 1`）の値は定数ファイルに定義が無い。** 意味が決まるまで畳まない<br>・`suspend_data` は SCORM の中断データで `last_position`（動画の再生位置）とは形式が違う。解釈できないものは `settings` に原文で残す |

### 移行の対象外（移行できないもの / 移行しないもの）

#### A. 移行できないもの

| 対象 | なぜ移行できないか |
|---|---|
| `enquete_answer` のうち `enquete_reply_time` が NULL の行 | `survey_responses.submitted_at` が NOT NULL（[共通仕様 3.5.1](../../migration-spec.md#351-not-null--unique--外部キーに当たる行)）。**制約は緩めない** |
| `user_learning_report` のうち `submit_date` が NULL の行（未提出） | 同じく `submissions.submitted_at` が NOT NULL |
| `certificate_type = 2`（商品単位の修了証） | `certificates.course_id` が NOT NULL でコース単位のみ。**`course_id` は NULL 可にしない** |

#### B. 方針として移行しないもの

| 対象 | 理由 |
|---|---|
| テスト中断・再開の3テーブル（計300万行） | **受験中の作業データ。** 採点時に `user_learning_test` へコピーされる（採点処理の実装で確定）。**cutover 時点で中断中の受験だけが失われる**ので、件数を確認して合意を取る |
