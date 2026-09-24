"""フェーズ5 — 会員に紐づくもの。

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

LINE_COLUMNS = ("user_id", "line_id", "regist_date")


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


class UserProfileValuesStep(Step):
    """自由記述（`user_profile1`〜`20`）の値を移す。

    **`item_type=0` の値は `users` の対応列**（フェーズ4）で受けており、ここに入るのは
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
    """通知の受取設定を**極性を反転**して移す。"""

    name = "notification_optouts"
    description = "通知の受取設定を optout に反転して移す"
    source_table = "user"
    target_table = "notification_optouts"
    depends_on = ("users", "master.email_kinds")

    def extract(self, ctx: RunContext) -> list[dict]:
        return ctx.require_source().fetch_for_tenant("user", OPTOUT_COLUMNS)

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        records: list[Record] = []
        for row in rows:
            user_id = ctx.ulid.for_row("user", row["user_id"])
            for optout in optouts_for(row, OPTOUT_SOURCES):
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
    **形式が違うものは移さず、一覧を運営に渡す。**
    """

    name = "line_links"
    description = "LINE の友だち紐付けを移す"
    source_table = "user"
    target_table = "line_links"
    depends_on = ("users",)

    def extract(self, ctx: RunContext) -> list[dict]:
        rows = ctx.require_source().fetch_for_tenant("user", LINE_COLUMNS)
        return [r for r in rows if r.get("line_id")]

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        records: list[Record] = []
        rejected: list[int] = []
        for row in rows:
            line_id = str(row["line_id"]).strip()
            if not (line_id.startswith("U") and len(line_id) == 33):
                rejected.append(int(row["user_id"]))
                continue
            records.append(
                Record(
                    table="line_links",
                    values={
                        "id": ctx.ulid.for_row("line_link", row["user_id"]),
                        "tenant_id": tenant_id,
                        "user_id": ctx.ulid.for_row("user", row["user_id"]),
                        "line_user_id": line_id,
                        # lw2 に友だち状態が無い。TRUE で入れ、初回 push の 403 で落とす
                        "is_friend": True,
                        # **NOT NULL**。旧に「連携した日時」は無いので会員の登録日を入れる
                        "linked_at": convert(row.get("regist_date"), ColumnKind.DATETIME),
                    },
                    natural_key=("tenant_id", "line_user_id"),
                    source_key=int(row["user_id"]),
                )
            )
        if rejected:
            ctx.logger.warning(
                "line_id の形式が違う会員が %d 名いる（移さない。一覧を運営に渡す）: %s",
                len(rejected),
                rejected[:20],
            )
        return records

#: 公開制限。**旧の8列をそのまま `field_code` にする**（決定2）。
#: `user` の6列と、`user_attached_info` の1列。
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
    """会員ごとの公開制限を移す。**旧の列名をそのまま `field_code` にする。**"""

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
