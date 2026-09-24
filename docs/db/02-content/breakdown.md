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
| `lesson_is_used` | — | O01 講座 | データ | 2,066 | C | 講座の利用可否 | 受け皿なし。`content_statuses` への写像を決める |
| `lesson_system` | — | O01 講座 | データ | 243 | C | 講座の表示・動作設定 | 受け皿なし。設定の内訳を突き合わせる |
| `lesson_tag` / `lesson_lesson_tag` | — | O01 講座 | データ / 中間 | 31 / 281 | C | 講座タグと割当 | 受け皿なし。`courses` にタグの概念が無い |
| `lesson_cate` | `course_categories` | O02 講座カテゴリ | データ | 482 | C | 講座カテゴリ | **`course_categories` は固定シードで、lesson_cate から作る段が ETL 設計に無い**（`courses.category` は FK） |
| — | `content_statuses` | O01 講座 | マスタ | — | — | `courses.status` の値 | migration で投入。`draft`/`published`/`archived` の3値で **`deleted` が無い** |
| — | `course_difficulties` | O01 講座 | マスタ | — | — | 講座の難易度 | 旧に対応列なし |

## C2 ユニット・動画

| 旧テーブル | 新テーブル | データ種 | lw2区分 | ローカルデータ数 | A·B·C | 説明 | 移行の注意 |
|---|---|---|---|---:|:--:|---|---|
| `unit` | `lessons` | O04 講義ユニット | データ | 51,463 | C | 講座内のユニット。**`unit_type_id` で動画/テスト/アンケート/課題/見出しを分岐** | **見出しブロック（type=0）は `lessons` に入れない。** 除外しないと FK 違反（ETL設計 §5-0） |
| `lecture` | `video_lessons` | O06 講義動画 | データ | 26,402 | C | 動画の実体 | `video_lessons.lesson_id` が PK なので**1ユニット1動画**。実測は最大1 |
| `lecture_path` | `video_lessons.video_url` | O04 講義ユニット | データ | 26,953 | C | **動画の配信先**（`pc_path` / `smartphone_path`） | **`lecture` に URL 列は無く、配信先はこちら。** recademy 2,559行（URL 1,171 / 相対パス 44 / 空 1,344）。**URL はそのまま移し、相対パスは L9 の移送後に書き換える** |
| `lecture_path_test` | — | O04 講義ユニット | データ | - | — | 動画パスの検証用 | 2026-07-28 以降に追加。実測値なし |
| — | `lesson_types` | O04 講義ユニット | マスタ | — | — | `lessons.type` の値 | migration で投入。`video`/`live`/`text` の3値 |

## C3 受講制御（前提条件・免除）

| 旧テーブル | 新テーブル | データ種 | lw2区分 | ローカルデータ数 | A·B·C | 説明 | 移行の注意 |
|---|---|---|---|---:|:--:|---|---|
| `unit_precondition` | — | O22 前提条件 | 中間 | 7,601 | C | 「このユニットを終えないと次に進めない」 | **受け皿なし。** 順序制御が丸ごと落ちる |
| `unit_exemption` | — | O23 免除 | 中間 | 226 | C | 特定受講者のユニット免除 | **受け皿なし** |

## C4 リモート PC

| 旧テーブル | 新テーブル | データ種 | lw2区分 | ローカルデータ数 | A·B·C | 説明 | 移行の注意 |
|---|---|---|---|---:|:--:|---|---|
| `remote_api_token` | — | O28 リモート PC | データ | 5 | C | 外部 API のトークン | **平文の可能性がある。移行できないものとして扱うか要確認** |
| — | `remote_pc_machines` / `remote_pc_reservations` / `remote_pc_blackouts` / `remote_pc_reservation_statuses` | O28 リモート PC | データ / マスタ | — | — | 新環境のリモート PC 予約 | **旧に対応データが無い新規機能。** 空で始める |

---

# 実績系（8 / 17）

## C5 テスト定義

| 旧テーブル | 新テーブル | データ種 | lw2区分 | ローカルデータ数 | A·B·C | 説明 | 移行の注意 |
|---|---|---|---|---:|:--:|---|---|
| `test` | `quizzes` | O08 テスト定義 | データ | 7,989 | C | テストの本体 | **`quizzes` の UNIQUE (tenant_id, lesson_id)** に、1ユニット複数テストが当たらないか確認する |
| `test_sub` | — | O08 テスト定義 | データ | 8,060 | C | テストの構成（大問） | 受け皿なし。`quizzes` は設問を直接持つ |
| `test_sub_question` | `quiz_questions` | O08 テスト定義 | 中間 | 652,050 | C | 大問と設問の割当 | **旧 ID を引き継げない**（採番の枯渇・履歴断裂。`lw2-migration-tables.md`） |
| `sort_test_sub_question` | — | O08 テスト定義 | データ | 114,747 | C | 設問の並び順 | 受け皿なし。`quiz_questions` の並び順に畳む |
| `question` | `quiz_questions` / `quiz_options` | O08 テスト定義 | データ | 64,176 | C | 設問と選択肢 | **画像22列が落ちる**（問題・選択肢・解説の画像） |
| `question_cate` | — | O08 テスト定義 | データ | 1,407 | C | 設問カテゴリ（問題バンク） | 受け皿なし。**カテゴリ×レベルからN問出題**の仕組みが落ちる |
| — | `quiz_question_types` | O08 テスト定義 | マスタ | — | — | `quiz_questions.type` の値 | migration で投入。`single_choice`/`multiple_choice` の2値 |

## C6 課題定義

| 旧テーブル | 新テーブル | データ種 | lw2区分 | ローカルデータ数 | A·B·C | 説明 | 移行の注意 |
|---|---|---|---|---:|:--:|---|---|
| `report` | `assignments` | O18 課題 | データ | 4,684 | C | 課題の定義 | |
| `report_path` | — | O18 課題 | データ | 4,597 | C | **課題の配布ファイル** | 受け皿なし。5本の配布ファイルが落ちる |

## C7 アンケート定義

| 旧テーブル | 新テーブル | データ種 | lw2区分 | ローカルデータ数 | A·B·C | 説明 | 移行の注意 |
|---|---|---|---|---:|:--:|---|---|
| `enquete` | `survey_lessons` | O14 アンケート | データ | 7,414 | C | アンケートの本体 | **`survey_lessons.lesson_id` が PK** なので、同じアンケートを複数ユニットで参照していると入らない |
| `enquete_page` | — | O14 アンケート | データ | 8,311 | C | ページ分け | 受け皿なし。設問の並びに畳む |
| `enquete_question` | `survey_questions` / `survey_question_options` | O14 アンケート | データ | 11,179 | C | 設問と選択肢 | **ファイル添付設問（O15）の受け皿が無い** |
| — | `survey_question_kinds` | O14 アンケート | マスタ | — | — | 設問種別の値 | migration で投入 |

## C8 ライブ定義

| 旧テーブル | 新テーブル | データ種 | lw2区分 | ローカルデータ数 | A·B·C | 説明 | 移行の注意 |
|---|---|---|---|---:|:--:|---|---|
| `live_lesson` | `lessons`(type=live) + `live_lessons` | L01 ライブ定義 | データ | 746 | C | ライブの本体（35列） | **lw2 のライブは講座に属さない。** `lessons.course_id` が NOT NULL なので、**受け皿の course を作らないと1行も入らない**。`live_lessons.scheduled_at` も NOT NULL だが、旧に対応する単一の日時が無い |
| `live_lesson_cate` | — | L01 ライブ定義 | データ | 65 | C | ライブのカテゴリ | 受け皿なし。**`live_lesson.live_lesson_cate_id` は使われておらず**、実際の紐付けは下の中間表にある |
| `live_lesson_lesson_cate` | — | L01 ライブ定義 | 中間 | 614 | C | ライブ×カテゴリの割当 | 受け皿なし。ライブを**多対多**でカテゴリに割り当てる。受け皿 course を案A（カテゴリごと）で作るならここが入力になる |
| `live_lesson_group` | — | L01 ライブ定義 | データ | 160 | C | ライブの公開グループ | 受け皿なし。ステージング実測は**0件** |
| `live_lesson_limit_item` | — | L01 ライブ定義 | データ | 17,345 | C | 予約できる商品の制限 | **受け皿は作らない。** 新環境の同じ仕組みは「講座の受講」で、**商品は実在の講座に1対1で紐づく**。ライブをその講座の配下に置く（ステージング実測は50件中45件が削除済みで、生きているのは5件） |
| `live_lesson_preview` | — | L01 ライブ定義 | データ | 15 | C | 編集中プレビューの一時データ | **UI の一時状態**。`edit_form_data` と同じ性質で移行しない |

## C9 ライブ開催回

| 旧テーブル | 新テーブル | データ種 | lw2区分 | ローカルデータ数 | A·B·C | 説明 | 移行の注意 |
|---|---|---|---|---:|:--:|---|---|
| `live_lesson_date` | `live_lesson_occurrences` | L02 開催日 | データ | 23,324 | C | 開催回の実体（14列 → 15列） | **この区分の主データ。** ステージング実測 2,840件。`datetime(3)` 列なので **UTC に直した値を明示的に書く**。`chk_llo_capacity` / `chk_llo_period` の2つの CHECK がある |
| `live_lesson_date_setting` / `live_lesson_date_setting_detail` | — | L02 開催日 | データ | 3,840 / 1,152 | C | 連日設定（開催回の生成ルール）と明細 | 受け皿なし。**生成された開催回は `live_lesson_date` に実体化済み** |
| `live_lesson_exclusion_date` | — | L02 開催日 | データ | 1,096 | C | 開催しない日 | 受け皿なし。**連日設定と対**で、片方だけ移すと意味が変わる。ステージング実測 128件 |
| `live_lesson_date_preview` | — | L02 開催日 | データ | 134 | C | 編集中プレビューの一時データ | **UI の一時状態**。移行しない |
