"""フェーズ4 — 会員本体。

**全列を移す。列を落とさず、複数列を1列に畳まない**（docs/db/01-foundation/review.md
「全列の行き先」）。この Step が守る取り決め:

- 姓 / 名は分割のまま。`name` は分割列から**生成**する（二重管理にしない）
- 固定電話と携帯電話は別の列
- 誕生日は3列（`birth_year` / `birth_month` / `birth_day`）
- `del_chk` / `valid_chk` は `status` に畳まず、`is_valid` と期間列を併せて残す
- プロフィール画像は**移さない**（運営の判断。列は空で始める）
"""

from __future__ import annotations

from ..context import RunContext
from ..core.datetimes import ColumnKind, DateBoundary, convert, convert_date, split_date
from ..core.records import Record
from ..core.text import LengthCheck, find_over_length, join_name
from ..errors import PreflightError
from .base import Step

#: 旧 `user` から読む列。画像列は移さないので読まない。
#: `password` は**復号して bcrypt に入れ替えるために読む**（`core/passwords.py`）。
#: 平文はログにも例外にも出さない
USER_COLUMNS = (
    "user_id",
    "password",
    "tenant_id",
    "login_id",
    "role_id",
    "name_sei",
    "name_mei",
    "kana_sei",
    "kana_mei",
    "mail_add",
    "mobile_mail_add",
    "tel",
    "mobile_tel",
    "nick_name",
    "sex_type",
    "birth_date",
    "blood_type",
    "self_introduction",
    "entry_date",
    "limit_date",
    "user_memo",
    "system_data",
    "recent_login_date",
    "recent_access_time",
    "total_login_count",
    "password_change_date",
    "is_lockout",
    "start_date_failing_login",
    "number_of_failing_login",
    "valid_chk",
    "del_chk",
    "new_user_chk",
    "regist_date",
    "update_date",
)

LENGTH_CHECKS = (LengthCheck("tel", 32), LengthCheck("mobile_tel", 32))

#: 会員の一意 ID（U2）。`users.member_no` に入れる
PERSONAL_NO_COLUMNS = ("user_id", "personal_no")
#: 会員の付属情報（U1）。`career_counselor_chk` は**ロールではなくフラグ**
ATTACHED_INFO_COLUMNS = ("user_id", "career_counselor_chk")
#: 会員の既定言語（A22）。国籍・海外住所と同じ `user_nationality_info` にある
LANGUAGE_COLUMNS = ("user_id", "language_code")

#: 新環境の外部連携の識別子。**ETL・ブリッジ・テストの3か所で同じ値にする**
EXTERNAL_SYSTEM = "lw2"


class UsersStep(Step):
    name = "users"
    description = "会員を移す（全列。畳まない）"
    source_table = "user"
    target_table = "users"
    depends_on = ("tenant", "master.user_roles")

    def extract(self, ctx: RunContext) -> list[dict]:
        source = ctx.require_source()
        rows = source.fetch_for_tenant("user", USER_COLUMNS)
        over = find_over_length(rows, LENGTH_CHECKS)
        if over:
            raise PreflightError(
                f"桁溢れがある: {over}。切り捨てず、新環境の列を広げてから移す"
            )

        # 別テーブルにある会員の列をここで合流させる。
        # **UPDATE を後から流さない** — 1行を1回の INSERT で完成させる
        personal = {
            int(r["user_id"]): r.get("personal_no")
            for r in source.fetch_joined(
                "user_personal_no", PERSONAL_NO_COLUMNS, parent="user", on="c.user_id = p.user_id"
            )
        }
        counselor = {
            int(r["user_id"]): r.get("career_counselor_chk")
            for r in source.fetch_joined(
                "user_attached_info", ATTACHED_INFO_COLUMNS, parent="user", on="c.user_id = p.user_id"
            )
        }
        languages = {
            int(r["user_id"]): r.get("language_code")
            for r in source.fetch_joined(
                "user_nationality_info", LANGUAGE_COLUMNS, parent="user", on="c.user_id = p.user_id"
            )
        }
        for row in rows:
            key = int(row["user_id"])
            row["_member_no"] = personal.get(key)
            row["_career_counselor"] = counselor.get(key)
            # 空文字は「未設定」。NULL にして新環境の既定（テナント → 既定ロケール）に任せる
            row["_language"] = (languages.get(key) or "").strip() or None
        return rows

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        role_map = ctx.role_map()
        tenant_id = ctx.tenant_id.value
        records: list[Record] = []
        # メールは**旧の値をそのまま入れる。** 空・重複は `users.email` の
        # NOT NULL / UNIQUE に当たり、その会員は移らない（一覧に出る）。
        # 合成アドレスを割り当てて通すことはしない — 何が本物か分からなくなる
        #
        # 旧の 3DES を復号して bcrypt に入れ替える。**鍵が無ければここで止まる**
        passwords = ctx.password_migration()
        rows = sorted(rows, key=lambda r: int(r["user_id"]))

        for row in rows:
            name = join_name(row.get("name_sei"), row.get("name_mei"))
            email = (row.get("mail_add") or "").strip() or None

            year, month, day = split_date(row.get("birth_date"))
            records.append(
                Record(
                    table="users",
                    values={
                        "id": ctx.ulid.for_row("user", row["user_id"]),
                        "tenant_id": tenant_id,
                        # **旧 ID を残す。** 外部のバッジシステムが lw2 の user_id で
                        # 付与実績を持っており（`BadgeApi` は /tenant/{id}/user/{id}/badges）、
                        # これが無いと新環境から「誰のバッジか」を引けない（A24）
                        "legacy_id": int(row["user_id"]),
                        "login_id": row.get("login_id"),
                        "email": email,
                        "mobile_email": row.get("mobile_mail_add"),
                        # 3DES 復号 → bcrypt。入れられないものは空になる（下で警告）
                        "password_hash": passwords.hash_for(row.get("password"), int(row["user_id"]))
                        or "",
                        "name": name or None,
                        "name_last": row.get("name_sei"),
                        "name_first": row.get("name_mei"),
                        "name_kana_last": row.get("kana_sei"),
                        "name_kana_first": row.get("kana_mei"),
                        "nickname": row.get("nick_name"),
                        "language_code": row.get("_language"),
                        "gender": row.get("sex_type"),
                        "blood_type": row.get("blood_type"),
                        "self_introduction": row.get("self_introduction"),
                        "phone": row.get("tel"),
                        "mobile_phone": row.get("mobile_tel"),
                        "birth_year": year,
                        "birth_month": month,
                        "birth_day": day,
                        "role": _role_of(row, role_map),
                        "status": _status_of(row),
                        "is_valid": _valid(row),
                        "is_new": bool(row.get("new_user_chk")),
                        "member_no": row.get("_member_no"),
                        # **ロールに畳まない。** 旧は role_id=6 に付く追加フラグ
                        "is_career_counselor": bool(row.get("_career_counselor")),
                        "avatar_url": None,  # 画像は移行対象外
                        "login_start_date": convert_date(
                            row.get("entry_date"), ColumnKind.DATE, DateBoundary.START
                        ),
                        "login_end_date": convert_date(
                            row.get("limit_date"), ColumnKind.DATE, DateBoundary.END
                        ),
                        "admin_memo": row.get("user_memo"),
                        "external_data": row.get("system_data"),
                        "last_login_at": convert(row.get("recent_login_date"), ColumnKind.DATETIME),
                        "last_access_at": convert(row.get("recent_access_time"), ColumnKind.DATETIME),
                        "total_login_count": int(row.get("total_login_count") or 0),
                        "password_changed_at": convert_date(
                            row.get("password_change_date"), ColumnKind.DATE
                        ),
                        "is_lockout": bool(row.get("is_lockout")),
                        "failed_login_started_at": convert(
                            row.get("start_date_failing_login"), ColumnKind.DATETIME
                        ),
                        "failed_login_count": int(row.get("number_of_failing_login") or 0),
                        "created_at": convert(row.get("regist_date"), ColumnKind.TIMESTAMP),
                        "updated_at": convert(row.get("update_date"), ColumnKind.TIMESTAMP),
                    },
                    natural_key=("tenant_id", "email"),
                    source_key=int(row["user_id"]),
                )
            )
        self._password_summary = passwords.summary()
        self._password_unusable = passwords.unusable
        return records


    def run(self, ctx: RunContext):
        result = super().run(ctx)
        password_note = getattr(self, "_password_summary", None)
        if password_note:
            result.note(f"パスワード: {password_note}")
            ctx.logger.info("パスワード: %s", password_note)
        unusable = getattr(self, "_password_unusable", [])
        if unusable:
            # **エラーにならない失敗。** 空のハッシュで入るとログインだけができない
            ctx.logger.warning(
                "パスワードが入らない会員が %d 名いる（ログインできない状態で移る）: %s",
                len(unusable),
                unusable[:20],
            )
        return result


class ExternalUserLinksStep(Step):
    """旧 `user.user_id` と新 `users.id` の対応表を作る。

    **会員の突き合わせはここだけが担う**（ブリッジは users.id をランダム ULID で
    採番するため、ID からは辿れない）。`external_system` の値は ETL・ブリッジ・
    テストの3か所で揃える。
    """

    name = "external_user_links"
    description = "lw2 の user_id と新 users.id の対応表を作る"
    source_table = "user"
    target_table = "external_user_links"
    depends_on = ("users",)

    def extract(self, ctx: RunContext) -> list[dict]:
        return ctx.require_source().fetch_for_tenant("user", ("user_id", "regist_date"))

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        return [
            Record(
                table="external_user_links",
                values={
                    "id": ctx.ulid.for_row("external_user_link", row["user_id"]),
                    "tenant_id": tenant_id,
                    "user_id": ctx.ulid.for_row("user", row["user_id"]),
                    "external_system": EXTERNAL_SYSTEM,
                    "external_id": str(row["user_id"]),
                    # **NOT NULL**。旧に「連携した日時」は無いので会員の登録日を入れる
                    "linked_at": convert(row.get("regist_date"), ColumnKind.DATETIME),
                },
                natural_key=("tenant_id", "external_system", "external_id"),
                source_key=int(row["user_id"]),
            )
            for row in rows
        ]


def _role_of(row: dict, role_map) -> str | None:
    """`user.role_id` を新環境のロールに写す。

    **NULL は既定値に倒さない。** `users.role` は NOT NULL なので、その会員は
    移らず一覧に出る。どのロールにするかは移行の外で決める判断で、
    黙って倒すと**権限が静かに変わる**。
    """
    value = row.get("role_id")
    if value is None:
        return None
    return role_map.to_new(int(value))


def _valid(row: dict) -> bool:
    """`valid_chk`（1 有効 / 0 無効）。**NULL のときだけ有効とみなす。**

    `int(valid_chk or 1)` と書くと **0 が 1 に化け、無効の会員が有効として入る**
    （ステージングで2名。旧 DB との突き合わせで判明）。
    """
    value = row.get("valid_chk")
    return True if value is None else int(value) == 1


def _status_of(row: dict) -> str:
    """`del_chk` / `valid_chk` / 期間から `users.status` を決める。

    **元の列は残す**（`is_valid` / `login_start_date` / `login_end_date`）。
    status はあくまで判定結果で、ここに畳むわけではない。
    """
    if int(row.get("del_chk") or 0) == 1:
        return "deleted"
    if not _valid(row):
        return "inactive"
    return "active"


def build() -> list[Step]:
    return [UsersStep(), ExternalUserLinksStep()]
