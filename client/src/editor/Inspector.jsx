import React, { useEffect, useMemo, useRef, useState } from "react";
import { useApp } from "../App.jsx";
import { ConfirmButton, Icon, NumInput, Seg, SliderRow, Toggle } from "../components/ui.jsx";
import { useEd } from "./EditorContext.js";
import { AUDIO_FX, FONTS, FX_RANGES } from "./fxspec.js";
import { useTime } from "./playback.js";
import { clamp, clipDur, fmtMs, kfValue, parseTc } from "./time.js";

const Sec = ({ title, children, right }) => (
  <div className="insp-sec">
    <h4 style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>{title}{right}</h4>
    {children}
  </div>
);

function Row({ label, children }) {
  return (
    <div className="row">
      <span className="l">{label}</span>
      <div style={{ minWidth: 0 }}>{children}</div>
    </div>
  );
}

function TcInput({ value, onCommit, disabled }) {
  const [text, setText] = useState(fmtMs(value));
  const editing = useRef(false);
  useEffect(() => { if (!editing.current) setText(fmtMs(value)); }, [value]);
  const commit = () => {
    editing.current = false;
    const ms = parseTc(text);
    if (ms === null) { setText(fmtMs(value)); return; }
    setText(fmtMs(ms));
    if (ms !== Math.round(value)) onCommit(ms);
  };
  return (
    <input
      className="field num mono"
      style={{ textAlign: "right" }}
      value={text}
      disabled={disabled}
      onFocus={(e) => { editing.current = true; e.target.select(); }}
      onChange={(e) => setText(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => { if (e.key === "Enter") e.target.blur(); if (e.key === "Escape") { editing.current = false; setText(fmtMs(value)); e.target.blur(); } }}
    />
  );
}

function ColorInput({ value, onChange, disabled }) {
  return <input type="color" value={(value || "#000000").slice(0, 7)} disabled={disabled} onChange={(e) => onChange(e.target.value.toUpperCase())} style={{ width: 40, height: 26, padding: 0, border: "1px solid var(--line-2)", borderRadius: 5, background: "var(--field)" }} />;
}

// ------------------------------------------------------------------ effects
function EffectsSection({ clip, ids }) {
  const { t, presets } = useApp();
  const ed = useEd();
  const [pick, setPick] = useState("");
  const list = Object.keys(presets?.effects || {});
  const isAudioClip = ed.doc.tracks.find((tr) => tr.clips.some((c) => c.id === clip?.id))?.kind === "audio";
  const options = list.filter((k) => (isAudioClip ? AUDIO_FX.has(k) : true));
  const add = () => {
    if (!pick) return;
    ed.edit([{ op: "filter_add", clips: ids, type: pick, params: { ...(presets.effects[pick] || {}) } }], t("lbl_effect"));
    setPick("");
  };
  const setParam = (idx, key, value) => {
    const next = clip.filters.map((f, i) => (i === idx ? { ...f, params: { ...f.params, [key]: value } } : f));
    ed.commitClipProps(clip.id, { filters: next }, t("lbl_effect_param"));
  };
  const toggleFx = (idx) => ed.edit([{ op: "set", clip: clip.id, props: { filters: clip.filters.map((f, i) => (i === idx ? { ...f, enabled: !f.enabled } : f)) } }], t("lbl_effect"));
  return (
    <Sec title={t("insp_effects")}>
      {clip?.filters?.map((f, idx) => {
        const spec = FX_RANGES[f.type] || {};
        return (
          <div key={f.type + idx} className="step" style={{ padding: "6px 8px", marginBottom: 6 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <input type="checkbox" checked={f.enabled !== false} onChange={() => toggleFx(idx)} aria-label={t(`fx_${f.type}`)} />
              <b style={{ flex: 1, fontSize: 12 }}>{t(`fx_${f.type}`)}</b>
              <button type="button" className="btn btn-ghost btn-icon btn-sm" aria-label={t("remove")} onClick={() => ed.edit([{ op: "filter_remove", clip: clip.id, type: f.type }], t("lbl_effect_rm"))}><Icon name="x" size={13} /></button>
            </div>
            {Object.entries(spec).map(([key, range]) => {
              const val = f.params?.[key] ?? presets?.effects?.[f.type]?.[key];
              if (range === "color") return <Row key={key} label={t(`fxp_${key}`)}><ColorInput value={val} onChange={(v) => setParam(idx, key, v)} /></Row>;
              if (range === "text") return <Row key={key} label={t(`fxp_${key}`)}><input className="field" value={val ?? ""} onChange={(e) => setParam(idx, key, e.target.value)} /></Row>;
              return <SliderRow key={key} label={t(`fxp_${key}`)} value={Number(val)} min={range[0]} max={range[1]} step={range[2]} decimals={range[2] >= 1 ? 0 : 2} defaultValue={presets?.effects?.[f.type]?.[key]} onChange={(v) => setParam(idx, key, v)} />;
            })}
          </div>
        );
      })}
      <div style={{ display: "flex", gap: 6 }}>
        <select className="field" value={pick} onChange={(e) => setPick(e.target.value)} aria-label={t("fx_add")}>
          <option value="">{t("fx_add")}</option>
          {options.map((k) => <option key={k} value={k}>{t(`fx_${k}`)}</option>)}
        </select>
        <button type="button" className="btn btn-sm" disabled={!pick} onClick={add}><Icon name="plus" size={14} /></button>
      </div>
    </Sec>
  );
}

// ------------------------------------------------------------------ keyframes
const KF_PROPS = ["x", "y", "scale", "opacity", "rotation"];

function KeyframesSection({ clip }) {
  const { t } = useApp();
  const ed = useEd();
  const local = Math.round(clamp(ed.pb.t - clip.start, 0, clipDur(clip)));
  const now = useTime(ed.pb, 120);
  const nowLocal = clamp(Math.round(now - clip.start), 0, clipDur(clip));
  const setKeys = (prop, keys) => ed.edit([{ op: "keyframes", clip: clip.id, prop, keys: [...keys].sort((a, b) => a.t - b.t) }], t("lbl_keyframes"));
  const add = (prop) => {
    const keys = clip.keyframes?.[prop] || [];
    const value = kfValue(keys, local, clip.transform[prop]);
    setKeys(prop, [...keys.filter((k) => Math.abs(k.t - local) > 1), { t: local, v: Math.round(value * 1000) / 1000, ease: "linear" }]);
  };
  const withKeys = KF_PROPS.filter((p) => clip.keyframes?.[p]?.length);
  return (
    <Sec title={t("insp_keyframes")}>
      <div className="muted" style={{ fontSize: 11.5, marginBottom: 6 }}>{t("kf_help", { t: fmtMs(nowLocal) })}</div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 5 }}>
        {KF_PROPS.map((p) => (
          <button key={p} type="button" className="btn btn-sm" onClick={() => add(p)}><Icon name="keyframe" size={11} />{t(`kf_${p}`)}</button>
        ))}
      </div>
      {withKeys.map((p) => (
        <div key={p} style={{ marginTop: 8 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <b style={{ fontSize: 12, flex: 1 }}>{t(`kf_${p}`)}</b>
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => setKeys(p, [])}>{t("kf_clear")}</button>
          </div>
          {clip.keyframes[p].map((k, i) => (
            <div key={i} style={{ display: "grid", gridTemplateColumns: "1fr 1fr 24px", gap: 6, marginTop: 4, alignItems: "center" }}>
              <button type="button" className="btn btn-ghost btn-sm mono" style={{ justifyContent: "flex-start" }} onClick={() => ed.pb.seek(clip.start + k.t)}>{fmtMs(k.t)}</button>
              <NumInput value={k.v} step={0.05} decimals={3} onCommit={(v) => setKeys(p, clip.keyframes[p].map((x, j) => (j === i ? { ...x, v } : x)))} />
              <button type="button" className="btn btn-ghost btn-icon btn-sm" style={{ width: 24 }} aria-label={t("remove")} onClick={() => setKeys(p, clip.keyframes[p].filter((_, j) => j !== i))}><Icon name="x" size={12} /></button>
            </div>
          ))}
        </div>
      ))}
    </Sec>
  );
}

// ------------------------------------------------------------------ text clip
function TextSection({ clip }) {
  const { t } = useApp();
  const ed = useEd();
  const st = clip.style || {};
  const [text, setText] = useState(clip.text);
  useEffect(() => { setText(clip.text); }, [clip.id, clip.text]);
  const style = (patch) => ed.commitClipProps(clip.id, { style: patch }, t("lbl_text_style"));
  return (
    <>
      <Sec title={t("insp_text")}>
        <textarea className="field" rows={3} value={text} aria-label={t("insp_text")} onChange={(e) => { setText(e.target.value); if (e.target.value.trim()) ed.commitClipProps(clip.id, { text: e.target.value }, t("lbl_text_edit"), 450); }} />
      </Sec>
      <Sec title={t("insp_text_style")}>
        <Row label={t("font")}>
          <input className="field" list="fonts" value={st.font || "Arial"} onChange={(e) => style({ font: e.target.value })} />
          <datalist id="fonts">{FONTS.map((f) => <option key={f} value={f} />)}</datalist>
        </Row>
        <SliderRow label={t("size")} value={st.size ?? 72} min={8} max={400} step={1} decimals={0} onChange={(v) => style({ size: Math.round(v) })} />
        <Row label={t("color")}><div style={{ display: "flex", gap: 8, alignItems: "center" }}><ColorInput value={st.color} onChange={(v) => style({ color: v })} /><span className="muted" style={{ fontSize: 11.5 }}>{t("outline")}</span><ColorInput value={st.outline} onChange={(v) => style({ outline: v })} /></div></Row>
        <SliderRow label={t("outline_w")} value={st.outline_width ?? 4} min={0} max={40} step={0.5} decimals={1} onChange={(v) => style({ outline_width: v })} />
        <Row label={t("box")}>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <input type="checkbox" checked={!!st.box} onChange={(e) => ed.edit([{ op: "set", clip: clip.id, props: { style: { box: e.target.checked ? "#000000B3" : null } } }], t("lbl_text_style"))} aria-label={t("box")} />
            {st.box ? <ColorInput value={st.box} onChange={(v) => style({ box: `${v}B3` })} /> : null}
          </div>
        </Row>
        <Row label={t("style")}>
          <div style={{ display: "flex", gap: 6 }}>
            <button type="button" className={`btn btn-sm ${st.bold !== false ? "btn-on" : ""}`} style={{ fontWeight: 800 }} aria-pressed={st.bold !== false} onClick={() => style({ bold: st.bold === false })}>B</button>
            <button type="button" className={`btn btn-sm ${st.italic ? "btn-on" : ""}`} style={{ fontStyle: "italic" }} aria-pressed={!!st.italic} onClick={() => style({ italic: !st.italic })}>I</button>
          </div>
        </Row>
        <Row label={t("align")}><Seg value={st.align || "center"} onChange={(v) => style({ align: v })} options={[{ value: "left", label: "⇤" }, { value: "center", label: "↔" }, { value: "right", label: "⇥" }]} /></Row>
        <Row label={t("position")}><Seg value={st.position || "middle"} onChange={(v) => style({ position: v })} options={[{ value: "top", label: t("pos_top") }, { value: "middle", label: t("pos_middle") }, { value: "bottom", label: t("pos_bottom") }]} /></Row>
        <SliderRow label={t("margin")} value={st.margin ?? 80} min={0} max={600} step={1} decimals={0} onChange={(v) => style({ margin: Math.round(v) })} />
        <Row label={t("animation")}>
          <select className="field" value={st.animation || "fade"} onChange={(e) => style({ animation: e.target.value })}>
            {["none", "fade", "pop", "slide_up", "typewriter"].map((a) => <option key={a} value={a}>{t(`anim_${a}`)}</option>)}
          </select>
        </Row>
      </Sec>
    </>
  );
}

// ------------------------------------------------------------------ one clip
function ClipInspector({ clip, track, media }) {
  const { t, presets } = useApp();
  const ed = useEd();
  const { actions } = ed;
  const isText = clip.type === "text";
  const isImage = media?.kind === "image";
  const isAudioTrack = track.kind === "audio";
  const tf = clip.transform;
  const commitT = (patch) => ed.commitClipProps(clip.id, { transform: patch }, t("lbl_transform"));
  const commitCrop = (patch) => ed.commitClipProps(clip.id, { crop: patch }, t("lbl_crop"));
  const setProps = (props, label) => ed.edit([{ op: "set", clip: clip.id, props, ripple: false }], label);
  const dur = clipDur(clip);
  const move = (start) => ed.edit([{ op: "move", clip: clip.id, start }], t("lbl_move"));
  const trim = (props) => ed.edit([{ op: "trim", clip: clip.id, ...props, ripple: true }], t("lbl_trim"));
  const mediaDur = media?.duration_ms || 0;

  return (
    <>
      <Sec title={isText ? t("insp_text_clip") : t("insp_clip")}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
          <Icon name={isText ? "type" : isAudioTrack ? "music" : isImage ? "image" : "film"} size={16} style={{ color: "var(--accent)" }} />
          <div className="ellipsis" style={{ fontWeight: 600 }} title={clip.label || media?.name}>{isText ? clip.text.slice(0, 40) : clip.label || media?.name}</div>
        </div>
        <Row label={t("start")}><TcInput value={clip.start} onCommit={(v) => move(Math.max(0, v))} /></Row>
        {!isText && !isImage ? (
          <>
            <Row label={t("src_in")}><TcInput value={clip.src_in} onCommit={(v) => trim({ src_in: clamp(v, 0, clip.src_out - 80) })} /></Row>
            <Row label={t("src_out")}><TcInput value={clip.src_out} onCommit={(v) => trim({ src_out: clamp(v, clip.src_in + 80, mediaDur || Infinity) })} /></Row>
            <Row label={t("duration")}><span className="mono num">{fmtMs(dur)}</span></Row>
          </>
        ) : (
          <Row label={t("duration")}><TcInput value={dur} onCommit={(v) => trim({ length: Math.max(100, v) })} /></Row>
        )}
      </Sec>

      {isText ? <TextSection clip={clip} /> : null}

      {!isText ? (
        <Sec title={t("insp_speed")}>
          <Row label={t("speed")}>
            <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
              <NumInput width={64} value={clip.speed} min={0.1} max={16} step={0.25} decimals={2} onCommit={(v) => ed.edit([{ op: "speed", clip: clip.id, speed: v }], t("lbl_speed"))} />
              {[0.5, 1, 2].map((v) => <button key={v} type="button" className={`btn btn-sm ${clip.speed === v ? "btn-on" : ""}`} onClick={() => ed.edit([{ op: "speed", clip: clip.id, speed: v }], t("lbl_speed"))}>{v}×</button>)}
            </div>
          </Row>
          {!isImage ? <Row label={t("reverse")}><Toggle checked={clip.reverse} onChange={(v) => setProps({ reverse: v }, t("lbl_reverse"))} label="" /></Row> : null}
        </Sec>
      ) : null}

      {!isText && !isImage && media?.has_audio ? (
        <Sec title={t("insp_audio")}>
          <SliderRow label={t("volume")} value={clip.volume_db} min={-60} max={24} step={0.5} decimals={1} defaultValue={0} onChange={(v) => ed.commitClipProps(clip.id, { volume_db: v }, t("lbl_volume"))} />
          <Row label={t("mute")}><Toggle checked={clip.mute} onChange={(v) => setProps({ mute: v }, t("lbl_mute"))} label="" /></Row>
          <Row label={t("fade_in")}><NumInput value={clip.audio_fade_in} min={0} step={100} decimals={0} onCommit={(v) => setProps({ audio_fade_in: Math.round(v) }, t("lbl_fade"))} /></Row>
          <Row label={t("fade_out")}><NumInput value={clip.audio_fade_out} min={0} step={100} decimals={0} onCommit={(v) => setProps({ audio_fade_out: Math.round(v) }, t("lbl_fade"))} /></Row>
        </Sec>
      ) : null}

      {!isAudioTrack ? (
        <>
          <Sec title={t("insp_video")}>
            {!isText ? (
              <>
                <Row label={t("fade_in")}><NumInput value={clip.fade_in} min={0} step={100} decimals={0} onCommit={(v) => setProps({ fade_in: Math.round(v) }, t("lbl_fade"))} /></Row>
                <Row label={t("fade_out")}><NumInput value={clip.fade_out} min={0} step={100} decimals={0} onCommit={(v) => setProps({ fade_out: Math.round(v) }, t("lbl_fade"))} /></Row>
              </>
            ) : null}
            {!isText ? (
              <Row label={t("fit")}>
                <select className="field" value={tf.fit} onChange={(e) => ed.edit([{ op: "set", clip: clip.id, props: { transform: { fit: e.target.value } }, ripple: false }], t("lbl_transform"))}>
                  {["contain", "cover", "fill", "none"].map((f) => <option key={f} value={f}>{t(`fit_${f}`)}</option>)}
                </select>
              </Row>
            ) : null}
            <SliderRow label={t("scale")} value={tf.scale} min={0.1} max={4} step={0.01} defaultValue={1} onChange={(v) => commitT({ scale: v })} />
            <SliderRow label="X" value={tf.x} min={-1} max={1} step={0.005} decimals={3} defaultValue={0} onChange={(v) => commitT({ x: v })} />
            <SliderRow label="Y" value={tf.y} min={-1} max={1} step={0.005} decimals={3} defaultValue={0} onChange={(v) => commitT({ y: v })} />
            <SliderRow label={t("rotation")} value={tf.rotation} min={-180} max={180} step={0.5} decimals={1} defaultValue={0} onChange={(v) => commitT({ rotation: v })} />
            <SliderRow label={t("opacity")} value={tf.opacity} min={0} max={1} step={0.01} defaultValue={1} onChange={(v) => commitT({ opacity: v })} />
            {!isText && tf.fit === "cover" ? (
              <>
                <SliderRow label={t("focus_x")} value={tf.focus_x} min={0} max={1} step={0.01} defaultValue={0.5} onChange={(v) => commitT({ focus_x: v })} />
                <SliderRow label={t("focus_y")} value={tf.focus_y} min={0} max={1} step={0.01} defaultValue={0.5} onChange={(v) => commitT({ focus_y: v })} />
                {clip.reframe?.path?.length ? <div className="chip chip-info" style={{ marginTop: 2 }}>{t("reframed")}</div> : null}
              </>
            ) : null}
          </Sec>
          {!isText ? (
            <Sec title={t("insp_crop")}>
              {["left", "top", "right", "bottom"].map((side) => <SliderRow key={side} label={t(`crop_${side}`)} value={clip.crop[side]} min={0} max={0.45} step={0.005} decimals={3} defaultValue={0} onChange={(v) => commitCrop({ [side]: v })} />)}
            </Sec>
          ) : null}
          <Sec title={t("insp_transition")}>
            <Row label={t("type")}>
              <select className="field" value={clip.transition_in?.type || ""} onChange={(e) => ed.edit([{ op: "transition", clip: clip.id, type: e.target.value || null, dur: clip.transition_in?.dur || 500 }], t("lbl_transition"))}>
                <option value="">{t("tr_none")}</option>
                {(presets?.transitions || []).map((x) => <option key={x} value={x}>{t(`tr_${x}`)}</option>)}
              </select>
            </Row>
            {clip.transition_in ? <Row label={t("duration")}><NumInput value={clip.transition_in.dur} min={40} max={5000} step={50} decimals={0} onCommit={(v) => ed.edit([{ op: "transition", clip: clip.id, type: clip.transition_in.type, dur: Math.round(v) }], t("lbl_transition"))} /></Row> : null}
          </Sec>
        </>
      ) : null}

      {!isImage || isText ? null : null}
      <EffectsSection clip={clip} ids={[clip.id]} />
      <KeyframesSection clip={clip} />

      <Sec title={t("insp_actions")}>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6 }}>
          <button type="button" className="btn btn-sm" onClick={() => actions.split()} title="S"><Icon name="scissors" size={14} />{t("split_here")}</button>
          <button type="button" className="btn btn-sm" onClick={() => actions.duplicate()}><Icon name="copy" size={14} />{t("duplicate")}</button>
          <button type="button" className="btn btn-sm btn-danger" onClick={() => actions.remove(true)} title="Supr"><Icon name="trash" size={14} />{t("delete")}</button>
          <button type="button" className="btn btn-sm btn-danger" onClick={() => actions.remove(false)} title="Shift+Supr"><Icon name="trash" size={14} />{t("delete_nogap")}</button>
          {!isText && !isImage && !isAudioTrack && media?.has_audio ? <button type="button" className="btn btn-sm" onClick={() => actions.detachAudio()}><Icon name="detach" size={14} />{t("detach_audio")}</button> : null}
          {!isText && !isAudioTrack ? <button type="button" className="btn btn-sm" onClick={() => actions.freeze()}><Icon name="freeze" size={14} />{t("freeze")}</button> : null}
          {!isText && !isImage && !isAudioTrack ? <button type="button" className="btn btn-sm" onClick={() => actions.stabilize()}><Icon name="stabilize" size={14} />{t("stabilize")}</button> : null}
        </div>
      </Sec>
    </>
  );
}

// ------------------------------------------------------------------ several clips
function MultiInspector({ clips }) {
  const { t } = useApp();
  const ed = useEd();
  const { actions } = ed;
  const [speed, setSpeed] = useState(1);
  const media = clips.filter(({ clip }) => clip.type === "media");
  return (
    <>
      <Sec title={t("insp_selection", { n: clips.length })}>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
          <button type="button" className="btn btn-sm btn-danger" onClick={() => actions.remove(true)}><Icon name="trash" size={14} />{t("delete")}</button>
          <button type="button" className="btn btn-sm btn-danger" onClick={() => actions.remove(false)}><Icon name="trash" size={14} />{t("delete_nogap")}</button>
          <button type="button" className="btn btn-sm" onClick={() => actions.duplicate()}><Icon name="copy" size={14} />{t("duplicate")}</button>
        </div>
      </Sec>
      {media.length ? (
        <Sec title={t("insp_speed")}>
          <Row label={t("speed")}>
            <div style={{ display: "flex", gap: 6 }}>
              <NumInput value={speed} min={0.1} max={16} step={0.25} decimals={2} onCommit={setSpeed} />
              <button type="button" className="btn btn-sm" onClick={() => ed.edit(media.map(({ clip }) => ({ op: "speed", clip: clip.id, speed })), t("lbl_speed"))}>{t("apply")}</button>
            </div>
          </Row>
        </Sec>
      ) : null}
      {media.length ? <EffectsSection clip={null} ids={media.map(({ clip }) => clip.id)} /> : null}
    </>
  );
}

// ------------------------------------------------------------------ track
function TrackInspector({ track }) {
  const { t } = useApp();
  const ed = useEd();
  const [vol, setVol] = useState(track.volume_db);
  const timer = useRef(0);
  useEffect(() => { setVol(track.volume_db); }, [track.id, track.volume_db]);
  const set = (props) => ed.edit([{ op: "track_set", track: track.id, props }], t("lbl_track"));
  const setVolDebounced = (v) => {
    setVol(v);
    clearTimeout(timer.current);
    timer.current = setTimeout(() => set({ volume_db: v }), 250);
  };
  return (
    <>
      <Sec title={t("insp_track")}>
        <Row label={t("name")}><input className="field" key={track.id} defaultValue={track.name} onBlur={(e) => e.target.value !== track.name && set({ name: e.target.value })} onKeyDown={(e) => e.key === "Enter" && e.target.blur()} /></Row>
        <Row label={t("type")}><span className="chip">{t(`track_${track.kind}`)} · {track.role}</span></Row>
        {track.kind !== "text" ? <Row label={t("mute")}><Toggle checked={track.muted} onChange={(v) => set({ muted: v })} label="" /></Row> : null}
        {track.kind !== "audio" ? <Row label={t("hide")}><Toggle checked={track.hidden} onChange={(v) => set({ hidden: v })} label="" /></Row> : null}
        <Row label={t("lock")}><Toggle checked={track.locked} onChange={(v) => set({ locked: v })} label="" /></Row>
        {track.kind !== "text" ? <SliderRow label={t("volume")} value={vol} min={-60} max={24} step={0.5} decimals={1} defaultValue={0} onChange={setVolDebounced} /> : null}
        {track.kind === "audio" ? <Row label={t("duck")}><Toggle checked={track.duck} onChange={(v) => set({ duck: v })} label={t("duck_help")} /></Row> : null}
        <div style={{ marginTop: 10 }}>
          <ConfirmButton icon="trash" label={t("track_delete")} confirmLabel={t("confirm_delete")} cancelLabel={t("cancel")} onConfirm={() => { ed.edit([{ op: "track_delete", track: track.id }], t("lbl_track_del")); ed.setSelection({ ids: [], track: null }); }} />
        </div>
      </Sec>
    </>
  );
}

// ------------------------------------------------------------------ project
function ProjectInspector() {
  const { t, presets } = useApp();
  const ed = useEd();
  const { doc } = ed;
  const c = doc.canvas;
  const set = (op) => ed.edit([{ op: "canvas", ...op }], t("lbl_canvas"));
  const current = presets ? Object.entries(presets.canvas_presets).find(([, p]) => p.width === c.width && p.height === c.height && p.fps === c.fps)?.[0] || "" : "";
  return (
    <>
      <Sec title={t("insp_project")}>
        <Row label={t("canvas")}>
          <select className="field" value={current} onChange={(e) => e.target.value && set({ preset: e.target.value })}>
            <option value="">{t("custom")}</option>
            {Object.entries(presets?.canvas_presets || {}).map(([k, p]) => <option key={k} value={k}>{p.label}</option>)}
          </select>
        </Row>
        <Row label={t("width")}><NumInput value={c.width} min={64} max={7680} step={2} decimals={0} onCommit={(v) => set({ width: Math.round(v) })} /></Row>
        <Row label={t("height")}><NumInput value={c.height} min={64} max={7680} step={2} decimals={0} onCommit={(v) => set({ height: Math.round(v) })} /></Row>
        <Row label="FPS"><NumInput value={c.fps} min={1} max={240} step={1} decimals={0} onCommit={(v) => set({ fps: v })} /></Row>
        <Row label={t("background")}><ColorInput value={c.background} onChange={(v) => set({ background: v })} /></Row>
        <Row label={t("length_mode")}>
          <Seg value={doc.length_mode} onChange={(v) => set({ length_mode: v })} options={[{ value: "main", label: t("len_main"), title: t("len_main_help") }, { value: "longest", label: t("len_longest"), title: t("len_longest_help") }]} />
        </Row>
        <div className="muted" style={{ fontSize: 11.5 }}>{doc.length_mode === "main" ? t("len_main_help") : t("len_longest_help")}</div>
      </Sec>
      <Sec title={t("insp_markers", { n: doc.markers.length })}>
        {doc.markers.length === 0 ? <div className="muted" style={{ fontSize: 12 }}>{t("markers_empty")}</div> : null}
        {doc.markers.map((m) => (
          <div key={m.id} style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
            <span style={{ width: 8, height: 8, borderRadius: 2, background: m.color, flex: "none" }} />
            <button type="button" className="btn btn-ghost btn-sm mono" onClick={() => ed.pb.seek(m.t)}>{fmtMs(m.t)}</button>
            <span className="ellipsis muted" style={{ flex: 1, fontSize: 12 }}>{m.label || t(`marker_kind_${m.kind}`)}</span>
            <button type="button" className="btn btn-ghost btn-icon btn-sm" aria-label={t("remove")} onClick={() => ed.edit([{ op: "marker_delete", id: m.id }], t("lbl_marker_del"))}><Icon name="x" size={12} /></button>
          </div>
        ))}
        <div style={{ display: "flex", gap: 6, marginTop: 6 }}>
          <button type="button" className="btn btn-sm" onClick={() => ed.actions.addMarker()}><Icon name="marker" size={14} />{t("marker_add")}</button>
          {doc.markers.length ? <ConfirmButton label={t("markers_clear")} confirmLabel={t("confirm_delete")} cancelLabel={t("cancel")} onConfirm={() => ed.edit([{ op: "marker_delete", kind: "note" }, { op: "marker_delete", kind: "beat" }, { op: "marker_delete", kind: "scene" }, { op: "marker_delete", kind: "highlight" }, { op: "marker_delete", kind: "chapter" }], t("lbl_marker_del"))} /> : null}
        </div>
      </Sec>
    </>
  );
}

export default function Inspector() {
  const { t } = useApp();
  const ed = useEd();
  const { doc, selection } = ed;
  const clips = ed.actions.selectedClips;
  const track = selection.track ? doc.tracks.find((x) => x.id === selection.track) : null;
  let body;
  if (clips.length === 1) body = <ClipInspector key={clips[0].clip.id} clip={clips[0].clip} track={clips[0].track} media={clips[0].clip.media ? ed.view.media[clips[0].clip.media] : null} />;
  else if (clips.length > 1) body = <MultiInspector clips={clips} />;
  else if (track) body = <TrackInspector key={track.id} track={track} />;
  else body = <ProjectInspector />;
  return (
    <aside className="ed-right" aria-label={t("inspector")}>
      {body}
    </aside>
  );
}
