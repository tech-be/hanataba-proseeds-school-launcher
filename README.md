# school-launcher データ移行ツール

旧環境 **learningware-kiracari** から新環境 **school-launcher** へデータを移行するための CLI ツールです。

- 実装言語: Python
- 実行形態: CLI のみ（GUI は提供しません）

## 概要

本ツールは learningware-kiracari のデータを抽出し、school-launcher のデータモデルに変換して投入します。
1 テーブル分の「抽出 (extract) → 変換 (transform) → 投入 (load)」を **Step** とし、
Step を **フェーズ**（`foundation.4` のような `区分.番号`）にまとめて順に流します。

```
learningware-kiracari ──▶ Step（抽出 → 変換 → 投入）──▶ school-launcher
                              └ フェーズ単位でコミットし、失敗したらロールバックする
```

**中間ファイルは作りません。** 旧 DB から読んだ行をそのまま変換して新 DB に入れるため、
途中のファイルを持ち回ることによる取り違えが起きません。`--dry-run` を付けると、
投入だけを実行せずに件数と SQL を確認できます。

**値を作り替えません。** 新環境の NOT NULL / UNIQUE / 外部キーに当たる行は
`out/not-migrated.csv` に出したうえで**移さず**、直すのは別ツール（[`fixups`](#暫定対応fixups)）の仕事です。

## 動作要件

- Python 3.11 以上
- 旧環境（learningware-kiracari）のデータソースへの参照権限
- 新環境（school-launcher）のデータストアへの書き込み権限

## セットアップ

```bash
git clone <このリポジトリ>
cd hanataba-proseeds-school-launcher

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 設定

接続情報や認証情報は環境変数で渡します。`.env.example` をコピーして値を設定してください。

```bash
cp .env.example .env
```

| 環境変数 | 説明 |
| --- | --- |
| `SOURCE_DB_URL` | 旧環境 learningware-kiracari の接続先 |
| `TARGET_DB_URL` | 新環境 school-launcher の接続先 |
| `LW2_CRYPT_KEY` | 旧環境の秘密鍵（`application.ini` の `security.mcrypt.key`）。**パスワードの復号に使うため、無いと会員の移行が始まりません** |
| `LOG_LEVEL` | ログ出力レベル（既定: `INFO`） |

> 認証情報をリポジトリにコミットしないでください。`.env` は `.gitignore` の対象です。
> **実際の環境変数のほうが `.env` より優先**されるので、CI や本番では `export` で渡せます。

移行の決め事（対象テナント・ロールの対応表・ULID の名前空間）は `config.yaml` に書きます。
**接続情報は書きません。**

```bash
cp config.yaml.example config.yaml
```

暫定対応で決めた値（メールアドレスの割り当てなど）は `overrides.csv` に書きます。
**個人情報を含むのでコミットしません**（`.gitignore` 対象）。作り方は [暫定対応](#暫定対応fixups)を参照してください。

### ローカル DB での動作確認

`.env.example` の既定値は、**両環境の docker-compose のローカル DB** を指しています。

| | 接続先 | 由来 |
| --- | --- | --- |
| 移行元 | `mysql://lw2user:lw2pass@127.0.0.1:3306/lw2` | learningware-kiracari の `db` サービス（`kiracari_db`） |
| 移行先 | `mysql://learningware:learningware@127.0.0.1:3307/learningware` | school-launcher の `mysql` サービス（ホスト側 **3307**） |

**ポートが 3306 / 3307 で分かれている**ので、両方を同時に起動したままで確認できます。

```bash
# 旧環境（learningware-kiracari）
docker compose up -d db

# 新環境（school-launcher）— 移行前にローカルデータを消して seed を入れ直す
make reseed

# このリポジトリで
python -m migrator doctor    # 接続・対象テナント・追加スキーマの適用状況を見る
```

> **移行先にはデモ seed のテナント（`demo` など9件）が居るのが正常です。**
> 移行の判定は**テナントの総数ではなく、`slug = recademy` が1件あるか**で行います。

## 使い方

### サブコマンド

```bash
python -m migrator plan        # 実行計画を出す（DB 接続なし）
python -m migrator doctor      # 接続と前提を確認する（書き込みなし）
python -m migrator preflight   # 事前検査だけ通す
python -m migrator verify      # 投入後の検証だけ通す
python -m migrator run         # 移行を実行する
```

**抽出・変換・投入を別々に呼ぶことはできません。** 中間ファイルを持たない作りのため、
3つは `run` の中で1つの Step として実行されます。試すときは `run --dry-run` を使います。

### 主なオプション

| オプション | 説明 |
| --- | --- |
| `--dry-run` | 実際には書き込まず、実行される SQL と件数のみを表示します |
| `--phase <区分.番号>` | そのフェーズだけを流します（`--phase foundation.4` / `--phase foundation.1-3`）。`--dry-run` と併用できます |
| `--section <区分>` | その区分をまるごと流します（`--section foundation`） |
| `--skip-preflight` | 事前検査を飛ばします（非推奨） |
| `--config <パス>` | 設定ファイルを指定します（既定: `config.yaml`） |
| `--log-level <レベル>` | ログ出力レベルを上書きします |
| `--help` | ヘルプを表示します |

## ツールの構成

**フェーズで順序を管理し、1テーブル = 1 Step に分けている。**

| ディレクトリ | 責任範囲 |
| --- | --- |
| `migrator/core/` | 変換部品（ULID・日時・コード値・極性・文字列）。**DB を知らない**ので単体テストできる |
| `migrator/db/` | I/O とガードのみ。禁止列・テナント絞り込み・移行対象外テーブルを**実行前に**弾く |
| `migrator/steps/` | 1テーブル = 1 Step。`extract` → `transform` → `load` の3メソッドだけを持つ |
| `migrator/phases/` | Step の集合と実行順。フェーズ境界で検証し、失敗したらロールバックする |
| `migrator/validation/` | 事前検査（`preflight`）と事後検証（`postcheck`）。Step から独立 |

**フェーズの識別子は `区分.番号` の2階層。** 区分をまたぐ順序（基盤 → オンデマンド → …）と
区分の中の順序（テナント → 会員 → …）は別の軸なので、1つの通し番号にまとめない
（区分が増えたときに番号がずれるため）。

```
common.0       スキーマ確認      追加スキーマが入っているか
foundation.1   マスタ            user_roles / tenant_statuses / auth_methods / email_kinds の不足値
foundation.2   テナント          tenants の1行 → ここで tenant_id が決まる
foundation.3   テナント設定・定義 上限・プロフィール項目
foundation.4   会員              users → external_user_links
foundation.5   会員に紐づくもの   住所・プロフィール値・通知設定・LINE 紐付け
ondemand.*     未作成（移行仕様がまだ無い区分は、指定すると理由つきで止まる）
```

`python -m migrator plan` で一覧できる（DB 接続は不要）。

**フェーズ単位で dry-run できる。** 途中のフェーズから始めるときは、`tenant_id` を新環境から `slug` で引き（無ければ旧 `tenant` 行から決定論 ULID で組み立て）、前のフェーズを完了済みとして扱う。

```bash
python -m migrator run --dry-run --phase foundation.4     # 会員だけ試す
python -m migrator run --dry-run --phase foundation.1-3   # テナント〜定義系まで
python -m migrator run --dry-run --section foundation     # 基盤まるごと
```

> `--phase 4` のように区分を省く書き方は、**その番号を持つ区分が1つに決まるうちだけ**通る。
> 区分が増えて曖昧になったら、区分を書くよう促して止まる。

> 飛ばしたフェーズが**実際に投入済みかは確認しない**（確認は `verify` の仕事）。未投入のまま次を流すと FK 違反になるため、警告を出す。

### 動作確認の順序

```bash
python -m migrator doctor                              # 接続と前提（書き込みなし）
python -m migrator plan                                # 実行計画（DB 接続なし）
python -m migrator preflight                           # 事前検査
python -m migrator run --dry-run --section foundation  # 書き込まずに試す
```

### テスト

```bash
python -m unittest discover -s tests
```

**仕様で禁じたことが止まることをテストで固定している** — 平文列の抽出、テナント絞り込みの欠落、
純ログの移行、`platform_admin` の出力、対応表に無いコード値、通知フラグの極性。

## 移行対象

`既存機能と新システムの保有.docx.pdf` が定義する **8区分 / 95データ種**を分類軸として、旧環境の全342テーブルと新環境の全256テーブルを対応づけています。

| ドキュメント | 内容 |
| --- | --- |
| [移行ツール仕様書（共通）](docs/migration-spec.md) | **実装の入口。** 区分をまたぐ登録順と、全区分に共通する抽出・変換・投入の規則 |
| [docs/db/](docs/db/README.md) | **DB ドキュメント一式の入口。** 構成の規約と、区分ごとのセットへの索引 |
| [基盤のマイグレーション対象](docs/db/01-foundation/schema-additions.md) | 新環境に足す DDL 一覧（必須48件 / 計画4件）。当てる順序とロールバックの注意つき |
| [データ種別 旧⇔新テーブル対照表](docs/db/data-type-mapping.md) | 95データ種ごとの旧テーブル・新テーブル・◯X判定・ETL段 |
| [旧環境テーブル逆引き](docs/db/legacy-table-coverage.md) | lw2 全342テーブル → データ種（未分類の理由つき） |
| [新環境テーブル逆引き](docs/db/new-table-coverage.md) | school-launcher 全256テーブル → データ種（新規機能の切り分けつき） |
| [差分・要確認事項](docs/db/data-type-findings.md) | PDF との食い違い、資料間の矛盾、判断が要る点 |

DB ドキュメントは **1区分 = 1ディレクトリ**で、その中に「テーブルの内訳」(`breakdown.md`) と「突き合わせ」(`review.md`) をセットで置いている。**突き合わせの見出しは内訳の対応表の行と1対1。** 深刻度「高」は全区分で 106 件。

### 区分ごとのデータ種

| 区分 | データ種 | 新システムに受け皿あり | 無し |
| --- | ---: | ---: | ---: |
| 基盤 | 12 | 5 | 7 |
| オンデマンド | 28 | 17 | 11 |
| ライブ | 9 | 6 | 3 |
| 受講 | 6 | 3 | 3 |
| 課金 | 13 | 11 | 2 |
| 運営 | 14 | 7 | 7 |
| 就職支援 | 8 | 4 | 4 |
| 対象外 | 5 | 0 | 5 |
| **合計** | **95** | **53** | **42** |

「受け皿あり / 無し」は新環境の `docs/db` を根拠に判定し直した値です。PDF の値（◯50 / X45）との差分は [差分・要確認事項](docs/db/data-type-findings.md) にあります。

### 移行のスコープ

- 対象は **recademy の1テナントのみ**（旧 `tenant_id` は設定 `tenant.legacy_id`。本番 12 / ステージング 10）
- 旧342テーブルのうち **67件はどのデータ種にも該当しない**（純ログ・一時テーブル・共通マスタ・PDF の粒度から漏れた機能）
- 新256テーブルのうち **101件は旧に対応する機能が無い**新システム固有のもので、移行ツールの対象外

## 実行手順の推奨フロー

1. 移行先をリセットしてシードを入れ直す（`make reseed`）。**前の移行結果が混ざると件数の照合が意味を失う**
2. `doctor` → `preflight` で接続と前提を確認する
3. `run --dry-run --section foundation` で件数と変換結果を確認する
4. `out/not-migrated.csv` を見て、[暫定対応](#暫定対応fixups)で直す
5. 旧環境・新環境のバックアップを取得する
6. **フェーズごとに**投入する（`run --phase foundation.1` → `.2` → …）。区切る単位でコミットと検証が入る
7. `verify` で検証する

## 暫定対応（fixups）

移行ツールは値を作り替えないため、制約に当たった行は移らずに `out/not-migrated.csv` に出ます。
**直すのは別ツールの仕事**です（移行ツールに暫定対応を入れると、何が本物のデータか分からなくなるため）。

```bash
python -m fixups plan       # 何を直せばよいかを分類する（SQL / 運営判断 / 巻き添え）
python -m fixups sql        # 移行元を直す SQL を出す（**実行はしない**）
python -m fixups template   # 運営が値を決める雛形（overrides.csv）を出す
python -m fixups check      # 書いてもらった値を検査する
```

`--propose` を付けると、機械的に決まる値だけを雛形に埋めます（**提案であって決定ではない**ので、
中身を読んでから使ってください）。直したあと移行ツールを再実行すると、直った分が入ります。

| 直し方 | 何を直すか | 当てる先 |
| --- | --- | --- |
| SQL | 機械的に決まるもの（重複した `login_id` の一意化、親が存在しない行の削除） | 移行元 DB |
| 補正データ | 運営の判断が要るもの（メールアドレス、ロール、どの会員に LINE を残すか） | `overrides.csv` |

## ログと再実行

- 実行ログは標準出力に出ます（`--log-level` で切り替え）。ファイルには書きません。
- 処理は冪等です。決定論 ULID と業務キーの UNIQUE で二重登録を防ぐため、同じコマンドで再実行できます。

## ディレクトリ構成

```
.
├── migrator/            # 移行ツール本体
│   ├── core/            # 変換部品（DB を知らない）
│   ├── db/              # I/O とガード
│   ├── steps/           # 1テーブル = 1 Step
│   ├── phases/          # Step の集合と実行順
│   └── validation/      # 事前検査・事後検証・制約チェック
├── fixups/              # 暫定対応ツール（移行ツールとは別）
├── docs/                # 移行ドキュメント
├── tests/               # テスト
├── config.yaml          # 移行の決め事（.gitignore 対象）
├── overrides.csv        # 暫定対応で決めた値（.gitignore 対象）
└── out/                 # 実行結果の出力（.gitignore 対象）
```
