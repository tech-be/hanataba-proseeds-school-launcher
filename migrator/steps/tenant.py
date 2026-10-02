"""フェーズ1 — `tenants` の1行。

**移行全体の起点。** ここで採番した `tenants.id` が全テーブルの `tenant_id` になる。

- 新環境にはシード値しか無いので、行は**移行側で新規に作る**
- `slug` は `recademy` 固定（既存ツールが `-tenant recademy` で引く）
- `status` は `active` を**明示**する（列の既定値は `trial`）
- **投入前に `name` で既登録を確認する**。`tenants.name` に UNIQUE が無く、
  同じ名前の行を何行でも作れてしまうため（slug の UNIQUE 違反を冪等性の担保にしない）
"""

from __future__ import annotations

import json

from ..context import RunContext
from ..core.datetimes import ColumnKind, convert
from ..core.records import Record, StepResult
from ..errors import PreflightError
from .base import Step

#: 旧 `site` から読む列（A3）。**接続情報4列は禁止列**なので含めない。
#: `site` は**インストール全体で1行**（テナント別ではない）。新環境の相当物が
#: テナント単位の `settings` なので、移行対象テナントの設定として入れる
SITE_COLUMNS = (
    "site_id",
    "site_url",
    "application_path",
    "lw_type",
    "service_name",
    "description",
    "service_start_date",
    "service_end_date",
    "test_analysis",
    "user_ranking_flg",
    "daily_mail_send_flg",
)

#: 旧 `payment_infomation` から読む列（P13。課金 04 の暫定の規則）。
#: **`agreement` は読まない** — 旧が使っていない古い列で、本文は `agreement` 表が正。
#: 規約の URL・表題の上書きは `tenant_legal_documents`（billing.3）に入れる
PAYMENT_INFO_COLUMNS = (
    "is_use_bank", "bank_account_information", "is_use_credit_card", "is_use_convenience",
    "is_visa", "is_mastercard", "is_jcb", "is_amex", "is_diners",
    "is_use_split_payment", "use_split_payment_number", "is_use_memo", "payment_trigger_media_chk",
)

#: 旧 `tenant` から読む列。**禁止列は含めない**（ガードが落とす）
SOURCE_COLUMNS = (
    "tenant_id",
    "tenant_code",
    "tenant_name",
    "tenent_name_short",  # 旧側の綴り誤り。新環境では short_name
    "language_code",
    "del_chk",
    "regist_date",
)


def _payment_settings(info: dict | None, receipt: dict | None) -> dict:
    """旧の決済まわりのテナント設定（P13）。**新の決済処理は読まない**（記録として残す）。"""
    if not info and not receipt:
        return {}
    info = info or {}
    flag = lambda key: bool(int(info.get(key) or 0))  # noqa: E731
    out = {
        "methods": {
            "bank": flag("is_use_bank"), "credit_card": flag("is_use_credit_card"),
            "convenience": flag("is_use_convenience"),
        },
        "card_brands": [
            brand for brand, key in (("visa", "is_visa"), ("mastercard", "is_mastercard"),
                                     ("jcb", "is_jcb"), ("amex", "is_amex"), ("diners", "is_diners"))
            if flag(key)
        ],
        # カード会社の分割で選べる回数（カンマ区切り）
        "card_installments": [
            int(n) for n in str(info.get("use_split_payment_number") or "").split(",") if n.strip().isdigit()
        ] if flag("is_use_split_payment") else [],
        "ask_memo": flag("is_use_memo"),
        "ask_trigger_media": flag("payment_trigger_media_chk"),
    }
    bank = (info.get("bank_account_information") or "").strip()
    if bank:
        out["bank_account_information"] = bank
    if receipt is not None:
        out["receipt_invoice_chk"] = bool(int(receipt.get("invoice_chk") or 0))
    return out


#: テナントの設定（2026-09-30 に 01 へ仕分け）。どれもテナントに1行で、**新に対応する列が無い**ので
#: `tenants.settings` にキーごとに入れる。**秘密の値は読まない**（下の除外を参照）
#:
#: `application_config` から**読まない列**:
#: - `special_pass_word` … 平文の認証情報（**移行できないもの**。01 review「移行の対象外 A」）
#: - `kanri_db_name` … 旧の接続先 DB 名（**移行できないもの**。`site` の接続情報と同じ扱い）
#: - `line_channel_sercret` / `send_line_chanel_token` … LINE の秘密の値。`tenant_secrets` に移す
#:   （`tenant_config.TenantSecretsStep`）
APP_CONFIG_COLUMNS = (
    "group_row_max_no",
    "disp_no_per_page",
    "is_userbbs_regist",
    "is_profile_group_open",
    "rank_flg",
    "all_rank_flg",
    "enable_friendship",
    "enable_attendance",
    "is_locked_user_is_open_diary",
    "is_locked_user_is_open_lesson",
    "enable_live",
    "enable_staff",
    "enable_adminbbs",
    "viewable_pass_word",
    "enablesso",
    "enablesso_password",
    "mobile_link_visible",
    "kaisha_menu_label",
    "enable_credit",
    "multh_login",
    "is_instructor_regist_chk",
    "is_use_big_alphabet_password",
    "is_use_small_alphabet_password",
    "is_use_num_password",
    "is_use_mark_password",
    "min_password_num",
    "inspect_name_share_type",
    "inspect_profile_share_type",
    "logo_file_name",
    "favicon_file_name",
    "ios_icon_file_name",
    "from_mail_name",
    "from_mail_address",
    "shop_code",
    "volume_type",
    "lang_chk",
    "ssl_chk",
    "ssl_lesson_chk",
    "disp_max_page",
    "twostep_chk",
    "twostep_role_chk",
    "twostep_date_span",
    "twostep_message",
    "bg_image_chk_login",
    "bg_image_path_login",
    "bg_img_file_name_login",
    "blur_bg_chk_login",
    "bg_image_chk",
    "bg_image_path",
    "bg_img_file_name",
    "blur_bg_chk",
    "authority_bg_color",
    "no_authority_bg_color",
    "base_color",
    "alert_color",
    "alert_bg_color",
    "header_bg_color",
    "footer_bg_color",
    "new_image_chk",
    "new_image",
    "free_image_chk",
    "free_image",
    "login_footer_link",
    "login_limit_count",
    "name_view_setting",
    "enable_support",
    "enable_mail_setting_edit",
    "news_mail_send",
    "allowed_ip",
    "allowed_ip_admin",
    "enable_lesson_banner",
    "badge_chk",
    "another_inquire_url",
    "cashback_chk",
    "tutorial_chk",
    "footprint_chk",
    "coupon_chk",
    "free_login_term",
    "portfolio_open_chk",
    "payment_update_chk",
    "unit_mail_day",
    "unit_mail_hour",
    "third_secure_chk",
    "line_chk",
    "line_id",
    "line_channel_id",
    "interview_chk",
    "remote_lesson_chk",
)
ACCOUNT_SETTING_COLUMNS = (
    "password_has_lower", "password_has_upper", "password_has_number", "password_has_symbol",
    "min_password_length", "password_is_not_same_as_id", "password_validity_period",
    "password_update_use_reminder", "password_update_first_login", "enable_after_update",
    "viewable_password", "enable_lockout", "lockout_period", "lockout_limit",
)
LOGIN_SETTING_COLUMNS = (
    "data_type", "message1", "message2", "message3", "message4", "message5",
    "site_environment_chk", "account_register_chk", "login_keep_chk", "passwd_reminder_chk",
    "image1", "image2", "image3", "image4", "image5", "password_reminder_chk",
    "login_dialog_valid_chk", "login_dialog_title", "title_bg_color", "message_bg_color",
    "login_dialog_message", "login_dialog_next", "login_dialog_close_label",
    "pass_change_limit_chk", "pass_change_limit_date_num", "pass_change_later_chk",
    "first_login_chk", "first_login_message",
)
REGISTRATION_SETTING_COLUMNS = ("message", "image1", "image2", "image3", "regist_date", "update_date")
TOP_PARTS_COLUMNS = (
    "top_parts_setting_id", "top_parts_code", "data_type", "col", "row", "title_chk",
    "data_num", "param1", "param2", "del_chk", "regist_date",
)
FUNCTION_DEFAULT_COLUMNS = (
    "function_default_id", "sort_no", "valid_chk", "disp_title", "unified_menu_chk",
    "menu_bg_color", "left_menu_file_name", "head_menu_file_name_on", "head_menu_file_name_off",
)
FUNCTION_ADMIN_TENANT_COLUMNS = ("function_admin_id", "valid_chk")
FUNCTION_ADMIN_ROLE_COLUMNS = ("function_admin_id", "role_id", "valid_chk")


def _tenant_settings(ctx: RunContext) -> dict:
    """テナントの設定6種を `tenants.settings` のキーにする。**行が無いものはキーを作らない。**"""
    source = ctx.require_source()

    def one(table: str, columns: tuple[str, ...]) -> dict | None:
        """主キーが `tenant_id` だけの表（テナントに1行）。"""
        rows = source.fetch_for_tenant(table, columns)
        return dict(rows[0]) if rows else None

    def many(table: str, columns: tuple[str, ...]) -> list[dict]:
        return [dict(r) for r in source.fetch_for_tenant(table, columns)]

    out = {
        "lw2_config": one("application_config", APP_CONFIG_COLUMNS),
        "lw2_account": one("account_setting", ACCOUNT_SETTING_COLUMNS),
        # **主キーが (tenant_id, data_type)。** 種別ごとに複数行あり得るので全行を種別の順に持つ
        "lw2_login": sorted(many("login_setting", LOGIN_SETTING_COLUMNS),
                            key=lambda r: int(r.get("data_type") or 0)) or None,
        "lw2_registration": one("registration_setting", REGISTRATION_SETTING_COLUMNS),
        "lw2_top_parts": many("top_parts_setting", TOP_PARTS_COLUMNS) or None,
        "lw2_functions": {
            "menu": many("function_default_tenant", FUNCTION_DEFAULT_COLUMNS),
            "admin_tenant": many("function_admin_tenant", FUNCTION_ADMIN_TENANT_COLUMNS),
            "admin_role": many("function_admin_role", FUNCTION_ADMIN_ROLE_COLUMNS),
        },
    }
    if not any(out["lw2_functions"].values()):
        out["lw2_functions"] = None
    return {k: v for k, v in out.items() if v is not None}


def _settings(
    ctx: RunContext, site: dict | None, payment: dict | None = None, extra: dict | None = None
) -> str:
    """旧 `site` の運用値を `tenants.settings` に入れる（A3）。

    **新環境に対応する機能が無くても移す**（[移行の原則](../../docs/00-template/review.md)の1）。
    値が無い列は入れない — 空のキーを並べても読む側が判断できない。

    - `service`  … サービス名・説明・提供期間・サイト URL
    - `features` … 旧のバッチ・機能フラグ（`lw_type` / テスト分析 / ランキング / 日次メール）
    - `lw2_*`    … テナントの設定（`_tenant_settings`）。秘密の値は含まない
    """
    extra = extra or {}
    if not site:
        base = {"lw2_payment": payment} if payment else {}
        base.update(extra)
        return json.dumps(base, ensure_ascii=False, default=str) if base else "{}"

    def clean(key: str):
        value = site.get(key)
        if value is None:
            return None
        text = str(value).strip() if not isinstance(value, (int,)) else value
        return text if text != "" else None

    service = {
        k: v
        for k, v in {
            "name": clean("service_name"),
            "description": clean("description"),
            "url": clean("site_url"),
            "application_path": clean("application_path"),
            "start_date": _date(site.get("service_start_date")),
            "end_date": _date(site.get("service_end_date")),
        }.items()
        if v is not None
    }
    features = {
        k: bool(int(site.get(v) or 0))
        for k, v in {
            "test_analysis": "test_analysis",
            "user_ranking": "user_ranking_flg",
            "daily_mail": "daily_mail_send_flg",
        }.items()
    }
    features["lw_type"] = int(site.get("lw_type") or 0)

    settings = {"legacy_site_id": int(site["site_id"])}
    if payment:
        settings["lw2_payment"] = payment
    if service:
        settings["service"] = service
    settings["features"] = features
    settings.update(extra)
    ctx.logger.info("site の運用値とテナントの設定を tenants.settings に入れる: %s", sorted(settings))
    return json.dumps(settings, ensure_ascii=False, default=str)


def _date(value) -> str | None:
    return None if value is None else str(value)


class TenantStep(Step):
    name = "tenant"
    description = "tenants の1行を作り、tenant_id を確定させる"
    source_table = "tenant"
    target_table = "tenants"

    def extract(self, ctx: RunContext) -> list[dict]:
        source = ctx.require_source()
        rows = source.fetch_for_tenant("tenant", SOURCE_COLUMNS)
        if len(rows) != 1:
            raise PreflightError(f"旧 tenant が1行ではない（{len(rows)} 行）。移行対象の確定が先")
        # サービス名・提供期間・機能フラグ（A3）。**1行を1回の INSERT で完成させる**
        site = source.fetch_global("site", SITE_COLUMNS)
        rows[0]["_site"] = site[0] if site else None
        # 決済まわりの設定（P13）。どちらもテナントに1行
        info = source.fetch_for_tenant("payment_infomation", PAYMENT_INFO_COLUMNS)
        receipt = source.fetch_for_tenant("receipt_setting", ("invoice_chk",))
        rows[0]["_payment"] = _payment_settings(info[0] if info else None, receipt[0] if receipt else None)
        # テナントの設定6種（秘密の値は読まない）
        rows[0]["_tenant_settings"] = _tenant_settings(ctx)
        return rows

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        row = rows[0]
        config = ctx.config

        name = (row.get("tenant_name") or "").strip() or (config.tenant.name or "").strip()
        if not name:
            raise PreflightError(
                "tenant_name が NULL / 空で、設定にも name が無い。"
                "tenants.name は NOT NULL なので投入値を運営に決めてもらう"
            )
        if int(row.get("del_chk") or 0) == 1:
            raise PreflightError("旧テナントが削除済み（del_chk=1）。移行方針から見直す")

        legacy_code = (row.get("tenant_code") or "").strip()
        if legacy_code and legacy_code != config.tenant.slug:
            # 止めはしない（slug は新環境側の確定値）が、必ず記録に残す
            ctx.logger.warning(
                "旧 tenant_code %r が slug %r と違う。旧値を捨ててよいか運営に確認すること",
                legacy_code,
                config.tenant.slug,
            )

        tenant_id = ctx.tenant_id.resolve(
            ctx.ulid.for_row("tenant", row["tenant_id"], created_at_ms(row.get("regist_date")))
        )
        return [
            Record(
                table="tenants",
                values={
                    "id": tenant_id,
                    # 旧 ID。バッジ API の URL が /tenant/{lw2 の tenant_id}/... （A24）
                    "tenant_id": config.tenant.legacy_id,
                    "slug": config.tenant.slug,
                    "name": name,
                    "short_name": row.get("tenent_name_short"),
                    "language_code": (row.get("language_code") or "ja"),
                    "db_type": "shared",
                    "plan_id": None,
                    "custom_domain": None,
                    "settings": _settings(
                        ctx, row.get("_site"), row.get("_payment"), row.get("_tenant_settings")
                    ),
                    "status": "active",
                    "created_at": convert(row.get("regist_date"), ColumnKind.TIMESTAMP),
                },
                natural_key=("slug",),
            )
        ]

    def load(self, ctx: RunContext, records: list[Record]) -> int:
        if not records:
            # 制約に当たって1件も残らなかった。**ここでは落とさない** —
            # 何が当たったかは `out/not-migrated.csv` に出ており、
            # tenant_id は `run()` が移行先から引き直す
            return 0
        record = records[0]
        self._guard_duplicate_name(ctx, str(record.values["name"]))
        return ctx.target.insert_many(records)

    def run(self, ctx: RunContext) -> StepResult:
        result = super().run(ctx)
        if result.loaded == 0:
            # 既に行がある（再実行）。tenant_id を DB から引き直して確定させる
            rows = ctx.target.query(
                "SELECT id FROM tenants WHERE slug = %s", (ctx.config.tenant.slug,)
            )
            if rows:
                ctx.tenant_id.resolve(str(rows[0]["id"]))
                result.note("既存の tenants 行を使う（再実行）")
        result.note(f"tenant_id = {ctx.tenant_id.value if ctx.tenant_id.resolved else '未確定'}")
        return result

    @staticmethod
    def _guard_duplicate_name(ctx: RunContext, name: str) -> None:
        rows = ctx.target.query(
            "SELECT id, slug FROM tenants WHERE name = %s", (name,)
        )
        others = [r for r in rows if r.get("slug") != ctx.config.tenant.slug]
        if others:
            raise PreflightError(
                f"同じ name のテナントが既にある: {others}。"
                "tenants.name に UNIQUE は無く、二重に作れてしまうので投入前に解消する"
            )


def created_at_ms(value: object) -> int | None:
    """旧 `regist_date` を ULID の時刻部（ms）にする。フェーズ1と bootstrap で同じ値を使う。"""
    from datetime import datetime

    if not isinstance(value, datetime):
        return None
    return int(convert(value, ColumnKind.TIMESTAMP).timestamp() * 1000)  # type: ignore[union-attr]
