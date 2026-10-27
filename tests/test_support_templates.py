"""support.9 自動メールの文面と、本文の直しの提案（fixups text）のテスト。

docs/db/05-support/migration-spec.md 0-3・0-9（Q2・Q7・Q8）。
"""

from __future__ import annotations

import csv
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from fixups import text
from migrator.overrides import Overrides
from migrator.steps.support import templates as tp
from tests.test_support_announcements import ctx_with


def mail(id_, type_id, title="件名", body="{USER_NAME} 様", lang="ja", deleted=0):
    return {"mail_setting_id": id_, "mail_type_id": type_id, "title": title, "body": body,
            "language_code": lang, "regist_date": datetime(2024, 1, 1), "update_date": datetime(2024, 1, 1),
            "del_chk": deleted}


class MailTemplatesTest(unittest.TestCase):
    def test_only_kinds_with_a_new_place_are_migrated(self) -> None:
        rows = [
            mail(1, 20, body="{{user_name}} 様"),  # 採る（welcome）
            mail(2, 35, body="{{user_name}}"),  # 同じ welcome だが採らない（Q7）
            mail(3, 1, lang="en"),  # 英語
            mail(4, 9),  # 新に種別が無い
            mail(5, 13, body="{USER_NAME} 様 {URL}"),  # 旧の差し込みが残る
        ]
        ctx = ctx_with({"mail_setting": rows})
        step = tp.MailTemplatesStep()
        kept = step.extract(ctx)
        self.assertEqual([r["mail_setting_id"] for r in kept], [1])
        dropped = {v.key: v.reason for v in step._take_dropped()}
        self.assertEqual(sorted(dropped), ["mail_setting:2", "mail_setting:3", "mail_setting:4", "mail_setting:5"])
        self.assertEqual(dropped["mail_setting:4"], "受け皿なし")
        [record] = step.transform(ctx, kept)
        self.assertEqual((record.values["kind"], record.values["enabled"]), ("welcome", True))

    def test_deleted_is_disabled(self) -> None:
        ctx = ctx_with({})
        [record] = tp.MailTemplatesStep().transform(ctx, [mail(1, 20, body="x", deleted=1)])
        self.assertFalse(record.values["enabled"])

    def test_line_template_of_sns_signup_goes_to_welcome(self) -> None:
        """LINE の文面は種類 35 にしか無いので welcome に入れる（R3）。"""
        rows = [{"mail_type_id": 35, "message": "{{user_name}} さん", "regist_date": datetime(2024, 1, 1)}]
        ctx = ctx_with({"line_message_mail_setting": rows})
        step = tp.LineTemplatesStep()
        [record] = step.transform(ctx, step.extract(ctx))
        self.assertEqual(record.values["kind"], "welcome")


class TextProposalTest(unittest.TestCase):
    def test_plain_text(self) -> None:
        html = "<p>こんにちは<br>受講者の皆さま</p><ul><li>一つ目</li><li>二つ目</li></ul>&amp; 以上&nbsp;"
        self.assertEqual(text.plain_text(html), "こんにちは\n受講者の皆さま\n・一つ目\n・二つ目\n& 以上")
        self.assertFalse(text.has_html("ただの文"))

    def test_only_html_bodies_are_proposed(self) -> None:
        rows = [{"news_id": 1, "news_detail": "<b>太字</b>"}, {"news_id": 2, "news_detail": "そのまま"}]
        self.assertEqual(
            [(t, k, c, v) for t, k, c, v, _ in text.propose_bodies(rows, "news", "news_id", "news_detail")],
            [("news", "1", "news_detail", "太字")],
        )

    def test_placeholders_are_rewritten_by_kind(self) -> None:
        new, unresolved = text.rewrite_placeholders("{USER_NAME} 様 {SERVICE_NAME} {URL}", "welcome")
        self.assertEqual((new, unresolved), ("{{user_name}} 様 {{tenant_name}} {{login_url}}", []))
        # **新に当たるものが無い差し込みは残し、名前を返す**
        new, unresolved = text.rewrite_placeholders("{LOGIN_ID} / {PASSWORD}", "welcome")
        self.assertEqual(unresolved, ["LOGIN_ID", "PASSWORD"])

    def test_unresolved_mail_is_left_blank(self) -> None:
        """**新に当たる差し込みが無い文面は提案しない**（空欄。運営に文面を決めてもらう）。"""
        rows = [mail(1, 20, body="{USER_NAME} {PASSWORD}"), mail(2, 13, body="{USER_NAME} {REMINDER_URL}")]
        proposals = {(r[1], r[2]): r[3] for r in text.propose_mail(rows)}
        self.assertEqual(proposals[("1", "body")], "")
        self.assertEqual(proposals[("2", "body")], "{{user_name}} {{reset_link}}")

    def test_long_multiline_value_round_trips(self) -> None:
        """補正データの 1 値に複数行の長い本文が入る（F3）。"""
        body = "1 行目\n\n" + "長い本文。" * 1500
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "overrides.csv"
            with path.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(["table", "key", "column", "value", "memo"])
                writer.writerow(["news", "187", "news_detail", body, "Q2"])
            overrides = Overrides.load(path)
        rows = [{"news_id": 187, "news_detail": "<p>元</p>"}]
        overrides.apply("news", rows)
        self.assertEqual(rows[0]["news_detail"], body)


if __name__ == "__main__":
    unittest.main()
