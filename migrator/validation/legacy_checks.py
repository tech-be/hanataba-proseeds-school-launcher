"""旧 DB との突き合わせ（`verify` の一部）。**移行ツールの変換コードを使わずに**旧 DB から数字を出し、移行先と比べる。

`reconcile`（照合）は「移行先 = 移行ツールの変換結果」を確かめる。変換の規則が間違っていれば、
間違ったまま一致する。ここでは**旧 DB に直接 SQL を投げて**、金額・件数・日付・本文が
旧の値を引き継いでいるかを見る。旧の値の意味（入金日の式など）は旧アプリの実装から写す。

- **区分ごとに持つ**（基盤・コンテンツ・受講・課金）。`CHECKS` に足せば他の区分にも広げられる
- **行の漏れ・紛れ:** 旧の対象の行が移行先に無いときは、同じ `verify` で「制約に当たって移さない」と
  一覧に出たもの（`ExclusionLog.keys`）だけを許す。**どこにも出ずに消えた行**と、旧の対象に無い行を NG にする
- **値:** 取り違えると気づかないまま誤データになるもの（名前・金額・得点・日数・種別・状態）に絞る
- 暫定の規則で**意図して移さない**もの（0円の申込など）は、移行先に入っていないことを確かめる
- 旧データの不整合で移らないもの（会員が物理削除された申込）は、旧側の数字から除いて比べる
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
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


@dataclass
class Env:
    """突き合わせに渡すもの。**移行ツールの変換コードは渡さない。**

    `ulid` は旧キー → 新 ID の対応（設定で決まる採番規則。変換の規則ではない）。
    旧 ID の列を持たない表を引き当てるのに使う。
    """

    src: Source
    dst: Target
    legacy_tenant: int
    tenant_id: str
    ulid: Callable[[str, object], str] = lambda ns, key: f"{ns}:{key}"
    #: 表 → その実行で「制約に当たって移さない」と一覧に出た旧キー
    excluded: dict[str, set[str]] | None = None
    #: 旧 role_id → 新 users.role（設定の対応表）
    roles: dict[int, str] | None = None
    #: career の DB（別の DB）。support の区分だけが使う。接続が無ければ None
    career: Target | None = None

    def skipped(self, table: str) -> set[str]:
        return (self.excluded or {}).get(table, set())


class Checker:
    def __init__(self, section: str) -> None:
        self.section = section
        self.results: list[CheckResult] = []

    def __call__(self, name: str, ok, detail: str = "") -> None:
        self.results.append(CheckResult(self.section, name, bool(ok), detail))

    def coverage(self, name: str, legacy: dict, new: set, skipped: set[str]) -> None:
        """**漏れと紛れ。** `legacy` は 新キー → 旧キー（一覧の目印）。

        旧にあって新に無い行は、一覧に出ていれば説明がつく（制約に当たって移さない）。
        一覧にも無いものは**黙って消えた行**として NG。新にだけある行も NG。
        """
        missing = [old for key, old in legacy.items() if key not in new]
        silent = [old for old in missing if str(old) not in skipped]
        stray = [key for key in new if key not in legacy]
        self(f"{name}: 漏れ", not silent,
             f"旧 {len(legacy)} / 新 {len(new) - len(stray)} / 移さない（一覧にあり）{len(missing) - len(silent)}"
             + (f" / **一覧に無い欠け** {_sample(silent)}" if silent else ""))
        self(f"{name}: 紛れ", not stray, _sample(stray) if stray else "")

    def values(self, name: str, pairs: list[tuple]) -> None:
        """旧と新の値の組（キー, 旧, 新）が同じか。"""
        bad = [(k, a, b) for k, a, b in pairs if not same(a, b)]
        self(name, not bad, _sample(bad) if bad else f"{len(pairs)} 件")


def _n_or_0(rows) -> int:
    return int(rows[0]["n"]) if rows else 0


def _in(values) -> tuple[str, tuple]:
    values = tuple(values)
    return (", ".join(["%s"] * len(values)) or "NULL"), values


# --- 基盤 ---------------------------------------------------------------------
def foundation_checks(env: Env) -> list[CheckResult]:
    c = Checker("foundation")
    t, d = (env.legacy_tenant,), (env.tenant_id,)

    old = env.src("tenant", "SELECT tenant_name, tenent_name_short, language_code FROM tenant WHERE tenant_id = %s", t)
    new = env.dst("SELECT name, short_name, language_code FROM tenants WHERE id = %s", d)
    if old and new:
        c.values("テナントの名前・略称・言語", [
            ("name", (old[0]["tenant_name"] or "").strip(), new[0]["name"]),
            ("short_name", old[0]["tenent_name_short"], new[0]["short_name"]),
            ("language_code", old[0]["language_code"] or "ja", new[0]["language_code"]),
        ])
    else:
        c("テナントがある", False, f"旧 {len(old)} / 新 {len(new)}")

    # 会員
    lu = {r["user_id"]: r for r in env.src("user", """
        SELECT user_id, login_id, role_id, name_sei, name_mei, kana_sei, kana_mei, mail_add, tel,
               birth_date, del_chk, valid_chk, entry_date, limit_date, is_lockout
        FROM user WHERE tenant_id = %s""", t)}
    nu = {r["user_id"]: r for r in env.dst("""
        SELECT user_id, login_id, role, name_last, name_first, name_kana_last, name_kana_first,
               email, phone, birth_year, birth_month, birth_day, status, must_change_password
        FROM users WHERE tenant_id = %s AND user_id IS NOT NULL""", d)}
    c.coverage("会員", {k: k for k in lu}, set(nu), env.skipped("users"))
    both = [k for k in lu if k in nu]
    names = (("name_sei", "name_last"), ("name_mei", "name_first"),
             ("kana_sei", "name_kana_last"), ("kana_mei", "name_kana_first"))
    c.values("会員の名前・カナ", [(k, lu[k][old], nu[k][new]) for k in both for old, new in names])
    c.values("会員のメール・ログインID・電話", [
        (k, a, b) for k in both for a, b in (
            # 削除済みの会員のメールは NULL（2026-10-26 決定）
            (None if int(lu[k]["del_chk"] or 0) == 1 else (lu[k]["mail_add"] or "").strip() or None, nu[k]["email"]),
            # 削除済みの会員は login_id を NULL で入れる（2026-10-02 決定）
            (None if int(lu[k]["del_chk"] or 0) == 1 else lu[k]["login_id"], nu[k]["login_id"]),
            (lu[k]["tel"], nu[k]["phone"]))])
    c.values("移した会員はパスワードの変更を求める（must_change_password）",
             [(k, 1, int(nu[k]["must_change_password"])) for k in both])
    c.values("会員の生年月日（年・月・日の3列）", [
        (k, _ymd(lu[k]["birth_date"]), (nu[k]["birth_year"], nu[k]["birth_month"], nu[k]["birth_day"]))
        for k in both])
    if env.roles:
        c.values("会員のロール（設定の対応表）", [
            (k, env.roles.get(int(lu[k]["role_id"])) if lu[k]["role_id"] is not None else None, nu[k]["role"])
            for k in both])
    # 旧でログインできない会員（ロックアウト中・利用開始日が空か未来・利用終了日を過ぎた）も inactive
    # （旧 AuthModel.class.php:149-154。2026-10-26 決定）。判定の日は照合を流した日（日本時間）
    today = _today_jst()
    c.values("会員の状態（削除 → deleted / 無効・旧でログインできない → inactive）", [
        (k, "deleted" if int(lu[k]["del_chk"] or 0) == 1
         else "inactive" if (int(lu[k]["valid_chk"] if lu[k]["valid_chk"] is not None else 1) == 0
                             or not _legacy_can_log_in(lu[k], today))
         else "active", nu[k]["status"]) for k in both])

    # 会員の個別番号（旧 scout_display_type は 0 名前 / 1 ニックネーム / 2 個別番号）
    lp = {r["user_id"]: r for r in env.src("user_personal_no", """
        SELECT p.user_id, p.regist_no, p.personal_no, p.scout_display_type
        FROM user_personal_no p JOIN user u ON u.user_id = p.user_id WHERE u.tenant_id = %s""", t)}
    np_ = {r["user_id"]: r for r in env.dst("""
        SELECT u.user_id, n.regist_no, n.personal_no, n.scout_display_type
        FROM user_personal_numbers n JOIN users u ON u.id = n.user_id WHERE n.tenant_id = %s""", d)}
    c.coverage("会員の個別番号", {k: k for k in lp}, set(np_), env.skipped("user_personal_numbers"))
    display = {0: "name", 1: "nickname", 2: "personal_no"}
    c.values("会員の個別番号・登録番号・スカウトでの名前の出し方", [
        (k, a, b) for k in lp if k in np_ for a, b in (
            (lp[k]["regist_no"], np_[k]["regist_no"]),
            (None if lp[k]["personal_no"] is None else str(lp[k]["personal_no"]), np_[k]["personal_no"]),
            (display.get(int(lp[k]["scout_display_type"])) if lp[k]["scout_display_type"] is not None
             else None, np_[k]["scout_display_type"]))])

    # LINE 連携の設定（チャネル ID は settings、シークレットは tenant_secrets。値は長さだけ比べる）
    ol = env.src("application_config", """
        SELECT line_chk, line_id, line_channel_id, CHAR_LENGTH(TRIM(line_channel_sercret)) secret_len
        FROM application_config WHERE tenant_id = %s""", t)
    if ol:
        st = env.dst("SELECT settings FROM tenants WHERE id = %s", d)
        line = (json.loads(st[0]["settings"] or "{}") if st else {}).get("line") or {}
        sl = env.dst("""SELECT CHAR_LENGTH(value) n FROM tenant_secrets
            WHERE tenant_id = %s AND kind = 'line_login_channel_secret'""", d)
        c.values("LINE 連携の設定（有効・公式アカウント・ログインチャネル）", [
            ("enabled", int(int(ol[0]["line_chk"] or 0) == 1), int(bool(line.get("enabled")))),
            ("official_account_id", ol[0]["line_id"], line.get("official_account_id")),
            ("login_channel_id", ol[0]["line_channel_id"], line.get("login_channel_id")),
            ("login_channel_secret の長さ", ol[0]["secret_len"] or None, sl[0]["n"] if sl else None),
        ])

    # グループと所属
    lg = {r["group_id"] for r in env.src("group", "SELECT group_id FROM `group` WHERE tenant_id = %s", t)}
    ng = {r["group_id"] for r in env.dst(
        "SELECT group_id FROM tenant_groups WHERE tenant_id = %s AND group_id IS NOT NULL", d)}
    c.coverage("グループ", {k: k for k in lg}, ng, env.skipped("tenant_groups"))
    lm = {(r["group_id"], r["user_id"]): r["user_id"] for r in env.src("user_group", """
        SELECT ug.group_id, ug.user_id FROM user_group ug JOIN `group` g ON g.group_id = ug.group_id
        JOIN user u ON u.user_id = ug.user_id WHERE g.tenant_id = %s""", t)}
    nm = {(r["gid"], r["uid"]) for r in env.dst("""
        SELECT g.group_id gid, u.user_id uid FROM tenant_group_members m
        JOIN tenant_groups g ON g.id = m.group_id JOIN users u ON u.id = m.user_id
        WHERE g.tenant_id = %s""", d)}
    c.coverage("グループの所属", lm, nm, env.skipped("tenant_group_members"))

    # 属性 → タグ。**削除済みの属性は移さない**（一覧に「移行対象外」。2026-10-26 決定）
    la = {r["attribute_id"]: r for r in env.src("attribute",
        "SELECT attribute_id, attribute_name, del_chk FROM attribute WHERE tenant_id = %s", t)}
    ntd = {r["attribute_id"]: r["deleted"] for r in env.dst(
        "SELECT attribute_id, deleted_at IS NOT NULL deleted FROM user_tags WHERE tenant_id = %s AND attribute_id IS NOT NULL", d)}
    c.coverage("タグ（旧の属性。削除済みは一覧に出る）", {k: k for k in la}, set(ntd), env.skipped("user_tags"))
    c("タグに削除済みの印の行が無い（削除済みの属性は移さない）", not any(ntd.values()),
      _sample([k for k, v in ntd.items() if v]) if any(ntd.values()) else "")
    lav = {(r["attribute_id"], r["user_id"]): f"{r['attribute_id']}:{r['user_id']}" for r in env.src("user_attribute", """
        SELECT ua.attribute_id, ua.user_id FROM user_attribute ua JOIN attribute a ON a.attribute_id = ua.attribute_id
        WHERE a.tenant_id = %s""", t)}
    nav = {(r["aid"], r["uid"]) for r in env.dst("""
        SELECT g.attribute_id aid, u.user_id uid FROM user_tag_assignments m
        JOIN user_tags g ON g.id = m.tag_id JOIN users u ON u.id = m.user_id
        WHERE m.tenant_id = %s""", d)}
    c.coverage("タグの割当（旧の会員の属性。削除済みの属性の割当は一覧に出る）", lav, nav, env.skipped("user_tag_assignments"))
    return c.results


def _today_jst():
    from datetime import datetime, timedelta, timezone
    return datetime.now(timezone(timedelta(hours=9))).date()


def _legacy_can_log_in(row: dict, today) -> bool:
    """旧でログインできるか。**旧 `AuthModel.class.php:149-154` の条件をそのまま写す**（移行ツールのコードは使わない）。"""
    from datetime import datetime as _dt

    def day(v):
        if v is None or (isinstance(v, str) and v.startswith("0000-00-00")):
            return None
        return v.date() if isinstance(v, _dt) else v
    if int(row.get("is_lockout") or 0) == 1:
        return False
    entry, limit = day(row.get("entry_date")), day(row.get("limit_date"))
    return entry is not None and entry <= today and (limit is None or limit >= today)


def _ymd(value):
    if value is None:
        return (None, None, None)
    v = value.date() if hasattr(value, "date") and callable(value.date) else value
    return (v.year, v.month, v.day)


# --- コンテンツ -----------------------------------------------------------------
#: 旧 `unit.unit_type_id` → 新 `lessons.type`。**02 の仕様書（A20）の決定**。0 見出し・5 集合研修は移さない
UNIT_TYPE = {1: "video", 2: "quiz", 3: "survey", 4: "assignment", 6: "document",
             7: "discussion", 8: "skill_check"}


def content_checks(env: Env) -> list[CheckResult]:
    c = Checker("content")
    t, d = (env.legacy_tenant,), (env.tenant_id,)

    # 講座: 自テナントの講座は全部。共有（tenant_id = 0）は移したものが旧に実在すること
    own = {r["lesson_id"]: r for r in env.src("lesson",
        "SELECT lesson_id, name, open_period, lesson_cate_id, sales_status, del_chk FROM lesson WHERE tenant_id = %s", t)}
    nc = {r["legacy_lesson_id"]: r for r in env.dst(
        "SELECT legacy_lesson_id, title, access_days, status FROM courses WHERE tenant_id = %s AND legacy_lesson_id IS NOT NULL", d)}
    shared_ids = [k for k in nc if k not in own]
    marks, ids = _in(shared_ids)
    shared = {r["lesson_id"]: r for r in env.src("lesson",
        f"SELECT lesson_id, name, open_period, lesson_cate_id, sales_status, del_chk FROM lesson WHERE tenant_id = 0 AND lesson_id IN ({marks})", ids)} \
        if shared_ids else {}
    c.coverage("講座（自テナント）", {k: k for k in own}, set(nc) - set(shared), env.skipped("courses"))
    c("講座（共有）: 移したものは旧の共有講座に実在する", set(shared_ids) == set(shared),
      _sample(set(shared_ids) - set(shared)) if set(shared_ids) != set(shared) else f"{len(shared)} 件")
    lessons = {**own, **shared}
    both = [k for k in nc if k in lessons]
    c.values("講座名", [(k, (lessons[k]["name"] or "").strip(), nc[k]["title"]) for k in both])
    c.values("受講日数（旧は月。× 30 日、0 は無期限）", [
        (k, int(lessons[k]["open_period"]) * 30 if int(lessons[k]["open_period"] or 0) > 0 else None,
         nc[k]["access_days"]) for k in both])
    # 販売停止は archived（2026-10-22。新は講座の下書きをやめた）。削除も archived（2026-10-26）
    c.values("講座の状態（販売中 → published / 販売停止・削除 → archived）", [
        (k, "archived" if int(lessons[k]["del_chk"] or 0) == 1
         else "published" if int(lessons[k]["sales_status"] or 0) == 1 else "archived", nc[k]["status"])
        for k in both])

    # 講座のカテゴリ（テナントごと。2026-10-22）。旧に実在する分類を持つ講座が、その分類に結ばれている
    cates = {r["lesson_cate_id"]: r["lesson_cate_name"] for r in env.src("lesson_cate",
        "SELECT lesson_cate_id, lesson_cate_name FROM lesson_cate WHERE tenant_id IN (%s, 0)", t)}
    want = [k for k in both if lessons[k]["lesson_cate_id"] and lessons[k]["lesson_cate_id"] in cates]
    ncat = {r["lid"]: r for r in env.dst("""
        SELECT co.legacy_lesson_id lid, tc.id cat_id, tc.name FROM course_category_links l
        JOIN courses co ON co.id = l.course_id JOIN tenant_course_categories tc ON tc.id = l.category_id
        WHERE l.tenant_id = %s""", d)}
    c.coverage("講座のカテゴリの結び付き（テナントのカテゴリ）", {k: k for k in want}, set(ncat),
               env.skipped("course_category_links"))
    c.values("講座のカテゴリ（どの分類か・名前）", [
        (k, (env.ulid("tenant_course_category", lessons[k]["lesson_cate_id"]),
             (cates[lessons[k]["lesson_cate_id"]] or "").strip()),
         (ncat[k]["cat_id"], ncat[k]["name"])) for k in want if k in ncat])

    # ユニット（ライブ以外）: 移した講座のユニットのうち、見出し・集合研修以外
    marks, ids = _in(nc)
    lu = {r["unit_id"]: r for r in env.src("unit", f"""
        SELECT u.unit_id, u.title, u.unit_type_id, u.del_chk FROM unit u JOIN lesson l ON l.lesson_id = u.lesson_id
        WHERE (l.tenant_id = %s OR l.lesson_id IN ({marks})) AND u.unit_type_id NOT IN (0, 5)""", t + ids)}
    nl = {r["unit_id"]: r for r in env.dst("""
        SELECT unit_id, title, type, deleted_at IS NOT NULL deleted FROM lessons
        WHERE tenant_id = %s AND unit_id IS NOT NULL AND type <> 'live'""", d)}
    c.coverage("ユニット", {k: k for k in lu}, set(nl), env.skipped("lessons"))
    both = [k for k in lu if k in nl]
    c.values("ユニット名", [(k, lu[k]["title"], nl[k]["title"]) for k in both])
    # 種別（2026-10-26 決定。02 の移行仕様 0-3 の Q2・Q6）: アンケートは survey、講義は再生できる
    # 動画（video_lessons の行がある）なら video・それ以外は text、ほかの旧の種別は text
    with_video = {r["unit_id"] for r in env.dst("""
        SELECT l.unit_id FROM video_lessons v JOIN lessons l ON l.id = v.lesson_id WHERE l.tenant_id = %s""", d)}

    def expected_type(k):
        legacy = int(lu[k]["unit_type_id"])
        if legacy == 3:
            return "survey"
        if legacy == 1:
            return "video" if k in with_video else "text"
        return "text"

    c.values("ユニットの種別（新が扱える 4 種）", [(k, expected_type(k), nl[k]["type"]) for k in both])
    # 新アプリはレッスンを deleted_at IS NULL で絞る（school-launcher 20261021082002）
    c.values("ユニットの削除済み（lessons.deleted_at）",
             [(k, int(int(lu[k]["del_chk"] or 0) == 1), int(nl[k]["deleted"])) for k in both])
    # 動画の置き場所。p-movie（旗とトークン）かどうかだけを旧から直接比べる
    pm = {r["unit_id"]: int(r["pm"]) for r in env.src("lecture", f"""
        SELECT le.unit_id, (le.pmovie_chk = 1 AND TRIM(COALESCE(le.pmovie_token, '')) <> '') pm
        FROM lecture le JOIN unit u ON u.unit_id = le.unit_id JOIN lesson l ON l.lesson_id = u.lesson_id
        WHERE (l.tenant_id = %s OR l.lesson_id IN ({marks})) AND u.unit_type_id = 1""", t + ids)}
    nv = {r["unit_id"]: r["video_source"] for r in env.dst("""
        SELECT l.unit_id, v.video_source FROM video_lessons v JOIN lessons l ON l.id = v.lesson_id
        WHERE l.tenant_id = %s""", d)}
    c.values("動画の置き場所（p-movie は pmovie）",
             [(k, pm[k], int(nv[k] == "pmovie")) for k in nv if k in pm])
    # 旧で p-movie の講義は、新でも動画（video）として移る（旧の値だけで決まる）
    c.values("p-movie の講義は video", [(k, "video", nl[k]["type"]) for k in both if pm.get(k)])

    # 見出し → 講座の章（削除済みも移す。2026-10-01）
    heads = {r["unit_id"]: r for r in env.src("unit", f"""
        SELECT u.unit_id, u.title, u.del_chk FROM unit u JOIN lesson l ON l.lesson_id = u.lesson_id
        WHERE (l.tenant_id = %s OR l.lesson_id IN ({marks})) AND u.unit_type_id = 0""", t + ids)}
    nchr = {r["unit_id"]: r for r in env.dst(
        "SELECT unit_id, title, deleted_at IS NOT NULL deleted FROM course_chapters WHERE tenant_id = %s AND unit_id IS NOT NULL", d)}
    nch = {k: v["title"] for k, v in nchr.items()}
    c.coverage("講座の章（旧の見出し。削除済みを含む）", {k: k for k in heads}, set(nch), env.skipped("course_chapters"))
    c.values("章の名前", [(k, (heads[k]["title"] or "").strip(), nch[k]) for k in heads if k in nch])
    c.values("章の削除済み", [(k, int(int(heads[k]["del_chk"] or 0) == 1), int(nchr[k]["deleted"]))
                         for k in heads if k in nchr])
    # ユニットの所属: 旧の講座ページと同じ規則で求めた章と、新の chapter_id。
    # **移行ツールの判定（chapter_of）は使わない。** 旧の並び（UnitModel::_buildSql の既定
    # `ORDER BY U.sort_no ASC, U.unit_id ASC`）を SQL でそのまま使い、直前の削除されていない見出しにまとめる
    expected: dict = {}
    current: dict = {}
    for r in env.src("unit", f"""
        SELECT u.unit_id, u.lesson_id, u.unit_type_id, u.del_chk FROM unit u
        JOIN lesson l ON l.lesson_id = u.lesson_id WHERE l.tenant_id = %s OR l.lesson_id IN ({marks})
        ORDER BY u.lesson_id, u.sort_no, u.unit_id""", t + ids):
        if int(r["unit_type_id"]) == 0:
            if int(r["del_chk"] or 0) == 0:
                current[r["lesson_id"]] = r["unit_id"]  # 削除済みの見出しは画面に出ないので区切りにしない
        else:
            expected[r["unit_id"]] = current.get(r["lesson_id"])
    nbelong = {r["unit_id"]: r["chapter"] for r in env.dst("""
        SELECT l.unit_id, ch.unit_id chapter FROM lessons l LEFT JOIN course_chapters ch ON ch.id = l.chapter_id
        WHERE l.tenant_id = %s AND l.unit_id IS NOT NULL AND l.type <> 'live'""", d)}
    c.values("ユニットの章（見出しの後ろのユニットがその章に入る）",
             [(k, expected.get(k), nbelong[k]) for k in nbelong if k in expected])

    # アンケートのユニットには定義（survey_lessons）が要る。**定義が無いと回答も入らない**
    surveys = {k for k, v in lu.items() if int(v["unit_type_id"]) == 3}
    marks_s, sids = _in(surveys)
    with_enquete = {r["unit_id"] for r in env.src("unit", f"""
        SELECT u.unit_id FROM unit u JOIN lesson l ON l.lesson_id = u.lesson_id
        WHERE l.tenant_id IN (%s, 0) AND u.unit_id IN ({marks_s}) AND u.enquete_id > 0""", t + sids)} if surveys else set()
    ns = {r["unit_id"] for r in env.dst("""
        SELECT l.unit_id FROM survey_lessons s JOIN lessons l ON l.id = s.lesson_id WHERE l.tenant_id = %s""", d)}
    c.coverage("アンケートの定義（アンケートを持つユニット）", {k: k for k in with_enquete}, ns, env.skipped("survey_lessons"))

    # テスト・課題（移したユニットに付くもの）
    marks_u, units = _in(nl)
    tests = {env.ulid("test", r["test_id"]): r["test_id"] for r in env.src("test",
        f"SELECT t.test_id FROM test t JOIN unit u ON u.unit_id = t.unit_id JOIN lesson l ON l.lesson_id = u.lesson_id "
        f"WHERE l.tenant_id IN (%s, 0) AND t.unit_id IN ({marks_u})", t + units)} if nl else {}
    nq = {r["id"] for r in env.dst("SELECT id FROM quizzes WHERE tenant_id = %s", d)}
    c.coverage("テスト", tests, nq, env.skipped("quizzes"))
    reports = {env.ulid("report", r["report_id"]): r["report_id"] for r in env.src("report",
        f"SELECT r.report_id FROM report r JOIN unit u ON u.unit_id = r.unit_id JOIN lesson l ON l.lesson_id = u.lesson_id "
        f"WHERE l.tenant_id IN (%s, 0) AND r.unit_id IN ({marks_u})", t + units)} if nl else {}
    na = {r["id"] for r in env.dst("SELECT id FROM assignments WHERE tenant_id = %s", d)}
    c.coverage("課題", reports, na, env.skipped("assignments"))

    # 設問の数（2026-10-26。02 の移行仕様 0-3 の Q8・Q10）: 移したテストの「固定出題の問題すべて
    # ＋ カテゴリからのランダム出題（type 2）の候補すべて」= 新 + 移さない（先頭の N 問より後ろ・
    # 採点できない設問は一覧に出る）
    nq_ids = {v for k, v in tests.items() if k in nq}
    marks_t, test_ids = _in(nq_ids)
    fixed = env.src("test_sub_question", f"""
        SELECT s.test_sub_type_id st, s.set_question_no n, COUNT(*) c FROM test_sub_question q
        JOIN test_sub s ON s.test_sub_id = q.test_sub_id JOIN question qq ON qq.question_id = q.question_id
        WHERE s.test_sub_type_id IN (0, 1) AND s.test_id IN ({marks_t}) AND qq.tenant_id IN (%s, 0)
        GROUP BY s.test_sub_id, s.test_sub_type_id, s.set_question_no""", test_ids + t) if nq_ids else []
    ranged = env.src("question", f"""
        SELECT COUNT(*) c FROM test_sub s JOIN question q ON q.question_cate_id = s.question_cate_id
        AND (s.question_level_id IS NULL OR s.question_level_id = 0 OR q.question_level_id = s.question_level_id)
        WHERE s.test_sub_type_id = 2 AND s.del_chk = 0 AND s.test_id IN ({marks_t}) AND q.tenant_id IN (%s, 0) AND q.del_chk = 0
        GROUP BY s.test_sub_id""", test_ids + t) if nq_ids else []
    legacy_n = sum(int(r["c"]) for r in fixed) + sum(int(r["c"]) for r in ranged)
    nqq = env.dst("SELECT COUNT(*) n FROM quiz_questions WHERE tenant_id = %s", d)[0]["n"]
    skipped = len(env.skipped("quiz_questions"))
    c("テストの設問の数（旧で出うる設問 = 新 + 移さない）", legacy_n == int(nqq) + skipped,
      f"旧 {legacy_n} / 新 {nqq} / 移さない {skipped}")
    empty = _n_or_0(env.dst("""SELECT COUNT(*) n FROM quizzes z WHERE z.tenant_id = %s
        AND NOT EXISTS (SELECT 1 FROM quiz_questions q WHERE q.quiz_id = z.id)""", d))
    c("移したテストはすべて設問を持つ", empty == 0, f"{empty} 件")

    # ライブと開催回
    # **ライブ由来のレッスンは旧 ID（unit_id）を持たない**（02 の A27。ユニットと採番系が違い衝突する）。ID で引く
    lives = {env.ulid("live_lesson", r["live_lesson_id"]): r["live_lesson_id"] for r in env.src(
        "live_lesson", "SELECT live_lesson_id FROM live_lesson WHERE tenant_id = %s", t)}
    nlive = {r["id"] for r in env.dst("SELECT id FROM lessons WHERE tenant_id = %s AND type = 'live'", d)}
    c.coverage("ライブ", lives, nlive, env.skipped("lessons"))
    dates = {env.ulid("live_lesson_date", r["live_lesson_date_id"]): r["live_lesson_date_id"] for r in env.src(
        "live_lesson_date", """SELECT dt.live_lesson_date_id FROM live_lesson_date dt
        JOIN live_lesson l ON l.live_lesson_id = dt.live_lesson_id WHERE l.tenant_id = %s""", t)}
    nd = {r["id"] for r in env.dst("SELECT id FROM live_lesson_occurrences WHERE tenant_id = %s", d)}
    c.coverage("ライブの開催回", dates, nd, env.skipped("live_lesson_occurrences"))
    # 除外日の全行（旧の形のまま。削除済み・保存のたびに積んだ行を含む）
    ln = env.src("live_lesson_exclusion_date",
                 "SELECT COUNT(*) n FROM live_lesson_exclusion_date WHERE tenant_id = %s", t)
    nn = env.dst("SELECT COUNT(*) n FROM live_lesson_exclusion_date_history WHERE tenant_id = %s", d)
    ln, nn = (int(ln[0]["n"]) if ln else 0), (int(nn[0]["n"]) if nn else 0)
    c(f"live_lesson_exclusion_date の全行（削除済みを含む。旧 {ln} / 新 {nn}）", ln == nn)
    # ライブごとの予約の期限（2026-10-22。旧もライブごとの日数）
    lpol = {env.ulid("live_lesson", r["live_lesson_id"]): r for r in env.src("live_lesson", """
        SELECT live_lesson_id, reserve_start_day, reserve_end_day, reserve_end_time
        FROM live_lesson WHERE tenant_id = %s""", t)}
    npol = {r["lesson_id"]: r for r in env.dst("""
        SELECT lesson_id, reserve_open_days_before, reserve_close_days_before, reserve_close_hours_before
        FROM live_lesson_reservation_policies WHERE tenant_id = %s""", d)}
    c.coverage("ライブの予約の期限", {k: v["live_lesson_id"] for k, v in lpol.items()}, set(npol),
               env.skipped("live_lesson_reservation_policies"))
    c.values("ライブの予約の期限（開始・締め切りの日数・時間）", [
        (lpol[k]["live_lesson_id"], (lpol[k]["reserve_start_day"], lpol[k]["reserve_end_day"], lpol[k]["reserve_end_time"]),
         (npol[k]["reserve_open_days_before"], npol[k]["reserve_close_days_before"], npol[k]["reserve_close_hours_before"]))
        for k in lpol if k in npol])

    # コース（旧の講座の販売商品。2026-10-22）
    li = {env.ulid("learning_path", r["item_id"]): r for r in env.src("payment_item", """
        SELECT item_id, item_name, price, valid_chk, display_chk, remote_chk, del_chk
        FROM payment_item WHERE tenant_id = %s AND item_type = 0""", t)}
    ni = {r["id"]: r for r in env.dst("""
        SELECT id, title, price, status, listed, remote_pc_enabled FROM learning_paths WHERE tenant_id = %s""", d)}
    c.coverage("コース（旧の講座の販売商品）", {k: v["item_id"] for k, v in li.items()}, set(ni),
               env.skipped("learning_paths"))
    both_i = [k for k in li if k in ni]
    # 組にして比べると same() が文字列で比べ、`1500` と `1500.00` が違って見える。1値ずつ渡す
    c.values("コースの名前・価格", [
        (li[k]["item_id"], a, b) for k in both_i
        for a, b in ((li[k]["item_name"], ni[k]["title"]), (li[k]["price"], ni[k]["price"]))])
    c.values("コースの状態（有効 → published / 無効・削除 → archived。2026-10-26）", [
        (li[k]["item_id"], "archived" if int(li[k]["del_chk"] or 0) == 1
         else "published" if int(li[k]["valid_chk"] or 0) == 1 else "archived", ni[k]["status"]) for k in both_i])
    c.values("コースの一覧への表示・リモートPC", [
        (li[k]["item_id"], (int(int(li[k]["display_chk"] or 0) == 1), int(int(li[k]["remote_chk"] or 0) == 1)),
         (int(ni[k]["listed"]), int(ni[k]["remote_pc_enabled"]))) for k in both_i])
    # 結び付き: 削除されていないものだけが入る（削除済みは受け皿が無く一覧に出る）
    lpc = {(r["item_id"], r["lesson_id"]): f"{r['item_id']}:{r['lesson_id']}" for r in env.src("payment_item_lesson", """
        SELECT c.item_id, c.lesson_id FROM payment_item_lesson c JOIN payment_item p ON p.item_id = c.item_id
        WHERE p.tenant_id = %s AND p.item_type = 0 AND c.del_chk = 0""", t)}
    item_of = {k: v["item_id"] for k, v in li.items()}
    npc = {(item_of.get(r["lp"]), r["lid"]) for r in env.dst("""
        SELECT x.learning_path_id lp, co.legacy_lesson_id lid FROM learning_path_courses x
        JOIN courses co ON co.id = x.course_id WHERE x.tenant_id = %s""", d)}
    c.coverage("コースの講座（削除されていない結び付き）", lpc, npc, env.skipped("learning_path_courses"))
    return c.results


# --- 受講 ---------------------------------------------------------------------
#: 学習記録は**会員側で絞る**（03 の決定。講座側で絞ると共有講座を通じて他テナントの会員を拾う）
BY_MEMBER = "JOIN user u ON u.user_id = ul.user_id WHERE u.tenant_id = %s"
#: 権限の行（期限・無期限の印・自動継続・解約）。**受講登録とコースの購入の照合で同じ形に読む**
AUTHORITY_TERMS = """c.del_chk, c.no_limit_chk, c.authority_end_date, p.is_auto_extension ext, pa.is_cancel cancel
        FROM payment_item_lesson_authority c JOIN user u ON u.user_id = c.user_id
        LEFT JOIN payment_item p ON p.item_id = c.item_id
        LEFT JOIN payment_application pa ON pa.application_id = c.application_id"""
#: 新の `expires_at`（UTC）に入れられる最後の日付（日本時間の 23:59:59 が `TIMESTAMP` の上限を超えない日）
LAST_EXPIRY_DATE = date(2038, 1, 18)


def serial_text(number, issued) -> str:
    """旧の修了証の番号の表示（`'No.' . date('Ymd') . $certificateNo`）を、発行日で作ったもの。"""
    day = issued.strftime("%Y%m%d") if isinstance(issued, (date, datetime)) else ""
    return f"No.{day}{int(number or 0)}"


def legacy_expiry(rows: list[dict]) -> date | None:
    """**旧の受講期限**（日付）。NULL は無期限。

    旧の受講可否は `authority_end_date >= 今日`（`LessonModel::1363`）で、会員 × 講座の `MAX()` を取る。
    **自動継続も同じ**（毎日のバッチが期限を1か月ずつ延ばす。sync-issues B6）。
    生きている行（`del_chk = 0`）で決め、全部消えていれば全行で決める。無期限の印か、
    新の列に入らない遠い日付（旧は無期限を100年後で表す）は無期限。
    """
    alive = [r for r in rows if int(r["del_chk"] or 0) == 0] or rows
    if any(int(r["no_limit_chk"] or 0) == 1 for r in alive):
        return None
    ends = [_day(r["authority_end_date"]) for r in alive if r["authority_end_date"] is not None]
    if not ends or max(ends) > LAST_EXPIRY_DATE:
        return None
    return max(ends)


def new_expiry(value) -> date | None:
    """新の `expires_at`（UTC）を、日本時間の日付にする。"""
    return None if value is None else (value + timedelta(hours=9)).date()


def _day(value) -> date:
    return value.date() if isinstance(value, datetime) else value


def is_live_subscription(row: dict) -> bool:
    """自動継続の商品で、まだ解約されていない権限の行。"""
    return int(row["ext"] or 0) == 1 and int(row["cancel"] or 0) == 0 and int(row["del_chk"] or 0) == 0


def enrollment_checks(env: Env) -> list[CheckResult]:
    c = Checker("enrollment")
    t, d = (env.legacy_tenant,), (env.tenant_id,)

    # 受講権限（会員 × 講座に畳む）
    auth: dict = defaultdict(list)
    for r in env.src("payment_item_lesson_authority", f"""
        SELECT c.user_id, c.lesson_id, {AUTHORITY_TERMS} WHERE u.tenant_id = %s""", t):
        auth[(r["user_id"], r["lesson_id"])].append(r)
    enr = {(r["uid"], r["cid"]): r for r in env.dst("""
        SELECT u.user_id uid, c.legacy_lesson_id cid, e.status, e.expires_at FROM enrollments e
        JOIN users u ON u.id = e.user_id JOIN courses c ON c.id = e.course_id
        WHERE e.tenant_id = %s AND c.legacy_lesson_id IS NOT NULL""", d)}
    ne = {k: r["status"] for k, r in enr.items()}
    c.coverage("受講権限（会員 × 講座）", {k: f"{k[0]}:{k[1]}" for k in auth}, set(ne), env.skipped("enrollments"))
    c.values("全部取り消された権限は revoked", [
        (k, "revoked", ne[k]) for k, rows in auth.items()
        if k in ne and all(int(r["del_chk"] or 0) == 1 for r in rows)])
    c.values("受講期限（旧の authority_end_date の最大値。自動継続も同じ。無期限は NULL）", [
        (k, legacy_expiry(rows), new_expiry(enr[k]["expires_at"])) for k, rows in auth.items() if k in enr])
    # **参考（NG にしない）。** 旧のバッチが止まったダンプでは、未解約の自動継続も期限切れで入る
    stale = [k for k, rows in auth.items()
             if k in ne and ne[k] == "expired" and any(is_live_subscription(r) for r in rows)]
    c("（参考）未解約の自動継続で、移した時点で期限切れのもの（本番ではダンプの鮮度を確かめる）", True,
      _sample(stale) if stale else "0 件")
    # 商品を経た権限はコースの購入で作った受講登録（2026-10-22。school-launcher 20261012174140）
    with_item = {(r["user_id"], r["lesson_id"]) for r in env.src("payment_item_lesson_authority", """
        SELECT c.user_id, c.lesson_id FROM payment_item_lesson_authority c
        JOIN user u ON u.user_id = c.user_id WHERE u.tenant_id = %s AND c.item_id IS NOT NULL""", t)}
    nvia = {(r["uid"], r["cid"]): int(r["via"]) for r in env.dst("""
        SELECT u.user_id uid, c.legacy_lesson_id cid, e.via_learning_path via FROM enrollments e
        JOIN users u ON u.id = e.user_id JOIN courses c ON c.id = e.course_id
        WHERE e.tenant_id = %s AND c.legacy_lesson_id IS NOT NULL""", d)}
    c.values("商品を経た権限はコースの購入で作った受講登録（via_learning_path）", [
        (k, int(k in with_item), nvia[k]) for k in auth if k in nvia])

    # 学習状況（会員 × ユニット）。重複した組は新しい1件に絞る規則なので、1件だけの組で修了を比べる。
    # **管理者が削除した受講の記録の下の行は移さない**（アンケートの回答があるものは残す。03 移行仕様 0-2 Q5）
    progress: dict = defaultdict(list)
    for r in env.src("user_learning_unit", f"""
        SELECT ul.user_id, uu.unit_id, uu.learning_status FROM user_learning_unit uu
        JOIN user_learning_lesson ul ON ul.user_learning_lesson_id = uu.user_learning_lesson_id {BY_MEMBER}
        AND (ul.del_chk = 0 OR EXISTS (SELECT 1 FROM enquete_answer a WHERE a.entity_type_id = 2
             AND a.entity_id = uu.user_learning_unit_id AND a.del_chk = 0))""", t):
        progress[(r["user_id"], r["unit_id"])].append(int(r["learning_status"] or 0))
    np_ = {(r["uid"], r["lid"]): r["done"] for r in env.dst("""
        SELECT u.user_id uid, l.unit_id lid, lp.completed_at IS NOT NULL done FROM lesson_progress lp
        JOIN users u ON u.id = lp.user_id JOIN lessons l ON l.id = lp.lesson_id
        WHERE lp.tenant_id = %s AND l.type <> 'live'""", d)}
    c.coverage("学習状況（会員 × ユニット）", {k: f"{k[0]}:{k[1]}" for k in progress}, set(np_),
               env.skipped("lesson_progress"))
    c.values("修了（learning_status = 1 ⇔ 修了日あり）", [
        (k, 1, int(np_[k])) if v[0] == 1 else (k, 0, int(np_[k]))
        for k, v in progress.items() if len(v) == 1 and k in np_])

    # テストの受験（得点）
    attempts = {r["user_learning_test_id"]: r for r in env.src("user_learning_test", f"""
        SELECT t.user_learning_test_id, t.sum_score FROM user_learning_test t
        JOIN user_learning_unit uu ON uu.user_learning_unit_id = t.user_learning_unit_id
        JOIN user_learning_lesson ul ON ul.user_learning_lesson_id = uu.user_learning_lesson_id {BY_MEMBER}""", t)}
    na = {r["id"]: r["score"] for r in env.dst("SELECT id, score FROM quiz_attempts WHERE tenant_id = %s", d)}
    keyed = {env.ulid("user_learning_test", k): k for k in attempts}
    c.coverage("テストの受験", keyed, set(na), env.skipped("quiz_attempts"))
    c.values("受験の得点（sum_score）", [
        (old, attempts[old]["sum_score"] or 0, na[new]) for new, old in keyed.items() if new in na])

    # 課題の提出（得点）
    reports = {r["user_learning_report_id"]: r for r in env.src("user_learning_report", f"""
        SELECT r.user_learning_report_id, r.score FROM user_learning_report r
        JOIN user_learning_unit uu ON uu.user_learning_unit_id = r.user_learning_unit_id
        JOIN user_learning_lesson ul ON ul.user_learning_lesson_id = uu.user_learning_lesson_id {BY_MEMBER}""", t)}
    ns = {r["id"]: r["score"] for r in env.dst("SELECT id, score FROM submissions WHERE tenant_id = %s", d)}
    keyed = {env.ulid("user_learning_report", k): k for k in reports}
    c.coverage("課題の提出", keyed, set(ns), env.skipped("submissions"))
    c.values("提出の得点", [(old, reports[old]["score"], ns[new]) for new, old in keyed.items() if new in ns])

    # アンケートの回答（ユニットに付くもの = entity_type 2）
    answers = {env.ulid("enquete_answer", r["enquete_answer_id"]): r["enquete_answer_id"] for r in env.src(
        "enquete_answer", f"""SELECT a.enquete_answer_id FROM enquete_answer a
        JOIN user_learning_unit uu ON uu.user_learning_unit_id = a.entity_id
        JOIN user_learning_lesson ul ON ul.user_learning_lesson_id = uu.user_learning_lesson_id
        {BY_MEMBER} AND a.entity_type_id = 2""", t)}
    nr = {r["id"] for r in env.dst("SELECT id FROM survey_responses WHERE tenant_id = %s", d)}
    c.coverage("アンケートの回答（ユニット）", answers, nr, env.skipped("survey_responses"))

    # ライブの予約（開催側の中止・キャンセル・出席は旗のとおり）
    reserves = {r["live_lesson_reserve_id"]: r for r in env.src("live_lesson_reserve", """
        SELECT r.live_lesson_reserve_id, r.stop_chk, r.cancel_chk, r.attendance_chk FROM live_lesson_reserve r
        JOIN live_lesson_date dt ON dt.live_lesson_date_id = r.live_lesson_date_id
        JOIN live_lesson l ON l.live_lesson_id = dt.live_lesson_id WHERE l.tenant_id = %s""", t)}
    nres = {r["id"]: r["status"] for r in env.dst("SELECT id, status FROM live_reservations WHERE tenant_id = %s", d)}
    keyed = {env.ulid("live_lesson_reserve", k): k for k in reserves}
    c.coverage("ライブの予約", keyed, set(nres), env.skipped("live_reservations"))

    def flag_status(r):
        if int(r["stop_chk"] or 0) == 1 or int(r["cancel_chk"] or 0) == 1:
            return "canceled"  # 開催側の中止も canceled（settings.stop_chk で区別。03 移行仕様 0-2 Q13）
        if int(r["attendance_chk"] or 0) == 1:
            return "attended"
        return None  # 予約中か欠席かは開催日で決まる（実行時刻に依存）

    pairs = [(old, flag_status(reserves[old]), nres[new]) for new, old in keyed.items()
             if new in nres and flag_status(reserves[old]) is not None]
    c.values("予約の状態（中止・キャンセル → canceled / 出席 → attended）", pairs)

    # 修了証（講座単位）
    certs = {env.ulid("user_certificate", f"{r['user_id']}:{r['entity_id']}"): r for r in env.src(
        "user_certificate", """SELECT c.user_id, c.entity_id, c.certificate_no, c.regist_date FROM user_certificate c
        JOIN user u ON u.user_id = c.user_id WHERE u.tenant_id = %s AND c.certificate_type = 1""", t)}
    dst_certs = {r["id"]: r for r in env.dst("SELECT id, serial_no, serial_text FROM certificates WHERE tenant_id = %s", d)}
    nce = {k: r["serial_no"] for k, r in dst_certs.items()}
    c.coverage("修了証", {k: f"{v['user_id']}:{v['entity_id']}" for k, v in certs.items()}, set(nce),
               env.skipped("certificates"))
    c.values("修了証の番号", [(k, certs[k]["certificate_no"] or 0, nce[k]) for k in certs if k in nce])
    c.values("修了証の番号の文字列（No. ＋発行日＋番号）", [
        (k, serial_text(certs[k]["certificate_no"], certs[k]["regist_date"]), dst_certs[k]["serial_text"])
        for k in certs if k in dst_certs])

    # 講座ごとの修了証の発行方針。**行が無い = 発行する** なので、移した全講座に行があること
    npol = {r["lid"]: r["issue"] for r in env.dst("""
        SELECT c.legacy_lesson_id lid, p.issue FROM courses c
        LEFT JOIN course_certificate_policies p ON p.course_id = c.id
        WHERE c.tenant_id = %s AND c.legacy_lesson_id IS NOT NULL""", d)}
    marks, ids = _in(npol)
    lcert = {r["lesson_id"]: int(r["certificate_id"] or 0) != 0 for r in env.src(
        "lesson", f"SELECT lesson_id, certificate_id FROM lesson WHERE tenant_id IN (%s, 0) AND lesson_id IN ({marks})",
        t + ids)} if npol else {}
    c("修了証の発行方針: 移した講座すべてに行がある", all(v is not None for v in npol.values()),
      _sample([k for k, v in npol.items() if v is None]))
    c.values("修了証を発行するか（旧の certificate_id の有無）",
             [(k, int(lcert[k]), int(bool(npol[k]))) for k in npol if k in lcert and npol[k] is not None])
    return c.results


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
#: 入金待ち（0）は failed（04 移行仕様 0-2 Q6）
STATUS = {0: "failed", 1: "succeeded", 2: "failed"}


def billing_checks(env: Env) -> list[CheckResult]:
    src, dst, legacy_tenant, tenant_id = env.src, env.dst, env.legacy_tenant, env.tenant_id
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
    for r in dst("SELECT status, amount, settings FROM payments WHERE tenant_id = %s AND application_id IS NOT NULL", d):
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
    check("決済の状態（1→succeeded / 0・2→failed）", wrong_status == 0, f"食い違い {wrong_status} 件")

    # 2. 会員ごとの支払い済み金額
    lu = {r["uid"]: num(r["amt"]) for r in src("payment_application", f"""
        SELECT a.user_id uid, SUM(a.amount) amt FROM payment_application a
        WHERE a.tenant_id = %s AND a.payment_type IN (1, 2, 3) AND a.application_result = 1 AND {LIVE_USER}
        GROUP BY 1""", t)}
    nu = {r["uid"]: num(r["amt"]) for r in dst("""
        SELECT u.user_id uid, SUM(p.amount) amt FROM payments p JOIN users u ON u.id = p.user_id
        WHERE p.tenant_id = %s AND p.status = 'succeeded' AND p.application_id IS NOT NULL GROUP BY 1""", d)}
    diff = {k: (lu.get(k), nu.get(k)) for k in set(lu) | set(nu) if lu.get(k) != nu.get(k)}
    check(f"会員ごとの支払い済み金額（{len(lu)} 名）", not diff, _sample(diff.items()) if diff else "")
    check("支払い済みの総額", sum(lu.values()) == sum(nu.values()),
          f"旧 {sum(lu.values())} 円 / 新 {sum(nu.values())} 円")

    # 3. 決済の種類（旧の商品から判定）
    kind = {}
    for r in src("payment_application", f"""
        SELECT a.application_id aid, i.item_type it, i.is_auto_extension ext
        FROM payment_application a
        JOIN payment_application_item x ON x.application_id = a.application_id
        JOIN payment_item i ON i.item_id = x.item_id
        WHERE a.tenant_id = %s AND {MONEY} AND {LIVE_USER}""", t):
        # 講座の商品はコースの購入（買い切りも自動継続も。2026-10-22）
        kind[r["aid"]] = ("learning_path_purchase" if r["it"] == 0
                          else "subscription" if r["ext"] == 1 else "lw2_purchase")
    nk = {r["application_id"]: r["type"] for r in dst(
        "SELECT application_id, type FROM payments WHERE tenant_id = %s AND application_id IS NOT NULL", d)}
    bad = [k for k in set(kind) | set(nk) if kind.get(k) != nk.get(k)]
    check(f"決済の種類（{len(kind)} 件）", not bad, _sample(bad) if bad else "")
    # コースの購入の明細（決済 → コース）。講座の商品の決済には、その商品（コース）を指す1行がある
    want = {}
    for r in src("payment_application", f"""
        SELECT a.application_id aid, i.item_id iid FROM payment_application a
        JOIN payment_application_item x ON x.application_id = a.application_id
        JOIN payment_item i ON i.item_id = x.item_id
        WHERE a.tenant_id = %s AND i.item_type = 0 AND {MONEY} AND {LIVE_USER}""", t):
        want[r["aid"]] = env.ulid("learning_path", r["iid"])
    got = {r["application_id"]: r["learning_path_id"] for r in dst("""
        SELECT p.application_id, d.learning_path_id FROM learning_path_purchase_payments d
        JOIN payments p ON p.id = d.payment_id WHERE p.tenant_id = %s""", d)}
    bad = [k for k in set(want) | set(got) if want.get(k) != got.get(k)]
    check(f"コースの購入の明細（決済 → コース。{len(want)} 件）", not bad, _sample(bad) if bad else "")

    # 4. 領収書
    lr = {r["receipt_log_id"]: r for r in src("receipt_log", f"""
        SELECT r.receipt_log_id, r.application_id, r.receipt_price, r.receipt_name, r.receipt_provision,
               r.company_name, r.tax_rate, r.excluding_tax_price, r.invoice_no, {REAL_PAYMENT_DATE} real_date
        FROM receipt_log r
        JOIN payment_application a ON a.application_id = r.application_id
        JOIN payment_application_item x ON x.application_id = a.application_id
        JOIN payment_item i ON i.item_id = x.item_id
        WHERE r.tenant_id = %s""", t)}
    nr = {r["receipt_log_id"]: r for r in dst("""
        SELECT r.receipt_log_id, r.issue_no, r.amount, r.recipient_name, r.note, r.issuer_name, r.tax_rate,
               r.tax_excluded_amount, r.issuer_invoice_registration_no, r.transaction_date, p.application_id app
        FROM receipts r JOIN payments p ON p.id = r.payment_id
        WHERE r.tenant_id = %s AND r.receipt_log_id IS NOT NULL""", d)}
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

    # 5. 商品。**旧の商品は tenant_plans / plan_courses に入れない**（2026-10-23 決定。コースとしてコンテンツで移す）。
    # 意図して移さないものなので、入っていないことを確かめる
    np_ = sum(int(r["n"] or 0) for r in dst(
        "SELECT COUNT(*) n FROM tenant_plans WHERE tenant_id = %s AND item_id IS NOT NULL", d))
    npc = sum(int(r["n"] or 0) for r in dst("""SELECT COUNT(*) n FROM plan_courses x JOIN tenant_plans p ON p.id = x.plan_id
        WHERE x.tenant_id = %s AND p.item_id IS NOT NULL""", d))
    check(f"旧の商品を tenant_plans / plan_courses に入れていない（新 {np_} / {npc}）", np_ == 0 and npc == 0)

    # 6. 受講と決済の結びつき
    auth: dict = defaultdict(set)
    for r in src("payment_item_lesson_authority", f"""
        SELECT c.user_id uid, c.lesson_id lid, a.application_id aid FROM payment_item_lesson_authority c
        JOIN user u ON u.user_id = c.user_id
        JOIN payment_application a ON a.application_id = c.application_id
        WHERE u.tenant_id = %s AND {MONEY} AND a.user_id = c.user_id""", t):
        # **払った会員が権限の会員と違う申込には結ばない**（会員の無い申込。04 移行仕様 0-2 Q8。
        # 補正データで申込の会員を直したときは、旧 DB のままのここと食い違う）
        auth[(r["uid"], r["lid"])].add(r["aid"])
    links = {(r["uid"], r["cid"]): r["pp"] for r in dst("""
        SELECT u.user_id uid, c.legacy_lesson_id cid, e.provider_payment_id pp FROM enrollments e
        JOIN users u ON u.id = e.user_id JOIN courses c ON c.id = e.course_id
        WHERE e.tenant_id = %s AND e.provider_payment_id LIKE 'lw2-%%'""", d)}
    enrolled = {(r["uid"], r["cid"]) for r in dst("""
        SELECT u.user_id uid, c.legacy_lesson_id cid FROM enrollments e
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
        SELECT u.user_id uid, t.ticket_id tid, SUM(g.remaining_quantity) n FROM ticket_grants g
        JOIN users u ON u.id = g.user_id JOIN ticket_types t ON t.id = g.ticket_type_id
        WHERE g.tenant_id = %s GROUP BY 1, 2""", d)}
    check(f"チケットの残枚数（会員 × 種別 {len(lt)} 組）", lt == nt, f"旧 {lt} / 新 {nt}" if lt != nt else "")

    # 9. 台帳: **開催が未来で専用チケット（payment_type 7）で払った**予約 × 1 枚（04 移行仕様 0-2 Q3・Q4）
    ledger = src("live_lesson_reserve", """
        SELECT COUNT(*) n, COUNT(*) cost FROM live_lesson_reserve r
        JOIN live_lesson_date dt ON dt.live_lesson_date_id = r.live_lesson_date_id
        JOIN live_lesson l ON l.live_lesson_id = dt.live_lesson_id
        JOIN payment_application pa ON pa.live_lesson_reserve_id = r.live_lesson_reserve_id AND pa.payment_type = 7
        WHERE l.tenant_id = %s AND l.item_ticket_price > 0 AND dt.live_lesson_date_from > NOW()
          AND COALESCE(r.stop_chk, 0) = 0 AND COALESCE(r.cancel_chk, 0) = 0
          AND EXISTS (SELECT 1 FROM ticket_limit_lesson tl WHERE tl.live_lesson_id = l.live_lesson_id AND tl.del_chk = 0
                      AND EXISTS (SELECT 1 FROM user_ticket g WHERE g.user_id = r.user_id
                                  AND g.ticket_id = tl.ticket_id AND g.ticket_num >= 1))""", t)[0]
    nled = dst("SELECT COUNT(*) n, -SUM(quantity_delta) cost FROM ticket_ledger_entries WHERE tenant_id = %s", d)[0]
    check("チケットの台帳（行数と枚数）",
          int(ledger["n"] or 0) == int(nled["n"] or 0) and num(ledger["cost"]) == num(nled["cost"]),
          f"旧 {ledger['n']} 件 {ledger['cost'] or 0} 枚 / 新 {nled['n']} 行 {nled['cost'] or 0} 枚")

    # 自動割当 → タグの自動付与ルール
    la = {r["assign_id"] for r in src("assign", "SELECT assign_id FROM assign WHERE tenant_id = %s", t)}
    na = {r["assign_id"] for r in dst(
        "SELECT assign_id FROM tag_auto_assign_rules WHERE tenant_id = %s AND assign_id IS NOT NULL", d)}
    check(f"自動割当のルール（旧 {len(la)} / 新 {len(na)}）", la == na,
          f"旧だけ {sorted(la - na)[:3]} / 新だけ {sorted(na - la)[:3]}" if la != na else "")
    lg = {r["assign_id"]: int(r["n"]) for r in src("assign_item", """
        SELECT assign_id, COUNT(*) n FROM assign_item WHERE tenant_id = %s
          AND item_type IN ('lesson', 'news', 'announce', 'coupon', 'recruit')
        GROUP BY assign_id""", t)}
    ng = {r["assign_id"]: int(r["n"]) for r in dst("""
        SELECT r.assign_id, COUNT(*) n FROM tag_auto_assign_rule_grants g
        JOIN tag_auto_assign_rules r ON r.id = g.rule_id WHERE r.tenant_id = %s GROUP BY r.assign_id""", d)}
    check("自動割当で付与するもの（ルールごとの件数。削除・無効を含む）", lg == ng, f"旧 {lg} / 新 {ng}" if lg != ng else "")
    def count(rows) -> int:
        return int(rows[0]["n"]) if rows else 0

    lt = count(src("assign_payment_item", """
        SELECT COUNT(*) n FROM assign_payment_item c JOIN assign a ON a.assign_id = c.assign_id WHERE a.tenant_id = %s""", t))
    nt_ = count(dst("""
        SELECT COUNT(*) n FROM tag_auto_assign_rule_triggers g JOIN tag_auto_assign_rules r ON r.id = g.rule_id
        WHERE r.tenant_id = %s""", d))
    check(f"自動割当のきっかけ（旧 {lt} / 新 {nt_}）", lt == nt_)
    # 講座の商品のきっかけは、移したコースを指す（2026-10-23。sync-issues B7）。コースが入っていない
    # 商品と、講座の商品でないもの（チケット・ライブ）は旧 ID だけ
    paths = {r["id"] for r in dst("SELECT id FROM learning_paths WHERE tenant_id = %s", d)}
    want = {}
    for r in src("assign_payment_item", """
        SELECT c.assign_id, c.item_id, p.item_type it FROM assign_payment_item c
        JOIN assign a ON a.assign_id = c.assign_id
        LEFT JOIN payment_item p ON p.item_id = c.item_id
        WHERE a.tenant_id = %s AND c.item_type = 0""", t):
        path = env.ulid("learning_path", r["item_id"])
        want[(r["assign_id"], r["item_id"])] = path if int(r["it"] or 0) == 0 and path in paths else None
    got = {(r["aid"], r["iid"]): r["lp"] for r in dst("""
        SELECT r.assign_id aid, g.item_id iid, g.learning_path_id lp FROM tag_auto_assign_rule_triggers g
        JOIN tag_auto_assign_rules r ON r.id = g.rule_id WHERE r.tenant_id = %s AND g.item_type = 0""", d)}
    bad = [(k, v, got.get(k)) for k, v in want.items() if got.get(k) != v]
    check(f"自動割当の商品のきっかけ → コース（{sum(v is not None for v in want.values())} / {len(want)} 件）",
          not bad, _sample(bad) if bad else "")
    # 旧の形のままの受け皿（全行）
    for legacy, target, sql in (
        # 除外日の全行はコンテンツで入れるので、コンテンツの照合（content_checks）で見る
        ("live_lesson_limit_item", "live_lesson_limit_item_history",
         "SELECT COUNT(*) n FROM live_lesson_limit_item c JOIN live_lesson p ON p.live_lesson_id = c.live_lesson_id WHERE p.tenant_id = %s"),
    ):
        ln = count(src(legacy, sql, t))
        nn = count(dst(f"SELECT COUNT(*) n FROM {target} WHERE tenant_id = %s", d))
        check(f"{legacy} の全行（削除済みを含む。旧 {ln} / 新 {nn}）", ln == nn)
    return out + _learning_path_enrollment_checks(env)


def _learning_path_enrollment_checks(env: Env) -> list[CheckResult]:
    """コースの購入・割り当て（受講 03 のデータ。billing.2 で流すので課金の照合で見る。2026-10-22）。

    **1回の購入・付与 = 旧の `authority_key`**（会員1人・商品1つ）。
    """
    c = Checker("billing")
    t, d = (env.legacy_tenant,), (env.tenant_id,)
    rows: dict = defaultdict(list)
    for r in env.src("payment_item_lesson_authority", f"""
        SELECT c.authority_key, c.user_id, c.item_id, c.application_id, c.lesson_id,
               pa.payment_type, {AUTHORITY_TERMS}
        WHERE u.tenant_id = %s AND c.item_id IS NOT NULL""", t):
        key = (r["authority_key"] or "").strip() or f"{r['user_id']}:{r['item_id']}:{r['application_id'] or ''}"
        rows[key].append(r)
    legacy = {env.ulid("authority_key", k): k for k in rows}
    new = {r["id"]: r for r in env.dst("""
        SELECT id, learning_path_id, source, status, expires_at FROM learning_path_enrollments
        WHERE tenant_id = %s""", d)}
    c.coverage("コースの購入・割り当て（旧の購入・付与ごと）", legacy, set(new), env.skipped("learning_path_enrollments"))

    def source(members) -> str:
        apps = [m for m in members if m["application_id"] is not None]
        if not apps:
            return "admin"
        return "free" if all(int(m["payment_type"] or 0) in (0, 4) for m in apps) else "purchase"

    pairs = []
    for nid, key in legacy.items():
        if nid not in new:
            continue
        members = rows[key]
        src = source(members)
        removed = all(int(m["del_chk"] or 0) == 1 for m in members)
        pairs += [
            (key, env.ulid("learning_path", members[0]["item_id"]), new[nid]["learning_path_id"]),
            (key, src, new[nid]["source"]),
        ]
        if removed:
            pairs.append((key, "revoked" if src == "admin" else "refunded", new[nid]["status"]))
    c.values("コースの購入のコース・種類・取り消し（購入・無料 → refunded / 管理者の付与 → revoked）", pairs)
    c.values("コースの購入の期限（旧の authority_end_date の最大値。自動継続も同じ。無期限は NULL）", [
        (key, legacy_expiry(rows[key]), new_expiry(new[nid]["expires_at"]))
        for nid, key in legacy.items() if nid in new])
    lc = {(env.ulid("authority_key", k), m["lesson_id"]): f"{k}:{m['lesson_id']}"
          for k, members in rows.items() for m in members}
    nc = {(r["lpe"], r["lid"]) for r in env.dst("""
        SELECT x.learning_path_enrollment_id lpe, co.legacy_lesson_id lid FROM learning_path_enrollment_courses x
        JOIN courses co ON co.id = x.course_id WHERE x.tenant_id = %s""", d)}
    c.coverage("コースの購入で渡した講座", lc, nc, env.skipped("learning_path_enrollment_courses"))
    return c.results


# --- サポート（未実装だった移行の分。docs/db/05-support/migration-spec.md 0 章） ----------
def support_checks(env: Env) -> list[CheckResult]:
    """旧の行が移ったか（漏れ・紛れ）と、移し方の要の値。**変換のコードは使わない。**"""
    c = Checker("support")
    t, d = (env.legacy_tenant,), (env.tenant_id,)

    # お知らせ・アナウンス（削除済みも取り下げで移す）
    legacy = {env.ulid("news", r["news_id"]): f"news:{r['news_id']}"
              for r in env.src("news", "SELECT news_id FROM news WHERE tenant_id = %s", t)}
    legacy |= {env.ulid("announce", r["announce_id"]): f"announce:{r['announce_id']}"
               for r in env.src("announce", "SELECT announce_id FROM announce WHERE tenant_id = %s", t)}
    new = {r["id"]: r for r in env.dst("SELECT id, status FROM announcements WHERE tenant_id = %s", d)}
    c.coverage("お知らせ・アナウンス", legacy, set(new), env.skipped("announcements"))
    deleted = {env.ulid("news", r["news_id"]) for r in env.src(
        "news", "SELECT news_id FROM news WHERE tenant_id = %s AND del_chk = 1", t)}
    deleted |= {env.ulid("announce", r["announce_id"]) for r in env.src(
        "announce", "SELECT announce_id FROM announce WHERE tenant_id = %s AND del_chk = 1", t)}
    c("削除済みのお知らせは取り下げ", all(new[k]["status"] == "withdrawn" for k in deleted if k in new),
      f"{len(deleted)} 件")

    # 配信先・既読（生きている配信先だけ。外された行は一覧に出る）
    for kind, child, read in (("news", "news_user", "news_disp_date"), ("announce", "announce_user", "disp_time")):
        rows = env.src(child, f"""SELECT c.{child}_id AS k, c.{kind}_id AS a, c.user_id AS u, c.{read} AS r
            FROM {child} c JOIN {kind} p ON p.{kind}_id = c.{kind}_id
            WHERE p.tenant_id = %s AND p.del_chk = 0 AND c.del_chk = 0""", t)
        targets = {(env.ulid(kind, r["a"]), env.ulid("user", r["u"])): f"{child}:{r['k']}" for r in rows}
        reads = {(env.ulid(kind, r["a"]), env.ulid("user", r["u"])): f"{child}:{r['k']}" for r in rows if r["r"]}
        ids = {a for a, _ in targets}
        if ids:
            marks = ", ".join(["%s"] * len(ids))
            got_t = {(r["a"], r["u"]) for r in env.dst(
                f"SELECT announcement_id a, user_id u FROM announcement_user_targets WHERE announcement_id IN ({marks})", tuple(ids))}
            got_r = {(r["a"], r["u"]) for r in env.dst(
                f"SELECT announcement_id a, user_id u FROM announcement_reads WHERE announcement_id IN ({marks})", tuple(ids))}
        else:
            got_t = got_r = set()
        label = "お知らせ" if kind == "news" else "アナウンス"
        c.coverage(f"{label}の配信先", targets, got_t, env.skipped("announcement_user_targets"))
        c.coverage(f"{label}の既読", reads, got_r, env.skipped("announcement_reads"))

    # クーポン（無料クーポンは一覧に出る）。個人の配布日は旧の登録日
    legacy = {env.ulid("coupon", r["coupon_id"]): f"coupon:{r['coupon_id']}"
              for r in env.src("coupon", "SELECT coupon_id FROM coupon WHERE tenant_id = %s", t)}
    new = {r["id"] for r in env.dst("SELECT id FROM coupons WHERE tenant_id = %s", d)}
    c.coverage("クーポン", legacy, new, env.skipped("coupons"))
    given = env.src("coupon_user", """SELECT c.coupon_id, c.user_id, c.regist_date FROM coupon_user c
        JOIN coupon p ON p.coupon_id = c.coupon_id WHERE p.tenant_id = %s AND c.del_chk = 0""", t)
    got = {(r["c"], r["u"]): r["at"] for r in env.dst(
        "SELECT coupon_id c, user_id u, created_at at FROM coupon_user_targets WHERE tenant_id = %s", d)}
    pairs = [(f"{r['coupon_id']}:{r['user_id']}", r["regist_date"] - timedelta(hours=9) if r["regist_date"] else None,
              got[(env.ulid("coupon", r["coupon_id"]), env.ulid("user", r["user_id"]))])
             for r in given if (env.ulid("coupon", r["coupon_id"]), env.ulid("user", r["user_id"])) in got]
    c.values("クーポンの配布日（配布日から N 日の起点）", pairs)

    # 問い合わせ（ログインしていない人・2 往復目は一覧に出る）。削除済みは deleted_at
    rows = env.src("inquire", """SELECT c.inquire_id, c.del_chk FROM inquire c
        JOIN inquire_cate p ON p.inquire_cate_id = c.inquire_cate_id WHERE p.tenant_id = %s""", t)
    legacy = {env.ulid("inquire", r["inquire_id"]): str(r["inquire_id"]) for r in rows}
    new = {r["id"]: r for r in env.dst("SELECT id, deleted_at FROM inquiries WHERE tenant_id = %s", d)}
    c.coverage("問い合わせ", legacy, set(new), env.skipped("inquiries"))
    wrong = [r["inquire_id"] for r in rows if env.ulid("inquire", r["inquire_id"]) in new
             and (new[env.ulid("inquire", r["inquire_id"])]["deleted_at"] is not None) != (int(r["del_chk"]) == 1)]
    c("削除済みの問い合わせは deleted_at", not wrong, _sample(wrong) if wrong else "")

    # 講座のディスカッションの投稿
    rows = env.src("discussion_board_comment", """SELECT c.discussion_board_comment_id k FROM discussion_board_comment c
        JOIN discussion_board b ON b.discussion_board_id = c.discussion_board_id
        JOIN unit u ON u.unit_id = b.unit_id JOIN user m ON m.user_id = c.user_id
        WHERE m.tenant_id = %s""", t)
    legacy = {env.ulid("discussion_board_comment", r["k"]): str(r["k"]) for r in rows}
    new = {r["id"] for r in env.dst("SELECT id FROM discussion_posts WHERE tenant_id = %s", d)}
    c.coverage("講座のディスカッションの投稿", legacy, new, env.skipped("discussion_posts"))

    # career の DB
    if env.career is not None:
        rows = env.src("company", """SELECT DISTINCT c.company_id FROM company c
            JOIN user p ON p.company_id = c.company_id WHERE p.tenant_id = %s""", t)
        legacy = {env.ulid("company", r["company_id"]): str(r["company_id"]) for r in rows}
        new = {r["id"] for r in env.career("SELECT id FROM companies WHERE tenant_id = %s", d)}
        c.coverage("企業（career）", legacy, new, env.skipped("companies"))
        rows = env.src("interview_record", "SELECT interview_id FROM interview_record WHERE tenant_id = %s", t)
        legacy = {env.ulid("interview", r["interview_id"]): str(r["interview_id"]) for r in rows}
        new = {r["id"] for r in env.career("SELECT id FROM interviews WHERE tenant_id = %s", d)}
        c.coverage("面談（career）", legacy, new, env.skipped("interviews"))
    return c.results


#: 区分 → 突き合わせ
CHECKS: dict[str, Callable[[Env], list[CheckResult]]] = {
    "foundation": foundation_checks,
    "content": content_checks,
    "enrollment": enrollment_checks,
    "billing": billing_checks,
    "support": support_checks,
}
ORDER = ("foundation", "content", "enrollment", "billing", "support")


def run(ctx, sections: set[str]) -> list[CheckResult]:
    """選んだ区分の突き合わせを流す。旧 DB と移行先の両方に接続が要る。

    **同じ `verify` で照合を流したあとに呼ぶ。** 移さなかった行の一覧（`ctx.exclusions().keys`）を
    「説明のつく欠け」として使うため。
    """
    if ctx.target.connectionless or ctx.source is None:
        return []
    source = ctx.require_source()
    roles = {int(k): str(v) for k, v in ((ctx.config.mappings.get("role") or {}).get("values") or {}).items()}
    env = Env(
        src=lambda table, sql, params: source.fetch(table, sql, params),
        dst=lambda sql, params: ctx.target.query(sql, params),
        legacy_tenant=ctx.config.tenant.legacy_id,
        tenant_id=ctx.tenant_id.value,
        ulid=lambda ns, key: ctx.ulid.for_row(ns, key),
        excluded=ctx.exclusions().keys,
        roles=roles,
        career=(lambda sql, params: ctx.career.query(sql, params)) if ctx.career is not None else None,
    )
    results: list[CheckResult] = []
    for section in ORDER:
        if section in sections:
            results += CHECKS[section](env)
    return results
