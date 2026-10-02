# 受講テーブルの内訳

移行計画の **3 受講**（受講権限 / 学習履歴 / テスト結果 / 課題提出 / アンケート回答 / ライブ予約 / 修了証）。

> **バッジは移行対象外**（2026-09-28 決定）。定義（`badge_item`）も付与実績も移さない（→ [対象外](../06-out-of-scope/breakdown.md#決定で対象外にしたもの)）。

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
| `payment_item_lesson_authority` | `enrollments` | J01 受講権限 | データ | 7,462 | C | 商品の購入で得た講座の受講権限 | **粒度が違う。** 旧は商品×講座で、同じ (会員, 講座) に複数行ある（ステージング実測 6,966 行 → 4,289 組）。**lw2 自身が `GROUP BY user_id, lesson_id` で畳んでいる**ので同じ規則で寄せる。**権限が要るのは 235講座中 71件だけ**で、残りは無料講座 |
| `user`（全会員） | `enrollments`（ライブの受け皿講座） | J01 受講権限 | データ | — | — | **lw2 に元データが無い行。** 旧の「制限の無いライブは全員が予約できる」を保つため、受け皿講座に全会員を受講登録する（`enrollment.live_host_enrollments`。2026-09-24 決定） | ステージングで 3,155名（削除済みの会員 503名を含む）。`source = 'admin'` / `status = 'active'` / 期限なし。権限由来の `admin` とは `course_id` で区別する |
| `payment_item_lesson_authority_log` | — | J01 受講権限 | イベント・履歴 | 121,199 | C | 権限の付与・変更の履歴 | **受け皿なし。** 純ログとして移さない |
| — | `enrollment_statuses` / `enrollment_sources` / `enrollment_event_kinds` | J01 | マスタ | — | — | 受講の状態・経路・イベント種別 | シード済み。`source` は `admin` を使う（`manual` は存在しない） |
| — | `enrollment_status_events` | J01 | イベント・履歴 | — | — | 受講状態の履歴 | 旧の履歴を移さないので空で始める |
| `user_learning_lesson_edit_log` | — | J01 受講権限 | イベント・履歴 | 495,835 | C | 管理者が受講期間などを編集した記録。実測 36,510件 | **受け皿なし。** 純ログとして移さない（`payment_item_lesson_authority_log` と同じ扱い） |
| `application_user_learning_lesson` | — | J01 受講権限 | データ | 0 | C | 申込ごとのお試し受講の期間 | **0件**。移すものが無い |

## E2 学習履歴

| 旧テーブル | 新テーブル | データ種 | lw2区分 | ローカルデータ数 | A·B·C | 説明 | 移行の注意 |
|---|---|---|---|---:|:--:|---|---|
| `user_learning_unit` | `lesson_progress` | J02 ユニット進捗 | データ | 19,009 | C | ユニットごとの学習状況（実測 7,209 行） | **`progress_status` はユニット種別ごとに意味が変わる**（同じ `2` がテストなら「受験中」、アンケートなら「回答済」）。新は `last_position` / `completed_at` の2列しかない。**`last_position` は常に NULL**（`suspend_data` は `settings` に原文で残す）。**同じ (会員, ユニット) の重複は `update_date` の新しい1行だけを残し、残りは一覧に出さずに捨てる**（ステージング 153組 495行 → 342行を捨てる） |
| `user_learning_lesson` | —（`enrollments.completed_at` に入れる想定だった） | J03 講座進捗 | データ | 35,532 | C | 講座ごとの学習状況（実測 24,484 行 / 23,956 組） | **母集合にはしない。** 差の 22,833 組は 93% が無料講座で、旧環境でも権限行を持たない（`LessonModel::1363` は「権限がある **OR** 有料講座でない」の2分岐）。**修了日（`lesson_complete_date`）は現状は移していない**（実装が無く、`enrollments.completed_at` は常に NULL。修了日のある行はステージング 258件。2026-10-02 の確認） |
| `user_learning_unit_log` | — | J02 ユニット進捗 | イベント・履歴 | 33,998 | C | 進捗の更新履歴 | **受け皿なし。** 純ログとして移さない |
| `user_lesson_session` | — | J02 ユニット進捗 | データ | 267,639 | C | ユニット画面の一時値（CSRF トークンなど）。実測 1,860件 | **一時データなので移さない** |
| `summary_finish_unit_num` | — | J02 ユニット進捗 | データ | 1 | C | 講座ごとの完了ユニット数の集計。実測0件 | **移さない。** 進捗から作り直せる集計 |

## E3 テスト受験

| 旧テーブル | 新テーブル | データ種 | lw2区分 | ローカルデータ数 | A·B·C | 説明 | 移行の注意 |
|---|---|---|---|---:|:--:|---|---|
| `user_learning_test` | `quiz_attempts` | O09 テスト受験 | データ | 697,444 | C | 受験の結果 | **`test_score` / `sum_score` / `total_score` の3列のどれを使うかで点数が壊れる** |
| — | `quiz_attempt_statuses` / `quiz_attempt_event_kinds` | O09 | マスタ | — | — | 受験状態・イベント種別 | migration で投入 |
| — | `quiz_attempt_events` | O09 | イベント・履歴 | — | — | 受験のイベント | 旧に対応データなし |

## E4 テスト設問別回答

| 旧テーブル | 新テーブル | データ種 | lw2区分 | ローカルデータ数 | A·B·C | 説明 | 移行の注意 |
|---|---|---|---|---:|:--:|---|---|
| `user_learning_test_sub` | `quiz_answers` / `quiz_answer_selected_options` | O10 設問別回答 | データ | **10,705,972** | C | 設問ごとの回答 | **区分最大のテーブル。** `question_answer` はパイプ区切りの選択肢番号。**出題条件（`test_sub_type_id = 2`）から出た問題の回答と、固定出題から一意に引けない回答は、一覧に出さずに飛ばす**（ステージング 4,922件中 50件。すべて前者） |

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

## E9 修了証の設定（バッジは対象外）

| 旧テーブル | 新テーブル | データ種 | lw2区分 | ローカルデータ数 | A·B·C | 説明 | 移行の注意 |
|---|---|---|---|---:|:--:|---|---|
| `config_certificate` | `certificate_settings` | O25 修了証 | 設定 | 3 | C | 修了証の発行設定 | **移行ツールで移す**（`cmd/import-certificates` は使わない。決定済み）。設定が無くても採番カウンタ（`certificate_no`）があれば行を作る |
| `certificate` | —（`certificate_layouts` の想定だった） | O25 修了証 | データ | 15 | C | 修了証のレイアウト | **現状は移していない**（実装が無い。2026-10-02 の確認）。ステージング `tenant_id = 10` は 0行。**任意 HTML のアップロードは新環境に無い** |
| `certificate_no` | `certificate_settings.serial_next` | O25 修了証 | 設定 | 10 | C | 証書番号の採番カウンタ（次に払い出す番号） | **次番号をそのまま `serial_next` に入れる**（ステージングは 7）。`certificate_serial_formats` には入れない |
| `badge_item` | — | O27 バッジ | データ | 91 | C | バッジの定義（この講座/ユニットが対象か） | **移行対象外**（2026-09-28 決定。→ [対象外](../06-out-of-scope/breakdown.md#決定で対象外にしたもの)） |
| `lesson.certificate_id` | `course_certificate_policies` | O25 修了証 | データ | — | — | 講座ごとの発行方針 | **移す講座ごとに1行作る**（共有講座を含む）。`issue` = 旧 `lesson.certificate_id` があるか。受け皿講座を作るテナントだけ、受け皿講座に `issue = FALSE` の行も作る |
| — | `certificate_event_kinds` / `certificate_revoke_reasons` / `badge_revoke_reasons` / `digital_badge_event_kinds` | O25 / O27 | マスタ | — | — | イベント種別・失効理由 | migration で投入 |

## E10 修了証の発行（バッジは対象外）

| 旧テーブル | 新テーブル | データ種 | lw2区分 | ローカルデータ数 | A·B·C | 説明 | 移行の注意 |
|---|---|---|---|---:|:--:|---|---|
| `user_certificate` | `certificates` | O25 修了証 | データ | 912 | C | 発行済み修了証 | **移行ツールで移す**（`cmd/import-certificates` は流さない。決定済み）。`certificate_type = 2`（商品単位）は移らない |
| — | `certificate_events` / `digital_badges` / `digital_badge_events` | O25 / O27 | データ / イベント | — | — | 修了証のイベント、バッジの付与 | `certificate_events` は移した証書ごとに `issued` を1件作る。**バッジは移行対象外**。`digital_badges` / `digital_badge_events` は空で始める |

## E11 自動割当

**実装済み**（`billing.4`。きっかけの商品 `tenant_plans` が課金の2で入るため、フェーズは課金の最後に置いた）。
発動の規則は [課金 migration-spec P15](../04-billing/migration-spec.md)。

| 旧テーブル | 新テーブル | データ種 | lw2区分 | ローカルデータ数 | A·B·C | 説明 | 移行の注意 |
|---|---|---|---|---:|:--:|---|---|
| `assign` | `tag_auto_assign_rules` | J04 購入時自動割当 | データ | 603 | C | 自動割当のルール。実測9件 | 名前が無いので「旧 自動割当 #id」。削除済みは `active = FALSE` |
| `assign_payment_item` | `tag_auto_assign_rule_triggers` | J04 購入時自動割当 | 中間 | 843 | C | きっかけの商品。実測1件 | 全行移す。講座の商品 → `plan_id`、レッスン（`item_type = 1`）→ `course_id`、チケット・ライブの商品は旧の商品 ID（`item_id`）だけ |
| `assign_attribute` | `tag_auto_assign_rule_conditions` | J05 自動割当の条件 | 中間 | 202 | C | 条件の属性。実測3件 | 属性はタグとして移している（基盤） |
| `assign_group` | `tag_auto_assign_rule_group_conditions`（2026-10-01 新設） | J05 自動割当の条件 | 中間 | 6 | C | 条件のグループ。実測0件 | **新のアプリはまだ読まない。** グループで絞っていたルールも新では全員に効く（ルールは旧の状態のまま有効） |
| `assign_item` | `tag_auto_assign_rule_grants` | J04 購入時自動割当 | データ | 888 | C | 付与するもの（講座・お知らせ・クーポン・求人）。実測13件 | 削除・無効も移す（`deleted_at` / `valid`。新はまだ読まない）。お知らせ・クーポンは 05 で移す予定の決定論 ULID を入れる |
| `assign_log` | `tag_auto_assign_logs` | J04 購入時自動割当 | イベント・履歴 | 615,893 | B | 付与の記録。実測4,908件 | **3,907件は付与したもの（`assign_item`）が物理削除されていて移せない**（[制約の不整合](../constraint-violations.md)） |

---
