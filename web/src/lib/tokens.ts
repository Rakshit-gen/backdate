"use client";

import { useMemo, useSyncExternalStore } from "react";

export type Tokens = { paper: string; sheet: string; ruling: string; graphite: string; carbon: string; redpen: string };

const FALLBACK: Tokens = {
  paper: "#0d1124",
  sheet: "#141932",
  ruling: "#252d50",
  graphite: "#e4e8f6",
  carbon: "#9fb0ff",
  redpen: "#ff7b6c",
};

function read(): Tokens {
  const css = getComputedStyle(document.documentElement);
  const get = (name: keyof Tokens) => css.getPropertyValue(`--${name}`).trim() || FALLBACK[name];
  return {
    paper: get("paper"),
    sheet: get("sheet"),
    ruling: get("ruling"),
    graphite: get("graphite"),
    carbon: get("carbon"),
    redpen: get("redpen"),
  };
}

function subscribeTo(query: string) {
  return (onChange: () => void) => {
    const mq = matchMedia(query);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  };
}

const stores = new Map<string, (onChange: () => void) => () => void>();

/** Whether a media query matches. False on the server and during hydration. */
export function useMedia(query: string): boolean {
  if (!stores.has(query)) stores.set(query, subscribeTo(query));
  return useSyncExternalStore(
    stores.get(query)!,
    () => matchMedia(query).matches,
    () => false,
  );
}

const noop = () => () => {};

/** False while rendering on the server and hydrating, true after. */
export const useHydrated = () =>
  useSyncExternalStore(
    noop,
    () => true,
    () => false,
  );

/** The page's colour tokens, read from CSS once hydrated, for use in WebGL. */
export function useTokens(): Tokens {
  const hydrated = useHydrated();
  // Tokens go to WebGL uniforms, never into markup, so reading the DOM here can't cause a mismatch.
  return useMemo(() => (hydrated ? read() : FALLBACK), [hydrated]);
}

export const useReducedMotion = () => useMedia("(prefers-reduced-motion: reduce)");
