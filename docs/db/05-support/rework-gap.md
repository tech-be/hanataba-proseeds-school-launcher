# サポート（未実装の移行の分） — 移行仕様と今の移行ツールの差分

移行の見直しの手順 4（[進捗](../rework-progress.md)）。[移行仕様の 0 章](migration-spec.md#0-見直し-未実装の移行2026-10-26-決定実装済み)（決定は 0-9）と、今の移行ツール・文書・school-launcher との差分。手順 5 でこの順に直す。

**今の移行ツール**: `support.2` クーポン・`support.3` お知らせ・`support.4` 問い合わせは Step が空。`support.6` 就業支援は助言メモ・スカウトのフォローだけ、`support.7` コミュニティは分類だけ。career の DB には繋いでいない。

## 1. 移行ツール（`migrator/`）

| # | 直すもの | 直す先 | 中身 |
|---|---|---|---|
| G1 | **career の DB への接続** | `migrator/config.py`、`migrator/context.py`、`migrator/db/`、`migrator/doctor.py`、`migrator/steps/schema.py` | 環境変数 `TARGET_CAREER_DB_URL` で受け取り、`ctx.career` に `TargetDatabase` を持たせる。`Record` に投入先（btoc / career）を持たせ、load・`exists`・制約の確認・`reconcile` が投入先の DB を使うようにする。`doctor` に career の必須スキーマ（`CAREER_SCHEMA`）を足す。**接続情報は表示しない** |
| G2 | **お知らせ**（`support.3`） | `migrator/steps/support/announcements.py`（新規）、`registry.py` | `news` / `announce` → `announcements`（ID の名前空間 `news` / `announce`）、配信先 → `announcement_user_targets`（`specific_users`）、既読 → `announcement_reads`、`news_reply` → `announcement_replies` / `_reply_comments`、`line_message` → `line_body`。削除済み → `withdrawn`。アナウンスの件名は固定の文言（設定 `provisional.announce_title`）。一覧に出すもの: 削除済み・外された配信先、会員がいない行、2 件目の返信、添付（ファイルを移せない）、アンケート付き・返信の締め切り |
| G3 | **クーポン**（`support.2`） | `migrator/steps/support/coupons.py`（新規） | `coupon`（無料の 2 件を除く 5 件。状態は旧のとおり）→ `coupons`、`coupon_user` → `coupon_user_targets`（`created_at` = 配布日）、`coupon_log` → `coupon_redemptions`。`provider_*` は空文字。一覧に出すもの: 無料クーポン、対象の商品（`coupon_item`）、ライブ・グループの対象 |
| G4 | **自動メールと LINE の文面**（`support.4` の前に置く新しいフェーズか、`support.4` に同居） | `migrator/steps/support/templates.py`（新規） | 旧の種類 → 新の種別の対応表（13→`password_reset`、20→`welcome`、21→`payment_succeeded`、32→`subscription_canceled`、31→`email_verification`、7→`inquiry_received`）。`line_message_mail_setting`（種類 35）→ `tenant_line_templates` の `welcome`。対応の無い種類・採らない種類（35・47・34・23 のメール、en）を一覧に出す。**差し込みの書き換えはしない**（補正データを読むだけ） |
| G5 | **問い合わせ**（`support.4`） | `migrator/steps/support/inquiries.py`（新規） | 分類: 新の既定 5 つを入れ、旧の分類を対応表で寄せる。`inquire` → `inquiries`（回答あり → `resolved`、無し → `open`、削除済み → `deleted_at`）。一覧に出すもの: ログインしていない人の 15 件、2 往復目の 5 行、講座の指定・添付 |
| G6 | **講座のディスカッション**（`support.7`） | `migrator/steps/support/community.py` | `discussion_board_comment` → `discussion_posts`（`lesson_id` = 旧ユニット）。一覧に出すもの: お題・採点・通知の設定 |
| G7 | **就活プロフィール**（`support.6`。career） | `migrator/steps/support/career.py` | 値のある会員だけ `learner_career_profiles`（`learner_name` = 会員の名前、`employment_status` = 空、学歴・職種・資格はそのまま、`desired_employment_types`）、`learner_desired_prefectures`（短い表記） |
| G8 | **企業**（career） | 同上 | `company` → `companies`（`tenant_id` は `user.company_id` でたどる。業種・メールは NULL） |
| G9 | **面談**（career） | 同上 | 担当者（`advisors`。旧のカウンセラーの会員）、予約済みの枠（`availability_slots`。面談日の 0 時 JST。**終わりの時刻が無いので開始と同じにする**）、`interviews`（`completed`・`career_consultation`）、`interview_records`（要約は空文字） |
| G10 | **移さない区分を一覧に出す** | 各 Step | 掲示板（`bbs` / `bbs_comment` / `bbs_set_*` / いいね）・お仕事募集（`recruit` / `recruit_user` / `line_message_recruit`）を理由「移行対象外」で一覧に出す（黙って落とさない） |
| G11 | 必須スキーマ | `migrator/steps/schema.py` | `inquiries.deleted_at`、`announcements.line_body`、`tenant_line_templates`、career の `companies` の NULL 可・`learner_desired_prefectures` |

## 2. 補正データ（`fixups/`）

| # | 直すもの | 中身 |
|---|---|---|
| F1 | 本文のプレーンテキスト化（Q2） | `news.news_detail` / `announce.message` の HTML を除いた本文を提案する（`<br>` → 改行、タグを除く、`&amp;` などを戻す）。補正データ `overrides.csv` に書き、移行ツールは読むだけ |
| F2 | 差し込みの書き換え（Q8） | `mail_setting` の件名・本文の `{USER_NAME}` → `{{user_name}}` などを提案する。新に無い差し込み（`{PASSWORD}`・`{LOGIN_ID}`・`{CODE}` など）は**提案せず空欄**にして、運営に文面を決めてもらう |
| F3 | `overrides.csv` が長い本文を持てるか | CSV の 1 値に数千字の本文が入る。読み書きの単体テストを足す |

## 3. 確認（`verify`）

| # | 中身 |
|---|---|
| V1 | `spec_checks` に 05 のデータの確認（S-01〜S-05・S-10〜S-14・S-20〜S-22・S-30〜S-32・S-50・S-51・S-60〜S-66）を足す。career の確認は career の DB に繋いで行う |
| V2 | `legacy_checks` に旧との照合を足す（件数・状態・既読・配信先・期限の起点）。変換のコードは使わない |

## 4. 単体テスト（`tests/`）

| # | 中身 |
|---|---|
| T1 | G2〜G9 の Step ごと（変換・一覧に出す行・ID の名前空間） |
| T2 | G1 の投入先の切り替え（career の Record が btoc に入らない） |
| T3 | F1〜F3、V1・V2 |

## 5. E2E

| # | 中身 |
|---|---|
| E1 | `scripts/e2e-stack.sh` に確認用の career-backend を足す（career の確認用の DB `career_lw2_check`） |
| E2 | `e2e/support.spec.ts`（新規）: S-06・S-07・S-15・S-16・S-23・S-24・S-33〜S-35・S-52・S-53・S-67・S-68・S-70・S-71 |

## 6. school-launcher（作業ブランチ `feat/lw2-migration-rework`）

| # | 中身 | 状態 |
|---|---|---|
| S3 | `inquiries.deleted_at` と、一覧・詳細を `deleted_at IS NULL` で絞る | **済み**（結合テスト済み） |
| S4 | career の企業の業種・メールを NULL 可にし、読み書きで NULL を扱う | **済み**（結合テスト済み） |

## 7. 文書

| # | 中身 |
|---|---|
| D1 | `migration-spec.md` の 1〜3 章を 0 章に合わせる（「未実装」の記述、移さないものの件数） |
| D2 | `breakdown.md` / `review.md` の該当の行 |
| D3 | `../not-migrated-summary.md` の 3 を、移した・移さないに振り分ける |
| D4 | `../open-questions.md` に運営への確認（掲示板・お仕事募集を移さないこと、クーポンが旧より広く効くこと、文面の差し込みの空欄、企業の業種・メール） |
| D5 | `../school-launcher-sync-issues.md`（E 節の受け皿、S3・S4） |

## 7-2. 手順 5・6 の状態と、そこで見つけて直したもの（2026-10-26）

**G1〜G11・F1〜F3・V1・V2・T1〜T3・E1・E2 は済み**（単体テスト 402 件・確認用の DB での run / verify / 流し直し / E2E）。D1〜D5 は済み（D2 の `breakdown.md` / `review.md` は 0 章を正とする注記だけ）。

| # | 見つけたこと | 直したこと |
|---|---|---|
| G12 | 希望勤務地の短い表記を `rstrip("都府県")` で作ると「京都府」が「京」になる | 末尾の 1 字だけ落とす（単体テスト） |
| G13 | 自動メールの文面に、新に当たる差し込みが無い旧の差し込み（`{PASSWORD}` など）が残ると、そのまま会員に届く | 残っている文面は移さず一覧に出す（補正データで直した文面が入れば移る） |
| V3 | S-05（本文の HTML）が、旧で `&lt;` と書かれていた「<」まで NG にした | 旧の本文に本物のタグがあるものだけを数える |
| E3 | パスワードの再設定のメールは、確認用の DB を作り直しても同じ会員に 1 日 3 通まで（DB の外で数えている） | 流し直すときは `e2e/users.json` の `reset` を別の会員にする |

## 8. 手順 5 の順番

1. G1（career の接続）→ T2
2. G2・G3・G5（btoc の 3 つ）→ T1
3. G4・F1〜F3 → T1・T3
4. G6〜G9 → T1
5. G10・G11、V1・V2 → T3
6. E1・E2
7. D1〜D5

## 9. 決めたうえでの細かい点（確認してほしいもの）

| # | 内容 | 案 |
|---|---|---|
| R1 | 面談の枠の終わりの時刻（旧に無い。NOT NULL） | 開始と同じ時刻にする（長さ 0 の枠） |
| R2 | 移すクーポンの「受講者に見せる」（旧に当たる値が無い） | FALSE（コードを知っている人だけが使える） |
| R3 | LINE の文面（種類 35「登録完了（SNS 連携）」）の行き先 | メールは 20 を採るが、LINE の文面は 35 しか無いので `welcome` の LINE の文面に入れる |
| R4 | 自動メールの文面の行き先のフェーズ | `support.4`（問い合わせ）とは分けて、新しいフェーズ `support.9 自動メールの文面` にする（区分の番号は増やすだけで、既存のフェーズの番号は変えない） |
