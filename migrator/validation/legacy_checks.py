"""旧 DB との突き合わせ（`verify` の一部）。**移行ツールの変換コードを使わずに**旧 DB から数字を出し、移行先と比べる。

`reconcile`（照合）は「移行先 = 移行ツールの変換結果」を確かめる。変換の規則が間違っていれば、
間違ったまま一致する。ここでは**旧 DB に直接 SQL を投げて**、金額・件数・日付・本文が
旧の値を引き継いでいるかを見る。旧の値の意味（入金日の式など）は旧アプリの実装から写す。

- **区分ごとに持つ。** いまは課金（billing）だけ。`CHECKS` に足せば他の区分にも広げられる
- 暫定の規則で**意図して移さない**もの（0円の申込など）は、移行先に入っていないことを確かめる
- 旧データの不整合で移らないもの（会員が物理削除された申込）は、旧側の数字から除いて比べる
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from typing import Callable

#: 旧 DB への問い合わせ: (ガード用の表名, SQL, 引数) → 行。`SourceDatabase.fetch` と同じ形
Source = Callable[[str, str, tuple], list[dict]]
#: 移行先への問い合わせ: (SQL, 引数) → 行。`TargetDatabase.query` と同じ形
Target = Callable[[str, tuple], list[dict]]


@dataclass
class CheckResult:
    section: str
    name: str
    ok: bool
    detail: str = ""

    def __str__(self) -> str:
        return ("[OK] " if self.ok else "[NG] ") + self.name + (f" — {self.detail}" if self.detail else "")


def num(value) -> Decimal:
    """金額を比べる形に。`980` と `980.00` を同じにする（文字列で比べると違って見える）。"""
    return Decimal(str(value if value is not None else 0))


def same(a, b) -> bool:
    """旧と新の1値が同じか。NULL と空文字は同じ、数値は値で比べる。"""
    if a in (None, "") and b in (None, ""):
        return True
    if isinstance(a, (int, float, Decimal)) and isinstance(b, (int, float, Decimal)):
        return num(a) == num(b)
    return str(a) == str(b)


def _sample(items, n: int = 3) -> str:
    items = list(items)
    return f"{len(items)} 件（例: {items[:n]}）"


# --- 課金 ---------------------------------------------------------------------
#: 会員の行が物理削除された申込は旧データの不整合（constraint-violations 旧 #11）。旧側から除く
LIVE_USER = "EXISTS (SELECT 1 FROM user u WHERE u.user_id = a.user_id)"
#: お金が動く申込（暫定の規則 P3 / P4）
MONEY = "a.payment_type IN (1, 2, 3) AND a.application_result <> 3"
#: 入金日。**旧 `PaymentModel:110-113` の `real_payment_date` の式をそのまま写す**
REAL_PAYMENT_DATE = """DATE(IF(a.payment_type = 1,
      IF(a.credit_payment_date IS NOT NULL AND IFNULL(i.is_use_trial, 0) = 0
         AND DATE(a.credit_payment_date) != DATE(a.application_date_time),
         a.credit_payment_date, a.application_date_time),
      IF(a.payment_type = 2, a.convenience_payment_date,
         IF(a.payment_type = 3, a.bank_payment_date, a.application_date_time))))"""
STATUS = {0: "pending", 1: "succeeded", 2: "failed"}


def billing_checks(src: Source, dst: Target, legacy_tenant: int, tenant_id: str) -> list[CheckResult]:
    out: list[CheckResult] = []

    def check(name, ok, detail=""):
        out.append(CheckResult("billing", name, bool(ok), detail))

    t = (legacy_tenant,)
    d = (tenant_id,)

    # 1. 支払い方法 × 状態
    legacy = {
        (r["pt"], r["ar"]): (int(r["n"]), num(r["amt"]))
        for r in src("payment_application", f"""
            SELECT a.payment_type pt, a.application_result ar, COUNT(*) n, SUM(a.amount) amt
            FROM payment_application a WHERE a.tenant_id = %s AND {LIVE_USER} GROUP BY 1, 2""", t)
    }
    new: dict = defaultdict(lambda: [0, Decimal(0)])
    wrong_status = 0
    for r in dst("SELECT status, amount, settings FROM payments WHERE tenant_id = %s AND legacy_id IS NOT NULL", d):
        st = json.loads(r["settings"] or "{}")
        key = (st.get("legacy_payment_type"), st.get("legacy_application_result"))
        new[key][0] += 1
        new[key][1] += num(r["amount"])
        if STATUS.get(key[1]) != r["status"]:
            wrong_status += 1
    for key in sorted(set(legacy) | set(new), key=lambda k: (k[0] if k[0] is not None else -1, k[1] if k[1] is not None else -1)):
        lo = legacy.get(key, (0, Decimal(0)))
        ne = tuple(new.get(key, (0, Decimal(0))))
        skipped = key[0] not in (1, 2, 3) or key[1] == 3
        if skipped:
            check(f"支払い方法 {key[0]} / 状態 {key[1]}: 決済にしない（P3 / P4）", ne[0] == 0,
                  f"旧 {lo[0]} 件 / 新 {ne[0]} 件")
        else:
            check(f"支払い方法 {key[0]} / 状態 {key[1]}: 件数と金額",
                  lo[0] == ne[0] and lo[1] == ne[1], f"旧 {lo[0]} 件 {lo[1]} 円 / 新 {ne[0]} 件 {ne[1]} 円")
    check("決済の状態（1→succeeded / 0→pending / 2→failed）", wrong_status == 0, f"食い違い {wrong_status} 件")

    # 2. 会員ごとの支払い済み金額
    lu = {r["uid"]: num(r["amt"]) for r in src("payment_application", f"""
        SELECT a.user_id uid, SUM(a.amount) amt FROM payment_application a
        WHERE a.tenant_id = %s AND a.payment_type IN (1, 2, 3) AND a.application_result = 1 AND {LIVE_USER}
        GROUP BY 1""", t)}
    nu = {r["uid"]: num(r["amt"]) for r in dst("""
        SELECT u.legacy_id uid, SUM(p.amount) amt FROM payments p JOIN users u ON u.id = p.user_id
        WHERE p.tenant_id = %s AND p.status = 'succeeded' AND p.legacy_id IS NOT NULL GROUP BY 1""", d)}
    diff = {k: (lu.get(k), nu.get(k)) for k in set(lu) | set(nu) if lu.get(k) != nu.get(k)}
    check(f"会員ごとの支払い済み金額（{len(lu)} 名）", not diff, _sample(diff.items()) if diff else "")
    check("支払い済みの総額", sum(lu.values()) == sum(nu.values()),
          f"旧 {sum(lu.values())} 円 / 新 {sum(nu.values())} 円")

    # 3. 決済の種類（旧の商品から判定）
    kind = {}
    for r in src("payment_application", f"""
        SELECT a.application_id aid, i.item_type it, i.is_auto_extension ext,
          (SELECT COUNT(*) FROM payment_item_lesson l WHERE l.item_id = i.item_id AND l.del_chk = 0) nl
        FROM payment_application a
        JOIN payment_application_item x ON x.application_id = a.application_id
        JOIN payment_item i ON i.item_id = x.item_id
        WHERE a.tenant_id = %s AND {MONEY} AND {LIVE_USER}""", t):
        kind[r["aid"]] = ("subscription" if r["ext"] == 1
                          else "course_purchase" if r["it"] == 0 and r["nl"] == 1 else "lw2_purchase")
    nk = {r["legacy_id"]: r["type"] for r in dst(
        "SELECT legacy_id, type FROM payments WHERE tenant_id = %s AND legacy_id IS NOT NULL", d)}
    bad = [k for k in set(kind) | set(nk) if kind.get(k) != nk.get(k)]
    check(f"決済の種類（{len(kind)} 件）", not bad, _sample(bad) if bad else "")

    # 4. 領収書
    lr = {r["receipt_log_id"]: r for r in src("receipt_log", f"""
        SELECT r.receipt_log_id, r.application_id, r.receipt_price, r.receipt_name, r.receipt_provision,
               r.company_name, r.tax_rate, r.excluding_tax_price, r.invoice_no, {REAL_PAYMENT_DATE} real_date
        FROM receipt_log r
        JOIN payment_application a ON a.application_id = r.application_id
        JOIN payment_application_item x ON x.application_id = a.application_id
        JOIN payment_item i ON i.item_id = x.item_id
        WHERE r.tenant_id = %s""", t)}
    nr = {r["legacy_id"]: r for r in dst("""
        SELECT r.legacy_id, r.issue_no, r.amount, r.recipient_name, r.note, r.issuer_name, r.tax_rate,
               r.tax_excluded_amount, r.issuer_invoice_registration_no, r.transaction_date, p.legacy_id app
        FROM receipts r JOIN payments p ON p.id = r.payment_id
        WHERE r.tenant_id = %s AND r.legacy_id IS NOT NULL""", d)}
    check(f"領収書の件数（旧 {len(lr)} / 新 {len(nr)}）", set(lr) == set(nr))
    for lf, nf, label in (
        ("receipt_price", "amount", "金額"), ("receipt_name", "recipient_name", "宛名"),
        ("receipt_provision", "note", "但し書き"), ("company_name", "issuer_name", "発行者"),
        ("tax_rate", "tax_rate", "税率"), ("excluding_tax_price", "tax_excluded_amount", "税抜額"),
        ("invoice_no", "issuer_invoice_registration_no", "登録番号"), ("application_id", "app", "申込"),
        ("real_date", "transaction_date", "取引日（旧の入金日の式）"),
    ):
        bad = [(k, lr[k][lf], nr[k][nf]) for k in lr if k in nr and not same(lr[k][lf], nr[k][nf])]
        check(f"領収書の{label}", not bad, _sample(bad) if bad else "")
    order: dict = defaultdict(list)
    for k in sorted(lr):
        order[lr[k]["application_id"]].append(k)
    bad = [k for ks in order.values() for i, k in enumerate(ks, 1) if k in nr and nr[k]["issue_no"] != i]
    check("領収書の issue_no（申込ごとに旧 ID の順の連番）", not bad, _sample(bad) if bad else "")

    # 5. 商品
    li = {r["item_id"]: r for r in src("payment_item",
        "SELECT item_id, price, is_auto_extension ext FROM payment_item WHERE tenant_id = %s AND item_type = 0", t)}
    np_ = {r["legacy_id"]: r for r in dst(
        "SELECT legacy_id, price, interval_type, status FROM tenant_plans WHERE tenant_id = %s AND legacy_id IS NOT NULL", d)}
    check(f"商品の件数（旧 {len(li)} / 新 {len(np_)}）", set(li) == set(np_))
    bad = [k for k in li if k in np_ and not (
        num(li[k]["price"]) == num(np_[k]["price"])
        and (np_[k]["interval_type"] == "month") == (li[k]["ext"] == 1)
        and np_[k]["status"] == "inactive")]
    check("商品の価格（税込）・継続かどうか・販売停止", not bad, _sample(bad) if bad else "")
    lpc = {(r["item_id"], r["lesson_id"]) for r in src("payment_item_lesson", """
        SELECT l.item_id, l.lesson_id FROM payment_item_lesson l JOIN payment_item i ON i.item_id = l.item_id
        WHERE i.tenant_id = %s AND i.item_type = 0 AND l.del_chk = 0""", t)}
    npc = {(r["pid"], r["cid"]) for r in dst("""
        SELECT p.legacy_id pid, c.legacy_id cid FROM plan_courses x
        JOIN tenant_plans p ON p.id = x.plan_id JOIN courses c ON c.id = x.course_id
        WHERE x.tenant_id = %s AND p.legacy_id IS NOT NULL""", d)}
    check(f"商品と講座の組（旧 {len(lpc)} / 新 {len(npc)}）", lpc == npc,
          f"旧だけ {sorted(lpc - npc)[:3]} / 新だけ {sorted(npc - lpc)[:3]}" if lpc != npc else "")

    # 6. 受講と決済の結びつき
    auth: dict = defaultdict(set)
    for r in src("payment_item_lesson_authority", f"""
        SELECT c.user_id uid, c.lesson_id lid, a.application_id aid FROM payment_item_lesson_authority c
        JOIN user u ON u.user_id = c.user_id
        JOIN payment_application a ON a.application_id = c.application_id
        WHERE u.tenant_id = %s AND {MONEY}""", t):
        auth[(r["uid"], r["lid"])].add(r["aid"])
    links = {(r["uid"], r["cid"]): r["pp"] for r in dst("""
        SELECT u.legacy_id uid, c.legacy_id cid, e.provider_payment_id pp FROM enrollments e
        JOIN users u ON u.id = e.user_id JOIN courses c ON c.id = e.course_id
        WHERE e.tenant_id = %s AND e.provider_payment_id LIKE 'lw2-%%'""", d)}
    enrolled = {(r["uid"], r["cid"]) for r in dst("""
        SELECT u.legacy_id uid, c.legacy_id cid FROM enrollments e
        JOIN users u ON u.id = e.user_id JOIN courses c ON c.id = e.course_id WHERE e.tenant_id = %s""", d)}
    wrong = [k for k, v in links.items() if not auth.get(k) or v != f"lw2-{max(auth[k])}"]
    check(f"受講と決済の結びつき（{len(links)} 件は最も新しい申込を指す）", not wrong, _sample(wrong) if wrong else "")
    unlinked = [k for k in auth if k in enrolled and k not in links]
    check("決済のある受講はすべて結ばれている", not unlinked, _sample(unlinked) if unlinked else "")

    # 7. 規約の本文
    legal = {}
    for table, kind_name in (("agreement", "terms"), ("cancel_policy", "cancel_policy"),
                             ("privacy_policy", "privacy_policy"), ("tokusyo", "commercial_disclosure")):
        for r in src(table, f"SELECT `{table}` body, language_code FROM `{table}` WHERE tenant_id = %s", t):
            if (r["body"] or "").strip():
                legal[(kind_name, (r["language_code"] or "ja").strip())] = r["body"].strip()
    nl = {(r["kind"], r["language_code"]): r["body"] for r in dst(
        "SELECT kind, language_code, body FROM tenant_legal_documents WHERE tenant_id = %s AND body IS NOT NULL", d)}
    check(f"規約の本文（{sorted(legal)}）", legal == nl,
          f"旧 {sorted(legal)} / 新 {sorted(nl)}" if legal != nl else "")

    # 8. チケットの残高（種別あり・1枚以上。#14 / #15 は移さない）
    lt = {(r["uid"], r["tid"]): int(r["n"]) for r in src("user_ticket", """
        SELECT c.user_id uid, c.ticket_id tid, SUM(c.ticket_num) n FROM user_ticket c
        JOIN user u ON u.user_id = c.user_id
        WHERE u.tenant_id = %s AND c.ticket_id IS NOT NULL AND c.ticket_num >= 1 GROUP BY 1, 2""", t)}
    nt = {(r["uid"], r["tid"]): int(r["n"]) for r in dst("""
        SELECT u.legacy_id uid, t.legacy_id tid, SUM(g.remaining_quantity) n FROM ticket_grants g
        JOIN users u ON u.id = g.user_id JOIN ticket_types t ON t.id = g.ticket_type_id
        WHERE g.tenant_id = %s GROUP BY 1, 2""", d)}
    check(f"チケットの残枚数（会員 × 種別 {len(lt)} 組）", lt == nt, f"旧 {lt} / 新 {nt}" if lt != nt else "")

    # 9. 台帳: 席を占める予約 × チケットが要るライブ × 使える残高
    ledger = src("live_lesson_reserve", """
        SELECT COUNT(*) n, SUM(l.item_ticket_price) cost FROM live_lesson_reserve r
        JOIN live_lesson_date dt ON dt.live_lesson_date_id = r.live_lesson_date_id
        JOIN live_lesson l ON l.live_lesson_id = dt.live_lesson_id
        WHERE l.tenant_id = %s AND l.item_ticket_price > 0
          AND COALESCE(r.stop_chk, 0) = 0 AND COALESCE(r.cancel_chk, 0) = 0
          AND EXISTS (SELECT 1 FROM ticket_limit_lesson tl WHERE tl.live_lesson_id = l.live_lesson_id AND tl.del_chk = 0
                      AND EXISTS (SELECT 1 FROM user_ticket g WHERE g.user_id = r.user_id
                                  AND g.ticket_id = tl.ticket_id AND g.ticket_num >= 1))""", t)[0]
    nled = dst("SELECT COUNT(*) n, -SUM(quantity_delta) cost FROM ticket_ledger_entries WHERE tenant_id = %s", d)[0]
    check("チケットの台帳（行数と枚数）",
          int(ledger["n"] or 0) == int(nled["n"] or 0) and num(ledger["cost"]) == num(nled["cost"]),
          f"旧 {ledger['n']} 件 {ledger['cost'] or 0} 枚 / 新 {nled['n']} 行 {nled['cost'] or 0} 枚")
    return out


#: 区分 → 突き合わせ。**いまは課金だけ**
CHECKS: dict[str, Callable[[Source, Target, int, str], list[CheckResult]]] = {
    "billing": billing_checks,
}


def run(ctx, sections: set[str]) -> list[CheckResult]:
    """選んだ区分の突き合わせを流す。旧 DB と移行先の両方に接続が要る。"""
    if ctx.target.connectionless or ctx.source is None:
        return []
    source = ctx.require_source()
    results: list[CheckResult] = []
    for section in sorted(sections & set(CHECKS)):
        results += CHECKS[section](
            lambda table, sql, params: source.fetch(table, sql, params),
            lambda sql, params: ctx.target.query(sql, params),
            ctx.config.tenant.legacy_id,
            ctx.tenant_id.value,
        )
    return results
