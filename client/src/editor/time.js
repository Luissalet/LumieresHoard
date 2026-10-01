// Time helpers. Everything on the timeline is integer milliseconds.
export const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));

// "m:ss.mmm" or "h:mm:ss.mmm"
export function fmtMs(ms) {
  ms = Math.max(0, Math.round(ms || 0));
  const h = Math.floor(ms / 3600000);
  const m = Math.floor((ms % 3600000) / 60000);
  const s = Math.floor((ms % 60000) / 1000);
  const f = ms % 1000;
  const mmm = String(f).padStart(3, "0");
  return h ? `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}.${mmm}` : `${m}:${String(s).padStart(2, "0")}.${mmm}`;
}

// Player timecode, always "hh:mm:ss:ff" (frames) like every editor, so 7 seconds never reads as 7 minutes.
export function fmtFrames(ms, fps = 30) {
  ms = Math.max(0, Math.round(ms || 0));
  const total = Math.floor((ms * fps) / 1000 + 1e-6);
  const f = total % Math.round(fps);
  const secs = Math.floor(ms / 1000);
  const s = secs % 60;
  const m = Math.floor(secs / 60) % 60;
  const h = Math.floor(secs / 3600);
  const two = (n) => String(n).padStart(2, "0");
  return `${two(h)}:${two(m)}:${two(s)}:${two(f)}`;
}

// Short label for rulers: 12s / 1:05 / 1:05.5
export function fmtRuler(ms, step) {
  const s = ms / 1000;
  const m = Math.floor(s / 60);
  const rest = s - m * 60;
  if (step >= 1000) return m ? `${m}:${String(Math.round(rest)).padStart(2, "0")}` : `${Math.round(rest)}s`;
  const digits = step >= 100 ? 1 : 2;
  return m ? `${m}:${rest.toFixed(digits).padStart(3 + digits, "0")}` : `${rest.toFixed(digits)}s`;
}

// Parses "1:23.5", "83.5", "1:02:03", "1500ms", "2s" -> ms (null when it is not a time).
export function parseTc(text) {
  const s = String(text ?? "").trim().replace(",", ".");
  if (!s) return null;
  let m = /^(-?\d+(?:\.\d+)?)\s*ms$/i.exec(s);
  if (m) return Math.round(parseFloat(m[1]));
  m = /^(\d+(?:\.\d+)?)\s*s$/i.exec(s);
  if (m) return Math.round(parseFloat(m[1]) * 1000);
  const parts = s.split(":");
  if (parts.length > 3 || parts.some((p) => !/^\d+(\.\d+)?$/.test(p))) return null;
  let secs = 0;
  for (const p of parts) secs = secs * 60 + parseFloat(p);
  return Math.round(secs * 1000);
}

export const frameMs = (fps) => 1000 / (fps || 30);

// Pick a ruler step (ms) so labels are at least `minPx` apart.
const STEPS = [10, 20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 15000, 30000, 60000, 120000, 300000, 600000, 1800000, 3600000];
export function rulerStep(pxPerMs, minPx = 90) {
  for (const s of STEPS) if (s * pxPerMs >= minPx) return s;
  return STEPS[STEPS.length - 1];
}

export function fmtBytes(n) {
  if (typeof n !== "number" || Number.isNaN(n)) return "—";
  if (n < 1024) return `${n} B`;
  if (n < 1048576) return `${(n / 1024).toFixed(1)} KB`;
  if (n < 1073741824) return `${(n / 1048576).toFixed(1)} MB`;
  return `${(n / 1073741824).toFixed(2)} GB`;
}

export function fmtDate(ts, lang) {
  if (!ts) return "—";
  const d = new Date(ts * 1000);
  return d.toLocaleString(lang === "en" ? "en-GB" : "es-ES", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
}

// Clip geometry helpers over the project document.
export const clipDur = (c) => (c.type === "text" ? c.length : Math.round((c.src_out - c.src_in) / (c.speed || 1)));
export const clipEnd = (c) => c.start + clipDur(c);

export function srcAt(c, t) {
  const off = (t - c.start) * (c.speed || 1);
  return c.reverse ? c.src_out - off : c.src_in + off;
}

export function findClip(doc, id) {
  for (const tr of doc.tracks) for (const c of tr.clips) if (c.id === id) return { track: tr, clip: c };
  return null;
}

// Rows top -> bottom as the timeline draws them: text, video (highest layer first), audio.
export function trackRows(doc) {
  const text = doc.tracks.filter((t) => t.kind === "text").reverse();
  const video = doc.tracks.filter((t) => t.kind === "video").reverse();
  const audio = doc.tracks.filter((t) => t.kind === "audio");
  return [...text, ...video, ...audio];
}

export const isMainTrack = (doc, track) => {
  const mains = doc.tracks.filter((t) => t.kind === "video" && t.role === "main");
  return mains.length ? mains[0].id === track.id : doc.tracks.find((t) => t.kind === "video")?.id === track.id;
};

export function projectDuration(doc) {
  const main = doc.tracks.find((t) => t.kind === "video" && t.role === "main") || doc.tracks.find((t) => t.kind === "video");
  const end = (tracks) => Math.max(0, ...tracks.flatMap((t) => t.clips.map(clipEnd)));
  if (doc.length_mode === "main" && main && main.clips.length) return end([main]);
  return end(doc.tracks);
}

// Keyframe interpolation.
function ease(kind, p) {
  switch (kind) {
    case "hold": return 0;
    case "ease_in": return p * p;
    case "ease_out": return 1 - (1 - p) * (1 - p);
    case "ease_in_out": return p < 0.5 ? 2 * p * p : 1 - Math.pow(-2 * p + 2, 2) / 2;
    default: return p;
  }
}
export function kfValue(keys, local, fallback) {
  if (!keys || !keys.length) return fallback;
  if (local <= keys[0].t) return keys[0].v;
  const last = keys[keys.length - 1];
  if (local >= last.t) return last.v;
  for (let i = 0; i < keys.length - 1; i++) {
    const a = keys[i];
    const b = keys[i + 1];
    if (local >= a.t && local < b.t) {
      const p = (local - a.t) / Math.max(1, b.t - a.t);
      return a.v + (b.v - a.v) * ease(a.ease, p);
    }
  }
  return last.v;
}
