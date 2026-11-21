"use client";

import { Canvas, useThree } from "@react-three/fiber";
import gsap from "gsap";
import { useEffect, useLayoutEffect, useMemo } from "react";
import * as THREE from "three";
import {
  edgeBuffers,
  type EdgeSpec,
  GROSS_Y,
  H,
  LEFT,
  layout,
  monthX,
  NODE_R,
  nodeStart,
  RIGHT,
  W,
  WH_Y,
} from "@/lib/loom";
import { MONTHS } from "@/lib/scene";
import { lineFrag, lineVert, nodeFrag, nodeVert } from "@/lib/shaders";
import { type Tokens, useReducedMotion, useTokens } from "@/lib/tokens";
import { ATTRIBUTE_NAMES } from "@/lib/format";
import type { Changeset, Graph } from "@/lib/types";

type Layout = ReturnType<typeof layout>;

function Camera() {
  const { camera, size, invalidate } = useThree();
  useLayoutEffect(() => {
    const cam = camera as THREE.OrthographicCamera;
    Object.assign(cam, { left: 0, right: W, top: 0, bottom: H, near: -10, far: 10, zoom: 1 });
    cam.position.set(0, 0, 5);
    cam.updateProjectionMatrix();
    invalidate();
  }, [camera, size, invalidate]);
  return null;
}

function lineGeometry(edges: EdgeSpec[]) {
  const b = edgeBuffers(edges);
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.BufferAttribute(b.position, 3));
  g.setAttribute("aAlong", new THREE.BufferAttribute(b.along, 1));
  g.setAttribute("aSide", new THREE.BufferAttribute(b.side, 1));
  g.setAttribute("aStart", new THREE.BufferAttribute(b.start, 1));
  g.setAttribute("aDur", new THREE.BufferAttribute(b.dur, 1));
  g.setIndex(b.index);
  return g;
}

function nodeGeometry(lay: Layout, picked: number | null) {
  const s = NODE_R * 3.4; // room for the ripple and the selection halo
  const pos: number[] = [];
  const local: number[] = [];
  const start: number[] = [];
  const pick: number[] = [];
  const index: number[] = [];
  lay.nodes.forEach((n, i) => {
    for (const [dx, dy] of [
      [-s, -s],
      [s, -s],
      [s, s],
      [-s, s],
    ] as const) {
      pos.push(n.x + dx, n.y + dy, 1);
      local.push(dx, dy);
      start.push(n.depth === null ? -1 : nodeStart(n.depth));
      pick.push(n.id === picked ? 1 : 0);
    }
    const a = i * 4;
    index.push(a, a + 1, a + 2, a, a + 2, a + 3);
  });
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
  g.setAttribute("aLocal", new THREE.Float32BufferAttribute(local, 2));
  g.setAttribute("aStart", new THREE.Float32BufferAttribute(start, 1));
  g.setAttribute("aPick", new THREE.Float32BufferAttribute(pick, 1));
  g.setIndex(index);
  return g;
}

function Ink({
  lay,
  tokens,
  picked,
  end,
  reduced,
  replay,
}: {
  lay: Layout;
  tokens: Tokens;
  picked: number | null;
  end: number;
  reduced: boolean;
  replay: number;
}) {
  const invalidate = useThree((s) => s.invalidate);

  const lanes = useMemo(() => {
    const base: EdgeSpec[] = lay.lanes.map((l) => ({
      points: [
        [LEFT, l.y],
        [RIGHT, l.y],
      ],
      start: -1,
      width: 1.5,
    }));
    const changed: EdgeSpec[] = lay.changed.map((c) => ({
      points: [
        [c.x0, c.lane.y],
        [c.x1, c.lane.y],
      ],
      start: 0,
      width: 7,
      dur: 0.3,
    }));
    return lineGeometry([...base, ...changed]);
  }, [lay]);
  const edges = useMemo(() => lineGeometry(lay.edges), [lay]);
  const nodes = useMemo(() => nodeGeometry(lay, picked), [lay, picked]);

  const mats = useMemo(() => {
    const line = (base: string) =>
      new THREE.ShaderMaterial({
        vertexShader: lineVert,
        fragmentShader: lineFrag,
        transparent: true,
        depthTest: false,
        side: THREE.DoubleSide,
        uniforms: {
          uTime: { value: 0 },
          uBase: { value: new THREE.Color(base) },
          uInk: { value: new THREE.Color() },
        },
      });
    const node = new THREE.ShaderMaterial({
      vertexShader: nodeVert,
      fragmentShader: nodeFrag,
      transparent: true,
      depthTest: false,
      side: THREE.DoubleSide,
      uniforms: {
        uTime: { value: 0 },
        uRadius: { value: NODE_R },
        uPaper: { value: new THREE.Color() },
        uGraphite: { value: new THREE.Color() },
        uInk: { value: new THREE.Color() },
        uCarbon: { value: new THREE.Color() },
      },
    });
    return { lane: line("#000"), edge: line("#000"), node };
  }, []);

  useEffect(() => {
    const u = (m: THREE.ShaderMaterial) => m.uniforms;
    u(mats.lane).uBase!.value.set(tokens.graphite);
    u(mats.lane).uInk!.value.set(tokens.redpen);
    u(mats.edge).uBase!.value.set(tokens.ruling);
    u(mats.edge).uInk!.value.set(tokens.redpen);
    u(mats.node).uPaper!.value.set(tokens.sheet);
    u(mats.node).uGraphite!.value.set(tokens.graphite);
    u(mats.node).uInk!.value.set(tokens.redpen);
    u(mats.node).uCarbon!.value.set(tokens.carbon);
    invalidate();
  }, [tokens, mats, invalidate]);

  // The one orchestrated moment: a single GSAP tween of time drives every line and node.
  useEffect(() => {
    const setTime = (t: number) => {
      for (const m of Object.values(mats)) m.uniforms.uTime!.value = t;
      invalidate();
    };
    if (reduced) {
      setTime(end + 1);
      return;
    }
    const box = { t: 0 };
    setTime(0);
    const tw = gsap.to(box, { t: end, duration: end, ease: "none", delay: 0.2, onUpdate: () => setTime(box.t) });
    return () => void tw.kill();
  }, [mats, invalidate, lay, end, reduced, replay]);

  useEffect(() => () => [lanes, edges, nodes].forEach((g) => g.dispose()), [lanes, edges, nodes]);

  return (
    <>
      <mesh geometry={edges} material={mats.edge} renderOrder={1} />
      <mesh geometry={lanes} material={mats.lane} renderOrder={2} />
      <mesh geometry={nodes} material={mats.node} renderOrder={3} />
    </>
  );
}

type Props = {
  graph: Graph;
  change: Changeset | undefined;
  picked: number | null;
  onPick: (id: number) => void;
  replay: number;
};

export function Loom({ graph, change, picked, onPick, replay }: Props) {
  const tokens = useTokens();
  const reduced = useReducedMotion();
  const lay = useMemo(() => layout(graph, change), [graph, change]);
  const end = useMemo(() => {
    const depths = [...lay.depth.values()];
    return depths.length ? nodeStart(Math.max(...depths)) + 0.9 : 0.5;
  }, [lay]);

  const pct = (x: number, y: number) => ({ left: `${(x / W) * 100}%`, top: `${(y / H) * 100}%` });

  return (
    <div className="loom" style={{ aspectRatio: `${W} / ${H}` }}>
      <Canvas orthographic frameloop="demand" dpr={[1, 2]} gl={{ antialias: true, alpha: true }} aria-hidden="true">
        <Camera />
        <Ink lay={lay} tokens={tokens} picked={picked} end={end} reduced={reduced} replay={replay} />
      </Canvas>
      {lay.lanes.map((l) => (
        <span key={`${l.entity}${l.attribute}`} className="loom-label lane" style={pct(LEFT - 14, l.y)}>
          {l.entity.startsWith("taxrate:") ? "Tax rate" : (ATTRIBUTE_NAMES[l.attribute] ?? l.attribute)}
          {l.entity.startsWith("taxrate:") ? ` (${l.entity.slice(8)})` : ""}
        </span>
      ))}
      <span className="loom-label row" style={pct(LEFT - 14, GROSS_Y)}>
        Gross
      </span>
      <span className="loom-label row" style={pct(LEFT - 14, WH_Y)}>
        Withholding
      </span>
      {MONTHS.map((m, i) => (
        <span key={m} className="loom-label month" style={pct(monthX(i), WH_Y + 34)}>
          {m}
        </span>
      ))}
      {lay.nodes.map((n) => (
        <button
          key={n.id}
          type="button"
          className="loom-node"
          style={pct(n.x, n.y)}
          aria-pressed={n.id === picked}
          aria-label={`${n.derivation} ${n.key}${n.depth !== null ? ", marked stale" : ""}`}
          onClick={() => onPick(n.id)}
        />
      ))}
    </div>
  );
}
