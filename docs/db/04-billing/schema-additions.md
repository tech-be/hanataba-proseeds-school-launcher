# 課金 — マイグレーション対象

[突き合わせ](review.md#新環境に追加するテーブルカラム) の追加一覧を、**school-launcher に当てる migration の単位**に落としたもの。

- **当てる先**: `school-launcher/btoc-backend/db/migrations/`（goose 形式。雛形は `make migrate-create`）
- **実物**: **まだ無い。** `20260924…_lw2_billing_additions.sql` として1本にまとめる
- **当てる時期**: **移行直前**（[migration-spec](migration-spec.md) のフェーズ0）
- **確認**: `python -m migrator doctor` — この区分が未適用なら `[TODO]` で出る

> **いまはチケット（4-1）ぶんだけ。** 決済（4-2）と帳票（4-3）は移行ツールが未実装なので、
> 追加が必要かどうかも決まっていない。

> **コンテンツ（2）が先。** `ticket_type_lessons` / `live_lesson_ticket_requirements` が
> コンテンツで作るライブの `lessons` を参照する。

## 2種類ある

| 区別 | 意味 | 欠けているとどうなるか |
|---|---|---|
| **必須** | Step が**実際に書き込む先** | `common.0` で止まる。移行できない |
| **計画** | **移行では使わない**もの | 止まらない。`doctor` が `[TODO]` で出す |

**この区分に「計画」はない。**

ツール側の定義は `migrator/steps/schema.py` の `BILLING_SCHEMA`（4件）。**この表とコードは一致させること。**

---

## 適用順

```
1  ticket_types / ticket_grants への列追加
2  月次チケット配布                        ← users を参照
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

> **`tenants` を RESTRICT で参照する。** `cmd/seed` の `cleanupDemoData` に列挙が要る。

---

## 計画（移行では使わない）

**なし。**

---

## まだ決まっていないもの

**決済（4-2）と帳票（4-3）は移行ツールが未実装。** 追加が必要かどうかもこれから。
受け皿の候補として名前が挙がっているのは `receipt_settings`（消費税）と `user_consents`（特商法・規約）で、
どちらも**既存の表**。列が足りるかは Step を書くときに確かめる。
