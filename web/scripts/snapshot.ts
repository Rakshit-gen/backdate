// Saves what the running web app reads from the live backend into src/data/recording.json.
// The page shows that recording, labelled as one, when no backend is configured.
import { writeFileSync } from "node:fs";

const base = process.env.WEB_URL ?? "http://localhost:3100";
const res = await fetch(`${base}/api/scene`);
if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
const scene = await res.json();
const recordedAt = new Date().toISOString();
type Change = { attribute: string; from: string };
const NAMES: Record<string, string> = { annual_salary_cents: "salary", fte_bp: "FTE", state: "state" };
const day = (iso: string) =>
  new Date(`${iso}T00:00:00Z`).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });
const corrections = (scene.changesets as { version: number; changes: Change[] }[])
  .slice(1)
  .map(
    (c) =>
      `v${c.version} changed the ${c.changes.map((x) => `${NAMES[x.attribute] ?? x.attribute} from ${day(x.from)}`).join(" and ")}`,
  );
// Every employee has 12 gross and 12 withholding results.
const employees = (Object.values(scene.clock.computations) as number[]).reduce((a, b) => a + b, 0) / 24;
const note =
  `It has ${employees} seeded employees and ${corrections.length} corrections to employee ${scene.employee}` +
  (corrections.length ? `: ${corrections.join(", ")}` : "") +
  ". Workers recomputed after each one.";
writeFileSync(
  new URL("../src/data/recording.json", import.meta.url),
  JSON.stringify({ recordedAt, note, scene }, null, 1) + "\n",
);
console.log(`saved recording at version ${scene.clock.version}`);
