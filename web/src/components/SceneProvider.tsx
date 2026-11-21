"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import type { Scene, Source, WriteResult } from "@/lib/types";

type Ctx = {
  source: Source;
  scene: Scene;
  live: boolean;
  /** Version the page last wrote, so sections can show what that write caused. */
  lastWrite: WriteResult | null;
  busy: boolean;
  post: (from: string, salaryCents: number) => Promise<WriteResult>;
};

const SceneContext = createContext<Ctx | null>(null);

export function useScene(): Ctx {
  const ctx = useContext(SceneContext);
  if (!ctx) throw new Error("useScene outside SceneProvider");
  return ctx;
}

const outstanding = (s: Scene) => s.clock.computations.pending + s.clock.computations.stale;

export function SceneProvider({ source, children }: { source: Source; children: React.ReactNode }) {
  const live = source.kind === "live";
  const [scene, setScene] = useState(source.scene);
  const [lastWrite, setLastWrite] = useState<WriteResult | null>(null);
  const [watching, setWatching] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);

  const refresh = useCallback(async () => {
    const res = await fetch(`/api/scene?employee=${source.scene.employee}`, { cache: "no-store" });
    if (!res.ok) throw new Error((await res.json()).error ?? res.statusText);
    const next = (await res.json()) as Scene;
    setScene(next);
    return next;
  }, [source.scene.employee]);

  // Poll while there is recompute work in flight, then stop.
  useEffect(() => {
    if (!live || !watching) return;
    let cancelled = false;
    const tick = async () => {
      try {
        const next = await refresh();
        if (cancelled) return;
        if (outstanding(next) === 0) {
          setWatching(false);
          return;
        }
      } catch {
        // The banner shows backend problems; keep trying while watching.
      }
      if (!cancelled) timer.current = setTimeout(tick, 350);
    };
    tick();
    return () => {
      cancelled = true;
      clearTimeout(timer.current);
    };
  }, [live, watching, refresh]);

  const post = useCallback(
    async (from: string, salaryCents: number) => {
      const res = await fetch("/api/bd/writes", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ employee: source.scene.employee, from, salary_cents: salaryCents }),
      });
      const body = await res.json();
      if (!res.ok) throw new Error(body.error ?? res.statusText);
      setLastWrite(body as WriteResult);
      setWatching(true);
      return body as WriteResult;
    },
    [source.scene.employee],
  );

  return (
    <SceneContext.Provider value={{ source, scene, live, lastWrite, busy: watching, post }}>
      {children}
    </SceneContext.Provider>
  );
}
