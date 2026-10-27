# 移行ツールの見直し — 進捗

新システムの機能から見て、移したデータが使えるかを確かめながら移行ツールを見直す（2026-10-26 開始）。
区分ごとに、次の 6 手順で進める。

1. **機能仕様書** — 今の新システムで、その区分のデータを使う機能を書き出す（`functional-spec.md`）
2. **テスト仕様書** — 1 をもとに、移したデータで確かめるテストケースを作る。新システムの E2E も参考にする（`test-spec.md`）
3. **移行仕様** — テスト仕様が通るように移し方を検討する。暫定対応は本番の対応を決める（`migration-spec.md`）
4. **差分** — 3 と今の移行ツール・文書・school-launcher の migration との差分を出す（`rework-gap.md`）
5. **実装** — 差分を実装する（移行ツール・単体テスト・文書）
6. **テスト** — テスト仕様書でテストする（データの確認＋主要な画面の E2E）

手順 3 と 4 の終わりで止めて、確認をもらう。

## 作業の場所

| リポジトリ | ブランチ | 場所 |
|---|---|---|
| このリポジトリ | `main` | — |
| school-launcher | `feat/lw2-migration-rework` | `/Users/ryota.doi/ghq/github.com/proseeds/school-launcher-lw2-rework`（worktree） |

> 手元の school-launcher の checkout（2026-10-26 時点は `feat/lw2-auto-assign-learning-path-trigger`。自動割当をコースの購入で動かす作業 = B7 らしい未コミットの変更がある）には触れない。

## 進捗

状態: 未着手 / 作業中 / 確認待ち / 回答待ち / 済み

| 区分 | 基準（`hanataba_dev`） | 1 機能仕様 | 2 テスト仕様 | 3 移行仕様 | 4 差分 | 5 実装 | 6 テスト |
|---|---|---|---|---|---|---|---|
| 01 基盤 | `584026af`（2026-10-24） | 済み（[functional-spec](01-foundation/functional-spec.md)） | 済み（[test-spec](01-foundation/test-spec.md)） | 済み（[migration-spec の 0 章](01-foundation/migration-spec.md#0-見直し2026-10-26-決定)） | 済み（[rework-gap](01-foundation/rework-gap.md)） | 済み（S1 は直さない） | 済み（[結果](01-foundation/test-spec.md#結果)。billing を除く） |
| 05 の一部（未実装の移行。[not-migrated-summary の 3](not-migrated-summary.md#3-移行ツールが未実装でまだ移していないもの)） | `584026af`（2026-10-24。2026-10-26 時点で最新） | 済み（[functional-spec](05-support/functional-spec.md)） | 済み（[test-spec](05-support/test-spec.md)） | 済み（[migration-spec の 0 章](05-support/migration-spec.md#0-見直し-未実装の移行2026-10-26-決定実装済み)） | 済み（[rework-gap](05-support/rework-gap.md)） | 済み | 済み（[結果](05-support/test-spec.md#結果)。billing を除く） |
| 02 コンテンツ | `584026af`（2026-10-24。2026-10-26 時点で最新） | 済み（[functional-spec](02-content/functional-spec.md)） | 済み（[test-spec](02-content/test-spec.md)） | 済み（[migration-spec の 0 章](02-content/migration-spec.md#0-見直し2026-10-26-決定)） | 済み（[rework-gap](02-content/rework-gap.md)） | 済み | 済み（[結果](02-content/test-spec.md#結果)。動画の URL・尺は NG のまま） |
| 03 受講 | `584026af`（2026-10-24。2026-10-26 時点で最新） | 済み（[functional-spec](03-enrollment/functional-spec.md)） | 済み（[test-spec](03-enrollment/test-spec.md)） | 済み（[migration-spec](03-enrollment/migration-spec.md) 0 章） | 済み（[rework-gap](03-enrollment/rework-gap.md)） | 済み | 済み（[結果](03-enrollment/test-spec.md#結果)。billing の分は 04 の確認で確かめた） |
| 04 課金 | `584026af`（2026-10-24。2026-10-26 時点で最新） | 済み（[functional-spec](04-billing/functional-spec.md)） | 済み（[test-spec](04-billing/test-spec.md)） | 済み（[migration-spec](04-billing/migration-spec.md) 0 章） | 済み（[rework-gap](04-billing/rework-gap.md)） | 済み | 済み（[結果](04-billing/test-spec.md#結果)） |
| 05 サポート（残り: LINE の紐付け・ライブラリ・運営メモ・フォロー・コミュニティの分類・利用料の集計） | `584026af`（2026-10-24。2026-10-26 時点で最新） | 済み（[functional-spec-remaining](05-support/functional-spec-remaining.md)） | 済み（[test-spec-remaining](05-support/test-spec-remaining.md)） | 済み（[migration-spec の 0R 章](05-support/migration-spec.md)） | 済み（[rework-gap-remaining](05-support/rework-gap-remaining.md)） | 済み | 済み（[結果](05-support/test-spec-remaining.md#結果)。資料のファイルの場所は L9 待ちで NG） |

## 決めたこと

| 日付 | 内容 |
|---|---|
| 2026-10-26 | テストは、データの確認（自動。新アプリの問い合わせと同じ条件で移行先を確かめる）＋ 主要な画面の E2E（移行した recademy のテナントに対して、このリポジトリに新しく書く） |
| 2026-10-26 | 基準は区分を始める時点の `origin/hanataba_dev`。確認用の DB を作るときだけ school-launcher を一時的に切り替え、すぐ戻す（この作業の中では毎回の相談なしでよい） |
| 2026-10-26 | 未実装の移行（クーポン・お知らせ・問い合わせ・自動メールの文面・掲示板・求人と面談など）も作る。career の DB に書くものは、その区分で取り決めを見直すかを相談する |
| 2026-10-26 | 暫定対応は、区分ごとに一覧と本番の対応案を出して決めてもらう。運営の回答が要るものは `open-questions.md` に載せる |
| 2026-10-26 | E2E は、確認用の DB を読む新アプリ（バックエンド :18080・フロント :13000）を別に一時的に立てて流す。動いている開発の環境には触れない |
| 2026-10-26 | E2E のログインは、確認用の DB の中だけでテスト用に選んだ会員のパスワードを入れ直す（環境変数で渡す。DB 名が `lw2_schema_check` でなければ止める） |
| 2026-10-26 | データの確認は `migrator/validation/spec_checks.py`（新規）に、テスト仕様のケース ID ごとに持ち、`verify` で流す |
| 2026-10-26 | 区分 01 の差分（rework-gap）で手順 5 に進む |
| 2026-10-26 | 区分 01 の手順 6: データの確認 27 項目・E2E 16 ケースとも通過。**基準のコミット `584026af` では billing を流せない**（B7 の migration `20261023075332` が別ブランチにしか無い）ので、billing を除いて確かめた |
| 2026-10-26 | 区分 01 を仕上げたら、未実装の移行（クーポン・お知らせ・自動メールの文面・問い合わせ・求人と面談・掲示板・ディスカッション・会員の就活の列。[not-migrated-summary の 3](not-migrated-summary.md#3-移行ツールが未実装でまだ移していないもの)）を、区分 05 の一部として先に 6 手順で作る。02〜04 の見直しはその後 |
| 2026-10-26 | 移行ツールから career の DB にも書く（「career には書かない」の取り決めを改める）。接続情報は環境変数で渡す |
| 2026-10-26 | 移していない・移せないもののうち、未実装（上）以外は、テストが通らないときに報告する |
| 2026-10-26 | school-launcher も直す: 移行に要る migration と、移したデータが動くためのアプリの修正。区分ごとの差分（手順 4）に載せ、確認をもらってから直す。アプリの仕様を変える判断が要るものは、その都度相談する |
| 2026-10-26 | school-launcher の作業ブランチは `feat/lw2-migration-rework`（`origin/hanataba_dev` の `584026af` から）。手元の checkout を切り替えないよう、worktree `../school-launcher-lw2-rework` に置く。追跡先は設定しない（誤って `hanataba_dev` に push しないため）。このリポジトリは `main` のまま |

