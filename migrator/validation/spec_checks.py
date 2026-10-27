"""テスト仕様のデータの確認（`verify` の一部。移行の見直しの手順 6）。

各区分の `test-spec.md` の **方式 D（データの確認）** のケースを、ケース ID ごとに持つ。
**新アプリの問い合わせ条件を写して**移行先を確かめる（例: ログインできるのは `status = 'active'` だけ、
レッスンは `deleted_at IS NULL` で絞る）。条件の出どころは各区分の `functional-spec.md`。

`legacy_checks`（旧 DB と移行先を直接比べる）とは観点が違う。あちらは「旧の値を引き継いだか」、
こちらは「新アプリから見て正しく使えるか」。旧 DB を読むのは、期待する状態を旧から決めるときだけ。
"""

from __future__ import annotations

import json
import re
from typing import Callable

from .legacy_checks import CheckResult, Checker, Env, _legacy_can_log_in, _sample, _today_jst

#: 新の LINE の設定で選べる通知の種類（school-launcher `internal/line/service/text.go` の SelectableKind。
#: 基準 `584026af`。区分 01 の機能仕様 4-7）
LINE_SELECTABLE_KINDS = frozenset({
    "welcome", "learning_reminder", "payment_succeeded", "payment_failed", "subscription_created",
    "subscription_canceled", "live_reservation_confirmed", "live_reservation_reminder", "referral_reward",
    "retention_reminder", "announcement_published",
})

#: 新アプリが読む `tenants.settings` のキー（区分 01 の機能仕様 1-3）。入れるならどれも JSON オブジェクト
SETTINGS_OBJECT_KEYS = (
    "line", "profile_fields", "branding", "payment", "referral", "community", "application_form",
    "help_chat_rollout", "top_catalog",
)


def _n(rows) -> int:
    return int(rows[0]["n"]) if rows else 0


# --- 基盤 ---------------------------------------------------------------------
def foundation_spec(env: Env) -> list[CheckResult]:
    c = Checker("foundation")
    d, t = (env.tenant_id,), (env.legacy_tenant,)
    migrated = "tenant_id = %s AND user_id IS NOT NULL"  # 移した会員（旧の会員 ID を持つ）

    # F-01 / F-03 テナント
    rows = env.dst("SELECT slug, status, settings FROM tenants WHERE id = %s", d)
    if rows:
        slug, status = rows[0]["slug"] or "", rows[0]["status"]
        try:
            settings = json.loads(rows[0]["settings"] or "{}")
        except ValueError:
            settings = None
        import re
        c("F-01 テナントの slug・状態・settings", bool(re.fullmatch(r"[a-z0-9-]{3,63}", slug))
          and slug not in ("www", "admin") and status == "active" and isinstance(settings, dict),
          f"slug={slug} status={status}")
        bad = [k for k in SETTINGS_OBJECT_KEYS if isinstance(settings, dict) and k in settings
               and not isinstance(settings[k], dict)]
        c("F-03 新アプリが読む settings のキーが JSON オブジェクト", not bad, _sample(bad) if bad else "")
    else:
        c("F-01 テナントがある", False)
        settings = {}

    # F-10 パスワード
    bad = _n(env.dst(f"""SELECT COUNT(*) n FROM users WHERE {migrated} AND status <> 'deleted'
        AND password_hash <> '' AND password_hash NOT LIKE '$2a$%%'""", d))
    empty = _n(env.dst(f"SELECT COUNT(*) n FROM users WHERE {migrated} AND status <> 'deleted' AND password_hash = ''", d))
    c("F-10 削除済みでない会員のパスワードは bcrypt（$2a$）", bad == 0, f"bcrypt でない {bad} / 空 {empty}")
    # F-11 状態
    c("F-11 状態は active / inactive / pending / deleted", _n(env.dst(
        f"SELECT COUNT(*) n FROM users WHERE {migrated} AND status NOT IN ('active','inactive','pending','deleted')", d)) == 0)
    # F-12 メール
    blank = _n(env.dst(f"SELECT COUNT(*) n FROM users WHERE {migrated} AND email = ''", d))
    synthetic = _n(env.dst(f"SELECT COUNT(*) n FROM users WHERE {migrated} AND email LIKE '%%@lw2.invalid'", d))
    dup = _n(env.dst("""SELECT COUNT(*) n FROM (SELECT LOWER(email) e FROM users WHERE tenant_id = %s AND email IS NOT NULL
        GROUP BY LOWER(email) HAVING COUNT(*) > 1) x""", d))
    c("F-12 メールに空文字・合成アドレスが無く、一意", blank == 0 and synthetic == 0 and dup == 0,
      f"空文字 {blank} / 合成アドレス {synthetic} / 重複 {dup}")
    # F-13 ログインの手段
    c("F-13 メールの無い会員はログイン ID を持つ", _n(env.dst(f"""SELECT COUNT(*) n FROM users WHERE {migrated}
        AND status <> 'deleted' AND email IS NULL AND (login_id IS NULL OR login_id = '')""", d)) == 0)
    # F-14 ログイン ID
    ws = _n(env.dst(f"SELECT COUNT(*) n FROM users WHERE {migrated} AND login_id REGEXP '[[:space:][:cntrl:]]'", d))
    coll = _n(env.dst("""SELECT COUNT(DISTINCT a.id) n FROM users a JOIN users b
        ON b.tenant_id = a.tenant_id AND b.id <> a.id AND LOWER(b.email) = LOWER(a.login_id)
        WHERE a.tenant_id = %s AND a.status <> 'deleted'""", d))
    c("F-14 ログイン ID に空白・制御文字が無い", ws == 0, f"{ws} 名")
    c("F-14 ログイン ID が別の会員のメールと同じ会員（運営に渡す。確認事項 D12）", True, f"{coll} 名")

    # F-15 旧でログインできなかった会員は inactive
    today = _today_jst()
    legacy = {r["user_id"]: r for r in env.src("user", """SELECT user_id, del_chk, valid_chk, entry_date, limit_date,
        is_lockout FROM user WHERE tenant_id = %s""", t)}
    new = {r["user_id"]: r["status"] for r in env.dst(f"SELECT user_id, status FROM users WHERE {migrated}", d)}
    wrong = [k for k, r in legacy.items() if k in new and int(r["del_chk"] or 0) == 0
             and not _legacy_can_log_in(r, today) and new[k] == "active"]
    c("F-15 旧でログインできなかった会員は active でない", not wrong, _sample(wrong) if wrong else "")

    # F-16 / F-21 / F-22
    c("F-16 移した会員はパスワードの変更を求める", _n(env.dst(
        f"SELECT COUNT(*) n FROM users WHERE {migrated} AND must_change_password = FALSE", d)) == 0)
    c("F-21 削除済みの会員のログイン ID は NULL", _n(env.dst(
        f"SELECT COUNT(*) n FROM users WHERE {migrated} AND status = 'deleted' AND login_id IS NOT NULL", d)) == 0)
    c("F-22 削除済みの会員のメールは NULL", _n(env.dst(
        f"SELECT COUNT(*) n FROM users WHERE {migrated} AND status = 'deleted' AND email IS NOT NULL", d)) == 0)

    # F-30 / F-31 ロール
    c("F-30 ロールは user_roles にある値", _n(env.dst(f"""SELECT COUNT(*) n FROM users u
        LEFT JOIN user_roles r ON r.code = u.role WHERE u.{migrated} AND r.code IS NULL""", d)) == 0)
    legacy_roles = env.dst(f"""SELECT role, COUNT(*) n FROM users WHERE {migrated} AND status <> 'deleted'
        AND role NOT IN ('platform_admin','tenant_admin','instructor','learner') GROUP BY role""", d)
    c("F-31 新が判定しないロールの会員（運営に確かめる。確認事項 D10）", True,
      ", ".join(f"{r['role']} {r['n']}" for r in legacy_roles) or "0 名")

    # F-40 / F-41 プロフィール
    c("F-40 名前が空でない", _n(env.dst(f"SELECT COUNT(*) n FROM users WHERE {migrated} AND (name IS NULL OR name = '')", d)) == 0)
    bad = _n(env.dst(f"""SELECT COUNT(*) n FROM users WHERE {migrated} AND (
        (gender IS NOT NULL AND gender NOT IN (1, 2))
        OR (birth_year IS NOT NULL AND birth_year < 1900)
        OR (birth_month IS NOT NULL AND (birth_month NOT BETWEEN 1 AND 12))
        OR (birth_day IS NOT NULL AND (birth_month IS NULL OR birth_year IS NOT NULL AND
            STR_TO_DATE(CONCAT(birth_year, '-', birth_month, '-', birth_day), '%%Y-%%m-%%d') IS NULL)))""", d))
    c("F-41 性別は 1・2・NULL、生年月日は新の検証の範囲", bad == 0, f"{bad} 名")
    bad = _n(env.dst("""SELECT COUNT(*) n FROM tenant_profile_items i
        LEFT JOIN tenant_profile_item_labels l ON l.item_id = i.id AND l.tenant_id = i.tenant_id AND l.locale = 'ja'
        WHERE i.tenant_id = %s AND i.item_type = 1 AND (l.label IS NULL OR l.label = ''
        OR CHAR_LENGTH(l.label) > 100 OR CHAR_LENGTH(COALESCE(l.memo, '')) > 500)""", d))
    c("F-42 独自項目は ja の空でないラベル（100 字以内）と注記（500 字以内）", bad == 0, f"{bad} 項目")
    bad = _n(env.dst("""SELECT COUNT(*) n FROM user_profile_values v JOIN tenant_profile_items i ON i.id = v.item_id
        WHERE v.tenant_id = %s AND (i.tenant_id <> v.tenant_id OR i.item_type <> 1 OR v.value = ''
        OR CHAR_LENGTH(v.value) > 255)""", d))
    c("F-44 独自項目の値は item_type = 1 を指し、空でなく 255 字以内", bad == 0, f"{bad} 件")
    bad = _n(env.dst("""SELECT COUNT(*) n FROM user_addresses WHERE tenant_id = %s AND (
        kind NOT IN ('primary','secondary','foreign') OR CHAR_LENGTH(COALESCE(postal_code,'')) > 16
        OR CHAR_LENGTH(COALESCE(prefecture,'')) > 10 OR CHAR_LENGTH(COALESCE(city,'')) > 100
        OR CHAR_LENGTH(COALESCE(street,'')) > 400 OR CHAR_LENGTH(COALESCE(country,'')) > 64
        OR CHAR_LENGTH(COALESCE(nationality,'')) > 64)""", d))
    c("F-47 住所の種類と文字数", bad == 0, f"{bad} 件")

    # F-50 / F-51 通知の受け取り設定
    c("F-50 受け取り設定の種類は user_optional の種類だけ", _n(env.dst("""SELECT COUNT(*) n FROM notification_optouts o
        LEFT JOIN email_kinds k ON k.code = o.kind WHERE o.tenant_id = %s AND (k.code IS NULL OR k.user_optional = FALSE)""",
        d)) == 0)
    mobile = _n(env.dst("SELECT COUNT(*) n FROM notification_optouts WHERE tenant_id = %s AND channel = 'mobile'", d))
    listed = sum(1 for key in env.skipped("notification_optouts") if key.endswith(":mobile"))
    c("F-51 携帯の受け取り設定は移さず一覧に出す", mobile == 0, f"移行先 {mobile} / 一覧 {listed}")

    # F-53 個別番号
    rows = env.dst("""SELECT t.tenant_id legacy, MAX(n.regist_no) mx,
        SUM(n.scout_display_type NOT IN ('name','nickname','personal_no')) bad
        FROM user_personal_numbers n JOIN tenants t ON t.id = n.tenant_id WHERE n.tenant_id = %s GROUP BY t.tenant_id""", d)
    if rows and rows[0]["mx"] is not None:
        r0 = rows[0]
        nxt = f"{r0['legacy']}0{int(r0['mx']) + 1}" if r0["legacy"] is not None else str(int(r0["mx"]) + 1)
        clash = _n(env.dst("SELECT COUNT(*) n FROM user_personal_numbers WHERE tenant_id = %s AND personal_no = %s",
                           d + (nxt,)))
        c("F-53 個別番号の表示の種類が正しく、次の採番が既存の番号と重ならない",
          int(r0["bad"] or 0) == 0 and clash == 0, f"次の番号 {nxt}")
    else:
        c("F-53 個別番号がある", False)

    # F-55 LINE の設定
    line = (settings or {}).get("line") if isinstance(settings, dict) else None
    if isinstance(line, dict):
        kinds = set(line.get("notification_kinds") or [])
        oa = line.get("official_account_id")
        problems = sorted(kinds - LINE_SELECTABLE_KINDS)
        if oa and not str(oa).startswith("@"):
            problems.append("official_account_id が @ で始まらない")
        if line.get("enabled"):
            secrets = {r["kind"] for r in env.dst("SELECT kind FROM tenant_secrets WHERE tenant_id = %s", d)}
            if not line.get("login_channel_id"):
                problems.append("login_channel_id が無い")
            for kind in ("line_login_channel_secret", "line_channel_access_token"):
                if kind not in secrets:
                    problems.append(f"{kind} が無い")
        c("F-55 LINE の設定が新の検証を通る形", not problems, ", ".join(problems))
    else:
        c("F-55 LINE の設定（無い）", True)

    # F-60〜F-62 タグ
    c("F-60 削除済みの印のタグが無い（削除済みの属性は移さない）", _n(env.dst(
        "SELECT COUNT(*) n FROM user_tags WHERE tenant_id = %s AND deleted_at IS NOT NULL", d)) == 0,
      f"一覧 {len(env.skipped('user_tags'))} 件")
    bad = _n(env.dst("""SELECT COUNT(*) n FROM user_tags WHERE tenant_id = %s AND (CHAR_LENGTH(name) > 100
        OR CHAR_LENGTH(COALESCE(memo, '')) > 200)""", d))
    c("F-61 タグの名前 100 字・メモ 200 字以内", bad == 0, f"{bad} 件")
    c("F-62 タグの割当はタグと同じテナント", _n(env.dst("""SELECT COUNT(*) n FROM user_tag_assignments a
        JOIN user_tags t ON t.id = a.tag_id WHERE a.tenant_id = %s AND t.tenant_id <> a.tenant_id""", d)) == 0)
    # F-64 グループ（属性名は新アプリ側の課題として対象外）
    c("F-64 グループの所属はグループと同じテナント", _n(env.dst("""SELECT COUNT(*) n FROM tenant_group_members m
        JOIN tenant_groups g ON g.id = m.group_id WHERE m.tenant_id = %s AND g.tenant_id <> m.tenant_id""", d)) == 0)
    return c.results


# --- サポート（未実装だった移行の分。docs/db/05-support/test-spec.md） -----------------

#: 新の自動メールで、種別ごとに**値が入る**差し込み（区分 05 の機能仕様 3-2）
MAIL_KEYS: dict[str, frozenset[str]] = {
    "password_reset": frozenset({"user_name", "tenant_name", "reset_link"}),
    "welcome": frozenset({"user_name", "tenant_name", "login_url"}),
    "payment_succeeded": frozenset({"user_name", "tenant_name", "course_name", "amount", "course_url"}),
    "subscription_canceled": frozenset({"user_name", "tenant_name", "plan_name", "access_end_date", "pricing_url"}),
    "email_verification": frozenset({"user_name", "tenant_name", "verify_link"}),
    "inquiry_received": frozenset({"tenant_name"}),
}
#: 運営画面に出るが、新にメールを送る処理が無い種別（区分 05 の機能仕様 0-7）
MAIL_NOT_SENT = frozenset({"announcement", "scout", "footprint", "bbs_comment"})
#: LINE で 1 人ずつ送れる種別（`internal/line/service/text.go`）
LINE_TEMPLATE_KINDS = frozenset({
    "welcome", "learning_reminder", "payment_succeeded", "payment_failed", "subscription_created",
    "subscription_canceled", "live_reservation_confirmed", "live_reservation_reminder", "referral_reward",
    "retention_reminder",
})
#: 新の希望勤務地（career `domain/prefecture.go`。短い表記と「海外」）
PREFECTURES = frozenset((
    "北海道 青森 岩手 宮城 秋田 山形 福島 茨城 栃木 群馬 埼玉 千葉 東京 神奈川 新潟 富山 石川 福井 山梨 長野 "
    "岐阜 静岡 愛知 三重 滋賀 京都 大阪 兵庫 奈良 和歌山 鳥取 島根 岡山 広島 山口 徳島 香川 愛媛 高知 福岡 "
    "佐賀 長崎 熊本 大分 宮崎 鹿児島 沖縄 海外"
).split())
EMPLOYMENT_STATUSES = frozenset({"", "full_time", "fixed_term", "temporary", "part_time"})
_LEGACY_PLACEHOLDER = re.compile(r"\{[A-Z][A-Z0-9_]*\}")
_PLACEHOLDER = re.compile(r"\{\{([a-z0-9_]+)\}\}")
_HTML = "'<[a-zA-Z/!]'"
_REAL_TAG = re.compile(r"<[a-zA-Z/!][^>]*>")


def support_spec(env: Env) -> list[CheckResult]:
    c = Checker("support")
    d = (env.tenant_id,)

    # --- お知らせ（S-01〜S-05） ---
    c("S-01 公開中のお知らせに公開日時がある", _n(env.dst(
        "SELECT COUNT(*) n FROM announcements WHERE tenant_id = %s AND status = 'published' AND published_at IS NULL", d)) == 0)
    bad = _n(env.dst("""SELECT COUNT(*) n FROM announcements WHERE tenant_id = %s AND (CHAR_LENGTH(title) NOT BETWEEN 1 AND 500
        OR TRIM(body) = '' OR CHAR_LENGTH(COALESCE(line_body, '')) > 400)""", d))
    c("S-02 件名 1〜500 字・本文あり・LINE の本文 400 字以内", bad == 0, f"{bad} 件")
    lonely = _n(env.dst("""SELECT COUNT(*) n FROM announcements a WHERE a.tenant_id = %s AND a.status = 'published'
        AND a.audience_type = 'specific_users'
        AND NOT EXISTS (SELECT 1 FROM announcement_user_targets t WHERE t.announcement_id = a.id)""", d))
    purchasers = _n(env.dst(
        "SELECT COUNT(*) n FROM announcements WHERE tenant_id = %s AND audience_type = 'purchasers'", d))
    c("S-03 配信対象と対象の表が合い、購入者（purchasers）を使わない", purchasers == 0,
      f"公開中で配信先が 0 人 {lonely} 件（誰にも見えない） / purchasers {purchasers} 件")
    c("S-04 既読は同じテナントのお知らせと会員を指す", _n(env.dst("""SELECT COUNT(*) n FROM announcement_reads r
        JOIN announcements a ON a.id = r.announcement_id JOIN users u ON u.id = r.user_id
        WHERE a.tenant_id = %s AND (r.tenant_id <> a.tenant_id OR u.tenant_id <> a.tenant_id)""", d)) == 0)
    # **旧でも文字として見えていた `<` は残ってよい。** 旧の本文が `&lt;strong&gt;`（画面には
    # 「<strong>」と出る）なら、プレーンテキストにした結果の `<strong>` は旧と同じ見え方。
    # 旧の本文に本物のタグがあるものだけを数える
    flagged = {r["id"] for r in env.dst(f"SELECT id FROM announcements WHERE tenant_id = %s AND body REGEXP {_HTML}", d)}
    real = set()
    if flagged:
        t = (env.legacy_tenant,)
        for kind, sql in (("news", "SELECT news_id k, news_detail b FROM news WHERE tenant_id = %s"),
                          ("announce", "SELECT announce_id k, message b FROM announce WHERE tenant_id = %s")):
            real |= {env.ulid(kind, r["k"]) for r in env.src(kind, sql, t)
                     if env.ulid(kind, r["k"]) in flagged and _REAL_TAG.search(r["b"] or "")}
    c("S-05 本文に HTML のタグが残っていない（補正データでプレーンテキストに直す）", not real,
      f"{len(real)} 件" + (f"（旧でも文字として見えていたもの {len(flagged - real)} 件は除く）" if flagged - real else ""))

    # --- クーポン（S-10〜S-14） ---
    bad = _n(env.dst("""SELECT COUNT(*) n FROM coupons WHERE tenant_id = %s AND (CHAR_LENGTH(code) > 50
        OR (validity_type = 'fixed' AND starts_at IS NULL AND expires_at IS NULL)
        OR (validity_type IN ('assignment_days', 'registration_days') AND (validity_days IS NULL OR validity_days NOT BETWEEN 1 AND 999))
        OR (discount_type = 'percent' AND discount_value > 100) OR discount_value <= 0)""", d))
    c("S-10・S-11 コード 50 字以内、期限と割引が新の検証の範囲", bad == 0, f"{bad} 件")
    c("S-13 使用の記録は同じテナントのクーポンと会員", _n(env.dst("""SELECT COUNT(*) n FROM coupon_redemptions r
        JOIN coupons cp ON cp.id = r.coupon_id JOIN users u ON u.id = r.user_id
        WHERE r.tenant_id = %s AND (cp.tenant_id <> r.tenant_id OR u.tenant_id <> r.tenant_id)""", d)) == 0)
    one_time = _n(env.dst("SELECT COUNT(*) n FROM coupons WHERE tenant_id = %s AND applies_to <> 'one_time'", d))
    c("S-14 移したクーポンは講座の単品購入向け（コースの購入には新で使えない）", one_time == 0,
      f"one_time 以外 {one_time} 件 / 対象の商品は一覧 {len(env.skipped('coupon_item'))} 件")

    # --- 自動メールと LINE の文面（S-20〜S-22） ---
    rows = env.dst("SELECT kind, subject, body FROM tenant_email_templates WHERE tenant_id = %s", d)
    bad = []
    for r in rows:
        keys = set(_PLACEHOLDER.findall(f"{r['subject']} {r['body']}"))
        allowed = MAIL_KEYS.get(r["kind"], frozenset())
        if (not (r["subject"] or "").strip() or len(r["subject"]) > 200 or len(r["body"] or "") > 4000
                or _LEGACY_PLACEHOLDER.search(f"{r['subject']} {r['body']}") or keys - allowed):
            bad.append(r["kind"])
    c("S-20 メールの件名・本文が新の検証の範囲で、差し込みはその種別で値が入るものだけ", not bad,
      _sample(bad) if bad else f"{len(rows)} 件")
    not_sent = [r["kind"] for r in rows if r["kind"] in MAIL_NOT_SENT]
    c("S-21 メールを送る処理がある種別だけ", not not_sent, _sample(not_sent) if not_sent else "")
    lines = env.dst("SELECT kind, body FROM tenant_line_templates WHERE tenant_id = %s", d)
    bad = [r["kind"] for r in lines if r["kind"] not in LINE_TEMPLATE_KINDS or len(r["body"] or "") > 400
           or _LEGACY_PLACEHOLDER.search(r["body"] or "")]
    c("S-22 LINE の文面は LINE で送れる種別で 400 字以内", not bad, _sample(bad) if bad else f"{len(lines)} 件")

    # --- 問い合わせ（S-30・S-31） ---
    c("S-30 分類に other がある", _n(env.dst(
        "SELECT COUNT(*) n FROM inquiry_categories WHERE tenant_id = %s AND code = 'other'", d)) == 1)
    bad = _n(env.dst("""SELECT COUNT(*) n FROM inquiries WHERE tenant_id = %s AND (
        (status IN ('resolved', 'closed') AND (resolution IS NULL OR TRIM(resolution) = ''))
        OR (status IN ('open', 'in_progress') AND resolution IS NOT NULL))""", d))
    c("S-31 状態と回答が合う", bad == 0, f"{bad} 件")

    # --- 講座のディスカッション（S-50・S-51） ---
    c("S-50 投稿のユニットが移したユニットで、削除されていない", _n(env.dst("""SELECT COUNT(*) n FROM discussion_posts p
        LEFT JOIN lessons l ON l.id = p.lesson_id WHERE p.tenant_id = %s AND (l.id IS NULL OR l.deleted_at IS NOT NULL)""", d)) == 0)
    c("S-51 返信の親が同じユニットの active の投稿", _n(env.dst("""SELECT COUNT(*) n FROM discussion_posts p
        JOIN discussion_posts q ON q.id = p.parent_id
        WHERE p.tenant_id = %s AND (q.lesson_id <> p.lesson_id OR q.status <> 'active')""", d)) == 0)

    # --- 残りの範囲（05 移行仕様 0R。docs/db/05-support/test-spec-remaining.md） ---
    dcount = lambda sql: _n(env.dst(sql, (env.tenant_id,)))  # noqa: E731
    n = dcount("""SELECT COUNT(*) n FROM line_links WHERE tenant_id = %s
        AND (line_user_id NOT LIKE 'U%%' OR CHAR_LENGTH(line_user_id) <> 33 OR line_user_id <> TRIM(line_user_id))""")
    dup = dcount("""SELECT COUNT(*) n FROM (SELECT LOWER(line_user_id) k FROM line_links WHERE tenant_id = %s
        GROUP BY k HAVING COUNT(*) > 1) x""")
    c("N-01 LINE の ID が U ＋ 32 文字で、1 会員にだけ付く", n == 0 and dup == 0, f"形の違い {n} 件 / 重なり {dup} 組")
    n = dcount("""SELECT COUNT(*) n FROM line_links l JOIN users u ON u.id = l.user_id
        WHERE l.tenant_id = %s AND l.is_friend AND u.status <> 'active'""")
    c("N-03 有効でない会員の紐付けは送らない（is_friend = FALSE）", n == 0, f"{n} 件")
    n = dcount("""SELECT COUNT(*) n FROM library_folders f WHERE f.tenant_id = %s
        AND f.audience_type IN ('course_enrolled', 'purchasers', 'specific_users')
        AND NOT EXISTS (SELECT 1 FROM library_folder_course_targets t WHERE t.folder_id = f.id)
        AND NOT EXISTS (SELECT 1 FROM library_folder_user_targets t WHERE t.folder_id = f.id)""")
    c("B-01 対象が要るフォルダに対象がある（0 件だと誰にも見えず、運営が保存できない）", n == 0, f"{n} 件")
    n = dcount("""SELECT COUNT(*) n FROM library_folders f WHERE f.tenant_id = %s AND f.published
        AND EXISTS (SELECT 1 FROM library_folder_group_targets g WHERE g.folder_id = f.id)""")
    c("B-02 グループで絞っていたフォルダが公開中でない（新はグループを読まず全員に見える）", n == 0, f"{n} 件")
    bad = dcount("""SELECT COUNT(*) n FROM library_materials m WHERE m.tenant_id = %s AND (
        (m.kind = 'file' AND (m.storage_key IS NULL OR m.storage_key NOT LIKE 'library/%%'))
        OR (m.kind = 'url' AND m.external_url IS NULL))""")
    c("B-03 資料のファイルが新のキー（library/…）にある", bad == 0,
      f"{bad} 件（旧のファイル名のまま。ファイルの移送 L9 で直す）")
    n = dcount("SELECT COUNT(*) n FROM admin_notes WHERE tenant_id = %s AND deleted_at IS NOT NULL")
    c("M-01 削除済みの運営メモが無い（新は deleted_at を読まず表示する）", n == 0, f"{n} 件")
    n = dcount("""SELECT COUNT(*) n FROM admin_notes m LEFT JOIN users u ON u.id = m.author_id AND u.tenant_id = m.tenant_id
        WHERE m.tenant_id = %s AND u.id IS NULL""")
    c("M-02 運営メモの著者が同じテナントの会員（違うと画面に出ない）", n == 0, f"{n} 件")

    # --- career（S-60〜S-66）。別の DB ---
    if env.career is None:
        c("S-60〜S-66 career の DB に接続している", False, "TARGET_CAREER_DB_URL が無い")
        return c.results
    careers = env.career
    profiles = careers("""SELECT user_id, learner_name, employment_status, education, job_category, qualification,
        desired_prefecture FROM learner_career_profiles WHERE tenant_id = %s""", d)
    bad = [p["user_id"] for p in profiles if (p["employment_status"] or "") not in EMPLOYMENT_STATUSES
           or len(p["education"] or "") > 100 or len(p["job_category"] or "") > 100
           or len(p["qualification"] or "") > 2000 or not (p["learner_name"] or "").strip()]
    c("S-60 就活プロフィールが新の検証の範囲（就業状況・字数・名前）", not bad, _sample(bad) if bad else f"{len(profiles)} 件")
    prefs = careers("SELECT prefecture FROM learner_desired_prefectures WHERE tenant_id = %s", d)
    bad = sorted({p["prefecture"] for p in prefs if p["prefecture"] not in PREFECTURES})
    single = [p["user_id"] for p in profiles if p["desired_prefecture"]]
    c("S-61 希望勤務地は短い表記で、単数の列は空", not bad and not single,
      f"{len(prefs)} 件" + (f" / 一覧外 {bad}" if bad else "") + (f" / 単数 {len(single)}" if single else ""))
    users = {p["user_id"] for p in profiles}
    for table, column in (("advisors", "user_id"), ("interviews", "learner_user_id")):
        users |= {r["u"] for r in careers(f"SELECT {column} u FROM {table} WHERE tenant_id = %s", d)}
    if users:
        marks = ", ".join(["%s"] * len(users))
        found = {r["id"] for r in env.dst(f"SELECT id FROM users WHERE tenant_id = %s AND id IN ({marks})", (*d, *users))}
    else:
        found = set()
    c("S-62 career の会員がすべて btoc の移した会員", users <= found, _sample(users - found) if users - found else f"{len(users)} 名")
    bad = _n(careers("SELECT COUNT(*) n FROM companies WHERE tenant_id = %s AND TRIM(name) = ''", d))
    c("S-63 企業の名前が空でない（業種・メールは NULL で入る）", bad == 0, f"{bad} 件")
    c("S-65 応募を移していない（旧に応募の記録は無い）", _n(careers(
        "SELECT COUNT(*) n FROM matches WHERE tenant_id = %s", d)) == 0)
    bad = _n(careers("""SELECT COUNT(*) n FROM interviews i LEFT JOIN availability_slots s ON s.id = i.slot_id
        LEFT JOIN advisors a ON a.id = i.advisor_id
        WHERE i.tenant_id = %s AND (s.id IS NULL OR a.id IS NULL OR (i.status = 'scheduled' AND NOT s.is_booked))""", d))
    c("S-66 面談に担当者と枠があり、予定の面談の枠は予約済み", bad == 0, f"{bad} 件")
    return c.results


# --- コンテンツ（docs/db/02-content/test-spec.md） -------------------------------

STATUSES_3 = "('draft', 'published', 'archived')"


def content_spec(env: Env) -> list[CheckResult]:
    c = Checker("content")
    d = (env.tenant_id,)

    def count(sql: str) -> int:
        return _n(env.dst(sql, d))

    # 講座・章（C-01〜C-05）
    n = count(f"SELECT COUNT(*) n FROM courses WHERE tenant_id = %s AND status NOT IN {STATUSES_3}")
    c("C-01 講座の状態は draft / published / archived だけ", n == 0, f"{n} 件")
    # 受講期間（access_days）は旧の `open_period` の値なので入ってよい（購入したときの期限に使う）
    n = count("""SELECT COUNT(*) n FROM courses WHERE tenant_id = %s AND (price IS NOT NULL
        OR is_sample OR thumbnail_url LIKE 'http%%')""")
    c("C-02 講座の価格は NULL、スターターでない、サムネイルはキー", n == 0, f"{n} 件")
    n = count("""SELECT COUNT(*) n FROM courses c LEFT JOIN course_categories k ON k.code = c.category
        WHERE c.tenant_id = %s AND c.category IS NOT NULL AND k.code IS NULL""")
    c("C-03 講座のカテゴリは NULL か course_categories にあるコード", n == 0, f"{n} 件")
    n = count("""SELECT COUNT(*) n FROM courses c LEFT JOIN users u ON u.id = c.instructor_id
        WHERE c.tenant_id = %s AND u.id IS NULL""")
    c("C-04 講座の講師が会員", n == 0, f"{n} 件")
    n = count("SELECT COUNT(*) n FROM course_chapters WHERE tenant_id = %s AND deleted_at IS NOT NULL")
    c("C-05 削除済みの章が無い（新は章の deleted_at を読まない）", n == 0, f"{n} 件")

    # レッスン（L-01〜L-05）
    n = count("SELECT COUNT(*) n FROM lessons WHERE tenant_id = %s AND type NOT IN ('video', 'live', 'text', 'survey')")
    c("L-01 レッスンの種別は video / live / text / survey だけ", n == 0, f"{n} 件")
    n = count("SELECT COUNT(*) n FROM lessons WHERE tenant_id = %s AND deleted_at IS NOT NULL AND status = 'published'")
    c("L-02 削除済みのレッスンは公開中でない", n == 0, f"{n} 件")
    n = count(f"SELECT COUNT(*) n FROM lessons WHERE tenant_id = %s AND type = 'text' AND description REGEXP {_HTML}")
    c("L-03 テキストのレッスンの本文に HTML が無い", n == 0, f"{n} 件")
    n = count("SELECT COUNT(*) n FROM lessons WHERE tenant_id = %s AND (drip_delay_days < 0 OR drip_delay_days > 365)")
    c("L-05 drip は 0〜365", n == 0, f"{n} 件")
    n = count("""SELECT COUNT(*) n FROM (SELECT course_id, sort_order FROM lessons WHERE tenant_id = %s
        AND deleted_at IS NULL GROUP BY course_id, sort_order HAVING COUNT(*) > 1) x""")
    c("L-04 講座の中でレッスンの並び順が重ならない", n == 0, f"{n} 組")

    # 動画（V-01・V-02）。p-movie の URL の規則が決まるまで NG のまま
    bad = count("""SELECT COUNT(*) n FROM video_lessons v JOIN lessons l ON l.id = v.lesson_id WHERE l.tenant_id = %s AND (
        (v.video_source = 'pmovie' AND NOT (v.video_url LIKE 'https://%%' AND v.video_url LIKE '%%.m3u8%%'))
        OR (v.video_source = 'storage' AND (v.video_url LIKE 'http%%' OR v.video_url LIKE './%%')))""")
    c("V-01 動画の URL が再生できる形（p-movie は https の .m3u8、storage はキー）", bad == 0,
      f"{bad} 件（p-movie のトークンは URL の規則を確かめてから補正データで直す）")
    n = count("""SELECT COUNT(*) n FROM video_lessons v JOIN lessons l ON l.id = v.lesson_id
        WHERE l.tenant_id = %s AND v.video_duration IS NULL""")
    c("V-02 動画の尺がある", n == 0, f"尺の無い動画 {n} 件（旧に尺が無い）")

    # テスト（Q-01〜Q-03）
    n = count("""SELECT COUNT(*) n FROM quizzes z WHERE z.tenant_id = %s
        AND NOT EXISTS (SELECT 1 FROM quiz_questions q WHERE q.quiz_id = z.id)""")
    c("Q-01 すべてのテストに設問がある", n == 0, f"{n} 件")
    n = count("""SELECT COUNT(*) n FROM quiz_questions q WHERE q.tenant_id = %s AND (TRIM(q.body) = '' OR q.points < 1
        OR (q.type IN ('single_choice', 'multiple_choice') AND (SELECT COUNT(*) FROM quiz_options o
            WHERE o.question_id = q.id AND o.is_correct) = 0)
        OR (q.type = 'single_choice' AND (SELECT COUNT(*) FROM quiz_options o WHERE o.question_id = q.id AND o.is_correct) > 1))""")
    c("Q-02 設問の本文あり・配点 1 以上・選択式は正解あり（単一選択は 1 件）", n == 0, f"{n} 件")
    n = count("SELECT COUNT(*) n FROM quizzes WHERE tenant_id = %s AND (passing_score < 0 OR passing_score > 100)")
    c("Q-03 合格点は 0〜100 の割合", n == 0, f"{n} 件")
    n = count("SELECT COUNT(*) n FROM quizzes WHERE tenant_id = %s AND (TRIM(title) = '' OR CHAR_LENGTH(title) > 255)")
    c("Q-06（データ）テストの題が 1〜255 字（空だと運営がテストを保存できない）", n == 0, f"{n} 件")

    # 課題・アンケート（A-01・S-02）
    n = count(f"""SELECT COUNT(*) n FROM assignments WHERE tenant_id = %s AND (TRIM(COALESCE(allowed_types, '')) = ''
        OR status NOT IN {STATUSES_3})""")
    c("A-01 課題の提出の種類があり、状態は draft / published / archived", n == 0, f"{n} 件")
    # 新は削除済みの設問を出さない（deleted_at IS NULL で絞る。school-launcher 20261026120001）
    n = count("""SELECT COUNT(*) n FROM survey_questions WHERE tenant_id = %s AND deleted_at IS NULL
        AND ((kind = 'file_upload' AND required) OR CHAR_LENGTH(prompt) > 500)""")
    dup = count("""SELECT COUNT(*) n FROM (SELECT o.question_id, o.label FROM survey_question_options o
        JOIN survey_questions q ON q.id = o.question_id WHERE q.tenant_id = %s AND q.deleted_at IS NULL
        GROUP BY o.question_id, o.label HAVING COUNT(*) > 1) x""")
    c("S-02 必須の添付が無い・設問文 500 字以内・選択肢が重ならない", n == 0 and dup == 0, f"{n} 件 / 重複 {dup} 組")

    # ライブ（LV-01〜LV-03）
    n = count("SELECT COUNT(*) n FROM live_lesson_occurrences WHERE tenant_id = %s AND deleted_at IS NOT NULL")
    c("LV-01 削除済みの開催回が無い", n == 0, f"{n} 件")
    n = count("""SELECT COUNT(*) n FROM live_lesson_occurrences o WHERE o.tenant_id = %s AND (o.ends_at <= o.starts_at
        OR (o.capacity IS NOT NULL AND o.capacity < (SELECT COUNT(*) FROM live_reservations r
            JOIN live_reservation_statuses s ON s.code = r.status WHERE r.occurrence_id = o.id AND s.occupies_seat)))""")
    c("LV-02 開催回の時刻と定員（定員 ≥ 席を使う予約）", n == 0, f"{n} 件")
    n = count("""SELECT COUNT(*) n FROM live_lesson_occurrences o JOIN lessons l ON l.id = o.lesson_id
        WHERE o.tenant_id = %s AND (l.type <> 'live' OR l.tenant_id <> o.tenant_id)""")
    c("LV-03 開催回のレッスンは同じテナントのライブ", n == 0, f"{n} 件")

    # コース（P-01・P-02）
    n = count(f"""SELECT COUNT(*) n FROM learning_paths WHERE tenant_id = %s AND (status NOT IN {STATUSES_3}
        OR (access_period_unit = 'day' AND access_period_value > 3650)
        OR (access_period_unit = 'month' AND access_period_value > 120) OR price < 0)""")
    c("P-01 コースの状態・受講期間・価格が新の範囲", n == 0, f"{n} 件")
    n = count("""SELECT COUNT(*) n FROM learning_paths p WHERE p.tenant_id = %s AND p.status = 'published' AND p.listed
        AND NOT EXISTS (SELECT 1 FROM learning_path_courses x JOIN courses c ON c.id = x.course_id
            WHERE x.learning_path_id = p.id AND c.status <> 'archived')""")
    c("P-02 公開中のコースに講座が 1 件以上ある", n == 0, f"{n} 件")
    return c.results


# --- 受講 ---------------------------------------------------------------------
#: 新の提出の状態・添削の結果（基準 `584026af` の CHECK。区分 03 の機能仕様 0-13）
SUBMISSION_STATUSES = "('submitted', 'under_review', 'graded', 'returned')"
FEEDBACK_RESULTS = "('pass', 'fail', 'needs_resubmission')"


def enrollment_spec(env: Env) -> list[CheckResult]:
    c = Checker("enrollment")
    t, d = (env.legacy_tenant,), (env.tenant_id,)

    def count(sql: str) -> int:
        return _n(env.dst(sql, d))

    # 受講登録（E-01〜E-05）
    n = count("SELECT COUNT(*) n FROM enrollments WHERE tenant_id = %s AND status = 'active' AND expires_at < UTC_TIMESTAMP()")
    c("E-01 期限が過ぎた受講登録が active でない", n == 0, f"{n} 件")
    # **旧の修了日がある組に completed_at がある**（03 移行仕様 0-2 Q1。旧は削除した受講の行を見ない）
    done = {(r["user_id"], r["lesson_id"]) for r in env.src("user_learning_lesson", """
        SELECT ull.user_id, ull.lesson_id FROM user_learning_lesson ull JOIN user u ON u.user_id = ull.user_id
        WHERE u.tenant_id = %s AND ull.del_chk = 0 AND ull.lesson_complete_date IS NOT NULL""", t)}
    enr = {(r["uid"], r["cid"]): r["done"] for r in env.dst("""
        SELECT u.user_id uid, c.legacy_lesson_id cid, e.completed_at IS NOT NULL done FROM enrollments e
        JOIN users u ON u.id = e.user_id JOIN courses c ON c.id = e.course_id
        WHERE e.tenant_id = %s AND c.legacy_lesson_id IS NOT NULL""", d)}
    missing = [k for k in done if k in enr and not enr[k]]
    extra = [k for k, v in enr.items() if v and k not in done]
    c("E-02 旧の修了日がある受講登録に completed_at がある（無いものに入っていない）", not missing and not extra,
      f"欠け {len(missing)} 件 / 余分 {len(extra)} 件（受講登録の無い修了 {len([k for k in done if k not in enr])} 件は D3）")
    n = count("SELECT COUNT(*) n FROM enrollments WHERE tenant_id = %s AND completed_at < enrolled_at")
    c("E-03（例外）修了日が受講開始より前（権限の付け直し。作り替えない。Q2）", True, f"{n} 件")
    # **コースの受講は課金の決済の後に流す**（`enrollment.learning_path_enrollments`）。無ければ確かめられない
    paths = count("SELECT COUNT(*) n FROM learning_path_enrollments WHERE tenant_id = %s")
    n = count("""SELECT COUNT(*) n FROM enrollments e WHERE e.tenant_id = %s AND e.via_learning_path AND e.status = 'active'
        AND NOT EXISTS (SELECT 1 FROM learning_path_enrollments p JOIN learning_path_courses x
            ON x.learning_path_id = p.learning_path_id AND x.course_id = e.course_id
            WHERE p.user_id = e.user_id AND p.status = 'active' AND (p.expires_at IS NULL OR p.expires_at > UTC_TIMESTAMP()))""")
    if paths:
        c("E-04 コース経由の有効な受講登録に、その講座を含む有効なコースの受講がある", n == 0, f"{n} 件")
    else:
        c("E-04（未確認）コース経由の受講登録とコースの受講", True,
          f"コースの受講が 0 件（billing を流していない）。コース経由の有効な受講登録 {n} 件は確かめていない")
    n = count("""SELECT COUNT(*) n FROM enrollments e LEFT JOIN users u ON u.id = e.user_id LEFT JOIN courses c
        ON c.id = e.course_id WHERE e.tenant_id = %s AND (u.id IS NULL OR c.id IS NULL)""")
    c("E-05 受講登録の会員・講座が移した会員・講座", n == 0, f"{n} 件")

    # コースの受講（P-01）
    n = count("""SELECT COUNT(*) n FROM learning_path_enrollment_courses WHERE tenant_id = %s
        AND prev_recorded AND (prev_status IS NULL OR prev_status NOT IN ('active', 'expired', 'refunded', 'revoked'))""")
    c("P-01 prev_recorded の行に元の状態がある", n == 0, f"{n} 件")

    # 学習の記録（R-01〜R-03）
    n = count("""SELECT COUNT(*) n FROM lesson_progress WHERE tenant_id = %s
        AND (updated_at < completed_at OR updated_at > UTC_TIMESTAMP() - INTERVAL 1 DAY)""")
    c("R-01 updated_at が旧の最終学習日時（完了より前でない、移行した日時でない）", n == 0, f"{n} 件")
    n = count("""SELECT COUNT(*) n FROM lesson_progress p JOIN lessons l ON l.id = p.lesson_id
        WHERE p.tenant_id = %s AND p.deleted_at IS NOT NULL AND l.deleted_at IS NULL""")
    c("R-02 削除済みの学習の記録は削除済みのレッスンのものだけ（新は記録の deleted_at を読まない）", n == 0, f"{n} 件")
    n = count("""SELECT COUNT(*) n FROM lesson_progress p LEFT JOIN lessons l ON l.id = p.lesson_id
        WHERE p.tenant_id = %s AND l.id IS NULL""")
    c("R-03 学習の記録のレッスンが移したレッスン", n == 0, f"{n} 件")

    # 修了証（C-01〜C-03）
    n = count("""SELECT COUNT(*) n FROM certificate_settings s WHERE s.tenant_id = %s
        AND s.serial_next <= (SELECT COALESCE(MAX(serial_no), 0) FROM certificates WHERE tenant_id = s.tenant_id)""")
    c("C-01 次の番号が発行済みの最大より大きい", n == 0, f"{n} 件")
    n = count("""SELECT COUNT(*) n FROM certificates t JOIN certificate_settings s ON s.tenant_id = t.tenant_id
        WHERE t.tenant_id = %s AND (s.serial_format <> 'date_prefixed'
            OR t.serial_text NOT REGEXP CONCAT('^No\\.[0-9]{8}', t.serial_no, '$'))""")
    c("C-02 書式が date_prefixed で、番号の文字列が No. ＋発行日＋番号", n == 0, f"{n} 件")
    n = count("""SELECT COUNT(*) n FROM courses c LEFT JOIN course_certificate_policies p ON p.course_id = c.id
        WHERE c.tenant_id = %s AND p.course_id IS NULL""")
    c("C-03 すべての講座に修了証の発行方針がある", n == 0, f"{n} 件")

    # テストの結果（Q-01・Q-02）
    n = count("""SELECT COUNT(*) n FROM quiz_attempts WHERE tenant_id = %s
        AND (started_at IS NULL OR score > max_score)""")
    c("Q-01 受験に開始時刻があり、得点 ≤ 満点", n == 0, f"{n} 件")
    n = count("""SELECT COUNT(*) n FROM quiz_attempts a JOIN quizzes z ON z.id = a.quiz_id WHERE a.tenant_id = %s
        AND a.status = 'completed' AND a.max_score > 0 AND a.passed IS NOT NULL
        AND (a.score * 100 / a.max_score >= z.passing_score) <> a.passed""")
    c("Q-02（例外）今の合格点で計算した合否が旧の合否と違う受験（受験後に合格点が変わった・旧でも合格できない。Q9）",
      True, f"{n} 件（ステージングでは 6 件の見込み）")

    # 課題（A-01・A-02）
    n = count(f"SELECT COUNT(*) n FROM submissions WHERE tenant_id = %s AND status NOT IN {SUBMISSION_STATUSES}")
    m = count(f"SELECT COUNT(*) n FROM submission_feedbacks WHERE tenant_id = %s AND result NOT IN {FEEDBACK_RESULTS}")
    c("A-01 提出の状態・添削の結果が新の値", n == 0 and m == 0, f"提出 {n} 件 / 添削 {m} 件")
    n = count("""SELECT COUNT(*) n FROM submissions s JOIN submission_feedbacks f ON f.submission_id = s.id
        WHERE s.tenant_id = %s AND s.status IN ('submitted', 'under_review') AND f.result IN ('pass', 'fail')""")
    c("A-02 合否の付いた提出が採点待ちに入らない", n == 0, f"{n} 件")

    # アンケートの回答（S-01・S-02）
    live = """FROM survey_responses r WHERE r.tenant_id = %s AND r.deleted_at IS NULL AND NOT r.suspended
        AND r.entity_type = 'lesson'"""
    n = count(f"""SELECT COUNT(*) n {live} AND NOT EXISTS (SELECT 1 FROM survey_submission_log g
        WHERE g.user_id = r.user_id AND g.lesson_id = r.lesson_id)""")
    c("S-01 回答した会員に survey_submission_log がある", n == 0, f"{n} 件")
    n = count(f"""SELECT COUNT(*) n {live} AND NOT EXISTS (SELECT 1 FROM lesson_progress p
        WHERE p.user_id = r.user_id AND p.lesson_id = r.lesson_id AND p.completed_at IS NOT NULL)""")
    c("S-02 回答した会員のアンケートのレッスンが完了", n == 0, f"{n} 件")
    return c.results


# --- 課金 ---------------------------------------------------------------------
def billing_spec(env: Env) -> list[CheckResult]:
    c = Checker("billing")
    t, d = (env.legacy_tenant,), (env.tenant_id,)

    def count(sql: str) -> int:
        return _n(env.dst(sql, d))

    # チケット（T-01〜T-07）
    n = count("""SELECT COUNT(*) n FROM ticket_grants WHERE tenant_id = %s
        AND (quantity < 1 OR remaining_quantity < 0 OR remaining_quantity > quantity)""")
    c("T-01 付与の枚数が新の制約の範囲", n == 0, f"{n} 件")
    # 旧の使える枚数: 専用チケット（種別あり）で、結び付く権限が今日有効（`LiveLessonModel:4858-4892`）
    legacy = {(r["uid"], r["tid"]): int(r["n"]) for r in env.src("user_ticket", """
        SELECT c.user_id uid, c.ticket_id tid, SUM(c.ticket_num) n FROM user_ticket c
        JOIN user u ON u.user_id = c.user_id
        LEFT JOIN payment_item_lesson_authority a ON a.authority_id = c.authority_id
        WHERE u.tenant_id = %s AND c.ticket_id IS NOT NULL AND c.ticket_num > 0
          AND (c.authority_id IS NULL OR (a.authority_start_date <= CURDATE() AND CURDATE() <= a.authority_end_date))
        GROUP BY 1, 2""", t)}
    usable = {(r["uid"], r["tid"]): int(r["n"]) for r in env.dst("""
        SELECT u.user_id uid, k.ticket_id tid, SUM(g.remaining_quantity) n FROM ticket_grants g
        JOIN users u ON u.id = g.user_id JOIN ticket_types k ON k.id = g.ticket_type_id
        WHERE g.tenant_id = %s AND g.remaining_quantity > 0 AND (g.expires_at IS NULL OR g.expires_at >= UTC_TIMESTAMP())
        GROUP BY 1, 2""", d)}
    c("T-02 会員 × 種別の使える枚数が旧と同じ（専用チケット）", legacy == usable,
      f"旧 {sum(legacy.values())} 枚 / 新 {sum(usable.values())} 枚")
    n = count("SELECT COUNT(*) n FROM ticket_grants WHERE tenant_id = %s AND starts_at > UTC_TIMESTAMP()")
    c("T-03（参考）利用開始日が未来の付与（新は開始日を読まず、すぐ使える）", True, f"{n} 件")
    n = count("""SELECT COUNT(*) n FROM ticket_grants g WHERE g.tenant_id = %s AND g.quantity < g.remaining_quantity
        + (SELECT COALESCE(-SUM(e.quantity_delta), 0) FROM ticket_ledger_entries e WHERE e.grant_id = g.id AND e.kind = 'consumed')""")
    c("T-04 予約で使った分を戻しても付与の枚数を超えない（キャンセルが失敗しない）", n == 0, f"{n} 件")
    n = count("SELECT COUNT(*) n FROM ticket_type_lessons WHERE tenant_id = %s AND deleted_at IS NOT NULL")
    c("T-05 種別の使えるレッスンに削除済みの行が無い（新は deleted_at を読まない）", n == 0, f"{n} 件")
    n = count("SELECT COUNT(*) n FROM live_lesson_ticket_requirements WHERE tenant_id = %s AND cost <> 1")
    c("T-06 予約 1 回で引く枚数は専用チケット 1 枚", n == 0, f"{n} 件")
    n = count("SELECT COUNT(*) n FROM ticket_types WHERE tenant_id = %s AND ticket_id IS NOT NULL AND refund_deadline_days IS NULL")
    c("T-09 移した種別はキャンセルでチケットを戻す（NULL だと新は戻さない。旧は必ず戻していた）", n == 0, f"{n} 件")
    n = count("SELECT COUNT(*) n FROM monthly_ticket_allowances WHERE tenant_id = %s")
    c("T-07（参考）毎月の配布の行（新は読まない。今の期間の残りは一覧に出る）", True, f"{n} 件")

    # ライブの予約（受講 03 の V-01・V-02）
    n = count("SELECT COUNT(*) n FROM live_reservations WHERE tenant_id = %s AND status = 'host_canceled'")
    c("V-01（03）予約の状態に host_canceled を使わない", n == 0, f"{n} 件")
    # 旧で送信済みの回（`live_lesson_date.mail_send_chk = 1`）の予約。未来の回は切り替え後に再送しない
    sent = {env.ulid("live_lesson_reserve", r["live_lesson_reserve_id"]) for r in env.src("live_lesson_reserve", """
        SELECT r.live_lesson_reserve_id FROM live_lesson_reserve r
        JOIN live_lesson_date dt ON dt.live_lesson_date_id = r.live_lesson_date_id
        JOIN live_lesson l ON l.live_lesson_id = dt.live_lesson_id WHERE l.tenant_id = %s AND dt.mail_send_chk = 1""", t)}
    unsent = {r["id"] for r in env.dst("SELECT id FROM live_reservations WHERE tenant_id = %s AND reminded_at IS NULL", d)}
    n = len(sent & unsent)
    c("V-02（03）旧で送信済みの回の予約に reminded_at がある", n == 0, f"{n} 件")

    # 決済（P-01〜P-06）
    migrated = "FROM payments p WHERE p.tenant_id = %s AND p.application_id IS NOT NULL"
    n = count(f"""SELECT COUNT(*) n {migrated} AND (p.provider NOT IN ('legacy_jpayment', 'bank_transfer')
        OR p.provider_payment_id NOT LIKE 'lw2-%%')""")
    c("P-01 決済代行は legacy_jpayment / bank_transfer、決済 ID は lw2- で始まる", n == 0, f"{n} 件")
    n = count(f"SELECT COUNT(*) n {migrated} AND p.status = 'pending'")
    c("P-02 移した決済に pending が無い（照合の枠を埋めない・入金確認の一覧に出ない）", n == 0, f"{n} 件")
    n = count(f"SELECT COUNT(*) n {migrated} AND (p.platform_fee <> 0 OR p.created_at > UTC_TIMESTAMP() - INTERVAL 1 DAY)")
    c("P-03 手数料 0、作成日時は旧の申込日時（移行した日時でない）", n == 0, f"{n} 件")
    legacy_months = {r["m"]: int(r["amt"] or 0) for r in env.src("payment_application", """
        SELECT DATE_FORMAT(a.application_date_time, '%%Y-%%m') m, SUM(a.amount) amt FROM payment_application a
        WHERE a.tenant_id = %s AND a.payment_type IN (1, 2, 3) AND a.application_result = 1
          AND EXISTS (SELECT 1 FROM user u WHERE u.user_id = a.user_id) GROUP BY 1""", t)}
    new_months = {r["m"]: int(r["amt"] or 0) for r in env.dst(f"""
        SELECT DATE_FORMAT(p.created_at + INTERVAL 9 HOUR, '%%Y-%%m') m, SUM(p.amount - p.platform_fee) amt
        {migrated} AND p.status = 'succeeded' GROUP BY 1""", d)}
    diff = sorted(m for m in set(legacy_months) | set(new_months) if legacy_months.get(m, 0) != new_months.get(m, 0))
    c("P-04 月別の売上（申込の月）が旧の支払い済みの合計と同じ", not diff, _sample(diff) if diff else
      "（旧の入金日の月とずれる 1 件・入金日の無い 7 件は分かっている差。0-2 Q7）")
    n = count("""SELECT COUNT(*) n FROM (SELECT provider_payment_id FROM enrollments WHERE tenant_id = %s
        AND provider_payment_id IS NOT NULL GROUP BY provider_payment_id HAVING COUNT(DISTINCT user_id) > 1) x""")
    c("P-05 受講登録の決済 ID が会員をまたいで重ならない（1 件の返金で他の会員が落ちない）", n == 0, f"{n} 件")
    n = count("""SELECT COUNT(*) n FROM learning_path_enrollments e JOIN payments p ON p.id = e.payment_id
        WHERE e.tenant_id = %s AND p.user_id <> e.user_id""")
    c("P-06 コースの購入の決済がその会員の決済", n == 0, f"{n} 件")

    # 領収書（R-01・R-02）
    n = count("""SELECT COUNT(*) n FROM receipts r JOIN payments p ON p.id = r.payment_id
        WHERE r.tenant_id = %s AND (p.status <> 'succeeded' OR r.user_id <> p.user_id)""")
    c("R-01 領収書の決済が成功していて、会員が決済の会員", n == 0, f"{n} 件")
    receipts = count("SELECT COUNT(*) n FROM receipts WHERE tenant_id = %s")
    enabled = count("SELECT COUNT(*) n FROM receipt_settings WHERE tenant_id = %s AND enabled")
    c("R-02 領収書を移したテナントは領収書の設定が有効", receipts == 0 or enabled == 1, f"領収書 {receipts} 件")

    # 自動割当（A-01〜A-04）
    n = count("""SELECT COUNT(*) n FROM tag_auto_assign_rule_grants g JOIN tag_auto_assign_rules r ON r.id = g.rule_id
        WHERE r.tenant_id = %s AND r.active AND (NOT g.valid OR g.deleted_at IS NOT NULL)""")
    c("A-01 動くルールの付与先に無効・削除済みが無い（新は読まない）", n == 0, f"{n} 件")
    n = count("""SELECT COUNT(DISTINCT r.id) n FROM tag_auto_assign_rules r
        JOIN tag_auto_assign_rule_group_conditions g ON g.rule_id = r.id WHERE r.tenant_id = %s AND r.active""")
    c("A-02 グループで絞る動くルールが無い（新は読まず全員に効く）", n == 0, f"{n} 件")
    n = count("""SELECT COUNT(*) n FROM tag_auto_assign_rules r WHERE r.tenant_id = %s AND r.active
        AND r.trigger_kind = 'purchase' AND (NOT EXISTS (SELECT 1 FROM tag_auto_assign_rule_triggers k WHERE k.rule_id = r.id)
          OR EXISTS (SELECT 1 FROM tag_auto_assign_rule_triggers k WHERE k.rule_id = r.id
                     AND k.course_id IS NULL AND k.plan_id IS NULL AND k.learning_path_id IS NULL))""")
    c("A-03 購入のルールのきっかけが講座・プラン・コースのどれかを指す", n == 0, f"{n} 件")
    n = count("""SELECT COUNT(*) n FROM tag_auto_assign_rule_grants g JOIN tag_auto_assign_rules r ON r.id = g.rule_id
        WHERE r.tenant_id = %s AND r.active AND g.ends_on < UTC_DATE()""")
    c("A-04（参考）動くルールで終了日が過去の付与先（配っても受講できない）", True, f"{n} 件")
    return c.results


#: 区分 → テスト仕様のデータの確認
CHECKS: dict[str, Callable[[Env], list[CheckResult]]] = {
    "foundation": foundation_spec,
    "content": content_spec,
    "enrollment": enrollment_spec,
    "billing": billing_spec,
    "support": support_spec,
}


def run(ctx, sections: set[str]) -> list[CheckResult]:
    """選んだ区分のテスト仕様のデータの確認を流す。**同じ `verify` で照合を流したあとに呼ぶ**（一覧を使う）。"""
    if ctx.target.connectionless or ctx.source is None:
        return []
    source = ctx.require_source()
    env = Env(
        src=lambda table, sql, params: source.fetch(table, sql, params),
        dst=lambda sql, params: ctx.target.query(sql, params),
        legacy_tenant=ctx.config.tenant.legacy_id,
        tenant_id=ctx.tenant_id.value,
        ulid=lambda ns, key: ctx.ulid.for_row(ns, key),
        excluded=ctx.exclusions().keys,
        career=(lambda sql, params: ctx.career.query(sql, params)) if ctx.career is not None else None,
    )
    results: list[CheckResult] = []
    for section, check in CHECKS.items():
        if section in sections:
            results += check(env)
    return results
