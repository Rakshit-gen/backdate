// Server only. Reads the backend when BACKDATE_API_URL is set, otherwise a recording.
import recording from "@/data/recording.json";
import type { Restatement, Scene, Source } from "./types";

const API = process.env.BACKDATE_API_URL?.replace(/\/$/, "");
const TOKEN = process.env.BACKDATE_TOKEN ?? "";
export const EMPLOYEE = Number(process.env.BACKDATE_EMPLOYEE ?? 7);

export class BackendError extends Error {}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  if (!API) throw new BackendError("BACKDATE_API_URL is not set");
  let res: Response;
  try {
    res = await fetch(`${API}/v1/${path}`, {
      ...init,
      cache: "no-store",
      headers: { authorization: `Bearer ${TOKEN}`, "content-type": "application/json", ...init?.headers },
      signal: AbortSignal.timeout(5000),
    });
  } catch (e) {
    throw new BackendError(`could not reach ${API}: ${(e as Error).message}`);
  }
  if (!res.ok) throw new BackendError(`${path} returned ${res.status}: ${await res.text()}`);
  return res.json() as Promise<T>;
}

async function allRestatements(prefix: string): Promise<Restatement[]> {
  const out: Restatement[] = [];
  let cursor = "0.0";
  for (let page = 0; page < 50; page++) {
    const r = await api<{ restatements: Restatement[]; cursor: string }>(
      `restatements?limit=1000&cursor=${cursor}`,
    );
    out.push(...r.restatements.filter((x) => x.computation.key.startsWith(prefix)));
    if (r.restatements.length < 1000) break;
    cursor = r.cursor;
  }
  return out;
}

export async function loadScene(employee = EMPLOYEE): Promise<Scene> {
  const e = `employee:${employee}`;
  const prefix = `${employee}:`;
  const [clock, salary, fte, state, graph, comps, restatements, changesets] = await Promise.all([
    api<Scene["clock"]>("clock"),
    api<Scene["salary"]>(`facts/${e}/annual_salary_cents/history`),
    api<Scene["fte"]>(`facts/${e}/fte_bp/history`),
    api<Scene["state"]>(`facts/${e}/state/history`),
    api<Scene["graph"]>(`graph?key_prefix=${prefix}`),
    api<{ computations: Scene["computations"] }>(`computations?key_prefix=${prefix}&limit=200`),
    allRestatements(prefix),
    api<{ changesets: Scene["changesets"] }>("changesets?limit=500"),
  ]);
  return {
    employee,
    clock,
    salary,
    fte,
    state,
    graph,
    computations: comps.computations,
    restatements,
    changesets: changesets.changesets.filter((c) => c.changes.some((x) => x.entity === e)),
  };
}

export async function getSource(): Promise<Source> {
  const rec = recording as unknown as { recordedAt: string; note: string; scene: Scene };
  if (!API) return { kind: "recording", scene: rec.scene, recordedAt: rec.recordedAt, note: rec.note };
  try {
    return { kind: "live", scene: await loadScene() };
  } catch (e) {
    return {
      kind: "recording",
      scene: rec.scene,
      recordedAt: rec.recordedAt,
      note: rec.note,
      problem: (e as Error).message,
    };
  }
}
