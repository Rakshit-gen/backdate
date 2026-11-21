"use client";

import { useScene } from "./SceneProvider";

/** Says where the numbers on the page come from. Always visible, never small print. */
export function SourceNote() {
  const { source, scene, busy } = useScene();
  if (source.kind === "live") {
    const c = scene.clock.computations;
    return (
      <div className="source live" role="status">
        <p>
          <strong>Live.</strong> Reading the backend at version {scene.clock.version}: {c.fresh} results fresh,{" "}
          {c.stale + c.pending} waiting{busy ? ", workers busy" : ""}
          {c.failed ? `, ${c.failed} failed` : ""}.
        </p>
      </div>
    );
  }
  return (
    <div className="source recording" role="status">
      <p>
        <strong>Recording.</strong> No backend is connected, so this page shows a capture of a real run made on{" "}
        {new Date(source.recordedAt).toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" })}.{" "}
        {source.note}
        {source.problem ? <> The backend was configured but failed: {source.problem}.</> : null} To make it live, run{" "}
        <code>web/scripts/backend.sh --fresh</code> and then <code>pnpm dev</code>.
      </p>
    </div>
  );
}
