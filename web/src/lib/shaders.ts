// GLSL for the invalidation graph. Ink is a function of time: each line and node knows when
// the correction reaches it (aStart, seconds; -1 means never), so one uniform drives everything.

export const lineVert = /* glsl */ `
  attribute float aAlong;
  attribute float aSide;
  attribute float aStart;
  attribute float aDur;
  varying float vAlong;
  varying float vSide;
  varying float vStart;
  varying float vDur;
  void main() {
    vAlong = aAlong;
    vSide = aSide;
    vStart = aStart;
    vDur = aDur;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }
`;

export const lineFrag = /* glsl */ `
  uniform float uTime;
  uniform vec3 uBase;
  uniform vec3 uInk;
  varying float vAlong;
  varying float vSide;
  varying float vStart;
  varying float vDur;
  void main() {
    vec3 col = uBase;
    float alpha = 0.9;
    if (vStart >= 0.0) {
      float p = clamp((uTime - vStart) / vDur, 0.0, 1.0);
      float inked = step(vAlong, p);
      col = mix(uBase, uInk, inked);
      // A short darker head where the ink is still travelling.
      float head = (1.0 - step(1.0, p)) * smoothstep(0.07, 0.0, abs(vAlong - p));
      col = mix(col, uInk * 0.7, head);
      alpha = mix(0.9, 1.0, inked);
    }
    alpha *= 1.0 - smoothstep(0.55, 1.0, abs(vSide));
    gl_FragColor = vec4(col, alpha);
    #include <colorspace_fragment>
  }
`;

export const nodeVert = /* glsl */ `
  attribute vec2 aLocal;
  attribute float aStart;
  attribute float aPick;
  varying vec2 vLocal;
  varying float vStart;
  varying float vPick;
  void main() {
    vLocal = aLocal;
    vStart = aStart;
    vPick = aPick;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }
`;

/** A result: a ring that fills with red when the ink arrives, and one ripple as it does. */
export const nodeFrag = /* glsl */ `
  uniform float uTime;
  uniform float uRadius;
  uniform vec3 uPaper;
  uniform vec3 uGraphite;
  uniform vec3 uInk;
  uniform vec3 uCarbon;
  varying vec2 vLocal;
  varying float vStart;
  varying float vPick;
  void main() {
    // vLocal is in pixels from the node centre.
    float d = length(vLocal);
    float aa = 0.8;
    float hit = vStart >= 0.0 ? smoothstep(vStart, vStart + 0.25, uTime) : 0.0;
    vec3 ring = mix(uGraphite, uInk, hit);
    vec3 fill = mix(uPaper, uInk, hit * 0.85);
    if (vPick > 0.5) ring = uCarbon;
    float body = 1.0 - smoothstep(uRadius - aa, uRadius + aa, d);
    float inner = 1.0 - smoothstep(uRadius - 2.0 - aa, uRadius - 2.0 + aa, d);
    vec3 col = mix(ring, fill, inner);
    float alpha = body;
    if (vStart >= 0.0) {
      float t = uTime - vStart;
      float r = uRadius + t * 34.0;
      float ripple = (1.0 - smoothstep(0.0, 1.6, abs(d - r))) * clamp(1.0 - t / 0.7, 0.0, 1.0) * step(0.0, t);
      col = mix(uInk, col, body);
      alpha = max(alpha, ripple * 0.6);
    }
    if (vPick > 0.5) {
      float halo = 1.0 - smoothstep(1.0, 2.2, abs(d - uRadius - 4.0));
      col = mix(col, uCarbon, halo * (1.0 - body));
      alpha = max(alpha, halo);
    }
    gl_FragColor = vec4(col, alpha);
    #include <colorspace_fragment>
  }
`;
