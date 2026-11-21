// What the most recent correction to the employee did, derived from one Scene.
import { affectedBy } from "./scene";
import type { Changeset, Restatement, Scene } from "./types";

export type Story = {
  change: Changeset;
  stale: number;
  restated: Restatement[];
  grossDelta: number;
  withholdingDelta: number;
  pending: number;
};

const num = (d: Restatement["delta"], k: string) => (d && typeof d === "object" ? (d[k] ?? 0) : 0);

/** The latest changeset that corrected something already known (not the first entry). */
export function latestCorrection(scene: Scene): Changeset | undefined {
  const first = scene.changesets[0]?.version;
  return [...scene.changesets].reverse().find((c) => c.version !== first);
}

export function story(scene: Scene, change = latestCorrection(scene)): Story | null {
  if (!change) return null;
  const restated = scene.restatements.filter(
    (r) => r.seq > 1 && (r.from_version ?? 0) < change.version && r.to_version >= change.version,
  );
  return {
    change,
    stale: affectedBy(change, scene.graph).size,
    restated,
    grossDelta: restated.reduce((s, r) => s + num(r.delta, "gross_cents"), 0),
    withholdingDelta: restated.reduce((s, r) => s + num(r.delta, "withholding_cents"), 0),
    pending: scene.computations.filter((c) => c.status === "stale" || c.status === "pending").length,
  };
}

export function signed(cents: number): string {
  const s = (Math.abs(cents) / 100).toLocaleString("en-US", { minimumFractionDigits: 2 });
  return cents > 0 ? `+${s}` : cents < 0 ? `−${s}` : s;
}
