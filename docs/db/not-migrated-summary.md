# 移していない・移せない・移しても効かないもの — 一覧

**移行対象外（[06](06-out-of-scope/breakdown.md)）ではない**のに、次のどれかに当たる表・列を、区分をまたいで 1 枚にまとめたもの（2026-10-26 時点）。

1. 削除済みのデータで、移さない・印が残らないもの
2. 新に対応する機能・受け皿が無いため移さないもの（ログ・一時データを含む）
3. 移行ツールが未実装で、まだ移していないもの
4. 移しても新アプリが読まないもの
5. 移しただけでは新で正しく動かないもの
6. 新旧のテーブルの作りの違い（制約・受け皿の形）で移せないもの
7. 旧データの不整合（親が無い）で移せないもの

**件数の出どころ**
- ステージング `tenant_id = 10`。行数は、2026-10-23 の移行の確認（`out/not-migrated.csv`。全 5,325 行）と、各区分の `migration-spec.md` の実測。
- 「全テナント」と書いたものは、旧 DB 全体の行数（このテナントの分を切り出していない）。
- **「決定・未実装」** は、2026-10-26 までに扱いを決めたが、移行ツールにはまだ入れていないもの。区分 01 の分は手順 5 で入れ、2026-10-26 の確認（billing を除く。全 6,592 行）で一覧の件数を確かめた（「実装済み」と書いた）。
- 「4. 移しても新アプリが読まない」は、**区分 01 は機能仕様書（[functional-spec](01-foundation/functional-spec.md)）で確かめた。02〜05 は、分かっている分だけ**（区分ごとの見直しの手順 1 で確かめる）。

## まとめ

| 分類 | 表・列の数 | 行数（ステージング） | 主なもの |
|---|---:|---:|---|
| 1. 削除済みのデータ | 6 | 3,195 行（ほか値 51 件） | 商品から外した講座の結び付き 618、削除済みのタグと割当 2,551 |
| 2. 機能・受け皿が無い | 37 | 約 1.4 万行（ログ・一時データを除く） | いいね 6,559、携帯の受け取り設定 2,654、ポートフォリオ 1,837 |
| 3. 移行ツールが未実装 | 9 | 500 行超（件数が分からないものを除く） | お知らせ 302、求人 154、自動メールの文面 46、掲示板 16、クーポン 7 |
| 4. 移しても読まれない | 17（区分 01 で確認） | 2 万行超 | 公開範囲 18,502、講師の担当範囲 121、会員の旧の列 |
| 5. 移しただけでは動かない | 15 | — | 動画 5,511、メールの無い会員 2,635、旧のロールの会員 75 |
| 6. 作りの違いで移せない | 12 | 約 1,400 行（制約 215 ＋ 表せないもの 1,179） | 旧のチケットの履歴 986、動画の配信先が空 172、課題の作成日が空 17 |
| 7. 旧データの不整合 | 18 | 4,442 行 | 自動割当の記録 3,907、問題バンク 155、学習状況 73 |

> `out/not-migrated.csv`（2026-10-23。5,325 行）の内訳は、1 の 618 行 ＋ 2-1 の 50 行 ＋ 6-1 の 215 行 ＋ 7 の 4,442 行。
>
> 2026-10-26 の区分 03 の確認（billing を流していない）では全 11,521 行。区分 02 の確認（9,289 行）から、2-1 の削除した受講の記録の下の学習の行 2,239 行が増え、7 の学習状況が 7 行減った。
>
> 2026-10-26 の確認（**billing を流していない**。全 6,592 行）では、区分 01 の見直しで「移行対象外」が 5,205 行（携帯の受け取り設定 2,654 ＋ 削除済みの属性の割当 2,550 ＋ 属性 1）増え、billing の分（自動割当の記録など）が無い。

---

## 1. 削除済みのデータで、移さない・印が残らないもの

共通のルールは「削除済みも移し、`deleted_at` に削除した日時を入れる」。その例外と、印が残らないもの。

| 区分 | 旧 | 件数 | 扱い | 理由 |
|---|---|---:|---|---|
| 02 | 削除済みの `payment_item_lesson`（商品から外した講座） | 618 | **移さない**（一覧に「移行対象外」） | 新もコースから外した講座の結び付きは物理削除で持たない。入れると外した講座まで購入で受講できる（2026-10-23 決定） |
| 01 | 削除済みの `attribute`（タグ「掲示板書き込みテスト」）と、その割当 `user_attribute` | 1 ＋ 2,550 | **移さない**（一覧に「移行対象外」）**実装済み**（2026-10-26 の確認で一覧 1 ＋ 2,550） | 新はタグの削除済みの印を見ず、一覧・会員の詳細に出てしまう（2026-10-26 決定） |
| 01 | 削除済みの会員のメール（`user.mail_add`） | 51 名（値） | **NULL で入れる**（会員は移す）**実装済み**（verify の F-22） | 残すと、そのアドレスで新しく登録できない（2026-10-26 決定） |
| 02 | テスト・アンケートの定義の `del_chk` | アンケート 26 | 移すが、**削除済みの印が残らない** | 受け皿に削除の列が無い（現状は移していない） |
| 02 | `lesson_tag.del_chk` | 0 | 移すが、印が残らない | `del_chk` を読むが使っていない |
| 02 | `lesson_cate.del_chk` の日時 | 0 | `course_categories` は `active = FALSE` だけ（`tenant_course_categories` には `deprecated_at` を入れる） | — |

## 2. 新に対応する機能・受け皿が無いため移さないもの

### 2-1. 受け皿が無い（データとして移せる先が無い）

| 区分 | 旧 | 件数 | 備考 |
|---|---|---:|---|
| 01 | 携帯の通知の受け取り設定（`sendmail_mobile_chk`） | 2,654 行 | **実装済み**（2026-10-26。一覧に「移行対象外」で 2,654 行。移らない会員 `user_id=911` の 1 行を含む）。新は携帯のアドレスに送らず、PC と区別しない。移すと PC も止まって見える |
| 01 | `user_attached_info.personal_record_chk` / `line_entry_chk` | 87 名（前者） | 現状は移していない |
| 01 | `user.sendmail_bbs_comment_pc_chk` / `_mobile_chk` | 全員に値（ほぼ 0） | 現状は移していない |
| 01 | `attribute.kiracari_user_chk` | 1 | `user_tags` に受け皿が無い |
| 05 | 形の違う LINE の ID（`user.line_id`） | 0 行（ステージング） | **実装済み**（2026-10-26。一覧に「旧データの不整合」）。Messaging API の userId の形でない |
| 05 | 削除済みの運営メモ（`personal_record_advice.del_chk = 1`） | 0 行（ステージング） | **実装済み**（2026-10-26。一覧に「受け皿なし」）。新は `admin_notes.deleted_at` を読まず表示する |
| 04 | 種別の無い回数チケット（`user_ticket.ticket_id` が NULL） | 3 行（残 5 枚） | **実装済み**（2026-10-26。一覧に「受け皿なし」）。新はチケットに種別が要る。旧で今も 2 人が使える。種別の決め方は確認事項 D22 |
| 04 | 月チケットの今の期間の残り（`month_user_ticket`） | 0 行（ステージング） | **実装済み**（2026-10-26。一覧に「受け皿なし」）。種別が無い（D22）。`monthly_ticket_allowances` には入るが新は読まない |
| 04 | ライブの配るチケットの枚数（`live_lesson.item_ticket_price`） | 3 ライブ | 新に入れる先が無い。予約 1 回で引く枚数（1 枚）とは別（04 移行仕様 0-2 Q3） |
| 03 | 管理者が削除した受講の記録（`user_learning_lesson.del_chk = 1`）の下の学習の行 | 2,239 行 | **実装済み**（2026-10-26。一覧に「受け皿なし」）。新は `lesson_progress.deleted_at` を読まず、入れると完了に数える。アンケートの回答がある 2 行は残す（03 移行仕様 0-2 Q5） |
| 01 | `profile_item.*_static_chk`（4 列） | 13 項目 | 受け皿が無い（2026-10-02 に検討して取り下げ） |
| 01 | `group.system_sort_no` | 28 | 同上 |
| 01 | `user.live_lesson_preview_icon` / `new_skill_user_chk` | 3 / 0 | 同上 |
| 01 | `system_admin_role` | 0 | 現状は移していない |
| 02 | `unit_exemption`（免除の規則） | 1 | 受け皿なし。件数を警告に出すだけ |
| 02 | `report_path`（提出後の解説ページの配信先） | 144 | 受け皿なし |
| 02 | `lesson` の表示・枠の列（`lesson_thumbnail_type` ほか 10 列） | — | 読んでいない |
| 02 | `unit.enquete_suspended_chk`、`unit_precondition.precondition_type_id` | — / 全件 `100` | 読んでいない・書いていない |
| 02 | `payment_item.extension_type`（期限切れの後も延長できるか） | 13 | 受け皿なし |
| 02 | `payment_item` の初回価格・試用・自動継続・支払い方法など | — | `learning_paths` に列が無い（一部は決済の `settings.item` に残る） |
| 03 | 設問別回答のうち受け皿が無いもの（`quiz_answers`） | 50 | 一覧に「受け皿なし」 |
| 03 | アンケートの回答のうちお知らせ・レポートに付いたもの（`enquete_answer.entity_type_id` 1 / 3） | 226 | `survey_responses.lesson_id` が NOT NULL。受け皿を検討して取り下げ |
| 04 | 商品の分類（`payment_item_cate` / `payment_item_item_cate`） | 3 / 7 | 現状は移していない |
| 04 | 申込と受講の古い対応表（`payment_application_set_user_learning_lesson`） | 27 | 現状は移していない |
| 04 | 流入元の計測（`analytics_tag` / `trigger_media` / `payment_trigger_media`） | 12 / 7 / 7 | 受け皿なし |
| 04 | チケット・ライブの商品（`payment_item.item_type` 1 / 2 / 3） | 21 | 商品としては移さない（決済の `settings` に残す） |
| 05 | ポートフォリオ（`portfolio` ほか 7 表） | 1,837 | 受け皿なし（確認事項 E58） |
| 05 | いいね（`like_user`） | 6,559 | 受け皿なし |
| 05 | SNS 共有（`unit_share`） | 707 | 受け皿なし（E61） |
| 05 | スカウト（`scout` ほか 4 表） | 109 | 受け皿なし |
| 05 | 足あと（`footprint`） | 76 | 受け皿なし・純ログ |
| 05 | 個別メッセージ（`thread` / `thread_comment` ほか） | 20 / 25 / 46 | 新のメッセージはチャネル型で 1 対 1 ではない |
| 05 | 既読（`user_content_viewed`） | 1,383 | 受け皿なし |
| 05 | Web Push（`message_send` / `subscription`） | 230 / 1,157（全テナント） | 購読はブラウザの許可に紐づき、移しても使えない |
| 05 | LINE の文面（フォローメール・求人の LINE の本文） | — | 受け皿が無い |

### 2-2. ログ・一時データ（方針として移さない）

| 区分 | 旧 | 件数 | 備考 |
|---|---|---:|---|
| 01 | ログイン・二段階認証のログ（`user_login_log` ほか） | — | 純ログ。cutover 後から記録 |
| 01 | 発行中のトークン（`user_auth_token` / `password_reminder` / `twostepverification`）、入力途中（`edit_form_data`） | — | 移した時点で無効 |
| 02 | `remote_api_token`、プレビュー（`live_lesson_preview` ほか） | — | 一時データ |
| 03 | 権限・学習のログ（`payment_item_lesson_authority_log` / `user_learning_unit_log`） | 121,199 / 33,998（全テナント） | 純ログ |
| 03 | テストの中断・再開（3 表） | 約 300 万（全テナント） | 受験中の作業データ（確認事項 D2） |
| 04 | チケットの増減の履歴（`user_ticket_log`） | 986 | 台帳は予約から組み立てる（6 にも関係） |
| 05 | 配信・送信のログ（`line_send` ほか、`mail_send`） | 31 / 36 / 2,771（全テナント） | 純ログ |
| 05 | アクセスログ・セッション・集計（`access_log` / `user_session` / `summary_user_learning_test`） | 2,759 / 857 / 146 | 純ログ・派生データ |

## 3. 移行ツールが未実装で、まだ移していないもの

移す方針だが、移行ツールにまだ実装が無いもの（2026-10-26 に「この見直しで作る」と決めた）。

> **2026-10-26 に実装した**（[05 の移行仕様 0 章](05-support/migration-spec.md#0-見直し-未実装の移行2026-10-26-決定実装済み)）。お知らせ・クーポン（無料 2 件を除く）・問い合わせ・講座のディスカッション・就活プロフィール・企業・面談は移す。**掲示板・お仕事募集は移行対象外**（決定）、**自動メールの文面は差し込みの文面待ち**（[D14](open-questions.md)）。移さない行の内訳は 05 の移行仕様 0-10。

| 区分 | 旧 | 件数 | 備考 |
|---|---|---:|---|
| 05 | クーポン（`coupon` ほか） | 7 | `support.2` が空 |
| 05 | お知らせ（`announce` / `news`）と既読 | 35 / 267 | `support.3` が空。LINE の本文（`line_message`）は `announcements.line_body` に受け皿がある |
| 05 | 自動メールの文面（`mail_setting` / `mail_template`） | 39 / 7 | LINE の文面（`line_message_mail_setting` 1 件）も一緒に移す（2026-10-22 決定） |
| 05 | 問い合わせ（`inquire` / `inquire_answer` / `inquire_cate`） | — / — / 7 | `support.4` が空 |
| 05 | 求人・応募・企業（`recruit` ほか、`company`） | 154 | career の DB に書く（取り決めの見直しが要る） |
| 05 | 面談（`interview_record` ほか） | — | 同上 |
| 05 | 掲示板（`bbs` / `bbs_comment`） | 16 | 確認事項 E60 |
| 05 | ディスカッション（`discussion_board` ほか） | 10 / 7 | — |
| 01・05 | 会員の就活の列（`education` / `job_category` / `qualification` ほか） | — | career の DB に受け皿がある（2026-10-16）。移行ツールは career に書かない取り決め |

## 4. 移しても新アプリが読まないもの

移しているが、新アプリのコードから一度も読まれない表・列（新の動きには効かない）。**区分 01 は機能仕様書で確かめた**（[functional-spec の 0 章](01-foundation/functional-spec.md#0-新システムが使っていない表列)）。

| 区分 | 移行先 | 件数 | 旧での意味 |
|---|---|---:|---|
| 01 | `users.is_valid` / `login_start_date` / `login_end_date` / `is_lockout` / `failed_login_*` | 3,154 名 | 有効・利用期間・ロックアウト（ログインの可否は `status` だけで決まる。旧でログインできなかった会員は `inactive` にする。**決定・未実装**） |
| 01 | `users.last_login_at` / `total_login_count` / `password_changed_at` / `is_new` | 3,154 名 | ログインの記録など |
| 01 | `users.name_last` / `name_first` / `mobile_phone` / `mobile_email` / `language_code` / `self_introduction` / `blood_type` / `admin_memo` / `is_career_counselor` / `user_id` | 3,154 名 | 姓・名、携帯、言語、自己紹介、血液型、運営メモなど（表示名は `users.name` だけ） |
| 01 | `tenants.short_name` / `language_code`、`tenants.settings` の `service` / `features` / `lw2_*` | 1 | 略称・既定の言語・旧の設定 |
| 01 | `tenant_limits` / `tenant_field_defaults` | 1 / 1 | 会員数の上限・登録時の既定値 |
| 01 | `tenant_profile_item_categories`、`tenant_profile_items` の `item_type = 0`（固定項目）・`category_id` / `default_value` | 5 / 34 | プロフィール項目の分類・固定項目の設定（新は `settings.profile_fields` を読む。2026-10-26 に入れないと決定） |
| 01 | `user_field_visibility` | 18,502 | 公開範囲 |
| 01 | `tenant_login_windows` / `tenant_sso_configs` | 0 / 0 | ログインできる時間帯・SSO |
| 01 | `tenant_secrets` の Facebook / X / Instagram、`linkpreview_api_key` | 5 前後 | SNS ログイン・リンクのプレビュー |
| 01 | `instructor_assignments` | 121 | 講師の担当範囲（講師はロールだけで判定され、全講座を扱える） |
| 01 | `tenant_groups` の `parent_id` / `depth`、`tenant_group_members` | 28 / 98 | グループの階層・所属（受講者のコース別進捗の CSV でだけ読む） |
| 01 | 旧のロール（`user_roles` の system_admin / group_manager / company_manager）の会員 | 75 名（生きている会員） | 新の判定に出てこない（5 にも関係。確認事項 D10） |
| 01 | `user_personal_numbers.scout_display_type` | 3,154 | 保存するだけで、表示に使う処理はまだ無い |
| 02 | `live_lesson_group_targets` | 0 | ライブの公開グループ |
| 04 | `tag_auto_assign_rule_group_conditions` | — | 自動割当のグループの条件（新はグループで絞らず全員に効く） |
| 05 | `library_folder_group_targets` / `library_material_group_targets` / `library_material_tag_targets`、`community_categories.group_id` | 0 / 0 / 0 / — | ライブラリ・コミュニティのグループ・タグでの公開先 |
| 05 | `scout_follows`・`community_categories`・利用料の集計（`tenant_usage_*` の 3 表）・資料のグループ・属性の公開先（`library_*_group_targets`・`library_material_tag_targets`）・運営メモの `deleted_at` | 14 / 3 / 1・111・18,122 / 0 | 2026-10-26 に機能仕様書（[functional-spec-remaining](05-support/functional-spec-remaining.md)）で確かめた。受け皿として残すだけ |
| 02〜05 | 講座・レッスン・動画・受講登録・決済の `settings`（旧の値を残す列）など | — | **未確認**（区分ごとの見直しの手順 1 で確かめる） |

## 5. 移しただけでは新で正しく動かないもの

移しているが、そのままでは新の動きが旧と違う・使えないもの。移行の外の作業（新アプリの修正・運営の判断・cutover の作業）が要る。

| 区分 | 何が | 件数 | 動かない理由 | 必要な作業 |
|---|---|---:|---|---|
| 02 | 動画（`video_lessons`） | 5,511（YouTube 3 を除く） | p-movie はトークン、それ以外は旧サーバーの URL。新は `.m3u8` の URL か自前ストレージのキーを求める | p-movie の URL を得る・動画を移す（[sync-issues](school-launcher-sync-issues.md) B1） |
| 01 | 旧のロールの会員 | 75 名 | 新の判定に出てこず、管理画面に入れない | 運営の判断（確認事項 D10） |
| 01 | メールの無い会員 | 2,635 名 | パスワードの再設定（メール）を使えない | 運営の判断（D13） |
| 01 | ログイン ID が別の会員のメールと同じ会員 | 6 名 | 新はメールを先に探すので、ログイン ID でログインできない | 運営の判断（D12） |
| 01 | 公式アカウントの LINE のシークレット | 1（テナント） | 旧に無く、新は Webhook を無視する | cutover 前に設定する（B4） |
| 01 | 旧で LINE ログインしていた会員 | — | 新の LINE ログインの識別子（`oauth_provider_id`）を移していない | 未確認 |
| 02 | 講師（全講座の `instructor_id`） | 325 講座 | 講座→講師の対応表が無く、代理講師に寄せている（暫定対応） | 対応表の提供（確認事項 B） |
| 02・04 | 移したコース（公開中） | 228 | 切り替えた直後から新で売られる | 運営の判断（D7。B9） |
| 04 | 自動割当の「商品の購入」のきっかけ | 1 | 新はコースの購入で自動割当を動かさない | 新アプリの修正（B7） |
| 04 | 講座別の売上 | 決済 347 | 新の講座別の売上は `course_purchase` だけを数える | 新アプリの修正（B8） |
| 03 | 自動継続（月額）の購入 | 331 組 | 新のコースに継続課金が無く、期限が無いまま続く | 運用の判断（B6・D4） |
| 03 | 無料の講座の受講 | 164 講座（受講登録の無い修了 146 組・アンケートの回答 63 件・学習の記録 3,115 件・受験 60 件。2026-10-26） | 旧は受講登録なしで開けた。新は受講登録が要り、移した記録も受講者から見えない | 運営の判断（D3） |
| 02 | recademy のトップのカテゴリ（`settings.top_catalog`） | 1 | 新の migration は既にあるテナントにしか入れない | cutover 後に設定する（B2） |
| 02 | 講座のカテゴリ | 42 | 新の講座の一覧は全テナント共通のカテゴリ、探す画面はテナントごとのカテゴリを使う | 新アプリの判断（B3） |
| 01 | 受講者のコース別進捗の CSV の属性名 | — | CSV は `tenant_attributes` を読み、移行と新のタグは `user_tags` | 新アプリの修正 |

## 6. 新旧のテーブルの作りの違い（制約・受け皿の形）で移せないもの

### 6-1. 新の制約に当たって移せない行（`not-migrated.csv`）

| 区分 | 移行先 | 件数 | 理由 |
|---|---|---:|---|
| 02 | `video_lessons` | 172 | `video_url` が NOT NULL（旧に配信先が無い） |
| 02 | `assignments` | 17 | `created_at` が NOT NULL |
| 03 | `submissions` | 13 | `submitted_at` が NOT NULL |
| 03 | `live_reservations` | 8 | 同じ開催回・同じ会員の予約が UNIQUE（確認事項 1-1 #4） |
| 04 | `ticket_grants` | 3 ＋ 1 | `ticket_type_id` が NOT NULL ／ 枚数の CHECK |
| 01 | `users`（`user_id = 911`） | 1 | ロールが空（2026-09-22 決定）。この会員に紐づく行も外部キーで移らない（下の 7） |

### 6-2. 受け皿の形が違い、表せないもの

| 区分 | 旧 | 件数 | 表せないこと |
|---|---|---:|---|
| 02 | `payment_item.display_chk = 2` | 2 | 「購入画面に出さない」（新は「一覧に出さない」だけ） |
| 02 | `config_live_lesson` のキャンセル不可・時間つきの期限 | 0 | 新の期限は日数だけで、「不可」を表せない |
| 03 | 取り消された購入 | — | 旧に返金は無いが、新の値は `refunded`（返金） |
| 03 | 受講期限の終わり | — | 最終日の 23:59:59 で入れる。新は「翌日 0:00」（1 秒ずれる） |
| 04 | 自動継続の講座の商品の決済 | 191 | コースの購入にそろえたので、継続課金だったことは `settings` にしか残らない |
| 04 | `user_ticket_log`（チケットの増減の履歴） | 986 | 新の台帳はどの付与への増減かが必須で、旧の履歴はそれを持たない |

## 7. 旧データの不整合（親が無い）で移せないもの

旧の時点で親の行が物理削除されているもの（[constraint-violations の 2 章](constraint-violations.md)）と、その連鎖。`out/not-migrated.csv` に出る。

| 区分 | 移行先 | 件数 | 理由 |
|---|---|---:|---|
| 04 | `tag_auto_assign_logs` | 3,907 | 付与したもの（`assign_item`）が物理削除されている |
| 02 | `quiz_question_banks` / `quiz_questions` / `quiz_options` / `quizzes` | 155 / 8 / 42 / 2 | 問題の分類・バンク・設問・ユニットが無い（外部キー） |
| 02 | `survey_lessons` | 5 | アンケートの定義が物理削除 |
| 02 | `learning_path_courses` | 1 | 講座が物理削除 |
| 03 | `quiz_answers` / `quiz_attempts` | 60 / 29 | 受験・ユニットが物理削除 |
| 03 | `lesson_progress` | 66 | ユニットが無い（外部キー。2026-10-26 に 73 → 66。7 行は削除した受講の記録の下の行で、2-1 に移った） |
| 03 | `submissions` / `submission_feedbacks` / `submission_feedback_files` | 69 / 35 / 5 | 課題・提出・添削が無い（外部キー） |
| 03 | `survey_responses` / `survey_answers` | 4 / 7 | 回答したユニット・設問が無い |
| 04 | `payments` / `learning_path_purchase_payments` | 11 / 11 | 会員が物理削除（2017〜2019 年） |
| 03 | `enrollments`（受講権限） | 3 | 会員（`user_id = 911`）が移らない |
| 01・03 | `user_id = 911` に紐づく行（外部 ID・住所・公開範囲・通知・個別番号・コースの購入・受け皿講座の受講） | 1 / 1 / 5 / 2 / 1 / 1＋3 / 1 | 会員が移らない（6-1） |

## 関連

- 運営への確認事項: [open-questions.md](open-questions.md)
- school-launcher への追従で見つかった問題と課題: [school-launcher-sync-issues.md](school-launcher-sync-issues.md)
- 制約による不整合: [constraint-violations.md](constraint-violations.md)
- 移行対象外: [06-out-of-scope](06-out-of-scope/breakdown.md)
