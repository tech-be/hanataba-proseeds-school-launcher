import { type APIRequestContext, type Page, expect } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

/** scripts/prepare_e2e_users.py apply が書く値（コミットしない）。 */
export type Persona = {
  user_id: number;
  id: string;
  email: string | null;
  login_id: string | null;
  status: string;
  role: string;
  personal_no: string | null;
  tags: string[];
  disabled_kinds: string[];
  legacy_login_id?: string | null;
  legacy_email?: string | null;
};

/** 区分 05 の E2E が見比べる ID（移行先の値。個人情報は含まない）。 */
export type SupportFacts = {
  announcements: Record<string, string[]>;
  admin_announcement: string | null;
  coupons: Array<{ code: string; status: string }>;
  inquiries?: string[];
  discussion_posts?: Array<{ id: string; lesson_id: string }>;
  interviews?: string[];
};

/** 区分 02 の E2E が見比べる ID（移行先の値）。 */
export type ContentFacts = {
  course: { id: string } | null;
  text_lesson: { id: string; course_id: string } | null;
  live_lesson: { id: string; course_id: string } | null;
  paths: string[];
  quiz_lesson?: { id: string; course_id: string } | null;
  survey_lesson?: { id: string } | null;
  assignment_course?: { course_id: string } | null;
  quiz_lessons?: string[];
};

/** 区分 03 の E2E が見比べる値（移行先の値）。 */
export type EnrollmentFacts = {
  settings: { serial_next: number; serial_format: string; max_serial: number | null } | null;
  path_member: { id: string } | null;
  completer?: { active: string[]; completed: { course_id: string } | null; expired: string[] };
  certificates?: Array<{ course_id: string; serial_no: number; serial_text: string }>;
  quiz?: { quiz_id: string; attempts: number } | null;
  submission?: { id: string; assignment_id: string; status: string; result: string } | null;
  survey?: { lesson_id: string } | null;
  survey_open?: { lesson_id: string } | null;
};

/** 区分 04 の E2E が見比べる値（移行先の値）。 */
export type BillingFacts = {
  payments: string[];
  rules: string[];
  grants?: Array<{ id: string; ticket_type_id: string; remaining_quantity: number }>;
  receipts?: string[];
  reservations?: string[];
  path_courses?: string[];
};

/** 区分 05 の残りの E2E が見比べる値（移行先の値）。 */
export type RemainingFacts = {
  open_folders: string[];
  folders: string[];
  notes: Array<{ id: string; user_id: string }>;
};

type Personas = {
  tenant: { slug: string; name: string };
  personas: Record<string, Persona>;
  support?: SupportFacts;
  content?: ContentFacts;
  enrollment?: EnrollmentFacts;
  billing?: BillingFacts;
  remaining?: RemainingFacts;
};

const PERSONAS_FILE = path.resolve(__dirname, ".personas.json");

function load(): Personas {
  if (!fs.existsSync(PERSONAS_FILE)) {
    throw new Error("e2e/.personas.json が無い。先に scripts/prepare_e2e_users.py apply を流す");
  }
  return JSON.parse(fs.readFileSync(PERSONAS_FILE, "utf8"));
}

const data = load();
export const TENANT = data.tenant;
export const SUPPORT: SupportFacts | undefined = data.support;
export const CONTENT: ContentFacts | undefined = data.content;
export const ENROLLMENT: EnrollmentFacts | undefined = data.enrollment;
export const BILLING: BillingFacts | undefined = data.billing;
export const REMAINING: RemainingFacts | undefined = data.remaining;

/** 一覧の API の返り値から配列を取り出す（`{data: [...]}` / `{items: [...]}` / 配列のどれか）。 */
export function listOf<T = Record<string, unknown>>(body: unknown): T[] {
  if (Array.isArray(body)) return body as T[];
  const b = body as { data?: T[]; items?: T[] };
  return b?.data ?? b?.items ?? [];
}

/** 役の会員。用意していない役なら、そのテストを飛ばせるよう undefined を返す。 */
export function persona(name: string): Persona | undefined {
  return data.personas[name];
}

/** テスト用のパスワード（環境変数。リポジトリに書かない）。 */
export const PASSWORD = (() => {
  const value = process.env.E2E_PASSWORD ?? "";
  if (value.length < 8) throw new Error("E2E_PASSWORD にテスト用のパスワードを入れる");
  return value;
})();

/** パスワードの変更・再設定で入れる値。新の規則（10 文字以上・英字と数字）を満たす。 */
export const NEW_PASSWORD = `${PASSWORD}Nw2x`;

export const MAILPIT = process.env.MAILPIT_URL ?? "http://localhost:8025";

/** ログインの識別子。メールが無ければログイン ID。 */
export function identifier(p: Persona): string {
  const value = p.email ?? p.login_id;
  if (!value) throw new Error(`user_id ${p.user_id} にメールもログイン ID も無い`);
  return value;
}

export function tenantHeaders(token?: string): Record<string, string> {
  return {
    "X-Tenant-Slug": TENANT.slug,
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

/** POST /auth/login。429 は待って押し直す（新システムの e2e/helpers.ts の apiLogin と同じ）。 */
export async function loginRequest(request: APIRequestContext, email: string, password = PASSWORD) {
  for (let attempt = 1; attempt <= 4; attempt++) {
    const resp = await request.post("/api/v1/auth/login", {
      headers: tenantHeaders(),
      data: { email, password },
    });
    if (resp.status() !== 429) return resp;
    await new Promise((r) => setTimeout(r, 500 * attempt));
  }
  throw new Error(`login が 429 のまま: ${email}`);
}

export async function apiLogin(request: APIRequestContext, p: Persona, password = PASSWORD): Promise<string> {
  const resp = await loginRequest(request, identifier(p), password);
  expect(resp.status(), `user_id ${p.user_id} がログインできない`).toBe(200);
  return (await resp.json()).token;
}

export async function getJson(request: APIRequestContext, url: string, token?: string) {
  const resp = await request.get(url, { headers: tenantHeaders(token) });
  expect(resp.status(), `GET ${url}`).toBe(200);
  return resp.json();
}

/** Cookie の同意の帯がボタンを覆うので、先に同意済みにしておく（新システムの global-setup と同じ）。 */
export async function acceptCookieConsent(page: Page) {
  await page.addInitScript(() => {
    try {
      localStorage.setItem("cookie-consent-accepted", "2026-01-01T00:00:00.000Z");
    } catch {
      /* ignore */
    }
  });
}

/** 画面からログインする。 */
export async function uiLogin(page: Page, id: string, password = PASSWORD) {
  await acceptCookieConsent(page);
  await page.goto("/login");
  await page.fill("#email", id);
  await page.fill("#password", password);
  await page.getByRole("button", { name: "ログイン", exact: true }).click();
}

/** mailpit に届いた、パスワードの再設定のトークン（新システムの 65 の spec と同じ取り方）。 */
export async function waitForResetToken(request: APIRequestContext, email: string, since: number) {
  for (let i = 0; i < 30; i++) {
    const search = await request.get(`${MAILPIT}/api/v1/search?query=${encodeURIComponent(`to:${email}`)}`);
    if (search.ok()) {
      const messages = ((await search.json()).messages ?? []) as Array<{ ID: string; Created: string }>;
      for (const m of messages) {
        if (Date.parse(m.Created) < since) continue;
        const body = await (await request.get(`${MAILPIT}/api/v1/message/${m.ID}`)).json();
        const hit = /token=([0-9a-f]+)/.exec(`${body.Text ?? ""}${body.HTML ?? ""}`);
        if (hit) return hit[1];
      }
    }
    await new Promise((r) => setTimeout(r, 1000));
  }
  throw new Error("パスワードの再設定のメールが mailpit に届かない");
}
