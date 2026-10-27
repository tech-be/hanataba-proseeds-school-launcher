"""foundation.2 — 会員に紐づくもの。

`users` の行が揃ってから流す。どの Step も `users` の ULID を
`ctx.ulid.for_row("user", 旧user_id)` で引く（対応表を引き直さない）。
"""

from __future__ import annotations

from ..context import RunContext
from ..core.codes import prefecture_name
from ..core.datetimes import ColumnKind, convert
from ..core.polarity import Channel, OptoutSource, optouts_for
from ..core.records import Record
from .base import Step

ADDRESS_COLUMNS = (
    "user_id",
    "zip_code",
    "pref_id",
    "city_name",
    "address",
    "zip_code2",
    "pref_id2",
    "city_name2",
    "address2",
)

#: 住所2組。用途は lw2 側で定義されていないため primary / secondary で持つ
ADDRESS_SETS = (
    ("primary", "zip_code", "pref_id", "city_name", "address"),
    ("secondary", "zip_code2", "pref_id2", "city_name2", "address2"),
)

#: 国籍と海外住所（`user_nationality_info`）。**`user` とは別テーブル**なので join で引く。
#: 海外住所は都道府県を持たないため `kind='foreign'` の3組目として入れる
NATIONALITY_COLUMNS = (
    "user_id",
    "nationality",
    "nationality_another",
    "country",
    "country_another",
    "foreign_zip_code",
    "foreign_city_name",
    "foreign_address",
)

PROFILE_VALUE_COLUMNS = ("user_id",) + tuple(f"user_profile{i}" for i in range(1, 21))

#: 通知の受取フラグ。**極性を反転**して optout にする。PC / 携帯は channel で分ける
OPTOUT_SOURCES = (
    OptoutSource("sendmail_pc_chk", "announcement", Channel.PC),
    OptoutSource("sendmail_mobile_chk", "announcement", Channel.MOBILE),
    OptoutSource("sendmail_scout_chk", "scout", Channel.PC),
    OptoutSource("notify_footprint_pc_chk", "footprint", Channel.PC),
    OptoutSource("notify_footprint_mobile_chk", "footprint", Channel.MOBILE),
)
OPTOUT_COLUMNS = ("user_id",) + tuple(s.column for s in OPTOUT_SOURCES)

#: 会員の状態（`users._status_of`）を決める列も読む。有効でない会員には送らない（05 移行仕様 0R-2 Q3）
LINE_COLUMNS = ("user_id", "line_id", "regist_date", "del_chk", "valid_chk", "entry_date", "limit_date", "is_lockout")

#: 会員の個別番号とスカウトでの名前の出し方（U2）。旧は `user_id` が主キー
PERSONAL_NO_COLUMNS = ("user_id", "regist_no", "personal_no", "scout_display_type")

#: 旧 `scout_display_type` → `scout_display_types.code`。旧は数値の直書きで、
#: 0 名前 / 1 ニックネーム / 2 個別番号（旧 `UserModel.class.php` の会員検索）
SCOUT_DISPLAY_TYPES = {0: "name", 1: "nickname", 2: "personal_no"}


class UserAddressesStep(Step):
    """住所2組を4項目（郵便番号 / 都道府県 / 市区町村 / 番地・建物名）で移す。"""

    name = "user_addresses"
    description = "住所2組を種別付きで移す"
    source_table = "user"
    target_table = "user_addresses"
    depends_on = ("users",)

    def extract(self, ctx: RunContext) -> list[dict]:
        source = ctx.require_source()
        rows = source.fetch_for_tenant("user", ADDRESS_COLUMNS)
        # 国籍・海外住所は別テーブル。**ここで合流させる**（後から UPDATE を流さない）
        foreign = {
            int(r["user_id"]): r
            for r in source.fetch_joined(
                "user_nationality_info",
                NATIONALITY_COLUMNS,
                parent="user",
                on="c.user_id = p.user_id",
            )
        }
        for row in rows:
            row["_foreign"] = foreign.get(int(row["user_id"]))
        return rows

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        prefs = ctx.prefecture_table()
        countries = ctx.country_table()
        tenant_id = ctx.tenant_id.value
        records: list[Record] = []
        for row in rows:
            user_id = ctx.ulid.for_row("user", row["user_id"])
            for kind, zip_col, pref_col, city_col, street_col in ADDRESS_SETS:
                if not any(row.get(c) for c in (zip_col, pref_col, city_col, street_col)):
                    continue  # 空の組は作らない
                records.append(
                    Record(
                        table="user_addresses",
                        values={
                            "id": ctx.ulid.for_row("user_address", f"{row['user_id']}:{kind}"),
                            "tenant_id": tenant_id,
                            "user_id": user_id,
                            "kind": kind,
                            "postal_code": row.get(zip_col),
                            # コード値のまま入れない。都道府県名に展開する
                            "prefecture": prefecture_name(row.get(pref_col), prefs),
                            "city": row.get(city_col),
                            "street": row.get(street_col),
                            "country": None,
                            "nationality": None,
                        },
                        natural_key=("user_id", "kind"),
                        source_key=int(row["user_id"]),
                    )
                )
            records += _foreign_address(ctx, row, tenant_id, user_id, countries)
        return records


def _foreign_address(
    ctx: RunContext, row: dict, tenant_id: str, user_id: str, countries: dict[str, str]
) -> list[Record]:
    """国籍と海外住所を `kind='foreign'` の1行にする。

    旧は `nationality` / `country` が**コード**（`country_master`）で、選択肢に無い値を
    `*_another` に自由入力する作り。**コードは国名に展開して入れる**（`AR` のまま入れると
    画面にコードが出る）。自由入力はそのまま。海外住所は都道府県を持たないので
    `prefecture` は NULL。
    """

    def name_of(code: object, free_text: object) -> str | None:
        if str(free_text or "").strip():
            return str(free_text)
        key = str(code or "").strip()
        if not key:
            return None
        return countries.get(key, key)  # 対応表に無いコードはそのまま残す（落とさない）

    info = row.get("_foreign")
    if not info:
        return []
    country = name_of(info.get("country"), info.get("country_another"))
    nationality = name_of(info.get("nationality"), info.get("nationality_another"))
    postal_code = info.get("foreign_zip_code")
    city = info.get("foreign_city_name")
    street = info.get("foreign_address")
    if not any(str(v or "").strip() for v in (country, nationality, postal_code, city, street)):
        return []
    return [
        Record(
            table="user_addresses",
            # **列の並びは住所1・2と同じにする。** 同じバッチで INSERT するため
            values={
                "id": ctx.ulid.for_row("user_address", f"{row['user_id']}:foreign"),
                "tenant_id": tenant_id,
                "user_id": user_id,
                "kind": "foreign",
                "postal_code": postal_code,
                "prefecture": None,  # 海外住所に都道府県は無い
                "city": city,
                "street": street,
                "country": country,
                "nationality": nationality,
            },
            natural_key=("user_id", "kind"),
            source_key=int(row["user_id"]),
        )
    ]


class UserPersonalNumbersStep(Step):
    """会員の個別番号を `user_personal_numbers` に移す（U2）。

    **番号は旧の値のまま。** 新システムは新しい会員に「テナント内の `regist_no` の最大 + 1」を
    振るので、旧の `regist_no` も持ち込まないと番号が重なる。`personal_no` は新では文字列。
    NULL・重複は表の NOT NULL / UNIQUE に当たり、その行は移らない（一覧に出る）。
    """

    name = "user_personal_numbers"
    description = "会員の個別番号とスカウトでの名前の出し方を移す"
    source_table = "user_personal_no"
    target_table = "user_personal_numbers"
    depends_on = ("users",)

    def extract(self, ctx: RunContext) -> list[dict]:
        return ctx.require_source().fetch_joined(
            "user_personal_no", PERSONAL_NO_COLUMNS, parent="user", on="c.user_id = p.user_id"
        )

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        records: list[Record] = []
        for row in sorted(rows, key=lambda r: int(r["user_id"])):
            personal_no = row.get("personal_no")
            records.append(
                Record(
                    table="user_personal_numbers",
                    values={
                        "id": ctx.ulid.for_row("user_personal_number", row["user_id"]),
                        "tenant_id": tenant_id,
                        "user_id": ctx.ulid.for_row("user", row["user_id"]),
                        "regist_no": row.get("regist_no"),
                        "personal_no": None if personal_no is None else str(personal_no),
                        "scout_display_type": _scout_display_type(row.get("scout_display_type")),
                    },
                    natural_key=("tenant_id", "user_id"),
                    source_key=int(row["user_id"]),
                )
            )
        return records


def _scout_display_type(value: object) -> str | None:
    """旧の数値を code にする。**対応表に無い値は既定（名前）に倒さない。**

    `scout_display_type` は NOT NULL なので、その会員の行は移らず一覧に出る。
    """
    if value is None:
        return None
    return SCOUT_DISPLAY_TYPES.get(int(value))


class UserProfileValuesStep(Step):
    """自由記述（`user_profile1`〜`20`）の値を移す。

    **`item_type=0` の値は `users` の対応列**（`users` Step）で受けており、ここに入るのは
    `item_type=1` の自由記述だけ。項目との対応は `profile_item.item_no` で取る。
    """

    name = "user_profile_values"
    description = "自由記述プロフィールの値を移す"
    source_table = "user"
    target_table = "user_profile_values"
    depends_on = ("users", "config.profile_items")

    def extract(self, ctx: RunContext) -> list[dict]:
        return ctx.require_source().fetch_for_tenant("user", PROFILE_VALUE_COLUMNS)

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        records: list[Record] = []
        for row in rows:
            user_id = ctx.ulid.for_row("user", row["user_id"])
            for no in range(1, 21):
                value = row.get(f"user_profile{no}")
                if value is None or str(value).strip() == "":
                    continue
                item_key = f"1:{no}"  # item_type=1 の item_no
                records.append(
                    Record(
                        table="user_profile_values",
                        values={
                            "id": ctx.ulid.for_row("user_profile_value", f"{row['user_id']}:{no}"),
                            "tenant_id": tenant_id,
                            "user_id": user_id,
                            "item_id": ctx.ulid.for_row("profile_item", item_key),
                            "value": value,
                        },
                        natural_key=("user_id", "item_id"),
                        source_key=int(row["user_id"]),
                    )
                )
        return records


class NotificationOptoutsStep(Step):
    """通知の受取設定を**極性を反転**して移す。

    **携帯の受け取り設定（`channel = 'mobile'`）は移さず一覧に出す**（2026-10-26 決定。移行対象外）。
    新は携帯のアドレスに送らず、受け取り設定の `channel` も見ない。移すと、携帯だけ止めていた会員の
    その種類の通知が、PC も LINE も止まって見える（ステージングでお知らせ 2,653 行）。
    """

    name = "notification_optouts"
    description = "通知の受取設定を optout に反転して移す"
    source_table = "user"
    target_table = "notification_optouts"
    depends_on = ("users", "master.email_kinds")

    def extract(self, ctx: RunContext) -> list[dict]:
        rows = ctx.require_source().fetch_for_tenant("user", OPTOUT_COLUMNS)
        for row in rows:
            for optout in optouts_for(row, OPTOUT_SOURCES):
                if optout.channel is Channel.MOBILE:
                    self.drop("notification_optouts", f"{row['user_id']}:{optout.kind}:{optout.channel.value}",
                              "移行対象外", "携帯の受け取り設定。新は携帯のアドレスに送らず、channel を見ない")
        return rows

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        records: list[Record] = []
        for row in rows:
            user_id = ctx.ulid.for_row("user", row["user_id"])
            for optout in optouts_for(row, OPTOUT_SOURCES):
                if optout.channel is Channel.MOBILE:
                    continue  # 抽出で一覧に出した（移行対象外）
                key = f"{row['user_id']}:{optout.kind}:{optout.channel.value}"
                records.append(
                    Record(
                        table="notification_optouts",
                        values={
                            "id": ctx.ulid.for_row("notification_optout", key),
                            "tenant_id": tenant_id,
                            "user_id": user_id,
                            "kind": optout.kind,
                            "channel": optout.channel.value,
                        },
                        natural_key=("tenant_id", "user_id", "kind", "channel"),
                        source_key=int(row["user_id"]),
                    )
                )
        return records


class LineLinksStep(Step):
    """LINE の友だち紐付けを移す（公式アカウントを継続する決定のため移行対象）。

    `line_links.line_user_id` は Messaging API の userId（`U` で始まる33文字）。
    **形式が違うものは移さず、理由を付けて一覧に出す**（05 移行仕様 0R-2 Q1）。

    **新は会員の状態を見ずに `is_friend = TRUE` の人へ送る。** 削除済み・利用停止の会員の紐付けは
    `is_friend = FALSE` で入れる（値は残すが送らない。Q3）。同じ ID の重なりは補正データで直す（Q2）。
    """

    name = "line_links"
    description = "LINE の友だち紐付けを移す"
    source_table = "user"
    target_table = "line_links"
    depends_on = ("users",)

    def extract(self, ctx: RunContext) -> list[dict]:
        rows = ctx.require_source().fetch_for_tenant("user", LINE_COLUMNS)
        kept = []
        for row in rows:
            if not row.get("line_id"):
                continue
            if not is_line_user_id(str(row["line_id"]).strip()):
                self.drop("line_links", row["user_id"], "旧データの不整合",
                          "LINE の ID の形が違う（Messaging API の userId は `U` ＋ 32 文字）")
                continue
            kept.append(row)
        return kept

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        from .users import _status_of, _today_jst

        today = _today_jst()
        records: list[Record] = []
        for row in rows:
            line_id = str(row["line_id"]).strip()
            records.append(
                Record(
                    table="line_links",
                    values={
                        "id": ctx.ulid.for_row("line_link", row["user_id"]),
                        "tenant_id": tenant_id,
                        "user_id": ctx.ulid.for_row("user", row["user_id"]),
                        "line_user_id": line_id,
                        # lw2 に友だち状態が無い。TRUE で入れ、初回 push の 403 で落とす。
                        # **有効でない会員は FALSE**（新は会員の状態を見ずに送る。Q3）
                        "is_friend": _status_of(row, today) == "active",
                        # **NOT NULL**。旧に「連携した日時」は無いので会員の登録日を入れる
                        "linked_at": convert(row.get("regist_date"), ColumnKind.DATETIME),
                    },
                    natural_key=("tenant_id", "line_user_id"),
                    source_key=int(row["user_id"]),
                )
            )
        return records


def is_line_user_id(value: str) -> bool:
    """Messaging API の userId の形（`U` ＋ 32 文字）。"""
    return value.startswith("U") and len(value) == 33


#: 公開制限。`user` の `*_open_chk` 6列を、それぞれ短いコード（列名から `_open_chk` を
#: 除いたもの）の `field_code` にする（決定2）。他の表からは読まない。
VISIBILITY_SOURCES = (
    ("profile_open_chk", "profile"),
    ("name_open_chk", "name"),
    ("address_open_chk", "address"),
    ("birthday_open_chk", "birthday"),
    ("diary_open_chk", "diary"),
    ("lesson_open_chk", "lesson"),
)
VISIBILITY_COLUMNS = ("user_id",) + tuple(c for c, _ in VISIBILITY_SOURCES)


class UserFieldVisibilityStep(Step):
    """会員ごとの公開制限を移す。**旧の列名から `_open_chk` を除いた名前を `field_code` にする。**"""

    name = "user_field_visibility"
    description = "プロフィールの公開制限を移す"
    source_table = "user"
    target_table = "user_field_visibility"
    depends_on = ("users",)

    def extract(self, ctx: RunContext) -> list[dict]:
        return ctx.require_source().fetch_for_tenant("user", VISIBILITY_COLUMNS)

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        records: list[Record] = []
        for row in rows:
            user_id = ctx.ulid.for_row("user", row["user_id"])
            for column, field_code in VISIBILITY_SOURCES:
                value = row.get(column)
                if value is None:
                    continue  # 未設定は行を作らない（既定に任せる）
                records.append(
                    Record(
                        table="user_field_visibility",
                        values={
                            "id": ctx.ulid.for_row(
                                "user_field_visibility", f"{row['user_id']}:{field_code}"
                            ),
                            "tenant_id": tenant_id,
                            "user_id": user_id,
                            "field_code": field_code,
                            # **極性は反転しない。** lw2 の *_open_chk は「公開する」で、
                            # 新環境の visible も「公開する」。通知（optout）とは違う
                            "visible": bool(int(value)),
                        },
                        natural_key=("user_id", "field_code"),
                        source_key=int(row["user_id"]),
                    )
                )
        return records


def build() -> list[Step]:
    """1-2 ユーザ。**LINE は含めない** — 区分はサポート機能（5-1）。"""
    return [
        UserAddressesStep(),
        UserPersonalNumbersStep(),
        UserProfileValuesStep(),
        UserFieldVisibilityStep(),
        NotificationOptoutsStep(),
    ]


def line_links() -> list[Step]:
    """5-1 LINE 友だち紐付け。

    **書き込み先は会員に紐づく表だが、区分はサポート機能。** 移行計画の分類に合わせる。
    会員（1-2）が入っていることが前提。
    """
    return [LineLinksStep()]
