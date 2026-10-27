"""support.4 問い合わせ（docs/db/05-support/migration-spec.md 0-4・0-9）のテスト。"""

from __future__ import annotations

import logging
import unittest
from dataclasses import replace
from datetime import datetime

from migrator.context import build_context
from migrator.db.target import TargetDatabase
from migrator.errors import ConfigError, MappingError
from migrator.steps.support import inquiries as iq
from tests.fakes import FakeSource
from tests.test_steps import CONFIG
from tests.test_support_announcements import TENANT

MAPPING = {"inquiry_category": {"values": {1110: "environment", 2: "other"}}}

INQUIRE = {
    "inquire_id": 20, "inquire_cate_id": 1110, "inquire_user_id": 101,
    "inquire_start_time": datetime(2024, 5, 1, 10, 0), "regist_date": datetime(2024, 5, 1, 10, 0),
    "update_date": datetime(2024, 5, 2, 10, 0), "del_chk": 0,
}


def answer(id_, inquire_id=20, detail="質問", reply="回答", end=datetime(2024, 5, 2, 9, 0), user=5, deleted=0):
    return {"inquire_answer_id": id_, "inquire_id": inquire_id, "answer_user_id": user,
            "inquire_detail": detail, "answer_detail": reply, "answer_end_time": end, "del_chk": deleted}


def ctx_with(tables: dict, mappings: dict | None = None):
    config = replace(CONFIG, mappings={**CONFIG.mappings, **(MAPPING if mappings is None else mappings)})
    ctx = build_context(config, FakeSource(tables), TargetDatabase(None, dry_run=True), logging.getLogger("test"))
    ctx.tenant_id.resolve(TENANT)
    return ctx


class CategoriesTest(unittest.TestCase):
    def test_defaults_include_other(self) -> None:
        """**`other` は必須**（無いと新しい問い合わせが 500 になる）。"""
        ctx = ctx_with({})
        step = iq.InquiryCategoriesStep()
        codes = [r.values["code"] for r in step.transform(ctx, step.extract(ctx))]
        self.assertIn("other", codes)
        self.assertEqual(len(codes), 5)

    def test_mapping_is_required_and_checked(self) -> None:
        with self.assertRaises(ConfigError):
            iq.category_map(ctx_with({}, mappings={}))
        with self.assertRaises(ConfigError):
            iq.category_map(ctx_with({}, mappings={"inquiry_category": {"values": {1: "software"}}}))


class InquiriesTest(unittest.TestCase):
    def run_step(self, tables):
        ctx = ctx_with(tables)
        step = iq.InquiriesStep()
        rows = step.extract(ctx)
        return ctx, step, rows

    def test_first_round_only_and_rest_listed(self) -> None:
        """**新は 1 往復だけ。** 2 往復目は一覧に出す。"""
        ctx, step, rows = self.run_step({
            "inquire": [INQUIRE],
            "inquire_answer": [answer(1), answer(2, detail="続きの質問", reply="続きの回答")],
        })
        self.assertEqual([v.key for v in step._take_dropped()], ["inquire_answer:2"])
        [record] = step.transform(ctx, rows)
        v = record.values
        self.assertEqual((v["question"], v["resolution"], v["status"]), ("質問", "回答", "resolved"))
        self.assertEqual(v["category_code"], "environment")
        self.assertEqual(v["assignee_id"], ctx.ulid.for_row("user", 5))
        self.assertEqual(v["resolved_at"], datetime(2024, 5, 2, 0, 0))

    def test_unanswered_is_open(self) -> None:
        ctx, step, rows = self.run_step({"inquire": [INQUIRE], "inquire_answer": [answer(1, reply="")]})
        [record] = step.transform(ctx, rows)
        self.assertEqual((record.values["status"], record.values["resolution"], record.values["assignee_id"]), ("open", None, None))

    def test_deleted_gets_deleted_at(self) -> None:
        """削除済みは `deleted_at`（新の状態に当たるものが無いので列を足した。Q1）。"""
        ctx, step, rows = self.run_step({"inquire": [{**INQUIRE, "del_chk": 1}], "inquire_answer": [answer(1)]})
        [record] = step.transform(ctx, rows)
        self.assertEqual(record.values["deleted_at"], datetime(2024, 5, 2, 1, 0))

    def test_guest_inquiry_has_no_user(self) -> None:
        """ログインしていない人は `user_id` が NULL のまま（NOT NULL に当たり一覧に出る）。"""
        ctx, step, rows = self.run_step({"inquire": [{**INQUIRE, "inquire_user_id": 0}], "inquire_answer": [answer(1)]})
        [record] = step.transform(ctx, rows)
        self.assertIsNone(record.values["user_id"])

    def test_unmapped_category_stops(self) -> None:
        with self.assertRaises(MappingError):
            self.run_step({"inquire": [{**INQUIRE, "inquire_cate_id": 999}], "inquire_answer": []})


if __name__ == "__main__":
    unittest.main()
