"""コンテンツ（区分 02）の値の直しの提案（`fixups text` の一部）。docs/db/02-content/migration-spec.md 0-3。

**移行ツールは値を作り替えない。** ここで提案し、補正データ（`overrides.csv`）に入れたものを移行ツールが読む。

| 対象 | 提案 | 決定 |
|---|---|---|
| テストの合格点（`test.pass_score`） | 点 → 割合: `floor(合格点 × 100 ÷ 旧の満点)`（03 の Q9 で `ceil` から変えた）。0 と、満点が 100 のものは同じ値なので出さない。合格点 > 満点（旧でも合格できない）は**空欄** | Q9 |
| 問題文・解説（`question`） | HTML をプレーンテキストに（画像のタグは除く。画像は L9 の移送と一緒に決める） | Q12 |
| アンケートの設問（`enquete_question`） | 必須の添付の設問を任意に、同じ設問の重複した選択肢に「（2）」 | Q13 |
| コース（`payment_item`） | 公開中で公開する講座が無いコースを無効に、期間が 120 か月を超えるものを無期限に | Q15 |
"""

from __future__ import annotations

import re

from .text import has_html, plain_text

FILE_UPLOAD = 4
MAX_MONTHS = 120
#: 旧 `manual_term_type` → 月に直す掛け数（日・週は月にしない）
TERM_MONTHS = {2: 1, 3: 12}
_IMG = re.compile(r"<\s*img[^>]*>", re.IGNORECASE)


# --- 合格点（Q9） ---------------------------------------------------------------
def legacy_max_score(subs: list[dict], fixed_counts: dict[int, int], ranged_counts: dict[int, int]) -> int:
    """旧の満点。出題条件ごとに「実際に出る問題の数 × 配点」を足す。

    - 固定出題（0）… 先頭の N 問（N が 0 なら全問）
    - 固定問題からランダム（1）… N 問（問題が N より少なければその数）
    - カテゴリからランダム（2）… N 問（候補が N より少なければその数）
    """
    total = 0
    for sub in subs:
        sub_type = int(sub.get("test_sub_type_id") or 0)
        n = int(sub.get("set_question_no") or 0)
        available = (fixed_counts if sub_type in (0, 1) else ranged_counts).get(int(sub["test_sub_id"]), 0)
        asked = min(n, available) if n > 0 else available
        total += asked * int(sub.get("score_per_question") or 0)
    return total


def pass_percent(pass_score: int, max_score: int) -> int | None:
    """合格点（点）を割合にする。**旧でも合格できない（合格点 > 満点）・満点 0 は None**（直さない）。

    **端数は切り捨て。** 新は `得点 × 100 ÷ 満点 ≥ 合格点（割合）` で判定する。切り上げると、ちょうど合格点の
    得点が端数で届かず不合格になる（例: 満点 3・合格点 2 → 67% だが得点 2 は 66.7%）。切り捨てなら、満点が
    100 点以下のとき旧の「合格点以上で合格」と必ず同じ判定になる（03 移行仕様 0-2 Q9。旧の受験と比べて
    食い違いが 10 件 → 6 件）。
    """
    if max_score <= 0 or pass_score > max_score:
        return None
    return pass_score * 100 // max_score  # 整数で割る（浮動小数の誤差で 1 下がらない）


def propose_pass_scores(tests: list[dict], subs_of: dict[int, list[dict]], fixed: dict[int, int],
                        ranged: dict[int, int]) -> list[tuple]:
    out = []
    for test in tests:
        score = int(test.get("pass_score") or 0)
        if score == 0:
            continue  # 0 は割合でも 0（常に合格）
        maximum = legacy_max_score(subs_of.get(int(test["test_id"]), []), fixed, ranged)
        if maximum == 100:
            continue  # 点と割合が同じ
        percent = pass_percent(score, maximum)
        if percent is None:
            out.append(("test", str(test["test_id"]), "pass_score", "",
                        f"合格点 {score} 点が旧の満点 {maximum} 点を超える（旧でも合格できない）。値を決めて value に書く"))
        else:
            out.append(("test", str(test["test_id"]), "pass_score", str(percent),
                        f"合格点 {score} 点 / 満点 {maximum} 点 → {percent}%（新は割合。Q9）"))
    return out


# --- 問題文・解説の HTML（Q12） ------------------------------------------------
def propose_question_text(questions: list[dict]) -> list[tuple]:
    out = []
    for q in questions:
        for column in ("question_text", "answer_explanation"):
            text = q.get(column) or ""
            if has_html(text):
                plain = plain_text(_IMG.sub("", text))
                out.append(("question", str(q["question_id"]), column, plain,
                            "HTML をプレーンテキストに直した（画像のタグは除いた。Q12）"))
    return out


# --- アンケート（Q13） --------------------------------------------------------
def propose_enquete(questions: list[dict]) -> list[tuple]:
    out = []
    for q in questions:
        key = str(q["enquete_question_id"])
        if int(q.get("question_type") or 0) == FILE_UPLOAD and int(q.get("required_chk") or 0):
            out.append(("enquete_question", key, "required_chk", "0",
                        "必須の添付の設問。新は添付の入力欄が無く、必須だと送信できない（Q13）"))
        seen: dict[str, int] = {}
        for n in range(1, int(q.get("selection_num") or 0) + 1):
            label = q.get(f"selection{n}")
            if label is None or not str(label).strip():
                continue  # 空の選択肢は新でも選択肢を作らない（重なりに数えない）
            count = seen.get(label, 0) + 1
            seen[label] = count
            if count > 1:
                out.append(("enquete_question", key, f"selection{n}", f"{label}（{count}）",
                            "同じ設問の選択肢が重なる。新は重複を保存で弾く（Q13）"))
    return out


# --- コース（Q15） ------------------------------------------------------------
def propose_items(items: list[dict], alive_course_counts: dict[int, int]) -> list[tuple]:
    out = []
    for item in items:
        key = str(item["item_id"])
        if int(item.get("del_chk") or 0):
            continue
        listed = int(item.get("valid_chk") or 0) == 1 and int(item.get("display_chk") or 0) == 1
        if listed and alive_course_counts.get(int(item["item_id"]), 0) == 0:
            out.append(("payment_item", key, "valid_chk", "0",
                        "公開中だが、販売中の講座を 1 件も含まない（新では中身の無いコースになる。Q15）"))
        kind = item.get("manual_term_type")
        months = int(item.get("manual_term") or 0) * TERM_MONTHS.get(int(kind), 0) if kind is not None else 0
        if not int(item.get("no_limit_chk") or 0) and months > MAX_MONTHS:
            out.append(("payment_item", key, "no_limit_chk", "1",
                        f"期間が {months} か月で新の上限 {MAX_MONTHS} か月を超える（一覧の API 全体が 500 になる）。無期限にする（Q15）"))
    return out


# --- 旧 DB から集める ---------------------------------------------------------
def collect(connection, tenant_id: int) -> list[tuple]:
    """旧 DB を読み、02 の提案をまとめて返す。**読むだけ。**"""
    from migrator.db.source import SourceDatabase

    cursor = connection.cursor()

    def rows(sql: str, params: tuple = ()) -> list[dict]:
        cursor.execute(sql, params)
        return [dict(r) for r in cursor.fetchall()]

    shared = sorted(SourceDatabase(connection, tenant_id).shared_lessons)
    marks = ", ".join(["%s"] * len(shared)) or "NULL"
    scope = f"(l.tenant_id = %s OR l.lesson_id IN ({marks}))"
    params = (tenant_id, *shared)

    tests = rows(f"""SELECT t.test_id, t.pass_score FROM test t JOIN unit u ON u.unit_id = t.unit_id
        JOIN lesson l ON l.lesson_id = u.lesson_id WHERE {scope} AND u.unit_type_id = 2""", params)
    subs = rows(f"""SELECT s.test_sub_id, s.test_id, s.test_sub_type_id, s.set_question_no, s.score_per_question,
        s.question_cate_id, s.question_level_id FROM test_sub s JOIN test t ON t.test_id = s.test_id
        JOIN unit u ON u.unit_id = t.unit_id JOIN lesson l ON l.lesson_id = u.lesson_id WHERE {scope}""", params)
    subs_of: dict[int, list[dict]] = {}
    for sub in subs:
        subs_of.setdefault(int(sub["test_id"]), []).append(sub)
    fixed = {int(r["k"]): int(r["n"]) for r in rows(f"""SELECT q.test_sub_id k, COUNT(*) n FROM test_sub_question q
        JOIN question qq ON qq.question_id = q.question_id JOIN test_sub s ON s.test_sub_id = q.test_sub_id
        JOIN test t ON t.test_id = s.test_id JOIN unit u ON u.unit_id = t.unit_id
        JOIN lesson l ON l.lesson_id = u.lesson_id WHERE {scope} GROUP BY q.test_sub_id""", params)}
    ranged = {int(r["k"]): int(r["n"]) for r in rows(f"""SELECT s.test_sub_id k, COUNT(*) n FROM test_sub s
        JOIN question q ON q.question_cate_id = s.question_cate_id AND q.del_chk = 0 AND q.tenant_id IN (%s, 0)
        AND (s.question_level_id IS NULL OR s.question_level_id = 0 OR q.question_level_id = s.question_level_id)
        JOIN test t ON t.test_id = s.test_id JOIN unit u ON u.unit_id = t.unit_id
        JOIN lesson l ON l.lesson_id = u.lesson_id WHERE s.test_sub_type_id = 2 AND {scope}
        GROUP BY s.test_sub_id""", (tenant_id, *params))}

    # 問題文・解説: このテナントで出題に使われうる問題（固定の設問と、カテゴリの範囲）
    used = rows(f"""SELECT DISTINCT qq.question_id, qq.question_text, qq.answer_explanation FROM question qq
        WHERE qq.tenant_id IN (%s, 0) AND (qq.question_id IN (
            SELECT q.question_id FROM test_sub_question q JOIN test_sub s ON s.test_sub_id = q.test_sub_id
            JOIN test t ON t.test_id = s.test_id JOIN unit u ON u.unit_id = t.unit_id
            JOIN lesson l ON l.lesson_id = u.lesson_id WHERE {scope})
          OR qq.question_cate_id IN (
            SELECT s.question_cate_id FROM test_sub s JOIN test t ON t.test_id = s.test_id
            JOIN unit u ON u.unit_id = t.unit_id JOIN lesson l ON l.lesson_id = u.lesson_id
            WHERE s.test_sub_type_id = 2 AND {scope}))""", (tenant_id, *params, *params))

    selection = ", ".join(f"q.selection{n}" for n in range(1, 21))
    enquete = rows(f"""SELECT q.enquete_question_id, q.question_type, q.required_chk, q.selection_num, {selection}
        FROM enquete_question q JOIN enquete_page p ON p.enquete_page_id = q.enquete_page_id
        JOIN enquete e ON e.enquete_id = p.enquete_id WHERE e.tenant_id IN (%s, 0) AND q.del_chk = 0
        AND e.enquete_id IN (SELECT u.enquete_id FROM unit u JOIN lesson l ON l.lesson_id = u.lesson_id
            WHERE {scope} AND u.unit_type_id = 3)""", (tenant_id, *params))

    items = rows("""SELECT item_id, valid_chk, display_chk, del_chk, manual_term_type, manual_term, no_limit_chk
        FROM payment_item WHERE tenant_id = %s AND item_type = 0""", (tenant_id,))
    alive = {int(r["k"]): int(r["n"]) for r in rows("""SELECT pil.item_id k, COUNT(*) n FROM payment_item_lesson pil
        JOIN payment_item pi ON pi.item_id = pil.item_id JOIN lesson l ON l.lesson_id = pil.lesson_id
        WHERE pi.tenant_id = %s AND pil.del_chk = 0 AND l.del_chk = 0 AND l.sales_status = 1
        GROUP BY pil.item_id""", (tenant_id,))}

    return (propose_pass_scores(tests, subs_of, fixed, ranged) + propose_question_text(used)
            + propose_enquete(enquete) + propose_items(items, alive))
