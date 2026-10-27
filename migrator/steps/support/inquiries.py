"""support.4 — 問い合わせ（`inquire` / `inquire_answer`）を `inquiries` に移す。

docs/db/05-support/migration-spec.md 0-4・0-9。

- テナントは**分類（`inquire_cate.tenant_id`）でたどる**（`inquire` は `tenant_id` を持たない）
- 旧の `inquire_answer` は 1 行が「質問＋回答」。**新は 1 往復だけ**なので 1 行目を移し、
  2 往復目以降は一覧に出す
- 回答がある → `resolved`、無い → `open`
- 削除済みは `deleted_at`（新の状態に当たるものが無いので列を足した。school-launcher
  `20261026120000_add_inquiry_deleted_at.sql`）
- ログインしていない人の問い合わせ（`inquire_user_id = 0`）は `user_id` が NOT NULL に当たり、
  制約の確認で一覧に出る（メールで会員に結ぶと値を作ることになるので結ばない）
- 分類は新の既定の 5 つを入れ、旧の分類を設定 `mappings.inquiry_category` の対応表で寄せる
"""

from __future__ import annotations

from ...context import RunContext
from ...core.datetimes import ColumnKind, convert
from ...core.records import Record
from ...errors import ConfigError, MappingError
from ..base import Step

#: 新の既定の分類（school-launcher `inquiry/domain/inquiry_category.go` の DefaultCategories と同じ）。
#: **`other` は必須**（分類の判定が外れたときの行き先。無いと新しい問い合わせが 500 になる）
DEFAULT_CATEGORIES = (
    ("course_content", "講座内容についてのご質問", 10, True),
    ("payment", "購入・お支払いについてのご質問", 20, False),
    ("environment", "動作環境・操作についてのご質問", 30, False),
    ("account", "お手続き・アカウントについてのご質問", 40, False),
    ("other", "その他のご質問", 50, False),
)

INQUIRE_COLUMNS = (
    "inquire_id", "inquire_cate_id", "inquire_user_id", "inquire_start_time",
    "regist_date", "update_date", "del_chk",
)
ANSWER_COLUMNS = (
    "inquire_answer_id", "inquire_id", "answer_user_id", "inquire_detail", "answer_detail",
    "answer_end_time", "del_chk",
)
FILE_COLUMNS = (
    *(f"inquire_save_file_name{n}" for n in range(1, 4)),
    *(f"answer_save_file_name{n}" for n in range(1, 4)),
)

NO_PLACE = "受け皿なし"
SECOND_ROUND_DETAIL = "2 往復目以降のやり取り。新の問い合わせは 1 往復だけ"
DELETED_ANSWER_DETAIL = "削除済みのやり取り"
NOT_MIGRATED = "移行対象外"
NO_FILE_DETAIL = "添付のファイルは移せない（2026-10-26 決定）"


def category_map(ctx: RunContext) -> dict[int, str]:
    raw = (ctx.config.mappings.get("inquiry_category") or {}).get("values") or {}
    if not raw:
        raise ConfigError(
            "問い合わせの分類の対応表が設定に無い（mappings.inquiry_category。"
            "docs/db/05-support/migration-spec.md 0-9 の Q9）"
        )
    codes = {c for c, *_ in DEFAULT_CATEGORIES}
    unknown = sorted(str(v) for v in raw.values() if v not in codes)
    if unknown:
        raise ConfigError(f"問い合わせの分類の対応表に新の既定に無い分類がある: {unknown}")
    return {int(k): str(v) for k, v in raw.items()}


class InquiryCategoriesStep(Step):
    """新の既定の分類を入れる。**新は分類が 0 件のテナントにだけ既定を入れる**ので、移行で入れる。"""

    name = "support.inquiry_categories"
    description = "問い合わせの分類（新の既定の 5 つ）を入れる"
    target_table = "inquiry_categories"

    def extract(self, ctx: RunContext) -> list[dict]:
        return [
            {"code": code, "name_ja": name, "sort_order": order, "notify": notify}
            for code, name, order, notify in DEFAULT_CATEGORIES
        ]

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        return [
            Record(
                table="inquiry_categories",
                values={
                    "tenant_id": tenant_id,
                    "code": row["code"],
                    "name_ja": row["name_ja"],
                    "sort_order": row["sort_order"],
                    "notify_course_admins": row["notify"],
                    "is_system": True,
                    "active": True,
                },
                natural_key=("tenant_id", "code"),
            )
            for row in rows
        ]


def _answers(ctx: RunContext) -> list[dict]:
    return ctx.require_source().fetch_joined(
        "inquire_answer", ANSWER_COLUMNS, parent="inquire_cate",
        on="i.inquire_cate_id = p.inquire_cate_id",
        via=[("inquire", "i", "c.inquire_id = i.inquire_id")],
    )


class InquiriesStep(Step):
    name = "support.inquiries"
    description = "問い合わせ（1 往復目）を移す"
    source_table = "inquire"
    target_table = "inquiries"
    depends_on = ("support.inquiry_categories", "users")

    def extract(self, ctx: RunContext) -> list[dict]:
        mapping = category_map(ctx)
        rows = ctx.require_source().fetch_joined(
            "inquire", INQUIRE_COLUMNS, parent="inquire_cate", on="c.inquire_cate_id = p.inquire_cate_id"
        )
        by_inquiry: dict[int, list[dict]] = {}
        for answer in sorted(_answers(ctx), key=lambda a: int(a["inquire_answer_id"])):
            key = f"inquire_answer:{answer['inquire_answer_id']}"
            if int(answer.get("del_chk") or 0) == 1:
                self.drop("inquiries", key, NO_PLACE, DELETED_ANSWER_DETAIL)
                continue
            by_inquiry.setdefault(int(answer["inquire_id"]), []).append(answer)
        for row in rows:
            cate = int(row["inquire_cate_id"])
            if cate not in mapping:
                raise MappingError(f"問い合わせの分類 {cate} の行き先が対応表に無い（mappings.inquiry_category）")
            row["_category"] = mapping[cate]
            answers = by_inquiry.get(int(row["inquire_id"]), [])
            row["_first"] = answers[0] if answers else {}
            for extra in answers[1:]:
                self.drop("inquiries", f"inquire_answer:{extra['inquire_answer_id']}", NO_PLACE, SECOND_ROUND_DETAIL)
        return rows

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        records = []
        for row in rows:
            first = row["_first"]
            resolution = (first.get("answer_detail") or "").strip() or None
            answered_by = int(first.get("answer_user_id") or 0)
            user = int(row.get("inquire_user_id") or 0)
            records.append(
                Record(
                    table="inquiries",
                    values={
                        "id": ctx.ulid.for_row("inquire", int(row["inquire_id"])),
                        "tenant_id": tenant_id,
                        # ログインしていない人（0）は NULL のまま NOT NULL に当たって一覧に出る
                        "user_id": ctx.ulid.for_row("user", user) if user else None,
                        "session_id": None,
                        "ai_session_id": None,
                        "category_code": row["_category"],
                        "status": "resolved" if resolution else "open",
                        "question": first.get("inquire_detail") or "",
                        "assignee_id": ctx.ulid.for_row("user", answered_by) if resolution and answered_by else None,
                        "resolution": first.get("answer_detail") if resolution else None,
                        "resolved_at": convert(first.get("answer_end_time"), ColumnKind.DATETIME) if resolution else None,
                        "deleted_at": (
                            convert(row.get("update_date"), ColumnKind.DATETIME)
                            if int(row.get("del_chk") or 0) == 1 else None
                        ),
                        "created_at": convert(
                            row.get("inquire_start_time") or row.get("regist_date"), ColumnKind.TIMESTAMP
                        ),
                        "updated_at": convert(row.get("update_date"), ColumnKind.TIMESTAMP),
                    },
                    natural_key=("id",),
                    source_key=int(row["inquire_id"]),
                )
            )
        return records


class InquiryAttachmentsStep(Step):
    """添付。**ファイルを移せない**ので、ファイルごとに一覧に出す。"""

    name = "support.inquiry_attachments"
    description = "問い合わせの添付（移さない。一覧に出す）"
    source_table = "inquire_answer"

    def extract(self, ctx: RunContext) -> list[dict]:
        for row in ctx.require_source().fetch_joined(
            "inquire_answer", ("inquire_answer_id", *FILE_COLUMNS), parent="inquire_cate",
            on="i.inquire_cate_id = p.inquire_cate_id",
            via=[("inquire", "i", "c.inquire_id = i.inquire_id")],
        ):
            for column in FILE_COLUMNS:
                if (row.get(column) or "").strip():
                    self.drop("inquiries", f"inquire_answer:{row['inquire_answer_id']}:{column}", NOT_MIGRATED, NO_FILE_DETAIL)
        return []

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        return []


def build() -> list[Step]:
    return [InquiryCategoriesStep(), InquiriesStep(), InquiryAttachmentsStep()]
