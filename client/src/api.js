// Thin fetch wrapper: JSON in/out, `{ error }` bodies become exceptions (with `status` and `code`).
async function request(method, path, { params, body, form } = {}) {
  const url = new URL(path, window.location.origin);
  for (const [key, value] of Object.entries(params || {})) {
    if (value !== undefined && value !== null && value !== "") url.searchParams.set(key, value);
  }
  const init = { method };
  if (form) {
    init.body = form;
  } else if (body !== undefined) {
    init.headers = { "Content-Type": "application/json" };
    init.body = JSON.stringify(body);
  }
  let response;
  try {
    response = await fetch(url, init);
  } catch {
    const error = new Error("network");
    error.code = "network";
    throw error;
  }
  const text = await response.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = { error: text };
  }
  if (!response.ok) {
    const detail = data && (data.error || (typeof data.detail === "string" ? data.detail : null));
    const error = new Error(detail || `Error ${response.status}`);
    error.status = response.status;
    error.code = data && data.code;
    throw error;
  }
  return data;
}

const e = encodeURIComponent;

export const api = {
  health: () => request("GET", "/api/health"),
  status: () => request("GET", "/api/status"),
  presets: () => request("GET", "/api/presets"),
  settings: () => request("GET", "/api/settings"),
  settingsUpdate: (body) => request("PATCH", "/api/settings", { body }),
  reveal: (path) => request("POST", "/api/reveal", { body: { path } }),
  fs: (path) => request("GET", "/api/fs", { params: { path } }),

  // media
  media: () => request("GET", "/api/media"),
  mediaGet: (id) => request("GET", `/api/media/${e(id)}`),
  mediaImport: (body) => request("POST", "/api/media/import", { body }),
  mediaUpload: (file) => {
    const form = new FormData();
    form.append("file", file);
    return request("POST", "/api/media/upload", { form });
  },
  mediaPatch: (id, body) => request("PATCH", `/api/media/${e(id)}`, { body }),
  mediaDelete: (id, force) => request("DELETE", `/api/media/${e(id)}`, { params: { force: force ? "true" : "" } }),
  mediaAnalyze: (id, kinds, force, extra) => request("POST", `/api/media/${e(id)}/analyze`, { body: { kinds, force: !!force, ...(extra || {}) } }),
  mediaSpeakers: (id) => request("GET", `/api/media/${e(id)}/speakers`),
  speakersEdit: (id, body) => request("POST", `/api/media/${e(id)}/speakers`, { body }),
  mediaTranscriptFix: (id, changes) => request("PATCH", `/api/media/${e(id)}/transcript`, { body: { changes } }),
  highlights: (id, params) => request("GET", `/api/media/${e(id)}/highlights`, { params }),
  short: (id, body) => request("POST", `/api/media/${e(id)}/short`, { body }),

  // projects
  projects: () => request("GET", "/api/projects"),
  projectCreate: (body) => request("POST", "/api/projects", { body }),
  timelineImport: (body) => request("POST", "/api/projects/import-timeline", { body }),
  otioUrl: (id) => `/api/projects/${e(id)}/otio`,
  project: (id) => request("GET", `/api/projects/${e(id)}`),
  projectRename: (id, name) => request("PATCH", `/api/projects/${e(id)}`, { body: { name } }),
  projectDelete: (id) => request("DELETE", `/api/projects/${e(id)}`),
  edit: (id, body) => request("POST", `/api/projects/${e(id)}/edit`, { body }),
  undo: (id) => request("POST", `/api/projects/${e(id)}/undo`),
  redo: (id) => request("POST", `/api/projects/${e(id)}/redo`),
  command: (id, body) => request("POST", `/api/projects/${e(id)}/command`, { body }),
  transcript: (id) => request("GET", `/api/projects/${e(id)}/transcript`),
  textCut: (id, body) => request("POST", `/api/projects/${e(id)}/text-cut`, { body }),
  multicamSync: (body) => request("POST", "/api/multicam/sync", { body }),
  multicam: (id) => request("GET", `/api/projects/${e(id)}/multicam`),
  multicamFrameUrl: (id, group, angle, t, width, stamp) => `/api/projects/${e(id)}/multicam/frame?group=${e(group)}&angle=${e(angle)}&t=${Math.round(t)}&width=${Math.round(width)}&v=${stamp ?? ""}`,
  freeze: (id, body) => request("POST", `/api/projects/${e(id)}/freeze`, { body }),
  stabilize: (id, body) => request("POST", `/api/projects/${e(id)}/stabilize`, { body }),
  musicPick: (id, params) => request("GET", `/api/projects/${e(id)}/music`, { params }),
  broll: (id, body) => request("POST", `/api/projects/${e(id)}/broll`, { body }),
  templateSave: (id, body) => request("POST", `/api/projects/${e(id)}/template`, { body }),
  templates: () => request("GET", "/api/templates"),
  templateCreate: (templateId, body) => request("POST", `/api/templates/${e(templateId)}/create`, { body }),
  render: (id, body) => request("POST", `/api/projects/${e(id)}/render`, { body }),
  nest: (id, body) => request("POST", `/api/projects/${e(id)}/nest`, { body }),
  nesting: (id) => request("GET", `/api/projects/${e(id)}/nesting`),
  sequencePrepare: (id) => request("POST", `/api/projects/${e(id)}/sequence/prepare`),
  frameUrl: (id, t, width, stamp) => `/api/projects/${e(id)}/frame?t=${Math.round(t)}&width=${Math.round(width)}&v=${stamp ?? ""}`,

  // translated subtitles
  subtitles: (id) => request("GET", `/api/projects/${e(id)}/subtitles`),
  subtitlesTranslate: (id, body) => request("POST", `/api/projects/${e(id)}/subtitles/translate`, { body }),
  subtitlesShow: (id, language, params) => request("GET", `/api/projects/${e(id)}/subtitles/${e(language)}`, { params }),
  subtitlesFix: (id, language, changes) => request("PATCH", `/api/projects/${e(id)}/subtitles/${e(language)}`, { body: { changes } }),
  subtitlesDelete: (id, language) => request("DELETE", `/api/projects/${e(id)}/subtitles/${e(language)}`),
  subtitlesUrl: (id, fmt, language, dual) => `/api/projects/${e(id)}/subtitles.${fmt}?language=${e(language || "")}&dual=${dual ? "true" : "false"}`,

  // plans
  plans: (id) => request("GET", `/api/projects/${e(id)}/plans`),
  planCreate: (id, body) => request("POST", `/api/projects/${e(id)}/plans`, { body }),
  planUpdate: (planId, steps) => request("PATCH", `/api/plans/${e(planId)}`, { body: { steps } }),
  planApply: (planId) => request("POST", `/api/plans/${e(planId)}/apply`),
  planDiscard: (planId) => request("POST", `/api/plans/${e(planId)}/discard`),

  // jobs / renders
  jobs: (params) => request("GET", "/api/jobs", { params }),
  job: (id) => request("GET", `/api/jobs/${e(id)}`),
  jobCancel: (id) => request("POST", `/api/jobs/${e(id)}/cancel`),
  renders: (project) => request("GET", "/api/renders", { params: { project } }),
  renderUrl: (id, download) => `/api/renders/${e(id)}/file${download ? "?download=true" : ""}`,
  renderDelete: (id) => request("DELETE", `/api/renders/${e(id)}`),
};

// Binary waveform peaks (one byte per 10 ms of source time), cached per URL.
const waves = new Map();
export function loadWaveform(url) {
  if (!url) return Promise.resolve(null);
  if (!waves.has(url)) {
    waves.set(
      url,
      fetch(url)
        .then((r) => (r.ok ? r.arrayBuffer() : null))
        .then((b) => (b ? new Uint8Array(b) : null))
        .catch(() => null),
    );
  }
  return waves.get(url);
}
export function forgetWaveform(url) {
  waves.delete(url);
}
