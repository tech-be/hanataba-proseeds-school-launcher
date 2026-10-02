# コンテンツテーブルの内訳

移行計画の **2 コンテンツ**（オンデマンド講座 / テスト定義・課題定義 / アンケート定義 / ライブ講座）。

[データ種別対照表](../data-type-mapping.md) が分類したデータ種を、**移行計画の区分**で切り直したもの。
移行ツールの**投入順序を決めるための一覧**として使う。新環境は実 FK を持つため、
前の区分が入っていないと1行も入らない。

- 全件の逆引き: [旧環境](../legacy-table-coverage.md) / [新環境](../new-table-coverage.md)
- カラムの突き合わせ: [review.md](review.md)
- 移行の手順: [migration-spec.md](migration-spec.md)

> **基盤（1）が終わっていること。** `courses.tenant_id` / `instructor_id` は `tenants` / `users` を参照する。

> **ローカルデータ数と A·B·C の定義は [README.md](../README.md#共通の列の意味) にある。**
> ローカルデータ数は**全73テナントの合計**で ReCADemy 単体ではない。本文中の「ステージング実測」は
> 2026-09-18 のダンプで `tenant_id = 10`（ReCADemy）に絞って数えた値。

---

## C1 講座・カテゴリ

| 旧テーブル | 新テーブル | データ種 | lw2区分 | ローカルデータ数 | A·B·C | 説明 | 移行の注意 |
|---|---|---|---|---:|:--:|---|---|
| `lesson` | `courses` | O01 講座 | データ | 2,208 | C | 講座の本体 | **`courses.instructor_id` が NOT NULL なのに lw2 に講座単位の講師が無い。** 既定講師を決めないと1行も入らない |
| `lesson_is_used` | `courses.is_used` | O01 講座 | データ | 2,066 | C | 講座の利用可否 | **`lesson_is_used` に行がある講座を `courses.is_used = TRUE` にする**（A1）。`status`（公開状態）とは別の列 |
| `lesson_system` | — | O01 講座 | データ | 243 | C | **講座をテナントに公開する対応表**（列は `lesson_id` / `tenant_id` の2つだけ） | 設定は持っていない。移行では**共有講座（`tenant_id = 0`）のどれを移すかの判定**にだけ使う（`SourceDatabase.shared_lessons`）。行そのものの移し先は無い |
| `lesson_tag` / `lesson_lesson_tag` | `course_tags` / `course_tag_links` | O01 講座 | データ / 中間 | 31 / 281 | C | 講座タグと割当 | A2 で受け皿を足して移す。**`lesson_tag.del_chk` と `icon_file_name` は現状は移していない**（実装が無い。2026-10-02 の確認。ステージングは削除済み0件） |
| `lesson_cate` | `course_categories` | O02 講座カテゴリ | データ | 482 | C | 講座カテゴリ | **移行ツールが `lesson_cate` から作る**（コードは `lw2-<旧テナントID>-<旧ID>`）。`courses` より先に入れる（`courses.category` は FK） |
| — | `content_statuses` | O01 講座 | マスタ | — | — | `courses.status` の値 | migration で投入。`draft`/`published`/`archived` の3値に、**移行で `deleted` を足す**（A3） |
| — | `course_difficulties` | O01 講座 | マスタ | — | — | 講座の難易度 | 旧に対応列なし |

## C2 ユニット・動画

| 旧テーブル | 新テーブル | データ種 | lw2区分 | ローカルデータ数 | A·B·C | 説明 | 移行の注意 |
|---|---|---|---|---:|:--:|---|---|
| `unit` | `lessons` | O04 講義ユニット | データ | 51,463 | C | 講座内のユニット。**`unit_type_id` で動画/テスト/アンケート/課題/見出しを分岐** | **見出しブロック（type=0）は `lessons` に入れない**（2026-09-30 から **`course_chapters`（講座の章）に入れ**、後ろのユニットを `lessons.chapter_id` で所属させる）。 除外しないと FK 違反（ETL設計 §5-0） |
| `lecture` | `video_lessons` | O06 講義動画 | データ | 26,402 | C | 動画の実体 | `video_lessons.lesson_id` が PK なので**1ユニット1動画**。実測は最大1 |
| `lecture_path` | `video_lessons.video_url` | O04 講義ユニット | データ | 26,953 | C | **動画の配信先**（`pc_path` / `smartphone_path`） | **`lecture` に URL 列は無く、配信先はこちら。** recademy 2,559行（URL 1,171 / 相対パス 44 / 空 1,344）。**URL はそのまま移し、相対パスは L9 の移送後に書き換える** |
| `lecture_path_test` | — | O04 講義ユニット | データ | - | — | 動画パスの検証用 | 2026-07-28 以降に追加。実測値なし |
| — | `lesson_types` | O04 講義ユニット | マスタ | — | — | `lessons.type` の値 | migration で投入。既存は `video`/`live`/`text`/`survey`。**移行で `quiz`/`assignment`/`document`/`discussion`/`skill_check` を足す**（A20） |

## C3 受講制御（前提条件・免除）

| 旧テーブル | 新テーブル | データ種 | lw2区分 | ローカルデータ数 | A·B·C | 説明 | 移行の注意 |
|---|---|---|---|---:|:--:|---|---|
| `unit_precondition` | `lesson_preconditions` | O22 前提条件 | 中間 | 7,601 | C | 「このユニットを終えないと次に進めない」 | A15 で受け皿を足して移す。**`precondition_type_id` は現状は移していない**（実装が無い。2026-10-02 の確認。ステージングは37行すべて `100`） |
| `unit_exemption` | — | O23 免除 | 中間 | 226 | C | 「別のユニットで◯点以上なら免除」という規則 | **受け皿なし。現状は移していない**（実装が無い。2026-10-02 の確認。移行ツールは件数を警告に出すだけ。ステージング1行） |

## C4 リモート PC

| 旧テーブル | 新テーブル | データ種 | lw2区分 | ローカルデータ数 | A·B·C | 説明 | 移行の注意 |
|---|---|---|---|---:|:--:|---|---|
| `remote_api_token` | — | O28 リモート PC | データ | 5 | C | 外部 API のトークン | **移行しない**（発行中の一時トークン）。移行ツールはこの表を読まず、`courses.remote_pc_enabled` は全講座 FALSE で入る |
| — | `remote_pc_machines` / `remote_pc_reservations` / `remote_pc_blackouts` / `remote_pc_reservation_statuses` | O28 リモート PC | データ / マスタ | — | — | 新環境のリモート PC 予約 | **旧に対応データが無い新規機能。** 空で始める |

---

# 実績系（8 / 17）

## C5 テスト定義

| 旧テーブル | 新テーブル | データ種 | lw2区分 | ローカルデータ数 | A·B·C | 説明 | 移行の注意 |
|---|---|---|---|---:|:--:|---|---|
| `test` | `quizzes` | O08 テスト定義 | データ | 7,989 | C | テストの本体 | **`quizzes` の UNIQUE (tenant_id, lesson_id)** に、1ユニット複数テストが当たらないか確認する。**削除済み（`del_chk = 1`）も削除の印なしで入る**（下の注） |
| `test_sub` | `quiz_question_rules` | O08 テスト定義 | データ | 8,060 | C | テストの構成（大問）と出題条件 | A8 で受け皿を足し、出題条件のまま移す（固定リストに展開しない） |
| `test_sub_question` | `quiz_questions` | O08 テスト定義 | 中間 | 652,050 | C | 大問と設問の割当 | **旧 ID を引き継げない**（採番の枯渇・履歴断裂。`lw2-migration-tables.md`）。固定出題（`test_sub_type_id` 0 / 1）の分だけ入る |
| `sort_test_sub_question` | — | O08 テスト定義 | データ | 114,747 | C | **受験ごとの出題順**（`token` / `session_id` / `user_id` を持つ） | 受験中の作業データで、定義の並び順ではない。**移行ツールは読まない。** 設問の並び順は `test_sub_question.sort_no` から取る |
| `question` | `quiz_question_banks`（＋ `quiz_questions` / `quiz_options`） | O08 テスト定義 | データ | 64,176 | C | 設問と選択肢 | 本体は問題バンクに入る（A6）。**選択肢と正解はテストに組み込まれた設問（`quiz_options`）にしか入らない。** 画像22列は L9 の移送待ちで `image_url` は空 |
| `question_cate` | `quiz_question_labels` | O08 テスト定義 | データ | 1,407 | C | 設問カテゴリ（問題バンク） | 管理者が作るラベルと同じ表に、旧 ID（`question_cate_id`）付きで移す（A6）。名前が重なる分は区別を付ける |
| — | `quiz_question_types` | O08 テスト定義 | マスタ | — | — | `quiz_questions.type` の値 | migration で投入。`single_choice`/`multiple_choice` の2値に、**移行で `free_text` を足す**（A7） |

> **削除済みの定義は、削除の印なしで入っている。** `test` / `test_sub` / `test_sub_question` / `question` / `question_cate`
> （とアンケートの `enquete` / `enquete_page` / `enquete_question`）は、移行ツールが `del_chk` を読むが使っておらず、
> 生きている行と同じ形で入る。**削除を表す扱いは現状は移していない**（実装が無い。2026-10-02 の確認）。
> ステージング実測（`tenant_id = 10` の定義）で `test` 297件中12件、`test_sub` 285件中4件、`question` 3,880件中5件、
> `enquete` 337件中26件、`enquete_page` 381件中62件、`enquete_question` 309件中101件が削除済み（`question_cate` は0件）。

## C6 課題定義

| 旧テーブル | 新テーブル | データ種 | lw2区分 | ローカルデータ数 | A·B·C | 説明 | 移行の注意 |
|---|---|---|---|---:|:--:|---|---|
| `report` | `assignments` / `assignment_materials` | O18 課題 | データ | 4,684 | C | 課題の定義と配布ファイル | **配布ファイル5本（`report_disp_file_name1..5` / `report_save_file_name1..5`）は `report` 自身の列**で、`assignment_materials` に1本1行で移す（A13） |
| `report_path` | — | O18 課題 | データ | 4,597 | C | **提出後に見せる解説ページの配信先**（`pc_path` / `smartphone_path`。配布ファイルではない） | **受け皿なし。現状は移していない**（実装が無い。2026-10-02 の確認）。ステージング 144行（共有講座の分を含む）、うち `pc_path` が入っているのは23行 |

## C7 アンケート定義

| 旧テーブル | 新テーブル | データ種 | lw2区分 | ローカルデータ数 | A·B·C | 説明 | 移行の注意 |
|---|---|---|---|---:|:--:|---|---|
| `enquete` | `survey_lessons` | O14 アンケート | データ | 7,414 | C | アンケートの本体 | **`survey_lessons.lesson_id` が PK** なので、同じアンケートを複数ユニットが参照しているときは**ユニットごとに複製して移す**（ページ・設問・選択肢も複製）。削除済みも削除の印なしで入る（C5 の注） |
| `enquete_page` | `survey_pages` | O14 アンケート | データ | 8,311 | C | ページ分け | A12 で受け皿を足して移す。設問は `survey_questions.page_id` でページに属する |
| `enquete_question` | `survey_questions` / `survey_question_options` | O14 アンケート | データ | 11,179 | C | 設問と選択肢 | ファイル添付設問（O15）は `file_upload` 種別で移す（A12） |
| — | `survey_question_kinds` | O14 アンケート | マスタ | — | — | 設問種別の値 | migration で投入。**移行で `file_upload` を足す**（A12） |

## C8 ライブ定義

| 旧テーブル | 新テーブル | データ種 | lw2区分 | ローカルデータ数 | A·B·C | 説明 | 移行の注意 |
|---|---|---|---|---:|:--:|---|---|
| `live_lesson` | `lessons`(type=live) + `live_lessons` | L01 ライブ定義 | データ | 746 | C | ライブの本体（35列） | **lw2 のライブは講座に属さない。** `lessons.course_id` が NOT NULL なので、**受け皿の course を作らないと1行も入らない**。`live_lessons.scheduled_at` も NOT NULL だが、旧に対応する単一の日時が無い |
| `live_lesson_cate` | `live_lesson_categories` | L01 ライブ定義 | データ | 65 | C | ライブのカテゴリ | A23 で受け皿を足して移す。**`live_lesson.live_lesson_cate_id` は使われておらず**、実際の紐付けは下の中間表にある |
| `live_lesson_lesson_cate` | `live_lesson_category_links` | L01 ライブ定義 | 中間 | 614 | C | ライブ×カテゴリの割当 | A23。ライブを**多対多**でカテゴリに割り当てたまま移す |
| `live_lesson_group` | `live_lesson_group_targets` | L01 ライブ定義 | データ | 160 | C | ライブの公開グループ | A24。削除済みも `deleted_at` 付きで移す。ステージング実測は**0件** |
| `live_lesson_limit_item` | — | L01 ライブ定義 | データ | 17,345 | C | 予約できる商品の制限 | **受け皿は作らない。** 新環境の同じ仕組みは「講座の受講」で、**商品は実在の講座に1対1で紐づく**。ライブをその講座の配下に置く（ステージング実測は50件中45件が削除済みで、生きているのは5件） |
| `live_lesson_preview` | — | L01 ライブ定義 | データ | 15 | C | 編集中プレビューの一時データ | **UI の一時状態**。`edit_form_data` と同じ性質で移行しない |

## C9 ライブ開催回

| 旧テーブル | 新テーブル | データ種 | lw2区分 | ローカルデータ数 | A·B·C | 説明 | 移行の注意 |
|---|---|---|---|---:|:--:|---|---|
| `live_lesson_date` | `live_lesson_occurrences` | L02 開催日 | データ | 23,324 | C | 開催回の実体（14列 → 15列） | **この区分の主データ。** ステージング実測 2,840件。`datetime(3)` 列なので **UTC に直した値を明示的に書く**。`chk_llo_capacity` / `chk_llo_period` の2つの CHECK がある |
| `live_lesson_date_setting` / `live_lesson_date_setting_detail` | `live_lesson_recurrence_rules` / `live_lesson_recurrence_details` | L02 開催日 | データ | 3,840 / 1,152 | C | 連日設定（開催回の生成ルール）と明細 | A26 で受け皿を足して移す。**生成された開催回は `live_lesson_date` に実体化済み** |
| `live_lesson_exclusion_date` | `live_lesson_recurrence_exclusions` ＋ `live_lesson_exclusion_date_history` | L02 開催日 | データ | 1,096 | C | 開催しない日 | A26。**連日設定と対**。ステージング実測 128行 / (ライブ, 日付) 22組。新の表は組ごとに1行、全行は旧の形のまま履歴の表に入れる |
| `live_lesson_date_preview` | — | L02 開催日 | データ | 134 | C | 編集中プレビューの一時データ | **UI の一時状態**。移行しない |
