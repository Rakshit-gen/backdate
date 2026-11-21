// Saves what the running web app reads from the live backend into src/data/recording.json.
// The page shows that recording, labelled as one, when no backend is configured.
import { writeFileSync } from "node:fs";

const base = process.env.WEB_URL ?? "http://localhost:3100";
const res = await fetch(`${base}/api/scene`);
if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
const scene = await res.json();
const recordedAt = new Date().toISOString();
const note =
  "Recorded from a real run: 20 seeded employees, then one raise for employee 7 backdated " +
  "to 1 March through the API, then a worker pass. Nothing in it is made up.";
writeFileSync(
  new URL("../src/data/recording.json", import.meta.url),
  JSON.stringify({ recordedAt, note, scene }, null, 1) + "\n",
);
console.log(`saved recording at version ${scene.clock.version}`);
