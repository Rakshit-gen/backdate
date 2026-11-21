// A narrow proxy so the browser never holds the API key. Only the calls the page makes.
import { api, BackendError } from "@/lib/source";

export const dynamic = "force-dynamic";

const READABLE = /^(clock|graph|computations|restatements|changesets)$/;
const WRITES_ON = process.env.BACKDATE_ALLOW_WRITES === "true";
const MAX_SALARY = 100_000_000; // 1,000,000.00 a year

type Ctx = { params: Promise<{ path: string[] }> };

function fail(message: string, status: number) {
  return Response.json({ error: message }, { status });
}

async function forward(path: string, init?: RequestInit) {
  try {
    return Response.json(await api(path, init));
  } catch (e) {
    return fail((e as Error).message, e instanceof BackendError ? 502 : 500);
  }
}

export async function GET(req: Request, { params }: Ctx) {
  const path = (await params).path.join("/");
  if (!READABLE.test(path)) return fail("not available through this proxy", 404);
  return forward(`${path}${new URL(req.url).search}`);
}

/** Only one kind of write: a salary change for one employee from a date onwards. */
export async function POST(req: Request, { params }: Ctx) {
  if ((await params).path.join("/") !== "writes") return fail("not available through this proxy", 404);
  if (!WRITES_ON) return fail("writes are turned off on this deployment (BACKDATE_ALLOW_WRITES)", 403);
  const body = (await req.json().catch(() => null)) as {
    employee?: unknown;
    from?: unknown;
    salary_cents?: unknown;
  } | null;
  const { employee, from, salary_cents } = body ?? {};
  if (
    !Number.isInteger(employee) ||
    typeof from !== "string" ||
    !/^2024-(0[1-9]|1[0-2])-01$/.test(from) ||
    !Number.isInteger(salary_cents) ||
    (salary_cents as number) <= 0 ||
    (salary_cents as number) > MAX_SALARY
  ) {
    return fail("expected {employee, from: 2024-MM-01, salary_cents: 1..100000000}", 400);
  }
  return forward("writes", {
    method: "POST",
    body: JSON.stringify({
      reason: "salary correction from the web demo",
      ops: [
        {
          op: "assert",
          entity: `employee:${employee}`,
          attribute: "annual_salary_cents",
          from,
          value: salary_cents,
        },
      ],
    }),
  });
}
