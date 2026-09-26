# 課金 — 移行仕様

区分 **4 課金**（チケット / 決済 / 帳票）を移行ツールでどう流すか。共通の方針は
[migration-spec.md](../../migration-spec.md)、突き合わせは [review.md](review.md)、
追加するスキーマは [schema-additions.md](schema-additions.md)。

> **実装済みは 4-1 チケットだけ。** 4-2 決済と 4-3 帳票は Step も migration も無い。

> **コンテンツ（2）が先。** `ticket_type_lessons` と `live_lesson_ticket_requirements` が
> コンテンツで作るライブの `lessons` を参照する。

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
| チケットの消費履歴は移さない | キャンセルに要るのは「誰が予約したか」と「何枚使うか」だけ。**台帳の行は予約から組み立てて作る** | 2026-09-24 |
| 欠席も消費済みとして数える | `occupies_seat = 1`。除くと台帳が0行になる | 2026-09-24 |

### 1-4. 本番ダンプ受領後に確認すること

- **チケット種別の使い分け。** 実測は2件だけで**両方とも同じ名前**、区別が読み取れない
- **`payment_item.item_type` の `0` 以外が何か。** 受講可否判定が `= 0` で絞っている
- **`payment_application` の決済手段の判定条件。** 5種類が1表に同居しており、
  **列名から推測せず `PaymentModel` を読んで確定する**（受講の `cancel_chk` と同じ誤りを繰り返さない）
- **流入元計測**（`trigger_media` / `payment_trigger_media`）は実測0件。本番で出たら扱いを決める

### 1-5. ステージングダンプでの実測（2026-09-18 取得）

| 旧テーブル | 全テナント | ReCADemy | 備考 |
|---|---:|---:|---|
| `ticket` | 41 | **2** | 両方とも同じ名前 |
| `user_ticket` | 3,231 | **8** | 種別なし3 / 残0が2 |
| `user_ticket_log` | 986 | — | 移さない |
| `month_user_ticket` | 54 | **1** | |
| `payment_item` | 336 | **301** | |
| `payment_item_lesson` | 1,134 | — | `tenant_id` なし |
| `payment_application` | 634 | **479** | |
| `receipt_log` | 21 | **21** | |
| `tax` | 1 | — | 全体設定 |
| `agreement` / `cancel_policy` / `privacy_policy` / `tokusyo` | 4 / 2 / 2 / 2 | **2 / 1 / 1 / 1** | |

---

## 2. データ登録順

```
[前提]       区分1 基盤（users）
             区分2 コンテンツ（lessons — ライブぶん）
                ↓
[migration]  A1 ticket_types.legacy_id / legacy_type、ticket_grants.starts_at
             A2 monthly_ticket_allowances
                ↓
billing.1    ticket_types → ticket_type_lessons → live_lesson_ticket_requirements
             → ticket_grants → ticket_ledger_entries → monthly_ticket_allowances
                ↓
billing.2    決済（未実装）
billing.3    帳票（未実装）← 決済に紐づくので後
```

> **台帳（`ticket_ledger_entries`）は受講（3）のライブ予約を参照する。** 予約が先。
> 実装上は `billing.1` の中で予約から組み立てるため、**`enrollment.6` より後に流す**。

### 2-2. 実行手順

```bash
.venv/bin/python -m migrator run --dry-run --section billing --skip-preflight
.venv/bin/python -m migrator run --section billing --skip-preflight
.venv/bin/python -m migrator verify
```

---

## 3. データ移行仕様

### 3.1 抽出（extract）

| 旧テーブル | 絞り込みの経路 |
|---|---|
| `ticket` / `user_ticket` | `tenant_id` を持つ |
| `ticket_limit_lesson` | `ticket` → `tenant_id` |
| `payment_item_lesson` | `payment_item.tenant_id` |
| `payment_application_item` | `payment_application.tenant_id` |
| `tax` | **`tenant_id` を持たない全体設定** |

### 3.2 変換（transform）

**チケット（4-1）**

- `ticket_types.legacy_type` は旧 `ticket.ticket_type`。**`user_ticket_log` が参照するのはこの値**
  （`ticket_id` ではない）。履歴を移さなくても後から突き合わせられるように残す
- **台帳は予約から組み立てる。** 旧に消費履歴が無いため、`live_reservations` の
  席を占有する予約 1 件につき消費 1 行を作る。**欠席（`no_show`）も占有する**

**決済（4-2）・帳票（4-3）**

未実装。実装前に 1-1 の #4〜#6 を決める。

### 3.3 投入（load）

自然キーは `ticket_types` が `(tenant_id, legacy_id)`、`ticket_grants` が `(id)`。

### 3.4 移行の対象外

[review.md の対象外](review.md#移行の対象外移行できないもの--移行しないもの) を参照。

| 対象 | 行数 | 理由 |
|---|---:|---|
| `user_ticket_log` | 986 | 消費履歴。台帳は予約から組み立てる（運営の判断） |
| `analytics_tag` / `trigger_media` / `payment_trigger_media` | 12 / 7 / 7 | 流入元計測。PDF・再判定とも X |
| 継続課金のカード情報 | — | **lw2 の DB に無い**（プロバイダ側） |

### 3.5 検証

- `verify` が OK になること
- 再実行で 0 行（冪等）
- `out/not-migrated.csv` の件数と理由が 1-1 で決めた内容と矛盾しないこと

---

## 未確定として残っているもの

- **4-2 決済と 4-3 帳票は Step も migration も無い。** 1-1 の #4〜#6 が決まってから着手する
- チケットの 1-1 #1〜#3（→ [制約に当たって移らない行](../constraint-violations.md)）
- `certificates.product_id`（受講 A6）は**この区分の移行後に埋める**
- `monthly_ticket_allowances.legacy_application_id` も同じく決済の移行後に解決する
