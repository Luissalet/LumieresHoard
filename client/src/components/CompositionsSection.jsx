import React, { useEffect, useState } from "react";
import { useApp } from "../App.jsx";
import { Spinner } from "./ui.jsx";

const words = {
  en: {
    title: "Creative engines", effect: "EffectCraft", film: "FilmCraft",
    unavailable: "CLI not configured", titleText: "Title card text", duration: "Duration (seconds)",
    createTitle: "Create editable title card", makeSequence: "Import copy and export video",
    renderTitle: "Render animated title to H.264",
    running: "Working…", preview: "Preview", project: "Download editable project",
    render: "Download rendered video", receive: "Copy media_receive URL", tools: "Live native MCP tools",
    noVideo: "Select a video in Lumiere's library to create a FilmCraft sequence.",
    safe: "Source media is copied into this composition folder; the library original is unchanged.",
    error: "Creative engine failed", copied: "URL copied", linked: "Linked Lumiere project",
  },
  es: {
    title: "Motores creativos", effect: "EffectCraft", film: "FilmCraft",
    unavailable: "CLI sin configurar", titleText: "Texto de la cartela", duration: "Duración (segundos)",
    createTitle: "Crear cartela editable", makeSequence: "Importar copia y exportar vídeo",
    renderTitle: "Renderizar cartela animada a H.264",
    running: "Procesando…", preview: "Vista previa", project: "Descargar proyecto editable",
    render: "Descargar vídeo renderizado", receive: "Copiar URL para media_receive", tools: "Herramientas MCP nativas",
    noVideo: "Selecciona un vídeo de la biblioteca para crear una secuencia FilmCraft.",
    safe: "El medio se copia dentro de esta composición; el original de la biblioteca permanece intacto.",
    error: "Error del motor creativo", copied: "URL copiada", linked: "Proyecto Lumiere vinculado",
  },
};

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { "Content-Type": "application/json", ...options.headers },
  });
  const text = await response.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch { data = { error: text }; }
  if (!response.ok) throw new Error(data?.error || `HTTP ${response.status}`);
  return data;
}

export default function CompositionsSection({ mediaId = null, projectId = null }) {
  const { lang = "en", fail } = useApp();
  const t = words[String(lang).toLowerCase().startsWith("es") ? "es" : "en"];
  const [status, setStatus] = useState(null);
  const [title, setTitle] = useState("");
  const [duration, setDuration] = useState(3);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [catalogue, setCatalogue] = useState(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => { api("/api/creative/status").then(setStatus).catch((e) => setError(e.message)); }, []);

  const createTitle = async (e) => {
    e.preventDefault();
    setBusy(true); setError(""); setResult(null);
    try {
      setResult(await api("/api/creative/title-card", { method: "POST", body: JSON.stringify({ text: title, duration, project_id: projectId || null }) }));
    } catch (err) { setError(err.message); fail?.(err); }
    finally { setBusy(false); }
  };

  const createFilm = async () => {
    if (!mediaId) return;
    setBusy(true); setError(""); setResult(null);
    try {
      setResult(await api("/api/creative/film-sequence", { method: "POST", body: JSON.stringify({ media_id: mediaId, project_id: projectId || null }) }));
    } catch (err) { setError(err.message); fail?.(err); }
    finally { setBusy(false); }
  };

  const renderTitle = async () => {
    if (!result?.id) return;
    setBusy(true); setError("");
    try { setResult(await api(`/api/creative/${result.id}/render-video`, { method: "POST", body: "{}" })); }
    catch (err) { setError(err.message); fail?.(err); }
    finally { setBusy(false); }
  };

  const showTools = async (engine) => {
    setError("");
    try { setCatalogue(await api(`/api/creative/tools/${engine}`)); }
    catch (err) { setError(err.message); }
  };

  const copyReceive = async () => {
    const url = result?.media_receive_url;
    if (!url) return;
    await navigator.clipboard.writeText(url);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1800);
  };

  const engines = status?.engines || {};
  const ready = (name) => !!engines[name]?.available;
  const statusLabel = (name) => ready(name) ? `${engines[name].release} · ${engines[name].expected_tools}` : t.unavailable;

  return (
    <section className="creative-engines" aria-labelledby="creative-engines-title" style={{ display: "grid", gap: 16, margin: "20px 0" }}>
      <header style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
        <h2 id="creative-engines-title" style={{ margin: 0 }}>{t.title}</h2>
        {projectId && <span className="muted" style={{ fontSize: 12 }}>{t.linked}: <code>{projectId}</code></span>}
      </header>
      <div style={{ display: "flex", alignItems: "center", gap: 14, flexWrap: "wrap", fontSize: 12 }}>
        <span><strong>{t.effect}</strong> · {statusLabel("effectcraft")}</span>
        <button type="button" className="btn" disabled={!ready("effectcraft")} onClick={() => showTools("effectcraft")}>{t.tools}</button>
        <span><strong>{t.film}</strong> · {statusLabel("filmcraft")}</span>
        <button type="button" className="btn" disabled={!ready("filmcraft")} onClick={() => showTools("filmcraft")}>{t.tools}</button>
      </div>

      <form onSubmit={createTitle} style={{ display: "grid", gridTemplateColumns: "minmax(200px, 1fr) 130px auto", alignItems: "end", gap: 10 }}>
        <label className="field-label" style={{ display: "grid", gap: 5 }}>
          <span>{t.titleText}</span>
          <input className="field" value={title} maxLength={300} required onChange={(e) => setTitle(e.target.value)} />
        </label>
        <label className="field-label" style={{ display: "grid", gap: 5 }}>
          <span>{t.duration}</span>
          <input className="field" type="number" min="0.5" max="30" step="0.5" value={duration} onChange={(e) => setDuration(Number(e.target.value))} />
        </label>
        <button type="submit" className="btn btn-primary" disabled={busy || !ready("effectcraft") || !title.trim()}>
          {busy ? <Spinner /> : null}{t.createTitle}
        </button>
      </form>

      <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
        <button type="button" className="btn" disabled={busy || !ready("filmcraft") || !mediaId} onClick={createFilm}>
          {busy ? <Spinner /> : null}{t.makeSequence}
        </button>
        {!mediaId && <span className="muted" style={{ fontSize: 12 }}>{t.noVideo}</span>}
      </div>
      <p className="muted" style={{ margin: 0, fontSize: 12 }}>{t.safe}</p>
      {error && <p className="error" role="alert">{t.error}: {error}</p>}
      {catalogue && <details open style={{ maxHeight: 250, overflow: "auto" }}>
        <summary>{catalogue.engine} · {catalogue.count} live MCP tools</summary>
        <ul>{catalogue.tools.map((tool) => <li key={tool.name}><code>{tool.name}</code> — {tool.description}</li>)}</ul>
      </details>}
      {result && (
        <div className="creative-result" style={{ display: "grid", gap: 8, borderTop: "1px solid var(--line)", paddingTop: 14 }}>
          {result.preview_url && <img src={result.preview_url} alt={t.preview} style={{ maxWidth: "100%", maxHeight: 260, objectFit: "contain", justifySelf: "start" }} />}
          {result.project_url && <a href={result.project_url}>{t.project}</a>}
          {result.engine === "effectcraft" && !result.render_url && <button type="button" className="btn btn-primary" disabled={busy} onClick={renderTitle}>{busy ? <Spinner /> : null}{t.renderTitle}</button>}
          {result.render_url && <a href={result.render_url}>{t.render}</a>}
          {result.media_receive_url && <button type="button" className="btn" onClick={copyReceive}>{copied ? t.copied : t.receive}</button>}
          <code style={{ fontSize: 11, overflowWrap: "anywhere" }}>{result.native_path}</code>
          {result.render_path && <code style={{ fontSize: 11, overflowWrap: "anywhere" }}>{result.render_path}</code>}
        </div>
      )}
    </section>
  );
}
