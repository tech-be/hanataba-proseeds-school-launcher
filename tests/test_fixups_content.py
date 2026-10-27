"""コンテンツ（区分 02）の値の直しの提案のテスト（docs/db/02-content/migration-spec.md 0-3）。"""

from __future__ import annotations

import unittest

from fixups import content


def sub(sid, sub_type, n, score, test_id=1):
    return {"test_sub_id": sid, "test_id": test_id, "test_sub_type_id": sub_type, "set_question_no": n,
            "score_per_question": score}


class PassScoreTest(unittest.TestCase):
    def test_legacy_max_score_counts_questions_actually_asked(self) -> None:
        subs = [sub(1, 0, 2, 10), sub(2, 1, 3, 5), sub(3, 2, 20, 2)]
        # 固定 2 問（5 問中）× 10、ランダム 3 問（10 問中）× 5、カテゴリ 20 問（候補 8 問しかない）× 2
        self.assertEqual(content.legacy_max_score(subs, {1: 5, 2: 10}, {3: 8}), 20 + 15 + 16)

    def test_pass_percent(self) -> None:
        """**旧は点、新は割合**（Q9）。端数は切り捨て（03 の Q9。ちょうど合格点の得点を合格にする）。"""
        self.assertEqual(content.pass_percent(60, 200), 30)
        self.assertEqual(content.pass_percent(7, 9), 77)
        # 満点 3・合格点 2: 得点 2 は 66.7%。切り上げ（67）だと不合格になる
        self.assertEqual(content.pass_percent(2, 3), 66)
        self.assertGreaterEqual(2 * 100 / 3, content.pass_percent(2, 3))
        self.assertIsNone(content.pass_percent(300, 200))  # 旧でも合格できない

    def test_proposals_skip_zero_and_full_hundred(self) -> None:
        tests = [{"test_id": 1, "pass_score": 0}, {"test_id": 2, "pass_score": 80},
                 {"test_id": 3, "pass_score": 60}, {"test_id": 4, "pass_score": 500}]
        subs_of = {2: [sub(1, 0, 10, 10, 2)], 3: [sub(2, 0, 10, 20, 3)], 4: [sub(3, 0, 10, 20, 4)]}
        out = {r[1]: r[3] for r in content.propose_pass_scores(tests, subs_of, {1: 10, 2: 10, 3: 10}, {})}
        self.assertEqual(out, {"3": "30", "4": ""})  # 1 は 0、2 は満点 100 なので出さない


class TextAndSurveyTest(unittest.TestCase):
    def test_question_html_drops_images(self) -> None:
        rows = [{"question_id": 1, "question_text": "<p>問題<img src='a.png'></p>", "answer_explanation": "説明"}]
        self.assertEqual(content.propose_question_text(rows), [
            ("question", "1", "question_text", "問題", "HTML をプレーンテキストに直した（画像のタグは除いた。Q12）")])

    def test_enquete_required_upload_and_duplicate_labels(self) -> None:
        rows = [{"enquete_question_id": 5, "question_type": 4, "required_chk": 1, "selection_num": 0},
                {"enquete_question_id": 6, "question_type": 1, "required_chk": 1, "selection_num": 4,
                 "selection1": "はい", "selection2": "はい", "selection3": "", "selection4": ""}]
        out = [(r[1], r[2], r[3]) for r in content.propose_enquete(rows)]
        self.assertEqual(out, [("5", "required_chk", "0"), ("6", "selection2", "はい（2）")])


class ItemTest(unittest.TestCase):
    def test_empty_listed_course_and_long_period(self) -> None:
        items = [
            {"item_id": 1, "valid_chk": 1, "display_chk": 1, "del_chk": 0, "manual_term_type": 2, "manual_term": 6},
            {"item_id": 2, "valid_chk": 1, "display_chk": 1, "del_chk": 0, "manual_term_type": 3, "manual_term": 30},
        ]
        out = [(r[1], r[2], r[3]) for r in content.propose_items(items, {2: 3})]
        # 1 は販売中の講座が 0 件、2 は 360 か月で上限超え
        self.assertEqual(out, [("1", "valid_chk", "0"), ("2", "no_limit_chk", "1")])


if __name__ == "__main__":
    unittest.main()
