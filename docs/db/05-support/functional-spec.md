# サポート（未実装の移行の分） — 新システムの機能仕様（移したデータの見え方）

移行の見直しの手順 1（[進捗](../rework-progress.md)）。**移行ツールがまだ移していないもの**（[not-migrated-summary の 3](../not-migrated-summary.md#3-移行ツールが未実装でまだ移していないもの)）について、新システムがそのデータをどう読み書きするかを、移したデータがどう見えるかの観点で書き出したもの。
手順 2 のテスト仕様書と、手順 3 の移行仕様の材料にする。

- **基準**: school-launcher `hanataba_dev` の `584026af`（2026-10-24。2026-10-26 時点でも最新）。コードを読んで調べた（動かしてはいない）。
- **範囲**: お知らせ・クーポン・自動メールと LINE の文面・問い合わせ・掲示板（コミュニティ）・講座のディスカッション・求人と応募・面談・就活プロフィール。
- **コードの場所**は school-launcher からの相対パス。`btoc-backend/internal/` は `internal/`、`btoc-backend/db/migrations/` は `MIG/`、`btoc-frontend/src/` は `frontend/`、`career-backend/internal/` は `career/` と略す。
- **未確認**と書いたものは、コードから推論しただけのもの。**確認済み**は、移し方に効く点をコードで読み直したもの。

## 0. 移し方に効く点（先に）

| # | 機能 | 内容 | 場所 |
|---|---|---|---|
| 0-1 | お知らせ・クーポン | **配信対象が「購入者」（`audience_type = 'purchasers'`）のものは、対象の講座を読み込まない**（**確認済み**）。受講者に見えるかの判定は SQL で直接見るので正しく動くが、運営が保存し直すと対象の講座が消える（お知らせは公開できなくなる。クーポンは状態の切り替えだけでも消える） | `internal/announcement/repository/announcement_repo.go:120-140`、`internal/commerce/repository/coupon_repo.go:151-171` |
| 0-2 | クーポン | **コースの購入にはクーポンを使えない**（**確認済み**。`service/learning_path_purchase.go` に coupon が無い）。使えるのは講座の単品購入とサブスクだけ。旧の商品は新でコースとして売るので、商品を対象にしたクーポンは使い道が無い | `internal/service/learning_path_purchase.go` |
| 0-3 | クーポン | 配布日から N 日の期限は `coupon_user_targets.created_at` を起点にする。既定値（移行した日）のままだと期限が数え直しになる | `coupon_repo.go:285-308` |
| 0-4 | クーポン | 使用の記録（`coupon_redemptions`）は 1 人 1 クーポン 1 行（UNIQUE）。移した行は利用回数の上限に数えられる | `MIG/168_coupon_redemptions.sql` |
| 0-5 | お知らせ | 本文はプレーンテキストで表示する。HTML はタグがそのまま見える。公開日時（`published_at`）が NULL だと一覧の末尾に並ぶ | `frontend/app/(tenant)/announcements/page.tsx:156`、`announcement_repo.go:268` |
| 0-6 | 自動メールの文面 | **件名が空だと上書きの全体が無視される**（**確認済み**）。差し込みは `{{key}}` の形だけで、旧の書き方は置換されず文字のまま届く | `btoc-backend/cmd/worker/main.go:1766`、`internal/notification/domain/email_template.go:59` |
| 0-7 | 自動メールの文面 | 種別 `announcement` / `scout` / `footprint` / `bbs_comment` は、運営画面に出るがメールを送る処理が無い。上書きしても使われない | `internal/service/email_service.go` |
| 0-8 | 問い合わせ | 1 件は「質問 1 本＋回答 1 本」。往復のあるやり取りは表せない。分類を 1 件でも入れるなら `other` を含めないと、新しい問い合わせが 500 になる | `internal/inquiry/` |
| 0-9 | 掲示板 | 新の受け皿はテナント単位のチャンネル（`community_*`）。**参加者（`community_members`）の行が無い会員はメッセージを読めない**。画面は最新 50 件まで。添付は画面に出ない。本文はプレーンテキスト | `internal/community/` |
| 0-10 | 講座のディスカッション | 投稿は `discussion_posts`（ユニット単位）。**全ユニットの右パネルにディスカッションのタブがある。** 種別 `discussion` のユニットは作成も本文の表示もできない | `internal/service/discussion_service.go` |
| 0-11 | 就活プロフィール | **就業状況（`employment_status`）が一覧外の値だと、その会員は就活プロフィールを一切保存できない**（**確認済み**）。学歴・職種 100 字、資格 2000 字を超えても同じ | `career/matching/domain/learner_profile.go:188-191, 203-222` |
| 0-12 | 面談 | 面談は枠（`slot_id`。NOT NULL・外部キー）と担当者（`advisor_id`）が必須。旧には枠が無い | `career-backend/db/migrations/002_add_foreign_keys.sql` |
| 0-13 | 求人 | 運営の求人の一覧は受講者向けの API（`status = 'open'` 固定）を使っている。**下書き・終了の求人は運営の画面に出ず、編集できない** | `frontend/hooks/use-admin-career.ts:146-150`、`career/.../job_posting_repo.go:100` |
| 0-14 | career 全般 | career は別の DB（`career`）。会員・テナントは btoc の `users.id` / `tenants.id`（ULID）で持つ。DB をまたぐ外部キーは無い。受講者の画面の一覧は多くが新しい順 20 件まで | `career-backend/internal/config/config.go` |

## 1. お知らせ

### 1-1. 画面・API

| 区分 | 経路 | 条件 | 場所 |
|---|---|---|---|
| 受講者の一覧 | `/announcements` → `GET /announcements` | `tenant_id`・`status = 'published'`・`publish_start_at` が空か過去・`publish_end_at` が空か未来・配信対象。並びは `pinned DESC, published_at DESC, id DESC` | `announcement_repo.go:243-278` |
| 受講者の詳細 | `GET /announcements/:id`（開くと既読） | 一覧と同じ条件。外れると 404 | `announcement_service.go:328-346` |
| 未読の数 | `GET /announcements/unread-count` | 一覧の条件＋既読の行が無い | `announcement_repo.go:290-300` |
| 既読 | `POST /announcements/:id/read` | `announcement_reads` に行を入れる（最初の時刻を保つ）。**行が無い＝未読** | `:302-312` |
| 添付 | `GET /:id/attachments`・`download-url` | 受講者に見えるお知らせだけ。ファイルはストレージの `storage_key` | `announcement_service.go:450-503` |
| 返信 | `POST /:id/reply`・`GET /:id/replies` | `reply_type = 0` は返信できない | `:511-551` |
| 運営の一覧・作成・更新・削除・公開・取り下げ | `/admin/announcements` → `/tenant/announcements` | 全状態。並びは `created_at DESC`。対象は「消して入れ直す」。`published_at` は最初の公開でだけ入る | `announcement_repo.go:45-205`、`domain/announcement.go:297-324` |
| 既読の集計 | `GET /:id/read-stats` | 配信対象の人数と既読の行数 | `announcement_repo.go:314-365` |
| 公開の通知 | 公開 API の中 | アプリ内の通知と LINE の配信（`line_body`。空ならタイトル＋本文）。**メールは送らない。** API を呼ばずに入れた行は通知されない | `internal/server/wire_announcement.go:47-70` |

**配信対象**（`announcement_repo.go:215-239`）: `all_users`（全員）、`course_enrolled`（`announcement_course_targets` の講座を受講中）、`specific_users`（`announcement_user_targets`）、`purchasers`（受講中かつ有料の受講）。

### 1-2. 列

| 表.列 | 制約 | 検証（運営が保存するとき） | 想定外の値 |
|---|---|---|---|
| `announcements.title` | VARCHAR(500) NOT NULL | 必須・500 字 | 空でも表示されるが、編集すると 400 |
| `.body` | TEXT NOT NULL | 必須 | HTML はタグのまま見える |
| `.line_body` | TEXT NULL | 400 字まで | 400 字を超えると編集で 400 |
| `.status` | 外部キー（draft / published / withdrawn） | — | — |
| `.audience_type` | 外部キー（4 種） | 対象の数（講座系は 1 件以上・個別は 1 人以上） | 対象が 0 件だと誰にも見えない |
| `.pinned` / `.reply_type` | BOOL / TINYINT | `reply_type` は 0〜2 | — |
| `.publish_start_at` / `.publish_end_at` | DATETIME(3)、UTC | 終わり＞始め | 終わりが過去なら見えない |
| `.published_at` | DATETIME(3) NULL | — | NULL は一覧の末尾 |
| `.created_by` | 外部キー users、NULL 可 | — | — |
| `announcement_reads` | PK（お知らせ, 会員）。`read_at` NOT NULL | — | `tenant_id` は書くだけで読まない |
| `announcement_attachments` | UNIQUE（お知らせ, 位置）。`storage_key` 512 字 | 位置 1〜5 | ファイルの実体が無いとリンク切れ（未確認） |
| `announcement_replies` / `announcement_reply_comments` | 返信は複数、運営のコメントは返信 1 件に 1 件 | — | — |

**読まない**: `announcement_statuses` / `announcement_audience_types`（外部キー先としてだけ）、`announcement_reads.tenant_id`、対象の表の `created_at`（並びだけ）。

**E2E（新システム）**: 53（運営の一覧・状態・既読率・公開と取り下げ・日時の JST）、54（受講者に配信分だけ出る・既読になる）、82（`line_body` の 400 字）。

## 2. クーポン

### 2-1. 画面・API

| 区分 | 経路 | 条件 | 場所 |
|---|---|---|---|
| 運営の一覧 | `/admin/coupons` → `GET /tenant/coupons` | `created_at DESC`。利用回数は使用の記録の数 | `coupon_repo.go:222-241` |
| 運営の作成 | `POST /tenant/coupons` | Stripe のテナントなら Stripe にも作る。ロボットペイメントなら `provider_*` は空文字 | `coupon_service.go:173-241` |
| 運営の更新 | `PATCH /tenant/coupons/:id` | 画面が使うのは状態と「受講者に見せる」の切り替えだけ。**期限の種類・開始・日数は変えられない。削除の API は無い** | `:255-303` |
| 受講者の一覧 | `/coupons` → `GET /coupons` | `visible_to_learners = TRUE` かつ配信対象。状態・期限では絞らず「使えない理由」を付けて返す | `coupon_repo.go:251-270` |
| コードの確かめ | `POST /coupons/validate` | 下の順で判定 | `coupon_service.go:331-408` |
| 講座の決済（Stripe） | `POST /tenant/checkout` | `provider_promotion_id` が空だと 400 | `payment_service.go:259-283` |
| 講座の決済（カード・ロボットペイメント） | `/card-checkout/[courseId]?coupon=` | 割引後の金額をサーバで計算。確定で使用の記録を入れる | `card_checkout_service.go:78-160` |
| サブスク | プランの申し込み | Stripe だけ | `subscription_service.go:153-171` |
| コースの購入 | — | **使えない**（0-2） | — |

**判定の順**（`coupon_service.go:527-572`）: コードを正規化（前後の空白を除き大文字、50 字）→ テナントとコードで引く → 購入の種類（`applies_to`）→ 配信対象 → 期限の起点 → 本人が使っていないか → `status = 'active'` → 期間内（`[開始, 終わり)`。相対期限は起点の JST の日付＋N 日の 0 時まで）→ 利用回数が上限未満。

### 2-2. 列

| 表.列 | 制約 | 想定外の値 |
|---|---|---|
| `coupons.provider_coupon_id` / `provider_promotion_id` | VARCHAR(255) NOT NULL | 空文字でよい（ロボットペイメント）。Stripe 経路は promotion が空だと使えない |
| `.name` / `.code` | 100 字 / 50 字、**UNIQUE（テナント, コード）** | 大文字小文字だけが違うコードは衝突する（照合順序。未確認） |
| `.discount_type` / `.discount_value` | percent / amount、DECIMAL | 読むときは検証しない（100% を超えると金額がマイナス） |
| `.max_redemptions` | INT NULL | NULL は無制限 |
| `.validity_type` | none / fixed / assignment_days / registration_days | none で `expires_at` があれば fixed 扱い |
| `.starts_at` / `.expires_at` | DATETIME(3)、UTC | — |
| `.validity_days` | 1〜999（CHECK） | 相対期限で NULL なら無効 |
| `.applies_to` / `.status` / `.visible_to_learners` / `.audience_type` | 外部キー・BOOL | `purchasers` は 0-1 |
| `coupon_course_targets` | PK（クーポン, 講座） | 講座の受講者向け |
| `coupon_user_targets` | PK、`created_at` = 配布日 | 0-3 |
| `coupon_redemptions` | UNIQUE（クーポン, 会員） | 0-4。`payment_id` / `discount_amount` / `redeemed_at` は読まない |

**E2E（新システム）**: 42（運営の作成・状態・期限）、55・56（配信対象）。コードの確かめ・決済への適用の E2E は無い。

## 3. 自動メールと LINE の文面

| 区分 | 経路 | 条件 | 場所 |
|---|---|---|---|
| 運営の画面 | `/admin/settings?tab=email-templates` | メールと LINE を同じカードで編集 | `frontend/app/(tenant)/admin/settings/_components/email-template-settings.tsx` |
| メールの一覧・保存・既定に戻す | `GET/PUT/DELETE /tenant/email-templates/:kind` | 種別は `email_kinds`（`active` かつ廃止でない）。既定に戻す＝行を消す | `internal/notification/service/email_template_service.go` |
| メールの送信 | worker | `tenant_email_templates`（`enabled = TRUE`）があれば上書き。無い・件名が空なら既定の文面 | `cmd/worker/main.go:1745-1777` |
| LINE の一覧・保存 | `GET/PUT/DELETE /tenant/line-templates/:kind` | **10 種別だけ**: welcome・learning_reminder・payment_succeeded・payment_failed・subscription_created・subscription_canceled・live_reservation_confirmed・live_reservation_reminder・referral_reward・retention_reminder | `internal/line/service/template.go`、`text.go:27-38` |
| LINE の送信 | 通知のたび | テナントの LINE が有効で、その種別を送る設定のときだけ。行があれば差し込んで送る | `internal/line/service/fanout.go:24-58` |

- **差し込み**: `{{key}}`（`[a-z0-9_]`）。保存で許すのは全種別共通の 24 個。値が入るのは種別ごとに決まったものだけで、他は メールでは `{{key}}` のまま、LINE では空になる（`email_service.go`）。例: welcome は `user_name`・`tenant_name`・`login_url`。
- **列**: `tenant_email_templates`（UNIQUE（テナント, 種別）。件名 200 字・本文 4000 字まで。件名が空だと上書きの全体が無視される）、`tenant_line_templates`（UNIQUE（テナント, 種別）。本文 400 字まで。10 種別以外の行は使われない）。どちらも `created_at` / `updated_at` は読まない。
- **E2E（新システム）**: 82（LINE の文面）。メールの文面の E2E は無い。

## 4. 問い合わせ

| 区分 | 経路 | 条件 | 場所 |
|---|---|---|---|
| 受講者の送信 | `POST /inquiries` | ヘルプチャット・講座のチャットからのエスカレーション。分類は AI が決め、外れたら `other` | `internal/inquiry/service/inquiry_service.go:57-98` |
| 受講者の履歴 | `/my-questions` → `GET /inquiries` | 本人の分、新しい順。**画面は 50 件まで**。回答があれば表示 | `inquiry_repo.go:186-202` |
| 運営の一覧・詳細 | `/admin/inquiries` | 状態で絞る（初期は `open`）。詳細のやり取りの記録はヘルプチャットがあるときだけ | `inquiry_repo.go:160-184`、`inquiry_service.go:119-143` |
| 担当・回答・回答の編集 | `POST /:id/assign`・`/respond`・`PATCH /:id/resolution` | `closed` は回答できない。回答の編集は `resolved` のときだけ画面に出る | `internal/inquiry/domain/inquiry.go:96-157` |
| 分類 | `/tenant/inquiry-categories` | テナントの行。**0 件のときだけ既定の 5 件が入る**。`other` は廃止できない | `inquiry_category_service.go:158-174` |
| 通知 | API の中 | 直接入れた行は通知されない | `wire_events_domain.go:249-307` |

| 列 | 制約・使われ方 |
|---|---|
| `inquiries.user_id` | NOT NULL、外部キー。一覧は users と INNER JOIN |
| `.category_code` | 外部キー（テナント, コード）。テナントに無い分類は入らない |
| `.status` | open / in_progress / resolved / closed |
| `.question` / `.resolution` | TEXT。質問は必須 |
| `.session_id` / `.ai_session_id` | NULL 可（NULL ならやり取りの記録・講座名が出ないだけ） |
| `.assignee_id` / `.updated_at` | API で返さない |
| `.resolved_at` / `.created_at` | 回答の日時・並び |

**状態と回答の組み合わせ**: `resolved` / `closed`＋回答あり＝回答済みで出る。`closed`＋回答なし＝回答のフォームが出るが送ると 400。`open` / `in_progress`＋回答あり＝運営には回答が隠れ、受講者には出る。

**E2E（新システム）**: 73（エスカレーション・回答・分類）。

## 5. 掲示板（コミュニティ）

| 区分 | 経路 | 条件 | 場所 |
|---|---|---|---|
| チャンネルの一覧 | `/community` → `GET /community/channels` | `status = 'active'`、新しい順。画面は 100 件 | `community_channel_repo.go:120-150` |
| 参加 | `POST /channels/:id/join` | active のチャンネルだけ | — |
| メッセージ | `/community/[channelId]` → `GET/POST /channels/:id/messages` | **参加者でないと 403。** `status = 'active'`、新しい順 50 件（画面は過去を読めない） | `community_service.go:209-268`、`frontend/hooks/use-community.ts:145` |
| 削除・アーカイブ | 本人がメッセージを消す・講師以上がチャンネルをアーカイブ | `status` を変える | — |

| 列 | 制約・使われ方 |
|---|---|
| `community_channels.name` | 100 字（変更時はバイトで数える） |
| `.created_by` | NOT NULL、外部キー。編集できるのは作成者だけ |
| `.status` | active / archived / hidden |
| `.course_id` | UNIQUE（テナント, 講座）。見える範囲には使わない |
| `community_members` | UNIQUE（テナント, チャンネル, 会員）。role は owner / member |
| `community_messages.content` | 添付が無ければ必須。プレーンテキスト表示 |
| `.attachment_*` | **画面に出ない**（アップロード・ダウンロードの経路が無い） |
| `.user_id` | 名前が引けなければ「Unknown」 |

**読まない**: `community_categories`（旧の分類の受け皿）、`community_*_status_events`。**返信・スレッドは無い。**

**E2E（新システム）**: 40（チャンネル・参加・メッセージ・権限）。

## 6. 講座のディスカッション

| 区分 | 経路 | 条件 | 場所 |
|---|---|---|---|
| 一覧 | ユニットの右パネル → `GET /lessons/:lessonId/discussions` | 親（`parent_id IS NULL`）で `status = 'active'`、ユニットが削除されていない。ピン留めが先・新しい順。返信は 1 ユニット 2000 件まで木にする。画面は 20 件ずつ | `internal/community/repository/discussion_repo.go:112-168` |
| 投稿・返信 | `POST /discussions` | 受講中であること。本文 1〜10000 字 | `internal/service/discussion_service.go` |
| 編集・削除・いいね・ピン留め・ベストアンサー | `PATCH/DELETE /discussions/:id` ほか | 本人か講師以上。ベストアンサーは返信だけ | — |
| 運営のダッシュボード | 「未回答の質問」の数 | 返信が 1 件も無い親を数える | `internal/repository/dashboard_repo.go:33-48` |

| 列 | 使われ方 |
|---|---|
| `discussion_posts.lesson_id` | NOT NULL、外部キー。削除したユニットの投稿は見えない |
| `.parent_id` | 自己参照。**親が active でないと返信も見えない**。親を先に入れる |
| `.body` | プレーンテキスト |
| `.status` | active / deleted / hidden |
| `.pinned_at` / `.best_answer_selected_at` | 値があれば ON |
| `.created_at` | 並び・表示 |
| `discussion_likes` | UNIQUE（テナント, 投稿, 会員） |

**種別 `discussion` のユニット**: 種別のマスタにはあるが、作成も種別の変更もできず（`internal/domain/course.go:119-133`）、受講の画面に本文を出す分岐が無い。開くと、タイトル・説明と右パネルだけになる（未確認）。

**E2E（新システム）**: 09（投稿・返信・いいね・バッジ）。種別 `discussion` のユニットの E2E は無い。

## 7. career（求人・応募・面談・就活プロフィール）

### 7-1. DB と会員の結び付け

| 項目 | 内容 |
|---|---|
| DB | `career`（btoc とは別）。migration は `career-backend/db/migrations/`（goose） |
| 接続の設定 | 環境変数 `CAREER_DATABASE_*`。migrate は `CAREER_DATABASE_DSN` |
| テナント・会員 | JWT の `tenant_id` / `user_id`＝btoc の `tenants.id` / `users.id`（ULID）。DB をまたぐ外部キーは無い |
| career から btoc | 内部 API で氏名・スキル・プロフィール項目の設定を読み、通知を頼む |
| 時刻 | UTC |

### 7-2. 企業・求人

| 表 | 制約・使われ方 |
|---|---|
| `companies` | `name` / `industry` / `contact_email` が NOT NULL。編集ではメールの形式を確かめる（旧に無いと編集できない）。`status` は active / inactive（inactive でも求人は出る） |
| `job_postings` | `company_id` 外部キー（企業を消すと消える）。`title` / `description` 必須。`employment_type` は 6 種。`status` は draft / open / closed。`prefecture` は短い表記（「東京」）で、**一覧の絞り込みは完全一致**。年収は万円 |
| `job_posting_skills` | UNIQUE（求人, スキル） |

- 受講者の一覧: `status = 'open'`、新しい順 20 件（ページ送りなし）。運営の一覧も同じ API（0-13）。
- 受講者の画面に企業名は出ない（API が返さない）。

### 7-3. 応募（`matches`）

- UNIQUE（プロフィール, 求人）。`status` は suggested / applied / accepted / rejected。`applied_at` / `responded_at` は NULL 可（アプリから応募すると `applied_at` が入らない不具合がある）。
- 運営の一覧は求人・企業・プロフィールと INNER JOIN。受講者の一覧は 20 件まで。
- `match_scores` は推薦の計算の置き場で、移さなくてよい。

### 7-4. 面談

| 表 | 制約・使われ方 |
|---|---|
| `advisors` | UNIQUE（テナント, 会員）。一覧は active だけ |
| `availability_slots` | 担当者・開始・終了（UTC）・`is_booked` |
| `interviews` | `slot_id`（NOT NULL・外部キー）、`advisor_id`、`learner_user_id`。`purpose` は 3 種、`status` は scheduled / in_progress / completed / canceled / no_show |
| `interview_records` | UNIQUE（面談）＝面談 1 件に記録 1 件。`summary` 必須 |

- 取り消しは枠の `is_booked = TRUE` が前提。記録を作れるのは completed の面談だけ。
- 面談の一覧の受講者名は就活プロフィールの `learner_name`（無いと「（不明）」）。

### 7-5. 就活プロフィール

| 列 | 値 | 旧 |
|---|---|---|
| `learner_career_profiles`（UNIQUE（テナント, 会員）） | `learner_name` NOT NULL | — |
| `.education` | 自由記述 100 字 | `user.education` |
| `.employment_status` | **`full_time` / `fixed_term` / `temporary` / `part_time` か空**（0-11） | `user.employment_status`（数値。対応は未確認） |
| `.job_category` | 自由記述 100 字 | `user.job_category` |
| `.qualification` | 2000 字 | `user.qualification` |
| `learner_desired_prefectures` | 短い表記（「東京」）と「海外」。長い表記は読むときに寄せ、一覧外は落とす | 旧の希望勤務地 |
| `.desired_prefecture`（単数） | 画面から保存すると NULL になる。複数の表に入れる | — |

- 受講者は `/career/profile` で編集する。学歴・就業状況・資格を出す運営の画面は無い。

**E2E（新システム）**: 18・19・20・32・36・50・84（どれも demo の seed が前提）。

## 8. まだ調べていないこと

- 旧システムの側（データの形・件数・差し込みの書き方・面談の状態 23 種と新の 5 種の対応・`recruit_user` が応募か配信の記録か）は手順 3 で調べる。
- recademy の決済がロボットペイメントか（Stripe ならクーポンに Stripe の promotion code が要る）。
- メールの上書きの HTML が共通のレイアウトで包まれるか。
