# サポート（残り） — 移行仕様と今の移行ツールの差分

移行の見直しの手順 4（[進捗](../rework-progress.md)）。[移行仕様の 0R 章](migration-spec.md#0r-見直し-残りの範囲2026-10-26-決定)（決定は 0R-2）と、今の移行ツール・文書・school-launcher との差分。手順 5 でこの順に直す。

**school-launcher の migration・アプリの変更は要らない。**

## 1. 移行ツール

| # | 直すもの | 直す先 | 今 | 直したあと |
|---|---|---|---|---|
| G1 | 形の違う LINE の ID（Q1） | `user_related.py` `LineLinksStep` | ログに出すだけ（黙って落とす） | `extract` で理由「旧データの不整合」・詳細「LINE の ID の形が違う（`U` ＋ 32 文字でない）」として一覧に出す。前後の空白は今どおり除く |
| G2 | 同じ LINE の ID の重なり（Q2） | — | UNIQUE に当たった行が制約違反で一覧に出る | 変えない（補正データで直す。確認 N-01 で重なりが無いことを確かめる） |
| G3 | 削除済み・利用停止の会員の紐付け（Q3） | `user_related.py` `LineLinksStep` | `is_friend = TRUE` | 会員の状態（`users._status_of` と同じ規則）が `active` でなければ **`is_friend = FALSE`**。`del_chk` などを読む列を足す |
| G4 | グループで絞ったフォルダ（Q4） | `support/library.py` | `audience_type = 'specific_users'`（対象 0 件）・公開は旧のまま | **`audience_type = 'all_users'`・`published = FALSE`**。グループは今どおり `library_folder_group_targets` に残す |
| G5 | 資料のファイルの場所（Q5） | — | 旧のファイル名 | 変えない（L9 で直す）。確認で件数を出す |
| G6 | 削除済みの運営メモ（Q6） | `support/career.py` `AdviceNotesStep` | `deleted_at` 付きで入れる | 入れずに、理由「受け皿なし」・詳細「削除済みの運営メモ。新は deleted_at を読まず表示する」で一覧に出す |

## 2. 確認（`verify`）

| # | 中身 |
|---|---|
| V1 | `spec_checks.support_spec` に足す: N-01〜N-03、B-01〜B-04、M-01・M-02。B-03 は L9 まで NG（件数を出す） |
| V2 | `legacy_checks` の運営メモの件数（削除済みを除く）、LINE の紐付けの件数（形の違うものを除く）を直す |

## 3. 単体テスト

| # | 中身 |
|---|---|
| T1 | G1・G3・G4・G6 |
| T2 | V1・V2 |

## 4. E2E

| # | 中身 |
|---|---|
| E1 | `e2e/support.spec.ts` に足す: N-04（LINE 連携の状態）・B-05（受講者のライブラリ）・B-06（運営がフォルダを開ける。保存しない）・M-03（運営メモ）。テスト用の会員に、LINE の紐付けのある会員・メモのある会員を足す |

## 5. 文書

| # | 中身 |
|---|---|
| D1 | `migration-spec.md` の 3 章（LINE・ライブラリ・運営メモ）、`review.md`、`breakdown.md` |
| D2 | `../not-migrated-summary.md`（G1・G6 の行、読まれない表） |
