# サポート機能 — 移行仕様

区分 **5 サポート機能**（LINE 友だち紐付け / クーポン / お知らせ / 問い合わせ / ファイル /
就業支援 / コミュニティ / 利用料の集計 / その他）を移行ツールでどう流すか。共通の方針は
[migration-spec.md](../../migration-spec.md)、突き合わせは [review.md](review.md)、
追加するスキーマは [schema-additions.md](schema-additions.md)。

> **実装済みは 5-1 LINE / 5-5 ファイル / 5-8 利用料の集計と、5-6・5-7 の一部**（助言メモ・フォロー・コミュニティの分類）。
> 5-2 クーポン / 5-3 お知らせ / 5-4 問い合わせ、5-6 の求人・面談・スキルチェック、5-7 の掲示板は Step も migration も無い。
> 5-6・5-7 の一部と 5-8 は、2026-09-30 に「どの区分にも仕分けていなかった旧テーブル」から足した。

> **この区分は「9項目の寄せ集め」で、依存も投入先もばらばら。** 5-9 その他は移さない表だけ（Step は無い）。
> 1本の流れとして設計せず、項目ごとに独立して扱う。

## 他の区分と違うところ

| 項目 | 違い |
|---|---|
| **5-6 就業支援** | **求人・面談の移行先が career-backend**（btoc とは別 DB）。移行ツールは btoc に接続しており、**そのままでは投入できない**。助言メモ・フォローは btoc に入る |
| 5-8 利用料の集計 | **新のアプリがまだ読まない表**に移す。集計した時点の会員の写しなので、**旧で消えた会員も含む** |
| 5-2 クーポン | **課金（4）の商品→講座の対応が先**。`coupon_item` が商品単位 |
| 5-3 お知らせ / 5-4 問い合わせ | **添付ファイルの受け皿が無い**（296件 / **706件**）。ファイル移送（L9）とセットで決める |

---

## 1. 前提

### 1-1. 運営への確認事項

**この区分の分も含めて [open-questions.md](../open-questions.md) に1枚でまとめてある。**
同じ話を2か所に置かない。

### 1-2. 制約による不整合

**[constraint-violations.md](../constraint-violations.md) にまとめてある。**
NOT NULL / UNIQUE / CHECK に当たるものと、参照先が物理削除されているものを分けて持つ。

### 1-3. 決定済み（再確認だけ）

| 決めたこと | 内容 | 決めた日 |
|---|---|---|
| 教材の公開範囲はグループ単位のまま持つ | ユーザー単位に展開すると、**後から会員をグループに足しても自動で公開されない** | 2026-09-24 |
| 教材は旧より広く見せない | 添付資料は講座ごとのフォルダで「その講座の受講者に公開」。新に機能の無い公開範囲は受け皿に残し、機能ができるまで非公開か「対象者なし」 | 2026-10-01 |
| 属性単位の公開の受け皿は作らない | 旧に対応データが無い（`drive_attribute` に相当する表が lw2 に無い） | 2026-09-24 |
| ライブレビューは受講（3）が持つ | ライブ単位のレビューは `enrollment.6`。この区分の担当ではない | 2026-09-24 |
| 仕分けていなかった旧テーブルは 05 に入れる | 既存の表に寄せられるものは寄せ、無ければ旧の構造のまま新設する（助言メモ → `admin_notes`、フォロー・分類・集計は新設） | 2026-09-30 |
| 逆引きで未分類の表は、01・06 が持つもの以外すべて 05 に入れる | 移すもの（5-6〜5-8）と、移さないもの（5-9 その他。ログ・一時データ・システムのマスタなど）に分けた | 2026-09-30 |
| `calc_param` は保留 | 模試の集計条件。模試（06 対象外）と一緒に [E63](../open-questions.md#e-切り替え後の機能で決めておきたいこと) の回答で決める | 2026-09-30 |

### 1-4. 本番ダンプ受領後に確認すること

- **`coupon_group`**（実測0件）。本番で出たら対象者割当の扱いを決める
- **`bbs_set_*` 5種の公開範囲**。実測を見てから受け皿の要否を決める
- **LINE の公式アカウントを継続するか。** 継続しないなら `line_message` ほかは移す意味が無い
- **添付ファイルの実体**（L9 の移送対象）。件数と総容量

### 1-5. ステージングダンプでの実測（2026-09-18 取得）

| 項目 | 旧テーブル | 全テナント | ReCADemy |
|---|---|---:|---:|
| 5-1 LINE | `line_send` / `line_send_batch` | 31 / 36 | — |
| 5-2 クーポン | `coupon` / `coupon_user` / `coupon_log` | 18 / 181 / 4 | **7** / — / — |
| 5-3 お知らせ | `announce` / `news` | 37 / 309 | **35 / 267** |
| 〃 既読 | `announce_user` / `news_user` | 1,147 / 1,214 | — |
| 〃 メール | `mail_template` / `mail_send` | 10 / 2,771 | **7** / — |
| 〃 Web Push | `message_send` / `subscription` | 230 / 1,157 | — |
| 5-4 問い合わせ | `inquire` / `inquire_answer` / `inquire_cate` | 56 / 62 / 16 | — / — / **7** |
| 〃 個別メッセージ | `thread` / `thread_comment` | 20 / 25 | — |
| 5-5 ファイル | `drive` / `unit_attached_file` | 111 / 6,250 | **3** / **79**（共有講座 173。移したのは 227） |
| 5-6 就業支援 | `recruit` / `portfolio` / `scout` | 154 / 1,846 / 111 | **154 / 1,837 / 109** |
| 5-7 コミュニティ | `bbs` / `unit_share` / `footprint` | 19 / 707 / 77 | **16** / — / **76** |
| 5-6 助言メモ・フォロー | `personal_record_advice` / `follow` | 33 / 382 | **1 / 14** |
| 5-7 分類 | `community_cate` | 203 | **3** |
| 5-8 利用料の集計 | `config_closing_date` / `accounting_user` / `accounting_user_detail` | 64 / 2,403 / 192,053 | **1 / 111 / 18,122** |
| 5-6 いいね | `like_user` | 27,117 | **6,559**（ポートフォリオ 6,537） |
| 5-7 既読・ディスカッション | `user_content_viewed` / `discussion_board` / `discussion_board_comment` | 271,315 / 13 / 122 | **1,383 / 10 / 7** |
| 5-9 その他（移さない） | `access_log` / `user_session` / `summary_user_learning_test` | 696,319 / 39,207 / 264,521 | **2,759 / 857 / 146** |

> 5-6 助言メモ以下の全テナントの値は [legacy-table-coverage.md](../legacy-table-coverage.md)（2026-07-28 ダンプ）、
> ReCADemy の値は 2026-09-30 にローカルの lw2 で数えた値。

---

## 2. データ登録順

**項目ごとに独立している。** 依存は前の区分に対するものだけ。

```
[前提]       区分1 基盤（users / tenant_groups）
             区分2 コンテンツ（lessons — 教材の公開対象が参照する）
                ↓
support.1    LINE 友だち紐付け        ← users
support.5    ファイル                 ← tenant_groups / lessons
support.6    就業支援（助言メモ・フォロー） ← users
support.7    コミュニティ（分類）      ← tenant_groups
support.8    利用料の集計             ← users（会員の写しが、移した会員を指すため）
                ↓
support.2    クーポン（未実装）        ← 課金（4）の商品→講座の対応
support.3    お知らせ（未実装）
support.4    問い合わせ（未実装）
support.6    就業支援（求人・面談・スキルチェックは未実装） ← **career-backend**
support.7    コミュニティ（掲示板・SNS 共有・足あとは未実装）
```

> **フェーズの番号は項目の番号と同じ**（`support.6` は 5-6）。未実装の項目も番号を空けてある。

### 2-2. 実行手順

```bash
.venv/bin/python -m migrator run --dry-run --section support --skip-preflight
.venv/bin/python -m migrator run --section support --skip-preflight
.venv/bin/python -m migrator verify
```

---

## 3. データ移行仕様

### 3.1 抽出（extract）

**`tenant_id` を持たない表が多い。** 親と join して絞る。

| 旧テーブル | 絞り込みの経路 |
|---|---|
| `unit_attached_file` | `unit` → `lesson.tenant_id` |
| `drive_group` | `drive.tenant_id` |
| `inquire` / `inquire_answer` | `inquire_cate.tenant_id` |
| `coupon_item` / `coupon_user` / `coupon_log` | `coupon.tenant_id` |
| `announce_user` / `news_user` | `announce` / `news` の `tenant_id` |
| `recruit_user` | `recruit.tenant_id` |
| `company` | **経路が無い**（`tenant_id` を持たず親も無い）。実測10件を目視で仕分ける |

`personal_record_advice` / `follow` / `community_cate` / `config_closing_date` / `accounting_user` /
`accounting_user_detail` は `tenant_id` を持つので、そのまま絞る。
`accounting_user_detail` は、**移行先に入っている会員**（`users.user_id`）を移行先から読み、写しの会員を引き当てる。

### 3.2 変換（transform）

**ファイル（5-5、実装済み）**

- `drive` はフォルダだけ。**中身のファイルは DB に無く**、ディスク上の `dir_name` 配下にある（L9 で運ぶ）
- **旧より広く見せない**（2026-10-01）
  - ユニット添付・講座添付は、**講座ごとの移行用フォルダ**に入れ、「その講座の受講者に公開」（`course_enrolled` ＋ `library_folder_course_targets`）
  - どのユニットの資料かは `library_material_lesson_targets` に残す
  - 資料ごとのグループ・属性の指定は `library_material_group_targets` / `library_material_tag_targets` に残し、**指定のある資料は非公開**
  - グループで絞っていたフォルダは `library_folder_group_targets` に残し、**公開先を「対象者なし」**（`specific_users`）にする
  - 削除済みのユニット・講座・フォルダ・添付資料は非公開
- 公開範囲は**グループ単位のまま**。ユーザー単位に展開しない
- `kind` は `file`。`content_type` / `size_bytes` は L9 で入れる。`document_file_detail`（フォルダの中のファイルの説明）も L9 で突き合わせる

**就業支援（5-6、助言メモ・フォロー）**

- 助言メモは既存の `admin_notes` に寄せる。旧の `user_id` は**書いた人**（`author_id`）、`target_user_id` が**対象の会員**（`user_id`）、
  `update_user_id` は**最後に直した人**（`updated_by`。足した列。旧の 0 / NULL は NULL）
- 削除済みの助言メモも移す（`admin_notes.deleted_at` を足した。2026-10-01。新のアプリはまだ読まない）
- フォローは `scout_follows` に旧の構造のまま移す。削除済みは `deleted_at` で残す

**コミュニティ（5-7、分類）**

- 旧のグループ 0（指定なし）は `group_id` を NULL にする。削除済みは `deleted_at` で残す

**利用料の集計（5-8）**

- 集計値は数え直さずに写す
- 会員の写しは、**移行先に会員がいれば `user_id` に ULID、いなければ NULL**。旧 ID は必ず `legacy_user_id` に残す
- ロールは基盤と同じ対応表で `user_roles.code` に読み替える

**残る項目**（クーポン・お知らせ・問い合わせ・求人・面談・掲示板）は未実装。実装前に 1-1 を決める。

### 3.3 投入（load）

| 表 | 自然キー |
|---|---|
| `library_folders` / `library_materials` | `(id)` |
| `library_folder_group_targets` | `(folder_id, group_id)` |
| `library_folder_course_targets` | `(folder_id, course_id)` |
| `library_material_lesson_targets` | `(material_id, lesson_id)` |
| `library_material_group_targets` / `library_material_tag_targets` | `(material_id, group_id)` / `(material_id, tag_id)` |
| `admin_notes`（助言メモ） | `(id)`。旧 ID の列が無いので決定論 ULID で重複を防ぐ |
| `scout_follows` | `(tenant_id, follow_id)` |
| `community_categories` | `(tenant_id, community_cate_id)` |
| `tenant_usage_settings` | `(tenant_id)` |
| `tenant_usage_snapshots` | `(tenant_id, batch_date)` |
| `tenant_usage_snapshot_users` | `(tenant_id, batch_date, legacy_user_id)` |

### 3.4 移行の対象外

[review.md の対象外](review.md#移行の対象外移行できないもの--移行しないもの) を参照。
この区分は**受け皿が無いものが多い**。

| 対象 | 実測 | 理由 |
|---|---:|---|
| `portfolio` ほか7件（S04） | 1,837 | **受け皿なし。** この区分で最大 |
| `unit_share`（U12 SNS 共有） | 707 | 受け皿なし |
| `scout` ほか4件（S03） | 109 | 受け皿なし |
| `footprint`（U13 足あと） | 76 | 受け皿なし。純ログ |
| `thread` ほか2件（U10 個別メッセージ） | 20 / 25 / 46 | `community_messages` はチャネル型で 1対1 ではない |
| `message_send` ほか6件（U14 Web Push） | 230 / 1,157 | 受け皿なし。**購読はブラウザの許可に紐づくので移しても使えない** |
| `login_dialog_log`（U04） | 28 | 受け皿なし |
| `mail_send` / `line_send` ほか送信ログ | 2,771 / 31 | 純ログ。cutover 後の送信から記録を始める |
| `skill_unit` ほか20件（S07） | 1 | 21テーブルで合計 973行、実質未使用 |
| `like_user`（ポートフォリオの分） | 6,537 | 受け皿なし。ポートフォリオ（S04）と一緒に決める |
| `user_content_viewed` | 1,383 | 受け皿なし。掲示板・課題のコメントと一緒に決める（**移さないと切り替え後は全部未読に見える**） |
| S9 その他の30表 | — | ログ・一時データ・システムのマスタ・画面の個人設定・成績の集計。理由は [review S9](review.md#s9-その他仕分けていなかった表のうち移さないもの) |

### 3.5 検証

- `verify` が OK になること
- 再実行で 0 行（冪等）
- `out/not-migrated.csv` の件数と理由が 1-1 で決めた内容と矛盾しないこと

---

## 未確定として残っているもの

- **5-2 / 5-3 / 5-4、5-6 の求人・面談・スキルチェック、5-7 の掲示板は Step も migration も無い。** 1-1 が決まってから着手する
- **5-6 のフォロー・5-7 の分類・5-8 の集計は、新のアプリがまだ読まない。** 受け皿に移しただけ（[features.md](features.md) F11〜F13）
- **ディスカッション**（`discussion` ほか5表）と**既読**（`user_content_viewed`）、**掲示板の「いいね」**（`like_user` の22件）。掲示板（`bbs`）と一緒に受け皿を決める
- `calc_param` と模試の集計の表は 06 対象外の X2 に置いた（E63 の回答待ち）
- **就業支援の投入先**（career-backend）。移行ツールの構造に関わるので早めに決める
- **添付ファイル 1,002件**（問い合わせ 706 + お知らせ 296）の受け皿とファイル移送（L9）
