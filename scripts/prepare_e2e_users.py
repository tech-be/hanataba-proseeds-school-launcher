"""E2E で使うテスト用の会員を、**確認用の DB の中だけで**ログインできる状態にする。

旧のパスワードの平文は読まない・使わない取り決めなので、テスト用に選んだ会員の
パスワードを、テスト用のパスワード（環境変数 `E2E_PASSWORD`）に入れ直す。

    .venv/bin/python scripts/prepare_e2e_users.py suggest   # 役ごとに会員を選んで e2e/users.json に書く
    .venv/bin/python scripts/prepare_e2e_users.py apply     # e2e/users.json の会員のパスワードを入れ直す

**扱いの決まり**

- 書き込むのは `--database`（既定 `lw2_schema_check`）だけ。`lw2_` で始まらない DB は拒む。
  `TARGET_DB_URL` の DB 名だけを差し替えて繋ぐ（接続情報は表示しない）
- 旧 DB は読むだけ（削除済みの会員の、旧のログイン ID とメールを引く）
- 画面に出すのは役と旧の `user_id` だけ。メール・ログイン ID は `e2e/.personas.json`
  （コミットしない）に書き、E2E がそこから読む
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlparse, urlunparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from migrator import config as config_mod  # noqa: E402
from migrator.core import passwords  # noqa: E402
from migrator.db.connect import connect  # noqa: E402

USERS_FILE = ROOT / "e2e" / "users.json"
PERSONAS_FILE = ROOT / "e2e" / ".personas.json"
PASSWORD_ENV = "E2E_PASSWORD"

#: ログインできる会員（区分 05 の役の共通の条件）
_LOGIN = "u.status = 'active' AND (u.email IS NOT NULL OR u.login_id IS NOT NULL)"

#: 役 → (初回にパスワードの変更を求めるか, 選ぶ条件)。条件は移行先の `users u` に対する WHERE。
#: **候補の少ない区分 05 の役を先に選ぶ**（重ならないように 1 人ずつ選ぶので、後だと取られる）。
#: `{career_user}` などは career の DB から引いた会員 ID の一覧に置き換える
PERSONAS: dict[str, tuple[bool, str]] = {
    # 区分 05 の残り: LINE の紐付けのある受講者（N-04）
    "line_linked": (False, _LOGIN + " AND EXISTS (SELECT 1 FROM line_links k WHERE k.user_id = u.id AND k.is_friend)"),
    # 区分 04: チケットの残高・ライブの予約・領収書・コースの受講のある受講者（T-08・V-03・R-03・P-02）
    "ticket_holder": (False, _LOGIN + " AND EXISTS (SELECT 1 FROM ticket_grants g WHERE g.user_id = u.id)"),
    "receipt_holder": (False, _LOGIN + " AND EXISTS (SELECT 1 FROM receipts r WHERE r.user_id = u.id)"),
    "reserver": (False, _LOGIN + """ AND EXISTS (SELECT 1 FROM live_reservations r
        JOIN live_lesson_occurrences o ON o.id = r.occurrence_id JOIN lessons l ON l.id = o.lesson_id
        WHERE r.user_id = u.id AND l.deleted_at IS NULL)"""),
    "path_learner": (False, _LOGIN + """ AND u.role = 'learner' AND EXISTS (SELECT 1 FROM learning_path_enrollments e
        WHERE e.user_id = u.id AND e.status = 'active' AND (e.expires_at IS NULL OR e.expires_at > NOW()))"""),
    # 区分 03: 旧で修了証を発行した受講者（C-04）・添削された提出がある受講者（A-03）・
    # アンケートに回答した受講者（S-04）・テストを受験した受講者（Q-03）・修了した有効な受講登録がある受講者（E-06・R-04）
    "certificate_holder": (False, _LOGIN + " AND EXISTS (SELECT 1 FROM certificates c WHERE c.user_id = u.id)"),
    "submitter": (False, _LOGIN + """ AND EXISTS (SELECT 1 FROM submissions s
        JOIN submission_feedbacks f ON f.submission_id = s.id WHERE s.user_id = u.id)"""),
    "completer": (False, _LOGIN + """ AND u.role = 'learner' AND EXISTS (SELECT 1 FROM enrollments e
        WHERE e.user_id = u.id AND e.status = 'active' AND e.completed_at IS NOT NULL)"""),
    # 回答の画面は受講登録が要る（期限は見ない）。無料講座の回答は受講登録が無い（D3）ので、ある会員を選ぶ
    "survey_responder": (False, _LOGIN + """ AND EXISTS (SELECT 1 FROM survey_responses r JOIN lessons l ON l.id = r.lesson_id
        JOIN enrollments e ON e.user_id = r.user_id AND e.course_id = l.course_id
        WHERE r.user_id = u.id AND r.deleted_at IS NULL AND NOT r.suspended AND l.deleted_at IS NULL)"""),
    "quiz_taker": (False, _LOGIN + """ AND EXISTS (SELECT 1 FROM quiz_attempts a JOIN quizzes z ON z.id = a.quiz_id
        JOIN lessons l ON l.id = z.lesson_id WHERE a.user_id = u.id AND l.deleted_at IS NULL)"""),
    # 区分 02: テストのある講座に受講登録している受講者（Q-05・A-02・S-03）
    "content_learner": (False, _LOGIN + """ AND u.role = 'learner' AND EXISTS (SELECT 1 FROM enrollments e
        JOIN lessons l ON l.course_id = e.course_id JOIN quizzes z ON z.lesson_id = l.id
        WHERE e.user_id = u.id AND e.status = 'active' AND l.status = 'published' AND l.deleted_at IS NULL)"""),
    "interviewee": (False, _LOGIN + " AND u.id IN ({interviewee})"),
    "career_user": (False, _LOGIN + " AND u.id IN ({career_user})"),
    "inquirer": (False, _LOGIN + """ AND EXISTS (SELECT 1 FROM inquiries i
        WHERE i.user_id = u.id AND i.deleted_at IS NULL AND i.status = 'resolved')"""),
    "discussant": (False, _LOGIN + """ AND EXISTS (SELECT 1 FROM discussion_posts p
        WHERE p.user_id = u.id AND p.status = 'active')"""),
    "news_reader": (False, _LOGIN + """ AND u.role = 'learner' AND EXISTS (SELECT 1 FROM announcement_user_targets t
        JOIN announcements a ON a.id = t.announcement_id WHERE t.user_id = u.id AND a.status = 'published'
        AND (a.publish_end_at IS NULL OR a.publish_end_at > NOW()))"""),
    # 独自項目の値・タグ・通知の受け取り設定を持つ受講者を優先する（F-33・F-46・F-52・F-63）
    "learner": (False, "u.role = 'learner' AND u.status = 'active' AND u.email IS NOT NULL"),
    "learner_change": (True, "u.role = 'learner' AND u.status = 'active' AND u.email IS NOT NULL"),
    "reset": (False, "u.role = 'learner' AND u.status = 'active' AND u.email IS NOT NULL"),
    "login_id_only": (False, "u.status = 'active' AND u.email IS NULL AND u.login_id IS NOT NULL"),
    "inactive": (False, "u.status = 'inactive' AND (u.email IS NOT NULL OR u.login_id IS NOT NULL)"),
    "deleted": (False, "u.status = 'deleted'"),
    "admin": (False, "u.role = 'tenant_admin' AND u.status = 'active'"),
}

#: 受講者を選ぶときに、見せられるデータが多い会員を先にする
_RICHNESS = """
    (EXISTS (SELECT 1 FROM user_profile_values v WHERE v.user_id = u.id))
  + (EXISTS (SELECT 1 FROM user_tag_assignments a WHERE a.user_id = u.id))
  + (EXISTS (SELECT 1 FROM notification_optouts o WHERE o.user_id = u.id))
"""


#: career の DB から候補を引く役（区分 05 の S-67〜S-71）
CAREER_CANDIDATES = {
    "career_user": "SELECT user_id AS u FROM learner_career_profiles WHERE tenant_id = %s",
    "interviewee": "SELECT learner_user_id AS u FROM interviews WHERE tenant_id = %s",
}


def check_career_database(name: str) -> str:
    """career の確認用の DB か。**開発の環境の career を壊さない。**"""
    if not name.startswith("career_") or name == "career":
        raise SystemExit(f"career の確認用の DB（career_ で始まる名前）だけを読む: {name}")
    return name


def career_dsn(cfg, name: str) -> str:
    base = cfg.target_career_dsn or cfg.target_dsn
    if not base:
        raise SystemExit("TARGET_DB_URL が無い（.env か環境変数で渡す）")
    return urlunparse(urlparse(base)._replace(path="/" + check_career_database(name)))


def check_database(name: str) -> str:
    """書き込んでよい DB 名かを確かめる。**開発の環境（learningware）を壊さない。**"""
    if not name.startswith("lw2_") or name == "learningware":
        raise SystemExit(f"確認用の DB（lw2_ で始まる名前）にだけ書き込む: {name}")
    return name


def with_database(dsn: str, name: str) -> str:
    """DSN の DB 名だけを差し替える。"""
    if not dsn:
        raise SystemExit("TARGET_DB_URL が無い（.env か環境変数で渡す）")
    return urlunparse(urlparse(dsn)._replace(path="/" + check_database(name)))


def e2e_password(env: dict[str, str]) -> str:
    """テスト用のパスワード。**リポジトリに書かない**ので環境変数からだけ受け取る。"""
    value = env.get(PASSWORD_ENV, "")
    if len(value) < 8:
        raise SystemExit(f"{PASSWORD_ENV} に 8 文字以上のテスト用のパスワードを入れる")
    return value


def pick(cursor, tenant: str, taken: set[int], career_ids: dict[str, list[str]] | None = None) -> dict[str, int]:
    """役ごとに 1 人ずつ、重ならないように選ぶ。"""
    chosen: dict[str, int] = {}
    career_ids = career_ids or {}
    for persona, (_, where) in PERSONAS.items():
        if persona in CAREER_CANDIDATES:
            ids = [i for i in career_ids.get(persona, []) if i.isalnum()]  # ULID だけ（SQL に埋め込む）
            if not ids:
                print(f"  {persona}: career の DB に候補がいない（この役の E2E は飛ばす）")
                continue
            where = where.replace("{" + persona + "}", ", ".join(f"'{i}'" for i in ids))
        cursor.execute(
            f"""SELECT u.user_id FROM users u
                WHERE u.tenant_id = %s AND u.user_id IS NOT NULL AND {where}
                ORDER BY {_RICHNESS} DESC, u.user_id
                LIMIT 50""",
            (tenant,),
        )
        for row in cursor.fetchall():
            user_id = int(row["user_id"])
            if user_id not in taken:
                chosen[persona] = user_id
                taken.add(user_id)
                break
        else:
            print(f"  {persona}: 条件に合う会員がいない（この役の E2E は飛ばす）")
    return chosen


def tenant_row(cursor, slug: str) -> dict:
    cursor.execute("SELECT id, slug, name FROM tenants WHERE slug = %s", (slug,))
    row = cursor.fetchone()
    if not row:
        raise SystemExit(f"テナント {slug} が移行先に無い（先に run する）")
    return row


def tenant_of(cursor, slug: str) -> str:
    return tenant_row(cursor, slug)["id"]


def describe(cursor, tenant: str, user_id: int) -> dict:
    """E2E が画面と見比べる値（移行先の値）。"""
    cursor.execute(
        """SELECT u.id, u.email, u.login_id, u.status, u.role, n.personal_no
           FROM users u LEFT JOIN user_personal_numbers n ON n.user_id = u.id
           WHERE u.tenant_id = %s AND u.user_id = %s""",
        (tenant, user_id),
    )
    row = cursor.fetchone()
    if not row:
        raise SystemExit(f"旧の user_id {user_id} の会員が移行先に無い")
    cursor.execute(
        """SELECT t.name FROM user_tag_assignments a JOIN user_tags t ON t.id = a.tag_id
           WHERE a.user_id = %s ORDER BY t.name""",
        (row["id"],),
    )
    tags = [r["name"] for r in cursor.fetchall()]
    cursor.execute(
        "SELECT DISTINCT kind FROM notification_optouts WHERE user_id = %s ORDER BY kind", (row["id"],)
    )
    disabled = [r["kind"] for r in cursor.fetchall()]
    return {**row, "tags": tags, "disabled_kinds": disabled}


def legacy_identifiers(source_dsn: str, legacy_tenant: int, user_id: int) -> dict:
    """削除済みの会員の、旧のログイン ID とメール（移行先では NULL になっている）。"""
    conn = connect(source_dsn)
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT login_id, mail_add FROM user WHERE tenant_id = %s AND user_id = %s",
            (legacy_tenant, user_id),
        )
        row = cursor.fetchone() or {}
    finally:
        conn.close()
    return {"legacy_login_id": row.get("login_id"), "legacy_email": (row.get("mail_add") or "").strip() or None}


def career_candidates(cfg, career_database: str, tenant: str) -> dict[str, list[str]]:
    conn = connect(career_dsn(cfg, career_database))
    try:
        cursor = conn.cursor()
        out = {}
        for persona, sql in CAREER_CANDIDATES.items():
            cursor.execute(sql, (tenant,))
            out[persona] = sorted({r["u"] for r in cursor.fetchall()})
        return out
    finally:
        conn.close()


def suggest(cfg, env: dict[str, str], database: str, career_database: str) -> None:
    conn = connect(with_database(cfg.target_dsn, database))
    try:
        cursor = conn.cursor()
        tenant = tenant_of(cursor, cfg.tenant.slug)
        chosen = pick(cursor, tenant, set(), career_candidates(cfg, career_database, tenant))
    finally:
        conn.close()
    USERS_FILE.write_text(json.dumps({p: {"user_id": u} for p, u in chosen.items()}, indent=2) + "\n")
    for persona, user_id in chosen.items():
        print(f"  {persona}: user_id={user_id}")
    print(f"{USERS_FILE.relative_to(ROOT)} に書いた（コミットしない）。役を変えるときは user_id を書き換える")


def support_facts(cursor, career, tenant: str, out: dict[str, dict]) -> dict:
    """区分 05 の E2E が見比べる ID（移行先の値）。**個人情報は書かない**（ID とコードだけ）。"""

    def ids(sql: str, params: tuple, cur=cursor) -> list[str]:
        cur.execute(sql, params)
        return [r["v"] for r in cur.fetchall()]

    visible = """SELECT a.id AS v FROM announcements a JOIN announcement_user_targets t ON t.announcement_id = a.id
        WHERE a.tenant_id = %s AND t.user_id = %s AND a.status = 'published'
        AND (a.publish_start_at IS NULL OR a.publish_start_at <= NOW(3))
        AND (a.publish_end_at IS NULL OR a.publish_end_at > NOW(3)) ORDER BY a.id"""
    facts: dict = {"announcements": {}}
    for persona in ("news_reader", "learner"):
        if persona in out:
            facts["announcements"][persona] = ids(visible, (tenant, out[persona]["id"]))
    facts["admin_announcement"] = next(iter(ids(
        """SELECT a.id AS v FROM announcements a WHERE a.tenant_id = %s AND a.status = 'published'
           AND EXISTS (SELECT 1 FROM announcement_user_targets t WHERE t.announcement_id = a.id) ORDER BY a.id LIMIT 1""",
        (tenant,))), None)
    cursor.execute("SELECT code, status FROM coupons WHERE tenant_id = %s ORDER BY code", (tenant,))
    facts["coupons"] = [dict(r) for r in cursor.fetchall()]
    if "inquirer" in out:
        facts["inquiries"] = ids("SELECT id AS v FROM inquiries WHERE user_id = %s AND deleted_at IS NULL ORDER BY id",
                                 (out["inquirer"]["id"],))
    if "discussant" in out:
        cursor.execute("""SELECT id, lesson_id FROM discussion_posts WHERE user_id = %s AND status = 'active'
            AND parent_id IS NULL ORDER BY id""", (out["discussant"]["id"],))
        facts["discussion_posts"] = [dict(r) for r in cursor.fetchall()]
    if career is not None and "interviewee" in out:
        facts["interviews"] = ids("SELECT id AS v FROM interviews WHERE learner_user_id = %s ORDER BY id",
                                  (out["interviewee"]["id"],), career)
    return facts


def content_facts(cursor, tenant: str, out: dict[str, dict]) -> dict:
    """区分 02 の E2E が見比べる ID（移行先の値。個人情報は含まない）。"""

    def one(sql: str, params: tuple):
        cursor.execute(sql, params)
        row = cursor.fetchone()
        return dict(row) if row else None

    facts: dict = {
        # 公開中で、公開中のレッスンを持つ講座（C-07・L-06・L-07）
        "course": one("""SELECT c.id FROM courses c WHERE c.tenant_id = %s AND c.status = 'published'
            AND EXISTS (SELECT 1 FROM lessons l WHERE l.course_id = c.id AND l.status = 'published' AND l.deleted_at IS NULL)
            ORDER BY c.id LIMIT 1""", (tenant,)),
        # 旧のテストのユニットを text で入れたレッスン（L-07）
        "text_lesson": one("""SELECT l.id, l.course_id FROM lessons l WHERE l.tenant_id = %s AND l.type = 'text'
            AND l.deleted_at IS NULL AND JSON_UNQUOTE(JSON_EXTRACT(l.settings, '$.legacy_unit_type')) = 'quiz'
            ORDER BY l.id LIMIT 1""", (tenant,)),
        "live_lesson": one("""SELECT l.id, l.course_id FROM lessons l WHERE l.tenant_id = %s AND l.type = 'live'
            AND l.deleted_at IS NULL AND EXISTS (SELECT 1 FROM live_lesson_occurrences o WHERE o.lesson_id = l.id)
            ORDER BY l.id LIMIT 1""", (tenant,)),
    }
    cursor.execute(
        """SELECT p.id FROM learning_paths p WHERE p.tenant_id = %s AND p.status = 'published' AND p.listed
           AND EXISTS (SELECT 1 FROM learning_path_courses x JOIN courses c ON c.id = x.course_id
                       WHERE x.learning_path_id = p.id AND c.status <> 'archived') ORDER BY p.id""",
        (tenant,))
    facts["paths"] = [r["id"] for r in cursor.fetchall()]
    # 運営が保存し直すテスト（Q-06）。移したテストすべて
    cursor.execute("""SELECT z.lesson_id FROM quizzes z JOIN lessons l ON l.id = z.lesson_id
        WHERE z.tenant_id = %s AND l.deleted_at IS NULL ORDER BY z.lesson_id""", (tenant,))
    facts["quiz_lessons"] = [r["lesson_id"] for r in cursor.fetchall()]
    if "content_learner" in out:
        uid = out["content_learner"]["id"]
        facts["quiz_lesson"] = one("""SELECT l.id, l.course_id FROM lessons l JOIN quizzes z ON z.lesson_id = l.id
            JOIN enrollments e ON e.course_id = l.course_id AND e.user_id = %s AND e.status = 'active'
            WHERE l.status = 'published' AND l.deleted_at IS NULL ORDER BY l.id LIMIT 1""", (uid,))
        facts["survey_lesson"] = one("""SELECT l.id FROM lessons l JOIN survey_lessons s ON s.lesson_id = l.id
            JOIN enrollments e ON e.course_id = l.course_id AND e.user_id = %s AND e.status = 'active'
            WHERE l.status = 'published' AND l.deleted_at IS NULL ORDER BY l.id LIMIT 1""", (uid,))
        facts["assignment_course"] = one("""SELECT a.course_id FROM assignments a
            JOIN enrollments e ON e.course_id = a.course_id AND e.user_id = %s AND e.status = 'active'
            WHERE a.status = 'published' ORDER BY a.id LIMIT 1""", (uid,))
    return facts


def enrollment_facts(cursor, tenant: str, out: dict[str, dict]) -> dict:
    """区分 03 の E2E が見比べる値（移行先の値。個人情報は含まない）。"""

    def one(sql: str, params: tuple):
        cursor.execute(sql, params)
        row = cursor.fetchone()
        return dict(row) if row else None

    def rows(sql: str, params: tuple) -> list[dict]:
        cursor.execute(sql, params)
        return [dict(r) for r in cursor.fetchall()]

    def uid(persona: str) -> str | None:
        return out[persona]["id"] if persona in out else None

    facts: dict = {
        "settings": one("""SELECT serial_next, serial_format,
            (SELECT MAX(serial_no) FROM certificates WHERE tenant_id = %s) AS max_serial
            FROM certificate_settings WHERE tenant_id = %s""", (tenant, tenant)),
        # 運営がコースの割り当て一覧を開ける会員（P-03）。コースの受講は billing の後に流すので、無ければ飛ばす
        "path_member": one("SELECT user_id AS id FROM learning_path_enrollments WHERE tenant_id = %s ORDER BY id LIMIT 1",
                           (tenant,)),
    }
    if uid("completer"):
        facts["completer"] = {
            "active": [r["course_id"] for r in rows("""SELECT course_id FROM enrollments WHERE user_id = %s
                AND status = 'active' ORDER BY course_id""", (uid("completer"),))],
            "completed": one("""SELECT course_id FROM enrollments WHERE user_id = %s AND status = 'active'
                AND completed_at IS NOT NULL ORDER BY course_id LIMIT 1""", (uid("completer"),)),
            "expired": [r["course_id"] for r in rows("""SELECT course_id FROM enrollments WHERE user_id = %s
                AND status <> 'active' ORDER BY course_id""", (uid("completer"),))],
        }
    if uid("certificate_holder"):
        facts["certificates"] = rows("""SELECT course_id, serial_no, serial_text FROM certificates
            WHERE user_id = %s ORDER BY serial_no""", (uid("certificate_holder"),))
    if uid("quiz_taker"):
        facts["quiz"] = one("""SELECT a.quiz_id, COUNT(*) AS attempts FROM quiz_attempts a JOIN quizzes z ON z.id = a.quiz_id
            JOIN lessons l ON l.id = z.lesson_id WHERE a.user_id = %s AND l.deleted_at IS NULL
            GROUP BY a.quiz_id ORDER BY attempts DESC, a.quiz_id LIMIT 1""", (uid("quiz_taker"),))
    if uid("submitter"):
        facts["submission"] = one("""SELECT s.id, s.assignment_id, s.status, f.result FROM submissions s
            JOIN submission_feedbacks f ON f.submission_id = s.id WHERE s.user_id = %s ORDER BY s.id LIMIT 1""",
                                  (uid("submitter"),))
    if uid("survey_responder"):
        # 生きている設問のあるアンケート（02 の S-03。旧でも設問が全部削除済みのアンケートがある）
        facts["survey_open"] = one("""SELECT s.lesson_id FROM survey_lessons s JOIN lessons l ON l.id = s.lesson_id
            JOIN enrollments e ON e.course_id = l.course_id AND e.user_id = %s
            WHERE l.deleted_at IS NULL AND l.status = 'published'
              AND EXISTS (SELECT 1 FROM survey_questions q WHERE q.lesson_id = s.lesson_id AND q.deleted_at IS NULL)
            ORDER BY s.lesson_id LIMIT 1""", (uid("survey_responder"),))
        facts["survey"] = one("""SELECT r.lesson_id FROM survey_responses r JOIN lessons l ON l.id = r.lesson_id
            JOIN enrollments e ON e.user_id = r.user_id AND e.course_id = l.course_id
            WHERE r.user_id = %s AND r.deleted_at IS NULL AND NOT r.suspended AND l.deleted_at IS NULL
            ORDER BY r.lesson_id LIMIT 1""", (uid("survey_responder"),))
    return facts


def billing_facts(cursor, tenant: str, out: dict[str, dict]) -> dict:
    """区分 04 の E2E が見比べる値（移行先の値。個人情報は含まない）。"""

    def rows(sql: str, params: tuple) -> list[dict]:
        cursor.execute(sql, params)
        return [dict(r) for r in cursor.fetchall()]

    def uid(persona: str) -> str | None:
        return out[persona]["id"] if persona in out else None

    facts: dict = {
        "payments": [r["id"] for r in rows("""SELECT id FROM payments WHERE tenant_id = %s AND application_id IS NOT NULL
            ORDER BY created_at DESC LIMIT 5""", (tenant,))],
        "rules": [r["id"] for r in rows("SELECT id FROM tag_auto_assign_rules WHERE tenant_id = %s ORDER BY id", (tenant,))],
    }
    if uid("ticket_holder"):
        facts["grants"] = rows("""SELECT id, ticket_type_id, remaining_quantity FROM ticket_grants
            WHERE user_id = %s ORDER BY id""", (uid("ticket_holder"),))
    if uid("receipt_holder"):
        facts["receipts"] = [r["id"] for r in rows("SELECT id FROM receipts WHERE user_id = %s ORDER BY id",
                                                    (uid("receipt_holder"),))]
    if uid("reserver"):
        facts["reservations"] = [r["id"] for r in rows("""SELECT r.id FROM live_reservations r
            JOIN live_lesson_occurrences o ON o.id = r.occurrence_id JOIN lessons l ON l.id = o.lesson_id
            WHERE r.user_id = %s AND l.deleted_at IS NULL ORDER BY r.id""", (uid("reserver"),))]
    if uid("path_learner"):
        facts["path_courses"] = [r["course_id"] for r in rows("""SELECT DISTINCT x.course_id FROM learning_path_enrollments e
            JOIN learning_path_courses x ON x.learning_path_id = e.learning_path_id
            JOIN enrollments n ON n.user_id = e.user_id AND n.course_id = x.course_id AND n.status = 'active'
            WHERE e.user_id = %s AND e.status = 'active' ORDER BY x.course_id""", (uid("path_learner"),))]
    return facts


def remaining_facts(cursor, tenant: str) -> dict:
    """区分 05 の残りの E2E が見比べる値（移行先の値。個人情報は含まない）。"""

    def rows(sql: str) -> list[dict]:
        cursor.execute(sql, (tenant,))
        return [dict(r) for r in cursor.fetchall()]

    return {
        # 全員向けで公開中のフォルダ（B-05。受講者なら誰でも見える）
        "open_folders": [r["id"] for r in rows("""SELECT id FROM library_folders WHERE tenant_id = %s
            AND published AND audience_type = 'all_users' ORDER BY id""")],
        "folders": [r["id"] for r in rows("SELECT id FROM library_folders WHERE tenant_id = %s ORDER BY id")],
        # 運営メモ（M-03）。著者が同じテナントの会員のもの
        "notes": rows("""SELECT n.id, n.user_id FROM admin_notes n JOIN users a ON a.id = n.author_id
            AND a.tenant_id = n.tenant_id WHERE n.tenant_id = %s ORDER BY n.id"""),
    }


def apply(cfg, env: dict[str, str], database: str, career_database: str) -> None:
    password = e2e_password(env)
    personas = json.loads(USERS_FILE.read_text())
    hashed = passwords.rehash(password)
    out: dict[str, dict] = {}
    conn = connect(with_database(cfg.target_dsn, database))
    try:
        cursor = conn.cursor()
        tenant_info = tenant_row(cursor, cfg.tenant.slug)
        tenant = tenant_info["id"]
        for persona, entry in personas.items():
            if persona not in PERSONAS:
                raise SystemExit(f"知らない役: {persona}")
            must_change, _ = PERSONAS[persona]
            user_id = int(entry["user_id"])
            cursor.execute(
                """UPDATE users SET password_hash = %s, must_change_password = %s
                   WHERE tenant_id = %s AND user_id = %s""",
                (hashed, must_change, tenant, user_id),
            )
            out[persona] = {"user_id": user_id, **describe(cursor, tenant, user_id)}
            if persona == "deleted":
                out[persona].update(legacy_identifiers(cfg.source_dsn, cfg.tenant.legacy_id, user_id))
        conn.commit()
        career_conn = connect(career_dsn(cfg, career_database))
        try:
            support = support_facts(cursor, career_conn.cursor(), tenant, out)
            content = content_facts(cursor, tenant, out)
            enrollment = enrollment_facts(cursor, tenant, out)
            billing = billing_facts(cursor, tenant, out)
            remaining = remaining_facts(cursor, tenant)
        finally:
            career_conn.close()
    finally:
        conn.close()
    document = {
        "tenant": {"slug": tenant_info["slug"], "name": tenant_info["name"]},
        "personas": out,
        "support": support,
        "content": content,
        "enrollment": enrollment,
        "billing": billing,
        "remaining": remaining,
    }
    PERSONAS_FILE.write_text(json.dumps(document, indent=2, ensure_ascii=False, default=str) + "\n")
    for persona, entry in out.items():
        print(f"  {persona}: user_id={entry['user_id']} のパスワードを入れ直した")
    print(f"{PERSONAS_FILE.relative_to(ROOT)} に E2E が使う値を書いた（コミットしない）")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["suggest", "apply"])
    parser.add_argument("--database", default="lw2_schema_check")
    parser.add_argument("--career-database", default="career_lw2_check")
    parser.add_argument("--config", default=str(config_mod.DEFAULT_CONFIG))
    args = parser.parse_args(argv)
    cfg = config_mod.load(args.config)
    env = dict(os.environ)
    check_database(args.database)
    check_career_database(args.career_database)
    {"suggest": suggest, "apply": apply}[args.command](cfg, env, args.database, args.career_database)


if __name__ == "__main__":
    main()
