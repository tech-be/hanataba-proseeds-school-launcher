# サポート機能 — 移行仕様

区分 **5 サポート機能**（LINE 友だち紐付け / クーポン / お知らせ / 問い合わせ / ファイル /
就業支援 / コミュニティ）を移行ツールでどう流すか。共通の方針は
[migration-spec.md](../../migration-spec.md)、突き合わせは [review.md](review.md)、
追加するスキーマは [schema-additions.md](schema-additions.md)。

> **実装済みは 5-1 LINE と 5-5 ファイルだけ。** 残る5項目は Step も migration も無い。

> **この区分は「7項目の寄せ集め」で、依存も投入先もばらばら。**
> 1本の流れとして設計せず、項目ごとに独立して扱う。

## 他の区分と違うところ

| 項目 | 違い |
|---|---|
| **5-6 就業支援** | **移行先が career-backend**（btoc とは別 DB）。移行ツールは btoc に接続しており、**そのままでは投入できない** |
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
| 属性単位の公開の受け皿は作らない | 旧に対応データが無い（`drive_attribute` に相当する表が lw2 に無い） | 2026-09-24 |
| ライブレビューは受講（3）が持つ | ライブ単位のレビューは `enrollment.6`。この区分の担当ではない | 2026-09-24 |

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
| 5-5 ファイル | `drive` / `unit_attached_file` | 111 / 6,250 | **3** / **3** |
| 5-6 就業支援 | `recruit` / `portfolio` / `scout` | 154 / 1,846 / 111 | **154 / 1,837 / 109** |
| 5-7 コミュニティ | `bbs` / `unit_share` / `footprint` | 19 / 707 / 77 | **16** / — / **76** |

---

## 2. データ登録順

**項目ごとに独立している。** 依存があるのは次の3つだけ。

```
[前提]       区分1 基盤（users / tenant_groups）
             区分2 コンテンツ（lessons — 教材の公開対象が参照する）
                ↓
support.1    LINE 友だち紐付け        ← users
support.5    ファイル                 ← tenant_groups / lessons
                ↓
support.2    クーポン（未実装）        ← 課金（4）の商品→講座の対応
support.3    お知らせ（未実装）
support.4    問い合わせ（未実装）
support.6    就業支援（未実装）        ← **career-backend**
support.7    コミュニティ（未実装）
```

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

### 3.2 変換（transform）

**ファイル（5-5、実装済み）**

- `drive` はフォルダだけ。**中身のファイルは DB に無く**、ディスク上の `dir_name` 配下にある
- ユニット添付には親フォルダが無いので、**移行用のフォルダを1つ作ってそこに入れ**、
  本来の結びつきは `library_material_lesson_targets` で持つ
- 公開範囲は**グループ単位のまま**。ユーザー単位に展開しない

**残る5項目**は未実装。実装前に 1-1 を決める。

### 3.3 投入（load）

自然キーは `library_folders` / `library_materials` が `(id)`、
`library_folder_group_targets` が `(folder_id, group_id)`。

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
| `skill_unit` ほか29件（S07） | 1 | 30テーブルで合計 1,137行、実質未使用 |

### 3.5 検証

- `verify` が OK になること
- 再実行で 0 行（冪等）
- `out/not-migrated.csv` の件数と理由が 1-1 で決めた内容と矛盾しないこと

---

## 未確定として残っているもの

- **5-2 / 5-3 / 5-4 / 5-6 / 5-7 は Step も migration も無い。** 1-1 が決まってから着手する
- **就業支援の投入先**（career-backend）。移行ツールの構造に関わるので早めに決める
- **添付ファイル 1,002件**（問い合わせ 706 + お知らせ 296）の受け皿とファイル移送（L9）
