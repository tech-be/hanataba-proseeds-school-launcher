"""暫定対応ツールの分類のテスト。"""

from __future__ import annotations

import unittest

from fixups.exclusions import Exclusion
from fixups.plan import NONE, OVERRIDE, REVIEW, SQL, classify


def exclusion(step, reason, key, table="t", detail=""):
    return Exclusion(step=step, table=table, key=key, reason=reason, detail=detail)


class KindTest(unittest.TestCase):
    def test_not_null_is_two_words(self):
        """**`NOT NULL` は空白を含む。** 先頭の語で切ると `NOT` になってしまう。"""
        self.assertEqual(exclusion("users", "NOT NULL `email`", "1").kind, "NOT NULL")
        self.assertEqual(exclusion("users", "NOT NULL `email`", "1").column, "email")
        self.assertEqual(exclusion("t", "外部キー `user_id`", "1").kind, "外部キー")


class ClassifyTest(unittest.TestCase):
    def test_splits_by_how_to_fix(self):
        items = [
            exclusion("users", "NOT NULL `email`", "2"),
            exclusion("users", "UNIQUE `uk_tenant_email` ('tenant_id', 'email')", "5"),
            exclusion("users", "NOT NULL `role`", "911"),
            exclusion("users", "UNIQUE `uk_users_login_id` ('tenant_id', 'login_id')", "483"),
            exclusion("line_links", "UNIQUE `uk_line_links_line_user` (...)", "3394"),
        ]
        tasks = {t.kind: t for t in classify(items, live_users={"2", "5", "911", "483", "3394"})}
        self.assertEqual(tasks["email-missing"].how, OVERRIDE)
        self.assertEqual(tasks["email-missing"].column, "mail_add")
        self.assertEqual(tasks["role-missing"].column, "role_id")
        self.assertEqual(tasks["login-duplicate"].how, SQL)
        self.assertEqual(tasks["line-duplicate"].column, "line_id")

    def test_child_rows_are_cascade_when_the_member_exists(self):
        """**巻き添えは直す対象ではない。** 大本の会員を直せば消える。"""
        items = [exclusion("user_addresses", "外部キー `user_id`", "2")]
        tasks = classify(items, live_users={"2"})
        self.assertEqual(tasks[0].kind, "cascade")
        self.assertEqual(tasks[0].how, NONE)

    def test_child_rows_are_orphans_when_the_member_is_gone(self):
        """移行元に会員が居ない行は、直しようがないので削除を提案する。"""
        items = [exclusion("user_attribute_values", "外部キー `user_id`", "13")]
        tasks = classify(items, live_users={"2"})
        self.assertEqual(tasks[0].kind, "orphan-row")
        self.assertEqual(tasks[0].how, SQL)
        self.assertEqual(tasks[0].keys, ["user_attribute_values:13"])

    def test_attribute_rows_are_keyed_by_attribute_and_member(self):
        """**会員の属性の一覧のキーは「属性 ID:会員 ID」。** 会員 ID を取り出して判定する。"""
        from fixups.sql import _orphan_rows

        items = [exclusion("user_attribute_values", "外部キー `user_id`", "3:13")]
        tasks = classify(items, live_users={"2"})
        self.assertEqual(tasks[0].kind, "orphan-row")
        self.assertIn("c.user_id IN (13)", _orphan_rows(tasks[0], 10))
        self.assertEqual(classify(items, live_users={"13"})[0].kind, "cascade")

    def test_rows_keyed_by_other_ids_are_not_read_as_members(self):
        """**申込 ID などで並ぶ Step のキーを会員 ID とみなさない。** 同じ番号の会員の有無で分類が変わる。"""
        items = [exclusion("billing.assign_logs", "外部キー `user_id`", "13")]
        self.assertEqual(classify(items, live_users={"13"})[0].kind, "user-unknown")
        self.assertEqual(classify(items, live_users=set())[0].kind, "user-unknown")

    def test_member_first_keys_are_read(self):
        """「会員 ID:講座 ID」のように会員が先頭のキーも、会員で判定する。"""
        items = [exclusion("enrollment.rights", "外部キー `user_id`", "13:2001")]
        self.assertEqual(classify(items, live_users={"13"})[0].kind, "cascade")
        self.assertEqual(classify(items, live_users=set())[0].kind, "orphan-row")

    def test_non_user_foreign_key_is_not_called_a_cascade(self):
        """**数値の旧 ID でも会員とは限らない。**

        `ondemand.quizzes` の `lesson_id` は見出しユニットを指す。これを「巻き添え」に
        分類すると、**運営に「対応不要」と伝えてしまう**（実際は親をどうするか決めが要る）。
        """
        items = [exclusion("content.quizzes", "外部キー `lesson_id`", "2014")]
        tasks = classify(items, live_users={"2014"})
        self.assertEqual(tasks[0].kind, "fk-other")
        self.assertEqual(tasks[0].how, REVIEW)

    def test_other_reasons_are_not_merged_into_one_bucket(self):
        """**理由ごとに分ける。** 1つの束にすると見出しが最初の1件の理由だけになる。"""
        items = [
            exclusion("content.video_lessons", "NOT NULL `video_url`", "5"),
            exclusion("enrollment.submissions", "NOT NULL `submitted_at`", "9"),
        ]
        tasks = classify(items, live_users=set())
        self.assertEqual(len(tasks), 2)
        self.assertEqual({len(t.keys) for t in tasks}, {1})

    def test_sql_comes_first(self):
        """**機械的に直せるものから出す。** 運営に投げる前に減らせる分は減らす。"""
        items = [
            exclusion("user_addresses", "外部キー `user_id`", "2"),
            exclusion("users", "NOT NULL `email`", "3"),
            exclusion("user_attribute_values", "外部キー `user_id`", "13"),
        ]
        hows = [t.how for t in classify(items, live_users={"2", "3"})]
        self.assertEqual(hows, [SQL, OVERRIDE, NONE])


class EmailProposalTest(unittest.TestCase):
    """メールの補正の提案（2026-10-26 決定）。"""

    def test_missing_email_stays_empty(self):
        """**合成アドレスを入れない。** 新はメールを任意にしたので NULL で入る。"""
        from fixups import proposals

        value, _ = proposals.for_missing_email("101", {})
        self.assertEqual(value, "")

    def test_duplicate_keeps_the_most_recently_logged_in_member(self):
        """重複した組は、最も新しくログインした会員に残し、ほかは NULL。"""
        from datetime import datetime
        from fixups import proposals

        group = [
            {"user_id": 1, "mail_add": "a@example.test", "recent_login_date": datetime(2020, 1, 1)},
            {"user_id": 2, "mail_add": "a@example.test", "recent_login_date": datetime(2025, 1, 1)},
            {"user_id": 3, "mail_add": "a@example.test", "recent_login_date": None},
        ]
        self.assertEqual(proposals.keeper_of(group), "2")
        self.assertEqual(proposals.for_duplicate_email("2", group[1], group)[0], "")
        self.assertEqual(proposals.for_duplicate_email("1", group[0], group)[0], "NULL")
        self.assertEqual(proposals.for_duplicate_email("3", group[2], group)[0], "NULL")

    def test_tie_keeps_the_smallest_user_id(self):
        from fixups import proposals

        group = [{"user_id": 5, "recent_login_date": None}, {"user_id": 4, "recent_login_date": None}]
        self.assertEqual(proposals.keeper_of(group), "4")


class DuplicateEmailTemplateTest(unittest.TestCase):
    def test_member_inserted_first_is_in_the_group(self):
        """**投入で先に入った会員（一覧に出ない）も組に入れる。** 入れないと、残す 1 人がまた UNIQUE に当たる。"""
        import csv
        import tempfile
        from datetime import datetime
        from pathlib import Path

        from fixups import templates
        from fixups.plan import OVERRIDE, Task

        users = {
            "1": {"mail_add": "a@example.test", "del_chk": 0, "recent_login_date": datetime(2020, 1, 1)},
            "2": {"mail_add": "A@example.test", "del_chk": 0, "recent_login_date": datetime(2025, 1, 1)},
            "3": {"mail_add": "a@example.test", "del_chk": 0, "recent_login_date": None},
            "4": {"mail_add": "a@example.test", "del_chk": 1, "recent_login_date": datetime(2026, 1, 1)},
        }
        # 1 が先に入り、2・3 が一覧に出た
        task = Task("email-duplicate", "メールの重複", OVERRIDE, "", keys=["2", "3"], column="mail_add")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "overrides.csv"
            templates.build([task], users, path, propose=True)
            rows = {r["key"]: r["value"] for r in csv.DictReader(path.open(encoding="utf-8-sig"))}
        # 最も新しくログインした 2 に残し、先に入った 1 も NULL にする。削除済みの 4 は組に入れない
        self.assertEqual(rows, {"1": "NULL", "2": "", "3": "NULL"})


class CheckTest(unittest.TestCase):
    """補正データの検査（2026-10-26 のメールの規則）。"""

    def _run(self, users, values):
        from fixups import check
        from migrator.overrides import Overrides

        return {f.label.split("（")[0]: f for f in check.run(Overrides(values=values), users, 10)}

    def test_deleted_members_do_not_count_as_duplicates(self):
        """削除済みの会員はメールが NULL で入るので、重複に数えない。"""
        users = {
            "1": {"mail_add": "a@example.test", "login_id": "a", "del_chk": 0},
            "2": {"mail_add": "a@example.test", "login_id": "b", "del_chk": 1},
        }
        self.assertTrue(self._run(users, {})["上書き後にアドレスが重複していない"].ok)

    def test_duplicate_detail_does_not_show_addresses(self):
        """**アドレスは出さない**（個人情報）。"""
        users = {
            "1": {"mail_add": "a@example.test", "login_id": "a", "del_chk": 0},
            "2": {"mail_add": "A@example.test", "login_id": "b", "del_chk": 0},
        }
        finding = self._run(users, {})["上書き後にアドレスが重複していない"]
        self.assertFalse(finding.ok)
        self.assertNotIn("example.test", finding.detail)
        fixed = self._run(users, {("user", "2"): {"mail_add": None}})
        self.assertTrue(fixed["上書き後にアドレスが重複していない"].ok)

    def test_missing_email_is_fine_only_with_login_id(self):
        """メールが無くてもよい（ログイン ID でログインする）。どちらも無ければ NG。"""
        users = {"1": {"mail_add": None, "login_id": "a", "del_chk": 0}}
        self.assertTrue(self._run(users, {})["メールもログイン ID も無い会員がいない"].ok)
        users["2"] = {"mail_add": "", "login_id": "", "del_chk": 0}
        self.assertFalse(self._run(users, {})["メールもログイン ID も無い会員がいない"].ok)


class LoginIdCollisionTest(unittest.TestCase):
    def test_login_id_equal_to_another_members_email(self):
        """新はメールを先に探すので、別の会員のメールと同じログイン ID ではログインできない。"""
        from fixups.plan import login_id_collisions

        users = {
            "1": {"login_id": "taro@example.test", "mail_add": "x@example.test", "del_chk": 0},
            "2": {"login_id": "jiro", "mail_add": "Taro@Example.test", "del_chk": 0},
            "3": {"login_id": "own@example.test", "mail_add": "own@example.test", "del_chk": 0},  # 本人のメールは問題ない
            "4": {"login_id": "x@example.test", "mail_add": None, "del_chk": 1},  # 削除済みは除く
        }
        self.assertEqual(login_id_collisions(users), ["1"])
