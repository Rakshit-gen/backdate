"use client";

import { useScene } from "./SceneProvider";

/** Says when the numbers on the page come from a recording rather than a running backend. */
export function SourceNote() {
  const { source } = useScene();
  // Live data needs no banner; a recording must always say it is one.
  if (source.kind === "live") return null;
  return (
    <div className="source recording" role="status">
      <p>
        <strong>Recording.</strong> No backend is connected, so this page shows a capture of a real run made on{" "}
        {new Date(source.recordedAt).toLocaleDateString("en-GB", {
          day: "numeric",
          month: "long",
          year: "numeric",
          timeZone: "UTC",
        })}
        . {source.note}
        {source.problem ? <> The backend was configured but failed: {source.problem}.</> : null} To make it live, run{" "}
        <code>web/scripts/backend.sh --fresh</code> and then <code>pnpm dev</code>.
      </p>
    </div>
  );
}
