// Number helpers that reproduce the render's arithmetic (render/compiler.py) so the WebGL preview lands on the same pixels.

export const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));

// Python's round(): halves go to the even neighbour (JS rounds them up).
export function pyRound(x) {
  const f = Math.floor(x);
  const d = x - f;
  if (d < 0.5) return f;
  if (d > 0.5) return f + 1;
  return f % 2 === 0 ? f : f + 1;
}

// int(round(x / 2)) * 2: the even size ffmpeg filters are given.
export const even = (x) => pyRound(x / 2) * 2;
export const evenCeil = (x) => Math.ceil(x / 2) * 2;

// ffmpeg's overlay / crop positions: truncated to an integer, then to a multiple of 2 (4:2:0 chroma).
export const snap2 = (d) => Math.trunc(d) & ~1;

// ---- keyframes: the same eased points, sampled by the same flat expression the render builds (keyframe_expr) ----

const cache = new WeakMap();

function easePoints(keys) {
  const sorted = [...keys].sort((a, b) => a.t - b.t);
  const out = [];
  for (let i = 0; i < sorted.length; i++) {
    const k = sorted[i];
    out.push([k.t / 1000, k.v]);
    if (i + 1 >= sorted.length) break;
    const n = sorted[i + 1];
    if (k.ease === "hold") {
      out.push([(n.t - 1) / 1000, k.v]);
    } else if (k.ease && k.ease !== "linear") {
      for (let j = 1; j < 6; j++) {
        const u = j / 6;
        let e;
        if (k.ease === "ease_in") e = u * u;
        else if (k.ease === "ease_out") e = 1 - (1 - u) * (1 - u);
        else e = 3 * u * u - 2 * u * u * u;
        out.push([(k.t + (n.t - k.t) * u) / 1000, k.v + (n.v - k.v) * e]);
      }
    }
  }
  return out.sort((a, b) => a[0] - b[0] || a[1] - b[1]);
}

// Value of an animated property at clip-local time `localMs`: v0 + sum(slope_i * clip(t - t_i, 0, dt_i)).
export function kfRender(keys, localMs, fallback) {
  if (!keys || !keys.length) return fallback;
  let pts = cache.get(keys);
  if (!pts) {
    pts = easePoints(keys);
    cache.set(keys, pts);
  }
  const t = localMs / 1000;
  let v = pts[0][1];
  for (let i = 0; i + 1 < pts.length; i++) {
    const [ta, va] = pts[i];
    const [tb, vb] = pts[i + 1];
    const dt = tb - ta;
    if (dt <= 1e-6 || Math.abs(vb - va) < 1e-6) continue;
    v += ((vb - va) / dt) * clamp(t - ta, 0, dt);
  }
  return v;
}

export function hexToRgb(hex, fallback = [0, 0, 0]) {
  const m = /^#?([0-9a-f]{6})/i.exec(hex || "");
  if (!m) return fallback;
  const n = parseInt(m[1], 16);
  return [((n >> 16) & 255) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255];
}
