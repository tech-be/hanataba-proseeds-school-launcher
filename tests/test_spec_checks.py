"""テスト仕様のデータの確認（`verify` の一部）のテスト。

**確認が「通った」と言ってしまう誤り**を中心に固定する。ケースごとに、外れた行があれば NG になること。
"""

from __future__ import annotations

import json
import unittest

from migrator.validation import legacy_checks as lc
from migrator.validation import spec_checks as sc
from tests.test_legacy_checks import fake


def run(dst_rows: dict, src_rows: dict | None = None, excluded: dict | None = None):
    base = {"SELECT slug, status, settings FROM tenants": [
        {"slug": "recademy", "status": "active", "settings": json.dumps({})}]}
    src, dst = fake(src_rows or {}, {**base, **dst_rows})
    return {r.name: r for r in sc.foundation_spec(lc.Env(src, dst, 10, "T", excluded=excluded))}


def ng(results) -> list[str]:
    return sorted(name for name, r in results.items() if not r.ok)


class FoundationSpecTest(unittest.TestCase):
    def test_everything_empty_passes_except_personal_numbers(self) -> None:
        """何も無ければ、個別番号が無いことだけが NG（移した会員がいれば番号もある）。"""
        self.assertEqual(ng(run({})), ["F-53 個別番号がある"])

    def test_deleted_member_with_email_is_ng(self) -> None:
        results = run({"status = 'deleted' AND email IS NOT NULL": [{"n": 1}]})
        self.assertFalse(results["F-22 削除済みの会員のメールは NULL"].ok)

    def test_mobile_optouts_are_ng(self) -> None:
        """**携帯の受け取り設定が移行先にあれば NG**（新は channel を見ず、PC も止まって見える）。"""
        results = run({"channel = 'mobile'": [{"n": 3}]})
        self.assertFalse(results["F-51 携帯の受け取り設定は移さず一覧に出す"].ok)

    def test_deleted_tags_are_ng(self) -> None:
        results = run({"FROM user_tags WHERE tenant_id = %s AND deleted_at IS NOT NULL": [{"n": 1}]})
        self.assertFalse(results["F-60 削除済みの印のタグが無い（削除済みの属性は移さない）"].ok)

    def test_synthetic_email_is_ng(self) -> None:
        results = run({"@lw2.invalid": [{"n": 2}]})
        self.assertFalse(results["F-12 メールに空文字・合成アドレスが無く、一意"].ok)

    def test_member_who_could_not_log_in_must_not_be_active(self) -> None:
        """旧で利用終了日を過ぎた会員が active なら NG（新は status だけでログインを決める）。"""
        from datetime import date

        src = {"FROM user WHERE tenant_id": [{"user_id": 7, "del_chk": 0, "valid_chk": 1, "is_lockout": 0,
                                              "entry_date": date(2018, 4, 1), "limit_date": date(2019, 3, 31)}]}
        results = run({"SELECT user_id, status FROM users": [{"user_id": 7, "status": "active"}]}, src)
        self.assertFalse(results["F-15 旧でログインできなかった会員は active でない"].ok)
        results = run({"SELECT user_id, status FROM users": [{"user_id": 7, "status": "inactive"}]}, src)
        self.assertTrue(results["F-15 旧でログインできなかった会員は active でない"].ok)

    def test_line_kind_not_selectable_is_ng(self) -> None:
        """**新で選べない通知の種類が残っていると、運営は LINE の設定を保存できない**（400）。"""
        settings = {"line": {"enabled": False, "notification_kinds": ["announcement"], "official_account_id": "@x"}}
        results = run({"SELECT slug, status, settings FROM tenants": [
            {"slug": "recademy", "status": "active", "settings": json.dumps(settings)}]})
        self.assertFalse(results["F-55 LINE の設定が新の検証を通る形"].ok)

    def test_next_personal_number_uses_the_legacy_format(self) -> None:
        """次の番号は旧の形（旧のテナント ID ＋ 0 ＋ 連番）。既存の番号と重なれば NG。"""
        numbers = {"FROM user_personal_numbers n JOIN tenants t": [{"legacy": 10, "mx": 3155, "bad": 0}]}
        self.assertIn("1003156", run(numbers)["F-53 個別番号の表示の種類が正しく、次の採番が既存の番号と重ならない"].detail)
        clash = {**numbers, "personal_no = %s": [{"n": 1}]}
        self.assertFalse(run(clash)["F-53 個別番号の表示の種類が正しく、次の採番が既存の番号と重ならない"].ok)



def run_support(dst_rows: dict, career_rows: dict | None = None):
    src, dst = fake({}, dst_rows)
    career = None
    if career_rows is not None:
        _, career = fake({}, career_rows)
    env = lc.Env(src, dst, 10, "T", career=career)
    return {r.name: r for r in sc.support_spec(env)}


class SupportSpecTest(unittest.TestCase):
    def test_empty_passes_when_career_connected(self) -> None:
        results = run_support({"code = 'other'": [{"n": 1}]}, career_rows={})
        self.assertEqual(ng(results), [])

    def test_career_not_connected_is_ng(self) -> None:
        """**career の DB に繋がずに通ったことにしない。**"""
        results = run_support({"code = 'other'": [{"n": 1}]})
        self.assertIn("S-60〜S-66 career の DB に接続している", ng(results))

    def test_html_body_is_ng_only_when_legacy_had_real_tags(self) -> None:
        """本文の HTML は補正データでプレーンテキストに直す（Q2）。**旧で文字として見えていた `<` は除く。**"""
        name = "S-05 本文に HTML のタグが残っていない（補正データでプレーンテキストに直す）"

        def results(legacy_body):
            src, dst = fake({"FROM news": [{"k": 15, "b": legacy_body}]},
                            {"code = 'other'": [{"n": 1}], "REGEXP": [{"id": "news:15"}]})
            _, career = fake({}, {})
            return {r.name: r for r in sc.support_spec(lc.Env(src, dst, 10, "T", career=career))}

        self.assertFalse(results("<strong>太字</strong>")[name].ok)
        self.assertTrue(results("&lt;strong&gt; と書く")[name].ok)

    def test_mail_template_with_legacy_or_unknown_placeholder_is_ng(self) -> None:
        name = "S-20 メールの件名・本文が新の検証の範囲で、差し込みはその種別で値が入るものだけ"
        for body in ("{USER_NAME} 様", "{{user_name}} {{reset_link}}"):
            rows = {"code = 'other'": [{"n": 1}],
                    "FROM tenant_email_templates": [{"kind": "welcome", "subject": "件名", "body": body}]}
            self.assertFalse(run_support(rows, career_rows={})[name].ok, body)
        rows = {"code = 'other'": [{"n": 1}],
                "FROM tenant_email_templates": [{"kind": "welcome", "subject": "件名", "body": "{{user_name}} {{login_url}}"}]}
        self.assertTrue(run_support(rows, career_rows={})[name].ok)

    def test_unknown_employment_status_is_ng(self) -> None:
        """**一覧外の就業状況が 1 件でもあると、その会員は就活プロフィールを保存できない。**"""
        profile = {"user_id": "U1", "learner_name": "山田", "employment_status": "1", "education": None,
                   "job_category": None, "qualification": None, "desired_prefecture": None}
        results = run_support({"code = 'other'": [{"n": 1}], "FROM users WHERE": [{"id": "U1"}]},
                              career_rows={"FROM learner_career_profiles": [profile]})
        self.assertFalse(results["S-60 就活プロフィールが新の検証の範囲（就業状況・字数・名前）"].ok)


class ContentSpecTest(unittest.TestCase):
    def test_empty_passes(self) -> None:
        src, dst = fake({}, {})
        results = {r.name: r for r in sc.content_spec(lc.Env(src, dst, 10, "T"))}
        self.assertEqual(ng(results), [])

    def test_unsupported_lesson_type_is_ng(self) -> None:
        """**新が扱えない種別のレッスンは NG**（本文が出ず、編集で 400）。"""
        src, dst = fake({}, {"type NOT IN ('video', 'live', 'text', 'survey')": [{"n": 3}]})
        results = {r.name: r for r in sc.content_spec(lc.Env(src, dst, 10, "T"))}
        self.assertFalse(results["L-01 レッスンの種別は video / live / text / survey だけ"].ok)


def run_enrollment(dst_rows: dict, src_rows: dict | None = None):
    src, dst = fake(src_rows or {}, dst_rows)
    return {r.name: r for r in sc.enrollment_spec(lc.Env(src, dst, 10, "T", ulid=lambda ns, k: f"{ns}:{k}"))}


class EnrollmentSpecTest(unittest.TestCase):
    E02 = "E-02 旧の修了日がある受講登録に completed_at がある（無いものに入っていない）"

    def test_empty_passes(self) -> None:
        self.assertEqual(ng(run_enrollment({})), [])

    def test_missing_completion_is_ng(self) -> None:
        """**旧の修了日がある組に completed_at が無ければ NG**（新の修了・修了証が出ない）。"""
        src = {"lesson_complete_date IS NOT NULL": [{"user_id": 1, "lesson_id": 2}]}
        enr = {"e.completed_at IS NOT NULL done": [{"uid": 1, "cid": 2, "done": 0}]}
        self.assertFalse(run_enrollment(enr, src)[self.E02].ok)
        enr = {"e.completed_at IS NOT NULL done": [{"uid": 1, "cid": 2, "done": 1}]}
        self.assertTrue(run_enrollment(enr, src)[self.E02].ok)

    def test_host_canceled_is_ng(self) -> None:
        src, dst = fake({}, {"status = 'host_canceled'": [{"n": 1}]})
        results = {r.name: r for r in sc.billing_spec(lc.Env(src, dst, 10, "T"))}
        self.assertFalse(results["V-01（03）予約の状態に host_canceled を使わない"].ok)

    def test_billing_empty_passes(self) -> None:
        src, dst = fake({}, {})
        results = {r.name: r for r in sc.billing_spec(lc.Env(src, dst, 10, "T"))}
        self.assertEqual(ng(results), [])

    def test_pending_payment_is_ng(self) -> None:
        """**移した決済の pending は NG**（新の照合が全テナントで古い順に 100 件しか見ない）。"""
        src, dst = fake({}, {"AND p.status = 'pending'": [{"n": 3}]})
        results = {r.name: r for r in sc.billing_spec(lc.Env(src, dst, 10, "T"))}
        self.assertFalse(results["P-02 移した決済に pending が無い（照合の枠を埋めない・入金確認の一覧に出ない）"].ok)

    def test_ticket_usable_mismatch_is_ng(self) -> None:
        """旧で使えない（権限の期限切れ）専用チケットが新で使えれば NG（T-02）。"""
        src, dst = fake({}, {"SUM(g.remaining_quantity) n FROM ticket_grants": [{"uid": 7, "tid": 1, "n": 3}]})
        results = {r.name: r for r in sc.billing_spec(lc.Env(src, dst, 10, "T"))}
        self.assertFalse(results["T-02 会員 × 種別の使える枚数が旧と同じ（専用チケット）"].ok)

    def test_reviewed_status_is_ng(self) -> None:
        results = run_enrollment({"FROM submissions WHERE tenant_id = %s AND status NOT IN": [{"n": 2}]})
        self.assertFalse(results["A-01 提出の状態・添削の結果が新の値"].ok)


if __name__ == "__main__":
    unittest.main()
