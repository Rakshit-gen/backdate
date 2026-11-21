// Saves what the running web app reads from the live backend into src/data/recording.json.
// The page shows that recording, labelled as one, when no backend is configured.
import { writeFileSync } from "node:fs";

const base = process.env.WEB_URL ?? "http://localhost:3100";
const res = await fetch(`${base}/api/scene`);
if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
const scene = await res.json();
const recordedAt = new Date().toISOString();
type Change = { attribute: string; from: string };
const corrections = (scene.changesets as { version: number; changes: Change[] }[])
  .slice(1)
  .map((c) => `v${c.version} changes ${c.changes.map((x) => `${x.attribute} from ${x.from}`).join(", ")}`);
const note =
  `Recorded from a real run at version ${scene.clock.version}: seeded employees, then ` +
  (corrections.length
    ? `these corrections to employee ${scene.employee}: ${corrections.join("; ")}. `
    : "no corrections. ") +
  "Workers recomputed after each one. Nothing in it is made up.";
writeFileSync(
  new URL("../src/data/recording.json", import.meta.url),
  JSON.stringify({ recordedAt, note, scene }, null, 1) + "\n",
);
console.log(`saved recording at version ${scene.clock.version}`);
