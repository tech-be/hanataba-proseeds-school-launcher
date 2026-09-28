# 課金 — マイグレーション対象

[突き合わせ](review.md#新環境に追加するテーブルカラム) の追加一覧を、**school-launcher に当てる migration の単位**に落としたもの。

- **当てる先**: `school-launcher/btoc-backend/db/migrations/`（goose 形式。雛形は `make migrate-create`）
- **実物**: `20260928132756_lw2_billing_additions.sql`（ブランチ `feat/lw2-billing-schema`）。A1〜A8 を1本にまとめた
- **当てる時期**: **移行直前**（[migration-spec](migration-spec.md) のフェーズ0）
- **確認**: `python -m migrator doctor` — この区分が未適用なら `[TODO]` で出る

> **チケット（A1 / A2）・決済（A3〜A6）・帳票（A7 / A8）の3つ。** どれも移行ツールの Step が書き込む先なので**必須**。

> **コンテンツ（2）が先。** `ticket_type_lessons` / `live_lesson_ticket_requirements` が
> コンテンツで作るライブの `lessons` を参照する。

## 2種類ある

| 区別 | 意味 | 欠けているとどうなるか |
|---|---|---|
| **必須** | Step が**実際に書き込む先** | `common.0` で止まる。移行できない |
| **計画** | **移行では使わない**もの | 止まらない。`doctor` が `[TODO]` で出す |

**この区分に「計画」はない。**

ツール側の定義は `migrator/steps/schema.py` の `BILLING_SCHEMA`（10件）。**この表とコードは一致させること。**
lookup への値の追加（A5 / A6）は列ではないので一覧に無い。無いと投入時の外部キー確認で止まる。

---

## 適用順

```
1  ticket_types / ticket_grants への列追加           (A1)
2  月次チケット配布                                  (A2) ← users を参照
3  tenant_plans / payments への列追加                (A3 / A4)
4  payment_providers / payment_types への値の追加     (A5 / A6)
5  receipts への列追加                              (A7)
6  規約の本文                                        (A8)
```

---

## 1. `ticket_types` / `ticket_grants` への列追加

**必須。**

```sql
ALTER TABLE ticket_types
    ADD COLUMN legacy_id   INT NULL,   -- 旧 ticket.ticket_id
    ADD COLUMN legacy_type INT NULL,   -- 旧 ticket.ticket_type（user_ticket_log が参照する値）
    ADD UNIQUE KEY uk_tt_legacy (tenant_id, legacy_id);

ALTER TABLE ticket_grants
    ADD COLUMN starts_at DATETIME(3) NULL;   -- 旧 user_ticket.ticket_start_date
```

| 列 | 旧の対応 | 備考 |
|---|---|---|
| `legacy_type` | `ticket.ticket_type` int(11) | **`user_ticket_log.ticket_type` が参照しているのはこの値**（`ticket_id` ではない）。**履歴を移さなくても、あとで人が突き合わせられるように残す** |
| `starts_at` | `user_ticket.ticket_start_date` date | 実測は全件 NULL |

> **`chk_tg_qty (quantity >= 1)` は触っていない。** 使い切った残高（`ticket_num = 0`、実測2件）が
> 入らないが、**緩めるかは運営の判断**（[migration-spec](migration-spec.md) の確認事項）。
> **緩めると決まったらここに追記する**:
>
> ```sql
> ALTER TABLE ticket_grants DROP CHECK chk_tg_qty,
>     ADD CONSTRAINT chk_tg_qty CHECK (quantity >= 0);
> ```
>
> **CHECK は事前検査でも見る。** 見ていなかった頃は dry-run を通って実 INSERT で落ちた。

> **消費の台帳（`ticket_ledger_entries`）に受け皿の追加は要らない。** 表は既にある。
> 旧に消費履歴が無いため、**移行時に予約から台帳行を組み立てて入れる**（運営の合意済み）。
> **欠席（`no_show`）も席を占有する**ので消費済みとして数える — 除くと台帳が0行になる。

---

## 2. 月次チケット配布

**必須。** 旧 `month_user_ticket`（実測1件）。「毎月◯枚まで」の契約と消化状況。

```sql
CREATE TABLE monthly_ticket_allowances (
    id                    CHAR(26)    NOT NULL PRIMARY KEY,
    tenant_id             CHAR(26)    NOT NULL,
    user_id               CHAR(26)    NOT NULL,
    legacy_id             INT         NOT NULL,   -- 旧 month_user_ticket_id
    target_month          VARCHAR(50) NOT NULL,   -- 旧 target_month（'YYYYMM' 等。書式を変えずに移す）
    agreed_on             DATE        NOT NULL,   -- 旧 agreement_date
    max_ticket_count      INT         NOT NULL,
    remaining_count       INT         NOT NULL,   -- 旧 ticket_count（残回数）
    expires_on            DATE        NOT NULL,   -- 旧 limit_date
    legacy_application_id INT         NULL,       -- 旧 application_id（決済 4-2 の移行後に解決）
    is_applied            BOOLEAN     NOT NULL DEFAULT FALSE,   -- 旧 is_application
    is_trial              BOOLEAN     NOT NULL DEFAULT FALSE,
    deleted_at            DATETIME(3) NULL,
    created_at            DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at            DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    UNIQUE KEY uk_mta_legacy (tenant_id, legacy_id),
    KEY idx_mta_user (tenant_id, user_id, target_month),
    CONSTRAINT fk_mta_user   FOREIGN KEY (user_id)   REFERENCES users (id) ON DELETE CASCADE,
    CONSTRAINT fk_mta_tenant FOREIGN KEY (tenant_id) REFERENCES tenants (id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

> **`target_month` は書式を変えずに移す。** `'YYYYMM'` の文字列で、DATE に直すと
> 旧の書式ゆれ（実測を確認していない）を握りつぶす。

> **`tenants` を RESTRICT で参照する。** `cmd/seed` の `cleanupDemoData` に列挙が要る
> （`make check-seed-cleanup` が要求する）。

---

## 3. 決済（A3〜A6）

**必須。** 旧 `payment_item`（商品）と `payment_application`（申込）。暫定の規則は [migration-spec 1-3](migration-spec.md) の P1〜P10。

```sql
ALTER TABLE tenant_plans
    ADD COLUMN legacy_id INT  NULL,   -- 旧 payment_item.item_id
    ADD COLUMN settings  JSON NULL,   -- 試用・受講期間・自動解約・支払日など、新の列に無い設定
    ADD UNIQUE KEY uk_tenant_plans_legacy (tenant_id, legacy_id);

ALTER TABLE payments
    ADD COLUMN legacy_id INT  NULL,   -- 旧 payment_application.application_id
    ADD COLUMN settings  JSON NULL,   -- J-Payment の ID、解約、分割回数、クーポン、税の情報
    ADD UNIQUE KEY uk_payments_legacy (tenant_id, legacy_id);

INSERT INTO payment_providers (code, name_ja, supports_marketplace, supports_subscription, sort_order, is_system)
    VALUES ('legacy_jpayment', 'J-Payment (lw2 から移行)', FALSE, FALSE, 90, TRUE);

INSERT INTO payment_types (code, name_ja, requires_course, is_revenue, sort_order, is_system)
    VALUES ('lw2_purchase', '購入 (lw2 から移行)', FALSE, TRUE, 90, TRUE);
```

> **`legacy_jpayment` は過去の記録を表すだけ。** 新の決済処理はこの値を扱わない。
> **`lw2_purchase` は講座が1つに決まらない購入**（講座2つ以上の商品・講座なし・チケット商品）。
> `course_purchase` は講座1つが必須（`course_purchase_payments.course_id` NOT NULL）で、入れると講座を選ぶことになる。
> 売上には数える（`is_revenue = TRUE`）。

> **継続課金（`learner_subscriptions`）と分割（`installment_plans`）には受け皿を足さない。** lw2 に毎月の課金の行が無く、
> 新の必須 ID（Stripe）も無い。初回の申込だけを `payments` ＋ `subscription_payments`（`subscription_id` NULL）にする。

## 4. 帳票（A7 / A8）

**必須。**

```sql
ALTER TABLE receipts
    ADD COLUMN legacy_id INT NULL,   -- 旧 receipt_log.receipt_log_id（旧で印字していた領収書番号）
    ADD UNIQUE KEY uk_receipts_legacy (tenant_id, legacy_id);

CREATE TABLE tenant_legal_documents (
    id            CHAR(26)     NOT NULL PRIMARY KEY,
    tenant_id     CHAR(26)     NOT NULL,
    kind          VARCHAR(32)  NOT NULL,   -- terms / cancel_policy / privacy_policy / commercial_disclosure
    language_code VARCHAR(5)   NOT NULL,
    title         VARCHAR(200) NULL,
    body          MEDIUMTEXT   NULL,
    external_url  VARCHAR(512) NULL,       -- 本文の代わりに外部ページを出す場合
    created_at / updated_at DATETIME(3),
    UNIQUE KEY uk_tld (tenant_id, kind, language_code),
    CONSTRAINT fk_tld_tenant FOREIGN KEY (tenant_id) REFERENCES tenants (id) ON DELETE RESTRICT
);
```

> **新の `issue_no` は決済ごとの連番**で、旧の番号（`receipt_log_id`）とは別物。旧はダウンロードのたびに1行作り、
> 印字する番号は `receipt_log_id` だったので `legacy_id` に残す。

> **規約の本文はアプリがまだ読まない。** 新は文面を画面に固定で持っており、テナントごとの本文を置く場所が無かった。
> 本文を失わないために受ける。どう見せるかは確認事項 D6。

> **`tenants` を RESTRICT で参照する。** `cleanupDemoData` に `monthly_ticket_allowances` と一緒に列挙してある。

---

## 計画（移行では使わない）

**なし。**

---

## まだ決まっていないもの

**なし**（スキーマとしては）。決済・帳票の移し方は暫定の規則で、運営の回答で変わりうる（[migration-spec 1-3](migration-spec.md)）。
規則が変わっても、多くは `settings` の中身か Step の振り分けで吸収でき、スキーマの追加は要らない見込み。
