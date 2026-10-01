import React, { useEffect, useState } from "react";
import { api } from "../../api.js";
import { go, useApp } from "../../App.jsx";
import { Icon, NumInput, Seg, SliderRow, Spinner, Toggle } from "../../components/ui.jsx";
import { useMediaLibrary } from "../../components/Media.jsx";
import { useEd } from "../EditorContext.js";
import { fmtMs } from "../time.js";
import { Hint, PanelHead } from "./Shared.jsx";

function Summary({ res }) {
  const { t } = useApp();
  if (!res) return null;
  const s = res.summary || {};
  const rows = Object.entries(s).filter(([, v]) => v !== null && typeof v !== "object");
  return (
    <div style={{ marginTop: 8, padding: 8, background: "var(--field)", borderRadius: 6, fontSize: 12 }}>
      <b>{res.preview ? t("tool_preview_result") : t("tool_applied")}</b>
      {res.duration_before ? <div className="muted num">{res.duration_before} → {res.duration_after}</div> : null}
      {rows.map(([k, v]) => <div key={k} className="muted"><span className="mono">{k}</span>: {String(v)}</div>)}
      {Array.isArray(s.examples) && s.examples.length ? <div className="muted" style={{ marginTop: 4 }}>{s.examples.slice(0, 5).map((x) => `${x.at} ${x.text}`).join(" · ")}</div> : null}
    </div>
  );
}

function ToolCard({ id, icon, title, help, children, run, canRun = true }) {
  const { t, fail } = useApp();
  const [busy, setBusy] = useState(null);
  const [res, setRes] = useState(null);
  const go_ = async (preview) => {
    setBusy(preview ? "preview" : "apply");
    try {
      setRes(await run(preview));
    } catch (e) { fail(e); } finally { setBusy(null); }
  };
  return (
    <details className="panel" style={{ marginBottom: 10 }} data-tool={id}>
      <summary style={{ padding: "9px 12px", display: "flex", alignItems: "center", gap: 8, fontWeight: 600 }}>
        <Icon name={icon} size={16} style={{ color: "var(--accent)" }} />{title}
      </summary>
      <div style={{ padding: "0 12px 12px" }}>
        <Hint>{help}</Hint>
        {children}
        <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
          <button type="button" className="btn btn-sm" disabled={!!busy || !canRun} onClick={() => go_(true)}>{busy === "preview" ? <Spinner /> : <Icon name="eye" size={14} />}{t("preview")}</button>
          <button type="button" className="btn btn-sm btn-primary" disabled={!!busy || !canRun} onClick={() => go_(false)}>{busy === "apply" ? <Spinner /> : <Icon name="check" size={14} />}{t("apply")}</button>
        </div>
        <Summary res={res} />
      </div>
    </details>
  );
}

function Labeled({ label, children }) {
  return <div className="row"><span className="l">{label}</span><div style={{ minWidth: 0 }}>{children}</div></div>;
}

function Highlights({ media }) {
  const { t, fail, notify } = useApp();
  const [mediaId, setMediaId] = useState("");
  const [count, setCount] = useState(5);
  const [len, setLen] = useState(30);
  const [res, setRes] = useState(null);
  const [busy, setBusy] = useState(false);
  const videos = (media || []).filter((m) => m.kind === "video");
  useEffect(() => { if (!mediaId && videos.length) setMediaId(videos[0].id); }, [mediaId, videos]);
  const find = async () => {
    setBusy(true);
    try { setRes(await api.highlights(mediaId, { count, length_s: len })); } catch (e) { fail(e); } finally { setBusy(false); }
  };
  const make = async (h, i) => {
    setBusy(true);
    try {
      const r = await api.short(mediaId, { start: h.start_ms, end: h.end_ms, name: `${t("short_name")} ${i + 1}`, preset: "reels", captions: true });
      notify(t("short_created"), "ok");
      go(`p/${r.project}`);
    } catch (e) { fail(e); setBusy(false); }
  };
  return (
    <details className="panel" style={{ marginBottom: 10 }} data-tool="highlights">
      <summary style={{ padding: "9px 12px", display: "flex", alignItems: "center", gap: 8, fontWeight: 600 }}><Icon name="star" size={16} style={{ color: "var(--accent)" }} />{t("tool_highlights")}</summary>
      <div style={{ padding: "0 12px 12px" }}>
        <Hint>{t("tool_highlights_help")}</Hint>
        <Labeled label={t("tool_media")}>
          <select className="field" value={mediaId} onChange={(e) => { setMediaId(e.target.value); setRes(null); }}>
            <option value="">—</option>
            {videos.map((m) => <option key={m.id} value={m.id}>{m.name} ({fmtMs(m.duration_ms).replace(/\.\d+$/, "")})</option>)}
          </select>
        </Labeled>
        <Labeled label={t("count")}><NumInput value={count} min={1} max={20} step={1} decimals={0} onCommit={(v) => setCount(Math.round(v))} /></Labeled>
        <Labeled label={t("clip_length_s")}><NumInput value={len} min={5} max={180} step={5} decimals={0} onCommit={(v) => setLen(Math.round(v))} /></Labeled>
        <button type="button" className="btn btn-sm btn-primary" disabled={!mediaId || busy} onClick={find}>{busy ? <Spinner /> : <Icon name="search" size={14} />}{t("highlights_find")}</button>
        {res ? (
          <div style={{ marginTop: 10 }}>
            <div className="muted" style={{ fontSize: 11.5, marginBottom: 6 }}>{t("signals")}: {(res.signals || []).join(", ") || "—"}</div>
            {(res.highlights || []).map((h, i) => (
              <div key={i} className="step" style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div className="mono num" style={{ fontSize: 12 }}>{h.range || `${fmtMs(h.start_ms)}–${fmtMs(h.end_ms)}`}</div>
                  <div className="muted" style={{ fontSize: 11.5 }}>{(h.reasons || []).map((r) => t(`reason_${r}`)).join(", ") || "—"} · {h.score}</div>
                </div>
                <button type="button" className="btn btn-sm" disabled={busy} onClick={() => make(h, i)}>{t("short_make")}</button>
              </div>
            ))}
          </div>
        ) : null}
      </div>
    </details>
  );
}

export default function ToolsPanel() {
  const { t } = useApp();
  const ed = useEd();
  const { media } = useMediaLibrary();
  const [sil, setSil] = useState({ auto: true, threshold: -35, min: 500, margin: 150, mode: "cut", speed: 4 });
  const [fill, setFill] = useState({ repeats: true, strict: false });
  const [scn, setScn] = useState({ mode: "split" });
  const [rf, setRf] = useState({ aspect: "9:16", mode: "auto" });
  const [ld, setLd] = useState({ target: -16 });
  const [bs, setBs] = useState({ music: "", source: "", beats: 2, mode: "scenes" });
  const audios = (media || []).filter((m) => m.has_audio && m.kind === "audio");
  const videos = (media || []).filter((m) => m.kind === "video");
  const cmd = (name, args) => (preview) => ed.runCommand(name, args, { preview });

  return (
    <div className="ed-panel">
      <PanelHead title={t("tab_tools")} />
      <div className="ed-panel-body">
        <Hint>{t("tools_help")}</Hint>

        <ToolCard id="remove_silences" icon="waveform" title={t("tool_silences")} help={t("tool_silences_help")}
          run={cmd("remove_silences", { ...(sil.auto ? {} : { threshold_db: sil.threshold }), min_silence_ms: sil.min, margin_ms: sil.margin, mode: sil.mode, ...(sil.mode === "speed" ? { speed: sil.speed } : {}) })}>
          <Labeled label={t("threshold")}><Toggle checked={sil.auto} onChange={(v) => setSil({ ...sil, auto: v })} label={t("auto")} /></Labeled>
          {!sil.auto ? <SliderRow label="dB" value={sil.threshold} min={-60} max={-10} step={1} decimals={0} onChange={(v) => setSil({ ...sil, threshold: v })} /> : null}
          <Labeled label={t("min_silence")}><NumInput value={sil.min} min={100} max={5000} step={50} decimals={0} onCommit={(v) => setSil({ ...sil, min: Math.round(v) })} /></Labeled>
          <Labeled label={t("margin")}><NumInput value={sil.margin} min={0} max={1000} step={10} decimals={0} onCommit={(v) => setSil({ ...sil, margin: Math.round(v) })} /></Labeled>
          <Labeled label={t("mode")}><Seg value={sil.mode} onChange={(v) => setSil({ ...sil, mode: v })} options={[{ value: "cut", label: t("mode_cut") }, { value: "speed", label: t("mode_speed") }]} /></Labeled>
          {sil.mode === "speed" ? <Labeled label={t("speed")}><NumInput value={sil.speed} min={1.5} max={16} step={0.5} decimals={1} onCommit={(v) => setSil({ ...sil, speed: v })} /></Labeled> : null}
        </ToolCard>

        <ToolCard id="remove_fillers" icon="mic" title={t("tool_fillers")} help={t("tool_fillers_help")} run={cmd("remove_fillers", { repeats: fill.repeats, strict: fill.strict })}>
          <Toggle checked={fill.repeats} onChange={(v) => setFill({ ...fill, repeats: v })} label={t("fillers_repeats")} />
          <div style={{ height: 6 }} />
          <Toggle checked={fill.strict} onChange={(v) => setFill({ ...fill, strict: v })} label={t("fillers_strict")} />
        </ToolCard>

        <ToolCard id="split_scenes" icon="split" title={t("tool_scenes")} help={t("tool_scenes_help")} run={cmd("split_scenes", { mode: scn.mode })}>
          <Labeled label={t("mode")}><Seg value={scn.mode} onChange={(v) => setScn({ mode: v })} options={[{ value: "split", label: t("scenes_split") }, { value: "markers", label: t("scenes_markers") }]} /></Labeled>
        </ToolCard>

        <ToolCard id="reframe" icon="crop" title={t("tool_reframe")} help={t("tool_reframe_help")} run={cmd("reframe", { aspect: rf.aspect, mode: rf.mode })}>
          <Labeled label={t("aspect")}><Seg value={rf.aspect} onChange={(v) => setRf({ ...rf, aspect: v })} options={["9:16", "1:1", "4:5", "16:9"].map((a) => ({ value: a, label: a }))} /></Labeled>
          <Labeled label={t("mode")}>
            <select className="field" value={rf.mode} onChange={(e) => setRf({ ...rf, mode: e.target.value })}>
              {["auto", "track", "stable", "center"].map((m) => <option key={m} value={m}>{t(`reframe_${m}`)}</option>)}
            </select>
          </Labeled>
        </ToolCard>

        <ToolCard id="match_loudness" icon="volume" title={t("tool_loudness")} help={t("tool_loudness_help")} run={cmd("match_loudness", { target_lufs: ld.target })}>
          <Labeled label="LUFS"><NumInput value={ld.target} min={-40} max={-5} step={1} decimals={0} onCommit={(v) => setLd({ target: v })} /></Labeled>
        </ToolCard>

        <ToolCard id="beat_sync" icon="music" title={t("tool_beat")} help={t("tool_beat_help")} canRun={!!bs.music && (bs.mode === "clips" || !!bs.source)}
          run={cmd("beat_sync", { music: bs.music, beats_per_cut: bs.beats, mode: bs.mode, ...(bs.mode === "scenes" && bs.source ? { source: bs.source } : {}) })}>
          <Labeled label={t("beat_music")}>
            <select className="field" value={bs.music} onChange={(e) => setBs({ ...bs, music: e.target.value })}>
              <option value="">—</option>
              {audios.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
            </select>
          </Labeled>
          <Labeled label={t("mode")}><Seg value={bs.mode} onChange={(v) => setBs({ ...bs, mode: v })} options={[{ value: "clips", label: t("beat_clips") }, { value: "scenes", label: t("beat_scenes") }]} /></Labeled>
          {bs.mode === "scenes" ? (
            <Labeled label={t("beat_source")}>
              <select className="field" value={bs.source} onChange={(e) => setBs({ ...bs, source: e.target.value })}>
                <option value="">—</option>
                {videos.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
              </select>
            </Labeled>
          ) : null}
          <Labeled label={t("beats_per_cut")}><NumInput value={bs.beats} min={1} max={16} step={1} decimals={0} onCommit={(v) => setBs({ ...bs, beats: Math.round(v) })} /></Labeled>
        </ToolCard>

        <Highlights media={media} />
      </div>
    </div>
  );
}
