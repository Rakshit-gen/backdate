"use client";

import { useEffect, useRef } from "react";
import { useReducedMotion, useTokens, type Tokens } from "@/lib/tokens";

// The landing background. Across: twelve months of valid time. Up: writes, drifting by as
// transaction time moves on. Every few seconds a correction lands on a past month and red ink
// runs forward through every stored row after it, which is what backdate recomputes.
// The pointer lights the month under it; a click drops a correction there.

const VERT = `
attribute vec2 aPos;
void main() { gl_Position = vec4(aPos, 0.0, 1.0); }
`;

const FRAG = `
precision highp float;
uniform vec2 uRes;
uniform float uTime;
uniform float uDpr;
uniform vec3 uPointer;
uniform vec4 uHits[4];
uniform vec3 uPaper;
uniform vec3 uInk;
uniform vec3 uRed;
uniform vec3 uBlue;

float hash(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }

void main() {
  vec2 px = gl_FragCoord.xy / uDpr;
  vec2 res = uRes / uDpr;
  float colW = res.x / 12.0;
  float rowH = 26.0;

  float y = px.y + uTime * 7.0;
  float row = floor(y / rowH);
  float fy = fract(y / rowH);
  float month = floor(px.x / colW);

  // One stored row per write: a value true from one month for a few months.
  float startM = floor(hash(vec2(row, 1.0)) * 11.0);
  float lenM = 1.0 + floor(hash(vec2(row, 2.0)) * (12.0 - startM));
  float present = step(0.22, hash(vec2(row, 3.0)));
  float x0 = startM * colW + 3.0;
  float x1 = (startM + lenM) * colW - 3.0;
  float inBar = present * step(x0, px.x) * step(px.x, x1) * step(0.32, fy) * step(fy, 0.68);
  float edge = inBar * (1.0 - step(x0 + 1.5, px.x) * step(px.x, x1 - 1.5) * step(0.32 + 1.5 / rowH, fy) * step(fy, 0.68 - 1.5 / rowH));

  float rule = 1.0 - smoothstep(0.0, 1.0, abs(fract(px.x / colW + 0.5) - 0.5) * colW);

  vec3 col = uInk;
  float a = inBar * 0.12 + edge * 0.26 + rule * 0.09;

  // Corrections: ink runs right from the corrected month, then fades.
  float red = 0.0;
  float mark = 0.0;
  for (int i = 0; i < 4; i++) {
    vec4 h = uHits[i];
    float age = uTime - h.z;
    if (h.z < 0.0 || age < 0.0) continue;
    float front = h.x + age * 420.0;
    float fade = exp(-age / 2.6);
    float reach = step(h.x, px.x) * (1.0 - smoothstep(front - 24.0, front, px.x));
    red = max(red, reach * fade * present * step(h.x, x1));
    mark = max(mark, (1.0 - smoothstep(0.0, 1.2, abs(px.x - h.x))) * fade);
  }
  col = mix(col, uRed, clamp(red * 1.4, 0.0, 1.0));
  a = max(a, inBar * red * 0.8 + edge * red * 0.4);
  col = mix(col, uRed, mark);
  a = max(a, mark * 0.8);

  // The month under the pointer.
  float lit = step(month * colW, uPointer.x) * step(uPointer.x, (month + 1.0) * colW) * uPointer.z;
  col = mix(col, uBlue, lit * (1.0 - red));
  a = max(a, lit * 0.05);
  a += lit * inBar * 0.14;

  // Keep it quiet behind the headline on the left and fade into the page at the bottom.
  float keep = mix(0.18, 1.0, smoothstep(0.3, 0.8, px.x / res.x)) * smoothstep(0.0, 0.25, px.y / res.y);
  keep *= mix(0.45, 1.0, step(760.0, res.x));
  gl_FragColor = vec4(col * a * keep, a * keep);
}
`;

const rgb = (hex: string) => {
  const h = hex.replace("#", "");
  return [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16) / 255) as [number, number, number];
};

function compile(gl: WebGLRenderingContext, type: number, src: string) {
  const s = gl.createShader(type)!;
  gl.shaderSource(s, src);
  gl.compileShader(s);
  if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s) ?? "shader");
  return s;
}

export function Ledger() {
  const canvas = useRef<HTMLCanvasElement>(null);
  const tokens = useTokens();
  const reduced = useReducedMotion();
  const colours = useRef<Tokens>(tokens);

  useEffect(() => {
    colours.current = tokens;
  }, [tokens]);

  useEffect(() => {
    const el = canvas.current;
    const band = el?.parentElement;
    const gl = el?.getContext("webgl", { premultipliedAlpha: true, antialias: false });
    // No WebGL, or a lost context: the band is decoration, so it just stays plain paper.
    if (!el || !band || !gl || gl.isContextLost()) return;

    const prog = gl.createProgram()!;
    gl.attachShader(prog, compile(gl, gl.VERTEX_SHADER, VERT));
    gl.attachShader(prog, compile(gl, gl.FRAGMENT_SHADER, FRAG));
    gl.linkProgram(prog);
    gl.useProgram(prog);
    gl.bindBuffer(gl.ARRAY_BUFFER, gl.createBuffer());
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
    const aPos = gl.getAttribLocation(prog, "aPos");
    gl.enableVertexAttribArray(aPos);
    gl.vertexAttribPointer(aPos, 2, gl.FLOAT, false, 0, 0);
    const u = (n: string) => gl.getUniformLocation(prog, n);

    let width = 0;
    let height = 0;
    let dpr = 1;
    let time = 0;
    let last = 0;
    let frame = 0;
    let visible = true;
    let nextAuto = 0.5;
    const hits = new Float32Array(16).fill(-1);
    let slot = 0;
    const pointer = { x: 0, y: 0, z: 0, target: 0 };

    const hit = (x: number, at: number) => {
      hits.set([x, 0, at, 0], slot * 4);
      slot = (slot + 1) % 4;
    };
    const monthX = (m: number) => (m * width) / 12;

    function draw() {
      const c = colours.current;
      gl!.viewport(0, 0, el!.width, el!.height);
      gl!.uniform2f(u("uRes"), el!.width, el!.height);
      gl!.uniform1f(u("uTime"), time);
      gl!.uniform1f(u("uDpr"), dpr);
      gl!.uniform3f(u("uPointer"), pointer.x, height - pointer.y, pointer.z);
      gl!.uniform4fv(u("uHits"), hits);
      gl!.uniform3fv(u("uPaper"), rgb(c.paper));
      gl!.uniform3fv(u("uInk"), rgb(c.graphite));
      gl!.uniform3fv(u("uRed"), rgb(c.redpen));
      gl!.uniform3fv(u("uBlue"), rgb(c.carbon));
      gl!.drawArrays(gl!.TRIANGLES, 0, 3);
    }

    function loop(now: number) {
      const dt = Math.min((now - (last || now)) / 1000, 0.05);
      last = now;
      time += dt;
      if (time > nextAuto) {
        hit(monthX(1 + Math.floor(Math.random() * 8)), time);
        nextAuto = time + 3.4;
      }
      pointer.z += (pointer.target - pointer.z) * 0.15;
      draw();
      frame = requestAnimationFrame(loop);
    }

    function sync() {
      cancelAnimationFrame(frame);
      last = 0;
      if (reduced) {
        // One still frame: a correction from April, part way through.
        hits.fill(-1);
        time = 10;
        hit(monthX(3), 9.4);
        draw();
      } else if (visible && !document.hidden) {
        frame = requestAnimationFrame(loop);
      }
    }

    function resize() {
      const r = el!.getBoundingClientRect();
      width = r.width;
      height = r.height;
      dpr = Math.min(devicePixelRatio || 1, 1.5);
      el!.width = Math.round(width * dpr);
      el!.height = Math.round(height * dpr);
      draw();
    }

    const move = (e: PointerEvent) => {
      const r = el.getBoundingClientRect();
      pointer.x = e.clientX - r.left;
      pointer.y = e.clientY - r.top;
      pointer.target = 1;
      if (reduced) draw();
    };
    const leave = () => {
      pointer.target = 0;
    };
    const press = (e: PointerEvent) => {
      if ((e.target as Element).closest("a, button") || reduced) return;
      const r = el.getBoundingClientRect();
      hit(monthX(Math.floor(((e.clientX - r.left) / width) * 12)), time);
      nextAuto = time + 3.4;
    };

    const ro = new ResizeObserver(resize);
    ro.observe(el);
    const io = new IntersectionObserver(([entry]) => {
      visible = entry!.isIntersecting;
      sync();
    });
    io.observe(el);
    band.addEventListener("pointermove", move, { passive: true });
    band.addEventListener("pointerleave", leave);
    band.addEventListener("pointerdown", press, { passive: true });
    document.addEventListener("visibilitychange", sync);
    resize();
    sync();

    return () => {
      cancelAnimationFrame(frame);
      ro.disconnect();
      io.disconnect();
      band.removeEventListener("pointermove", move);
      band.removeEventListener("pointerleave", leave);
      band.removeEventListener("pointerdown", press);
      document.removeEventListener("visibilitychange", sync);
    };
  }, [reduced]);

  return <canvas ref={canvas} className="hero-canvas" aria-hidden="true" />;
}
