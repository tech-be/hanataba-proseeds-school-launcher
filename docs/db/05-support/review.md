# サポート機能 — 突き合わせ

[サポート機能の内訳](breakdown.md) の対応表と **1対1で対応**する。内訳の行それぞれに `###` 見出しが1つあり、
**順序も内訳と同じ**。ひな形は [00-template/review.md](../00-template/review.md)。

- 観点（テーブル / カラム / 型 / 性質）と深刻度（高 / 中 / 低）の定義は [README.md](../README.md#突き合わせの4つの観点)
- **「内容」は問題点だけ、「修正方法」はどう直すかだけ。** 修正方法が `未決:` で始まるものは**実装前に閉じるべき論点**
- 本文中の「ステージング実測」は 2026-09-18 のダンプで `tenant_id = 10`（ReCADemy）に絞った値

> **[移行の原則](../00-template/review.md#移行の原則)に従う。** 対象外のデータ以外はすべて移行し、
> 受け皿が無ければ追加し、元の構造を維持する。

---

## S1 LINE 友だち紐付け

### `user.line_id` ほか → `line_links`

**実装済み**（`support.1`）。基盤で移した会員に LINE の紐付けを足す。
突き合わせは[基盤の `user`](../01-foundation/review.md) 側にある。

### `line_send` / `line_send_batch` / `line_message` → なし

ローカルデータ数 31 / 36 / 1 ／ いずれも `tenant_id` を持たない

| 旧カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|:--:|---|---|
| テーブル全体 | 性質 | 低 | 配信の履歴と文面 | **純ログなので移さない**（→ [対象外 B](#b-方針として移行しないもの)）。`line_send_logs` は cutover 後の配信から記録を始める |

**まとめ**: 受け皿が無い列 — / 高 0 件

## S2 クーポン

**移行ツールは未実装。**

### `coupon` → `coupons`

`coupon` (—) → `coupons` ／ ローカルデータ数 18 / C ／ ステージング実測 7件

| 旧カラム | 新カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|---|:--:|---|---|
| — | `provider_coupon_id` **NOT NULL** | **性質** | **高** | **決済代行側のクーポン ID で、lw2 に対応する値が無い。** この値が決まらないと1行も入らない | 受け皿を NULL 可にするか、**移行用の合成値を入れるか**を決める。**制約は緩めない方針**なので、合成値の形を運営と決める |
| 割引の指定 | `discount_types` | 性質 | 中 | 定額と定率の区別 | `discount_types` の値に写す |
| 有効期間 | `coupon_statuses` | 性質 | 中 | 期限切れの表現 | 受講権限（[受講 A10](../03-enrollment/review.md)）と同じく、**期限切れを状態に写すか期日で持つか**を揃える |

**まとめ**: 受け皿が無い列 1 / 変換規則が要る列 2 / **高 1 件**

### `coupon_item` / `coupon_group` / `coupon_user` / `coupon_log` → `coupon_*_targets` / `coupon_redemptions`

ローカルデータ数 21 / 0 / 181 / 4

| 旧カラム | 新カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|---|:--:|---|---|
| `coupon_item.item_id` | `coupon_course_targets.course_id` | 性質 | 中 | **粒度が商品→講座に変わる。** 商品と講座が 1:N | 課金（4）の商品→講座の対応で解決する。**課金が先** |
| `coupon_group` | `coupon_user_targets` | 性質 | 低 | 実測0件 | 本番で出たら扱いを決める |

**まとめ**: 受け皿が無い列 — / 変換規則が要る列 2 / 高 0 件

### `coupon_live_lesson` → なし

`coupon_live_lesson` (7列) → なし ／ ETL段 — ／ ローカルデータ数 10 / C ／ ステージング実測 **0件**

| 旧カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|:--:|---|---|
| `(coupon_id, item_id, live_lesson_id)` | テーブル | 中 | **ライブ単位のクーポンが落ちる。** 新環境の `coupon_course_targets` は**コース単位**で、ライブ単位の割引を表現できない | **クーポン本体（`coupon`）は課金区分（未コミット）**なので、**その区分と合わせて決める**。ライブ側で先に受け皿を作らない。ステージング実測0件 |

**まとめ**: 受け皿が無い列 7 / 高 0 件

---

---

## S3 お知らせ

**移行ツールは未実装。**

### `announce` / `news` → `announcements`

ローカルデータ数 37 / 309 ／ ステージング実測 35 / 267件

| 旧カラム | 新カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|---|:--:|---|---|
| 2系統のテーブル | `announcements` **1表** | 性質 | 中 | **旧は「お知らせ」と「ニュース」が別表。** 1表に寄せると区別が消える | 区別が要るなら種別の列を足す。**要否を運営と決める** |
| 配信期間 | `announcement_statuses` | 性質 | 中 | 公開期間の表現 | |
| （副）添付 | — | **性質** | **高** | **`announcements` に添付カラムが無い**（ファイル 296件） | 受け皿を追加するか、**添付を落とすことを受け入れる**かを決める |
| `news_reply` | — | カラム | 低 | ニュースへの返信（13件） | 受け皿なし |

**まとめ**: 受け皿が無い列 2 / 変換規則が要る列 2 / **高 1 件**

### `announce_user` / `news_user` → `announcement_reads`

ローカルデータ数 1,147 / 1,214 ／ どちらも `tenant_id` を持たない

**`news_user` は写さない方針**（既読 5.5%）。`announce_user` だけ移す。

### `login_dialog_log` → なし

ログイン後モーダル（実測28件）。**受け皿なし**。PDF の `config_dialog` は lw2 に実在しない。

### `mail_follow_setting` ほか → `retention_rules` / `retention_sends`

ローカルデータ数 5 / 40。受け皿はある。**送信ログ（`mail_follow_user_log`）は純ログなので移さない。**

### `mail_template` ほか13件 → `tenant_email_templates` / `email_send_logs` ほか

ローカルデータ数 10 / 2,771 ／ ステージング実測 テンプレート7件

| 旧カラム | 新カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|---|:--:|---|---|
| 文面 | `tenant_email_templates` | 型 | 低 | テンプレート本文 | そのまま移す |
| `mail_send` ほか送信ログ | `email_send_logs` | 性質 | 低 | 送信履歴 2,771件 | **純ログなので移さない。** cutover 後の送信から記録を始める |

**まとめ**: 受け皿が無い列 — / 高 0 件

### `message_send` ほか6件 → なし

Web Push（実測 配信230件 / 購読1,157件）。**受け皿なし。**
`in_app_notifications` はアプリ内通知で Web Push ではない。
**購読はブラウザの許可に紐づくので、移しても cutover 後には使えない。**

## S4 問い合わせ

**移行ツールは未実装。**

### `inquire` / `inquire_answer` → `inquiries`

ローカルデータ数 56 / 62 ／ どちらも `tenant_id` を持たない

| 旧カラム | 新カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|---|:--:|---|---|
| `tenant_id` が無い | `inquiries.tenant_id` **NOT NULL** | 性質 | 中 | **`inquire_cate` と join しないとテナントが決まらない** | join して絞る。落とすと全73テナントが混ざる |
| 回答が別表 | `inquiries` の列 | 性質 | 中 | 旧は問い合わせと回答が別表で、**1問い合わせに複数回答がありうる**（56 → 62件） | **2件目以降の回答をどう持つか決める。** 1列に畳むと落ちる |
| （副）添付 | — | **性質** | **高** | **`inquiries` に添付カラムが無い**（ファイル **706件・区分最大の塊**） | 受け皿を追加するか、落とすことを受け入れるかを決める |

**まとめ**: 受け皿が無い列 1 / 変換規則が要る列 2 / **高 1 件**

### `inquire_cate` → `inquiry_categories`

ローカルデータ数 16 ／ ステージング実測 7件。**旧カテゴリ → 新カテゴリの対応表 CSV が要る。**

### `thread` / `thread_comment` / `thread_member` → なし

個別メッセージ（実測 20 / 25 / 46件）。**受け皿なし。**
`community_messages` はチャネル型で、1対1のやり取りではない。

## S5 ファイル

内訳: [breakdown.md](breakdown.md) の同名の節

### `unit_attached_file` → `library_materials`

`unit_attached_file` (6列) → `library_materials` (16列) ／ ETL段 L8 + L9 ／ ローカルデータ数 6,250 / C（**recademy 単体では実測3件**）

| 旧カラム | 新カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|---|:--:|---|---|
| `unit_id` | `library_folder_course_targets`（コース単位） | **性質** | **高** | **粒度が変わる。** 旧はユニットに直接添付、新はフォルダをコースに公開する形で、**「このユニットの資料」という結びつきが失われる** | `library_material_lesson_targets` を新設し、**ユニットとの紐付けを保つ**（→ A1）。コース単位の公開はそのまま併存させる |
| `disp_file_name` varchar(200) | `title` varchar(300) **NOT NULL** + `file_name` varchar(300) | 性質 | 低 | 旧にタイトルが無い | 表示用ファイル名を `title` と `file_name` の両方に入れる |
| `save_file_name` | `storage_key` varchar(512) | 性質 | 中 | ファイル名 → オブジェクトキーへの変換が要る | L9 の移送先キーを入れる |
| — | `kind` varchar(32) **NOT NULL** / `content_type` / `size_bytes` | カラム | 中 | 旧に対応列なし | 拡張子から推定する。推定できないものは `library_material_kinds` の既定値 |

**まとめ**: 受け皿が無い列 — / 変換規則が要る列 3 / **高 1 件**

### `unit_attached_file_attribute` / `unit_attached_file_group` → `library_folder_user_targets` / `library_folder_course_targets`

ローカルデータ数 3,663 / 4,349 / C

| 旧カラム | 新カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|---|:--:|---|---|
| `attribute_id` / `group_id` | `library_folder_user_targets` | **性質** | **高** | **公開範囲の軸が変わる。** 旧は属性・グループ単位、新はユーザー単位。展開すると**後から属性を足しても自動で公開されない** | **基盤 [A10](../01-foundation/review.md#新環境に追加するテーブルカラム) / [A11](../01-foundation/review.md#新環境に追加するテーブルカラム) のグループ・属性を参照する形にする**（→ A1）。`library_folder_group_targets` / `library_folder_attribute_targets` を新設し、**軸を保つ**。ユーザー単位への展開はしない |

**まとめ**: 受け皿が無い列 — / **高 1 件**

### `lesson_attached_file` ほか2件 → `library_materials`

`lesson_attached_file` / `_attribute` / `_group` ／ ローカルデータ数 **0 / 0 / 0** / C

**3テーブルとも0行。** 講座単位の添付教材で、recademy では使われていない。

| 旧カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|:--:|---|---|
| テーブル全体 | テーブル | 低 | **移行するデータが無い。** 構造は `unit_attached_file` と同じ | 実装はする（`unit_attached_file` と同じ経路）。**データが0件であることを抽出時に確認する** |

**まとめ**: 受け皿が無い列 — / 高 0 件

### `document_file_detail` → `library_materials`

`document_file_detail` (3列) ／ ローカルデータ数 761 / C

| 旧カラム | 新カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|---|:--:|---|---|
| ファイルの説明文 | — | カラム | 低 | **説明文を入れる列が無い** | `library_materials.description` を追加して移す（→ A1） |

**まとめ**: 受け皿が無い列 3 / 高 0 件

### `drive` / `drive_group` → `library_folders`

`drive` (10列) + `drive_group` ／ ローカルデータ数 111 / 429 / C

| 旧カラム | 新カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|---|:--:|---|---|
| `drive_name` text | `library_folders.name` varchar(200) | 型 | 低 | text → varchar(200) で切り捨ての恐れ | 抽出時に200文字超を検査する |
| `dir_name` | — | カラム | 低 | 実ディレクトリ名を入れる列が無い | **例外: 移行しない。** L9 の移送に使うだけで、移送後は参照されない |
| `open_chk` | `published` | 性質 | 低 | 対応あり | そのまま移す |
| — | `audience_type` varchar(32) **NOT NULL** | カラム | 中 | 旧に対応列なし | `library_audience_types` から既定値を決めて入れる |
| `drive_group`（公開グループ） | `library_folder_user_targets` | 性質 | 中 | 公開範囲の軸が変わる | `unit_attached_file_group` と同じく、A1 でグループ単位のまま持つ |

**まとめ**: 受け皿が無い列 1 / 変換規則が要る列 3 / 高 0 件

### なし → `library_material_kinds` / `library_audience_types`

マスタ2件。**旧に対応テーブルなし。** migration で投入する。

### なし → `library_downloads`

`library_downloads`（イベント・履歴）

**旧に対応データなし。** ダウンロード履歴で、**純ログなので空で始める**。

---

## S6 就業支援

**移行ツールは未実装。移行先が career-backend**（btoc とは別 DB）である点が他の項目と違う。

### `recruit` / `recruit_cate` / `recruit_user` → `career:job_postings` ほか

ローカルデータ数 154 / 2 / 574 ／ ステージング実測 154 / 2件（`recruit_user` は `tenant_id` なし）

| 旧カラム | 新カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|---|:--:|---|---|
| 投入先 | **career-backend** | **性質** | **高** | **別サービスの DB。** 移行ツールは btoc に接続しており、そのままでは投入できない | **接続先を増やすか、career は別ツールにするかを決める。** 区分5の中でここだけ構造が違う |
| 応募 | `career:job_postings` の配下 | 性質 | 中 | 応募 574件の受け皿 | career 側のスキーマを確認する |

**まとめ**: 受け皿が無い列 — / **高 1 件**

### `company` → `career:companies`

ローカルデータ数 10 ／ `tenant_id` を持たない。career-backend に受け皿あり。

### `job_career` ほか → `career:learner_career_profiles` / `career:learner_career_skills`

ローカルデータ数 76。career-backend に受け皿あり。

### `interview_record` / `interview_contents` / `interview_status` → `career:interviews` ほか

ローカルデータ数 1 / 80 ／ ステージング実測 1 / 20件。career-backend に受け皿あり。

### `scout` / `portfolio` / `skill_unit` ほか → なし

| 対象 | 実測 | 内容 |
|---|---:|---|
| `scout` ほか4件（S03 スカウト） | 109 | **受け皿なし** |
| `portfolio` ほか7件（S04 ポートフォリオ） | **1,837** | **受け皿なし。この区分で最大のデータ** |
| `skill_unit` ほか29件（S07 スキルチェック） | 1 | **30テーブルで合計 1,137行、実質未使用** |
| `public_learning_skill_unit` ほか7件（S08） | — | **受け皿なし** |

## S7 コミュニティ

**移行ツールは未実装。**

### `bbs` / `bbs_comment` → `discussion_posts` ほか

ローカルデータ数 19 / 33 ／ ステージング実測 16件

| 旧カラム | 新カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|---|:--:|---|---|
| テーブル全体 | `discussion_posts` | 性質 | 中 | **PDF は X だが受け皿はある**（構造は異なる） | 構造の差を実装前に突き合わせる |
| `bbs_set_attribute` / `_group` / `_lesson` / `_payment_item` / `_role` | — | 性質 | 中 | **公開範囲5種の受け皿が無い** | 教材（S5）と同じく**軸を保って追加する**か、落とすかを決める |

**まとめ**: 受け皿が無い列 5 / 高 0 件

### `unit_share` / `footprint` → なし

SNS 共有（707件）と足あと（実測76件）。**どちらも受け皿なし。** 足あとは純ログ。

## 新環境に追加するテーブル・カラム

> **migration に落とした形は [マイグレーション対象](schema-additions.md)。**
> **この区分の migration はまだ無い** — `doctor` が `[TODO]` で出るのが現在の正しい状態。

| # | 追加するもの | 旧環境の対応 | 変更が必要な機能 |
|---|---|---|---|
| **A1** | `library_material_lesson_targets` / `library_folder_group_targets` | `unit_attached_file.unit_id` / `drive_group`（実測0行） | ・**ユーザー単位に展開しない。** 旧はグループ単位で公開範囲を決めており、展開すると**後から会員をグループに足しても自動で公開されない**<br>・ユニット添付には親フォルダが無いので、**移行用のフォルダを1つ作ってそこに入れ**、本来の結びつきは `library_material_lesson_targets` で持つ |

**5-1 LINE 友だち紐付けに追加は無い。** 既存の `line_links` で足りる（移行ツール実装済み）。
**5-2 クーポン / 5-3 お知らせ / 5-4 問い合わせ / 5-6 就業支援 / 5-7 コミュニティ**は移行ツールが未実装で、
追加の要否も未確認。

### 移行の対象外（移行できないもの / 移行しないもの）

#### A. 移行できないもの

| 対象 | なぜ移行できないか |
|---|---|
| `drive` 配下のファイル本体 | **DB に無い。** ディスク上の `dir_name` 配下にあり、DB から作れるのは**フォルダだけ**。ファイルは L9 の移送で運ぶ |

#### B. 方針として移行しないもの

| 対象 | 理由 |
|---|---|
| 属性単位の公開範囲（`library_folder_attribute_targets`） | **旧に対応するデータが無い。** `drive` に属性の列は無く、`drive_attribute` に相当するテーブルも lw2 に存在しない。グループ単位（`drive_group`）だけが実在する。**受け皿は取り下げた** — 属性で公開範囲を切る運用が本番で見つかったときに足す |
| ライブレビュー | **区分が違う。** 受講（3）の [A7](../03-enrollment/review.md#新環境に追加するテーブルカラム) が持つ |
