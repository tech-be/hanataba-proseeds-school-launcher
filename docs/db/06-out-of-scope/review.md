# 対象外 — 新旧テーブル・カラム突き合わせ

対象データ種: 5件（X01 集合研修 / X02 模試 / X03 タイピング / X04 外部リンク集 / X05 運営スケジュール）。

**PDF・再判定ともに 5件すべてが X で、新環境に受け皿が1つも無い。** したがってカラム単位の突き合わせをする対象が存在しない。

**中分類ごとの一覧は [breakdown.md](breakdown.md) にある。** ここは「落とす根拠」を残す場所。

## 落ちる旧テーブル（19件）

| データ種 | 旧テーブル | 備考 |
|---|---|---|
| X01 集合研修 | `training`, `training_sub`, `ex_training`, `ex_training_cate`, `ex_training_record`, `facility` | **集合研修ユニット（`unit_type_id=5`）は ReCADemy に20件ある**（削除済みでない。ETL設計 §5-0 の「0件」は誤り。2026-09-30 に数え直した）。ただし研修の本体（`training`）は0件で、ユニットは中身を持たない。**02 はこの20件を `lessons` に入れない**（受講の進捗3件も移らない）。`training` / `training_sub` は**テーブルごと空**。外部研修は実測 `ex_training` 9件 / `ex_training_record` 9件。`facility` の実測1件は**施設名「ご自身のパソコン」で住所・TEL・URL がすべて空** |
| X02 模試 | `test_mock_setting` | `test.is_mock_test` / `mock_post_message` / `mark_type_id` も連動して落ちる（[コンテンツ](../02-content/review.md) O08 参照） |
| X03 タイピング | `typing_question`, `typing_ranking`, `typing_log` | **`typing_log` / `typing_ranking` はどちらも 0 行で、機能が使われていない。** `typing_question`（720行）は**全テナント共通の教材マスタ**でテナントのデータではない |
| X04 外部リンク集 | `link`, `link_lesson`, `link_group`, `link_attribute` | 公開範囲を講座・グループ・属性で絞る3テーブルを伴う。**実測3件**なので、必要なら新環境で登録し直せる量 |
| X05 運営スケジュール | `schedule`, `schedule_attribute`, `schedule_group`, `schedule_lesson`, `schedule_user` | **空テーブル**（`lw2-migration-tables.md` の「空テーブル 26件」に含まれる） |

## 実測で確かめたこと（2026-09-18 ダンプ）

| 確認 | 結果 |
|---|---|
| X05 運営スケジュール | **5テーブルすべて 0 行。** 判断不要 |
| X03 タイピング | **`typing_log` / `typing_ranking` とも 0 行。** 機能ごと使われていない |
| X01 `ex_training`（外部研修） | **9件。** ETL 設計に件数が無かったので数えた。少数だが**0ではない** |
| X01 `facility` | **1件**、内容は「ご自身のパソコン」。教室の実体ではない |
| X04 `link` | **3件** |

**「使っていないから移さない」が根拠のものと、「少数だが実在する」ものが混在している。**

- **判断不要**: X05（0行）、X03（0行）
- **合意が要る**: X01 の外部研修9件、X04 のリンク3件、X02 の模試設定
  → いずれも**新環境で登録し直せる量**。これらを落とす合意は ETL設計 §11-1 の対象

> **本番ダンプで件数を取り直すこと。** 根拠が「ほぼ使われていない」なので、
> **本番で桁が変わったら判断をやり直す**。
