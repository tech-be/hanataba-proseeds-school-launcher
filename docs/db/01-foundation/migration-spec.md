# 基盤 — 移行仕様

[基盤の内訳](breakdown.md) / [突き合わせ](review.md) と3点セット。**旧32件 / 新13件**（テナント・権限・会員・認証・ログイン履歴）を移すための手順。

- **根拠**: 旧⇔新の判断は [review.md](review.md)。**本書はそれを実装の手順に落としたもの**で、個別カラムの判断は突き合わせを正とする
- **全区分に共通する規則**（抽出の絞り込み / ULID / 日時 / 文字コード / 冪等性）は [移行ツール仕様書](../../migration-spec.md)。ここには**基盤固有のことだけ**を書く
- **[移行の原則](../00-template/review.md#移行の原則)** に従う。対象外区分のデータ以外はすべて移し、受け皿が無ければ追加し、元の構造を維持する

> **前提**: 新環境には **migration のシード値しか入っていない。** テナント行も会員も無いので、**`tenants` の1行を作るところが移行全体の起点**になる。この区分が終わるまで、他の区分は1行も入らない。

---

## 1. 前提

### 1-1. 運営への確認事項

**この区分の分も含めて [open-questions.md](../open-questions.md) に1枚でまとめてある。**
同じ話を2か所に置かない。

### 1-2. 制約による不整合

**[constraint-violations.md](../constraint-violations.md) にまとめてある。**
NOT NULL / UNIQUE / CHECK に当たるものと、参照先が物理削除されているものを分けて持つ。

### 1-3. 決定済み（再確認だけ）

**内容ごとにまとめてある。** 同じ決定を2か所に書かない。

**移す / 移さないの範囲**

| 事項 | 決定 |
|---|---|
| LINE 公式アカウント | **継続する。** `user.line_id` → `line_links` を移行対象にする |
| プロフィール画像 | **データは移行しない。** `avatar_url` の列は使うが空で始め、会員が登録し直す |
| プロフィール項目 | **非表示のものも含めて全項目を移す**（固定34・自由記述15）。`show_flag` などの制御はそのまま移し、**新環境の画面に出ないことは移行の問題としない**。ステージング実測では非表示7項目に値は0件だったが、あれば値も移す |
| `site` の運用値 | **`tenants.settings` に移す**（A3）。`service`（名称・説明・提供期間・URL・`application_path`）と `features`（`lw_type` / テスト分析 / ランキング / 日次メール）。`linkpreview_api_key` は `tenant_secrets` へ。**新環境に対応する機能が無くても移す** — 参照されないことは移行しない理由にならない |
| 純ログ | **移行しない。** `user_login_log` / `user_login_log_monthly` / `twostepverification_log` の3件。cutover 後の認証から記録を始める |
| グループ階層 | **`group.parent_group_id` が正本。** `group_structure` は `GroupModel::makeGroupStructure()` が作り直す閉包テーブルなので移行しない（[対象外 B](#34-移行の対象外)）。`tenant_groups` は `parent_id` と `depth` で持つ |
| SNS ログインの認証情報 | **移行する。** 旧 `sns_setting` の6列を `tenant_secrets` へ（種別は `facebook_client_id` など6種を追加。A7）。**新環境でもそのまま使えるため、移行できない理由が無い**（[移行の原則](../00-template/review.md#移行の原則)の1）。**移行後、SNS ログインを動かすには SNS 側の管理画面でコールバック URL を新環境のものに修正する作業が要る** — データの移行だけでは動作しない（移行の可否には影響しない） |
| 平文の認証情報 | **抽出クエリで SELECT しない。** `migrator/db/guards.py` の `FORBIDDEN_COLUMNS` が実行前に検査して止める（テスト済み）。対象は [3.4 の A](#34-移行の対象外)の3か所（lw2 自身の DB 接続情報、入力パスワードの平文、失効済みの認証コード）。**承認を取る項目ではなく、ツールの既定動作。** ただし **`user.password` と `sns_setting` の6列は読む** — どちらも移行対象のため（`user.password` は 3DES 復号 → bcrypt。鍵の受け渡しは [確認事項](../open-questions.md)） |

**データの持ち方（畳まない・元の粒度を保つ）**

| 事項 | 決定 |
|---|---|
| 氏名 | **姓 / 名を分けたまま移す**（`name_last` / `name_first`）。`name` は分割列から生成する |
| 誕生日 | **`birth_year` / `birth_month` / `birth_day` の3列で管理する。** `birthday` date 1列には畳まない |
| 固定電話と携帯電話 | **別の列で持つ**（`phone` / `mobile_phone`）。1列に畳まない |
| 住所 | **郵便番号 / 都道府県 / 市区町村 / 番地・建物名の4項目 × 2組**で移す |
| 国籍・海外住所 | **`user_addresses` の `kind='foreign'` で移す**（A12）。`nationality` / `country` は**コードなので `country_master` で国名に展開**する（`AR` → アルゼンチン）。選択肢に無い値は `*_another` の自由入力をそのまま使う |
| パスワード | **3DES 復号 → bcrypt 再ハッシュを移行ツールで行う。** 新環境と同じ `$2a$` / コスト10。**会員にパスワード再設定を求めない。** 旧の秘密鍵は**環境変数 `LW2_CRYPT_KEY`**（設定ファイルに書かない）。平文はログにも例外にも出さない。復号できないものは**空で入れず、件数と会員 ID を警告に出す** |
| ロールの対応表 | **実データで確定。** 1=`system_admin` / 2=`tenant_admin` / 3=`facility_manager`（削除済み）/ 4=`company_manager` / 5=`instructor` / 6=`group_manager` / 7=`learner` / 8=`supporter`（削除済み）。**表示名は `translate_master` から、並び順は `role_index` から**（`role_id` と食い違う） |
| 追加ロールの権限 | **移行としては問題なし。** 移したロール文字列（`system_admin` 17名 / `company_manager` 56名 / `group_manager` 20名）に新環境のコードが対応していないことは**把握済み**。権限をどう実装するかは移行とは別の判断で、[追加一覧の「変更が必要な機能」](review.md#新環境に追加するテーブルカラム)に置く |
| プロフィール項目の分類 | **`profile_cate` を `tenant_profile_item_categories` に移す**（項目より先）。`profile_cate_id=0` は「分類なし」で NULL |
| 会員単位の言語 | **`users.language_code` を追加して移す**（A22 / M10）。旧 `user_nationality_info.language_code`。**列を足しただけでは効かない** — 言語の判定を「cookie → 会員の既定 → テナントの既定 → `defaultLocale`」に直す機能修正が要る |
| 会員列のテナント既定値 | **`tenant_field_defaults` を新設して移す**（A23 / M10）。旧 `user_item_default`。`tenant_profile_items.default_value`（プロフィール項目の既定値）とは**別物なので畳まない** |

**制約に当たる行の扱い**（[共通仕様 3.5.1](../../migration-spec.md#351-not-null--unique--外部キーに当たる行)）

| 事項 | 決定 |
|---|---|
| 当たった行の処理 | **移さず `out/not-migrated.csv` に出し、暫定対応で直してから再実行する。** **どこが当たるか**は [確認事項](../open-questions.md)の確認事項に挙げる |
| 投入前の検査 | **NOT NULL / UNIQUE / 外部キーを、変換した直後に移行先のスキーマと突き合わせる。** dry-run では INSERT が実行されないので、ここで見ないと違反が本番まで見つからない |
| 暫定対応の置き場所 | **移行ツールには入れない。** 別ツール `fixups`（`plan` / `sql` / `template` / `check`）が、移行元を直す SQL と、運営が値を決める補正データ（`overrides.csv`）を作る。移行ツールは補正データを**読むだけ**で、値は作らない |
| メールアドレス | **旧の値をそのまま入れる。** 欠損・重複した会員は移らない。**合成アドレスはツールで作らない**（作ると何が本物か分からなくなる）。割り当ては暫定対応で決める |
| `role_id` が NULL の会員 | **既定ロールに倒さない**（権限が静かに変わる）。その会員は移らず、[3.4 の B](#34-移行の対象外)に理由つきで対象外として記録する。ステージングの該当は `user_id=911` の1名（受講0件・未ログインの重複アカウント）。**本番ダンプでは該当者を取り直す** |
| 同じ LINE アカウントを持つ会員 | **どの会員にも紐付けない**（`(tenant_id, line_user_id)` が UNIQUE）。一覧に出し、暫定対応で1人に決めてから再実行する |
| 親の無いプロフィールラベル | **落とす**（対応する `profile_item` が無く、`item_id` の FK 先を作れない）。落とした内容を警告に出す |
| 親が存在しない子データ | **移さず一覧に出す。** 移行元から消すかは暫定対応の判断で、消しても消さなくても移行結果は同じ |

**実行の段取り**

| 事項 | 決定 |
|---|---|
| 新環境へのスキーマ追加（A1〜A23） | **移行直前に実施する。** フェーズ0（第2章）。DDL と適用順は [マイグレーション対象](schema-additions.md) |
| `tenant_statuses` | **`deleted` を追加する**（recademy 自体は `active`） |
| マスタとテナントの順序 | **マスタが先**（`foundation.1`）。FK の参照先をそろえてからテナントの行を作る |
| `tenants` の1行作成 | **移行手順に含める**（`foundation.2`）。採番した `id` を設定値として配る |
| 動作確認時の移行先 | **移行前にローカルデータを削除し seed を入れ直す**（`make reseed`）。判定は `slug='recademy'` が1件かで行い、**テナントの総数では判断しない** |
| 移行元に無いテーブル | **設定 `source.absent_tables` に書いたときだけ**読み飛ばす。書かなければ事前検査で停止する。**書いた分のデータは移らない**ので、本番では空にして実在を確かめる |

### 1-4. 本番ダンプ受領後に確認すること

同梱の `lw2.sql`（2019-08-28 時点）で当たりは付けてあるが、**本番の最新値で必ず取り直す**。

| 確認 | 効く先 |
|---|---|
| 移行対象テナントの `tenant_name` が NULL / 空でないか | `tenants.name` は NOT NULL |
| **`tenant_code` の文字種・桁・重複**（73件分）。大文字 / アンダースコア / 3文字以下 / 同じ値が無いか | slug をそのまま使えるかの判断（[1-1 #2](../open-questions.md)） |
| `del_chk` / `language_code` の実値 | `status`、多言語判断 |
| `role_master` 8行が検証用と同じか（`FACILITY_MANAGER` / `SUPPORTER` が削除済みか） | ロール対応表。**ローカルでは確定済み** |
| **会員のロール分布**（本番の実数） | 追加する4ロールに該当者がいるか |
| `profile_item` の `show_chk=1` の項目 | 移すプロフィール項目 |
| `tel` / `mobile_tel` に32文字超があるか | `varchar(32)` を広げるかの判断 |
| `line_id` が `U` 始まり33文字か | `line_links` に入れてよいか |
| `mail_add` の欠損・重複件数 | UNIQUE 違反の実数 |
| 文字コード（cp932 混入） | 抽出時の検証 |

> 残りは [docs/db/README.md](../README.md) の「実データが無いと判断できないこと」を参照。

### 1-5. ステージングダンプでの実測（2026-09-22 実施）

**ここの数値は本番ではない。** `lw2_stg_kiracari_20260918_1946.sql.gz`（2026-09-18 取得、MySQL 5.6.35、335テーブル）を
旧環境のローカル DB に入れ替え、新環境を `make reseed` で初期化したうえで **dry-run（書き込みなし）**を流した結果。
**本番の見積もりにこの数値を使わない。** 1-3 の確認は本番ダンプで取り直す。

**テナント構成が本番と違う**

| 旧 `tenant_id` | `tenant_code` | `tenant_name` |
|---:|---|---|
| 0 | master | （管理用） |
| **10** | **career** | **ReCADemy(リカデミー)** ← 移行対象 |
| 11 | career2 | — |
| 12 | solastudy | ソラスタディ |

**本番では recademy が `tenant_id=12`** とされている。設定 (`tenant.legacy_id`) を環境ごとに変えること。
`tenant_code='career'` は slug `recademy` と一致しないため警告が出る（**出るのが正しい動作**）。

**1-3 の項目をステージング値で取り直したもの**

| 確認 | ステージング実測 |
|---|---|
| `tenant_name` の NULL / 空 | 値あり（`ReCADemy(リカデミー)`） |
| `role_master` 8行 | 検証用と同じ。`FACILITY_MANAGER` / `SUPPORTER` は削除済み |
| 会員のロール分布 | `system_admin` 17 / `tenant_admin` 78 / `company_manager` 56 / `instructor` 18 / `group_manager` 20 / `learner` 2,965 / **NULL 1**（計 3,155） |
| `profile_item` の `show_chk=1` | 固定項目 34/34、自由記述 8/15 |
| `tel` / `mobile_tel` の32文字超 | 0件（列を広げる必要なし） |
| `mail_add` の欠損・重複 | **欠損 2,698名 / 重複 389名**（この 3,088名は移行しない。会員の 98%） |
| 文字コード | 化けなし |
| `user_login_chk_log` | **テーブルが存在しない**（`20230821_cdss.sql` に DDL はあるが未適用）。ログのため[対象外](#34-移行の対象外) |

**dry-run の件数（`--section foundation`、合計 35,617行）**

| フェーズ | Step | 抽出 | 投入予定 |
|---|---|---:|---:|
| foundation.1 | master.user_roles | 8 | 1 |
| | master.tenant_statuses.deleted / auth_methods / email_kinds | 10 | 0 |
| foundation.2 | tenant | 1 | 1 |
| foundation.3 | config.tenant_limits | 1 | 1 |
| | config.profile_item_categories | 5 | 5 |
| | config.profile_items | 49 | 49 |
| | config.profile_item_labels | 50 | **49**（親の無いラベル1件を除く） |
| | config.groups | 28 | 28 |
| | config.attributes | 7 | 7 |
| | config.attribute_required_courses | 5 | 5 |
| | config.sso / config.login_windows | 0 | 0 |
| foundation.4 | users | 3,155 | 3,155 |
| | external_user_links | 3,155 | 3,155 |
| foundation.5 | user_addresses | 3,155 | **218** |
| | user_profile_values | 3,155 | **27** |
| | user_field_visibility | 3,155 | 18,507 |
| | notification_optouts | 3,155 | 7,063 |
| | line_links | 4 | **1**（同じ LINE を4名が共有） |
| | tenant_group_members | 98 | 98 |
| | user_attribute_values | 3,127 | 3,127（うち36件は会員が無い → 1-1 #9） |
| | instructor_assignments | 121 | 121 |

**旧 DB と照合済み**（抽出件数と投入件数が食い違うものは、すべて旧の値どおり）

- `user_addresses` 218 = 住所1が入っている 211名 ＋ 住所2が入っている 7名
- `user_profile_values` 27 = `user_profile1`〜`20` のうち空でない値の数
- `user_field_visibility` 18,507 = `*_open_chk` 6列の NOT NULL 数

**dry-run で判明して対処したもの**

| 事象 | 実測 | 対処 |
|---|---|---|
| `user.birth_date` にゼロ日付 (`0000-00-00`) | 3件 | **NULL として移行。** ドライバが日時に直せず文字列で返すため、読み出し時にまとめて倒し、件数を警告に出す |
| `pref_id` / `pref_id2` が `0` | 465件 / 569件 | **未選択として NULL。** `pref_master` は 1 始まりで `0` は存在しない。うち5件は郵便番号・市区町村が入っているのに都道府県が `0`（そのまま移す） |
| 都道府県の対応表が3件しかなかった | — | **`pref_master` から引く**（48件。`description` が名称、`99=海外`）。設定に書けばそちらが優先 |
| `role_id` が NULL | 1名 | **移行しない**（`users.role` は NOT NULL）。ロールを決めてから再実行する（[3.4 の B](#34-移行の対象外)） |
| `user_login_chk_log` が無い | — | **ログなので移行対象外に変更**し、受け皿（A17 `user_login_periods`）も取り消した |

**実投入の予行（INSERT してロールバック）で判明したもの**

dry-run は INSERT を実行しないため、制約違反は出ない。実際に書き込んで巻き戻す予行で、
**7件すべてが投入時に落ちる**ことが分かった。1〜5はツールで対処済み、6・7は判断待ち。

| 事象 | 実測 | 対処 |
|---|---|---|
| `tenant_profile_items.category_id` の参照先が無い | 49件 | **`profile_cate` を移す Step を追加**（項目より先）。`0` は NULL |
| 親の無いプロフィールラベル | 1件（`item_type=0 / item_no=18` 日記の公開設定） | 落として警告に出す |
| `external_user_links.linked_at` が INSERT の列に無い（NOT NULL） | 3,155件 | 会員の `regist_date` を入れる |
| `line_links.linked_at` が常に NULL | 全件 | `regist_date` を抽出列に加えていなかった（バグ）。修正 |
| 同じ LINE アカウントを4名が共有 | 1組4名（3名は削除済み） | **4名とも移行しない。** 1人に決めてから再実行する |
| `login_id` の重複 | 8組21名 | **共通仕様で処理**（1-1 #5） |
| 会員が存在しない属性割当 | 36件 | **共通仕様で処理**。暫定対応で移行元から削除した（1-1 #8） |

**dry-run は 2026-09-22 に最後まで通っている**（`run --dry-run --section foundation`、事前検査9件すべて OK、
`foundation.1`〜`5` 完走、終了コード0）。止まらずに完走するが、**投入できるのは 795 行**で、
残りは暫定対応待ち。

**制約に当たって移さない行**（ステージング実測。`out/not-migrated.csv` の内訳）

移行ツールは暫定対応を持たないため、**メールが決まらないと会員が移らず、紐づく行もすべて移らない**。

| Step | 移さない | 理由 |
|---|---:|---|
| users | **3,088 / 3,155** | `email` が NULL 2,698 ／ `email` の重複 389 ／ `role` が NULL 1 |
| external_user_links | 3,088 | 会員が移らないため |
| user_field_visibility | 18,144 | 同上 |
| notification_optouts | 6,975 | 同上 |
| user_attribute_values | 3,081 | 会員が移らない 3,045 ＋ **元から会員が存在しない 36**（1-1 #8） |
| user_addresses | 208 | 会員が移らないため |
| tenant_group_members | 98 | 同上 |
| instructor_assignments | 121 | 同上 |
| line_links | 4 | 同じ LINE アカウントを4名が共有（1-2） |
| user_profile_values | 19 | 会員が移らないため |
| **合計** | **34,826 行** | 投入できるのは 795 行 |

> **`login_id` の重複21名（1-1 #5）は、この一覧に `login_id` の理由では出ない。**
> 全員がメールの側で先に外れているため。メールの暫定対応を終えると `login_id` の重複が現れる。

**暫定対応を当てたあと**（2026-09-22。`fixups` で直してから再実行した結果）

| | 投入 | 移行しない |
|---|---:|---:|
| 暫定対応の前 | 795 | 34,826 |
| **あと** | **35,572** | **10** |

| 当てたもの | 内容 |
|---|---|
| SQL（移行元 DB） | 会員が存在しない `user_attribute` 36件を削除 ／ `login_id` の重複12件に `#<user_id>` を付与（各組の最小 `user_id` はそのまま） |
| 補正データ（`overrides.csv`） | メール欠損 2,698名・重複 342名に合成アドレス（`ext-<user_id>@lw2.invalid`。ブリッジと同じ形式）／ LINE を共有する4名のうち3名の `line_id` を `NULL` |

**実投入の予行（INSERT → ロールバック）も完走**し、35,572行が実際に INSERT できることを確認した
（移行先はシード状態のまま）。

残る 10 行は**すべて `user_id=911`**（`zentai001` の重複アカウント）の分。ロールが決まっていないため移らない。

**実投入の結果**（2026-09-22。ステージングのデータを新環境のローカル DB へ）

`foundation.1` から `5` までフェーズごとに区切って投入し、`verify` まで通した。**合計 35,572 行。**

| 移行先テーブル | 件数 |
|---|---:|
| `users` / `external_user_links` | 各 3,154 |
| `user_field_visibility` | 18,502 |
| `notification_optouts` | 7,061 |
| `user_attribute_values` | 3,091 |
| `user_addresses` | 217 |
| `instructor_assignments` | 121 |
| `tenant_group_members` | 98 |
| `tenant_profile_items` | 49 ／ `tenant_groups` 28 ／ `line_links` 1 |

- `tenants.id` = `01BJWWJPR0A1WS56QQMF0NZ2KK`（slug `recademy`）
- ロール分布: `learner` 2,965 ／ `tenant_admin` 78 ／ `company_manager` 56 ／ `group_manager` 20 ／ `instructor` 18 ／ `system_admin` 17
- 状態: `active` 2,651 ／ `deleted` 503
- **`platform_admin` 0件**、**パスワードが空の会員 0件**、**`$2a$` 以外のハッシュ 0件**、**他テナントへの混入 0件**
- 旧パスワードで新しい bcrypt ハッシュが通ることを5件抽出して確認
- 移行しなかったのは `user_id=911` の分 10 行のみ（[3.4 の B](#34-移行の対象外)）

> **投入中に直したもの。** ①事前検査「移行先の状態」が、フェーズを分けて流す2回目以降で
> 「テナントがすでにある」として止めていた → **テナントを作るフェーズを含むかで判定を変えた。**
> ②`verify` が `tenant_id` を引き当てていなかった → 移行先から `slug` で引くようにした。

**パスワード**（ステージングの実測。平文は記録しない）

| 項目 | 実測 |
|---|---|
| 3DES 復号に成功 | 3,155件中 **3,154件** |
| 旧が空 | 1件（ログインできない状態で入る） |
| 復号できず / 72バイト超 | 0件 |
| 再ハッシュにかかる時間 | 約2.2分（bcrypt コスト10 × 3,155件） |
| 照合の確認 | 旧パスワードで新しい `$2a$` ハッシュが通ることを確認済み |


---

## 2. データ登録順

新環境は**実 FK を持つ**ため順序が強制される。**前のフェーズが終わるまで次に進まない。**

```
フェーズ0  新環境のスキーマ追加（A1〜A21 の migration）※ 移行直前に実施する
              ↓  ※ 追加が入る前に L1 以降を流すと、受け皿の無い列が落ちる
フェーズ1  L0: マスタの追加値 ※ FK の参照先をそろえる
              ├ user_roles に system_admin / company_manager / group_manager / supporter
              ├ tenant_statuses に deleted
              ├ auth_methods に saml / facebook / twitter / instagram / totp
              ├ email_kinds に announcement / scout / footprint / bbs_comment
              └ tenant_secret_kinds に外部 API キーの種別
              ↓
フェーズ2  L0: tenants の1行（recademy）※ 移行手順に含める。手作業で先に作らない
              ↓  ここで採番した tenants.id を設定値として配る
フェーズ3  L1: テナント設定・定義系（会員より先に入れる）
              ├ tenant_limits / tenant_sso_configs / tenant_login_windows
              ├ tenant_profile_item_categories → tenant_profile_items → *_labels
              ├ tenant_groups → tenant_group_members は後（会員の後）
              └ tenant_attributes / attribute_required_courses
              ↓
フェーズ4  L1: 会員本体
              users → external_user_links
              ↓  ※ 既存ブリッジ（external_user_import_service）が正本。cutover 前夜にフル同期
フェーズ5  L1: 会員に紐づくもの（users の行が揃ってから）
              ├ user_addresses / user_profile_values / user_field_visibility
              ├ notification_optouts（極性を反転）
              ├ tenant_group_members / user_attribute_values
              ├ instructor_assignments
              └ line_links
```

> **`login_history` は入れない。** 純ログのため移行せず、**cutover 後の認証から記録を始める**。

**この区分が終わるまで、他の区分は1行も入らない。** 区分をまたぐ順序は [移行ツール仕様書](../../migration-spec.md) を参照。

**順序の根拠**

- **マスタが先。** `user_roles` / `tenant_statuses` / `auth_methods` / `email_kinds` は
  いずれも **`tenant_id` を持たないグローバルマスタ**で、テナントを参照しない。
  **FK の参照先をすべてそろえてから、それを使う行を作る**という順序にそろえてある
  （`tenants.status` → `tenant_statuses`、`users.role` → `user_roles`、
  `notification_optouts.kind` → `email_kinds` はいずれも実 FK）

- `tenants` が無いと `tenant_id` を持つ全テーブルが FK 違反になる
- `users` が無いと会員に紐づくテーブルが入らない。`courses.instructor_id` は NOT NULL なので、**講師の users 行はコースより先**
- マスタ（`*_statuses` / `*_kinds` / `*_methods` / `user_roles`）は FK の参照先なので、値を使う行より先
- `tenant_group_members` は `tenant_groups`（フェーズ3）と `users`（フェーズ4）の両方に依存するのでフェーズ5

---

## 2-2. 実行手順

**フェーズの指定は `区分.番号`**（`foundation.4` など）。区分をまたぐ順序と区分の中の順序を混ぜないための形。**フェーズは区切って流す。** 区切る単位でコミットと検証が入るので、失敗したときのやり直しが小さくなる。

**前提**（どちらも欠けると事前検査で止まる）

- **移行先はリセット＋シード投入の直後**であること（`make reseed` が `make seed` まで通っていること）。
  途中で止まった状態は「テナント0件」になり、件数の照合が意味を失う
- **環境変数 `LW2_CRYPT_KEY`** に旧環境の `security.mcrypt.key` が入っていること。
  無いとパスワードを復号できず、**会員の移行は始まらない**

```bash
# 0. 追加スキーマを当てる → 移行先を初期化する（school-launcher のリポジトリで）
#    DDL 一覧: docs/db/01-foundation/schema-additions.md
#    ローカルデータを消して seed を入れ直す。前回の移行結果が混ざらない
#    ※ btoc-backend / career-backend / skill-passport が起動していないと seed は流れない
make reseed

#    **8080 が埋まっていて btoc-backend が起動できないとき**（lw2 の kiracari_app が握る）。
#    `docker compose run` はポートを公開しないので、止めずに seed だけ流せる
#    （`--profile passport` は skill-passport を起動するのに要る）
docker compose run --rm --no-deps btoc-backend go run ./cmd/seed
docker compose exec -T career-backend go run ./cmd/seed
docker compose --profile passport exec -T skill-passport go run ./cmd/seed

# 1. 接続と前提を確認する / 実行計画を見る
python -m migrator doctor
python -m migrator plan

# 2. 追加スキーマが入っているかを確認する
python -m migrator run --phase common.0

# 3. 事前検査（3.1 の事前検査）
python -m migrator preflight

# 4. dry-run。**フェーズ単位で試せる**
python -m migrator run --dry-run --phase foundation.1      # マスタだけ
python -m migrator run --dry-run --phase foundation.2      # テナントだけ
python -m migrator run --dry-run --phase foundation.1-3    # 定義系まで
python -m migrator run --dry-run --section foundation      # 基盤まるごと

# 5. 本番投入。フェーズごとに結果を見てから次へ
python -m migrator run --phase foundation.1
python -m migrator run --phase foundation.2
python -m migrator run --phase foundation.3
python -m migrator run --phase foundation.4
python -m migrator run --phase foundation.5

# 6. 検証（3.5）
python -m migrator verify
```

### 暫定対応（移行ツールの外）

制約に当たった行は移らず `out/not-migrated.csv` に出る。**直すのは移行ツールではなく、
別の暫定対応ツール**（`fixups/`）。移行ツールは値を作らないので、ここを通さないと
何度流しても同じ行が落ちる。

```bash
# 1. 何を直せばよいかを分類する（SQL で直せるもの / 運営判断 / 巻き添え）
python -m fixups plan

# 2. 機械的に直せるものは SQL にする。**実行はしない**ので中身を読んでから当てる
python -m fixups sql                      # → out/fixups.sql
mysql -ulw2user -p lw2 < out/fixups.sql

# 3. 運営判断が要るものは雛形を出し、value 列を埋めてもらう
python -m fixups template                 # → overrides.csv（value が空の雛形）
python -m fixups check                    # 埋めた値を検査（重複・書き間違い）

# 4. 移行ツールを再実行すると、直った分が入る
python -m migrator run --dry-run --section foundation
```

| 直し方 | 何を直すか | 当てる先 |
|---|---|---|
| **SQL** | 機械的に決まるもの（`login_id` の一意化、会員が存在しない行の削除） | 移行元 DB |
| **補正データ** | 運営の判断が要るもの（メールアドレス、ロール、どの会員に LINE を残すか） | `overrides.csv` |

`overrides.csv` は `table,key,column,value,memo` の5列で、**移行元の行を読んだ直後に
当てる**（`migrator/overrides.py`）。`value` が空の行は適用しないので、雛形のまま流しても
事故らない。値を消したいときだけ `NULL` と書く。**個人情報を含むのでリポジトリに入れない。**

> **巻き添えは直さない。** 会員が1人移らないと、その会員の住所・通知設定・所属も移らない。
> `fixups plan` はそれを「対応不要」として分けて出す。**大本を直せば消える。**

> **dry-run は `--section` で流す。** 単独フェーズの dry-run は、前のフェーズが
> 実際には投入されていないため、外部キーの参照先が無く**全行が「移行しない」になる**。
> 単独フェーズが意味を持つのは実投入のとき（前のフェーズが入っている状態）。
>
> **`foundation.2` の直後に `tenants.id` を控えて設定値として配る。** 他のツールが同じ値を読む必要がある。
>
> **途中のフェーズから流すとき**、ツールは `tenant_id` を新環境から `slug` で引く（無ければ旧 `tenant` 行から
> 決定論 ULID で組み立てる）。ただし**飛ばしたフェーズが投入済みかは確認しない**ので、
> 未投入のまま次を流すと FK 違反になる。警告が出たら意図どおりか確かめること。

---

## 3. データ移行仕様

**カラム単位の仕様は [review.md](review.md) が正。** 旧カラム1件ごとに行き先・変換規則・注意が書いてある。ここには**複数テーブルに効くもの**と、**取り違えると致命的なもの**だけを置く。

| 内容 | 場所 |
|---|---|
| `tenants` の1行の作り方と投入前後の確認 | [移行時の注意事項](review.md#移行時の注意事項) |
| ロールの8値対応 | [ロール対応表](review.md#ロール対応表) |
| `user` 90列すべての行き先 | [全列の行き先](review.md#全列の行き先) |
| プロフィール項目の構造（定義 / ラベル / 値の3分割） | [M4](review.md#m4-会員項目状態の定義) |
| 新環境に追加するテーブル・カラムと、変更が必要な機能 | [A1〜A21](review.md#新環境に追加するテーブルカラム) |

### 3.1 抽出（extract）

**基盤固有の絞り込み**

- `tenant` は設定 `tenant.legacy_id` の1行だけ（本番 12 / ステージング 10）。`user` 以下の会員テーブルも同じ条件で絞る
- `role_master` / `profile_cate` は **`tenant_id` を持たない全テナント共通のマスタ**。テナントで絞らず全行読み、移すときに recademy 用として扱う
- 削除済み会員（`del_chk=1`）も**移す**。`users.status='deleted'` で表現する

**SELECT してはいけない列**

| テーブル | 列 | 理由 |
|---|---|---|
| `site` | `db_server` / `user_id` / `password` / `database` | DB 接続情報の平文 |
| `user_login_log` | `input_password` | 入力パスワードの平文（**そもそも純ログなので抽出しない**） |
| `twostepverification_log` | `input_code` / `correct_code` | 認証コードの平文 |

> **抽出クエリのレビュー項目にする。** 「移さない」ではなく「読み出さない」。

**事前検査**

| 検査 | 対象 | 判断 |
|---|---|---|
| NULL / 空 | `tenant.tenant_name` | NOT NULL なので1件でもあれば投入前に値を決める |
| 値の照合 | `tenant.tenant_code` | `recademy` と一致するか |
| 欠損・重複 | `user.mail_add` | ステージング実測で欠損 2,698名・重複 389名。**この会員は移行しない**（一覧に出る） |
| 桁溢れ | `user.tel` / `mobile_tel`（32文字超） | 超過があれば列を `varchar(50)` に広げる |
| 形式 | `user.line_id`（`U` 始まり33文字か） | 外れたものは `line_links` に入れず一覧を渡す |
| コード値の網羅 | `user.role_id` / `pref_id` / `sex_type` / `blood_type` | 対応表に無い値が無いこと |
| 復号 | `user.password` を200件試す | 鍵が違っても例外にならず**意味のない文字列**が返る。半数以上失敗なら鍵違いとして止める |
| 一意性 | `user.login_id` | 新環境の UNIQUE に当たる重複を**再ハッシュ（数分）の前に**出す |
| 初期状態 | 移行先の `tenants` | 対象テナントが未登録で、シードが入っていること。**前の移行の残りが混ざると件数の照合が意味を失う** |
| テーブルの実在 | Step が読む旧テーブル全件 | lw2 は個別 SQL でテーブルを足すことがあり、環境で構成が揃わない。**読みに行って落ちる前に、まとめて名前を出す** |

### 3.2 変換（transform）

| 変換 | 規則 |
|---|---|
| `tenant.tenant_id` → `tenants.id` | **L0 で採番した1値を設定値として使う。** 再計算しない |
| `tenant.tenant_code` → `tenants.slug` | `recademy` を入れる（既存ツールが引くキー） |
| `tenant.del_chk` → `tenants.status` | `active` を**明示**して入れる（列の既定値は `trial`） |
| `user.role_id` → `users.role` | [ロール対応表](review.md#ロール対応表)で8値を1対1。**`platform_admin` は出力し得ないことをテストで固定** |
| `role_master.role_name` → `user_roles.code` | 小文字化（`COMPANY_MANAGER` → `company_manager`）。**表示名は `translate_master` の ja から `name_ja` へ** |
| `role_master.role_index` → `sort_order` | **`role_id` とは別の値。** 定数ではなく実データを正とする |
| `user.name_sei` / `name_mei` | 分割のまま `name_last` / `name_first` へ。`name` は連結して生成する |
| `user.pref_id` / `pref_id2` | 都道府県コード → 名称の文字列に展開（`pref_master` の `description`）。**`0` は未選択なので NULL** |
| `user.password` → `users.password_hash` | **base64 → 3DES-CBC 復号 → bcrypt（`$2a$` / コスト10）**。鍵導出は lw2 の `Crypt` と同じ（鍵 = `substr(md5(秘密鍵),0,24)` / IV = `substr(md5(鍵),0,8)` / ゼロ埋め）。**1文字でも変えると一部だけ壊れる** |
| ゼロ日付 (`0000-00-00`) | **NULL として扱う**（日時列すべて共通）。件数を警告に出す |
| `user.birth_date` | `birth_year` / `birth_month` / `birth_day` に分解（時刻部は捨てる。全件 `00:00:00`） |
| `user.role_id` が NULL | 設定に既定があればその値。**無ければ停止する**（黙って倒さない） |
| `user.del_chk` / `valid_chk` / `limit_date` | `status` は判定結果。**元の列は `is_valid` / `login_start_date` / `login_end_date` に残す** |
| `sendmail_*_chk` ほか通知系 | **極性を反転**して `notification_optouts` へ（`channel` で PC / 携帯を分ける） |

> **取り違え注意**
> - **`role_index` と `role_id` を混同しない。** 取り違えると求人企業とグループ管理者が入れ替わる
> - **通知フラグの極性。** lw2 は「受け取る」、新は「受け取らない」。反転を忘れると通知が真逆に出る
> - **`platform_admin` は絶対に付けない。** 付くと他テナントが見える

### 3.3 投入（load）

- **冪等性**: 決定論 ULID と業務キーの UNIQUE（`tenants.slug`、`external_user_links` の `(tenant_id, external_system, external_id)`）で担保する
- **投入前の確認**: `tenants` は **`name` に UNIQUE が無い**ため、`SELECT id, slug, name FROM tenants WHERE name = '<正式名称>'` で0件を確認してから INSERT する。詳細は [移行時の注意事項](review.md#移行時の注意事項)
- **`external_system` の値**: `lw2` と `kiracari` のどちらかに**3か所（ETL / ブリッジ / テスト）を揃える**。食い違うと同じ会員が二重登録される
- **投入前の検査**: 変換した直後に、移行先のスキーマ（`information_schema`）と突き合わせる。
  **NOT NULL で既定値の無い列を書いていない / UNIQUE が重複している（同じバッチの中・移行先の既存行の両方）/
  外部キーの参照先が無い**の3つを見る。**当たった行は移さず、`work_dir/not-migrated.csv` に出す。**
  止めるのでも、値を作り替えて通すのでもない — 直すのは移行の外（暫定対応）で、
  そのあと同じコマンドで再実行すれば入る。`insert_many` は既存行としか照合しないため、
  バッチ内の重複はここでしか見つからない
- **エラー時**: フェーズ単位でやり直す。会員を部分投入したまま次のフェーズに進まない

### 3.4 移行の対象外

**詳細と理由は [review.md](review.md#移行の対象外移行できないもの--移行しないもの) にある。** 実装で必要な要点だけ再掲する。

**A. 移行できないもの** — 移そうとしても成立しない。

| 対象 | なぜ移行できないか |
|---|---|
| `site` の DB 接続情報4列 | lw2 自身の DB への接続情報。**新環境は別サーバー・別 DB で、移しても機能しない。** 平文のため経路に乗せない |
| `user_login_log.input_password` | 入力パスワードの平文。**保存してよい場所が新環境に無い** |
| `twostepverification_log` の `input_code` / `correct_code` | 認証コードの平文。同上 |
| `twostepverification.verification_code` | 発行中の認証コード。**移した時点ですでに無効** |
| `user_auth_token` / `password_reminder` | 発行中の一時トークン。cutover 後は新環境が発行し直す |

> **上の4件（平文）は「移さない」ではなく「読み出さない」。** 抽出クエリで SELECT しないことをレビューで確認する。

**B. 方針として移行しないもの**

| 対象 | 理由 |
|---|---|
| `user_login_chk_log` | **日次バッチが作るログ**（ログイン可否の状態変化）。**ステージングの lw2 に存在しない**（DDL はあるが未適用）。受け皿も作らない |
| `user_login_log` / `user_login_log_monthly` / `twostepverification_log` | **純ログ**。受け皿はあるが移さず、cutover 後から記録を始める |
| `edit_form_data` | **旧環境自身が3日で消している**（`EditFormDataModel::create()` が毎回 `DELETE ... regist_date <= NOW() - 3 DAY` を流す）。中身は管理画面の入力途中と `onetime_token`（**一回限りのトークン**）で、移した時点で無効 |
| `user.user_img_file_name` / `*1` | プロフィール画像。**運営の判断で対象外**（列は使うが空で始める） |
| `user.role_id` が NULL の会員 | **ロールが決まらないため移せない**（`users.role` は NOT NULL + FK）。ステージングでは `user_id=911` の1名。`zentai001` を `user_id=483` と共有する重複アカウントで、**受講0件・グループ0件・属性0件・一度もログインなし**。メールも57名が共有する `yoneda.mw@gmail.com`。移して困るデータが無いため対象外とする（2026-09-22 決定）。**本番ダンプでは該当者と件数を取り直す** |

### 3.5 検証

| 検証 | 方法 |
|---|---|
| 対象テナントが1件か | `SELECT id, name FROM tenants WHERE slug = 'recademy'`。**総数では判断しない**（デモ seed のテナントが同居しているのが正常）。あわせて同じ `name` が別 `slug` に無いかも見る |
| 会員の件数 | 抽出時の件数と `SELECT COUNT(*) FROM users` を照合（ステージング実測 3,155名） |
| ロールの分布 | `users.role` ごとの人数を出し、運営に確認してもらう（ステージング実測は [1-5](#1-5-ステージングダンプでの実測2026-09-22-実施)） |
| `platform_admin` が0件か | 1件でもあれば停止して原因を追う |
| メールの一意性 | `UNIQUE (tenant_id, email)` 違反が出ないこと。**移さなかった会員の件数**を `not-migrated.csv` と突き合わせる |
| 通知設定の極性 | 数名分を lw2 と突き合わせ、**真逆になっていない**ことを確認する |

---

## 未確定として残っているもの

| 項目 | 状態 |
|---|---|
| ETL設計 (`scrun-etl-design.md`) の段割当 | 当リポジトリに現物が無く、§番号の参照のみ。`tenants` の行作成と継続課金に段の割当が無いことは判明している |
| 本番ダンプ | **未受領。** ステージング（2026-09-18 取得）で dry-run まで確認済み（[1-5](#1-5-ステージングダンプでの実測2026-09-22-実施)）。件数・テナント構成・ロール構成は本番と違う |
