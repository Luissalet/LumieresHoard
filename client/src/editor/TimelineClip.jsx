import React, { useEffect, useRef, useState } from "react";
import { loadWaveform } from "../api.js";
import { Icon } from "../components/ui.jsx";

const TILE_Q = 256;

// Quantised visible range of a clip (in clip-local px) so memoised clips do not redraw on every scroll tick.
export function visibleRange(clipX, clipW, scrollLeft, viewW) {
  const a = Math.max(0, scrollLeft - clipX - 300);
  const b = Math.min(clipW, scrollLeft + viewW - clipX + 300);
  return [Math.floor(a / TILE_Q) * TILE_Q, Math.min(clipW, Math.ceil(b / TILE_Q) * TILE_Q)];
}

function Filmstrip({ clip, media, info, ppm, h, visL, visR }) {
  const si = info?.sprite_info;
  const sprite = media?.urls?.sprite;
  const poster = media?.urls?.poster;
  if (visR <= visL) return null;
  if (media?.kind === "image") {
    return <div style={{ position: "absolute", left: visL, width: visR - visL, top: 0, height: h, backgroundImage: poster ? `url(${poster})` : undefined, backgroundSize: "auto 100%", backgroundRepeat: "repeat-x", backgroundPosition: `${-visL}px 0` }} />;
  }
  if (!si || !sprite) return null;
  const tw = Math.max(8, (h * si.tile_w) / si.tile_h);
  const first = Math.floor(visL / tw);
  const last = Math.ceil(visR / tw);
  const rows = Math.ceil(si.count / si.cols);
  const tiles = [];
  for (let i = first; i < last; i++) {
    const tMs = ((i + 0.5) * tw) / ppm;
    const src = clip.reverse ? clip.src_out - tMs * clip.speed : clip.src_in + tMs * clip.speed;
    const idx = Math.max(0, Math.min(si.count - 1, Math.floor(src / si.interval_ms)));
    const col = idx % si.cols;
    const row = Math.floor(idx / si.cols);
    tiles.push(
      <div
        key={i}
        style={{ position: "absolute", left: i * tw, top: 0, width: tw, height: h, backgroundImage: `url(${sprite})`, backgroundSize: `${si.cols * tw}px ${rows * h}px`, backgroundPosition: `${-col * tw}px ${-row * h}px` }}
      />,
    );
  }
  return <>{tiles}</>;
}

function Waveform({ clip, media, ppm, h, visL, visR, bottom }) {
  const canvas = useRef(null);
  const [wave, setWave] = useState(null);
  const url = media?.urls?.waveform;
  useEffect(() => {
    let live = true;
    if (url) loadWaveform(url).then((w) => live && setWave(w));
    return () => { live = false; };
  }, [url]);
  const width = Math.max(0, Math.round(visR - visL));
  useEffect(() => {
    const cv = canvas.current;
    if (!cv || !wave || width <= 0) return;
    const dpr = 1;
    cv.width = width * dpr;
    cv.height = h * dpr;
    const ctx = cv.getContext("2d");
    ctx.clearRect(0, 0, cv.width, cv.height);
    ctx.fillStyle = bottom ? "rgba(255,255,255,0.45)" : "rgba(255,255,255,0.7)";
    const mid = bottom ? h : h / 2;
    const amp = bottom ? h : h / 2 - 1;
    for (let i = 0; i < width; i++) {
      const t0 = (visL + i) / ppm;
      const t1 = (visL + i + 1) / ppm;
      let a;
      let b;
      if (clip.reverse) {
        b = clip.src_out - t0 * clip.speed;
        a = clip.src_out - t1 * clip.speed;
      } else {
        a = clip.src_in + t0 * clip.speed;
        b = clip.src_in + t1 * clip.speed;
      }
      let i0 = Math.max(0, Math.floor(a / 10));
      const i1 = Math.min(wave.length - 1, Math.max(i0, Math.floor(b / 10)));
      let peak = 0;
      const stepSkip = Math.max(1, Math.floor((i1 - i0) / 24));
      for (; i0 <= i1; i0 += stepSkip) if (wave[i0] > peak) peak = wave[i0];
      const v = Math.min(1, (peak / 255) * 1.15) * amp;
      if (bottom) ctx.fillRect(i, mid - v, 1, v);
      else ctx.fillRect(i, mid - v, 1, Math.max(1, v * 2));
    }
  }, [wave, width, visL, ppm, h, clip.src_in, clip.src_out, clip.speed, clip.reverse, bottom]);
  if (!url || width <= 0) return null;
  return <canvas ref={canvas} style={{ position: "absolute", left: visL, top: bottom ? undefined : 0, bottom: bottom ? 0 : undefined, width, height: h, pointerEvents: "none" }} />;
}

const TrimIcon = null;

function TimelineClipImpl({ clip, track, media, info, x, w, h, ppm, selected, dragging, visL, visR, onBody, onEdge, label, hasTransition, transName }) {
  const isText = clip.type === "text";
  const isAudio = track.kind === "audio";
  const bg = clip.color || (isText ? "var(--clip-text)" : isAudio ? "var(--clip-audio)" : "var(--clip-video)");
  const innerH = h - 6;
  return (
    <div
      className={`tl-clip${selected ? " sel" : ""}${dragging ? " dragging" : ""}`}
      data-clip={clip.id}
      style={{ left: x, width: Math.max(2, w), background: bg }}
      onPointerDown={(e) => onBody(e, clip, track)}
      title={label}
    >
      {!isText && !isAudio ? <Filmstrip clip={clip} media={media} info={info} ppm={ppm} h={innerH + 4} visL={visL} visR={visR} /> : null}
      {isAudio ? <Waveform clip={clip} media={media} ppm={ppm} h={innerH} visL={visL} visR={visR} /> : null}
      {!isText && !isAudio && media?.has_audio && h > 36 ? <Waveform clip={clip} media={media} ppm={ppm} h={Math.min(18, innerH / 2.5)} visL={visL} visR={visR} bottom /> : null}
      {hasTransition ? <div className="tl-trans" style={{ width: Math.min(w, clip.transition_in.dur * ppm) }} title={transName} /> : null}
      <div className="lbl">
        <span className="ellipsis" style={{ flex: 1, minWidth: 0 }}>{isText ? `“${clip.text}”` : label}</span>
        {clip.speed !== 1 ? <span className="tl-badge">×{Math.round(clip.speed * 100) / 100}</span> : null}
        {clip.reverse ? <span className="tl-badge">⟲</span> : null}
        {clip.filters?.length ? <span className="tl-badge" title={clip.filters.map((f) => f.type).join(", ")}>fx</span> : null}
        {clip.keyframes && Object.keys(clip.keyframes).length ? <span className="tl-badge" style={{ color: "var(--warn)" }}>◆</span> : null}
        {clip.mute ? <Icon name="mute" size={12} /> : null}
      </div>
      {hasTransition ? <div style={{ position: "absolute", left: 2, bottom: 2 }}><span className="tl-badge" style={{ background: "#fffc", color: "#000" }}>{transName}</span></div> : null}
      <div className="tl-edge l" data-edge="l" onPointerDown={(e) => onEdge(e, clip, track, "l")} />
      <div className="tl-edge r" data-edge="r" onPointerDown={(e) => onEdge(e, clip, track, "r")} />
    </div>
  );
}

export default React.memo(TimelineClipImpl);
export { TrimIcon };
