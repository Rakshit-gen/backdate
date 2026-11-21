"use client";

import { Canvas, useThree } from "@react-three/fiber";
import gsap from "gsap";
import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { inkFrag, passUv, sheetFrag } from "@/lib/shaders";
import { isCorrection, knownAt, MONTHS, yearFraction } from "@/lib/scene";
import { type Tokens, useReducedMotion, useTokens } from "@/lib/tokens";
import type { HistoryRow } from "@/lib/types";

// World layout. x is valid time, y is knowledge version, z is the attribute lane.
const W = 10;
const D = 3.3;
const GAP = 0.62;
const LANES = 3;
const LANE_D = D / LANES;
const xOf = (frac: number) => -W / 2 + (frac * W * 12) / 13; // 2024 takes 12 of 13 columns
const zOf = (lane: number) => -D / 2 + LANE_D * (lane + 0.5);
const yOf = (v: number) => (v - 1) * GAP;

export type Lane = { attribute: string; rows: HistoryRow[] };
type InkKind = "graphite" | "carbon" | "redpen";
type Ink = { lane: number; x0: number; x1: number; open: boolean; kind: InkKind };

/** What is printed on sheet v: every row believed at v, coloured by whether it is new there. */
export function inksFor(lanes: Lane[], v: number): Ink[] {
  const out: Ink[] = [];
  lanes.forEach(({ rows }, lane) => {
    for (const r of knownAt(rows, v)) {
      const x0 = xOf(yearFraction(r.from));
      const x1 = r.to === null ? W / 2 : xOf(yearFraction(r.to));
      if (x1 - x0 < 1e-3) continue;
      const kind: InkKind = r.tx_from !== v ? "graphite" : isCorrection(rows, r, v) ? "redpen" : "carbon";
      out.push({ lane, x0, x1, open: r.to === null, kind });
    }
  });
  return out;
}

function sheetTarget(v: number, selected: number) {
  if (v === selected) return { lift: 0.14, alpha: 1 };
  if (v < selected) return { lift: 0, alpha: 0.4 };
  return { lift: 0.9 + (v - selected) * 0.25, alpha: 0.06 }; // not known yet: peeled back
}

type Anim = { lift: number; alpha: number };

function apply(group: THREE.Group, mats: THREE.ShaderMaterial[], v: number, st: Anim) {
  group.position.y = yOf(v) + st.lift;
  mats[0]!.uniforms.uOpacity!.value = st.alpha < 0.1 ? st.alpha * 2 : 0.35 + 0.6 * st.alpha;
  for (const m of mats.slice(1)) m.uniforms.uOpacity!.value = st.alpha * 0.92;
}

type SheetProps = { v: number; inks: Ink[]; tokens: Tokens; selected: number; reduced: boolean };

function Sheet({ v, inks, tokens, selected, reduced }: SheetProps) {
  const group = useRef<THREE.Group>(null);
  const anim = useRef<Anim | null>(null);
  const invalidate = useThree((s) => s.invalidate);
  const mats = useMemo(() => {
    const sheet = new THREE.ShaderMaterial({
      vertexShader: passUv,
      fragmentShader: sheetFrag,
      transparent: true,
      depthWrite: false,
      side: THREE.DoubleSide,
      uniforms: {
        uPaper: { value: new THREE.Color() },
        uRuling: { value: new THREE.Color() },
        uOpacity: { value: 0 },
        uLanes: { value: LANES },
        uSeed: { value: v * 17.3 },
      },
    });
    const ink = inks.map(
      (k) =>
        new THREE.ShaderMaterial({
          vertexShader: passUv,
          fragmentShader: inkFrag,
          transparent: true,
          depthWrite: false,
          uniforms: {
            uColor: { value: new THREE.Color() },
            uOpacity: { value: 0 },
            uFadeFrom: { value: k.open ? (xOf(1) - k.x0) / (k.x1 - k.x0) : 1 },
            uSeed: { value: v * 3.1 + k.lane },
          },
        }),
    );
    return [sheet, ...ink];
  }, [v, inks]);

  useEffect(() => () => mats.forEach((m) => m.dispose()), [mats]);

  useEffect(() => {
    mats[0]!.uniforms.uPaper!.value.set(tokens.paper);
    mats[0]!.uniforms.uRuling!.value.set(tokens.ruling);
    inks.forEach((k, i) => mats[i + 1]!.uniforms.uColor!.value.set(tokens[k.kind]));
    invalidate();
  }, [mats, inks, tokens, invalidate]);

  // First mount: drop into the stack (the page's one orchestrated moment).
  // After that: move to wherever the selected version puts this sheet.
  useEffect(() => {
    const g = group.current;
    if (!g) return;
    const target = sheetTarget(v, selected);
    const first = anim.current === null;
    if (first) anim.current = reduced ? { ...target } : { lift: 3, alpha: 0 };
    const st = anim.current!;
    if (reduced) {
      Object.assign(st, target);
      apply(g, mats, v, st);
      invalidate();
      return;
    }
    apply(g, mats, v, st);
    const tween = gsap.to(st, {
      ...target,
      duration: first ? 0.7 : 0.35,
      delay: first ? 0.15 + v * 0.09 : 0,
      ease: first ? "power3.out" : "power2.out",
      overwrite: true,
      onUpdate: () => {
        apply(g, mats, v, st);
        invalidate();
      },
    });
    return () => void tween.kill();
  }, [v, selected, reduced, mats, invalidate]);

  return (
    <group ref={group}>
      <mesh rotation-x={-Math.PI / 2} material={mats[0]} renderOrder={v * 2}>
        <planeGeometry args={[W, D]} />
      </mesh>
      {inks.map((k, i) => (
        <mesh
          key={i}
          rotation-x={-Math.PI / 2}
          position={[(k.x0 + k.x1) / 2, 0.003, zOf(k.lane)]}
          material={mats[i + 1]}
          renderOrder={v * 2 + 1}
        >
          <planeGeometry args={[k.x1 - k.x0, LANE_D * 0.56]} />
        </mesh>
      ))}
    </group>
  );
}

type Label = { id: string; text: string; x: number; y: number; kind: "month" | "lane" };
type LabelSpec = Omit<Label, "x" | "y"> & { p: THREE.Vector3 };

function Rig({ versions, labels, onProject }: { versions: number; labels: LabelSpec[]; onProject: (l: Label[]) => void }) {
  const { camera, size, invalidate } = useThree();
  useEffect(() => {
    const cam = camera as THREE.OrthographicCamera;
    const height = yOf(versions) + 1.6;
    cam.zoom = Math.min(size.width / (W * 1.12), size.height / (height + D * 0.75));
    cam.position.set(4.2, 7 + height / 2, 10);
    cam.lookAt(0, height / 2 - 0.4, 0);
    cam.updateProjectionMatrix();
    cam.updateMatrixWorld();
    onProject(
      labels.map((l) => {
        const p = l.p.clone().project(cam);
        return { ...l, x: ((p.x + 1) / 2) * size.width, y: ((1 - p.y) / 2) * size.height };
      }),
    );
    invalidate();
  }, [camera, size, versions, labels, onProject, invalidate]);
  return null;
}

export function SheetStack({ lanes, versions, selected }: { lanes: Lane[]; versions: number; selected: number }) {
  const tokens = useTokens();
  const reduced = useReducedMotion();
  const [projected, setProjected] = useState<Label[]>([]);

  const sheets = useMemo(
    () => Array.from({ length: versions }, (_, i) => ({ v: i + 1, inks: inksFor(lanes, i + 1) })),
    [lanes, versions],
  );

  const labels = useMemo(() => {
    const out: LabelSpec[] = MONTHS.map((m, i) => ({
      id: `m${i}`,
      text: m,
      kind: "month" as const,
      p: new THREE.Vector3(xOf((i + 0.5) / 12), 0, D / 2 + 0.15),
    }));
    ["Salary", "FTE", "State"].forEach((t, i) =>
      out.push({ id: `l${i}`, text: t, kind: "lane", p: new THREE.Vector3(W / 2 + 0.15, 0, zOf(i)) }),
    );
    return out;
  }, []);

  return (
    <div className="stack" aria-hidden="true">
      <Canvas orthographic frameloop="demand" dpr={[1, 2]} gl={{ antialias: true, alpha: true }}>
        <Rig versions={versions} labels={labels} onProject={setProjected} />
        {sheets.map((s) => (
          <Sheet key={`${s.v}:${s.inks.length}`} v={s.v} inks={s.inks} tokens={tokens} selected={selected} reduced={reduced} />
        ))}
      </Canvas>
      {projected.map((l) => (
        <span key={l.id} className={`stack-label ${l.kind}`} style={{ left: l.x, top: l.y }}>
          {l.text}
        </span>
      ))}
    </div>
  );
}
