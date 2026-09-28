# コンテンツ — 突き合わせ

[コンテンツの内訳](breakdown.md) の対応表と **1対1で対応**する。内訳の行それぞれに `###` 見出しが1つあり、
**順序も内訳と同じ**。ひな形は [00-template/review.md](../00-template/review.md)。

- 観点（テーブル / カラム / 型 / 性質）と深刻度（高 / 中 / 低）の定義は [README.md](../README.md#突き合わせの4つの観点)
- **「内容」は問題点だけ、「修正方法」はどう直すかだけ。** 修正方法が `未決:` で始まるものは**実装前に閉じるべき論点**
- 本文中の「ステージング実測」は 2026-09-18 のダンプで `tenant_id = 10`（ReCADemy）に絞った値

> **[移行の原則](../00-template/review.md#移行の原則)に従う。** 対象外のデータ以外はすべて移行し、
> 受け皿が無ければ追加し、元の構造を維持する。

---

## C1 講座・カテゴリ

内訳: [breakdown.md](breakdown.md) の同名の節

### `lesson` → `courses`

`lesson` (30列) → `courses` (17列) ／ ETL段 L2 ／ ローカルデータ数 2,208 / C

そのまま対応: 4列（`name`→`title`、`description`、`regist_date`→`created_at`、`update_date`→`updated_at`）

| 旧カラム | 新カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|---|:--:|---|---|
| — | `instructor_id` char(26) **NOT NULL** + FK → `users` | **テーブル** | **高** | **lw2 に講座単位の講師が無い。** この値が決まらないと**1行も入らない** | **代理講師の `users` 行を1件作り、全講座に割り当てる**（→ A21）。`instructor_id` は NOT NULL のまま触らない。**パスワードを空にしてログインできない行**にし、**講座→講師の対応表を受け取ってから本来の講師に付け替える**。講師の担当範囲は基盤 A18 の `instructor_assignments` が持つので、ここは表示用の代表1名でよい |
| `lesson_cate_id` int(11) | `category` varchar(50) + FK → `course_categories(code)` | **テーブル** | **高** | **`course_categories` は固定シードを持たない**（`200_courses_category_difficulty_lookup.sql` は既存 `courses.category` からの吸い上げだけ）。**新規 DB では空**なので FK 違反になる | **ETL の L0 に「`lesson_cate` から `course_categories` を作る」段を足す**（[ETL 設計との関係](../README.md) の抜け）。`courses` より先に投入する |
| `open_period` smallint(6) **（月）** | `access_days` int **（日）** | **性質** | **高** | **単位が月→日。** そのまま入れると受講期間が 1/30 になる | ETL で `open_period * 30` に換算する。**単位換算をテストで固定する**。ETL設計 §5-2 は `payment_item` 側から引くとしているので、どちらを正とするかを課金（K01）と揃える |
| `sales_status` tinyint(4) | `status` varchar(32) | 性質 | 中 | `content_statuses` は `draft`/`published`/`archived` の3値 | 販売中→`published`、それ以外→`draft` に変換する（ETL設計 §5-2） |
| `allowed_ip_address` text | — | カラム | 中 | **講座単位の IP 制限を入れる列が無い** | `courses.allowed_ip_address` を追加して移す（→ [追加一覧](#新環境に追加するテーブルカラム) A1） |
| `open_pc_chk` / `open_smartphone_chk` / `lesson_thumbnail_type` / `img_smartphone` | — | カラム | 中 | **デバイス別の公開設定とスマホ用画像を入れる列が無い** | A1 の `courses.settings`（json）に移す。スマホ用画像は L9 で移送して URL を入れる |
| `drill_chk` / `quiz_chk` / `sns_shared_chk` / `inquiry_chk` / `inquiry_address` / `progress_display_chk` | — | カラム | 低 | 講座単位の機能 ON/OFF（弱点問題集・ランキング・SNS共有・問い合わせ・進捗率表示）を入れる列が無い | A1 の `courses.settings`（json）にまとめて移す。**読み出し側が無いものは、機能を作るかを別途決める**（移行はする） |
| `frame_id` / `disp_type_id` / `frame_height` / `frame_width` / `operating_env` / `inquire_cate_id` | — | カラム | 低 | 表示フレーム設定・動作環境・問い合わせカテゴリを入れる列が無い | 同じく A1 の `courses.settings` に移す |
| `certificate_id` | `course_certificate_policies` | テーブル | 低 | 修了証の紐付け | [`config_certificate` → `certificate_settings`](../03-enrollment/review.md#config_certificate--certificate_settings) と合わせて移す |
| — | `price` decimal(10,2) | 性質 | 中 | **lw2 は価格を講座ではなく商品 (`payment_item`) に持つ。** 商品と講座が 1:N なので、どの価格を入れるか決まらない | 未決: **講座→価格の対応表**を受け取ってから埋める。`courses.price` は **NULL 可なので投入は止まらない**（移行時は NULL、対応表が来てから更新）。商品が複数ある講座の扱いを課金（K01）と揃える |

**まとめ**: 受け皿が無い列 12 / 変換規則が要る列 5 / **高 3 件**

### `lesson_is_used` → なし

`lesson_is_used` (—) ／ ローカルデータ数 2,066 / C

**該当テーブルなし。** 講座の利用可否（テナントごとの有効化）。

| 旧カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|:--:|---|---|
| テーブル全体 | 性質 | 中 | **`courses.status` は公開状態で、利用可否とは別の軸。** 2つを1列に畳むと、非公開なのか未利用なのかが区別できなくなる | `courses.is_used` を追加して移す（→ A1）。`status`（公開）と分けて持つ |

**まとめ**: 受け皿が無い列 — / 高 0 件

### `lesson_system` → なし

`lesson_system` (—) ／ ローカルデータ数 243 / C

**該当テーブルなし。** 講座の表示・動作設定。

| 旧カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|:--:|---|---|
| テーブル全体 | カラム | 中 | 講座ごとの表示・動作設定を入れる場所が無い | A1 の `courses.settings`（json）に移す。**列の内訳はダンプ受領後に確認する** |

**まとめ**: 受け皿が無い列 — / 高 0 件

### `lesson_tag` / `lesson_lesson_tag` → なし

`lesson_tag` / `lesson_lesson_tag` ／ ローカルデータ数 31 / 281 / C

**該当テーブルなし。** 講座タグと、その割当。

| 旧カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|:--:|---|---|
| テーブル全体 | **テーブル** | 中 | **タグの概念が新環境に無い。** カテゴリ（1講座1件）とは別に、横断的な分類が落ちる | `course_tags` と `course_tag_links` を新設して移す（→ A2） |

**まとめ**: 受け皿が無い列 — / 高 0 件

### `lesson_cate` → `course_categories`

`lesson_cate` (9列) → `course_categories` (11列, マスタ) ／ ETL段 L2 ／ ローカルデータ数 482 / C

| 旧カラム | 新カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|---|:--:|---|---|
| `tenant_id` | — | **性質** | **高** | **旧はテナントごと、新は `code` を PK とするグローバルマスタで `tenant_id` を持たない。** 他テナントとカテゴリ名が衝突する | recademy 単体では実害が無いので、**`code` にテナントを含めない**まま進める。**将来テナントを増やすときに `tenant_id` を足す**ことを新環境側の課題として残す（A3） |
| `lesson_cate_name` varchar(200) | `code` varchar(50) / `name_ja` varchar(128) | 型 | 中 | **200 → 50 / 128 で桁が足りない。** 日本語カテゴリ名をそのまま `code` にする設計 | 抽出時に50文字超・128文字超の件数を検査する。**超過があれば列を広げる**（切り捨てない） |
| `lesson_cate_img_file_name` varchar(255) | `icon` varchar(64) | 性質 | 低 | **意味が違う。** 旧は画像ファイル名、新はアイコン識別子 | **そのまま入れない。** 画像は L9 で移送し、A3 の `course_categories.image_url` に入れる |
| `sort_no` | `sort_order` | — | — | 対応あり | そのまま移す |
| `del_chk` | `active` / `deprecated_at` | 性質 | 低 | **削除状態を2列で持つため二重管理になる** | `del_chk=1` は `active=FALSE` + `deprecated_at` に日時を入れる。判定は `deprecated_at IS NULL` に寄せる（基盤 `user_roles` と同じ扱い） |
| `regist_user_id` | — | カラム | 低 | 登録者を入れる列が無い | A3 の `course_categories.created_by` を追加して移す |

**まとめ**: 受け皿が無い列 2 / 変換規則が要る列 3 / **高 1 件**

### なし → `content_statuses`

`content_statuses` (マスタ)

**旧に対応テーブルなし。** `courses.status` / `lessons.status` の値で `draft`/`published`/`archived` の3値。**`deleted` が無い**ため、旧 `del_chk=1` を写す先がない。

| 旧カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|:--:|---|---|
| `lesson.del_chk` / `unit.del_chk` | 性質 | 中 | **削除済みの講座・ユニットを表現できない。** `archived` に畳むと「運営が意図して非公開にしたもの」と区別できなくなる | `content_statuses` に `deleted` を追加する（→ A3）。基盤の `tenant_statuses` と同じ扱い |

### なし → `course_difficulties`

`course_difficulties` (マスタ)

**旧に対応テーブルなし。** migration で投入する。lw2 に講座の難易度が無いため、移行では使わない（`courses.difficulty` は NULL か既定値）。

---

## C2 ユニット・動画

内訳: [breakdown.md](breakdown.md) の同名の節

### `unit` → `lessons`

`unit` (22列) → `lessons` (12列) ／ ETL段 L2 ／ ローカルデータ数 51,463 / C

そのまま対応: 3列（`title`、`regist_date`→`created_at`、`update_date`→`updated_at`）

| 旧カラム | 新カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|---|:--:|---|---|
| `unit_type_id` tinyint(4) 0〜6 | `type` varchar(32) + FK → `lesson_types(code)` | 性質 | 中 | `lesson_types` は `video`/`live`/`text` の**3値しかない**。テスト(2)・レポート(4)・講座資料(6) がすべて `text` に畳まれ、**移行後に種別で区別できなくなる** | **`lesson_types` に `quiz` / `assignment` / `document` / `discussion` / `skill_check` を追加する**（→ A20）。畳まない。**見出し(0) だけは `lessons` に入れない**（ETL設計 §5-0）。**7（ディスカッション）・8（スキル診断）は `UnitConstants.php` に定数が無い**が、`ShareController::UNIT_TYPE_DISCUSSION` / `UNIT_TYPE_SKILL` にあり、`DiscussionModel` も `unit_type_id = 7` で引いている正規の種別 |
| `sort_no` | `sort_order` | 性質 | 中 | 見出し(type=0) を落とす分、番号が飛ぶ | ETL で講座ごとに採番し直す。**元の並び順は保つ** |
| `detail` text **NOT NULL** | `description` text NULL可 | 性質 | 低 | 新環境は本文 HTML を信用しない方針。**旧に HTML が入っていれば、表示が崩れるか XSS になる** | **変換せずそのまま移す。** 同梱ダンプの `unit` 2,533行を調べたところ **HTML は1件も無く、`\r\n` 区切りの平文だった**。改行をそのまま保持し、**表示時にサニタイズする**（元を壊さない）。**本番ダンプで同じ棚卸しをやり直す**（[1-3](migration-spec.md#1-4-本番ダンプ受領後に確認すること)） |
| `open_datetime` / `close_datetime` | — | **カラム** | **高** | **絶対日時での公開開始・終了を入れる列が無い。** 新は `drip_delay_days`（申込日からの相対日数）しか持たず、「この日から公開」を再現できない | `lessons.open_at` / `close_at` を追加して移す（→ A4）。相対日数（`drip_delay_days`）と併存させ、**両方を見て判定する**ようアプリ側を直す |
| `close_day_from_lesson_start_date` | — | カラム | 中 | 受講開始日からの終了日数を入れる列が無い | A4 の `lessons.close_after_days` を追加して移す |
| `open_day` / `payment_open_day` | `drip_delay_days` | 性質 | 中 | **2列を1列に畳むと、どちらの起点だったかが消える** | A4 に `drip_delay_basis`（`enrollment` / `payment`）を追加し、**2列とも保持する** |
| `complete_message` text NOT NULL | — | カラム | 中 | ユニット修了時のメッセージを入れる列が無い | A4 の `lessons.complete_message` を追加して移す |
| `search_keyword` text NOT NULL | — | カラム | 低 | 検索キーワードを入れる列が無い | A4 の `lessons.search_keyword` を追加して移す |
| `unit_duration` int(11)（分） | — | カラム | 低 | 所要時間を入れる列が無い（`video_lessons.video_duration` は動画のみで単位も別） | A4 の `lessons.duration_min` を追加して移す |
| `open_close_chk` / `payment_unit` / `not_skill_result_chk` / `enquete_suspended_chk` | — | カラム | 低 | ユニットの開閉・有料属性・スキル診断結果連動・アンケート中断の設定を入れる列が無い | A4 の `lessons.settings`（json）にまとめて移す |
| `enquete_id` | `survey_lessons` | テーブル | 中 | アンケートの紐付け | [`enquete` → `survey_lessons`](#enquete--survey_lessons) を参照 |
| `del_chk` | `status` | 性質 | 低 | `content_statuses` に `deleted` が無い | A3 で `deleted` を追加し、そこへ移す |
| — | `is_preview` | カラム | 低 | 旧に対応なし | 既定値に任せる。対応不要 |

**まとめ**: 受け皿が無い列 10 / 変換規則が要る列 6 / **高 1 件**

### `lecture` → `video_lessons`

`lecture` (12列) → `video_lessons` (6列) ／ ETL段 L2 + L9 ／ ローカルデータ数 26,402 / C

| 旧カラム | 新カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|---|:--:|---|---|
| `lecture_id` / `unit_id` | `lesson_id` char(26) **PK** | テーブル | 中 | **`lesson_id` が PK なので 1レッスン1動画。** lw2 は 1:N になりうる（実測では最大1本） | 抽出時に**1ユニットに複数 `lecture` がある件数を検査する**。0件なら PK のまま進め、あれば `video_lessons` の PK を見直す |
| `pmovie_token` text | `video_url` varchar(512) **NOT NULL** | 性質 | 中 | トークンと URL で形式が違う。**recademy では 2,533件中 1,181件が空**（p-movie を使っていない動画） | **`pmovie_chk` が立っている動画だけ p-movie の URL に組み立てる。** 立っていない動画の配信先は**別テーブル [`lecture_path`](#lecture_path--video_lessonsvideo_url)** |
| `lecture_complete_type` / `pmovie_complete_type` | — | **カラム** | **高** | **「どこまで見たら修了か」の修了設定を入れる列が無い。** 進捗判定の基準が変わり、移行後に修了状態がずれる | `video_lessons.complete_type` を追加して移す（→ A5）。**判定ロジックも旧の基準に合わせる** |
| `skip_prevention_setting` | — | **カラム** | **高** | **スキップ防止（早送り禁止）の設定を入れる列が無い。** 資格・研修系の要件だった場合、コンプライアンス上の後退になる | A5 の `video_lessons.skip_prevention` を追加して移し、**プレイヤー側の制御も入れる** |
| `is_continue_watch_chk` | — | カラム | 低 | 続きから再生する設定を入れる列が無い | A5 の `video_lessons.settings`（json）に移す |
| `plugin_chk` | — | カラム | 低 | プラグイン連携フラグを入れる列が無い | 同上 |
| — | `video_duration` int | カラム | 低 | 旧に対応列なし | p-movie 側から取得するか NULL。対応不要 |

**まとめ**: 受け皿が無い列 5 / 変換規則が要る列 2 / **高 2 件**

### `lecture_path` → `video_lessons.video_url`

`lecture_path` ／ ローカルデータ数 26,953 / C

**動画の配信先。** `lecture` には URL の列が無く、**配信先はこのテーブルが持つ**。
`pmovie_chk` が立っていない動画は `LessonController::frameContentsAction` が
`pc_path` を読んで配信している。

| 旧カラム | 新カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|:--:|---|---|---|
| `pc_path` varchar(200) | `video_lessons.video_url` varchar(512) | 性質 | 中 | **値が3種類混ざっている。** recademy 2,559行のうち **URL 1,171 / 相対パス 44 / 空 1,344**。相対パスは `/html/contents/<tenant_code>/lesson` からの参照で、そのまま入れても新環境では解決できない | **URL はそのまま移す。** 相対パスは **L9 のファイル移送後に新しい配信先の URL へ書き換える**。空の行は `pmovie_token` 側で配信している動画なので、そちらから組み立てる |
| `smartphone_path` varchar(200) | — | カラム | 低 | **PC と携帯で配信先を分けている。** 新環境は `video_url` 1本 | 入れる先が無い。**PC 用を採用する**（新環境はレスポンシブで、端末別の配信先を持たない） |
| `sort_no` | — | カラム | 低 | 1ユニットに複数の配信先を持てる（順序つき） | 新環境は1ユニット1動画。**`sort_no` の最小の行を採用する**（lw2 も `array_shift` で先頭を使っている） |

**まとめ**: 受け皿が無い列 2 / 高 0 件

### `lecture_path_test` → なし

`lecture_path_test` ／ ローカルデータ数 - / —

**該当テーブルなし。** 動画パスの検証用。2026-07-28 ダンプ以降に追加されたため実測値が無い。

| 旧カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|:--:|---|---|
| テーブル全体 | テーブル | 低 | 検証用の一時テーブルとみられるが、**中身を確認できていない** | 未決: ダンプ受領後に中身と用途を確認し、検証用なら移行しない |

**まとめ**: 受け皿が無い列 — / 高 0 件

### なし → `lesson_types`

`lesson_types` (マスタ)

**旧に対応テーブルなし。** `lessons.type` の値で `video`/`live`/`text` の3値。**テスト・レポート・講座資料を区別する値が無い**ため、A20 で `quiz` / `assignment` / `document` を追加する。

---

## C3 受講制御（前提条件・免除）

内訳: [breakdown.md](breakdown.md) の同名の節

### `unit_precondition` → なし

`unit_precondition` ／ ローカルデータ数 7,601 / C

**該当テーブルなし。** 「このユニットを終えないと次に進めない」という順序制御。

| 旧カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|:--:|---|---|
| `unit_id` + 前提ユニット | **テーブル** | **高** | **順序制御が丸ごと落ちる。** 新環境は `drip_delay_days`（日数）しか持たず、「前のユニットを終えたら」を表現できない。**移行後は全ユニットが最初から受講できる** | `lesson_preconditions` を新設して移す（→ A15）。**受講画面の進行制御も実装する**（テーブルだけでは効かない） |

**まとめ**: 受け皿が無い列 — / **高 1 件**

### `unit_exemption` → なし

`unit_exemption` ／ ローカルデータ数 226 / C

**該当テーブルなし。** 特定受講者のユニット免除。

| 旧カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|:--:|---|---|
| `unit_id` + `user_id` | **テーブル** | 中 | **免除が落ちると、免除されていた受講者が未修了になる** | `lesson_exemptions` を新設して移す（→ A15）。進捗判定で免除を見るようにする |

**まとめ**: 受け皿が無い列 — / 高 0 件

---

## C4 リモート PC

内訳: [breakdown.md](breakdown.md) の同名の節

### `remote_api_token` → なし

`remote_api_token` (6列) ／ ローカルデータ数 5 / C

**該当テーブルなし。** 外部リモート環境へ渡す一時トークン。

| 旧カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|:--:|---|---|
| `token` + `limit_date` | **性質** | **高** | **概念が違う。** 旧は一時トークンで**予約という概念が無い**。新は machine / 時間枠 / status を持つ予約システム | **例外: 移行しない。** 発行中の一時トークンで、移した時点で無効（基盤の `user_auth_token` と同じ）。**ただし `lesson_id` から「どの講座がリモート PC 対象か」を導けるので、`courses.remote_pc_enabled` の初期値には使う** |

**まとめ**: 受け皿が無い列 — / **高 1 件**

### なし → `remote_pc_machines` ほか3件

**旧に対応データなし。** 新環境固有の予約機能。**空で始める**（マシン定義は運用で登録する）。

---

## C5 テスト定義

内訳: [breakdown.md](breakdown.md) の同名の節

### `test` → `quizzes`

`test` (23列) → `quizzes` (9列) ／ ETL段 L2 ／ ローカルデータ数 7,989 / C

| 旧カラム | 新カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|---|:--:|---|---|
| `unit_id` | `lesson_id` + **UNIQUE (tenant_id, lesson_id)** | **テーブル** | **高** | **1レッスン1クイズ。** lw2 の `test.unit_id` は MUL で、1ユニットに複数テストを持てる | 抽出時に**複数テストを持つユニットの件数を検査する**。**UNIQUE は外さない**（緩めない方針）。**2件目以降のテストは移らない**ので、件数を数えて規模を記録する |
| — | `title` varchar(255) **NOT NULL** | カラム | 中 | 旧 `test` にタイトル列が無い | `unit.title` から持ってくる |
| `exam_limit_times` | `time_limit_sec` int | 型 | 中 | **単位が違う。** 受験画面の残り時間計算が `exam_limit_times * 60 - test_time` なので、**旧は分・`test_time` は秒**（`UserLearningLessonModel`） | **`exam_limit_times * 60` で秒に換算する。** `test_time`（秒）はそのまま `quiz_attempts.duration_sec` へ |
| `pass_score` | `passing_score` int | — | — | 対応あり | そのまま移す |
| `exam_max_number` / `suspended_chk` | — | カラム | 中 | 受験回数制限（O13）と中断機能（O12）を入れる列が無い | `quizzes.max_attempts` / `suspend_enabled` を追加して移す（→ A8） |
| `test_result_disp_chk` / `test_score_disp_chk` / `error_disp_chk` / `answer_disp_chk` / `comment_disp_chk` / `disp_question_count` | — | カラム | 中 | **「正解を見せるか」「解説を見せるか」「点数を見せるか」の表示制御6列を入れる列が無い。** 受講者に見える情報が変わる | A8 の `quizzes.display_settings`（json）にまとめて移し、**出題画面の表示制御を実装する** |
| `is_mock_test` / `mock_post_message` / `mark_type_id` / `ranking_chk` / `repeat_chk` / `test_start_time` | — | カラム | 低 | 模試（X02）・ランキング・開始時刻を入れる列が無い | 模試は[対象外](../06-out-of-scope/review.md)区分なので移行しない。**残りは A8 の `display_settings` に移す** |
| **カラムコメントの文字化け** | — | **性質** | **高** | `disp_question_count` 〜 `comment_disp_chk` の**カラムコメントが cp932 混入で壊れている**。実データにも混入の可能性がある | **抽出時に文字コード検証を入れる**（区分共通。[共通仕様](../../migration-spec.md) 3.4） |

**まとめ**: 受け皿が無い列 13 / 変換規則が要る列 3 / **高 2 件**

### `test_sub` → なし

`test_sub` (13列) ／ ローカルデータ数 8,060 / C

**該当テーブルなし。** 「問題カテゴリ × レベルから N 問を出題する」という**出題条件**。

| 旧カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|:--:|---|---|
| `question_cate_id` + `question_level_id` + `set_question_no` + `score_per_question` + `distribution_factor` + `random_option` | **テーブル** | **高** | **テスト定義の構造が根本的に違う。** lw2 は条件で出題し**受験者ごとに出る問題が変わる**。新は `quiz_questions` の固定リスト。条件を展開して固定化すると、**受験者ごとに違う問題が出ていた事実が再現できない** | `quiz_question_rules` を新設して**出題条件をそのまま移す**（→ A6）。あわせて A6 の問題バンク（`quiz_question_banks`）を作り、**条件による出題を新環境でも成立させる**。固定化はしない |

**まとめ**: 受け皿が無い列 13 / **高 1 件**

### `test_sub_question` → `quiz_questions`

`test_sub_question` ／ ETL段 L2 ／ ローカルデータ数 652,050 / C

**大問と設問の割当**（中間表）。

| 旧カラム | 新カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|---|:--:|---|---|
| 主キー | `quiz_questions.id` | **性質** | **高** | **採番が枯渇・履歴断裂しており、旧 ID を外部キーとして引き継げない**（`lw2-migration-tables.md`） | 決定論 ULID を**旧 ID ではなく `(test_id, question_id, 並び順)` から採番する**。旧 ID に依存する参照を作らない |

**まとめ**: 受け皿が無い列 — / **高 1 件**

### `sort_test_sub_question` → なし

`sort_test_sub_question` ／ ローカルデータ数 114,747 / C

**該当テーブルなし。** 設問の並び順。

| 旧カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|:--:|---|---|
| テーブル全体 | 性質 | 低 | 並び順を独立して持つテーブルは新環境に無い | `quiz_questions.sort_order` に畳んで移す。**これは情報の欠落ではない**（1対1で表現できる） |

**まとめ**: 受け皿が無い列 — / 高 0 件

### `question` → `quiz_questions` / `quiz_options`

`question` (58列) → `quiz_questions` (10列) + `quiz_options` (6列) ／ ETL段 L2 ／ ローカルデータ数 64,176 / C

| 旧カラム | 新カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|---|:--:|---|---|
| `question`（`tenant_id` 直下の問題バンク） | `quiz_questions.quiz_id` **NOT NULL** | **テーブル** | **高** | **lw2 の `question` はテスト非依存の共有問題バンク。** 新は問題がクイズに属するため、**同じ問題を複数テストで使っていると複製になる**（総数が膨らみ、以後の編集も分岐する） | `quiz_question_banks` を新設し、**問題の本体はバンクに置く**（→ A6）。`quiz_questions` はバンクへの参照にする |
| `question_img_file_name` / `selection1..20_img_file_name` / `answer_explanation_img_file_name`（画像22列） | — | **カラム** | **高** | **問題・選択肢・解説の画像を入れる列が無い。** 図表を使った問題が成立しなくなる | `quiz_questions.image_url` と `quiz_options.image_url`、解説画像の列を追加して移す（→ A7）。**L9 でファイルを移送して URL を入れる** |
| `selection1..20` (text×20) | `quiz_options`（縦持ち） | 性質 | 中 | 横持ち → 縦持ち | 有効数は `selection_num` を見て展開する |
| `selection1..20` text | `quiz_options.body` varchar(1000) | 型 | 中 | **text → varchar(1000) で切り捨ての恐れ** | 抽出時に1000文字超を検査し、**超過があれば列を広げる** |
| `answer` varchar(1000) | `quiz_options.is_correct` | 性質 | 中 | 正解文字列 → 選択肢ごとのフラグへ分解する規則が要る | `answer` の格納形式を実装で確認し、選択肢番号と突き合わせて `is_correct` を立てる |
| `question_type_id` | `quiz_questions.type` | 性質 | 中 | `quiz_question_types` は `single_choice` / `multiple_choice` の**2値のみ**。自由記述（O11）の受け皿が無い | `quiz_question_types` に `free_text` を追加して移す（→ A7） |
| `question_cate_id` / `question_level_id` | — | カラム | 中 | **問題カテゴリ・レベルを入れる列が無い。** これは `test_sub` の出題条件が参照しているので、落とすと条件も再現できない | A6 の `quiz_question_banks.category_id` / `level` に移す |
| `question_name` / `hint` / `require_chk` | — | カラム | 中 | 問題名・ヒント・必須フラグを入れる列が無い | A7 で `quiz_questions.name` / `hint` / `required` を追加して移す |

**まとめ**: 受け皿が無い列 27 / 変換規則が要る列 5 / **高 2 件**

### `question_cate` → なし

`question_cate` ／ ローカルデータ数 1,407 / C

**該当テーブルなし。** 問題バンクのカテゴリ。

| 旧カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|:--:|---|---|
| テーブル全体 | **テーブル** | 中 | **カテゴリが無いと `test_sub` の出題条件（カテゴリ×レベルから N 問）が成立しない** | `quiz_question_labels`（管理者が作るラベルと同じ表）に `legacy_id` 付きで移す（→ A6）。名前が重なる分は区別を付ける |

**まとめ**: 受け皿が無い列 — / 高 0 件

### なし → `quiz_question_types`

`quiz_question_types` (マスタ)

**旧に対応テーブルなし。** `quiz_questions.type` の値で `single_choice`/`multiple_choice` の2値。**自由記述の受け皿が無い**ため A7 で `free_text` を追加する。

> **記述式も採点される。** 正解候補は `question.answer` にパイプ区切りで入っており、`quiz_options` に `is_correct = TRUE` の行として展開する。**選択式と違い、候補に「番号」ではなく「文字列そのもの」が入る**点に注意する。

---

## C6 課題定義

内訳: [breakdown.md](breakdown.md) の同名の節

### `report` → `assignments`

`report` (26列) → `assignments` (12列) ／ ETL段 L2 ／ ローカルデータ数 4,684 / C

| 旧カラム | 新カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|---|:--:|---|---|
| — | `title` varchar(255) **NOT NULL** | カラム | 中 | 旧 `report` にタイトル列が無い | `unit.title` から持ってくる |
| — | `allowed_types` varchar(100) **NOT NULL** | カラム | 中 | 旧は課題ごとに設定を持たず、**アップロード共通のホワイトリスト**（`UploadUtil::$extension_file`）で制限していた | **そのホワイトリストを既定値として入れる**: `txt,rtf,pdf,csv,doc,docx,xls,xlsx,ppt,pptx,ppsx,jpg,jpeg,gif,bmp,png,htm,html,zip,lzh,mp3`。**カンマ区切りで89文字なので `varchar(100)` に収まる**（実装時に確認。桁拡大は要らない） |
| `limit_Date` datetime | `due_at` datetime(3) | 型 | 低 | **列名が `limit_Date` と大文字混じり。** MySQL は区別しないが、DictCursor では綴りどおりのキーになる | 抽出時のキーを綴りどおりに書く。**`limit_date` と書くと取りこぼす** |
| `limit_Date_Num` | — | カラム | 中 | 相対日数での提出期限を入れる列が無い | `assignments.due_after_days` を追加して移す（→ A13） |
| `report_pmovie_chk` / `report_pmovie_token` | — | カラム | 中 | **課題に紐づく動画を入れる列が無い** | A13 の `assignments.video_url` を追加して移す |
| `send_mail_chk` / `enable_change_chk` / `complete_condition_chk` / `no_submit_chk` / `report_commentary_chk` | — | カラム | 低 | 提出通知・再提出制限・修了条件・評価のみ・解説設定を入れる列が無い | A13 の `assignments.settings`（json）にまとめて移す |

**まとめ**: 受け皿が無い列 8 / 変換規則が要る列 3 / 高 0 件

### `report_path` → なし

`report_path` ／ ローカルデータ数 4,597 / C

**該当テーブルなし。** 課題として配る資料ファイル（`report_disp_file_name1..5` / `report_save_file_name1..5`）。

| 旧カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|:--:|---|---|
| 配布ファイル10列 | **カラム** | **高** | **課題として配る資料5本を入れる場所が無い。** 設問の添付資料が消えると課題が成立しなくなる | `assignment_materials` を新設し、**5本とも1行ずつ移す**（→ A13）。L9 でファイルを移送する |

**まとめ**: 受け皿が無い列 10 / **高 1 件**

---

## C7 アンケート定義

内訳: [breakdown.md](breakdown.md) の同名の節

### `enquete` → `survey_lessons`

`enquete` (7列) → `survey_lessons` (7列) ／ ETL段 L2 ／ ローカルデータ数 7,414 / C

| 旧カラム | 新カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|---|:--:|---|---|
| `enquete`（独立エンティティ） | `survey_lessons.lesson_id` **PK** | **テーブル** | **高** | **1レッスン1アンケート。** lw2 の `enquete` は `unit.enquete_id` から参照される独立エンティティで、**同じアンケートを複数ユニットで使い回していると入らない** | 抽出時に**複数ユニットから参照されているアンケートの件数を検査する**。0件でなければ、`survey_lessons` の PK を外して `survey_id` を独立させる（→ A12）。**複製はしない**（回答の集計単位が分かれるため） |
| `enquete_name` text NOT NULL | — | カラム | 中 | **`survey_lessons` に名前の列が無い** | A12 の `survey_lessons.name` を追加して移す |

**まとめ**: 受け皿が無い列 1 / **高 1 件**

### `enquete_page` → なし

`enquete_page` ／ ローカルデータ数 8,311 / C

**該当テーブルなし。** アンケートのページ分割。

| 旧カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|:--:|---|---|
| テーブル全体 | テーブル | 中 | **ページの概念が新環境に無い。** 設問が `lesson_id` 直下に並ぶため、長いアンケートが1画面になる | `survey_pages` を新設し、`survey_questions.page_id` で紐付ける（→ A12） |

**まとめ**: 受け皿が無い列 — / 高 0 件

### `enquete_question` → `survey_questions` / `survey_question_options`

`enquete_question` (52列) ／ ETL段 L2 ／ ローカルデータ数 11,179 / C

| 旧カラム | 新カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|---|:--:|---|---|
| `question_text` text | `survey_questions.prompt` varchar(500) **NOT NULL** | **型** | **高** | **text → varchar(500) で切り捨てが起きる** | 抽出時に500文字超を検査し、**超過があれば列を `TEXT` に広げる**（→ A12）。切り捨てない |
| `question_type` 1〜4 | `survey_questions.kind` | 性質 | 中 | `survey_question_kinds` の5値に**4=ファイル添付が無い**（実測7件） | `survey_question_kinds` に `file_upload` を追加して移す（→ A12） |
| `question_img_file_name` + `selection1..20_img_file_name`（画像21列） | — | **カラム** | **高** | **設問・選択肢の画像を入れる列が無い** | `survey_questions.image_url` / `survey_question_options.image_url` を追加して移す（→ A12）。L9 でファイルを移送する |
| `selection1..20` text | `survey_question_options` | 性質 | 中 | 横持ち → 縦持ち | `sort_order` = 1..n で展開する |

**まとめ**: 受け皿が無い列 21 / 変換規則が要る列 2 / **高 2 件**

### なし → `survey_question_kinds`

`survey_question_kinds` (マスタ)

**旧に対応テーブルなし。** 設問種別の値。**ファイル添付の受け皿が無い**ため A12 で `file_upload` を追加する。

---

## C8 ライブ定義

内訳: [breakdown.md](breakdown.md#c8-ライブ定義)

### `live_lesson` → `lessons`(type=live) / `live_lessons`

`live_lesson` (35列) → `lessons` (21列) + `live_lessons` (6列) ／ ETL段 L5 ／ ローカルデータ数 746 / C ／ ステージング実測 18件（うち削除済み3件）

そのまま対応: 4列（`live_lesson_name`→`lessons.title`、`live_lesson_detail`→`lessons.description`、`regist_date`→`created_at`、`update_date`→`updated_at`）

| 旧カラム | 新カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|---|:--:|---|---|
| — | `lessons.course_id` char(26) **NOT NULL** + FK → `courses` | **テーブル** | **高** | **lw2 のライブは講座に属さないので、親となる course が存在しない。** この値が決まらないと**1行も入らない** | **商品制限のあるライブ（5件）は、その商品が売っている実在の講座に置く。** `live_lesson_limit_item` → `payment_item` → `payment_item_lesson` で講座に1対1でたどれ、**その2講座はオンデマンドで移行済み**。**制限の無い13件だけ受け皿が要る**（→ [`live_lesson_limit_item`](#live_lesson_limit_item--なし)）。ETL設計 §11-4 の案A / 案B は**カテゴリで分ける案**だが、カテゴリの紐付けは18件中6件しかなく成立しない |
| `live_lesson_id` int(11) | `lessons.legacy_id` int + **UNIQUE `uk_lessons_legacy (tenant_id, legacy_id)`** | **テーブル** | **高** | **`lessons.legacy_id` はオンデマンドが `unit.unit_id` で使っている。** ライブの ID を同じ列に入れると衝突する。ステージング実測で **18件中 11件**が既存の `unit_id` と重なる | **`lessons.legacy_id` はライブでは使わず NULL にし、`live_lessons.legacy_id` を追加して旧 ID を持つ**（→ A22）。`UNIQUE (tenant_id, legacy_id)` はそちらに張る。**`uk_lessons_legacy` は外さない** |
| — | `live_lessons.scheduled_at` timestamp **NOT NULL** | **性質** | **高** | **1ライブに複数の開催回がある**（ステージング実測 2,840件、最大 1,657回／ライブ）のに、`live_lessons` は単一の開催日時を要求する。**開催回は `live_lesson_occurrences` 側にあるため、この列は重複した情報を持つ** | **直近の開催予定日を入れる**（過去の回しか無ければ最後の回）。**ダッシュボードの「今日のライブ」がこの列だけを見ており**（`dashboard_repo.go: ListTodaysLiveLessons`）、開催回テーブルを参照していない。**誰も更新しないので移行の翌日には古くなる** — 導出に変えるかは新環境側の課題（[migration-spec の未確定](migration-spec.md#未確定として残っているもの)） |
| `live_lesson_type` tinyint(4) | — | 性質 | 中 | **`0` = オンラインレッスン、`1` = 教室レッスン**（`LiveLessonController::$liveLessonTypeList`）。ステージング実測 15 / 3。**入力の必須項目が逆**で、`0` は `live_lesson_url` 必須、`1` は `facility_id` 必須（`LiveLessonController::570`） | **どちらもライブとして移す。** A22 の `live_lessons.settings` に種別と会場を残す。ReCADemy の教室レッスン3件はすべて施設「ご自身のパソコン」で、**対面の教室ではなく自席でソフトを使う予約枠**だった |
| `live_lesson_url` text | `live_lesson_occurrences.meeting_url` varchar(1000) | 性質 | 中 | **レッスン側の URL → 開催回ごとの URL** へ移す。**`live_lessons.live_room_id`（LiveKit のルーム）とは別物**で、取り違えると会議 URL が消える。text → varchar(1000) の切り捨ても起きうる | 全開催回に同じ URL を複製する。**桁溢れは抽出時に検査**（ステージング実測の最大は 77文字で余裕がある）。`live_room_id` は NULL のままにする |
| `capacity` / `reserve_start_day` / `reserve_end_day` / `reserve_end_time` | `occurrences.capacity` / `reserve_opens_at` / `reserve_closes_at` | 性質 | 中 | **レッスン側の既定値が落ちる。** 旧は開催回側にも同名の列があり、**開催回の値が優先、無ければレッスン側**という解決をしている。単位も違う（レッスン側は「何日前」の int、開催回側は日付・日時） | 開催回へ展開するときに**レッスン側の既定値で埋める**（→ [migration-spec 3.2](migration-spec.md#32-変換transform)）。**レッスン側の生値も A22 の `live_lessons.settings` に残す** |
| `reserve_max_count` / `reserve_max_count_start_date` | — | カラム | 中 | **1人あたりの予約上限が落ちる。** 「1人◯回まで」の運用ができなくなる | A22 の `live_lessons.settings`（json）に移す。**判定する機能は新環境に無い**ので、機能を作るかは別途決める |
| `detail_tag_head` / `detail_tag_body` text **NOT NULL** | — | カラム | 中 | 詳細画面に埋め込む HTML タグが落ちる | A22 の `live_lessons.settings` に移す |
| `live_lesson_cate_id` int(11) | — | カラム | 低 | ライブ側が持つカテゴリ ID。**ステージング実測では全件 NULL か 0 で、使われていない**（実際の紐付けは `live_lesson_lesson_cate`） | **移さない。** 値が入っていない列で、同じ意味の中間表が別にある。本番ダンプで値が入っていれば移す |
| `lesson_instructor_id` | `courses.instructor_id` | 性質 | 中 | ライブの講師。**新は course 単位でしか講師を持てない**ので、ライブごとの講師が畳まれる | 受け皿 course の `instructor_id` に使う。**案B（course 1本）だと18人分が1人に畳まれる**ので、A22 の `live_lessons.settings` に元の講師 ID も残す。ステージング実測では全18件に講師が設定され、孤児は0件 |
| `item_ticket_price` | `live_lesson_ticket_requirements.cost` | 性質 | 中 | 1予約あたりの消費枚数。**`cost` には `CHECK (cost >= 1)` がある**ので、`0`（= チケット不要）を入れられない | **`0` の行は `live_lesson_ticket_requirements` に行を作らない**（行が無い = チケット不要）。ステージング実測は 18件中 15件が `0` |
| `img_file_name` | — | カラム | 低 | ライブの画像が落ちる | L9 でファイルを移送し、A22 の `live_lessons.settings` に URL を入れる。ステージング実測2件 |
| `facility_id` | — | 性質 | 中 | **教室レッスンの開催場所。** `facility` は集合研修（X01、対象外）のテーブル。ステージング実測は3件とも `facility_id = 1`（施設名「ご自身のパソコン」、住所・TEL・URL すべて空） | **施設名と説明を A22 の `live_lessons.settings` に文字列で残す**（`facility` テーブルごとは移さない）。**本番に住所や地図が要る施設があれば別表の追加が要る**（[migration-spec 1-3](migration-spec.md#1-4-本番ダンプ受領後に確認すること)） |
| `save_file_name1..3` / `disp_file_name1..3` | — | カラム | 低 | 添付資料3組が落ちる | **ステージング実測0件**。本番で件数を確認し、あれば L9 で移送する |
| `public_chk` / `valid_chk` / `send_pc_chk` / `send_mobile_chk` / `sort_no` | `lessons.status` / `sort_order` ほか | カラム | 低 | 外部公開・有効フラグ・メール送信設定が落ちる。`valid_chk` は `lessons.status` に写せるが、**残り4列は受け皿が無い** | `valid_chk` → `status`（有効→`published` / 無効→`draft`）、`sort_no` → `lessons.sort_order`。残りは A22 の `live_lessons.settings` に移す |
| `del_chk` | `lessons.status = 'deleted'` | 性質 | 中 | 削除済みのライブ（ステージング実測3件）を表す先 | `content_statuses.deleted`（オンデマンドで追加済み）を使う。**`valid_chk` より `del_chk` を優先**する |
| `regist_user_id` / `update_user_id` | — | カラム | 低 | 登録者・更新者が落ちる | A22 の `live_lessons.settings` に移す |
| — | `live_lessons.live_room_id` varchar(255) | カラム | 低 | LiveKit のルーム ID。旧に対応概念なし | NULL のまま。cutover 後に新環境が採番する |

**まとめ**: 受け皿が無い列 13 / 変換規則が要る列 8 / **高 3 件**

### `live_lesson_cate` → なし

`live_lesson_cate` (8列) → なし ／ ETL段 — ／ ローカルデータ数 65 / C ／ ステージング実測 5件（削除済み0件）

| 旧カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|:--:|---|---|
| 全8列 | **テーブル** | **高** | **受け皿が無い。** 新環境にライブのカテゴリという概念が無く、`course_categories` は**講座のカテゴリ**で粒度が違う | **`live_lesson_categories` を追加する**（→ A23）。**案A で受け皿 course を作るなら、その course 名の出どころにもなる**ので、捨てる前に吸い上げる |
| `live_lesson_cate_name` varchar(200) | 型 | 低 | ステージング実測の中身は「testyoga / フルート / ギター / ドラム / ソフト予約」 | A23 の `name` に移す |
| `sort_no` / `del_chk` / `regist_user_id` | カラム | 低 | 並び順・削除・登録者 | A23 に `sort_order` / `deprecated_at` / `created_by` を持たせる |

**まとめ**: 受け皿が無い列 8 / **高 1 件**

### `live_lesson_lesson_cate` → なし

`live_lesson_lesson_cate` (3列) → なし ／ ETL段 — ／ ローカルデータ数 614 / C ／ ステージング実測 6件

| 旧カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|:--:|---|---|
| `(live_lesson_id, live_lesson_cate_id)` | **テーブル** | **高** | **ライブとカテゴリは多対多**だが、受け皿が無い。**`live_lesson.live_lesson_cate_id` ではなくこちらが正**（前者は使われていない） | A23 と対の中間表 `live_lesson_category_links` を追加する。**案A の受け皿 course を作るときの入力**でもある |
| — | — | **性質** | **高** | **ステージング実測では 18件中 6件にしかカテゴリが付いていない。** 案A（カテゴリごとに course）だと**残り12件の行き先が無い** | 未決: **[`live_lesson` の `course_id`](#live_lesson--lessonstypelive--live_lessons) と同じ論点。** 案A を採るなら「カテゴリ無し」の course を別に作る必要がある |

**まとめ**: 受け皿が無い列 3 / **高 2 件**

### `live_lesson_group` → なし

`live_lesson_group` (6列) → なし ／ ETL段 — ／ ローカルデータ数 160 / C ／ ステージング実測 **0件**

| 旧カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|:--:|---|---|
| `(live_lesson_id, group_id)` | テーブル | 中 | **ライブをグループ単位で公開する仕組みが落ちる。** 新環境の `lessons` に公開範囲の概念が無い | `live_lesson_group_targets` を追加する（→ A24）。参照先のグループは基盤（A10）で移行済み。**ステージング実測0件なので、本番ダンプで件数を確認してから実装する** |

**まとめ**: 受け皿が無い列 6 / 高 0 件

### `live_lesson_limit_item` → なし

`live_lesson_limit_item` (5列) → なし ／ ETL段 — ／ ローカルデータ数 17,345 / C ／ ステージング実測 50件

> **これがライブのアクセス制御の本体。** `LiveLessonModel::36-120` が、ライブを出す条件を
> 「①この商品の受講権限（`payment_item_lesson_authority`）を期間内で持つ ②**そもそも制限が無い**
> ③すでに予約済み」の OR で組み立てている。
>
> **ステージング実測の50件は45件が削除済みで、生きているのは5件だけ。**
> しかも**商品は実在の講座に1対1で紐づいている**（`payment_item_lesson`）。

| 旧カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|:--:|---|---|
| `(live_lesson_id, item_id)` | **テーブル** | **高** | **新環境の同じ仕組みは「講座の受講」**（`ReservationService.verifyEnrolled` → `enrollments`）。粒度が商品から講座に変わる | **受け皿を作らず、ライブをその商品が売っている講座の配下に置く。** `payment_item_lesson_authority` は受講（04）で `enrollments` になるため、**アクセス制御がそのまま写る**。**受け皿の追加は不要**（ライブ専用のアクセス制御表は作らない） |
| （制限が無いライブ） | **性質** | **高** | **lw2 は制限を付けなければ全員に予約できたが、新環境に「講座に属さないレッスン」は無い。** どこに置いても受講が要る。ステージング実測で**13ライブ / 開催回536件 / 予約12件** | 未決: **①全会員をその講座に受講登録する ②ライブも受講必須に運用を変える**（[migration-spec 1-1](../open-questions.md) の #1）。**移行の工夫では埋まらない** |
| `del_chk` | カラム | 低 | 削除フラグ。**50件中45件が削除済み** | 削除済みの行は移さない（行の不在で「制限なし」を表せる） |

**まとめ**: 受け皿が無い列 — / **高 2 件**

### `live_lesson_preview` → なし

`live_lesson_preview` (31列) → なし ／ ETL段 — ／ ローカルデータ数 15 / C ／ ステージング実測 1件

| 旧カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|:--:|---|---|
| 全31列 | テーブル | 低 | **編集中の内容を保存する UI の一時データ。** `preview_key` で画面と結びついており、**保存すると `live_lesson` 側に反映される** | **移行しない**（→ [移行の対象外 B](#b-方針として移行しないもの)）。基盤で `edit_form_data` を移行しないと決めたのと同じ理由 |

**まとめ**: 受け皿が無い列 — / 高 0 件

## C9 ライブ開催回

内訳: [breakdown.md](breakdown.md#c9-ライブ開催回)

### `live_lesson_date` → `live_lesson_occurrences`

`live_lesson_date` (14列) → `live_lesson_occurrences` (15列) ／ ETL段 L5 ／ ローカルデータ数 23,324 / C ／ ステージング実測 2,840件（うち削除済み 817件）

そのまま対応: 2列（`live_lesson_date_from`→`starts_at`、`live_lesson_date_to`→`ends_at`）

| 旧カラム | 新カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|---|:--:|---|---|
| `del_chk` | `canceled_at` datetime(3) | **性質** | **高** | **意味が違う。** `del_chk` は「運営が削除した開催回」、`canceled_at` は「開催を中止した回」。削除を中止として移すと、**受講者の履歴に「中止された」と見える**。ステージング実測で **817件（29%）**が削除済み | **`live_lesson_occurrences.deleted_at` を追加する**（→ A25）。`canceled_at` は `live_lesson_reserve.stop_chk` から作る（下の [`live_lesson_reserve`](../03-enrollment/review.md#live_lesson_reserve--live_reservations) 参照）。**削除済みの開催回も移す**（[移行の原則](../00-template/review.md#移行の原則)の1） |
| 日時型すべて | `starts_at` / `ends_at` ほか **datetime(3)** | 型 | 中 | **この表は `timestamp` ではなく `datetime(3)`。** セッション TZ の自動変換が効かない（`live_lessons.scheduled_at` は `timestamp` なので**挙動が逆**） | **UTC に直した値を明示的に書く**（[共通仕様](../../migration-spec.md)）。同じ区分の中で2つの流儀が混ざるので、**テーブルごとに変換の有無を固定する** |
| `capacity` int NULL可 | `capacity` int + **CHECK `chk_llo_capacity (capacity IS NULL OR capacity >= 1)`** | 型 | 中 | **`capacity = 0` の行があると CHECK 違反で投入できない。** `0` は「定員なし」の意図の可能性がある | ステージング実測は **0件**（NULL が 926件）。本番で出たら **NULL に変換する**か移さないかを決める（→ [migration-spec 1-1](../open-questions.md)） |
| `live_lesson_date_from` / `_to` | **CHECK `chk_llo_period (ends_at > starts_at)`** | 型 | 中 | **終了 ≦ 開始の行があると投入できない。** 旧に制約が無い | ステージング実測は **0件**。本番で出たら移さない（値を作らない） |
| `reserve_start_day` **date** | `reserve_opens_at` datetime(3) | 型 | 中 | **date → datetime で時刻が 00:00:00 になる。** JST の 00:00 を UTC に直すと**前日 15:00** になり、予約開始が実質1日早まる | **JST の 00:00:00 として UTC に変換する**（[共通仕様](../../migration-spec.md) の date → 日時型の規則）。ステージング実測では NULL 0件 |
| `reserve_end_day` datetime | `reserve_closes_at` datetime(3) | 型 | 低 | 開催回ごとに絶対時刻で入っている | JST naive → UTC。ステージング実測では NULL 0件 |
| — | `cancel_closes_at` datetime(3) | 性質 | 中 | **旧に対応列が無い。** テナント設定から計算するしかない | [`config_live_lesson`](../03-enrollment/review.md#config_live_lesson--live_lesson_occurrencescancel_closes_at) から `starts_at − ticket_cancel_day 日 − ticket_cancel_time 時間` で作る |
| `mail_send_chk` tinyint(4) | — | **性質** | **高** | **前日リマインドの送信可否設定が落ちる。** 新は `live_reservations.reminded_at`（送信済み時刻）しか持たず、**送る／送らないの設定を持たない**。ステージング実測で **1,868件（66%）**が送信対象 | **`live_lesson_occurrences.remind_enabled` を追加する**（→ A25）。**これが無いと cutover 後に「送らない」設定の開催回にもリマインドが飛ぶ** |
| `date_type` tinyint(4) | — | カラム | 低 | **`1` = 個別に登録した開催回、`2` = 連日設定から生成した開催回**（`LiveLessonModel::1120`〜`1158` が生成時に書き分けている）。ステージング実測 42 / 2,798 で、**大半が連日設定由来** | A25 の `live_lesson_occurrences.settings`（json）に移す。**A26（連日設定）を移すなら、どの回がルール由来かを示す値になる** |
| `live_lesson_time` int(11) | — | カラム | 低 | レッスン時間（分） | **移さない。** `starts_at` / `ends_at` から導出できる。**旧の値と導出値が食い違う行がないかは抽出時に検査する** |
| `live_lesson_id` | `lesson_id` char(26) + FK → `live_lessons` | 性質 | 中 | 親の引き当て | [`live_lesson`](#live_lesson--lessonstypelive--live_lessons) で採番した ULID に読み替える。**削除済みのライブにぶら下がる開催回が 44件**あるので、親を移さないと巻き添えで落ちる |
| `tenant_id` | `tenant_id` char(26) + FK → `tenants` | — | — | 対応あり | テナント跨ぎはステージング実測 0件 |
| — | `recording_url` / `recording_published` | カラム | 低 | 旧に録画の概念なし | NULL / `0` のまま |

**まとめ**: 受け皿が無い列 3 / 変換規則が要る列 7 / **高 2 件**

### `live_lesson_date_setting` / `live_lesson_date_setting_detail` → なし

`live_lesson_date_setting` (8列) / `_detail` (11列) → なし ／ ETL段 — ／ ローカルデータ数 3,840 / 1,152 / C ／ ステージング実測 86件 / 93件

| 旧カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|:--:|---|---|
| `date_setting_type` / `starting_date` / `target_youbi` / `timing_month` / `timing_day` / `target_time_from` / `target_time_to` | テーブル | 中 | **開催回を自動生成するルール**（毎週火曜10時、毎月15日など）が落ちる。**生成された開催回そのものは `live_lesson_date` に実体化済み**なので過去の予約には影響しないが、**cutover 後に開催回を増やせなくなる** | `live_lesson_recurrence_rules` ＋ `live_lesson_recurrence_details` を追加する（→ A26）。**ルールを解釈して開催回を生成する機能は新環境に無い**ので、機能を作るかは別途決める |
| `del_chk` | カラム | 低 | 削除フラグ | A26 に `deleted_at` を持たせる |

**まとめ**: 受け皿が無い列 19 / 高 0 件

### `live_lesson_exclusion_date` → なし

`live_lesson_exclusion_date` (6列) → なし ／ ETL段 — ／ ローカルデータ数 1,096 / C ／ ステージング実測 128件

| 旧カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|:--:|---|---|
| `exclusion_date` date | テーブル | 中 | **「この日は開催しない」という除外日**が落ちる。連日設定と対になっていて、**片方だけ移すとルールの意味が変わる** | A26 と対の `live_lesson_recurrence_exclusions` を追加する。**A26 を移さないならこちらも移さない**（単体では意味を持たない） |

**まとめ**: 受け皿が無い列 6 / 高 0 件

### `live_lesson_date_preview` → なし

`live_lesson_date_preview` (9列) → なし ／ ETL段 — ／ ローカルデータ数 134 / C ／ ステージング実測 9件

| 旧カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|:--:|---|---|
| 全9列 | テーブル | 低 | 編集中の開催回を保存する **UI の一時データ** | **移行しない**（→ [移行の対象外 B](#b-方針として移行しないもの)）。`live_lesson_preview` と同じ |

**まとめ**: 受け皿が無い列 — / 高 0 件

---

## 新環境に追加するテーブル・カラム

**受け皿が無いものは、原則として新環境に追加して受ける。** 「移行しない」は例外で、その都度理由を書く（下の[移行の対象外](#移行の対象外移行できないもの--移行しないもの)）。

> **migration に落とした形は [マイグレーション対象](schema-additions.md)。** 当てる順序・DDL・ロールバックの注意はそちらにある。
> 実物は `school-launcher/btoc-backend/db/migrations/20260924022810_lw2_content_additions.sql` の1本にまとまっている。

> **DDL を足すだけでは機能しない。** どの項目にも「変更が必要な機能」を併記した。バックエンドは最低でも **構造体（`internal/domain/`）→ repository → service → DTO → handler** の5層、フロントは **型定義 → API クライアント → 画面** を触ることになる。以下では**その定型部分は省き、機能として決めが要るところだけ**を挙げている。

### C1 講座・カテゴリ

| # | 追加するもの | 旧環境の対応 | 変更が必要な機能 |
|---|---|---|---|
| **A1** | `courses.allowed_ip_address` TEXT NULL / `courses.is_used` BOOLEAN NOT NULL DEFAULT TRUE / `courses.settings` JSON NULL | `lesson.allowed_ip_address` / `lesson_is_used` / `lesson` の機能フラグ12列 ＋ `lesson_system` | ・IP 制限の判定を受講開始時に入れる<br>・**`is_used` と `status` を混ぜない**（公開状態と運用中かは別の軸）。管理画面で2軸を出す<br>・`settings` の各フラグ（弱点問題集 / ランキング / SNS 共有 / 問い合わせ / 進捗率表示 / デバイス別公開 / 表示フレーム）は**読み出し側が無い**。機能を作るかを個別に決める |
| **A2** | `course_tags` / `course_tag_links` | `lesson_tag`（19行）/ `lesson_lesson_tag`（39行） | ・講座一覧のタグ絞り込み<br>・講座編集画面のタグ入力<br>・**`category` と併存する**（カテゴリは1件、タグは複数） |
| **A3** | `course_categories.image_url` VARCHAR(512) NULL / `course_categories.created_by` CHAR(26) NULL ／ `content_statuses` に `deleted` | `lesson_cate_img_file_name` / `regist_user_id` ／ `lesson.del_chk` / `unit.del_chk` | ・カテゴリ画像の表示（**`icon` とは別物**。アイコン識別子に流用しない）<br>・**`deleted` を一覧から外す**判定（`is_visible=FALSE` / `is_editable=FALSE` で入れてある） |
| **A21** | 代理講師の `users` 行（**DDL ではなくデータ**） | 該当なし（lw2 に講座単位の講師が無い） | ・**`courses.instructor_id` は NOT NULL のまま。** 移行ツールが1行作って全講座に割り当てる<br>・`password_hash` を空にして**ログインできない行**にする<br>・**対応表を受け取ったら付け替え、代理講師のままの講座が0件になったことを確認する** |
| **A27** | `courses.legacy_id` INT NULL ＋ UNIQUE `uk_courses_legacy (tenant_id, legacy_id)` / `lessons.legacy_id` ＋ `uk_lessons_legacy` | `lesson.lesson_id` / `unit.unit_id` | ・**移行ツールが旧 ID で親子を突き合わせるのに要る**（無いと dry-run が止まる）<br>・cutover 後の問い合わせ調査で「旧画面のこの講座」を引く手段になる<br>・**ライブ由来の `lessons` は NULL のまま**（採番系が違うので衝突する。→ A22） |

### C2 ユニット・動画

| # | 追加するもの | 旧環境の対応 | 変更が必要な機能 |
|---|---|---|---|
| **A4** | `lessons.open_at` / `close_at` DATETIME(3) NULL、`close_after_days` INT NULL、`drip_delay_basis` VARCHAR(16) NOT NULL DEFAULT 'enrollment'、`complete_message` / `search_keyword` TEXT NULL、`duration_min` INT NULL、`settings` JSON NULL | `unit.open_datetime` / `close_datetime` / `close_day_from_lesson_start_date` / `open_day` / `payment_open_day` ほか | ・**絶対日時の開閉判定**（新は相対日数しか見ていない）<br>・**`drip_delay_basis` を見る**。受講開始起点と決済起点を1列に畳むと起点が消える<br>・修了時メッセージの表示、検索キーワードでの絞り込み、想定学習時間の表示 |
| **A5** | `video_lessons.complete_type` VARCHAR(32) NULL / `skip_prevention` BOOLEAN NOT NULL DEFAULT FALSE / `settings` JSON NULL | `lecture_complete_type` / `pmovie_complete_type` / `skip_prevention_setting` | ・**「どこまで見たら修了か」の判定**。無いと移行後に修了状態がずれる<br>・早送り禁止の再生制御（資格・研修系の要件だった場合の後退を防ぐ） |
| **A20** | `lesson_types` に `quiz` / `assignment` / `document` / `discussion` / `skill_check` | `unit_type_id` 2 / 4 / 6 / 7 / 8 | ・**これが無いとテスト・課題・資料が全部 `text` に畳まれる**<br>・種別ごとの受講画面の出し分け<br>・**`discussion`（7）/ `skill_check`（8）も足す**（2026-09-28 決定）。ユニットは移し、中身（投稿・診断結果）はこの区分の範囲外 |

### C3 受講制御

| # | 追加するもの | 旧環境の対応 | 変更が必要な機能 |
|---|---|---|---|
| **A15** | `lesson_preconditions`（`lesson_id` / `required_lesson_id`） | `unit_precondition`（37行） | ・**受講画面の進行制御。** テーブルだけでは効かず、**無いまま cutover すると全ユニットが最初から受講できる**<br>・前提未達のユニットをどう見せるか（隠す / 灰色で出す）を決める |

### C5 テスト定義

| # | 追加するもの | 旧環境の対応 | 変更が必要な機能 |
|---|---|---|---|
| **A6** | `quiz_question_labels.legacy_id`（分類。当初の `quiz_question_categories` から統合）/ `quiz_question_banks` | `question_cate` / `question`（3,880行） | ・**問題バンクの管理画面**（テストに属さない問題の一覧・編集）<br>・出題条件から問題を引く出題ロジック<br>・分類は管理画面の「カテゴリ」として見え、編集できる（2026-09-28 に統合） |
| **A7** | `quiz_questions.bank_id`（＋FK）/ `image_url` / `name` / `hint` / `required`、`quiz_options.image_url`、`quizzes.max_attempts` / `suspend_enabled` / `display_settings` ／ `quiz_question_types` に `free_text` | `question_name` / `hint` / 画像ファイル名 / `test.exam_max_number` / `suspended_chk` / 表示設定6列 | ・受験回数の上限チェック<br>・中断・再開（`suspend_enabled`）<br>・正解 / 解説 / 点数を見せるかの出し分け<br>・**`free_text` は候補との完全一致で自動採点する。** lw2 の `UserLearningLessonModel::_markAnswers` が `question_type_id == 3` のとき `explode('|', answer)` した候補に `in_array` で判定しており、移行先も同じ形。**正解候補は `quiz_options` に `is_correct = TRUE` の行として展開する**（候補はすべて正解。記述式に不正解の選択肢は無い） |
| **A8** | `quiz_question_rules`（カテゴリ・難易度・出題数） | `test_sub`（285行） | ・**ランダム出題。** 「このカテゴリ・この難易度から N 問」を解釈する出題ロジック<br>・**これが無いと固定リストのテストにしかならない**<br>・**スキーマだけ先に置いてある**（2026-09-28 決定）。作るかどうかは cutover 前に決める（→ [確認事項 C6](../open-questions.md)） |

### C6 課題定義

| # | 追加するもの | 旧環境の対応 | 変更が必要な機能 |
|---|---|---|---|
| **A13** | `assignment_materials`（配布資料を行に展開）/ `assignments.due_after_days` / `video_url` / `settings` | `report_disp_file_name1-5` / `limit_Date_Num` / `report_pmovie_token` ほか | ・配布資料のダウンロード（**ファイル本体は L9 の移送が要る**）<br>・受講開始起点の提出期限計算<br>・課題の説明動画の再生<br>・**提出側（`submission_files` ほか）は受講（3）の担当**（→ [03-enrollment](../03-enrollment/review.md)） |

### C7 アンケート定義

| # | 追加するもの | 旧環境の対応 | 変更が必要な機能 |
|---|---|---|---|
| **A12** | `survey_pages`（UNIQUE は `(tenant_id, lesson_id, legacy_id)`）/ `survey_lessons.name` / `survey_questions.page_id`（＋FK）/ `image_url`、`survey_questions.prompt` を TEXT へ、`survey_question_options.image_url` ／ `survey_question_kinds` に `file_upload` | `enquete_page` / `enquete_name` / 設問画像 / 添付設問 | ・ページ単位の設問表示とページ送り<br>・**UNIQUE に `lesson_id` を含めた理由**: 1つの `enquete` を複数ユニットが参照する（実測7件）。テナント単位だと 89行中 60行が入らない<br>・`prompt` を TEXT に広げたので**入力欄の文字数制限を合わせる**<br>・**回答側（`survey_responses` ほか）は受講（3）の担当** |

### C8 ライブ定義

| # | 追加するもの | 旧環境の対応 | 変更が必要な機能 |
|---|---|---|---|
| **A22** | `live_lessons.legacy_id` ＋ UNIQUE `uk_live_lessons_legacy` / `live_lessons.settings` JSON NULL | `live_lesson.live_lesson_id` ほか（予約上限・詳細 HTML・公開設定・画像・元の講師・種別・施設） | ・**`lessons.legacy_id` には入れない。** オンデマンドが `unit.unit_id` で使っており、実測18件中11件が衝突する<br>・1人あたりの予約上限（`reserve_max_count`）の判定は**新環境に無い**。機能を作るかを決める<br>・教室レッスンの会場（`facility`）は文字列で残すだけ。住所や地図が要るなら別表が要る |
| **A23** | `live_lesson_categories` / `live_lesson_category_links` | `live_lesson_cate`（5件）/ `live_lesson_lesson_cate`（6件） | ・**ライブとカテゴリは多対多**（`live_lesson.live_lesson_cate_id` は使われていない）<br>・ライブ一覧のカテゴリ絞り込み |
| **A24** | `live_lesson_group_targets`（`lesson_id` / `group_id`） | `live_lesson_group`（実測0件） | ・グループ単位の公開判定。参照先のグループは基盤 A10 で移行済み<br>・**実測0件なので、本番ダンプで件数を確認してから実装する** |

### C9 ライブ開催回

| # | 追加するもの | 旧環境の対応 | 変更が必要な機能 |
|---|---|---|---|
| **A25** | `live_lesson_occurrences.deleted_at` / `remind_enabled` / `settings` ＋ `idx_llo_deleted` | `live_lesson_date.del_chk`（実測817件 = 29%）/ `mail_send_chk`（1,868件 = 66%）/ `date_type` | ・**`del_chk` を `canceled_at` に写さない。** 「運営が削除した」を「開催を中止した」として移すと受講者の履歴に中止と見える<br>・**`remind_enabled` が無いと、送らない設定の開催回にもリマインドが飛ぶ** |
| **A26** | `live_lesson_recurrence_rules` / `_details` / `_exclusions` | `live_lesson_date_setting`（86件）/ `_detail`（93件）/ `live_lesson_exclusion_date`（18件） | ・**ルールを解釈して開催回を生成する機能が新環境に無い。** 生成済みの回は `live_lesson_occurrences` に実体化しているので過去の予約には影響しないが、**無いと cutover 後に開催回を増やせなくなる**<br>・除外日はルールと対。**片方だけ移すと意味が変わる** |

### 移行の対象外（移行できないもの / 移行しないもの）

**いずれも「受け皿が無いから落とす」ではない。** 理由の性質で2つに分かれる。

#### A. 移行できないもの

**移そうとしても成立しない。** 旧と新で構造が違い、値をそのまま置く先が無いもの。

| 対象 | なぜ移行できないか |
|---|---|
| `unit_exemption`（実測1行） | **旧は規則、新は会員ごと。** lw2 は `(unit_id, exemption_unit_id, exemption_score)` で「ユニット A で◯点以上なら B を免除」という**規則**を持つ。会員ごとの免除表（当初 `lesson_exemptions` として追加しかけた）では、**何行入れればよいかが決まらない**。**受け皿は取り下げた** — 前提条件（A15）側の拡張（`exempt_by_lesson_id` ＋ `min_score`）として設計し直す |
| `live_lesson_limit_item`（ライブの商品別アクセス制御） | **粒度が商品から講座に変わる。** 新環境の同じ仕組みは「講座の受講」（`enrollments`）で、`payment_item_lesson_authority` が受講（3）で `enrollments` になるため**アクセス制御はそのまま写る**。ライブ専用の受け皿を作る必要が無い |

#### B. 方針として移行しないもの

**移せるが、移さないと決めたもの。**

| 対象 | 理由 |
|---|---|
| `live_lesson_preview` / `live_lesson_date_preview` 全体 | **編集中の内容を保存する UI の一時データ。** 画面を開き直せば作り直される |
| `facility` テーブル全体 | **集合研修（X01、対象外）のテーブル。** 実測3件はすべて施設「ご自身のパソコン」で住所・TEL・URL が空。施設名と説明は A22 の `live_lessons.settings` に文字列で残す |
