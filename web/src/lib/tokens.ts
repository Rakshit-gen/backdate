"use client";

import { useMemo, useSyncExternalStore } from "react";

export type Tokens = { paper: string; sheet: string; ruling: string; graphite: string; carbon: string; redpen: string };

const FALLBACK: Tokens = {
  paper: "#edf1e7",
  sheet: "#f6f8f2",
  ruling: "#bccdb6",
  graphite: "#262820",
  carbon: "#2b3a9c",
  redpen: "#c0281a",
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

/** The page's colour tokens, kept in sync with the colour scheme, for use in WebGL. */
export function useTokens(): Tokens {
  const dark = useMedia("(prefers-color-scheme: dark)");
  const hydrated = useHydrated();
  // Tokens go to WebGL uniforms, never into markup, so reading the DOM here can't cause a mismatch.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  return useMemo(() => (hydrated ? read() : FALLBACK), [dark, hydrated]);
}

export const useReducedMotion = () => useMedia("(prefers-reduced-motion: reduce)");
