# サポート（残り） — 新システムの機能仕様（移したデータの見え方）

移行の見直しの手順 1（[進捗](../rework-progress.md)）。区分 05 のうち、未実装の移行（[functional-spec.md](functional-spec.md)）の**後に残った範囲**: LINE の友だちの紐付け・ライブラリ（資料フォルダと資料）・運営メモ・スカウトのフォロー・コミュニティの分類・利用料の集計。

- **基準**: school-launcher `hanataba_dev` の `584026af`（2026-10-24。2026-10-26 時点で最新）＋ 作業ブランチの変更。コードを読んで調べた（動かしてはいない）
- **コードの場所**は school-launcher の `btoc-backend/` からの相対パス。フロントは `btoc-frontend/src/`

## 0. 移し方に効く点（先に）

| # | 内容 | 場所 |
|---|---|---|
| 0-1 | **アプリが読まない表**: `scout_follows`・`community_categories`・`tenant_usage_settings`・`tenant_usage_snapshots`・`tenant_usage_snapshot_users`・`library_folder_group_targets`・`library_material_group_targets`・`library_material_tag_targets`。`library_material_lesson_targets` は講座の複製でだけ読む（画面には出ない） | `MIG/20260930052453_lw2_support_additions.sql:13`、`internal/repository/course_duplicate_repo.go:80, 629-643` |
| 0-2 | 利用料の集計を書くバッチは無い（移した行とぶつからない） | `cmd/worker/main.go` |
| 0-3 | **運営メモの `deleted_at` は読まれない**（削除済みのメモも出る）。著者（`author_id`）は同じテナントの会員でないとメモが画面に出ない。表示は新しい順の 20 件まで | `internal/repository/admin_note_repo.go:37-41, 75-81`、`internal/service/learner_analytics_service.go:87` |
| 0-4 | **`line_links` は (テナント, 会員) と (テナント, LINE の ID) がどちらも UNIQUE**（大文字小文字を区別しない）。前後の空白があると webhook で引けない。同じ LINE の ID が別の会員に付いていると、後から連携した会員は連携されないのに成功と表示される | `MIG/20260909081130_line_messaging.sql:81-83`、`internal/line/repository/link_repo.go:54-68`、`internal/handler/oauth_line_handler.go:206-215` |
| 0-5 | **送るかは `is_friend = TRUE` だけで決まる**（会員の状態は見ない）。ブロック済みは最初の送信の 403 で FALSE になる。それ以外の失敗（無効な ID など）は落ちず、送るたびに失敗が積まれる | `link_repo.go:94-116`、`internal/line/service/line_service.go:300-306`、`broadcast.go:178-207` |
| 0-6 | 友だち追加・ブロックの webhook は、既存の行を LINE の ID で引いて `is_friend` を更新する。行の無い LINE ユーザーは無視 | `internal/line/handler/webhook_handler.go:41-96`、`line_service.go:226-248` |
| 0-7 | LINE ログイン（`users.oauth_provider`）では `line_links` は作られない（通知には別に行が要る） | `oauth_line_handler.go:111-131` |
| 0-8 | **資料フォルダが見えるかは `audience_type` と対象の表だけで決まる**: `course_enrolled` / `purchasers` は対象の講座を `active` で受講、`specific_users` は個別の対象（`library_folder_user_targets`）、`all_users` は全員。**グループ・タグでの絞り込みは評価されない** | `internal/library/repository/library_folder_repo.go:42-66` |
| 0-9 | **対象が要る種別で対象が 0 件のフォルダは誰にも見えず、運営が名前や公開を変えても 400 になる**（保存のたびに対象を検証する） | `internal/library/domain/library.go:156-227` |
| 0-10 | 公開の既定値はフォルダが FALSE・資料が TRUE | `MIG/20260804000328_add_library_materials.sql:90, 150` |
| 0-11 | **資料を開くと `storage_key` をそのまま署名した URL を返す**（形式を確かめない）。旧のファイル名のままだと URL は出るがストレージで 404。ダウンロードの記録は残る。`file` で `storage_key` が NULL、`url` で `external_url` が NULL だと 500。新のキーは `library/<tenantID>/<folderID>/<ULID>.<拡張子>` | `internal/library/service/library_service.go:243-257, 519-538` |
| 0-12 | ライブラリの表に削除日時は無い（削除は物理削除）。旧で削除済みのものは移さないか非公開にするしかない | `library_folder_repo.go:189-196` |

## 1. LINE の友だちの紐付け（`line_links`）

- **受講者**: `GET /api/v1/tenant/line/status`（`enabled, linked, is_friend, add_friend_url, …`。設定の画面の LINE 連携のカード）、連携の開始 `GET /api/v1/tenant/line/link/start`、解除 `DELETE /api/v1/tenant/line/link`
- **送信**: メールと同時に LINE にも送る（テナントの LINE 連携が有効・その種類が ON・トークンあり・`is_friend`）。お知らせの一斉配信は公開時に積み、worker が送る
- **運営**: /admin/line は送信の記録だけ（`line_links` は出ない）
- `linked_at`・`unfollowed_at` は書くだけ

## 2. ライブラリ

- **受講者**: `GET /api/v1/library/folders`（公開中で自分が対象のフォルダ。`id, name, description, material_count`）、`GET /api/v1/library/folders/:id/materials`（公開中の資料）、`POST /api/v1/library/materials/:id/open`（`url, kind, file_name`）
- **運営**: `/api/v1/tenant/library/folders`（`audience_type, course_ids, user_ids, published, sort_order, material_count`）、資料の更新（題・説明・URL・公開・並び。キーと種類は変えられない）
- 並び順は `sort_order, created_at, id`。`sort_order` は画面から変えられない

## 3. 運営メモ（`admin_notes`）

- `GET /api/v1/tenant/analytics/learners/:userId` の `admin_notes[]`（`author_name, body, created_at`）。会員の学習状況（insights）の画面。追加だけで、編集・削除は無い
- 読まない列: `updated_at`・`updated_by`・`deleted_at`

## 4. 読まれない表

`scout_follows`・`community_categories`・利用料の集計の 3 表は、画面にも API にも出ない（受け皿として残すだけ）。

## 5. 新システムの E2E（参考）

ライブラリ `57-admin-library`・`58-learner-library`、LINE `72-line-settings`・`82-line-message-templates`、学習状況 `15-admin-analytics`。運営メモ・LINE の ID の重なり・webhook の E2E は無い。
