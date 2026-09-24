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


def _settings(ctx: RunContext, site: dict | None) -> str:
    """旧 `site` の運用値を `tenants.settings` に入れる（A3）。

    **新環境に対応する機能が無くても移す**（[移行の原則](../../docs/00-template/review.md)の1）。
    値が無い列は入れない — 空のキーを並べても読む側が判断できない。

    - `service`  … サービス名・説明・提供期間・サイト URL
    - `features` … 旧のバッチ・機能フラグ（`lw_type` / テスト分析 / ランキング / 日次メール）
    """
    if not site:
        return "{}"

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
    if service:
        settings["service"] = service
    settings["features"] = features
    ctx.logger.info("site の運用値を tenants.settings に入れる: %s", sorted(settings))
    return json.dumps(settings, ensure_ascii=False)


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
                    "legacy_id": config.tenant.legacy_id,
                    "slug": config.tenant.slug,
                    "name": name,
                    "short_name": row.get("tenent_name_short"),
                    "language_code": (row.get("language_code") or "ja"),
                    "db_type": "shared",
                    "plan_id": None,
                    "custom_domain": None,
                    "settings": _settings(ctx, row.get("_site")),
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
