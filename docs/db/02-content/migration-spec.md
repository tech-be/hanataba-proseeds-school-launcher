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
| 見出しブロック（`unit_type_id=0`） | **`lessons` に入れない**（ETL設計 §5-0）。除外しないと FK 違反 |
| カテゴリ未設定の講座（235件中142件） | **そのまま移す**（`courses.category` は NULL 可）。旧の状態をそのまま写すだけで、**カテゴリを整備するかは移行とは別の作業**。cutover 前に「講座一覧の絞り込みが半分以上で効かない」ことは伝える |
| 模試（`is_mock_test` ほか） | **移行しない。** 対象外（未コミット）区分（X02） |
| 更新履歴3件（計300万行） | **移行しない。** 受験中の作業データで、採点時に本テーブルへコピーされる。**cutover 時点の中断中の受験だけは失われる** |
| 動画の配信先 | **`lecture_path.pc_path` を `video_lessons.video_url` に移す。** `lecture` に URL 列は無いが、**別テーブル `lecture_path` が配信先を持つ**（recademy 2,559行。URL 1,171 / 相対パス 44 / 空 1,344）。`pmovie_chk` が立っていない動画はこちらで配信している |
| 画像（問題22列・設問21列） | **移す。** L9 でファイルを移送し `image_url` に入れる（A7 / A12） |
| 提出ファイル・配布ファイル | **5本とも移す**（`submission_files` / `assignment_materials`）。1本に畳まない（A13 / A14） |
| ユニットの順序制御・免除 | **移す。** `lesson_preconditions` / `lesson_exemptions` を追加する（A15） |
| アンケート回答の `entity_type` 1/3（お知らせ・レポート添付） | **受講（3）の担当。** 列（A12）だけでは移せない — `survey_responses.lesson_id` が NOT NULL なので、行き先を設計し直す（→ [受講 E7](../03-enrollment/review.md#e7-アンケート回答)） |

**データの持ち方（畳まない・元の粒度を保つ）**

| 事項 | 決定 |
|---|---|
| ユニットの種別 | **畳まない。** `lesson_types` に `quiz` / `assignment` / `document` / **`discussion`** / **`skill_check`** を追加する（A20）。7・8 は `UnitConstants.php` に無く、**`ShareController` / `UnitController` に定数がある**（`UNIT_TYPE_DISCUSSION` / `UNIT_TYPE_SKILL`）。正規の種別で、`LessonController` も進捗の更新対象にしている |
| ディスカッション・スキル診断の中身 | **ユニットは移すが、中身はこの区分の範囲外。** 投稿（`discussion` / `discussion_board` / `discussion_board_comment`）は[逆引き表](../legacy-table-coverage.md)で**区分が未分類**、診断結果（`public_learning_skill_unit*`）は**就職支援（07）**。**その区分を移すまで中身は空のまま**（ステージング実測でユニット22件） |
| 出題条件（`test_sub`） | **固定リストに展開しない。** `quiz_question_rules` と問題バンクを追加して条件のまま移す（A6） |
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
| 未提出の課題（`submissions.submitted_at` が NOT NULL） | **NULL 可に変更する**（A21）。提出日時を NULL にして「未提出」を表現する。**制約を緩める判断なので、[確認事項](../open-questions.md)で意図を確認してから実施する** |
| 発行済み修了証の発行者名 | **`certificates.issuer_name` は NOT NULL**（発行時点の値を凍結する列）。**テナントの設定側 `certificate_settings.issuer_name` は NULL 可**で「NULL なら `tenants.name`」という別の仕様。**取り違えない** |

**暫定対応（2026-09-23 決定）**

**本決まりではない。** 対応表やデータが届くまでの仮置きで、**届いたら差し替える**。
仮データを入れた行は**あとで特定できる必要がある**ので、入れた値と件数を記録する。

| 事項 | 暫定対応 |
|---|---|
| 講座の講師（`courses.instructor_id` が NOT NULL） | **代理講師の `users` 行を1件作り、全講座に割り当てる**（A21）。対応表を受け取ってから付け替え、**代理講師のままの講座が0件になったことを確認する** |
| 講座の価格 | **仮データを入れる。** 対応表を受け取ってから差し替える。**入れる値は運営と決める**（0 円は「無料」と区別がつかない） |
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
| 削除済みのライブ・開催回 | **移す。** ライブは `lessons.status = 'deleted'`、開催回は **`deleted_at` を追加**して表す（A5）。ステージング実測でライブ3件 / 開催回817件（29%） |
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
| ライブの旧 ID | **`live_lessons.legacy_id` に持つ**（A1）。`lessons.legacy_id` はオンデマンドが `unit.unit_id` で使用済みで、**同じ列に入れると衝突する**（ステージング実測 18件中11件）。**`uk_lessons_legacy` は外さない** |
| 削除と中止 | **別の軸として持つ。** `live_lesson_date.del_chk` → **`deleted_at`（追加）**、開催の中止 → `canceled_at`。**混ぜると受講者の履歴に「中止された」と見える** |
| 予約の3フラグ | **`status` に畳むが、元の値は残す。** `cancel_chk` / `attendance_chk` / `stop_chk` を A7 の `live_reservations.settings` に保持する |
| 開催中止で不成立になった予約 | **`live_reservation_statuses` に値を1つ足す**（A7）。既存4値（`reserved`/`canceled`/`attended`/`no_show`）では**受講者都合のキャンセルと区別できない** |
| リマインドの送信可否 | **`live_lesson_occurrences.remind_enabled` を追加する**（A5）。旧 `mail_send_chk` を移す |
| 連日設定・除外日 | **3表をセットで移す**（A6。実測 86 / 93 / 128件）。**片方だけ移すとルールの意味が変わる**（除外日だけ残ると、何を除外しているのか分からない）。**開催回を自動生成する機能を作るかは移行とは別の判断** |
| リマインドの送信可否（再掲） | **`live_lesson_occurrences.remind_enabled` に移す**（A5）。**送る／送らないを判定する機能を作るかは移行とは別の判断** |
| チケット種別の名前が重複 | **そのまま移す。** ステージングの2件は同名（「3級マンツーマンレッスン専用チケット」）。`ticket_types.name` に UNIQUE は無いので投入は止まらない。**運営画面で区別が付かないことは cutover 前に伝える** |
| ライブのカテゴリ | **多対多のまま移す**（A2）。`live_lesson.live_lesson_cate_id` ではなく `live_lesson_lesson_cate` が正 |
| チケット残高 | **残高1行 = 付与1行。** `quantity = remaining_quantity = ticket_num` とし、`note` に「lw2 移行時点の残高」と書く（ETL設計 §5-6）。**「何枚付与されて何枚使ったか」は旧が持たないので表現しない** |
| チケットの出どころ | **すべて `manual`。** `ticket_grant_sources` の既存3値から選ぶ |
| **消費の台帳行（2026-09-24 決定）** | **移行する予約に対して `consumed` の台帳行を作る。** lw2 の `user_ticket_log` は再生しないが、**台帳行が無いとキャンセルしてもチケットが戻らない**（`RefundForReservation` が `ticket_ledger_entries` から「その予約で何枚引いたか」を読む）。会員と枚数だけでは足りない理由は2つ — **①予約後に `cost` が変わっている可能性がある**（実装が現在の `cost` を見ないのはこのため）**②消費は複数の付与にまたがりうる**（`AllocateForConsumption` が期限の近い順に割り振る） |
| ライブ1件あたりの必要枚数 | **`item_ticket_price = 0` は行を作らない**（`chk_lltr_cost (cost >= 1)` に当たるため）。**行が無い = チケット不要**。ステージング実測は 18件中15件 |

**制約に当たる行の扱い**（[共通仕様 3.5.1](../../migration-spec.md#351-not-null--unique--外部キーに当たる行)）

| 事項 | 決定 |
|---|---|
| **新環境の制約を緩めない** | **2026-09-23 決定（オンデマンドと同じ）。** 旧データが入らない箇所でも `NOT NULL` / `UNIQUE` / `CHECK` を外さない。**例外を作る場合は 1-1 で意図を確認してから** |
| 当たった行の処理 | **移さず `out/not-migrated.csv` に出し、暫定対応で直してから再実行する。** **どこが当たるか**は [確認事項](../open-questions.md) に挙げた12件 |
| migration の実装 | **school-launcher 側で行う。** [schema-additions.md](schema-additions.md) は当てる内容と順序を示すもので、ファイルの作成・適用は school-launcher のリポジトリの作業 |
| 巻き添えの扱い | **大本を直せば消えるので、子を個別に直さない。** 削除済みのライブにぶら下がる開催回44件、削除済みの開催回にぶら下がる予約3件がこれに当たる（いずれも親を移すので巻き添えにはならない） |

**暫定対応**

**本決まりではない。** 対応表やデータが届くまでの仮置きで、**届いたら差し替える**。
仮データを入れた行は**あとで特定できる必要がある**ので、入れた値と件数を記録する。

| 事項 | 暫定対応 |
|---|---|
| ライブの受け皿 course | **未決（1-1 の #1）。** 決まるまで実装しない。**暫定で案B を仮置きすると、案A に変えるとき全ライブの ULID が変わる** |
| `live_lessons.scheduled_at` | **未決（1-1 の #2）。** 同上 |
| ライブの必要枚数の種別 | `ticket_limit_lesson` から逆引きできないライブは、**`live_lesson_ticket_requirements` の行を作らない**（チケット不要として扱う）。**対象を記録し、あとで運営が付け直せるようにする** |

**実行の段取り**

| 事項 | 決定 |
|---|---|
| 前提区分 | **基盤（`foundation.*`）と オンデマンドのフェーズ1〜4**（`lesson_types` / `content_statuses` / `courses` / `lessons`）が先。**受講（04）・課金（05）には依存しない** |
| 課金区分への依存 | **`live_lesson_limit_item.item_id` と `user_ticket.authority_id` の参照先は課金区分（未コミット）。** 旧 ID を保持する形で先に入れ、**課金の移行後に解決する** |

### 1-4. 本番ダンプ受領後に確認すること

> **制約を緩めないと決めたため、下の3件は「何件が移らないか」を数える項目**になる。
> 判断は済んでいるが、**規模は運営に伝える必要がある**。

| 確認 | 効く先 |
|---|---|
| 1ユニットに複数のテストを持つ件数（`test.unit_id` の重複） | 2件目以降のテストは移らない |
| `report_answer.submit_date` が NULL の件数 | その未提出データは移らない |

| 確認 | 効く先 |
|---|---|
| 1ユニットに複数の `test` があるか | `quizzes` の UNIQUE (tenant_id, lesson_id)。あれば UNIQUE を外す |
| 1ユニットに複数の `lecture` があるか | `video_lessons.lesson_id` が PK。実測では最大1 |
| 同じ `enquete` を複数ユニットが参照しているか | `survey_lessons.lesson_id` が PK |
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
| `live_lesson_id` と `unit_id` が重なる件数 | `uk_lessons_legacy`。**`live_lessons.legacy_id`（A1）が要るかの判断**（ステージング 18件中11件） |
| `live_lesson_url` に1000文字超があるか | `live_lesson_occurrences.meeting_url` varchar(1000)。**切り捨てない**（ステージング最大77文字） |
| `live_lesson_name` に255文字超があるか | `lessons.title` varchar(255)（ステージング最大15文字） |
| `live_lesson_cate_name` に200文字超があるか | A2 の `live_lesson_categories.name`（ステージング実測は全件短い） |
| `live_lesson.live_lesson_cate_id` に値が入っているか | 入っていれば移す（ステージングは全件 NULL か `0`） |
| **本番の `facility` に住所・TEL・URL が入っているか** | ステージングは施設1件（「ご自身のパソコン」）で**すべて空**。**住所や地図が要る施設があれば、`settings` の文字列では足りず別表の追加が要る** |
| `live_lesson_type = 1`（教室レッスン）の件数 | ステージング3件。**本番で対面の教室が多ければ、会場の持ち方を決め直す** |
| `live_lesson_group` / `coupon_live_lesson` の件数 | **ステージングは両方0件**で、実装の検証になっていない |
| `live_lesson_reserve.change_reserve_id` / `base_reserve_id` の件数 | 振替予約の有無（ステージング0件）。あれば A7 に列を足す |
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
> 混ざっており、いまの区分2の実測とは一致しない。**現在の値は
> [1-5 実測](#1-5-検証データでの実測2026-09-24-実施)と[受講の移行仕様](../03-enrollment/migration-spec.md)を見る**
> （2026-09-26 の通し実行で 基盤 35,580 / コンテンツ 47,118 / 受講 28,806 行）。

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
| **同じアンケートを複数ユニットが参照する** | 7件 | **ユニットごとに複製**して移す。`uk_survey_pages` を `(tenant_id, legacy_id)` → **`(tenant_id, lesson_id, legacy_id)`** に変えた（変える前は89件中60件が落ちた） |
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
| `submission_feedbacks` / `submission_files` | 40 | 上の巻き添え（提出が移らないので添削・ファイルも移らない） |
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
ondemand.1  マスタの追加値 ※ FK の参照先をそろえる
              ├ content_statuses に deleted
              ├ lesson_types に quiz / assignment / document / discussion / skill_check
              ├ quiz_question_types に free_text
              └ survey_question_kinds に file_upload
              ↓
ondemand.2  代理講師 → course_categories → courses
              ↓  **course_categories は courses より先**（courses.category が FK）
ondemand.3  lessons（見出しブロックを除く）→ video_lessons
              ↓
ondemand.4  テスト定義
              quiz_question_categories → quiz_question_banks → quizzes
                → quiz_question_rules → quiz_questions → quiz_options
              ↓
ondemand.5  アンケート・課題定義
              ├ survey_lessons → survey_pages → survey_questions → survey_question_options
              └ assignments → assignment_materials
              ↓
ondemand.6  受講実績
              ├ quiz_attempts → quiz_answers → quiz_answer_selected_options
              ├ survey_responses → survey_answers → survey_answer_selected_options
              └ submissions → submission_files → submission_feedbacks
              ↓
ondemand.7  certificate_settings → certificates → certificate_events
              ↓
ondemand.8  教材・受講制御
              ├ library_folders → library_materials → library_material_lesson_targets
              └ lesson_preconditions
```

> **番号は `migrator/phases/registry.py` と一致させること。** 指定は `--phase ondemand.4` の形。

**順序の根拠**

- **マスタが先。** `content_statuses` / `lesson_types` / `quiz_question_types` / `survey_question_kinds` はいずれも FK の参照先で、`tenant_id` を持たないグローバルマスタ
- **`course_categories` は `courses` より先。** `courses.category` は `course_categories(code)` への FK で、**新規 DB では空**（既存 `courses.category` からの吸い上げでしか作られない）
- **`courses` は `lessons` より先**（`lessons.course_id`）、**`lessons` は quizzes / surveys / assignments より先**
- **実績は定義の後。** `quiz_attempts.quiz_id` / `submissions.assignment_id` が参照する
- **実績は受講区分（04）を待たない。** `quiz_attempts` / `survey_responses` / `submissions` は
  いずれも `enrollments` を参照しない（実装時に確認）。旧 `user_learning_test` から会員を引くのに
  `user_learning_unit` → `user_learning_lesson` の2段を**移行元で**たどるだけで足りる
- **教材・受講制御（8）は最後でよい。** `lessons` にしか依存しないので、どの段の後でも動く
- **R3（テスト中断・再開）はこの図に入れない。** 受験中の作業データなので移行しない

## 2-2. 実行手順

**フェーズの指定は `区分.番号`**（`ondemand.3` など）。**フェーズは区切って流す。**

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
python -m migrator run --dry-run --phase ondemand.1
python -m migrator run --dry-run --section ondemand

# 5. 本番投入。フェーズごとに結果を見てから次へ
python -m migrator run --phase ondemand.1
python -m migrator run --phase ondemand.2
...

# 6. 検証
python -m migrator verify
```

> **1,070万行のフェーズ6は、時間とバッチサイズを見てから流す。** dry-run で件数を確認し、必要なら投入を分割する。

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
- **削除済み（`del_chk = 1`）も移す。** `content_statuses` に `deleted` を追加して表現する

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
| `unit.unit_type_id` → `lessons.type` | **畳まない。** 1→`video`、2→`quiz`、3→`survey`、4→`assignment`、6→`document`、**7→`discussion`**、**8→`skill_check`**。**0=見出しは除外**、5=集合研修は対象外区分。**対応表に無い値は止める**（黙って `text` に倒さない） |
| `unit.sort_no` → `sort_order` | 見出しを除いた分を**講座ごとに採番し直す**（並び順は保つ） |
| `question.selection1..20` → `quiz_options` | 横持ち → 縦持ち。有効数は `selection_num` |
| `question.answer` → `quiz_options.is_correct` | 正解文字列を選択肢と突き合わせてフラグを立てる |
| `sum_score` / `total_score` → `score` / `max_score` | **`test_score`（百分率）は使わない。** `sum_score` が素点、`total_score` が満点 |
| `exam_limit_times`（**分**）→ `time_limit_sec`（**秒**） | **×60 で換算する。** `test_time` は秒なのでそのまま |
| `question_answer` → `quiz_answer_selected_options` | **`|` で分割**し、`quiz_options` と突き合わせる。`question_type_id=3` は判定が逆 |
| `enquete_answer.answer`(JSON) → `survey_answers` | キーは `answer_<enquete_question_id>`（ETL設計 §5-5）。設問タイプごとに入れる列が変わる |
| `test_sub_question` の ID | **旧 ID を引き継がない**（採番が枯渇・履歴断裂）。`(test_id, question_id, 並び順)` から採番する |
| 画像ファイル名 → `image_url` | L9 でファイルを移送し、移送先の URL を入れる |
| `test_start_time` / `test_end_time` → `started_at` / `completed_at` | **`timestamp` 列なので JST naive → UTC に変換してから書く** |

> **取り違え注意**
> - **`open_period` の単位**（月→日）。受講期間が 1/30 になる
> > > - **`limit_Date` は大文字混じり**。`limit_date` と書くと取りこぼす

### 3.3 投入（load）

- **冪等性**: 決定論 ULID と業務キーの UNIQUE で担保する。**`quiz_attempts` には業務的な一意キーが無く、決定論 ULID だけが頼り**なので、採番の入力（entity 名）を変えない
- **大きいテーブルは分割する**: `user_learning_test_sub`（1,070万行）/ `test_sub_question`（65万行）。**dry-run で件数と所要を確認してから流す**
- **エラー時**: フェーズ単位でやり直す。定義系を部分投入したまま実績系に進まない

### 3.4 移行の対象外

**A. 移行できないもの**

| 対象 | なぜ移行できないか |
|---|---|
| `remote_api_token` 全体 | **発行中の一時トークン**で、移した時点で無効。新環境は予約システムで概念も違う。ただし `lesson_id` は `courses.remote_pc_enabled` の初期値に使う |
| `drive.dir_name` | ファイルパスそのもの。**L9 の移送で URL に置き換わる**ため、移送後は参照されない（移送の入力としては使う） |

**B. 方針として移行しないもの**

| 対象 | 理由 |
|---|---|
| `test.is_mock_test` / `mock_post_message` / `mark_type_id` | **模試は対象外（未コミット）区分**（X02） |
| `library_downloads` | 新環境側の**純ログ**。旧に対応データも無く、空で始める |

### 3.5 検証

| 検証 | 方法 |
|---|---|
| 件数の照合 | 抽出時の件数と投入後の件数を突き合わせる（**講座2,208 / ユニット51,463 が目安**。recademy 単体の実数はダンプで確認） |
| 見出しブロックの除外 | `lessons` に旧 `unit_type_id=0` 由来の行が無いこと |
| ユニット種別 | `lessons.type` の分布を出し、**全部 `text` になっていないこと**（A20 が効いているか） |
| 点数 | `quiz_attempts` の `score` / `max_score` を数件抽出し、lw2 の画面表示と突き合わせる |
| 合否 | `passed` が当時の `test_pass` と一致すること |
| アンケート回答 | `entity_type` 2（ユニット）が入っていること。**1 / 3 は受け皿が未定**（→ [受講 E7](../03-enrollment/review.md#e7-アンケート回答)） |
| 提出ファイル | 5本使っている提出（実測2件）でファイルが5行あること |
| 画像 | 問題・選択肢・解説の `image_url` が埋まっていること |

---

## 4. ライブ講座（content.4）に固有のこと

**旧「ライブ」区分の移行仕様。** コンテンツ（2）に統合したが、**投入順序と変換の規則が他の3フェーズと大きく違う**ため節を分けてある。

### 4-1. 検証データでの実測

**dry-run は未実施。** ライブの移行ツールがまだ無い（`migrator/phases/registry.py` で `live` は `pending`）。

本書の「ステージング実測」は、**移行ツールを通さず旧 DB に直接クエリして数えた値**。

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

**実装したら、次を通したうえでこの節を書き直すこと。**

1. `run --dry-run --section live` — 件数と変換結果
2. **実際に INSERT してロールバックする予行** — dry-run は INSERT を実行しないため、
   制約違反はここでしか出ない（基盤では dry-run 通過後の予行で**7件**の違反が出た）

---

### 4-2. データ登録順

新環境は**実 FK を持つ**ため順序が強制される。**前のフェーズが終わるまで次に進まない。**

```
前提       foundation.*（tenants / users / グループ / 属性）
           ondemand.1〜4（lesson_types / content_statuses / courses / lessons）
              ↓
フェーズ0  追加スキーマを当てる（schema-additions.md）
              ↓
フェーズ1  マスタの追加値
              └ live_reservation_statuses に「開催中止で不成立」を1件（A7）
              ↓
フェーズ2  ライブの受け皿
              ├ live_lesson_categories（A2）
              └ courses（ライブ用。案A / 案B）
              ↓
フェーズ3  lessons(type=live) → live_lessons
              ├ live_lesson_category_links（A2）
              ├ live_lesson_group_targets（A3）
              └ live_lesson_item_restrictions（A4）
              ↓
フェーズ4  live_lesson_occurrences
              └ live_lesson_recurrence_rules / _details / _exclusions（A6）
              ↓
フェーズ5  ticket_types → ticket_type_lessons / live_lesson_ticket_requirements
              ↓
フェーズ6  live_reservations
              ↓
フェーズ7  ticket_grants → ticket_ledger_entries（予約ぶんの consumed）→ monthly_ticket_allowances（A9）
              └ live_lesson_reviews（A9）
```

**順序の根拠**

- **`courses` が先。** `lessons.course_id` は `courses(id)` への FK で **NOT NULL**。**lw2 のライブは講座に属さないため、この course は移行で作る**
- **`live_lessons` は `lessons` の子。** PK が `lesson_id` で `lessons(id)` への FK（`ON DELETE CASCADE`）
- **`live_lesson_occurrences` は `live_lessons` の子**（`fk_llo_lesson`）。`live_lessons` が入っていないと1行も入らない
- **`ticket_types` は `ticket_type_lessons` / `live_lesson_ticket_requirements` / `ticket_grants` より先**（3つとも `ticket_type_id` の FK を持つ）
- **`ticket_type_lessons.lesson_id` と `live_lesson_ticket_requirements.lesson_id` は `lessons` を指す**（`live_lessons` ではない）。フェーズ3の後
- **`live_reservations` は開催回と会員の両方に依存する**（`fk_lr_occurrence` / `fk_lr_user`）。**会員は基盤で入っている**
- **`ticket_ledger_entries` はこの図に入れない。** 履歴を再生しない方針のため
- **`live_lesson_item_restrictions`（A4）の `item_id` は課金区分（未コミット）を指す。** 旧 ID を保持する形で入れ、**課金の移行後に解決する**

#### 2-2. 実行手順

**フェーズの指定は `区分.番号`**（`live.3` など）。**フェーズは区切って流す。**

```bash
# 0. 追加スキーマを当てる → 移行先を初期化する（school-launcher のリポジトリで）
#    DDL 一覧: docs/db/02-content/schema-additions.md
make reseed

# 1. 接続と前提を確認する / 実行計画を見る
python -m migrator doctor
python -m migrator plan

# 2. 前提区分が終わっていることを確認する
python -m migrator run --section foundation
python -m migrator run --section ondemand
python -m migrator verify

# 3. 事前検査
python -m migrator preflight

# 4. dry-run。**フェーズ単位で試せる**
python -m migrator run --dry-run --phase live.1
python -m migrator run --dry-run --section live

# 5. 本番投入。フェーズごとに結果を見てから次へ
python -m migrator run --phase live.1
python -m migrator run --phase live.2
...

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
- **削除済み（`del_chk = 1`）も移す。** ライブは `content_statuses.deleted`、開催回は A5 の `deleted_at` で表す
- **プレビュー2表は抽出しない**（`live_lesson_preview` / `live_lesson_date_preview`）
- **除外日と制限商品は `del_chk = 0` の行だけ読む。** どちらも保存のたびに旧行を `del_chk = 1` にして
  積む作りで、**除外日は 128行のうち110行が削除済み**（生きているのは18行）、
  **制限商品は 50行のうち45行が削除済み**（生きているのは5行）。
  全部読むと `uk_llre_lesson_date` に当たり、件数の見積もりも狂う

**SELECT してはいけない列**

**なし。** ライブに平文の認証情報は無い。`live_lesson_reserve.verification_key` は
**出席確認に使う照合値**で、パスワードや認証コードの平文ではないため読んでよい。

**事前検査**

| 検査 | 対象 | 判断 |
|---|---|---|
| 重複 | `live_lesson_reserve` の `(live_lesson_date_id, user_id)` | **0件でなければ、どれを残すかが決まっていること**（1-1 の #4）。決まっていなければ止める |
| ID の衝突 | `live_lesson.live_lesson_id` ⇔ `unit.unit_id`（同一テナント） | **重なりがあれば A1（`live_lessons.legacy_id`）が必須。** `lessons.legacy_id` には入れない |
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
| `live_lesson` の `capacity` / `reserve_start_day` / `reserve_end_day` / `reserve_end_time` | **開催回の値が優先、無ければレッスン側。** ただし**単位が違う** — レッスン側は「開始の何日前」の `int`、開催回側は `date` / `datetime`。レッスン側を使うときは `starts_at` から逆算する |
| `config_live_lesson` → `occurrences.cancel_closes_at` | `starts_at − ticket_cancel_day 日 − ticket_cancel_time 時間`。**テナント設定を開催回ごとの絶対時刻に焼き付ける** |
| `live_lesson_date.reserve_start_day`（**date**）→ `reserve_opens_at` | **JST の 00:00:00 として UTC に変換する。** 素で入れると**前日15:00**になり予約開始が1日早まる |
| `user_ticket.ticket_end_date`（**date**）→ `expires_at` | **JST の 23:59:59 として変換する**（終了日なので日の終わりを補う） |
| `live_lesson_reserve` の3フラグ → `live_reservations.status` | `stop_chk=1` → **A7 の新値**、`cancel_chk=1` → `canceled`、`attendance_chk=1` → `attended`、いずれでもなく**開催回が過去** → `no_show`、**未来** → `reserved`。**元の3フラグは `settings` に残す** |
| `live_lesson_reserve.stop_chk` → `occurrences.canceled_at` | **予約から開催回へ持ち上げる。** `stop_chk = 1` の予約がある開催回に中止時刻を入れる |
| `live_lesson_date.del_chk` → `occurrences.deleted_at` | **`canceled_at` ではない**（A5） |
| `live_lesson.valid_chk` / `del_chk` → `lessons.status` | **`del_chk` を優先。** `del_chk=1` → `deleted`、`valid_chk=1` → `published`、それ以外 → `draft` |
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
  - `lessons`(type=live) / `live_lessons` — `live_lesson.live_lesson_id`（**`lessons.legacy_id` には入れず、`live_lessons.legacy_id` に入れる**）
  - `live_lesson_occurrences` — `live_lesson_date.live_lesson_date_id`
  - `live_reservations` — **重複を畳んだあとの `(live_lesson_date_id, user_id)`**。残す行が変わると ID も変わるので、**畳み方を決めてから流す**
  - `ticket_grants` — `user_ticket` の `(user_id, ticket_id, authority_id)`（旧 UNIQUE）
- **受け皿 course の ULID を後から変えない。** 案A / 案B を切り替えると**全ライブの `course_id` が変わる**ので、**決まってから実装する**
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
| 旧 ID | **`lessons.legacy_id` にライブ由来の値が入っていないこと**（オンデマンドの `unit_id` と衝突するため） |
| 開催回 | `live_lesson_occurrences` の件数と、旧 `live_lesson_date`（削除済みを含む）の件数が一致すること |
| 削除と中止 | **`deleted_at` が入った行と `canceled_at` が入った行が混ざっていないこと。** 旧 `del_chk = 1` の817件が `canceled_at` に入っていたら誤り |
| 予約の状態 | `live_reservations.status` の分布を出し、**全部 `reserved` になっていないこと**（A7 が効いているか） |
| 日時 | `live_lessons.scheduled_at`（timestamp）と `live_lesson_occurrences.starts_at`（datetime(3)）を数件抽出し、**JST に戻して旧の値と一致すること**（変換の流儀が2つあるため） |
| リマインド | **過去の開催回の予約で `reminded_at` が NULL の行が0件であること**（cutover 後の再送防止） |
| チケット残高 | 会員ごとの `SUM(ticket_grants.remaining_quantity)` が、旧 `SUM(user_ticket.ticket_num)` と一致すること（**移らなかった行の分を差し引いて**） |
| テナント | ライブ・開催回・予約・チケットのすべてで、`tenant_id` が移行対象テナント1件だけであること |

---

---

## 未確定として残っているもの

| 項目 | 状態 |
|---|---|
| 未決13件 | 1-1 の確認事項。**4・5・6（点数・単位・回答形式）は lw2 の実装を読めば閉じる** |
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
| 移行ツールの実装 | **未着手。** `migrator/phases/registry.py` で `live` は `pending` |
