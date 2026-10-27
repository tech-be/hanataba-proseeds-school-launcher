# コンテンツ — 移行仕様

[コンテンツの内訳](breakdown.md) / [突き合わせ](review.md) と3点セット。**オンデマンド講座 / テスト・課題定義 / アンケート定義 / ライブ講座**を移すための手順。

- **根拠**: 旧⇔新の判断は [review.md](review.md)。**本書はそれを実装の手順に落としたもの**で、個別カラムの判断は突き合わせを正とする
- **全区分に共通する規則**（抽出の絞り込み / ULID / 日時 / 文字コード / 冪等性）は [移行ツール仕様書](../../migration-spec.md)。ここには**コンテンツ固有のことだけ**を書く
- **[移行の原則](../00-template/review.md#移行の原則)** に従う。対象外区分のデータ以外はすべて移し、受け皿が無ければ追加し、元の構造を維持する
- 新環境に足す DDL は [schema-additions.md](schema-additions.md)

> **前提**: **基盤（`foundation.*`）が終わっていること。** `courses.tenant_id` / `instructor_id` は `tenants` / `users` を参照し、教材の公開範囲は基盤で作るグループ・属性（A10 / A11）を参照する。
>
> **8区分で最大。** `user_learning_test_sub` が 1,070万行、`test_sub_question` 65万行。**投入時間とバッチサイズを事前に見積もる。** 中断・再開の3テーブル（計300万行）は**受験中の作業データなので移行しない**。

---

## 0. 見直し（2026-10-26 決定）

移行の見直しの手順 3（[進捗](../rework-progress.md)）。[機能仕様書](functional-spec.md)と[テスト仕様書](test-spec.md)のケースが通るように、移し方を見直す。件数はステージング `tenant_id = 10`（「共有」は、このテナントが使っている共有講座 90 件の分）。

### 0-1. 旧のデータで分かったこと（テスト仕様の「?」の答え）

| ケース | 旧のデータ | 結果 |
|---|---|---|
| L-03 ユニットの本文 | 短い説明（`unit.detail`）だけで HTML 0 件。**旧に「テキストのユニット」は無い** | 通る |
| L-05 drip | すべて 0 | 通る |
| Q-02 設問 | 本文が空 0 件、配点 0 は 0 件。**選択肢 0 件の単一選択 15 件・正解の番号が範囲外 2 件** | 一部 × |
| Q-03 合格点 | **旧の `pass_score` は「点」**（`UserLearningLessonModel.class.php:1237`。管理画面も「点」）。満点 100 のものは同じ値、それ以外の 70 件は割合と合わない。合格点 > 満点（旧でも合格できない）8 件 | × |
| Q-04 記述式 | 正解の候補は全件 1 つ（`|` 区切り 0 件） | 通る |
| Q-06 時間の制限 | 0 か 5 分以上（60 秒未満 0 件） | 通る |
| 問題文・解説 | **旧は HTML として表示していた。** 問題文 1,638 件・解説 1,087 件に HTML（`<img>` 約 325 件ずつ） | ×（タグが見える） |
| S-01 アンケートの並び | ページは ID 順、設問はページの中の `sort_no` 順。通し番号にしないと順が変わるのは 1 件 | × |
| S-02 アンケート | 必須の添付の設問 1 件、選択肢の重複 1 件 | × |
| LV-01 削除済みの開催回 | 817 件。**すべて過去**。予約のある回 2 件 | × |
| LV-02 開催回 | 終了 ≦ 開始 0 件、定員超え 0 件 | 通る |
| LV-04 リマインド | 未来の回の予約 0 件 | 通る（再送は起きない） |
| P-02 コース | 公開中なのに公開する講座が 1 件も無いコース 9 件 | × |
| 0-14 コースの期間 | 30 年・100 年の 2 件が新の上限（120 か月）を超え、**一覧の API 全体が 500** | × |
| V-01 動画 | p-movie の 40 字のトークン 3,247 件。storage の行は動画ではなく旧サーバーの HTML 教材 約 2,000 件・PDF・p-movie のプレーヤーの URL など。YouTube 5 件、Vimeo 0 件 | × |
| V-02 尺 | 旧に尺の列が無い | ×（NULL のまま） |
| L-04 並び | 同じ講座で `sort_no` が重なるレッスン 6 組。新は ID（ULID）の順になり、旧（`unit_id` の順）と変わりうる | × |
| C-05 削除済みの章 | 27 件。今の移し方では中のレッスンは前の章に付け直されて 0 件だが、新は空の見出しとして出す | × |
| C-03 カテゴリ | `courses.category` は旧のコード（`lw2-{テナント}-{id}`）。新の `/courses` の絞り込みは recademy の 6 つのコードを見るので合わない | × |
| テストの設問 0 件（Q-01） | 出題条件なし 20 件（旧でも受験すると例外）、アンケート・講義のユニットに付いたテスト 60 件（中身なし）、問題の無い固定出題 3 件、カテゴリからのランダム出題だけ 5 件 | × |

### 0-2. 決めてほしいこと

| # | 内容 | 推奨 |
|---|---|---|
| Q1 | **削除済みの講座 14・コース 29・課題 24**（今は状態 `deleted` で入れていて、受講者に見え、編集で 400）。新の状態に `deleted` に当たるものが無い | 新にある状態 `archived` で入れる。**販売停止と削除が同じ `archived` になる**のを避けたいなら、講座・コースに `deleted_at` を足す（school-launcher の migration とアプリの修正。05 の問い合わせと同じ） |
| Q2 | **レッスンの種別**（テスト 362・課題 209・資料 216・ディスカッション 24・スキル診断 1。今は旧の種別のまま入れていて、本文が出ず、編集で 400） | **`text` で入れる。** テストは今どおり右パネルのテストのタブで受けられる。旧の種別は `settings` に残す |
| Q3 | **完了の条件**（旧はテストは合格で、課題は提出か添削で、資料は修了に数えない）。新は種別を区別せず、すべて「完了にする」か本文を読んで完了 | 新の仕様のまま受け入れる（運営に確認）。資料を修了の条件から外したいなら、資料をレッスンにせず、ライブラリ（05 で移し済み）だけにする |
| Q4 | **並び**（`sort_no` が重なる 6 組） | 講座の中で「章 → `sort_no` → 旧 ID」の通し番号に振り直す（並びの意味は変えない） |
| Q5 | **削除済みの章**（27 件。中のレッスンは 0 件） | 移さない（一覧に出す） |
| Q6 | **動画の URL** | p-movie のトークンから `https://….m3u8` を組み立てる規則を p-movie 側に確かめ、`fixups` で直す。storage の行（旧サーバーの HTML 教材・PDF など。動画ではない）は、**種別を `text` にして本文に URL を載せる**か、移行の対象外にするかを決める |
| Q7 | **動画の尺**（旧に無い） | NULL のまま（途中の進捗率は 0%）。URL を直した後に測るかは後で決める |
| Q8 | **設問が 0 件になるテスト** | 出題条件なし 20 件・テスト以外のユニットのテスト 60 件・問題の無い 3 件は**移さない**（一覧に出す）。カテゴリからのランダム出題だけの 5 件は、**候補の問題をすべて固定の設問にする**（旧で出うる問題を含む） |
| Q9 | **合格点**（旧は点、新は割合） | 割合に直す（`floor(合格点 × 100 ÷ 旧の満点)`。**2026-10-26 に `ceil` から変えた**（受講 03 の Q9: 切り上げだと、ちょうど合格点の得点が端数で不合格になる）。満点は出題数 × 配点）。値の作り替えなので **`fixups` で行う**。旧でも合格できない 8 件は直さず一覧に出す |
| Q10 | **出題数**（旧は固定出題で先頭の N 問、ランダム出題は N 問を選んで出していた） | 固定出題は旧どおり先頭の N 問だけ。ランダム出題の 39 件は**全問を入れる**（合格点は割合なので意味を保てる） |
| Q11 | **採点できない設問**（選択肢 0 件の単一選択 15 件・正解の番号が範囲外 2 件） | 移さない（一覧に出す）。テストの残りの設問は移す |
| Q12 | **問題文・解説の HTML**（1,638 件・1,087 件） | 05 のお知らせと同じく、`fixups` でプレーンテキストに直す。画像（`<img>`）は画像の移送（L9）と一緒に決める |
| Q13 | **アンケート** | 設問の並びをページをまたいだ通し番号にする。必須の添付の設問 1 件は `fixups` で任意にする。選択肢の重複 1 件は `fixups` で区別を付ける |
| Q14 | **削除済みの開催回**（817 件。すべて過去） | 移さない（予約のある 2 回・2 件の予約も一覧に出す）。05 の Q1 に合わせるなら「新の状態」の `canceled_at` で入れる案もある |
| Q15 | **コース** | 公開中で公開する講座が無い 9 件は `archived`、期間が 120 か月を超える 2 件は無期限にする。どちらも値の作り替えなので `fixups` で行う |
| Q16 | **講座のカテゴリ**（`courses.category`） | 新の 6 つのコードとの対応表を運営から受け取るまで NULL（テナントのカテゴリ `course_category_links` は今のまま） |
| Q17 | **有料でないユニット**（旧の `payment_unit = 0`。t10 1,227・共有 1,307。旧では未購入の人にも見せていた可能性） | 旧の画面で未購入の人に見えていたかを確かめ、見えていたなら `is_preview = TRUE` |

### 0-3. 決まったこと（2026-10-26。すべて推奨どおり）

Q1〜Q17 は 0-2 の推奨どおり。補足:

- **Q1**: 削除済みの講座・コース・課題は `archived`（`deleted_at` は足さない）。販売停止と同じ状態になる
- **Q6**: storage の行（動画ではない旧サーバーの HTML 教材・PDF など）は **種別を `text` にし、本文に URL を載せる**。p-movie のトークンは、URL を組み立てる規則を p-movie 側に確かめるまで今のまま（[open-questions](../open-questions.md) に載せる）
- **Q17**: 旧は `payment_unit = 0` のユニットを購入の権限なしで開けた（`PaymentAuthorityModel.class.php:1659` の `OR (UN.payment_unit = 0)`）ので、**`is_preview = TRUE`** にする
- 値の作り替えになるもの（Q9 合格点・Q12 HTML・Q13 アンケート・Q15 コース）は `fixups` の提案にし、移行ツールは補正データを読むだけ

**追加の決定（2026-10-26。手順 5 で見つけたもの）**: アンケートの削除済みの設問（72 件）・ページが通常の設問として移っていた（受講者に出て、必須なら回答を送れない）。**新に `deleted_at` を足して移し、アプリで除く**（school-launcher `20261026120001_add_survey_deleted_at.sql`・`survey_repo.go`・`course_duplicate_repo.go`。作業ブランチ）。テストの削除済みの出題条件・設問（計 3 件）も出題から外した。

**新システムに機能が無いので移しても効かないもの**（文書に記録する）: 前提条件の鍵 37 件・公開期間 328 件・終了日時 1 件（過去。旧では閉じていた）・受験回数の上限（全件 0）・課題の締切（全件 NULL）・アンケートのページ分け・ライブの繰り返し・講座のタグ。

### 0-4. 後から決まったこと

| 日付 | 内容 |
|---|---|
| 2026-10-26 | **テストの題（`quizzes.title`）にユニット名（＝レッスンの題）を入れる。** 全区分の通しの確認で Q-06 を初めて流し、移したテスト 316 件すべてで題が空のため、運営がテストの設定を保存すると 400 になると分かった。旧 `test` に題の列が無く、旧の画面ではユニット名がテストの名前として出ていた |

## 1. 前提

### 1-1. 運営への確認事項

**この区分の分も含めて [open-questions.md](../open-questions.md) に1枚でまとめてある。**
同じ話を2か所に置かない。

### 1-2. 制約による不整合

**[constraint-violations.md](../constraint-violations.md) にまとめてある。**
NOT NULL / UNIQUE / CHECK に当たるものと、参照先が物理削除されているものを分けて持つ。

### 1-3. 決定済み（再確認だけ）

**内容ごとにまとめてある。** 同じ決定を2か所に書かない。

**移す / 移さないの範囲**

| 事項 | 決定 |
|---|---|
| 見出しブロック（`unit_type_id=0`） | **`lessons` に入れない**（ETL設計 §5-0）。**`course_chapters`（講座の章）に入れ、後ろのユニットを `lessons.chapter_id` で章に所属させる**（2026-09-30。削除済みの見出しも `deleted_at` 付きで移す。2026-10-01）。所属の判定は旧の講座ページと同じく `sort_no` → `unit_id` の順（`UnitModel::_buildSql` の既定の並び。移す範囲（ReCADemy の講座と、参照される共有講座）で見出しと並び順が重なる組は50。ReCADemy 自身の講座だけなら21。2026-10-02 に数え直した） |
| カテゴリ未設定の講座（235件中142件） | **そのまま移す**（`courses.category` は NULL 可）。旧の状態をそのまま写すだけで、**カテゴリを整備するかは移行とは別の作業**。cutover 前に「講座一覧の絞り込みが半分以上で効かない」ことは伝える |
| 模試（`is_mock_test` ほか） | **移行しない。** 対象外（未コミット）区分（X02） |
| 更新履歴3件（計300万行） | **移行しない。** 受験中の作業データで、採点時に本テーブルへコピーされる。**cutover 時点の中断中の受験だけは失われる** |
| コース（旧の講座の販売商品） | **`content.5` で `learning_paths` / `learning_path_courses` に移す**（2026-10-22 決定）。school-launcher は「コース＝旧の販売商品（`payment_item`）」という作りにした（`20261009113244`）。対象は `item_type = 0`（講座）で、ステージング 280 件・結び付き 985 件。**購入の記録（`learning_path_enrollments`）は受講・課金の区分で扱う**。課金（04）の `tenant_plans` には移さない（2026-10-23 決定）。対応は 3.2 |
| 販売停止の講座（`sales_status = 0`） | **`archived` で入れる**（2026-10-22 決定。それまでは `draft`）。新は講座の下書きをやめ（`20261012065004`）、画面から公開にする操作が無い。`archived` ならアーカイブの解除で戻せる。旧の値は `courses.settings.sales_status` に残す（ステージング 4 件。削除済みは `deleted`） |
| 講座のカテゴリ（テナントごと） | **`tenant_course_categories` と `course_category_links` にも入れる**（2026-10-22）。旧 `lesson_cate` はテナントごとなので、新のテナントごとのカテゴリ（`20261020001030`）が受け皿として合う。全テナント共通の `course_categories` / `courses.category` への書き込みも残す（新アプリの講座の一覧がまだ使っている）。削除済みのカテゴリは `deprecated_at` |
| 削除済みのレッスン | **`lessons.deleted_at` を入れる**（2026-10-22）。新アプリはレッスンを `deleted_at IS NULL` で絞る（`20261021082002`）。`status = 'deleted'` も残す。値は見出しと同じく旧の `update_date`。ライブのレッスンも同じ |
| 動画の置き場所（`video_source`） | **種類だけ正しく入れる**（2026-10-22 決定）。`pmovie_chk = 1` でトークンがある → `pmovie`、YouTube / Vimeo のホスト（新アプリと同じ一覧）→ `youtube` / `vimeo`、それ以外 → 既定の `storage`。**`video_url` は旧の値のまま**（トークンから URL を組み立てない）。**このままでは新アプリで再生できない** — 新は `pmovie` を `.m3u8` の URL、`storage` を自前ストレージのキーとして扱うが、旧の値は 40 文字のトークン（ステージング 6,656 件）と旧の自前サーバーの URL（`rome.learning-ware.jp` など）。再生できるようにするのは移行の外の作業（p-movie 側で URL を得る、動画を移す） |
| 動画の配信先 | **`lecture_path.pc_path` を `video_lessons.video_url` に移す。** `lecture` に URL 列は無いが、**別テーブル `lecture_path` が配信先を持つ**（recademy 2,559行。URL 1,171 / 相対パス 44 / 空 1,344）。`pmovie_chk` が立っていない動画はこちらで配信している |
| 画像（問題22列・設問21列） | **移す。** L9 でファイルを移送し `image_url` に入れる（A7 / A12） |
| 添削のファイル・配布ファイル | **5本とも移す**（`submission_feedback_files` / `assignment_materials`）。1本に畳まない（A13 / A14）。旧 `eval_*` は添削者が付けたファイル（2026-09-30 に `submission_files` から改めた） |
| ユニットの順序制御・免除 | **順序制御は移す**（`lesson_preconditions`。A15）。**免除（`unit_exemption`）は現状は移していない**（実装が無い。2026-10-02 の確認）。旧は「別ユニットで◯点以上なら免除」という規則で、会員ごとの免除表（`lesson_exemptions`）は取り下げた。移行ツールは件数を警告に出すだけ（ステージング1行） |
| アンケート回答の `entity_type` 1/3（お知らせ・レポート添付） | **受講（3）の担当。** 列（A12）だけでは移せない — `survey_responses.lesson_id` が NOT NULL なので、行き先を設計し直す（→ [受講 E7](../03-enrollment/review.md#e7-アンケート回答)） |

**データの持ち方（畳まない・元の粒度を保つ）**

| 事項 | 決定 |
|---|---|
| ユニットの種別 | **畳まない。** `lesson_types` に `quiz` / `assignment` / `document` / **`discussion`** / **`skill_check`** を追加する（A20）。7・8 は `UnitConstants.php` に無く、**`ShareController` / `UnitController` に定数がある**（`UNIT_TYPE_DISCUSSION` / `UNIT_TYPE_SKILL`）。正規の種別で、`LessonController` も進捗の更新対象にしている |
| ディスカッション・スキル診断の中身 | **ユニットは移すが、中身はこの区分の範囲外。** 投稿（`discussion` / `discussion_board` / `discussion_board_comment`）は[逆引き表](../legacy-table-coverage.md)で**区分が未分類**、診断結果（`public_learning_skill_unit*`）は**就職支援（07）**。**その区分を移すまで中身は空のまま**（ステージング実測でユニット22件） |
| 出題条件（`test_sub`） | **固定リストに展開しない。** `quiz_question_rules` と問題バンクを追加して条件のまま移す（A6）。**アプリの出題ロジックは未実装で、スキーマだけ置いてある**（2026-09-28 決定。→ [確認事項 C6](../open-questions.md)） |
| 問題カテゴリ（`question_cate`） | **`quiz_question_labels` に移す**（管理者が作るラベルと同じ表。2026-09-28 決定）。名前が重なる分は「（共有）」「（2）」などを付けて区別する |
| 合否・正誤 | **当時の結果をそのまま移す**（`quiz_attempts.passed` / `quiz_answers.is_correct`）。都度計算に任せない（A9 / A10） |
| ユニット本文の HTML | **変換せずそのまま移す。** 同梱ダンプでは `unit` 2,533行に HTML が1件も無く、`\r\n` 区切りの平文だった。表示時にサニタイズする |
| 点数の3列 | **`sum_score` → `score`、`total_score` → `max_score`。** `test_score` は百分率の派生値なので移行しない（採点処理で確定） |
| 回答の格納形式 | **パイプ `|` 区切り**（正解列 `question.answer` と同じ形式）。分割して `quiz_options` と突き合わせる |
| テストの制限時間 | **`exam_limit_times * 60` で秒に換算**（旧は分。残り時間計算が `*60 - test_time` で確定） |
| 課題の許可拡張子 | **lw2 の共通ホワイトリスト**（`UploadUtil::$extension_file` の21種）を既定値にする |

**制約に当たる行の扱い**（[共通仕様 3.5.1](../../migration-spec.md#351-not-null--unique--外部キーに当たる行)）

| 事項 | 決定 |
|---|---|
| **新環境の制約を緩めない** | **2026-09-23 決定。** 旧データが入らない箇所でも `NOT NULL` / `UNIQUE` を外さない。帰結として**移らないデータ**がある（下の3行） |
| 未提出の課題 | **移らない。** `submissions.submitted_at` は NOT NULL のまま（A21 から NULL 可化を取り下げ）。**「誰が提出していないか」は新環境に残らない** |
| 商品単位の修了証 | **移らない。** `certificates.course_id` は NOT NULL のまま（A16 から NULL 可化を取り下げ）。旧 `certificate_type=2` が対象（ステージング0件） |
| バッジ（定義・付与実績とも） | **移さない。** 2026-09-28 に移行対象外と決定（→ [対象外](../06-out-of-scope/breakdown.md#決定で対象外にしたもの)） |
| 1ユニットに複数のテスト | **2件目以降は移らない。** `quizzes` の `UNIQUE (tenant_id, lesson_id)` は外さない |
| migration の実装 | **school-launcher 側で行う。** [マイグレーション対象](schema-additions.md)は当てる内容と順序を示すもので、ファイルの作成・適用は school-launcher のリポジトリの作業 |
| 当たった行の処理 | **移さず `out/not-migrated.csv` に出し、暫定対応で直してから再実行する。** **どこが当たるか**は [確認事項](../open-questions.md)の確認事項に挙げる |
| 既定講師（`courses.instructor_id` が NOT NULL） | **代理講師の `users` 行を1件作り、全講座に割り当てる**（A21）。NOT NULL は外さない。対応表を受け取ってから付け替える |
| 発行済み修了証の発行者名 | **`certificates.issuer_name` は NOT NULL**（発行時点の値を凍結する列）。**テナントの設定側 `certificate_settings.issuer_name` は NULL 可**で「NULL なら `tenants.name`」という別の仕様。**取り違えない** |

**暫定対応（2026-09-23 決定）**

**本決まりではない。** 対応表やデータが届くまでの仮置きで、**届いたら差し替える**。
仮データを入れた行は**あとで特定できる必要がある**ので、入れた値と件数を記録する。

| 事項 | 暫定対応 |
|---|---|
| 講座の講師（`courses.instructor_id` が NOT NULL） | **代理講師の `users` 行を1件作り、全講座に割り当てる**（A21）。対応表を受け取ってから付け替え、**代理講師のままの講座が0件になったことを確認する** |
| 講座の価格 | **仮データを入れる。** 対応表を受け取ってから差し替える。**入れる値は運営と決める**（0 円は「無料」と区別がつかない）。**現状は設定 `provisional.course_price` の値を全講座に入れ、設定が無ければ NULL**（`courses.price` は NULL 可。2026-10-02 の確認） |
| アンケートの回答日時（`survey_responses.submitted_at` が NOT NULL） | **仮データを入れる。** 旧 `enquete_answer.regist_date`（NOT NULL）を代替値にする |
| 発行済み修了証の発行者名（`certificates.issuer_name` が NOT NULL） | **仮データを入れる。** 設定側（`config_certificate.issuer_name`）が NULL なら `tenants.name` を入れる |
| 修了証の通し番号（`certificates.serial_text` が NOT NULL） | **仮データを入れる。** 旧 `certificate_no` を文字列にして入れる（書式定義は後から適用する） |
| 通し番号の重複（`uk_cert_tenant_serial`） | **仮データを入れる。** 重複した2件目以降に**未使用の番号を振り直す**。振り直した対象を記録する |
| 修了証の重複（`uk_cert_tenant_user_course`） | **移行しない。** 同じ会員・同じ講座に複数ある場合、**その組はどれも移さない**（`(tenant_id, user_id, course_id)` が UNIQUE で、仮データでは一意にできない）。件数と対象を記録し、**あとで運営が選べるようにする** |

**実行の段取り**

| 事項 | 決定 |
|---|---|
| 修了証 | **移行ツールで実装する。** `cmd/import-certificates`（Go）とは役割分担せず、**既存ツールは流さない** |

**ライブ講座（content.4）**

**内容ごとにまとめてある。** 同じ決定を2か所に書かない。

**ライブの置き場所とアクセス制御（2026-09-24 決定）**

| 事項 | 決定 |
|---|---|
| 商品制限のあるライブ（5件） | **その商品が売っている実在の講座の配下に置く。** `live_lesson_limit_item` → `payment_item` → `payment_item_lesson` で講座に1対1でたどれる（248「３級デモ講座」/ 1308「★Revitプロジェクト実践講座」。**どちらもオンデマンドで移行済み**）。受け皿の講座は作らない |
| 商品制限の無いライブ（13件） | **受け皿の講座を1本作り、全会員をそこに受講登録する。** lw2 の「制限が無ければ全員に予約できる」を保つため。**開催回536件・予約12件が対象**。`enrollments` を作る段が要るので、**受講（04）と噛み合わせる** |
| `live_lessons.scheduled_at`（代表日時） | **直近の開催予定日を入れる。** 過去の回しか無いライブは最後の回。**開催回の本体は `live_lesson_occurrences`** で、この列は表示用 |
| 教室レッスン（`live_lesson_type = 1`、3件） | **ライブとして移す。** 会場は `live_lessons.settings` に施設名・説明を入れる。ReCADemy の施設は**1件だけで「ご自身のパソコン」**（住所・TEL・URL すべて空）。**対面の教室ではなく自席でソフトを使う予約枠**なので、集合研修（X01）として扱う必要はない |

**移す / 移さないの範囲**

| 事項 | 決定 |
|---|---|
| 削除済みのライブ・開催回 | **移す。** ライブは `lessons.status = 'deleted'`、開催回は **`deleted_at` を追加**して表す（A25）。ステージング実測でライブ3件 / 開催回817件（29%） |
| プレビュー2表（`live_lesson_preview` / `live_lesson_date_preview`） | **移行しない。** **UI の一時状態**で、保存すると本体に反映される。基盤で `edit_form_data` を移行しないと決めたのと同じ |
| `live_lesson.live_lesson_cate_id` | **移さない。** ステージング実測で全件が NULL か `0` で使われていない。実際の紐付けは `live_lesson_lesson_cate`。**本番ダンプで値が入っていれば移す** |
| `live_lesson_date.live_lesson_time` | **移さない。** `starts_at` / `ends_at` からの導出値。**旧の値と導出値が食い違う行がないかは抽出時に検査する** |
| チケットの消費履歴（`user_ticket_log`） | **移行しない。** `ticket_ledger_entries.grant_id`（NOT NULL）を決められず、増減の符号も旧に無い。移行時点の残高に対する `granted` 1行だけを入れる（ETL設計 §5-6） |
| `course_ticket_grants`（新側） | **空で始める。** 旧に対応データが無い（lw2 の付与は商品側） |
| `coupon_live_lesson` | **課金区分（未コミット）と合わせて決める。** クーポン本体がそちらにあるため、ライブ側だけ先に受け皿を作らない |
| `live_lesson.facility_id` の参照先（`facility` テーブル） | **移さない。** 集合研修（X01）で対象外。**ただし教室レッスンの開催場所が消えるため、施設名は文字列で残す**（1-1 の #3 と連動） |

**データの持ち方（畳まない・元の粒度を保つ）**

| 事項 | 決定 |
|---|---|
| ライブの旧 ID | **`live_lessons.live_lesson_id` に持つ**（A22）。`lessons.unit_id` はオンデマンドが `unit.unit_id` で使用済みで、**同じ列に入れると衝突する**（ステージング実測 18件中11件）。**`uk_lessons_legacy` は外さない** |
| 削除と中止 | **別の軸として持つ。** `live_lesson_date.del_chk` → **`deleted_at`（追加）**、開催の中止 → `canceled_at`。**混ぜると受講者の履歴に「中止された」と見える** |
| 予約の3フラグ | **`status` に畳むが、元の値は残す。** `cancel_chk` / `attendance_chk` / `stop_chk` を受講 A5 の `live_reservations.settings` に保持する |
| 開催中止で不成立になった予約 | **`live_reservation_statuses` に値を1つ足す**（受講 A5 の `host_canceled`）。既存4値（`reserved`/`canceled`/`attended`/`no_show`）では**受講者都合のキャンセルと区別できない** |
| リマインドの送信済み | **旧 `mail_send_chk` は「送信済み」の印。** その回の予約の `live_reservations.reminded_at` に移す。`remind_enabled`（A25）は全回 TRUE（2026-09-30 訂正。以前は `mail_send_chk` を `remind_enabled` に写していた） |
| 連日設定・除外日 | **3表をセットで移す**（A26。実測 86 / 93件、除外日は 128行 / (ライブ, 日付) 22組。除外日の全行は `live_lesson_exclusion_date_history` にも入れる）。**片方だけ移すとルールの意味が変わる**（除外日だけ残ると、何を除外しているのか分からない）。**開催回を自動生成する機能を作るかは移行とは別の判断** |
| チケット種別の名前が重複 | **そのまま移す。** ステージングの2件は同名（「3級マンツーマンレッスン専用チケット」）。`ticket_types.name` に UNIQUE は無いので投入は止まらない。**運営画面で区別が付かないことは cutover 前に伝える** |
| ライブのカテゴリ | **多対多のまま移す**（A23）。`live_lesson.live_lesson_cate_id` ではなく `live_lesson_lesson_cate` が正 |
| チケット残高 | **残高1行 = 付与1行。** `quantity = remaining_quantity = ticket_num` とし、`note` に「lw2 移行時点の残高」と書く（ETL設計 §5-6）。**「何枚付与されて何枚使ったか」は旧が持たないので表現しない** |
| チケットの出どころ | **すべて `manual`。** `ticket_grant_sources` の既存3値から選ぶ |
| **消費の台帳行（2026-09-24 決定）** | **移行する予約に対して `consumed` の台帳行を作る。** lw2 の `user_ticket_log` は再生しないが、**台帳行が無いとキャンセルしてもチケットが戻らない**（`RefundForReservation` が `ticket_ledger_entries` から「その予約で何枚引いたか」を読む）。会員と枚数だけでは足りない理由は2つ — **①予約後に `cost` が変わっている可能性がある**（実装が現在の `cost` を見ないのはこのため）**②消費は複数の付与にまたがりうる**（`AllocateForConsumption` が期限の近い順に割り振る） |
| ライブ1件あたりの必要枚数 | **`item_ticket_price = 0` は行を作らない**（`chk_lltr_cost (cost >= 1)` に当たるため）。**行が無い = チケット不要**。ステージング実測は 18件中15件 |

**制約に当たる行の扱い**（[共通仕様 3.5.1](../../migration-spec.md#351-not-null--unique--外部キーに当たる行)）

| 事項 | 決定 |
|---|---|
| **新環境の制約を緩めない** | **2026-09-23 決定（オンデマンドと同じ）。** 旧データが入らない箇所でも `NOT NULL` / `UNIQUE` / `CHECK` を外さない。**例外を作る場合は 1-1 で意図を確認してから** |
| 当たった行の処理 | **移さず `out/not-migrated.csv` に出し、暫定対応で直してから再実行する。** **どこが当たるか**は [確認事項](../open-questions.md) と [制約による不整合](../constraint-violations.md) にまとめてある（1-1 には置いていない） |
| migration の実装 | **school-launcher 側で行う。** [schema-additions.md](schema-additions.md) は当てる内容と順序を示すもので、ファイルの作成・適用は school-launcher のリポジトリの作業 |
| 巻き添えの扱い | **大本を直せば消えるので、子を個別に直さない。** 削除済みのライブにぶら下がる開催回44件、削除済みの開催回にぶら下がる予約3件がこれに当たる（いずれも親を移すので巻き添えにはならない） |

**暫定対応**

**本決まりではない。** 対応表やデータが届くまでの仮置きで、**届いたら差し替える**。
仮データを入れた行は**あとで特定できる必要がある**ので、入れた値と件数を記録する。

| 事項 | 暫定対応 |
|---|---|
| ライブの受け皿 course | **上の 2026-09-24 決定どおり実装してある**（商品制限のあるライブはその講座、無いライブは受け皿講座1本）。受け皿講座の `instructor_id` は、受け皿に入るライブの講師のうち担当数が最も多い1名 |
| `live_lessons.scheduled_at` | **直近の開催予定日、無ければ最後の回**（削除済みでない回を優先）で実装してある |
| ライブの必要枚数の種別 | `ticket_limit_lesson` から逆引きできないライブは、**`live_lesson_ticket_requirements` の行を作らない**（チケット不要として扱う）。**対象を記録し、あとで運営が付け直せるようにする** |

**実行の段取り**

| 事項 | 決定 |
|---|---|
| 前提区分 | **基盤（`foundation.*`）と `content.1`**（`lesson_types` / `content_statuses` / `courses` / `lessons`）が先。**受講（04）・課金（05）には依存しない** |
| 課金区分への依存 | **`live_lesson_limit_item.item_id` と `user_ticket.authority_id` の参照先は課金区分（未コミット）。** 旧 ID を保持する形で先に入れ、**課金の移行後に解決する** |

### 1-4. 本番ダンプ受領後に確認すること

> **制約を緩めないと決めたため、下の2件は「何件が移らないか」を数える項目**になる。
> 判断は済んでいるが、**規模は運営に伝える必要がある**。

| 確認 | 効く先 |
|---|---|
| 1ユニットに複数のテストを持つ件数（`test.unit_id` の重複） | `quizzes` の UNIQUE (tenant_id, lesson_id)。UNIQUE は外さず、2件目以降のテストは移らない |
| `report_answer.submit_date` が NULL の件数 | その未提出データは移らない |

**そのほかの確認**

| 確認 | 効く先 |
|---|---|
| 1ユニットに複数の `lecture` があるか | `video_lessons.lesson_id` が PK。実測では最大1 |
| 同じ `enquete` を複数ユニットが参照しているか | `survey_lessons.lesson_id` が PK。**ユニットごとに複製して移す**ので、件数は複製の規模 |
| `lesson_cate_name` に50文字超・128文字超があるか | `course_categories.code` / `name_ja` |
| `enquete_question.question_text` に500文字超があるか | `survey_questions.prompt` |
| `question.selection1..20` に1000文字超があるか | `quiz_options.body` |
| `drive.drive_name` に200文字超があるか | `library_folders.name` |
| `lesson_attached_file` 3テーブルが0行であること | 移行するデータが無いことの確認 |
| `lecture_path_test` の中身と用途 | 検証用なら移行しない |
| **`unit.detail` に HTML が入っていないか**（同梱ダンプでは0件） | 入っていればサニタイズ方針を決める |
| **cutover 時点で中断中の受験があるか**（`user_learning_test_update` に未採点の行） | あれば再受験してもらう合意が要る |
| **実データへの cp932 混入** | `test` のカラムコメントが文字化けしている。**実データにも混入の可能性がある** |

**ライブ講座（content.4）**

| 確認 | 効く先 |
|---|---|
| `live_lesson_date.capacity = 0` の件数 | `chk_llo_capacity`。あれば NULL に倒すか移さないかを決める（ステージング0件） |
| `live_lesson_date` で `live_lesson_date_to <= live_lesson_date_from` の件数 | `chk_llo_period`。**値は作らない**ので、あれば移らない（ステージング0件） |
| `live_lesson_reserve` の `(live_lesson_date_id, user_id)` 重複件数 | `uk_lr_occurrence_user`。**重複した組はどれも移らない**（ステージング4組8行） |
| `live_lesson_reserve.reserve_date` が NULL の件数 | `live_reservations.reserved_at` は NOT NULL（ステージング0件） |
| `user_ticket.ticket_id` が NULL の件数 / `ticket_num <= 0` の件数 | `ticket_grants` の NOT NULL と `chk_tg_qty`（ステージング3件 / 2件） |
| **cutover 時点で未来の開催回に残る予約の件数** | その予約は cutover 後にキャンセルされうる。**台帳行を作れないとチケットが戻らない** |
| **チケットを要するライブの予約のうち、会員に対応する付与が無い／0枚のもの** | 台帳行を作れない。**ステージングでは11件中9件**（会員3181 が使い切って `ticket_num = 0`）。**残り0枚の付与を移すかの判断と連動する** |
| `live_lesson_id` と `unit_id` が重なる件数 | `uk_lessons_legacy`。**`live_lessons.live_lesson_id`（A22）が要るかの判断**（ステージング 18件中11件） |
| `live_lesson_url` に1000文字超があるか | `live_lesson_occurrences.meeting_url` varchar(1000)。**切り捨てない**（ステージング最大77文字） |
| `live_lesson_name` に255文字超があるか | `lessons.title` varchar(255)（ステージング最大15文字） |
| `live_lesson_cate_name` に200文字超があるか | A23 の `live_lesson_categories.name`（ステージング実測は全件短い） |
| `live_lesson.live_lesson_cate_id` に値が入っているか | 入っていれば移す（ステージングは全件 NULL か `0`） |
| **本番の `facility` に住所・TEL・URL が入っているか** | ステージングは施設1件（「ご自身のパソコン」）で**すべて空**。**住所や地図が要る施設があれば、`settings` の文字列では足りず別表の追加が要る** |
| `live_lesson_type = 1`（教室レッスン）の件数 | ステージング3件。**本番で対面の教室が多ければ、会場の持ち方を決め直す** |
| `live_lesson_group` / `coupon_live_lesson` の件数 | **ステージングは両方0件**で、実装の検証になっていない |
| `live_lesson_reserve.change_reserve_id` / `base_reserve_id` の件数 | 振替予約の有無（ステージング0件）。あれば受講 A5 の `live_reservations.settings` に残す（実装済み） |
| `config_live_lesson` の `ticket_cancel_day` / `ticket_cancel_time` の実値 | `cancel_closes_at` の計算。**ステージングは 1日 0時間**で、ETL設計 §5-6 の「14日前」と食い違う |
| `user_ticket_log.action_type` の値の分布 | **カラムコメント（`create,update,use,cancel`）と実データが食い違う**（ステージングに `lesson_cancel` がある）。履歴を再生しない判断の再確認 |
| 予約のある開催回のうち、cutover 時点で未来のものの件数 | `reminded_at` の埋め方（1-1 の #5。ステージングは32件すべて過去） |

### 1-5. 検証データでの実測（2026-09-24 実施）

> **ここの数値は本番ではない。** 2026-09-18 取得のステージングダンプ
> （`lw2_stg_kiracari_20260918_1946`）をローカルの lw2 に取り込み、`tenant_id = 10`（ReCADemy）で
> `run --dry-run --section ondemand` と、**実際に INSERT してロールバックする予行**を
> 通したもの。**本番の見積もりにこの数値を使わない。**

**本番と違う前提**

- ステージングのテナントは4件（本番は73件）。ReCADemy は `tenant_id = 10`（本番は 12）
- **修了証が3件しかなく、重複の検証になっていない**
- `live` / 課金まわりの参照先が未移行なので、それに依存する列は NULL で入る

**件数（投入 27,834 行 / 移行しない 314 行）。dry-run と予行で一致する。**

> **この表は区分を組み替える前（旧 `ondemand.1`〜`8`）の記録。** 受講（3）の Step が
> 混ざっており、いまの区分2の実測とは一致しない。**区分ごとの現在の合計は
> 2026-09-26 の通し実行で 基盤 35,580 / コンテンツ 47,118 / 受講 28,806 行**。
> 受講の Step の値は [受講の移行仕様](../03-enrollment/migration-spec.md) を見る。

| フェーズ | Step | 抽出 | 投入 | 移行しない |
|---|---|---:|---:|---:|
| ondemand.1 | master.lesson_types ほか4件 | 8 | 2 | 0 |
| ondemand.2 | proxy_instructor / course_categories / courses | 260 | 260 | 0 |
| ondemand.3 | lessons / video_lessons | 6,235 | 5,508 | **140** |
| ondemand.4 | quiz_question_categories | 124 | 124 | 0 |
| ondemand.4 | quiz_question_banks | 3,880 | 3,880 | 0 |
| ondemand.4 | quizzes | 297 | 295 | **2** |
| ondemand.4 | quiz_question_rules | 285 | 285 | 0 |
| ondemand.4 | quiz_questions | 3,950 | 3,950 | 0 |
| ondemand.4 | quiz_options | 3,950 | 8,667 | 0 |
| ondemand.5 | survey_lessons / pages / questions / options | 487 | 736 | 0 |
| ondemand.5 | assignments / assignment_materials | 226 | 150 | **1** |
| ondemand.6 | quiz_attempts / answers / selected | 4,935 | 3,359 | 0 |
| ondemand.6 | survey_responses / answers / selected | 415 | 314 | **7** |
| ondemand.6 | submissions / files / feedbacks | 493 | 112 | **158** |
| ondemand.7 | certificate_settings / certificates / events | 6 | 0 | **6** |
| ondemand.8 | library_folders / materials / lesson_targets | 161 | 162 | 0 |
| ondemand.8 | lesson_preconditions | 30 | 30 | 0 |

**dry-run で判明して対処したもの**

| 事象 | 実測 | 対処 |
|---|---:|---|
| **同じテストの別の大問に同じ問題が入る** | 1組 | `quiz_questions` の ULID を `(test_id, question_id, 並び順)` から **`(test_sub_id, question_id, 並び順)`** に変えた。テスト単位だと衝突して両方とも移らなかった |
| **同じアンケートを複数ユニットが参照する** | 7件 | **ユニットごとに複製**して移す。`uk_survey_pages` を `(tenant_id, legacy_id)` → **`(tenant_id, lesson_id, legacy_id)`** に変えた（その後、旧 ID の列は `enquete_page_id` に改名）（変える前は89件中60件が落ちた） |
| **`survey_lessons` の主キーが `lesson_id`** | — | 投入済みの親を覚える列に `lesson_id` を足した（`TargetDatabase.REFERENCED_COLUMNS`）。無いと子が全部「親が無い」と判定された |
| **添削者が記録されていない添削** | 37件中33件 | `submission_feedbacks.reviewer_id` は NOT NULL。**代理講師に倒して移す**（暫定対応）。倒さないと添削の本文と点数ごと落ちる |
| 選択肢が0件の選択式問題 | 19件 | 選択肢を作らない（旧データの時点で選べない） |

**実 INSERT してロールバックする予行で判明したもの**

**dry-run は INSERT を実行しない**ので、下の2件は流すまで出なかった。どちらも
**既定値を持つ NOT NULL 列に、明示的に NULL を書こうとしていた**もの。

| 事象 | 実測 | 対処 |
|---|---:|---|
| `assignments.created_at` に NULL | 250件中23件 | **旧 `report.regist_date` にゼロ日付がある。** `update_date` で代替する。**両方ゼロの17件は移らない**（→ [制約に当たって移らない行 #8](../constraint-violations.md)） |
| `library_folders.created_at` に NULL | 1件 | ユニット添付用に**移行が作るフォルダ**。旧に対応する日時が無いので**実行時刻**を入れる |
| （検証の穴） | — | `_not_null` が**既定値のある列を見ていなかった**。`created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP` は書かなければ DB が埋めるが、**INSERT の列に入れて NULL を渡すと既定値は効かない**。**Step が書く列は既定値があっても見る**よう直した |

> **この修正で、隠れていた違反がもう1件表に出た。** `submissions.submitted_at`（NOT NULL /
> 既定値あり）に NULL を渡していた**13件**。**未提出の課題は移らない**という
> [1-3 の決定](#1-3-決定済み再確認だけ)どおりの結果で、これまでは
> **黙って「移行実行日時」が入るところだった**。

**移行しない 314 行の内訳**

| 何が | 件数 | なぜ |
|---|---:|---|
| `video_lessons` | 140 | `video_url` が NOT NULL。p-movie トークンも `lecture_path.pc_path` も空 |
| `submissions` | 105 | 参照先の課題が無い。**32件は孤児**（`report` が物理削除）。残りを「別テナントの課題」としていたのは**読み違い**で、実体は**共有講座（`tenant_id = 0`）の課題**と、**`created_at` に入れる値が無くて落ちた課題17件の巻き添え** |
| `submissions` | 13 | **未提出**（`submit_date` が NULL）。`submitted_at` は NOT NULL のままにする決定どおり |
| `submission_feedbacks` / `submission_feedback_files` | 40 | 上の巻き添え（提出が移らないので添削・ファイルも移らない） |
| `assignments` | 17 | `regist_date` も `update_date` もゼロ日付で、`created_at` に入れる値が無い（当時は1件と記録していたが、共有講座ぶんを数えられていなかった） |
| `survey_answers` | 7 | 回答 JSON が、そのアンケートに属さない設問を指している |
| `certificates` / `certificate_events` | 6 | **読み違いだった（2026-09-26 に修正済み、いまは6件とも入る）。** `entity_id` を講座 ID と解釈していたが、実体は `user_learning_lesson_id`（→ [受講 E10](../03-enrollment/review.md#user_certificate--certificates)） |
| `quizzes` | 2 | 見出しブロック（`unit_type_id = 0`）にテストがぶら下がっている。見出しは `lessons` に入れないので巻き添え |

**移せなかったもの（制約違反ではなく、受け皿が無い）**

| 何が | 件数 | なぜ |
|---|---:|---|
| 設問別の回答のうち条件出題ぶん | 4,922件中 **50件** | `user_learning_test_sub` は `question_id` しか持たず、どの大問から出たかを記録していない。条件出題（`test_sub_type_id = 2`）には `quiz_questions` の行自体が無い |
| アンケート回答のうちユニット以外 | 232件中 **152件**（1=お知らせ3件 / 3=レポート149件） | `entity_type_id` が 1 / 3 の回答は、`survey_responses.lesson_id`（NOT NULL）に入れるレッスンが決まらない。**ユニット回答80件のうち3件も、受講の行が引けず移らない**（抽出77件） |
| `unit_exemption`（免除） | 1件 | lw2 は「別ユニットで◯点以上なら免除」という**規則**、新環境の `lesson_exemptions` は**会員ごとの免除**。構造が違う |
| バッジの付与実績 | — | lw2 の DB に無い（外部のバッジシステム） |

> **予行と実投入を通した（2026-09-24）。** 38 Step すべてが最後まで走り、
> **27,834 行を投入**した（`verify` OK）。**dry-run・予行・実投入の件数はすべて一致する。**

**投入後の検証で見つけたもの**

**制約には当たらないが値の意味が違う**ものは、投入して旧と突き合わせるまで分からなかった。

| 事象 | 実測 | 対処 |
|---|---:|---|
| **全受験が「中断」で入った** | 251件 | `user_learning_test.finished_chk` を完了フラグとして読んでいたが、**lw2 が更新するのは同名の `user_learning_test_update.finished_chk` だけ**で、こちらは全件 `0`。**終了時刻の有無**で判断するよう直し、251件を削除して入れ直した |
| 正解の選択肢が存在しない設問 | 2件 | **旧データの不整合。** `selection_num = 2` なのに `answer = "3"`。lw2 でも誰も正解できない状態なので、**そのまま移す**（正解フラグの付いた選択肢が無い） |

**投入後に突き合わせた項目**

| 検証 | 結果 |
|---|---|
| 受験251件の点数・満点・合否・所要時間・状態・完了日時 | **食い違い0件**（決定論 ULID で突き合わせ） |
| `lessons.type` の分布 | video 2,527 / quiz 249 / assignment 145 / document 97 / survey 83 / discussion 21 / skill_check 1。**全部 `text` になっていない** |
| 見出しブロック・集合研修の除外 | 旧 3,710 − 新 3,123 = **587件**。旧の `unit_type_id in (0, 5)` と一致 |
| テナント跨ぎ | 設問・選択肢・受験のいずれも**0件** |
| 共有アンケートの複製 | 旧ページ1件が最大**10レッスン**に複製されている（設計どおり） |
| 正解フラグの総数 | 3,914（旧から数えた 3,916 との差2件は上記の不整合） |

---

## 2. データ登録順

新環境は**実 FK を持つ**ため順序が強制される。**前のフェーズが終わるまで次に進まない。**

```
前提       foundation.* が完了していること（tenants / users / グループ / 属性）
              ↓
content.1  オンデマンド講座
              ├ マスタの追加値 ※ FK の参照先をそろえる
              │   master.lesson_types（quiz / assignment / document / discussion / skill_check）
              │   master.content_statuses.deleted / master.quiz_question_types（free_text）
              │   master.survey_question_kinds（file_upload）
              ├ content.proxy_instructor（代理講師）
              ├ content.course_categories → content.tenant_course_categories
              │   → content.courses → content.course_category_links   ※ courses.category が FK
              ├ content.course_tags → content.course_tag_links
              ├ content.chapters（見出しブロック → course_chapters）
              ├ content.lessons（見出しブロックを除く）→ content.video_lessons
              └ content.lesson_preconditions
              ↓
content.2  テスト定義・課題定義
              ├ content.quiz_question_categories（→ quiz_question_labels）→ content.quiz_question_banks
              │   → content.quizzes → content.quiz_question_rules → content.quiz_questions → content.quiz_options
              └ content.assignments → content.assignment_materials
              ↓
content.3  アンケート定義
              content.survey_lessons → content.survey_pages → content.survey_questions
                → content.survey_question_options
              ↓
content.4  ライブ講座（→ 4-2）
              content.live_host_course → content.live_lessons → content.live_lesson_details
                → content.live_reservation_policies
                → content.live_occurrences → content.live_categories → content.live_category_links
                → content.live_group_targets → content.live_recurrence_rules → content.live_recurrence_details
                → content.live_recurrence_exclusions → content.live_exclusion_history
              ↓
content.5  コース（旧の講座の販売商品。2026-10-22）
              content.learning_paths → content.learning_path_courses
```

> **番号は `migrator/phases/registry.py` と一致させること。** 指定は `--phase content.2` の形。

**この区分に入っていないもの**（以前の `ondemand.6`〜`8` にあったもの）

| 何が | どこで流すか |
|---|---|
| 受験・アンケート回答・課題提出の実績 | 受講の `enrollment.3`〜`5`（[受講の移行仕様](../03-enrollment/migration-spec.md)） |
| 修了証 | 受講の `enrollment.7` |
| 受け皿講座への全会員の受講登録 | 受講の `enrollment.1`（`enrollment.live_host_enrollments`） |
| ライブの予約・レビュー | 受講の `enrollment.6` |
| チケット / ライブを予約できる商品の全行（`live_lesson_limit_item_history`） | 課金の `billing.1` / `billing.2` |
| 教材・ライブラリ | サポートの `support.5` |

**順序の根拠**

- **マスタが先。** `content_statuses` / `lesson_types` / `quiz_question_types` / `survey_question_kinds` はいずれも FK の参照先で、`tenant_id` を持たないグローバルマスタ
- **`course_categories` は `courses` より先。** `courses.category` は `course_categories(code)` への FK で、**新規 DB では空**（既存 `courses.category` からの吸い上げでしか作られない）
- **`courses` は `lessons` より先**（`lessons.course_id`）、**章（`course_chapters`）は `lessons` より先**（`lessons.chapter_id`）、**`lessons` は quizzes / surveys / assignments より先**
- **ライブは講座の後。** `lessons.course_id` が NOT NULL で、商品制限のあるライブは `content.1` で入れた講座に置く
- **コースは講座の後。** `learning_path_courses.course_id` が講座を指す
- **R3（テスト中断・再開）はこの図に入れない。** 受験中の作業データなので移行しない

## 2-2. 実行手順

**フェーズの指定は `区分.番号`**（`content.2` など）。**フェーズは区切って流す。**

```bash
# 0. 追加スキーマを当てる → 移行先を初期化する（school-launcher のリポジトリで）
#    DDL 一覧: docs/db/02-content/schema-additions.md
make reseed

# 1. 接続と前提を確認する / 実行計画を見る
python -m migrator doctor
python -m migrator plan

# 2. 基盤が終わっていることを確認する
python -m migrator run --section foundation
python -m migrator verify

# 3. 事前検査
python -m migrator preflight

# 4. dry-run。**フェーズ単位で試せる**
python -m migrator run --dry-run --phase content.1
python -m migrator run --dry-run --section content

# 5. 本番投入。フェーズごとに結果を見てから次へ
python -m migrator run --phase content.1
python -m migrator run --phase content.2
...

# 6. 検証
python -m migrator verify
```

> **実績（受験・回答・提出）は受講の区分で流す。** 大きい表（`user_learning_test_sub` 1,070万行）の時間とバッチサイズは、受講の移行仕様で見積もる。

---

## 3. データ移行仕様

**カラム単位の仕様は [review.md](review.md) が正。** ここには**複数テーブルに効くもの**と、**取り違えると致命的なもの**だけを置く。

### 3.1 抽出（extract）

**オンデマンド固有の絞り込み**

- **`tenant_id` を持たないテーブルが多い。** 親と join して絞る。**join を落とすと全73テナントを拾う**
  - `unit` → `lesson` と join（`lesson_id`）
  - `test` / `report` → `unit` → `lesson` と join（`unit_id`）
  - `enquete_answer` → `enquete` と join。**落とすと 64,883件を拾う**（recademy 単体は 2,464件。26分の1）
  - `lesson` / `question` / `enquete` は `tenant_id` を持つので直接絞れる
- **見出しブロック（`unit.unit_type_id = 0`）を除外する。** `lessons` に入れると FK 違反になる（ETL設計 §5-0）
- **削除済み（`del_chk = 1`）も移す。** 講座・ユニット・課題は `status = 'deleted'`（`content_statuses` に `deleted` を追加）、見出しは `course_chapters.deleted_at` で表現する
  - **テスト・アンケートの定義は、削除済みも削除の印なしで入る。** `test` / `test_sub` / `test_sub_question` / `question` / `question_cate` /
    `enquete` / `enquete_page` / `enquete_question` は、移行ツールが `del_chk` を読むが使っておらず、生きている行と同じ形で入る。
    **削除を表す扱いは現状は移していない**（実装が無い。2026-10-02 の確認。受け皿の列も無い）。
    ステージング（`tenant_id = 10` の定義）で `test` 297件中12件、`test_sub` 285件中4件、`question` 3,880件中5件、
    `enquete` 337件中26件、`enquete_page` 381件中62件、`enquete_question` 309件中101件（`question_cate` は0件）

**SELECT してはいけない列**

| テーブル | 列 | 理由 |
|---|---|---|
| `remote_api_token` | `token` | **発行中の一時トークン。** 移した時点で無効で、持ち出す意味がない |

**事前検査**

| 検査 | 対象 | 判断 |
|---|---|---|
| 重複 | 1ユニットあたりの `test` / `lecture` 件数、複数ユニットから参照される `enquete` | 0件でなければ PK / UNIQUE を見直す |
| 桁溢れ | `lesson_cate_name`(50/128) / `question.selection*`(1000) / `enquete_question.question_text`(500) / `drive_name`(200) | **超過があれば列を広げる**（切り捨てない） |
| 文字コード | `test` 系のテキスト列 | **cp932 混入の疑いがある。** 検出したら人が見る |
| コード値の網羅 | `unit_type_id` / `question_type_id` / `enquete_question.question_type` | 対応表に無い値があれば停止する |
| 件数 | `lesson_attached_file` 3件が0行か | 0行なら実装は通すだけ |

### 3.2 変換（transform）

| 変換 | 規則 |
|---|---|
| `lesson.open_period`（**月**）→ `courses.access_days`（**日**） | **×30 で換算する。** 忘れると受講期間が 1/30 になる |
| `lesson.sales_status` / `del_chk` → `courses.status` | 削除 → `deleted`、販売中（1）→ `published`、販売停止 → **`archived`**（2026-10-22） |
| `payment_item`（`item_type = 0`）→ `learning_paths` | `item_name` → `title`、`price`（**税込**）→ `price`、`sort_no` → `sort_order`、`remote_chk` → `remote_pc_enabled`、`extension_price` → `extension_fee`（旧の延長は、この料金で月額の自動継続に切り替える）、`display_chk` 1 → `listed = TRUE`（0・2 は FALSE）。状態は削除 → `deleted`、有効 → `published`、無効 → `archived`（`learning_paths.status` は `content_statuses` への FK）。`sequential` は FALSE |
| `manual_term` / `manual_term_type` → `access_period_value` / `_unit` | 種類は 0 日間 / 1 週間 / 2 ヶ月 / 3 年間 / 4 期限なし（`PaymentItemController.php:737`）。新は日・月だけなので**週は ×7 日、年は ×12 ヶ月**に直す。`no_limit_chk = 1`・種類 4・**種類が NULL（自動継続の商品。ステージング 92 件）は無期限**（両方 NULL）。数が無いのに種類があるものは作り替えず、CHECK に当たって一覧に出る（ステージング 0 件） |
| `payment_item_lesson` → `learning_path_courses` | **削除されていない結び付きだけ**を入れる（3.4 の D。削除済みは移行対象外）。`sort_order` は旧の登録順（`item_set_lesson_id`。旧は商品の中の講座に並びを持たない） |
| `unit.unit_type_id` → `lessons.type` | **畳まない。** 1→`video`、2→`quiz`、3→`survey`、4→`assignment`、6→`document`、**7→`discussion`**、**8→`skill_check`**。**0=見出しは除外**、5=集合研修は対象外区分。**対応表に無い値は止める**（黙って `text` に倒さない） |
| `unit.sort_no` → `sort_order` | **現状は `sort_no` をそのまま入れている**（講座ごとに採番し直していない。2026-10-02 の確認）。見出しを除いた分の番号が飛び、旧で同じ `sort_no` だった組も同じ値のまま残る（旧は `unit_id` 順で並べていた） |
| `question.selection1..20` → `quiz_options` | 横持ち → 縦持ち。有効数は `selection_num` |
| `question.answer` → `quiz_options.is_correct` | 正解文字列を選択肢と突き合わせてフラグを立てる |
| `sum_score` / `total_score` → `score` / `max_score` | **`test_score`（百分率）は使わない。** `sum_score` が素点、`total_score` が満点 |
| `exam_limit_times`（**分**）→ `time_limit_sec`（**秒**） | **×60 で換算する。** `test_time` は秒なのでそのまま |
| `question_answer` → `quiz_answer_selected_options` | **`|` で分割**し、`quiz_options` と突き合わせる。`question_type_id=3` は判定が逆 |
| `enquete_answer.answer`(JSON) → `survey_answers` | キーは `answer_<enquete_question_id>`（ETL設計 §5-5）。設問タイプごとに入れる列が変わる |
| `test_sub_question` の ID | **旧 ID を引き継がない**（採番が枯渇・履歴断裂）。**`(test_sub_id, question_id, sort_no)` から採番する**（同じテストの別の大問に同じ問題が入るため、テスト単位だと衝突する） |
| 画像ファイル名 → `image_url` | L9 でファイルを移送し、移送先の URL を入れる |
| `test_start_time` / `test_end_time` → `started_at` / `completed_at` | **`timestamp` 列なので JST naive → UTC に変換してから書く** |

> **取り違え注意**
> - **`open_period` の単位**（月→日）。受講期間が 1/30 になる
> - **`limit_Date` は大文字混じり**。`limit_date` と書くと取りこぼす

### 3.3 投入（load）

- **冪等性**: 決定論 ULID と業務キーの UNIQUE で担保する。**`quiz_attempts` には業務的な一意キーが無く、決定論 ULID だけが頼り**なので、採番の入力（entity 名）を変えない
- **大きいテーブルは分割する**: `user_learning_test_sub`（1,070万行）/ `test_sub_question`（65万行）。**dry-run で件数と所要を確認してから流す**
- **エラー時**: フェーズ単位でやり直す。定義系を部分投入したまま実績系に進まない

### 3.4 移行の対象外

**A. 移行できないもの**

| 対象 | なぜ移行できないか |
|---|---|
| `remote_api_token` 全体 | **発行中の一時トークン**で、移した時点で無効。新環境は予約システムで概念も違う。**移行ツールはこの表を読まず、`courses.remote_pc_enabled` は全講座 FALSE**（`lesson_id` から初期値を導く案は現状は実装が無い。2026-10-02 の確認） |
| `drive.dir_name` | ファイルパスそのもの。**L9 の移送で URL に置き換わる**ため、移送後は参照されない（移送の入力としては使う） |

**B. 方針として移行しないもの**

| 対象 | 理由 |
|---|---|
| `test.is_mock_test` / `mock_post_message` / `mark_type_id` | **模試は対象外（未コミット）区分**（X02） |
| `library_downloads` | 新環境側の**純ログ**。旧に対応データも無く、空で始める |

**C. 現状は移していないもの（実装が無い。2026-10-02 の確認）**

**移さないと決めたものではない。** 移行ツールに実装が無く、いまは入っていないもの。

| 対象 | 状態 |
|---|---|
| `unit_exemption`（免除の規則） | 受け皿なし。移行ツールは件数を警告に出すだけ（ステージング1行） |
| `report_path`（提出後の解説ページの配信先） | 受け皿なし。読んでいない（ステージング144行、`pc_path` あり23行） |
| テスト・アンケート定義の `del_chk` | 削除済みも削除の印なしで入る（3.1） |
| `lesson` の `lesson_thumbnail_type` / `img_smartphone` / `lesson_img_file_name` / `inquiry_address` / `frame_id` / `disp_type_id` / `frame_height` / `frame_width` / `operating_env` / `inquire_cate_id` | 読んでいない。`courses.settings` に入るのは7フラグ（`open_pc` / `open_smartphone` / `progress_display` / `drill` / `quiz` / `sns_shared` / `inquiry`）だけ |
| `lesson.update_date` / `unit.update_date` / `live_lesson.update_date` → `updated_at` | 書いていない（投入時の既定値になる） |
| `unit.enquete_suspended_chk` | 読んでいない |
| `unit_precondition.precondition_type_id` | 読むが書いていない（ステージングは全件 `100`） |
| `lesson_cate.regist_user_id` → `created_by`、`del_chk` の日時 → `course_categories.deprecated_at` | どちらも NULL（`del_chk = 1` は `active = FALSE` だけ）。テナントごとのカテゴリ（`tenant_course_categories`）には `deprecated_at` を入れる（2026-10-22） |
| `lesson_tag.del_chk` / `icon_file_name` | `del_chk` は読むが使っていない（削除済みも生きているタグと同じ形で入る）。`icon_file_name` は読んでいない（ステージングは削除済み0件） |
| `lecture.pmovie_token` の URL 化 | トークンをそのまま `video_url` に入れている（`video_source = 'pmovie'`。2026-10-22）。新アプリでは再生できない（1-3） |
| `payment_item.display_chk = 2`（一覧と購入画面に出さない） | `listed = FALSE` にしかならない。「購入画面に出さない」を表す列が無い（ステージング 2 件） |
| `payment_item.extension_type`（期限切れの後も延長できるか） | 受け皿が無い（ステージング 13 件に値） |
| `payment_item` のそのほかの列（初回価格・試用・自動継続・支払い方法など） | `learning_paths` に列が無い。名前・講座・自動継続かは決済の `settings.item` に残る（2026-10-23 から課金の `tenant_plans.settings` には入れない） |

**D. 移さず、一覧（`out/not-migrated.csv`）に出すもの（2026-10-22。理由は 2026-10-23 に改めた）**

| 対象 | 件数（ステージング） | 理由 |
|---|---:|---|
| 削除済みの `payment_item_lesson`（`content.learning_path_courses`） | 618 | **移行対象外**（2026-10-23 決定）。旧で運営がコースから外した講座で、新もコースから外した講座の結び付きは物理削除で持たない。入れると、外した講座まで購入で受講できるようになる。誰に何を渡したかは受講（03）の `learning_path_enrollment_courses` に残している |
| 移行の対象に無い講座を指す `payment_item_lesson` | 1 | 旧データの不整合（2026-10-23 までは課金の `billing.plan_courses` にも同じ行が出ていた） |

### 3.5 検証

| 検証 | 方法 |
|---|---|
| 件数の照合 | 抽出時の件数と投入後の件数を突き合わせる（**講座2,208 / ユニット51,463 が目安**。recademy 単体の実数はダンプで確認） |
| 講座の状態・カテゴリ・削除済みのレッスン・動画の置き場所 | `verify` が旧 DB と直接比べる（販売停止 → `archived`、テナントのカテゴリの結び付き、`lessons.deleted_at`、p-movie の動画が `pmovie` か） |
| コース | `verify` が旧 DB と直接比べる（漏れ・紛れ、名前・価格・状態・一覧への表示・リモートPC、削除されていない結び付き） |
| 見出しブロックの除外 | `lessons` に旧 `unit_type_id=0` 由来の行が無いこと |
| ユニット種別 | `lessons.type` の分布を出し、**全部 `text` になっていないこと**（A20 が効いているか） |
| 点数 | `quiz_attempts` の `score` / `max_score` を数件抽出し、lw2 の画面表示と突き合わせる |
| 合否 | `passed` が当時の `test_pass` と一致すること |
| アンケート回答 | `entity_type` 2（ユニット）が入っていること。**1 / 3 は受け皿が未定**（→ [受講 E7](../03-enrollment/review.md#e7-アンケート回答)） |
| 添削のファイル | 5本使っている添削（実測2件）でファイルが5行あること |
| 画像 | 問題・選択肢・解説の `image_url` が埋まっていること |

---

## 4. ライブ講座（content.4）に固有のこと

**旧「ライブ」区分の移行仕様。** コンテンツ（2）に統合したが、**投入順序と変換の規則が他の3フェーズと大きく違う**ため節を分けてある。

### 4-1. 検証データでの実測

**移行ツールは実装済み**（`content.4`。`migrator/steps/content/live_*.py`）。本書の「ステージング実測」は、**移行ツールを通さず旧 DB に直接クエリして数えた値**。

> **ここの数値は本番ではない。** 2026-09-18 取得のステージングダンプ（`lw2_stg_kiracari_20260918_1946`）を
> ローカルの lw2 に取り込み、`tenant_id = 10`（ReCADemy）で絞って数えたもの。
> **本番の見積もりにこの数値を使わない。** 1-3 の確認は本番ダンプで取り直す。

**本番と違う前提**

- **ステージングのテナントは4件**（`master` / `career` / `career2` / `solastudy`）。本番は73テナント
- **ReCADemy の `tenant_id` が違う。** ステージングは 10（`tenant_code = 'career'`）、本番は 12（`recademy`）
- **件数の桁が違う。** ライブは全テナント合わせて18件しかなく、[逆引き表](../legacy-table-coverage.md)のローカルデータ数（`live_lesson` 746件）とも一桁以上違う

**旧 DB で数えた件数（`tenant_id = 10`）**

| 旧テーブル | 件数 | 内訳 |
|---|---:|---|
| `live_lesson` | 18 | 削除済み3 / オンライン15・教室3 |
| `live_lesson_cate` | 5 | 削除済み0 |
| `live_lesson_lesson_cate` | 6 | **18件中6件のライブにしかカテゴリが付いていない** |
| `live_lesson_group` | **0** | |
| `live_lesson_limit_item` | 50 | |
| `live_lesson_preview` | 1 | |
| `live_lesson_date` | 2,840 | 削除済み817 / 定員 NULL 926 / 個別登録42・連日設定由来2,798 |
| `live_lesson_date_setting` / `_detail` | 86 / 93 | |
| `live_lesson_exclusion_date` | 128 | |
| `live_lesson_date_preview` | 9 | |
| `live_lesson_reserve` | 32 | キャンセル10 / 開催中止2 / 出席3 |
| `config_live_lesson` | 1 | `ticket_cancel_day = 1` / `ticket_cancel_time = 0` |
| `ticket` | 2 | **両方とも同じ名前** |
| `ticket_limit_lesson` | 2 | `live_lesson_id` 3 と 5 を指す |
| `user_ticket` | 8 | 4名 / 計17枚 |
| `month_user_ticket` | 1 | |
| `user_ticket_log` | 34 | `use` 19 / `lesson_cancel` 9 / `create` 4 / `update` 2 |
| `live_lesson_review` | 3 | |
| `coupon_live_lesson` | **0** | |

**1-3 の項目を検証データで取り直したもの**

| 確認 | 実測 |
|---|---|
| `live_lesson_id` と `unit_id` の重なり | **18件中11件**（`unit_id` は 1〜2,100,219,899 の範囲に3,710件） |
| 予約の `(開催回, 会員)` 重複 | **4組8行**（すべて片方が `cancel_chk = 1`） |
| `user_ticket.ticket_id` が NULL | **8件中3件** |
| `user_ticket.ticket_num = 0` | **8件中2件** |
| `live_lesson.item_ticket_price > 0` で `ticket_limit_lesson` が無い | **3件中1件**（`live_lesson_id = 10`） |
| `capacity = 0` / `ends <= starts` / `reserve_date` が NULL | **いずれも0件** |
| 孤児・テナント跨ぎ | **いずれも0件** |
| 1ライブあたりの最大開催回数 | **1,657回**（`live_lesson_id = 11`） |
| 開催回の日時レンジ | 2022-11-07 〜 2026-12-15（過去2,742 / 未来98） |
| 予約のある開催回 | **32件すべて過去** |

**この節の件数は移行ツールを通さず旧 DB に直接クエリして数えた値。** 移行ツールは `content.4` として実装してある（4-2）。
dry-run と、実際に INSERT してロールバックする予行の件数でこの節を取り直すこと（dry-run は INSERT を実行しないため、制約違反は予行でしか出ない）。

---

### 4-2. データ登録順

新環境は**実 FK を持つ**ため順序が強制される。**前のフェーズが終わるまで次に進まない。**

```
前提       foundation.*（tenants / users / グループ / 属性）
           content.1（lesson_types / content_statuses / courses / lessons）
              ↓
content.4  ライブ講座
              content.live_host_course      受け皿講座（商品制限の無いライブを入れる。無ければ作らない）
                ↓
              content.live_lessons          lessons(type=live)。商品制限のあるライブはその講座、無いものは受け皿講座
                ↓
              content.live_lesson_details   live_lessons（代表日時・旧設定・旧 ID）
                ↓
              content.live_reservation_policies  ライブごとの予約・キャンセルの期限（2026-10-22）
                ↓
              content.live_occurrences      live_lesson_occurrences（削除は deleted_at、中止は予約の stop_chk から）
                ↓
              content.live_categories → content.live_category_links
              content.live_group_targets
              content.live_recurrence_rules → content.live_recurrence_details
                → content.live_recurrence_exclusions（(ライブ, 日付) ごとに1行）
              content.live_exclusion_history（除外日の全行を旧の形のまま）
```

**ライブに関わるが、この区分では流さないもの**

| 何が | Step | どこで流すか |
|---|---|---|
| 受け皿講座への全会員の受講登録 | `enrollment.live_host_enrollments` | 受講 `enrollment.1` |
| チケット種別・対象・必要枚数・付与・台帳 | `billing.ticket_types` ほか | 課金 `billing.1` |
| ライブを予約できる商品の全行 | `billing.live_limit_item_history` | 課金 `billing.2`（`plan_id` が商品を指すため） |
| 予約・レビュー | `enrollment.live_reservations` / `enrollment.live_reviews` | 受講 `enrollment.6` |

**順序の根拠**

- **`courses` が先。** `lessons.course_id` は `courses(id)` への FK で **NOT NULL**。**lw2 のライブは講座に属さないため、置き場所の講座は `content.1` で入れた講座か、移行で作る受け皿講座**
- **`live_lessons` は `lessons` の子。** PK が `lesson_id` で `lessons(id)` への FK（`ON DELETE CASCADE`）
- **`live_lesson_occurrences` は `lessons` の子**（`fk_llo_lesson`。school-launcher `20260930013549` で `live_lessons` から付け替わった）。`live_lessons` の行が無いライブ（開催回が 0 件で代表日時が決まらないもの）にも開催回は入れられるが、そういうライブは開催回を持たないので、移す行は変わらない
- **`live_lesson_reservation_policies` もライブのレッスン（`lessons`）の子**
- **カテゴリの割当・公開グループ・連日設定はレッスンを参照する**ので、`content.live_lessons` の後
- **`ticket_type_lessons.lesson_id` と `live_lesson_ticket_requirements.lesson_id` は `lessons` を指す**（`live_lessons` ではない）。`content.4` の後
- **`live_reservations` は開催回と会員の両方に依存する**（`fk_lr_occurrence` / `fk_lr_user`）。**会員は基盤で入っている**

#### 2-2. 実行手順

**フェーズの指定は `区分.番号`**（`content.4`）。

```bash
# 0. 追加スキーマを当てる → 移行先を初期化する（school-launcher のリポジトリで）
#    DDL 一覧: docs/db/02-content/schema-additions.md
make reseed

# 1. 接続と前提を確認する / 実行計画を見る
python -m migrator doctor
python -m migrator plan

# 2. 前提のフェーズが終わっていることを確認する
python -m migrator run --section foundation
python -m migrator run --phase content.1
python -m migrator verify

# 3. 事前検査
python -m migrator preflight

# 4. dry-run
python -m migrator run --dry-run --phase content.4

# 5. 投入
python -m migrator run --phase content.4

# 6. 検証
python -m migrator verify
```

---

### 4-3. データ移行仕様

**カラム単位の仕様は [review.md](review.md) が正。** ここには**複数テーブルに効くもの**と、**取り違えると致命的なもの**だけを置く。

#### 3.1 抽出（extract）

**ライブ固有の絞り込み**

- **`tenant_id` を持つテーブルは直接絞れる**: `live_lesson` / `live_lesson_cate` / `live_lesson_date` / `live_lesson_reserve` / `live_lesson_exclusion_date` / `live_lesson_review` / `config_live_lesson` / `ticket`
- **持たないテーブルは親と join して絞る**。**join を落とすと全73テナントを拾う**
  - `live_lesson_lesson_cate` / `live_lesson_group` / `live_lesson_limit_item` / `live_lesson_date_setting` → `live_lesson`（`live_lesson_id`）
  - `live_lesson_date_setting_detail` → `live_lesson_date_setting` → `live_lesson`（**2段の join**）
  - `ticket_limit_lesson` → `ticket`（`ticket_id`）
  - `user_ticket` / `month_user_ticket` / `user_ticket_log` → `user`（`user_id`）
  - `coupon_live_lesson` → `live_lesson`（`live_lesson_id`）
- **削除済み（`del_chk = 1`）も移す。** ライブは `content_statuses.deleted`、開催回は A25 の `deleted_at` で表す。カテゴリ（`deprecated_at`）と連日設定（`deleted_at`）は、**削除日時ではなく `regist_date` を入れている**（旧の削除日時を読んでいない。2026-10-02 の確認）
- **親のライブが物理削除されている開催回（孤児）は移さず、「移さない行」の一覧に出す**（ステージング0件）
- **プレビュー2表は抽出しない**（`live_lesson_preview` / `live_lesson_date_preview`）
- **除外日と制限商品は全行を旧の形のまま移す**（2026-10-01）。どちらも保存のたびに旧行を `del_chk = 1` にして
  積む作りで、**除外日は 128行のうち110行が削除済み**、**制限商品は 50行のうち45行が削除済み**。
  - 除外日: 新の `live_lesson_recurrence_exclusions` は (ライブ, 日付) で一意なので**組ごとに1行**
    （生きている行があれば生きた行、全部削除済みなら `deleted_at` 付き。実測22組・うち削除済み4組）。
    全行は `live_lesson_exclusion_date_history` に入れる。`exclusion_date` が NULL の行は新の表に入らず、履歴の表にだけ入る（ステージング0件）
  - 制限商品: 置き場所の判定は生きている行だけを見る。全行は `live_lesson_limit_item_history` に入れる（課金の2で流す）

**SELECT してはいけない列**

**なし。** ライブに平文の認証情報は無い。`live_lesson_reserve.verification_key` は
**出席確認に使う照合値**で、パスワードや認証コードの平文ではないため読んでよい。

**事前検査**

| 検査 | 対象 | 判断 |
|---|---|---|
| 重複 | `live_lesson_reserve` の `(live_lesson_date_id, user_id)` | **0件でなければ、どれを残すかが決まっていること**（1-1 の #4）。決まっていなければ止める |
| ID の衝突 | `live_lesson.live_lesson_id` ⇔ `unit.unit_id`（同一テナント） | **重なりがあれば A22（`live_lessons.live_lesson_id`）が必須。** `lessons.unit_id` には入れない |
| NULL | `user_ticket.ticket_id`、`live_lesson_reserve.reserve_date` | 件数を出して `out/not-migrated.csv` の見込みを示す |
| CHECK | `live_lesson_date.capacity = 0`、`live_lesson_date_to <= live_lesson_date_from`、`user_ticket.ticket_num <= 0`、`live_lesson.item_ticket_price < 0` | 0件なら続行。あれば件数を出す |
| 桁溢れ | `live_lesson_url`(1000) / `live_lesson_name`(255) / `live_lesson_cate_name`(200) / `verification_key`(200) | **超過があれば列を広げる**（切り捨てない） |
| コード値の網羅 | `live_lesson_type`（0/1）、`live_lesson_date.date_type`（1/2）、`user_ticket_log.action_type` | **対応表に無い値があれば停止する**（`action_type` はカラムコメントと実データが食い違う） |
| 導出値の一致 | `live_lesson_date.live_lesson_time` ⇔ `(live_lesson_date_to - live_lesson_date_from)` | **食い違う行があれば、どちらが正かを決める**（移さない列だが、開催時間の表示に影響する） |
| 件数 | `live_lesson_group` / `coupon_live_lesson` が0行か | 0行なら実装は通すだけ |

#### 3.2 変換（transform）

| 変換 | 規則 |
|---|---|
| `live_lesson.live_lesson_url` → `occurrences.meeting_url` | **レッスン側の1つの URL を、そのライブの全開催回に複製する。** 開催回ごとに URL を変える概念は旧に無い |
| `live_lesson` の `capacity` / `reserve_start_day` / `reserve_end_day` / `reserve_end_time` | **`capacity` だけ、開催回の値が優先・無ければレッスン側**（`0` は NULL）。**`reserve_opens_at` / `reserve_closes_at` は開催回の値だけから作り、レッスン側での補完は現状していない**（実装が無い。2026-10-02 の確認。ステージングは開催回側の NULL が0件）。レッスン側は「開始の何日前」の `int` で単位が違うので、補完するなら `starts_at` から逆算する。レッスン側の生値は `live_lessons.settings.defaults` に残る |
| `config_live_lesson` → `occurrences.cancel_closes_at` | `starts_at − ticket_cancel_day 日 − ticket_cancel_time 時間`。**テナント設定を開催回ごとの絶対時刻に焼き付ける**。キャンセル不可（`ticket_cancel_chk = 0`）なら `starts_at` |
| `live_lesson.reserve_start_day` / `reserve_end_day` / `reserve_end_time` → `live_lesson_reservation_policies` | **ライブごとの日数をそのまま入れる**（2026-10-22）。`reserve_open_days_before` / `reserve_close_days_before` / `reserve_close_hours_before`（`reserve_end_time` は「時間前」。`LiveLessonModel.class.php:1262`）。新は、運営が開催回を編集するとここから開催回の日時を計算し直す |
| `config_live_lesson.ticket_cancel_day` → `live_lesson_reservation_policies.cancel_days_before` | **テナントの値を各ライブに入れる**（2026-10-22 決定）。**日数で表せないときは NULL**（警告を出す）: `ticket_cancel_time` が 0 以外のとき、および**キャンセル不可（`ticket_cancel_chk = 0`）のとき**（旧は受講者がキャンセルできない。`default/LiveLessonController.php:749`。新の NULL は「開始まで可」で、「不可」を表す値が無い）。ステージングは `ticket_cancel_chk = 1`・1 日前・0 時間で当たらない |
| `live_lesson_date.reserve_start_day`（**date**）→ `reserve_opens_at` | **JST の 00:00:00 として UTC に変換する。** 素で入れると**前日15:00**になり予約開始が1日早まる |
| `user_ticket.ticket_end_date`（**date**）→ `expires_at` | **JST の 23:59:59 として変換する**（終了日なので日の終わりを補う） |
| `live_lesson_reserve` の3フラグ → `live_reservations.status` | `stop_chk=1` → **受講 A5 の新値 `host_canceled`**、`cancel_chk=1` → `canceled`、`attendance_chk=1` → `attended`、いずれでもなく**開催回が過去** → `no_show`、**未来** → `reserved`。**元の3フラグは `settings` に残す** |
| `live_lesson_reserve.stop_chk` → `occurrences.canceled_at` | **予約から開催回へ持ち上げる。** `stop_chk = 1` の予約がある開催回に中止時刻を入れる |
| `live_lesson_date.del_chk` → `occurrences.deleted_at` | **`canceled_at` ではない**（A25） |
| `live_lesson.valid_chk` / `del_chk` → `lessons.status` | **`del_chk` を優先。** `del_chk=1` → `deleted`（`lessons.deleted_at` も入れる。2026-10-22）、`valid_chk=1` → `published`、それ以外 → `draft` |
| `live_lesson.item_ticket_price` → `live_lesson_ticket_requirements` | **`0` なら行を作らない**（`chk_lltr_cost` に当たる）。種別は `ticket_limit_lesson` から逆引きする |
| `user_ticket.ticket_num` → `quantity` / `remaining_quantity` | **両方に同じ値**。`source = 'manual'`、`note = 'lw2 移行時点の残高'` |
| `ticket.del_chk` → `ticket_types.active` / `deprecated_at` | `del_chk=1` → `active = FALSE` + `deprecated_at` |
| 予約 → `ticket_ledger_entries`（`consumed`） | **席を占める予約**（`reserved` / `attended`）で、ライブが `item_ticket_price > 0` のものに1行以上作る。枚数は `item_ticket_price`、付与は**アプリと同じ規則（期限の近い順）**で選び、**複数にまたがるなら分割して1付与1行**。**`remaining_quantity` は減らさない** — lw2 の `user_ticket.ticket_num` は**すでに引かれたあとの残高**なので、ここで引くと二重に減る |

> **取り違え注意**
> - **`live_lessons.scheduled_at` は `timestamp`、`live_lesson_occurrences.*` は `datetime(3)`。** 同じ区分の中で TZ の扱いが逆になる。**`timestamp` はセッション TZ で自動変換され、`datetime(3)` はされない**（[共通仕様](../../migration-spec.md)）
> - **`live_lesson_url`（Zoom などの会議 URL）と `live_lessons.live_room_id`（LiveKit のルーム）は別物。** 取り違えると会議 URL が消える
> - **`del_chk`（削除）と `stop_chk`（開催中止）は別。** 混ぜると受講者の履歴に「中止された」と見える
> - **`user_ticket_log.ticket_type` は `ticket.ticket_type` を指し、`ticket_id` ではない。** ID として扱うと別のチケットに結びつく

#### 3.3 投入（load）

- **冪等性**: 決定論 ULID と業務キーで担保する
  - `lessons`(type=live) / `live_lessons` — `live_lesson.live_lesson_id`（**`lessons.unit_id` には入れず、`live_lessons.live_lesson_id` に入れる**）
  - `live_lesson_occurrences` — `live_lesson_date.live_lesson_date_id`
  - `live_reservations` — **重複を畳んだあとの `(live_lesson_date_id, user_id)`**。残す行が変わると ID も変わるので、**畳み方を決めてから流す**
  - `ticket_grants` — `user_ticket` の `(user_id, ticket_id, authority_id)`（旧 UNIQUE）
- **受け皿 course の ULID を後から変えない。** 固定のキー `HOST_COURSE_KEY = "lw2-live-host"`（`live_courses.py`）から採番して実装してある（lw2 に対応する行が無いため）。キーを変えると**受け皿に置いた全ライブの `course_id` が変わる**
- **エラー時**: フェーズ単位でやり直す。**開催回だけ入って予約が入っていない状態で次に進まない**

#### 3.4 移行の対象外

**A. 移行できないもの**

| 対象 | なぜ移行できないか |
|---|---|
| `user_ticket_log` 全体 | **`ticket_ledger_entries.grant_id`（NOT NULL）を決められない。** 旧ログは「どの付与に対する増減か」を持たず、参照するのは種別コード（`ticket_type`）だけで `ticket_id` すら無い。**増減の符号も持たない**（`ticket_num` は残高のスナップショットで、`use` の行は NULL）。再生すると残高の正本（`user_ticket.ticket_num`）と必ず食い違う |
| `live_lesson_date.live_lesson_time` | **`starts_at` / `ends_at` からの導出値**で、独立した情報を持たない |

**B. 方針として移行しないもの**

| 対象 | 理由 |
|---|---|
| `live_lesson_preview` / `live_lesson_date_preview` | **UI の一時状態。** 編集中の内容を `preview_key` で保持しているだけで、保存すると本体に反映される |
| `live_lesson.facility_id` の参照先（`facility` テーブル） | **集合研修（X01）で対象外**（未コミット）。**施設名は文字列で残す** |
| `live_lesson.live_lesson_cate_id` | **ステージング実測で全件が NULL か `0`。** 同じ意味の中間表（`live_lesson_lesson_cate`）が使われている |
| `ticket_limit_lesson.del_chk = 1` の行 | 中間表なので、**行が無いことで「割り当てが無い」を表現できる** |
| `course_ticket_grants`（新側） | 旧に対応データが無い。**空で始める** |
| `coupon_live_lesson` | **クーポン本体が課金区分（未コミット）。** そちらと合わせて決める |

#### 3.5 検証

**投入後に必ず通す。**

| 検証 | 方法 |
|---|---|
| 件数の照合 | 抽出時の件数と投入後の件数を突き合わせる。**`out/not-migrated.csv` の件数を足すと一致すること** |
| 階層 | `lessons` のうち `type = 'live'` の行がすべて `live_lessons` に対応行を持つこと |
| 旧 ID | **`lessons.unit_id` にライブ由来の値が入っていないこと**（オンデマンドの `unit_id` と衝突するため） |
| 開催回 | `live_lesson_occurrences` の件数と、旧 `live_lesson_date`（削除済みを含む）の件数が一致すること |
| 予約の期限 | 全ライブに `live_lesson_reservation_policies` が1行あり、日数が旧 `live_lesson` と一致すること（`verify`） |
| 削除と中止 | **`deleted_at` が入った行と `canceled_at` が入った行が混ざっていないこと。** 旧 `del_chk = 1` の817件が `canceled_at` に入っていたら誤り |
| 予約の状態 | `live_reservations.status` の分布を出し、**全部 `reserved` になっていないこと**（受講 A5 が効いているか） |
| 日時 | `live_lessons.scheduled_at`（timestamp）と `live_lesson_occurrences.starts_at`（datetime(3)）を数件抽出し、**JST に戻して旧の値と一致すること**（変換の流儀が2つあるため） |
| リマインド | **過去の開催回の予約で `reminded_at` が NULL の行が0件であること**（cutover 後の再送防止） |
| チケット残高 | 会員ごとの `SUM(ticket_grants.remaining_quantity)` が、旧 `SUM(user_ticket.ticket_num)` と一致すること（**移らなかった行の分を差し引いて**） |
| テナント | ライブ・開催回・予約・チケットのすべてで、`tenant_id` が移行対象テナント1件だけであること |

---

---

## 未確定として残っているもの

| 項目 | 状態 |
|---|---|
| 運営への確認事項 | **1-1 には未決を置いていない。** この区分の分も [open-questions.md](../open-questions.md) にまとめてある |
| バッジ（定義・付与実績とも） | **移行対象外**（2026-09-28 決定。→ [対象外](../06-out-of-scope/breakdown.md#決定で対象外にしたもの)） |
| `cmd/import-certificates` との役割分担 | 修了証を二重投入しないための切り分け |

---

# ライブ講座（2-4）

> **旧 `03-live` の内容をここに統合した。** 移行計画ではライブ講座はコンテンツの4番目。
> **予約は受講（3-6）、チケットは課金（4-1）** に分かれているので、そちらは各区分の移行仕様を見ること。

**ライブ講座（content.4）**

| 項目 | 状態 |
|---|---|
| **`scheduled_at` が古くなる**（school-launcher 側の課題） | ダッシュボードの「今日のライブ」は **`live_lessons.scheduled_at` だけを見ており、`live_lesson_occurrences` を見ていない**（`dashboard_repo.go: ListTodaysLiveLessons`）。移行時は直近の開催予定日を入れるが、**誰も更新しないので翌日には古くなる**。1ライブが最大1,657回の開催を持つため、**大半の開催回がダッシュボードに出ない**。**開催回から導出するか、ダッシュボードを `live_lesson_occurrences` 参照に変えるか**は移行の範囲外 |
| 予約の重複をどう畳むか | **1-1 の #4。** 決まらないと該当する会員の予約が丸ごと移らない |
| チケット消費履歴の提供形式 | **1-1 の #7。** 台帳には再生できないので、必要なら参照専用 CSV |
| 課金区分（未コミット）への依存2件 | `live_lesson_limit_item.item_id` と `user_ticket.authority_id`。**その区分の移行後に解決する** |
| 移行ツールの実装 | **実装済み**（`content.4`。2026-10-02 の確認）。予約・チケットは受講・課金の区分で流す（4-2） |
