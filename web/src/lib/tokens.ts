"use client";

import { useEffect, useState } from "react";

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

/** The page's colour tokens, kept in sync with the colour scheme, for use in WebGL. */
export function useTokens(): Tokens {
  const [tokens, setTokens] = useState(FALLBACK);
  useEffect(() => {
    setTokens(read());
    const mq = matchMedia("(prefers-color-scheme: dark)");
    const update = () => setTokens(read());
    mq.addEventListener("change", update);
    return () => mq.removeEventListener("change", update);
  }, []);
  return tokens;
}

export function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    const mq = matchMedia("(prefers-reduced-motion: reduce)");
    setReduced(mq.matches);
    const update = () => setReduced(mq.matches);
    mq.addEventListener("change", update);
    return () => mq.removeEventListener("change", update);
  }, []);
  return reduced;
}
