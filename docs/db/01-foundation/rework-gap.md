# 基盤 — 見直しの差分

移行の見直しの手順 4（[進捗](../rework-progress.md)）。[移行仕様の 0 章](migration-spec.md#0-見直し2026-10-26-決定)で決めたことと、[テスト仕様書](test-spec.md)を実装するために、**今の移行ツール・単体テスト・文書・school-launcher の migration** のどこを直すかを並べたもの。
手順 5 では、この表の順に直す。

- **基準**: school-launcher `hanataba_dev` の `584026af`（2026-10-24）
- **school-launcher の migration の変更**: **無し**（どれも今のスキーマで受けられる）
- **school-launcher のアプリの修正**: 下の 5 章（2026-10-26 に「移したデータが動くための修正も行う」と決めた）

## 1. 移行ツール

| # | 直すもの | 直す先 | 中身 | 根拠 |
|---|---|---|---|---|
| G1 | 旧でログインできない会員を inactive に | `migrator/steps/users.py` の `_status_of` | 削除済み → deleted、無効 → inactive に加えて、**ロックアウト中（`is_lockout = 1`）・利用開始日が空か未来・利用終了日の翌日 0 時を過ぎた → inactive**（旧 `AuthModel.class.php:149-154` と同じ条件）。判定の日は移行を流した日（JST）。期間・ロックアウトの列は今のまま入れる | F-15 |
| G2 | 削除済みの会員のメールを NULL に | `migrator/steps/users.py` の `transform` | `del_chk = 1` の会員は `email = NULL`（ログイン ID を NULL にしているのと同じ扱い） | F-22 |
| G3 | **メールが NULL の会員が流し直しで二重に入らないように** | `migrator/steps/users.py` の `natural_key` | 今の `("tenant_id", "email")` は、メールが NULL だと既存の行を見つけられず、流し直しで同じ会員を二度入れようとする（G2・G5 でメールが NULL の会員が増える）。**`("tenant_id", "user_id")`（旧の会員 ID）にする** | F-12・F-22・冪等性 |
| G4 | 携帯の受け取り設定を移さない | `migrator/steps/user_related.py` の `NotificationOptoutsStep` | `channel = 'mobile'` になる行（`sendmail_mobile_chk`・`notify_footprint_mobile_chk`）は作らず、`drop()` で一覧に出す（理由「移行対象外」、詳細「新は携帯のアドレスに送らない」） | F-51 |
| G5 | 削除済みのタグと割当を移さない | `migrator/steps/org.py` のタグ（`user_tags`）と割当（`user_tag_assignments`）の Step | `attribute.del_chk = 1` のタグと、それを指す割当を作らず、`drop()` で一覧に出す（理由「移行対象外」）。**自動割当の条件（04 の `billing.assign_conditions`）が削除済みのタグを指していれば、同じ理由で一覧に出す**（外部キーで落ちる前に） | F-60 |
| G6 | データの確認（テスト仕様の D のケース）を足す | `migrator/validation/spec_checks.py`（新規）、`verify` の呼び出し（`migrator/cli.py` など） | ケース ID ごとに、新アプリの問い合わせ条件を写した SQL で移行先を確かめる。旧 DB と比べるもの（F-15 の期待する状態など）は旧 DB も読む。結果は `verify` に `[OK] F-15 …` の形で出す | テスト仕様 |
| G7 | 今の照合を決めたことに合わせる | `migrator/validation/legacy_checks.py` の `foundation_checks` | 会員の状態の期待（G1）、メールの期待（G2・補正データの変更）、タグの漏れ（削除済みを除く。G5） | G1・G2・G5 |

## 2. 補正データ（`fixups`）

| # | 直すもの | 直す先 | 中身 | 根拠 |
|---|---|---|---|---|
| G8 | メールが空の会員に合成アドレスを入れない | `fixups/plan.py`（メールが空の会員を「直す行」に数えない）、`fixups/proposals.py` | 新はメールを任意にしたので、メールが空の会員は NULL のまま入る。`not-migrated.csv` にも出なくなる | 移行仕様 0-2 |
| G9 | メールが重複する組の提案を変える | `fixups/proposals.py` の `for_duplicate_email` | 今は「最小の `user_id` に残し、ほかは合成アドレス」。**「最も新しく使われた（`recent_login_date` が最も新しい）会員に残し、ほかは NULL」** にする。運営の回答（確認事項 D11）で差し替える | 移行仕様 0-2 |
| G10 | 今の `overrides.csv` を作り直す | `overrides.csv`（コミットしない） | G8・G9 で `fixups template` を流し直す。合成アドレス 3,040 件が無くなり、重複の組の非保持者が NULL になる | 移行仕様 0-2 |
| G11 | ログイン ID が別の会員のメールと同じ会員を一覧にする | `fixups/check.py`（または `fixups plan` の出力） | 6 名を、運営に渡す一覧として出す（確認事項 D12）。移行は止めない | F-14 |

## 3. 単体テスト

| # | 足す・直すテスト | 置き場所 |
|---|---|---|
| T1 | G1: ロックアウト中・開始日が空・開始日が未来・終了日を過ぎた会員が inactive、終了日の当日は active | `tests/test_steps.py`（`UsersStepTest`） |
| T2 | G2・G3: 削除済みの会員のメールが NULL、自然キーが旧の会員 ID | 同上 |
| T3 | G4: 携帯の受け取り設定が作られず、一覧に出る | `tests/test_steps.py`（`UserRelatedTest`） |
| T4 | G5: 削除済みのタグと割当が作られず、一覧に出る | `tests/test_steps.py`（`OrgStepTest`） |
| T5 | G6: データの確認の各ケースが、期待どおりの行で OK、外れた行で NG になる | `tests/test_spec_checks.py`（新規） |
| T6 | G8・G9: メールの補正の提案 | `tests/test_fixups.py` |

## 4. E2E（新規）

| # | 作るもの | 置き場所 |
|---|---|---|
| E1 | 確認用の DB を読む新アプリを、別のポートで立てる・止める手順（バックエンド :18080・フロント :13000） | `scripts/e2e-stack.sh`（新規） |
| E2 | テスト用の会員のパスワードを、確認用の DB の中だけで入れ直すスクリプト（DB 名が `lw2_schema_check` でなければ止める。パスワードは環境変数） | `scripts/prepare_e2e_users.py`（新規） |
| E3 | テスト用の会員の選び方（`prepare_e2e_users.py suggest` が移行先から役ごとに条件で選び、旧の `user_id` を `e2e/users.json` に書く。`apply` が E2E の見る値を `e2e/.personas.json` に書く） | `e2e/users.example.json`（新規。実際の値のファイルはコミットしない） |
| E4 | Playwright の設定と、テスト仕様の E のケース（F-02・F-17〜F-20・F-23・F-32〜F-34・F-45・F-46・F-52・F-54・F-56・F-57・F-63） | `e2e/`（新規。`package.json`、`playwright.config.ts`、`foundation.spec.ts`） |

**状態（2026-10-26）:** E1〜E4 とも作った（`e2e/helpers.ts` も足した）。E2 は単体テスト `tests/test_prepare_e2e_users.py`。**動かすのは手順 6。**

## 4-2. 手順 6 で見つけて直したもの（2026-10-26）

| # | 直したもの | 直した先 | 中身 |
|---|---|---|---|
| G12 | 投入後の検査がメールの NULL を重複に数えていた | `migrator/validation/postcheck.py`（`email_unique`）、`tests/test_phases.py` | `email IS NOT NULL` で数える。止まったときにアドレスを出さない（件数だけ） |
| G13 | 補正データの雛形で、メールの重複の組に「先に入った会員」が入っていなかった | `fixups/templates.py`、`tests/test_fixups.py` | 組は移行元の会員全体（削除済みを除く）から作る。入れないと「残す 1 人」がまた UNIQUE に当たる |
| G14 | 補正データの検査が以前の規則（メールは必須・削除済みも重複に数える）のままで、アドレスを出していた | `fixups/check.py`、`tests/test_fixups.py` | 削除済みを除いて重複を見る。メールが空でもよく、メールもログイン ID も無い会員だけ NG。会員 ID だけを出す |
| G15 | 試し流し（dry-run）では LINE の共有が一覧に出ず、雛形から LINE の補正が抜けた | `overrides.csv`（コミットしない） | 以前の補正データの LINE の 3 行（4 名のうち 1 名に残す）をそのまま引き継いだ。**雛形が LINE の共有を拾えないのは未対応**（`fixups plan` で移行元から直接見るのが本筋） |
| E5 | E2E の起動スクリプトで、`docker compose run` に無い `--add-host` を使っていた | `scripts/e2e-stack.sh` | 外した |

## 5. school-launcher（作業ブランチ `feat/lw2-migration-rework`）

| # | 直すもの | 直す先 | 中身 | 根拠 | 状態 |
|---|---|---|---|---|---|
| S1 | 受講者のコース別進捗の CSV の「属性名」を、タグ（`user_tags` / `user_tag_assignments`）から出す | `btoc-backend/internal/repository/learner_analytics_repo.go`（558-588 行目あたり）と、その結合テスト | 今は `tenant_attributes` / `user_attribute_values` を読んでいて、移した属性も新で作ったタグも出ない | F-64 | **直さない**（2026-10-26 決定。開発チームへの課題。[sync-issues](../school-launcher-sync-issues.md)） |
| S2 | 個別番号の新しい会員の採番を旧と同じ形に | `btoc-backend/internal/repository/user_personal_number_repo.go`、結合テスト | 旧の ID があるテナント（`tenants.tenant_id`）では `旧のテナント ID + "0" + 連番`（旧 `UserModel.class.php:2157-2166`）。旧の ID が無いテナントは連番のまま（2026-10-26 決定） | 0-3 | **済み**（結合テスト 9 件が通る。専用のテスト用 DB `lw2_rework_test` で確認） |

> B7（自動割当をコースの購入で動かす）は、手元の school-launcher の別のブランチ（`feat/lw2-auto-assign-learning-path-trigger`）で進んでいるようなので、ここでは扱わない。

## 6. 文書

| # | 直すもの | 中身 |
|---|---|---|
| D1 | `migration-spec.md` の 1〜3 章 | 会員の状態（G1）、メール（G2・補正データ）、受け取り設定（G4）、タグ（G5）、自然キー（G3）。0 章と食い違う記述を直す |
| D2 | `review.md`・`breakdown.md` | `users` の `valid_chk` / 期間 / ロックアウトの行、メールの行、通知の行、`attribute` の行 |
| D3 | `../constraint-violations.md` | メールの欠損・重複の扱い（NOT NULL に当たらなくなる） |
| D4 | `../open-questions.md` | 済み（D10〜D13 を足した） |
| D5 | `../school-launcher-sync-issues.md` | 新アプリ側の課題（属性名の CSV・個別番号の桁）を足す |
| D6 | `functional-spec.md` | 変更なし |

## 7. 手順 5 の順番

1. G3（自然キー）→ G2 → G1 → T1・T2
2. G4 → T3、G5 → T4
3. G8〜G11 → T6
4. G6・G7 → T5
5. E1〜E4
6. D1〜D5
7. S1（確認後）
