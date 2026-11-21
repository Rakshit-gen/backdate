// GLSL for the sheet stack and the stale graph. Kept as strings next to each other so the
// shared noise function is written once.

const noise = /* glsl */ `
  float hash(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
  float grain(vec2 p) {
    vec2 i = floor(p), f = fract(p);
    vec2 u = f * f * (3.0 - 2.0 * f);
    return mix(mix(hash(i), hash(i + vec2(1, 0)), u.x), mix(hash(i + vec2(0, 1)), hash(i + vec2(1, 1)), u.x), u.y);
  }
`;

export const passUv = /* glsl */ `
  varying vec2 vUv;
  void main() {
    vUv = uv;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }
`;

/** A sheet of ledger paper: grain, a rule at each month, lane separators. */
export const sheetFrag = /* glsl */ `
  uniform vec3 uPaper;
  uniform vec3 uRuling;
  uniform float uOpacity;
  uniform float uLanes;
  uniform float uSeed;
  varying vec2 vUv;
  ${noise}
  float line(float x, float w) { return 1.0 - smoothstep(0.0, w, abs(x)); }
  void main() {
    // 12 months span the first 12/13 of the sheet; the last 13th is "after 2024".
    float m = vUv.x * 13.0;
    float monthRule = line(fract(m + 0.5) - 0.5, 0.035) * step(m, 12.02);
    float lane = line(fract(vUv.y * uLanes + 0.5) - 0.5, 0.02 * uLanes);
    float edge = max(line(vUv.x, 0.004), max(line(vUv.x - 1.0, 0.004), max(line(vUv.y, 0.01), line(vUv.y - 1.0, 0.01))));
    float g = grain(vUv * vec2(420.0, 160.0) + uSeed) * 0.5 + grain(vUv * vec2(60.0, 24.0) + uSeed) * 0.5;
    vec3 col = uPaper * (0.965 + 0.05 * g);
    col = mix(col, uRuling, max(monthRule * 0.55, max(lane * 0.35, edge)));
    gl_FragColor = vec4(col, uOpacity);
    #include <colorspace_fragment>
  }
`;

/** Ink printed on a sheet. Open-ended ranges fade out from uFadeFrom (in the quad's own u). */
export const inkFrag = /* glsl */ `
  uniform vec3 uColor;
  uniform float uOpacity;
  uniform float uFadeFrom;
  uniform float uSeed;
  varying vec2 vUv;
  ${noise}
  void main() {
    float press = 0.82 + 0.18 * grain(vUv * vec2(90.0, 18.0) + uSeed);
    float fade = uFadeFrom < 1.0 ? 1.0 - smoothstep(uFadeFrom, 1.0, vUv.x) : 1.0;
    gl_FragColor = vec4(uColor, uOpacity * press * fade);
    #include <colorspace_fragment>
  }
`;
