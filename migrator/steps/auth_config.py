"""認証まわりの設定（A6 / A8）。

**移行データはほぼ無いが、受け皿は移行と同時に作る**と決めた。

- `sso_config` は1行（IdP 設定）
- `login_limit` は **0行**（recademy は未使用）。テーブルだけ作って cutover 後に運営が設定する
- 2FA（`user_two_factor_secrets`）は**テーブルを作るだけ**。旧 `twostepverification` が持つのは
  発行中の認証コード（平文）で設定ではないため、移す行が無い → Step も無い
"""

from __future__ import annotations

import json

from ..context import RunContext
from ..core.records import Record
from .base import Step

SSO_COLUMNS = ("tenant_id", "sso_type", "sso_parameter")
LOGIN_LIMIT_COLUMNS = ("tenant_id", "youbi_type", "detail_no", "limit_type", "start_time", "end_time")

#: 旧 `sso_config.sso_type`（int）→ `auth_methods.code`。
#: **対応表に無い値は落とさず停止する**ので、実データを見て足すこと
SSO_TYPE_TO_PROVIDER = {1: "saml"}


class SsoConfigStep(Step):
    name = "config.sso"
    description = "SSO（IdP）設定を移す"
    source_table = "sso_config"
    target_table = "tenant_sso_configs"
    depends_on = ("tenant", "master.auth_methods")

    def extract(self, ctx: RunContext) -> list[dict]:
        return ctx.require_source().fetch_for_tenant("sso_config", SSO_COLUMNS)

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        from ..core.codes import CodeMap

        provider_map = CodeMap(
            name="sso_type",
            mapping=SSO_TYPE_TO_PROVIDER,
            source="migrator/steps/auth_config.py（実データを見て足す）",
        )
        tenant_id = ctx.tenant_id.value
        records = []
        for row in rows:
            provider = provider_map.to_new(int(row["sso_type"]))
            records.append(
                Record(
                    table="tenant_sso_configs",
                    values={
                        "id": ctx.ulid.for_row("sso_config", f"{row['tenant_id']}:{row['sso_type']}"),
                        "tenant_id": tenant_id,
                        "provider": provider,
                        "metadata": _as_json(row.get("sso_parameter")),
                        "active": True,
                    },
                    natural_key=("tenant_id", "provider"),
                )
            )
        return records


class LoginWindowsStep(Step):
    name = "config.login_windows"
    description = "曜日・時間帯のログイン制限を移す（recademy は0行）"
    source_table = "login_limit"
    target_table = "tenant_login_windows"
    depends_on = ("tenant",)

    def extract(self, ctx: RunContext) -> list[dict]:
        return ctx.require_source().fetch_for_tenant("login_limit", LOGIN_LIMIT_COLUMNS)

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        return [
            Record(
                table="tenant_login_windows",
                values={
                    "id": ctx.ulid.for_row(
                        "login_limit", f"{row['tenant_id']}:{row['youbi_type']}:{row['detail_no']}"
                    ),
                    "tenant_id": tenant_id,
                    "day_of_week": int(row["youbi_type"]),
                    "limit_type": int(row.get("limit_type") or 0),
                    "start_time": row.get("start_time"),
                    "end_time": row.get("end_time"),
                },
                natural_key=("tenant_id", "day_of_week"),
            )
            for row in rows
        ]


def _as_json(value: object) -> str | None:
    """`sso_parameter`（text）を JSON 列に入れる形にする。

    JSON として読めればそのまま、読めなければ `{"raw": "..."}` で包む
    （**捨てない**。原則3）。
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        json.loads(text)
    except ValueError:
        return json.dumps({"raw": text}, ensure_ascii=False)
    return text


def build() -> list[Step]:
    return [SsoConfigStep(), LoginWindowsStep()]
