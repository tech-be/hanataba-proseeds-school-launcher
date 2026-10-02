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
python -m migrator verify      # 投入後の検証（移行元から作り直して移行先と照合する。書き込みなし）
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
foundation.1   マスター          マスタの不足値 → tenants の1行（ここで tenant_id が決まる）→ テナント設定・定義
foundation.2   ユーザ            users → external_user_links → 住所・プロフィール値・公開設定・通知設定・所属・タグ・講師の担当範囲
content.1〜4   コンテンツ        講座・ユニット・章・動画 / テスト・課題 / アンケート / ライブ・開催回
enrollment.1〜7 受講             受講権限 / 学習履歴 / テスト結果 / 課題提出 / アンケート回答 / ライブ予約 / 修了証
billing.1〜4   課金              チケット / 決済 / 帳票 / 自動割当
support.1〜8   サポート機能      LINE / クーポン・お知らせ・問い合わせ（未実装）/ ファイル / 就業支援 / コミュニティ / 利用料の集計
```

`python -m migrator plan` で一覧できる（DB 接続は不要）。

**フェーズ単位で dry-run できる。** 途中のフェーズから始めるときは、`tenant_id` を新環境から `slug` で引き（無ければ旧 `tenant` 行から決定論 ULID で組み立て）、前のフェーズを完了済みとして扱う。

```bash
python -m migrator run --dry-run --phase foundation.2     # 会員だけ試す
python -m migrator run --dry-run --phase foundation.1     # マスタ・テナント〜定義系まで
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
| [基盤のマイグレーション対象](docs/db/01-foundation/schema-additions.md) | 新環境に足す DDL 一覧（必須49件 / 計画4件）。当てる順序とロールバックの注意つき |
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
- **移行対象外を除き、削除済み（`del_chk = 1`）も含めてすべての行を移す**（2026-10-01 の方針）。
  削除済みは移し先の `deleted_at`（無ければ足した列）に削除した日時を入れる。旧が保存のたびに積んだ行
  （除外日・ライブを予約できる商品）は、旧の形のままの表（`*_history`）に全行入れる。
  **新のアプリはまだ足した `deleted_at` を読まない**ので、削除済みの行も生きた行として扱われる
  （例: 商品から外した講座も購入で付与される、削除済みのタグ・章が出る）

## 実行手順の推奨フロー

1. **実行前に移行先の DB を作り直す**（`make reseed`）。**前の移行結果が混ざると件数の照合が意味を失う。**
   また `run` は既にある行を更新しないので、移行ツールを直したあとに作り直さずに流すと、前の版の値が残る
2. `doctor` → `preflight` で接続と前提を確認する
3. `run --dry-run --section foundation` で件数と変換結果を確認する
4. `out/not-migrated.csv` を見て、[暫定対応](#暫定対応fixups)で直す
5. 旧環境・新環境のバックアップを取得する
6. **フェーズごとに**投入する（`run --phase foundation.1` → `.2` → …）。区切る単位でコミットと検証が入る
7. `verify` で検証する（投入と同じ `--section` / `--phase` を付ける）

## 投入後の照合（verify）

`run` の再実行は自然キーが既にある行を飛ばすだけで、**値までは見ません**。
古いツールで入れた行に誤りが残っていても、件数は合い、再実行も 0 行で終わります。
`verify` はそれを拾うために、**移行元から全 Step を作り直し（書き込みなし）、移行先の行と1行ずつ突き合わせます。**

```bash
python -m migrator verify --section foundation --section content --section enrollment
```

| 見るもの | 内容 |
| --- | --- |
| 行が無い | 変換結果にあるのに、移行先に自然キーが一致する行が無い |
| 値が違う | 自然キーは一致するが列の値が違う。**`id` も比べる**ので決定論 ULID の照合を兼ねる |
| 移行先にだけある | 対象テナントの行なのに、変換結果のどれにも当たらない（そのテーブルに書く Step をすべて流したときだけ数える） |
| パスワード | bcrypt はソルトが毎回変わるので、**旧パスワードを復号した平文と移行先のハッシュを `checkpw` で照らす**。平文は一覧にもログにも出さない |

- 差の一覧は `out/verify/differences.csv`。差が1件でもあれば終了コード 1
- 制約に当たって移さない行は照合の対象外（`run` と同じ判定）。一覧は `out/verify/not-migrated.csv` に出し、`run` の作業リストは上書きしない
- **実行した時刻で値が決まる列**（`live_lessons.scheduled_at` など）は `Step.volatile_columns` に書き、有無だけを見る
- 期限切れの判定（`enrollments.status`）も実行時刻に依存する。**`run` の直後に流す**こと。日を置くと、その間に期限を迎えた行が差に出る
- テナント・`platform_admin`・メール重複の事後検証も続けて通す

**照合は「移行先 = 移行ツールの変換結果」までしか言えない。** 変換の規則が間違っていれば、間違ったまま一致する。
そこで `verify` は、**旧 DB に直接 SQL を投げて独立に出した数字**とも突き合わせる（`migrator/validation/legacy_checks.py`）。
移行ツールの変換コードは使わない。旧の値の意味（入金日の式など）は旧アプリの実装から写してある。

- **基盤・コンテンツ・受講・課金の4区分**（ステージングで 104 項目。削除済みの行が移っていることも見る）
  - 基盤: 会員（漏れ・紛れ、名前・メール・ロール・生年月日・状態）、グループと所属、タグ（旧の属性）とその割当
  - コンテンツ: 講座（自テナント・共有）と受講日数、ユニットと種別、講座の章（旧の見出し）とユニットの所属、アンケートの定義、テスト・課題・設問の数、ライブと開催回
  - 受講: 受講権限と取り消し、学習状況と修了、受験と得点、提出と得点、アンケートの回答、予約の状態、修了証、講座ごとの修了証の発行方針
  - 課金: 支払い方法 × 状態ごとの件数と金額、会員ごとの支払い済み金額、決済の種類、領収書、商品、受講と決済の結びつき、規約の本文、チケット、自動割当のルールと付与するもの
- **サポート機能（5）は照合だけ**（旧 DB との突き合わせは無い）
- **行の漏れ:** 旧の対象の行が移行先に無いときは、同じ `verify` で「移さない」と一覧に出たものだけを許す。
  **一覧にも出ずに消えた行は NG**。抽出の段階で落とす行は `Step.drop()` で一覧に出す
- **意図して移さないもの**（0円の申込など、暫定の規則）は、移行先に入っていないことを確かめる
- NG が1項目でもあれば終了コード 1。区分を足すときは `CHECKS` に関数を足す

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
