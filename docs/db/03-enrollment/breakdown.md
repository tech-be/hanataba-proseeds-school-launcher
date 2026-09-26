# 受講テーブルの内訳

移行計画の **3 受講**（受講権限 / 学習履歴 / テスト結果 / 課題提出 / アンケート回答 / ライブ予約 / 修了証・バッジ）。

[データ種別対照表](../data-type-mapping.md) が分類したデータ種を、**移行計画の区分**で切り直したもの。
移行ツールの**投入順序を決めるための一覧**として使う。新環境は実 FK を持つため、
前の区分が入っていないと1行も入らない。

- 全件の逆引き: [旧環境](../legacy-table-coverage.md) / [新環境](../new-table-coverage.md)
- カラムの突き合わせ: [review.md](review.md)
- 移行の手順: [migration-spec.md](migration-spec.md)

> **コンテンツ（2）が終わっていること。** 実績は定義に紐づく（`quiz_attempts.quiz_id` ほか）。
> **`enrollments` は参照しない**ので、受講権限の本体が未実装でも投入はできる。

> **ローカルデータ数と A·B·C の定義は [README.md](../README.md#共通の列の意味) にある。**
> ローカルデータ数は**全73テナントの合計**で ReCADemy 単体ではない。本文中の「ステージング実測」は
> 2026-09-18 のダンプで `tenant_id = 10`（ReCADemy）に絞って数えた値。

---

## 書くこと

ひな形は [00-template/breakdown.md](../00-template/breakdown.md)。実例は [01 基盤の内訳](../01-foundation/breakdown.md)。

1. 大分類の定義と件数（基盤は「マスター系 / ユーザー系」。区分ごとに適切な軸を選ぶ）
2. 中分類ごとの一覧表（旧テーブル / 新テーブル / データ種 / lw2区分 / ローカルデータ数・A·B·C / 説明 / 移行の注意）
3. 投入順序（新環境は実 FK があるため順序が強制される）
4. 新側に受け皿が無い中分類の名指し

作ったら **[review.md](review.md) の `###` 見出しを、この対応表の行と1対1・同じ順序に揃え直すこと**（現状はデータ種軸）。ひな形は [00-template/review.md](../00-template/review.md)。

## E1 受講権限

| 旧テーブル | 新テーブル | データ種 | lw2区分 | ローカルデータ数 | A·B·C | 説明 | 移行の注意 |
|---|---|---|---|---:|:--:|---|---|
| `payment_item_lesson_authority` | `enrollments` | J01 受講権限 | データ | 7,462 | C | 商品の購入で得た講座の受講権限 | **粒度が違う。** 旧は商品×講座で、同じ (会員, 講座) に複数行ある（実測 3,684 行 → 2,246 組）。**lw2 自身が `GROUP BY user_id, lesson_id` で畳んでいる**ので同じ規則で寄せる。**権限が要るのは 235講座中 71件だけ**で、残りは無料講座 |
| `payment_item_lesson_authority_log` | — | J01 受講権限 | イベント・履歴 | 121,199 | C | 権限の付与・変更の履歴 | **受け皿なし。** 純ログとして移さない |
| — | `enrollment_statuses` / `enrollment_sources` / `enrollment_event_kinds` | J01 | マスタ | — | — | 受講の状態・経路・イベント種別 | シード済み。`source` は `admin` を使う（`manual` は存在しない） |
| — | `enrollment_status_events` | J01 | イベント・履歴 | — | — | 受講状態の履歴 | 旧の履歴を移さないので空で始める |

## E2 学習履歴

| 旧テーブル | 新テーブル | データ種 | lw2区分 | ローカルデータ数 | A·B·C | 説明 | 移行の注意 |
|---|---|---|---|---:|:--:|---|---|
| `user_learning_unit` | `lesson_progress` | J02 ユニット進捗 | データ | 19,009 | C | ユニットごとの学習状況（実測 7,209 行） | **`progress_status` はユニット種別ごとに意味が変わる**（同じ `2` がテストなら「受験中」、アンケートなら「回答済」）。新は `last_position` / `completed_at` の2列しかない |
| `user_learning_lesson` | `enrollments.completed_at` のみ | J03 講座進捗 | データ | 35,532 | C | 講座ごとの学習状況（実測 24,484 行 / 23,956 組） | **母集合にはしない。** 差の 22,833 組は 93% が無料講座で、旧環境でも権限行を持たない（`LessonModel::1363` は「権限がある **OR** 有料講座でない」の2分岐）。修了日だけ使う |
| `user_learning_unit_log` | — | J02 ユニット進捗 | イベント・履歴 | 33,998 | C | 進捗の更新履歴 | **受け皿なし。** 純ログとして移さない |

## E3 テスト受験

| 旧テーブル | 新テーブル | データ種 | lw2区分 | ローカルデータ数 | A·B·C | 説明 | 移行の注意 |
|---|---|---|---|---:|:--:|---|---|
| `user_learning_test` | `quiz_attempts` | O09 テスト受験 | データ | 697,444 | C | 受験の結果 | **`test_score` / `sum_score` / `total_score` の3列のどれを使うかで点数が壊れる** |
| — | `quiz_attempt_statuses` / `quiz_attempt_event_kinds` | O09 | マスタ | — | — | 受験状態・イベント種別 | migration で投入 |
| — | `quiz_attempt_events` | O09 | イベント・履歴 | — | — | 受験のイベント | 旧に対応データなし |

## E4 テスト設問別回答

| 旧テーブル | 新テーブル | データ種 | lw2区分 | ローカルデータ数 | A·B·C | 説明 | 移行の注意 |
|---|---|---|---|---:|:--:|---|---|
| `user_learning_test_sub` | `quiz_answers` / `quiz_answer_selected_options` | O10 設問別回答 | データ | **10,705,972** | C | 設問ごとの回答 | **区分最大のテーブル。** `question_answer` の格納形式を実データで確認する（選択式の復元） |

## E5 テスト中断・再開

| 旧テーブル | 新テーブル | データ種 | lw2区分 | ローカルデータ数 | A·B·C | 説明 | 移行の注意 |
|---|---|---|---|---:|:--:|---|---|
| `user_learning_test_update` | — | O12 中断・再開 | データ | 815,895 | C | 受験の更新履歴 | **受け皿なし** |
| `user_learning_test_sub_update` | — | O12 中断・再開 | データ | 2,212,972 | C | 回答の更新履歴 | **受け皿なし** |
| `user_learning_test_suspend_data` | — | O12 中断・再開 | データ | 326 | C | SCORM の中断データ | **受け皿なし** |

## E6 課題提出・添削

| 旧テーブル | 新テーブル | データ種 | lw2区分 | ローカルデータ数 | A·B·C | 説明 | 移行の注意 |
|---|---|---|---|---:|:--:|---|---|
| `user_learning_report` | `submissions` / `submission_feedbacks` | O18 課題 | データ | 40,098 | C | 提出と添削 | **提出ファイル（O19）の受け皿を確認する** |
| — | `submission_status_events` | O18 | イベント・履歴 | — | — | 提出状態の履歴 | 旧に対応データなし |

## E7 アンケート回答

| 旧テーブル | 新テーブル | データ種 | lw2区分 | ローカルデータ数 | A·B·C | 説明 | 移行の注意 |
|---|---|---|---|---:|:--:|---|---|
| `enquete_answer` | `survey_responses` / `survey_answers` / `survey_answer_selected_options` | O14 アンケート | データ | 64,883 | C | 回答 | **`tenant_id` を持たない**ので親と join して絞る。**recademy 単体では 2,464件**（26分の1） |
| — | `survey_submission_log` | O14 | 中間 | — | — | 提出ログ | |

## E8 ライブ予約・出欠

| 旧テーブル | 新テーブル | データ種 | lw2区分 | ローカルデータ数 | A·B·C | 説明 | 移行の注意 |
|---|---|---|---|---:|:--:|---|---|
| `live_lesson_reserve` | `live_reservations` | L03 予約 | データ | 18,041 | C | 予約・キャンセル・出欠（16列 → 11列） | **UNIQUE `(occurrence_id, user_id)` に当たる。** 旧は同じ会員が同じ開催回に複数行持てる（キャンセル後の再予約）。旧の3フラグを `status` 1列に畳む |
| `config_live_lesson` | `live_lesson_occurrences.cancel_closes_at` | L03 予約 | 設定 | 64 | C | テナント単位のキャンセル期限設定 | **旧に対応列が無く、計算で作る**。`starts_at − ticket_cancel_day 日 − ticket_cancel_time 時間` |
| — | `live_reservation_statuses` | L03 予約 | マスタ | — | — | `live_reservations.status` の値 | シード済み4値（`reserved`/`canceled`/`attended`/`no_show`）。**「開催側の中止」を表す値が無い** |

---

## E9 修了証・バッジの設定

| 旧テーブル | 新テーブル | データ種 | lw2区分 | ローカルデータ数 | A·B·C | 説明 | 移行の注意 |
|---|---|---|---|---:|:--:|---|---|
| `config_certificate` | `certificate_settings` | O25 修了証 | 設定 | 3 | C | 修了証の発行設定 | **`cmd/import-certificates` が既にある**ので、ツールの責任範囲を決める |
| `certificate` | `certificate_layouts` | O25 修了証 | データ | 15 | C | 修了証のレイアウト | **任意 HTML のアップロードは新環境に無い**（実測で recademy は既定レイアウトのみ） |
| `certificate_no` | `certificate_serial_formats` | O25 修了証 | 設定 | 10 | C | 証書番号の採番規則 | |
| `badge_item` | **受け皿なし** | O27 バッジ | データ | 91 | C | バッジの定義（この講座/ユニットが対象か） | **付与実績は外部のバッジシステムにあり、lw2 の DB には無い**（`BadgeApi` 経由。ダンプの範囲外）。定義は移せる |
| — | `course_certificate_policies` | O25 修了証 | データ | — | — | 講座ごとの発行条件 | 旧に対応なし |
| — | `certificate_event_kinds` / `certificate_revoke_reasons` / `badge_revoke_reasons` / `digital_badge_event_kinds` | O25 / O27 | マスタ | — | — | イベント種別・失効理由 | migration で投入 |

## E10 修了証・バッジの発行

| 旧テーブル | 新テーブル | データ種 | lw2区分 | ローカルデータ数 | A·B·C | 説明 | 移行の注意 |
|---|---|---|---|---:|:--:|---|---|
| `user_certificate` | `certificates` | O25 修了証 | データ | 912 | C | 発行済み修了証 | **`cmd/import-certificates` が既存**。ツールと役割が重複しないよう決める |
| — | `certificate_events` / `digital_badges` / `digital_badge_events` | O25 / O27 | データ / イベント | — | — | 修了証のイベント、バッジの付与 | **バッジの付与行は移行元が存在しない** |

---
