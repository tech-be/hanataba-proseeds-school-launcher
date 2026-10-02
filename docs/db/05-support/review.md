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

### `line_send` ほか4件 / `line_message` ほか5件 → なし

対象: 配信の履歴 `line_send` / `line_send_batch` / `line_send_user` / `line_send_user_log` / `line_send_batch_log`（ローカル 12,798 / 183,739 / 2,127 / 218,736 / 34,997、実測 31 / 36 / 0 / 41 / 5）、
文面と一時データ `line_message` / `line_message_mail_follow_setting` / `line_message_mail_setting` / `line_message_recruit` / `tmp_line_entry` / `tmp_line_message`（ローカル 1,310 / 96 / 58 / 23 / 0 / 9、実測 1 / — / 1 / 4 / 0 / 0）。
多くは `tenant_id` を持たない

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

### `summary_news_reply_new` / `summary_news_sub_num` → なし

ローカルデータ数 5,521 / 0 ／ ステージング実測 10 / 0件。ニュースの新着返信と既読数の**集計**。本体から作り直せるので移さない。

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

### `lesson_inquiry_user` → なし

ローカルデータ数 0。講座ごとの問い合わせ先。**0件で移すものが無い。**

### `thread` / `thread_comment` / `thread_member` → なし

個別メッセージ（実測 20 / 25 / 46件）。**受け皿なし。**
`community_messages` はチャネル型で、1対1のやり取りではない。

## S5 ファイル

内訳: [breakdown.md](breakdown.md) の同名の節。**実装済み**（`support.5`）。

> **旧より広く見せない（2026-10-01）。** 以前は添付資料を1つの「全員に公開」フォルダに入れており、
> 切り替え後は全会員が、買っていない講座の資料まで見られた。新の公開先はフォルダ単位なので、
> **講座ごとにフォルダを作って「その講座の受講者に公開」**にし、新に機能の無い公開範囲は受け皿に残して
> 機能ができるまで閉じておく。新に同じ機能を作れば、受け皿を読むだけで旧と同じ範囲になる。

### `unit_attached_file` → `library_materials` / `library_material_lesson_targets`

`unit_attached_file` (6列) → `library_materials` (16列) ／ ETL段 `support.5` ＋ L9 ／ ローカルデータ数 6,250 / C ／ ステージング実測 ReCADemy の講座 79・共有講座 173件（移したのは227件）

| 旧カラム | 新カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|---|:--:|---|---|
| `unit_id` | `folder_id`（講座ごとの移行用フォルダ）＋ `library_material_lesson_targets.lesson_id` | **性質** | **高** | **粒度が変わる。** 旧は講座資料のユニットの中に出し、講座を開ける人だけが見えた。新はフォルダ単位で公開し、ユニットに結ぶ仕組みが無い | 講座ごとのフォルダ（`course_enrolled`）に入れて見える範囲を旧に近づけ、ユニットとの結びつきは `library_material_lesson_targets` に残す（A1）。新でユニットの画面に資料を出す機能を作れば、この表を読むだけで旧と同じになる |
| `disp_file_name` varchar(200) | `title` varchar(300) **NOT NULL** + `file_name` varchar(300) | 性質 | 低 | 旧にタイトルが無い | 表示用ファイル名を `title` と `file_name` の両方に入れる |
| `save_file_name` | `storage_key` varchar(512) | 性質 | 中 | ファイル名 → オブジェクトキーへの変換が要る | L9 の移送先キーで置き換える |
| — | `kind` varchar(32) **NOT NULL** | — | — | 新の種別は「アップロードしたファイル」（`file`）と「外部 URL」（`url`）の2つ | 添付資料はすべて `file` |
| — | `content_type` / `size_bytes` | カラム | 低 | 旧に対応列なし。大きさはファイルの実体からしか分からない | **L9 の移送で入れる**（ストレージに上げるときに分かる）。それまでは NULL（受講者の画面にサイズが出ないだけ） |
| （ユニットの `del_chk`） | `published` | 性質 | 中 | 削除済みのユニットの資料は旧で見えない（実測4件） | **非公開で移す** |

**まとめ**: 受け皿が無い列 — / 変換規則が要る列 3 / **高 1 件**

### なし → `library_folders`（講座ごとの移行用フォルダ）/ `library_folder_course_targets`

**lw2 に対応する行は無い。** 添付資料を持つ講座ごとに1つ作る（実測66件）。名前は「講座名（lw2 の添付資料）」、
公開先は `course_enrolled` ＋ その講座。作成日時はその講座の最初の添付資料の登録日時。

> **旧と完全には同じでない。** 旧は無料の講座を受講登録なしで開けたので、その講座の資料も誰でも見えた。
> 新は受講中（`enrollments` が `active`）の会員だけに見せる。**狭まる方向**なので、見せてはいけない人に見えることは無い
> （無料講座の受講登録は [D3](../open-questions.md#d-cutover-の運用で決めておきたいこと)）。

### `unit_attached_file_group` / `unit_attached_file_attribute` → `library_material_group_targets` / `library_material_tag_targets`

ローカルデータ数 4,349 / 3,663 / C ／ ステージング実測 **0 / 0件**

| 旧カラム | 新カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|---|:--:|---|---|
| `group_id` / `attribute_id` | `library_material_group_targets.group_id` / `library_material_tag_targets.tag_id` | **性質** | **高** | **資料ごとの公開範囲の受け皿が無かった。** 旧は資料ごとに見せるグループ・属性を指定でき、両方あれば両方を満たす会員だけに見せた（`LessonController`） | 2表を新設して移す（A6。属性はタグとして）。**新に資料単位の公開先が無いので、指定のある資料は非公開**（`published = FALSE`）で移す。新で機能を作るときに、この2表に行がある資料を公開に戻す |

**まとめ**: 受け皿が無い列 — / **高 1 件**

### `lesson_attached_file` / `_group` / `_attribute` → `library_materials` ほか

ローカルデータ数 **0 / 0 / 0** / C

講座に直接添付した資料。**ユニット添付と同じ経路で移す**（講座のフォルダに入れる。ユニットには結ばない）。
公開範囲は上の2表に、削除済み（`del_chk`）は非公開で。**どの環境でも0行**だが、本番で行があっても黙って落ちない。

### `document_file_detail` → なし（L9 で移す）

`document_file_detail` (3列) ／ ローカルデータ数 761 / C

| 旧カラム | 新カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|---|:--:|---|---|
| `file_path_hash` / `detail` | `library_materials.description` | **性質** | 中 | **資料フォルダの中のファイルの説明文。** キーがディスク上のファイルのパスの md5 で、`tenant_id` も `drive` への参照も無い。説明を付ける先の資料（フォルダの中のファイル）も DB に無い | **DB だけでは移せない。** L9 でフォルダの中のファイルを資料として移すとき、同じ規則でパスの md5 を作って突き合わせ、`description` に入れる |

**まとめ**: 受け皿が無い列 — / 高 0 件

### `drive` / `drive_group` → `library_folders` / `library_folder_group_targets`

`drive` (10列) + `drive_group` ／ ローカルデータ数 111 / 429 / C ／ ステージング実測 3 / 0件

| 旧カラム | 新カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|---|:--:|---|---|
| `drive_name` text | `library_folders.name` varchar(200) | 型 | 低 | text → varchar(200) で切り捨ての恐れ | 200文字超があれば投入で落ちて一覧に出る（実測は全件200文字以内） |
| `dir_name` | — | カラム | 低 | 実ディレクトリ名を入れる列が無い | **例外: 移行しない。** L9 の移送に使うだけ |
| （フォルダの中のファイル） | `library_materials` | **性質** | **高** | **DB に無い**（ディスク上） | L9 の移送で資料として移す |
| `open_chk` / `del_chk` | `published` | 性質 | 低 | 削除済みのフォルダは旧で見えない | `open_chk = 1` かつ削除済みでなければ公開 |
| `drive_group`（公開グループ） | `library_folder_group_targets` ＋ `audience_type` | 性質 | 中 | 新に「グループに公開」が無い。全員に公開すると旧より広がる | グループは `library_folder_group_targets` に残し（A1）、**公開先は「対象者なし」（`specific_users`、対象の会員0人）**。新で「グループに公開」を作れば、この表を読むだけで旧と同じになる |

**まとめ**: 受け皿が無い列 1 / 変換規則が要る列 2 / **高 1 件**

### なし → `library_material_kinds` / `library_audience_types`

マスタ2件。**旧に対応テーブルなし。** migration で投入する。

### なし → `library_downloads`

`library_downloads`（イベント・履歴）

**旧に対応データなし。** ダウンロード履歴で、**純ログなので空で始める**。

---

## S6 就業支援

**移行ツールは助言メモとフォローだけ実装済み**（`support.6`。どちらも btoc に入る）。求人・面談・スキルチェックは未実装で、
**移行先が career-backend**（btoc とは別 DB）である点が他の項目と違う。

### `recruit` / `recruit_cate` / `recruit_user` → `career:job_postings` ほか

ローカルデータ数 154 / 2 / 574 ／ ステージング実測 154 / 2件（`recruit_user` は `tenant_id` なし）

| 旧カラム | 新カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|---|:--:|---|---|
| 投入先 | **career-backend** | **性質** | **高** | **別サービスの DB。** 移行ツールは btoc に接続しており、そのままでは投入できない | **接続先を増やすか、career は別ツールにするかを決める。** 区分5の中でここだけ構造が違う |
| 応募 | `career:job_postings` の配下 | 性質 | 中 | 応募 574件の受け皿 | career 側のスキーマを確認する |

**まとめ**: 受け皿が無い列 — / **高 1 件**

### `recruit_reply` / `summary_recruit_reply_new` / `summary_recruit_sub_num` → なし

ローカルデータ数 548 / 262 / 0 ／ ステージング実測 0 / 0 / 0件。応募へのやり取りとその集計。**ReCADemy は0件。** 求人（`recruit_user`）と一緒に career-backend へ移すかを決める。

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
| `skill_unit` ほか20件（S07 スキルチェック） | 1 | **21テーブルで合計 973行、実質未使用** |
| `public_learning_skill_unit` ほか7件（S08） | — | **受け皿なし** |

### `personal_record_advice` → `admin_notes`

`personal_record_advice` (9列) → `admin_notes`（既存） ／ ETL段 `support.6` ／ ローカルデータ数 33 / C ／ ステージング実測 1件

| 旧カラム | 新カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|---|:--:|---|---|
| テーブル全体 | `admin_notes` | テーブル | 中 | **助言メモの専用の受け皿が無い** | **既存の運営メモに寄せる。** 対象の会員・書いた人・本文の3つが揃う（2026-09-30 決定） |
| `target_user_id` / `user_id` | `user_id` / `author_id` | 性質 | 低 | 旧は「書いた人」が `user_id`、「対象の会員」が `target_user_id` | 取り違えないように写す |
| `advice_memo` | `body` | — | — | — | そのまま |
| `personal_record_advice_id` | — | カラム | 低 | 運営メモに旧 ID の列が無い | 決定論 ULID で再移行の重複を防ぐ |
| `del_chk` | `deleted_at`（2026-10-01 追加） | カラム | 低 | 運営メモに削除の列が無かった | 削除済みも移す。実測0件 |
| `update_user_id` | `updated_by`（追加、A5） | カラム | 低 | 最後に直した人。運営メモに列が無かった | `admin_notes.updated_by` を足して移す。旧の 0 / NULL（直していない）は NULL |

**まとめ**: 受け皿が無い列 2 / 高 0 件

### `follow` → `scout_follows`

`follow` (7列) → `scout_follows`（新設、A2） ／ ETL段 `support.6` ／ ローカルデータ数 382 / C ／ ステージング実測 14件

| 旧カラム | 新カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|---|:--:|---|---|
| テーブル全体 | — | テーブル | 中 | **フォローの受け皿が無い**（スカウト S03 の本体も無い） | `scout_follows` を新設し、旧の構造のまま持つ（A2） |
| `follow_id` | `follow_id` | — | — | 旧 ID | 旧列名で持つ（NULL 可） |
| `user_id` / `followed_user_id` | 同名（ULID） | 型 | 低 | int → 会員の ULID | 決定論 ULID |
| `del_chk` | `deleted_at` | 性質 | 低 | 真偽値 → 日時 | `del_chk = 1` なら `update_date` を入れる |
| `register_date` / `update_date` | `created_at` / `updated_at` | 型 | 低 | JST naive → UTC | 共通の変換 |

**まとめ**: 受け皿が無い列 — / 高 0 件

### `like_user` → なし

`like_user` (6列) → なし ／ ローカルデータ数 27,117 / C ／ ステージング実測 6,559件（親の `like` の種別で ポートフォリオ 6,537 / 掲示板の投稿 4 / 掲示板のコメント 18）

| 旧カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|:--:|---|---|
| テーブル全体（ポートフォリオ） | テーブル | 中 | **ポートフォリオの「いいね」の受け皿が無い**（`like` と `portfolio` も受け皿なし） | 未決: ポートフォリオ（S04）と一緒に決める |
| テーブル全体（掲示板） | テーブル | 低 | 掲示板の「いいね」は新の `discussion_likes` に受け皿がある | 掲示板（S7 `bbs`）を移すときに一緒に移す（未実装） |

**まとめ**: 受け皿が無い列 6 / 高 0 件

### `personal_record_open_status` / `personal_record_detail_open_status` → なし

ローカルデータ数 491 / 0 ／ ステージング実測 **0 / 0件**

学習カルテ（自己紹介・職歴・希望条件・バッジなど）を誰に見せるかの設定。**受け皿なし。実測0件なので移すものが無い。**
学習カルテの本体（S05 就活プロフィール）を移すときに、本番の件数を見て決め直す。

## S7 コミュニティ

**移行ツールは分類だけ実装済み**（`support.7`）。掲示板・SNS 共有・足あとは未実装。

### `bbs` / `bbs_comment` → `discussion_posts` ほか

ローカルデータ数 19 / 33 ／ ステージング実測 16件

| 旧カラム | 新カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|---|:--:|---|---|
| テーブル全体 | `discussion_posts` | 性質 | 中 | **PDF は X だが受け皿はある**（構造は異なる） | 構造の差を実装前に突き合わせる |
| `bbs_set_attribute` / `_group` / `_lesson` / `_payment_item` / `_role` | — | 性質 | 中 | **公開範囲5種の受け皿が無い** | 教材（S5）と同じく**軸を保って追加する**か、落とすかを決める |

**まとめ**: 受け皿が無い列 5 / 高 0 件

### `unit_share` / `footprint` → なし

SNS 共有（707件。画像の `unit_share_image` / `public_unit_share_image` はローカル 7 / 3件、ReCADemy 0件）と足あと（実測76件）。**どちらも受け皿なし。** 足あとは純ログ。

### `community_cate` → `community_categories`

`community_cate` (8列) → `community_categories`（新設、A3） ／ ETL段 `support.7` ／ ローカルデータ数 203 / C ／ ステージング実測 3件

| 旧カラム | 新カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|---|:--:|---|---|
| テーブル全体 | — | テーブル | 中 | **コミュニティの分類の受け皿が無い** | `community_categories` を新設する（A3） |
| `community_cate_id` | `community_cate_id` | — | — | 旧 ID | 旧列名で持つ（NULL 可） |
| `group_id` | `group_id`（`tenant_groups`） | 性質 | 低 | **旧は 0 =「グループ指定なし」** | 0 は NULL |
| `del_chk` | `deleted_at` | 性質 | 低 | 真偽値 → 日時 | `del_chk = 1` なら `update_date` を入れる |

**まとめ**: 受け皿が無い列 — / 高 0 件

### `user_content_viewed` / `content_master` → なし

`user_content_viewed` (7列) → なし ／ ローカルデータ数 271,315 / 3 ／ ステージング実測 1,383件（掲示板 112 / 課題 613 / 学習ユニット 623 / 種別4 35）

| 旧カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|:--:|---|---|
| テーブル全体 | テーブル | 中 | **掲示板・課題のコメントの既読の受け皿が無い**（旧は `BbsModel` / `ReportModel` で未読の印に使う）。新の既読はお知らせ（`announcement_reads`）だけ | 未決: 掲示板（S7）と課題のコメントを新で作るときに一緒に決める。移さないと、切り替え後は全部未読に見える |
| `content_type` = 4 | 性質 | 低 | `content_master` に無い種別（35件） | 旧のソースで意味を確かめてから決める |

**まとめ**: 受け皿が無い列 7 / 高 0 件

### `discussion` / `discussion_board` / `discussion_board_comment` → `discussion_posts` ほか

ローカルデータ数 31 / 13 / 122 ／ ステージング実測 25 / 10 / 7件（共有講座を含む）

| 旧カラム | 新カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|---|:--:|---|---|
| テーブル全体 | `discussion_posts` | 性質 | 中 | **ユニットに付くディスカッション**。ユニットは 02 で `discussion` 型として移したが、中身（設定・板・書き込み）は移していない。新の `discussion_posts` は掲示板向けで、ユニットに結びつかない | 未決: 掲示板（`bbs`）と一緒に受け皿を決める（未実装） |
| `*_disp_file_name1` / `*_save_file_name1` | — | カラム | 低 | 添付ファイル | ファイル移送（L9）と一緒に決める |

**まとめ**: 受け皿が無い列 — / 高 0 件

### `user_learning_discussion` / `user_learning_discussion_alert` → なし

ローカルデータ数 2 / 11 ／ ステージング実測 3 / 4件。ディスカッションのユニットの採点（点数・コメント）と通知の設定。
**受け皿なし。** 上のディスカッションと一緒に決める。

## S8 利用料の集計

**実装済み**（`support.8`）。受け皿は新設した（A4）。**新のアプリはまだ読まない。**

### `config_closing_date` → `tenant_usage_settings`

ローカルデータ数 64 / C ／ ステージング実測 1件

| 旧カラム | 新カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|---|:--:|---|---|
| `closing_date` / `month_end_chk` | `closing_day` / `month_end` | — | — | 締め日と月末締め | そのまま |

**まとめ**: 受け皿が無い列 — / 高 0 件

### `accounting_user` → `tenant_usage_snapshots`

ローカルデータ数 2,403 / C ／ ステージング実測 111件（2017-06〜2026-08）

| 旧カラム | 新カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|---|:--:|---|---|
| （主キーなし） | `id` | 性質 | 低 | 旧は `(tenant_id, batch_date)` で1行 | `batch_date` から決定論 ULID を作る。一意制約も同じ組 |
| 会員数の5列 | 同名 | — | — | 集計値 | そのまま（数え直さない） |

**まとめ**: 受け皿が無い列 — / 高 0 件

### `accounting_user_detail` → `tenant_usage_snapshot_users`

ローカルデータ数 192,053 / C ／ ステージング実測 18,122件

| 旧カラム | 新カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|---|:--:|---|---|
| `user_id` | `user_id` / `legacy_user_id` | **性質** | 中 | **集計した時点の写しなので、旧で消えた会員も含む。** `users` を指す外部キーにそのまま入れると落ちる | 移行先に会員がいれば `user_id` に ULID、いなければ NULL。旧 ID は `legacy_user_id` に必ず残す（新の `user_id` と意味が違うので `legacy_` を付ける） |
| `role_id` | `role` | 性質 | 低 | 旧のロール ID | `user_roles.code` に読み替える（基盤と同じ対応表） |
| `name_sei` / `name_mei` | `name_last` / `name_first` | — | — | 写しの氏名 | そのまま |

**まとめ**: 受け皿が無い列 — / 高 0 件

> **`calc_param`（模試の集計条件）はこの区分ではない。** 06 対象外の [X2 模試](../06-out-of-scope/breakdown.md#x2-模試) に置き、
> 模試と一緒に [E63](../open-questions.md#e-切り替え後の機能で決めておきたいこと) の回答で決める。

## S9 その他（仕分けていなかった表のうち、移さないもの）

**どれも移さない。** 内訳の行ごとに理由を書く。

### `access_log` ほか6件（ログ） → なし

ローカルデータ数 696,319 ほか（A 区分）／ ReCADemy 実測 `access_log` 2,759・`live_lesson_batch_log` 1,417・`file_download_log` 1

| 旧カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|:--:|---|---|
| テーブル全体 | 性質 | 低 | アクセス・ダウンロード・バッチ・CSV 連携の記録 | **純ログなので移さない**（→ [対象外 B](#b-方針として移行しないもの)） |

### `php_session` ほか5件（一時データ） → なし

ローカルデータ数 326 / 39,207 / 16,031 / 553 / 2,307 / 0 ／ ReCADemy 実測 `user_session` 857・`tmp_user_token` 17・`new_redirect_url` 3

| 旧カラム | 観点 | 深刻度 | 内容 | 修正方法 |
|---|---|:--:|---|---|
| テーブル全体 | 性質 | 低 | セッション・トークン・書きかけの学習時間・ログイン後の遷移先・CSV 取り込みの受付 | **移さない。** 切り替えで全員ログインし直すので、旧のセッションとトークンは使えない |

### `code_master` ほか4件（システムのマスタ） → なし

ローカルデータ数 35 / 15 / 197 / 13 / 9。**テナントのデータではない。** ユニットの種別（`unit_type_master`）は
02 で `lesson_types` に読み替え済み（[コンテンツ A20](../02-content/review.md)）。それ以外は新のマスタを使う。

### `function_admin_master` ほか3件（画面の機能の定義） → なし

ローカルデータ数 224 / 42 / 13 / 0。管理画面・受講者画面の機能とトップページの部品の**定義**。
テナントごとの ON/OFF と並び（`function_*_tenant` / `function_admin_role` / `top_parts_setting`）は
01 で `tenants.settings` に**旧のコードのまま**残した（[基盤のテナントの設定](../01-foundation/review.md#テナントの設定2026-09-30-に仕分け)）。
定義は旧の画面の部品で、新に対応が無いので移さない。コードの意味を引くときは lw2 のダンプを見る。

### `batch_schedule` / `batch_schedule_detail` → なし

ローカルデータ数 19 / 19。旧のバッチの実行予定で、全テナント共通。**移さない。** 新のバッチは新の仕組みで動く。

### `search_condition` / `user_generic_config` → なし

ローカルデータ数 402 / 18 ／ ReCADemy 実測 27 / 2件。管理画面の検索条件の保存と、画面の個人設定
（例: `{"default_lesson":{"lessonTimeStatus":"1"}}`）。**旧の画面の部品に結びつく値で、新に対応が無いので移さない。**

### `summary_user_learning_test` → なし

ローカルデータ数 264,521 ／ ReCADemy 実測146件。テストの成績の集計（初回・最終・最高点・受験回数）。
**受験結果（03 の `quiz_attempts`）から作り直せる**ので移さない。

### `config_cookie` / `hosting_capacity` / `user_cookie_log` → なし

**lw2 の DB に表が無い**（lw2 のドキュメントにだけある）。移すものが無い。

## 新環境に追加するテーブル・カラム

> **migration に落とした形は [マイグレーション対象](schema-additions.md)。**
> **migration は school-launcher の `20260930052453_lw2_support_additions.sql`**（`feat/lw2-billing-schema`）。A1〜A6 をまとめて足す。

| # | 追加するもの | 旧環境の対応 | 変更が必要な機能 |
|---|---|---|---|
| **A1** | `library_material_lesson_targets` / `library_folder_group_targets` | `unit_attached_file.unit_id` / `drive_group`（実測0行） | ・**ユーザー単位に展開しない。** 旧はグループ単位で公開範囲を決めており、展開すると**後から会員をグループに足しても自動で公開されない**<br>・ユニット添付には親フォルダが無いので、**移行用のフォルダを1つ作ってそこに入れ**、本来の結びつきは `library_material_lesson_targets` で持つ |
| **A2** | `scout_follows` | `follow`（実測14件） | ・新のアプリはまだ読まない。スカウト（S03）を作るときに使う |
| **A3** | `community_categories` | `community_cate`（実測3件） | ・新のアプリはまだ読まない。掲示板（S7）の分類として使う |
| **A4** | `tenant_usage_settings` / `tenant_usage_snapshots` / `tenant_usage_snapshot_users` | `config_closing_date` / `accounting_user` / `accounting_user_detail`（実測 1 / 111 / 18,122件） | ・新のアプリはまだ読まない。LMS 事業者への課金の計上を新で作るときに使う（[features F13](features.md)） |
| **A5** | `admin_notes.updated_by` | `personal_record_advice.update_user_id` | ・新のアプリはまだ書かない・読まない。運営メモを編集する機能を作るときに使う |
| **A6** | `library_material_group_targets` / `library_material_tag_targets` | `unit_attached_file_group` / `_attribute`、`lesson_attached_file_group` / `_attribute`（実測0行） | ・新に資料単位の公開先が無い。**指定のある資料は非公開で移す**。資料ごとの公開範囲を作るときに、この2表に行がある資料を公開に戻す |

**5-1 LINE 友だち紐付けに追加は無い。** 既存の `line_links` で足りる（移行ツール実装済み）。
**助言メモ（S6）は既存の `admin_notes` に寄せ、足りない「最後に直した人」の列だけ足す**（A5）。
**5-2 クーポン / 5-3 お知らせ / 5-4 問い合わせ、5-6 の求人・面談・スキルチェック、5-7 の掲示板**は移行ツールが未実装で、
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
| S9 のログ・一時データ・システムのマスタ・画面の個人設定・成績の集計（計30表） | **移しても意味を持たない。** 理由は S9 の各節 |
