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
