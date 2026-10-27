"""サポート（区分 05 の残り）の見直しのテスト（docs/db/05-support/migration-spec.md 0R-2、rework-gap-remaining.md）。"""

from __future__ import annotations

import unittest
from datetime import date, datetime

from migrator.steps import user_related
from migrator.steps.support import career
from tests.test_billing import make_ctx

LINE_ID = "U" + "a" * 32


def member(**over):
    row = {"user_id": 7, "line_id": LINE_ID, "regist_date": datetime(2020, 1, 1), "del_chk": 0, "valid_chk": 1,
           "entry_date": date(2019, 4, 1), "limit_date": None, "is_lockout": 0}
    row.update(over)
    return row


class LineLinksTest(unittest.TestCase):
    def _run(self, rows):
        ctx = make_ctx({"user": rows})
        step = user_related.LineLinksStep()
        return step, step.transform(ctx, step.extract(ctx))

    def test_malformed_id_is_listed(self) -> None:
        """**形の違う ID は黙って落とさず一覧に出す**（Q1）。"""
        step, recs = self._run([member(line_id="line-xyz")])
        self.assertEqual(recs, [])
        [dropped] = step._take_dropped()
        self.assertEqual((dropped.table, dropped.reason), ("line_links", "旧データの不整合"))

    def test_inactive_member_is_not_a_friend(self) -> None:
        """**有効でない会員には送らない**（新は会員の状態を見ずに送る。Q3）。"""
        _, [active] = self._run([member()])
        _, [deleted] = self._run([member(del_chk=1)])
        _, [expired] = self._run([member(limit_date=date(2020, 1, 1))])
        self.assertTrue(active.values["is_friend"])
        self.assertFalse(deleted.values["is_friend"])
        self.assertFalse(expired.values["is_friend"])

    def test_whitespace_is_trimmed(self) -> None:
        _, [rec] = self._run([member(line_id=f" {LINE_ID} ")])
        self.assertEqual(rec.values["line_user_id"], LINE_ID)


class AdviceNotesTest(unittest.TestCase):
    def test_deleted_note_is_listed(self) -> None:
        """**削除済みの運営メモは移さない**（新は deleted_at を読まず表示する。Q6）。"""
        row = {"personal_record_advice_id": 1, "user_id": 3, "target_user_id": 9, "advice_memo": "m",
               "update_user_id": 0, "del_chk": 1, "regist_date": datetime(2024, 4, 10),
               "update_date": datetime(2024, 4, 11)}
        ctx = make_ctx({"personal_record_advice": [row, {**row, "personal_record_advice_id": 2, "del_chk": 0}]})
        step = career.AdviceNotesStep()
        [rec] = step.transform(ctx, step.extract(ctx))
        self.assertNotIn("deleted_at", rec.values)
        [dropped] = step._take_dropped()
        self.assertEqual((dropped.table, dropped.reason), ("admin_notes", "受け皿なし"))


if __name__ == "__main__":
    unittest.main()
