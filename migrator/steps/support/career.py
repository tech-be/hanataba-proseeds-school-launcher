"""support.6 — 就業支援。会員どうしの記録（助言メモ・スカウトのフォロー）と、career の DB に書くもの。

2026-09-30 に「その他」から 05 へ仕分けたもの。

**career の DB に書くもの**（docs/db/05-support/migration-spec.md 0-7・0-9。`database = "career"`）:
就活プロフィール・希望勤務地・企業・面談。会員とテナントは btoc の ULID で持つ（DB をまたぐ
外部キーは無い）ので、**btoc に移っていない会員の行は作らない**（一覧に出す）。
お仕事募集（`recruit`）は移行対象外（`out_of_scope.RecruitStep`）。スキルチェックは未実装。

- `personal_record_advice` … 管理者・キャリアカウンセラーが会員に残した助言メモ。
  **既存の `admin_notes`（運営メモ）に寄せる**（対象の会員・書いた人・本文の3つが揃う）
- `follow` … 求人企業（と管理者）が受講者をフォローした記録。受け皿 `scout_follows` を新設した
"""

from __future__ import annotations

from datetime import datetime, time

from ...context import RunContext
from ...core.datetimes import ColumnKind, convert
from ...core.records import Record
from ...core.text import join_name
from ..base import Step

ADVICE_COLUMNS = (
    "personal_record_advice_id", "user_id", "target_user_id", "advice_memo", "del_chk",
    "update_user_id", "regist_date", "update_date",
)
FOLLOW_COLUMNS = ("follow_id", "user_id", "followed_user_id", "register_date", "update_date", "del_chk")


class AdviceNotesStep(Step):
    """助言メモを `admin_notes` に移す。

    **削除済みのメモは移さず一覧に出す**（05 移行仕様 0R-2 Q6）。新は `deleted_at` を読まず、生きたメモとして
    会員の学習状況の画面に出す。
    """

    name = "support.advice_notes"
    description = "会員への助言メモを運営メモとして移す"
    source_table = "personal_record_advice"
    target_table = "admin_notes"
    depends_on = ("users",)

    def extract(self, ctx: RunContext) -> list[dict]:
        kept = []
        for row in ctx.require_source().fetch_for_tenant("personal_record_advice", ADVICE_COLUMNS):
            if int(row.get("del_chk") or 0) == 1:
                self.drop("admin_notes", row["personal_record_advice_id"], "受け皿なし",
                          "削除済みの運営メモ。新は deleted_at を読まず表示する")
                continue
            kept.append(row)
        return kept

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        return [
            Record(
                table="admin_notes",
                values={
                    # 運営メモに旧 ID の列は無い。決定論 ULID で再移行の重複を防ぐ
                    "id": ctx.ulid.for_row("personal_record_advice", int(row["personal_record_advice_id"])),
                    "tenant_id": tenant_id,
                    "user_id": ctx.ulid.for_row("user", int(row["target_user_id"])),
                    "author_id": ctx.ulid.for_row("user", int(row["user_id"])),
                    # 最後に直した人（school-launcher 20260930052453 で足した列）。旧は 0 / NULL = 未更新
                    "updated_by": (
                        ctx.ulid.for_row("user", int(row["update_user_id"]))
                        if int(row.get("update_user_id") or 0) else None
                    ),
                    "body": row.get("advice_memo") or "",
                    "created_at": convert(row.get("regist_date"), ColumnKind.TIMESTAMP),
                    "updated_at": convert(row.get("update_date"), ColumnKind.TIMESTAMP),
                },
                natural_key=("id",),
                source_key=int(row["personal_record_advice_id"]),
            )
            for row in rows
        ]


class ScoutFollowsStep(Step):
    name = "support.scout_follows"
    description = "求人企業による受講者のフォローを移す"
    source_table = "follow"
    target_table = "scout_follows"
    depends_on = ("users",)

    def extract(self, ctx: RunContext) -> list[dict]:
        return ctx.require_source().fetch_for_tenant("follow", FOLLOW_COLUMNS)

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        return [
            Record(
                table="scout_follows",
                values={
                    "id": ctx.ulid.for_row("follow", int(row["follow_id"])),
                    "tenant_id": tenant_id,
                    "follow_id": int(row["follow_id"]),
                    "user_id": ctx.ulid.for_row("user", int(row["user_id"])),
                    "followed_user_id": ctx.ulid.for_row("user", int(row["followed_user_id"])),
                    "deleted_at": (
                        convert(row.get("update_date"), ColumnKind.DATETIME)
                        if int(row.get("del_chk") or 0) == 1 else None
                    ),
                    "created_at": convert(row.get("register_date"), ColumnKind.TIMESTAMP),
                    "updated_at": convert(row.get("update_date"), ColumnKind.TIMESTAMP),
                },
                natural_key=("tenant_id", "follow_id"),
                source_key=int(row["follow_id"]),
            )
            for row in rows
        ]


# --- career の DB ----------------------------------------------------------------

PROFILE_COLUMNS = (
    "user_id", "name_sei", "name_mei", "education", "job_category", "qualification",
    "desired_employment_status", "desired_job_location",
)
#: 旧の希望雇用形態（`employment_status_master`）→ 新の雇用形態
EMPLOYMENT_TYPES = {1: "full_time", 2: "fixed_term", 3: "temporary", 4: "part_time"}
OVERSEAS = 99
NOT_IN_BTOC = "外部キー `user_id`"
NOT_IN_BTOC_DETAIL = "btoc に移っていない会員（career の DB は会員の有無を確かめない）"


def short_prefecture(pref_id: int, table: dict[int, str]) -> str | None:
    """都道府県を新の短い表記にする（「東京都」→「東京」、99 →「海外」）。"""
    if pref_id == OVERSEAS:
        return "海外"
    name = table.get(pref_id)
    if not name:
        return None
    # **末尾の 1 字だけ**落とす（rstrip だと「京都府」が「京」になる）
    return name[:-1] if name != "北海道" and name[-1] in "都府県" else name


def _blank(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def _has_career_data(row: dict) -> bool:
    return bool(
        _blank(row.get("education")) or _blank(row.get("job_category")) or _blank(row.get("qualification"))
        or int(row.get("desired_employment_status") or 0) in EMPLOYMENT_TYPES
        or int(row.get("desired_job_location") or 0) > 0
    )


def _in_btoc(ctx: RunContext, user_ids: list[int]) -> set[int]:
    """btoc に移った会員（この実行で入れた行も含む）。"""
    ulids = {ctx.ulid.for_row("user", u): u for u in user_ids}
    known = ctx.target.known_ids("users", "id", set(ulids))
    return {ulids[k] for k in known}


class CareerProfilesStep(Step):
    """就活プロフィール。**値のある会員だけ**作る。就業状況は空（旧の 2 値と意味が合わない。Q14）。"""

    name = "support.career_profiles"
    description = "就活プロフィール（学歴・職種・資格・希望雇用形態）を career に移す"
    source_table = "user"
    target_table = "learner_career_profiles"
    database = "career"
    depends_on = ("users",)

    def extract(self, ctx: RunContext) -> list[dict]:
        rows = [r for r in ctx.require_source().fetch_for_tenant("user", PROFILE_COLUMNS) if _has_career_data(r)]
        migrated = _in_btoc(ctx, [int(r["user_id"]) for r in rows])
        kept = []
        for row in rows:
            if int(row["user_id"]) in migrated:
                kept.append(row)
            else:
                self.drop(self.target_table, str(row["user_id"]), NOT_IN_BTOC, NOT_IN_BTOC_DETAIL)
        return kept

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        records = []
        for row in rows:
            kind = EMPLOYMENT_TYPES.get(int(row.get("desired_employment_status") or 0))
            records.append(
                Record(
                    table="learner_career_profiles",
                    values={
                        "id": ctx.ulid.for_row("career_profile", int(row["user_id"])),
                        "tenant_id": tenant_id,
                        "user_id": ctx.ulid.for_row("user", int(row["user_id"])),
                        "learner_name": join_name(row.get("name_sei"), row.get("name_mei")),
                        "education": _blank(row.get("education")),
                        "employment_status": "",
                        "job_category": _blank(row.get("job_category")),
                        "qualification": _blank(row.get("qualification")),
                        "desired_employment_types": kind,
                        "desired_prefecture": None,  # 単数の列は使わない（複数の表に入れる）
                    },
                    natural_key=("tenant_id", "user_id"),
                    source_key=int(row["user_id"]),
                )
            )
        return records


class DesiredPrefecturesStep(CareerProfilesStep):
    """希望勤務地（旧は 1 つ）。新の短い表記で `learner_desired_prefectures` に 1 行。"""

    name = "support.desired_prefectures"
    description = "希望勤務地を career に移す"
    target_table = "learner_desired_prefectures"
    depends_on = ("support.career_profiles",)

    def extract(self, ctx: RunContext) -> list[dict]:
        return [r for r in super().extract(ctx) if int(r.get("desired_job_location") or 0) > 0]

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        table = ctx.prefecture_table()
        records = []
        for row in rows:
            prefecture = short_prefecture(int(row["desired_job_location"]), table)
            records.append(
                Record(
                    table="learner_desired_prefectures",
                    values={
                        "id": ctx.ulid.for_row("desired_prefecture", int(row["user_id"])),
                        "tenant_id": tenant_id,
                        "profile_id": ctx.ulid.for_row("career_profile", int(row["user_id"])),
                        "prefecture": prefecture,
                    },
                    natural_key=("id",),
                    source_key=int(row["user_id"]),
                )
            )
        return records


COMPANY_COLUMNS = ("company_id", "company_name", "business_content", "site_url", "regist_date", "update_date", "del_chk")


class CompaniesStep(Step):
    """企業。**`tenant_id` を持たない**ので、会員（`user.company_id`）からたどる。
    業種・連絡先メールは旧に無いので NULL（Q12。career の migration で NULL 可にした）。"""

    name = "support.companies"
    description = "企業を career に移す"
    source_table = "company"
    target_table = "companies"
    database = "career"

    def extract(self, ctx: RunContext) -> list[dict]:
        rows: dict[int, dict] = {}
        for row in ctx.require_source().fetch_joined(
            "company", COMPANY_COLUMNS, parent="user", on="p.company_id = c.company_id"
        ):
            rows.setdefault(int(row["company_id"]), row)  # 1 社に会員が複数いる
        return [rows[k] for k in sorted(rows)]

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        return [
            Record(
                table="companies",
                values={
                    "id": ctx.ulid.for_row("company", int(row["company_id"])),
                    "tenant_id": tenant_id,
                    "name": row.get("company_name") or "",
                    "industry": None,
                    "description": _blank(row.get("business_content")),
                    "website_url": _blank(row.get("site_url")),
                    "contact_email": None,
                    # 削除済みは新の状態 inactive（Q1）
                    "status": "inactive" if int(row.get("del_chk") or 0) == 1 else "active",
                    "created_at": convert(row.get("regist_date"), ColumnKind.TIMESTAMP),
                    "updated_at": convert(row.get("update_date"), ColumnKind.TIMESTAMP),
                },
                natural_key=("id",),
                source_key=int(row["company_id"]),
            )
            for row in rows
        ]


INTERVIEW_COLUMNS = (
    "interview_id", "interview_date", "counselor_user_id", "student_user_id", "interview_content1",
    *(f"interview_content{n}" for n in range(2, 21)),
    "regist_date", "update_date", "del_chk",
)
INTERVIEW_DETAIL_CONTENT = "面談の項目（2 番目以降）。新の記録は要約 1 つ"


def _interviews(ctx: RunContext) -> list[dict]:
    rows = ctx.require_source().fetch_for_tenant("interview_record", INTERVIEW_COLUMNS)
    migrated = _in_btoc(ctx, [int(r[c]) for r in rows for c in ("counselor_user_id", "student_user_id")])
    return [
        r for r in rows
        if int(r["counselor_user_id"]) in migrated and int(r["student_user_id"]) in migrated
    ]


def _interview_start(row: dict) -> datetime | None:
    """面談の日時。**旧は日付だけ**なので、その日の 0 時（JST）にする（2026-10-26 決定）。"""
    day = row.get("interview_date")
    return None if day is None else convert(datetime.combine(day, time(0, 0)), ColumnKind.TIMESTAMP)


class AdvisorsStep(Step):
    """面談の担当者。旧のキャリアカウンセラー（面談の `counselor_user_id`）から作る。"""

    name = "support.advisors"
    description = "面談の担当者を career に作る"
    source_table = "interview_record"
    target_table = "advisors"
    database = "career"
    depends_on = ("users",)

    def extract(self, ctx: RunContext) -> list[dict]:
        counselors = sorted({int(r["counselor_user_id"]) for r in _interviews(ctx)})
        if not counselors:
            return []
        users = {
            int(u["user_id"]): u
            for u in ctx.require_source().fetch_for_tenant("user", ("user_id", "name_sei", "name_mei"))
        }
        return [users[c] for c in counselors if c in users]

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        return [
            Record(
                table="advisors",
                values={
                    "id": ctx.ulid.for_row("advisor", int(row["user_id"])),
                    "tenant_id": tenant_id,
                    "user_id": ctx.ulid.for_row("user", int(row["user_id"])),
                    "name": join_name(row.get("name_sei"), row.get("name_mei")),
                    "status": "active",
                },
                natural_key=("tenant_id", "user_id"),
                source_key=int(row["user_id"]),
            )
            for row in rows
        ]


class InterviewSlotsStep(Step):
    """面談の枠。**旧に枠は無い**ので、面談 1 件に予約済みの枠を 1 つ作る（開始＝終わり。R1）。"""

    name = "support.interview_slots"
    description = "面談の予約済みの枠を career に作る"
    source_table = "interview_record"
    target_table = "availability_slots"
    database = "career"
    depends_on = ("support.advisors",)

    def extract(self, ctx: RunContext) -> list[dict]:
        return _interviews(ctx)

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        return [
            Record(
                table="availability_slots",
                values={
                    "id": ctx.ulid.for_row("interview_slot", int(row["interview_id"])),
                    "tenant_id": tenant_id,
                    "advisor_id": ctx.ulid.for_row("advisor", int(row["counselor_user_id"])),
                    "start_time": _interview_start(row),
                    "end_time": _interview_start(row),
                    "is_booked": True,
                },
                natural_key=("id",),
                source_key=int(row["interview_id"]),
            )
            for row in rows
        ]


class InterviewsStep(Step):
    """面談。過去の面談の記録なので `completed`、目的は `career_consultation`（2026-10-26 決定）。"""

    name = "support.interviews"
    description = "面談を career に移す"
    source_table = "interview_record"
    target_table = "interviews"
    database = "career"
    depends_on = ("support.interview_slots",)

    def extract(self, ctx: RunContext) -> list[dict]:
        rows = _interviews(ctx)
        for row in rows:
            if int(row.get("del_chk") or 0) == 1:
                # 新の面談の状態に削除は無い。件数は 0（ステージング）。出たら扱いを決める
                self.drop(self.target_table, str(row["interview_id"]), "移行対象外", "削除済みの面談（新に当たる状態が無い）")
        return [r for r in rows if int(r.get("del_chk") or 0) == 0]

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        return [
            Record(
                table="interviews",
                values={
                    "id": ctx.ulid.for_row("interview", int(row["interview_id"])),
                    "tenant_id": tenant_id,
                    "slot_id": ctx.ulid.for_row("interview_slot", int(row["interview_id"])),
                    "advisor_id": ctx.ulid.for_row("advisor", int(row["counselor_user_id"])),
                    "learner_user_id": ctx.ulid.for_row("user", int(row["student_user_id"])),
                    "purpose": "career_consultation",
                    "status": "completed",
                    "scheduled_at": _interview_start(row),
                    "created_at": convert(row.get("regist_date"), ColumnKind.TIMESTAMP),
                    "updated_at": convert(row.get("update_date"), ColumnKind.TIMESTAMP),
                },
                natural_key=("id",),
                source_key=int(row["interview_id"]),
            )
            for row in rows
        ]


class InterviewRecordsStep(InterviewsStep):
    """面談の記録。要約は旧の項目 1（キャリア棚卸内容）。空なら空文字。2 番目以降の項目は一覧に出す。"""

    name = "support.interview_records"
    description = "面談の記録を career に移す"
    target_table = "interview_records"
    depends_on = ("support.interviews",)

    def extract(self, ctx: RunContext) -> list[dict]:
        rows = super().extract(ctx)
        for row in rows:
            for n in range(2, 21):
                if _blank(row.get(f"interview_content{n}")):
                    self.drop(self.target_table, f"{row['interview_id']}:{n}", "受け皿なし", INTERVIEW_DETAIL_CONTENT)
        return rows

    def transform(self, ctx: RunContext, rows: list[dict]) -> list[Record]:
        tenant_id = ctx.tenant_id.value
        return [
            Record(
                table="interview_records",
                values={
                    "id": ctx.ulid.for_row("interview_record", int(row["interview_id"])),
                    "tenant_id": tenant_id,
                    "interview_id": ctx.ulid.for_row("interview", int(row["interview_id"])),
                    "advisor_id": ctx.ulid.for_row("advisor", int(row["counselor_user_id"])),
                    "summary": row.get("interview_content1") or "",
                    "created_at": convert(row.get("regist_date"), ColumnKind.TIMESTAMP),
                    "updated_at": convert(row.get("update_date"), ColumnKind.TIMESTAMP),
                },
                natural_key=("interview_id",),
                source_key=int(row["interview_id"]),
            )
            for row in rows
        ]


def build() -> list[Step]:
    from .out_of_scope import RecruitStep

    return [
        AdviceNotesStep(), ScoutFollowsStep(),
        CareerProfilesStep(), DesiredPrefecturesStep(), CompaniesStep(),
        AdvisorsStep(), InterviewSlotsStep(), InterviewsStep(), InterviewRecordsStep(),
        RecruitStep(),
    ]
