"""Who speaks when: speaker separation (diarization) of a word-level transcript, entirely local.

Two engines share one clustering core:

* **embeddings** (optional, ``requirements-speakers.txt``): when speechbrain's ECAPA model or resemblyzer is installed, every
  speech segment gets a voice embedding and segments are grouped by cosine distance. Nothing is downloaded from a gated source.
* **built in** (always there): per word, spectral features computed with numpy only (cepstral means of a log-mel
  filterbank and the median pitch), then agglomerative clustering with an automatic number of speakers (or the number the
  person gives), a re-assignment of every word to the nearest voice and a light smoothing of isolated flips. It is an
  approximation: clearly different voices separate well, similar voices of the same pitch may merge, and one voice
  seldom splits (the number of speakers is only raised when the gap between voices is clear).

Everything here is a pure function of the audio samples and the words; ``speakers.py`` does the storing.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional

import numpy as np

log = logging.getLogger("lumiere.speakers")

RATE = 16000
WIN = 400          # 25 ms
HOP = 160          # 10 ms
NFFT = 512
PITCH_WIN = 640    # 40 ms: two periods of the lowest voice
PITCH_NFFT = 2048
N_MEL = 26
N_CEP = 4         # c1..c4: the broad spectral shape (brightness, first resonances); finer coefficients mostly follow the vowel being said
F0_WEIGHT = 6.0   # the pitch counts this many cepstral coefficients: it is the cue that separates voices best
MAX_SPEAKERS = 8
PALETTE = ["#4FC3F7", "#FFB74D", "#81C784", "#F06292", "#BA68C8", "#4DB6AC", "#FFD54F", "#A1887F"]


# ---------------------------------------------------------------- features

def _mel_bank() -> np.ndarray:
    def hz_to_mel(f):
        return 2595.0 * np.log10(1.0 + f / 700.0)

    def mel_to_hz(m):
        return 700.0 * (10 ** (m / 2595.0) - 1.0)

    pts = mel_to_hz(np.linspace(hz_to_mel(100.0), hz_to_mel(7600.0), N_MEL + 2))
    bins = np.floor((NFFT + 1) * pts / RATE).astype(int)
    bank = np.zeros((N_MEL, NFFT // 2 + 1))
    for i in range(N_MEL):
        a, b, c = bins[i], bins[i + 1], bins[i + 2]
        if b > a:
            bank[i, a:b] = (np.arange(a, b) - a) / (b - a)
        if c > b:
            bank[i, b:c] = (c - np.arange(b, c)) / (c - b)
    return bank


def _dct_matrix() -> np.ndarray:
    n = np.arange(N_MEL)
    return np.array([np.cos(np.pi * k * (2 * n + 1) / (2 * N_MEL)) for k in range(1, N_CEP + 1)])  # c1..c4 (c0 is loudness)


_BANK = _mel_bank()
_DCT = _dct_matrix()
_HAMMING = np.hamming(WIN)
_PITCH_HANN = np.hanning(PITCH_WIN)


def frame_features(audio: np.ndarray, frames: Optional[np.ndarray] = None, block: int = 1500) -> dict[str, np.ndarray]:
    """Per 10 ms frame: cepstra c1..c12, f0 in Hz (0 = unvoiced), voicing strength and level in dB. ``frames`` limits the work to the
    given frame indexes (the frames of words); pitch needs a longer window than the cepstra, centred on the same frame."""
    audio = np.asarray(audio, dtype=np.float32)
    n_frames = max(0, (audio.size - WIN) // HOP + 1)
    idx = np.arange(n_frames) if frames is None else np.asarray(frames, dtype=np.int64)
    idx = idx[(idx >= 0) & (idx < n_frames)]
    cep = np.zeros((idx.size, N_CEP), dtype=np.float32)
    f0 = np.zeros(idx.size, dtype=np.float32)
    voicing = np.zeros(idx.size, dtype=np.float32)
    level = np.full(idx.size, -120.0, dtype=np.float32)
    pre = np.concatenate([audio[:1], audio[1:] - 0.97 * audio[:-1]]) if audio.size else audio
    lo_lag, hi_lag = int(RATE / 400), int(RATE / 70)
    for s in range(0, idx.size, block):
        part = idx[s: s + block]
        starts = part * HOP
        take = starts[:, None] + np.arange(WIN)[None, :]
        raw = audio[take]
        level[s: s + part.size] = 10 * np.log10(np.mean(raw.astype(np.float64) ** 2, axis=1) + 1e-12)
        spec = np.abs(np.fft.rfft(pre[take] * _HAMMING, NFFT, axis=1)) ** 2
        logmel = np.log(spec @ _BANK.T + 1e-10)
        cep[s: s + part.size] = logmel @ _DCT.T
        centre = starts + WIN // 2
        a = centre[:, None] - PITCH_WIN // 2 + np.arange(PITCH_WIN)[None, :]
        a = np.clip(a, 0, audio.size - 1)
        seg = audio[a] * _PITCH_HANN
        seg = seg - seg.mean(axis=1, keepdims=True)
        f = np.fft.rfft(seg, PITCH_NFFT, axis=1)
        ac = np.fft.irfft(np.abs(f) ** 2, PITCH_NFFT, axis=1)[:, : hi_lag + 2]
        r0 = ac[:, 0] + 1e-9
        r = ac / r0[:, None]
        win_r = r[:, lo_lag: hi_lag + 1]
        # the first strong peak, not the highest: the second period is as high and would halve the pitch
        best = win_r.max(axis=1)
        cand = win_r >= (0.88 * best)[:, None]
        # local maxima only
        peak = np.zeros_like(cand)
        peak[:, 1:-1] = (win_r[:, 1:-1] >= win_r[:, :-2]) & (win_r[:, 1:-1] >= win_r[:, 2:])
        pick = np.argmax(cand & peak, axis=1)
        ok = (cand & peak)[np.arange(part.size), pick]
        lag = (pick + lo_lag).astype(np.float64)
        # parabolic refinement of the peak
        k = np.clip(pick, 1, win_r.shape[1] - 2)
        y0, y1, y2 = win_r[np.arange(part.size), k - 1], win_r[np.arange(part.size), k], win_r[np.arange(part.size), k + 1]
        den = y0 - 2 * y1 + y2
        shift = np.where(np.abs(den) > 1e-9, 0.5 * (y0 - y2) / np.where(den == 0, 1, den), 0.0)
        lag = lag + np.where(k == pick, np.clip(shift, -1, 1), 0.0)
        voiced = ok & (best > 0.45)
        f0[s: s + part.size] = np.where(voiced, RATE / np.maximum(lag, 1.0), 0.0)
        voicing[s: s + part.size] = best
    return {"frames": idx, "cep": cep, "f0": f0, "voicing": voicing, "level": level}


def word_features(audio: np.ndarray, words: list[dict[str, Any]]) -> tuple[np.ndarray, np.ndarray]:
    """One feature row per word (c1..c12 minus the file's mean, log pitch) and a ``valid`` mask. Words without enough sound
    (very short, or under the noise floor) are invalid; the caller gives them the speaker of their neighbours."""
    n = len(words)
    spans = []
    need: list[np.ndarray] = []
    for w in words:
        a = int(max(0, round(w["t0"] / 10)))
        b = int(max(a + 1, round(w["t1"] / 10)))
        spans.append((a, b))
        need.append(np.arange(a, b))
    if not need:
        return np.zeros((0, N_CEP + 1)), np.zeros(0, dtype=bool)
    frames = np.unique(np.concatenate(need))
    ff = frame_features(audio, frames)
    pos = {int(f): i for i, f in enumerate(ff["frames"])}
    # the frames are all inside words: "active" means not far below the loud ones (word edges and breaths are skipped)
    active_floor = float(np.percentile(ff["level"], 95)) - 28.0 if ff["level"].size else -100.0
    active_all = ff["level"] > active_floor
    mean_cep = ff["cep"][active_all].mean(axis=0) if active_all.any() else np.zeros(N_CEP)
    feats = np.zeros((n, N_CEP + 1), dtype=np.float64)
    valid = np.zeros(n, dtype=bool)
    logf0_all = np.full(n, np.nan)
    for i, (a, b) in enumerate(spans):
        rows = np.array([pos[f] for f in range(a, b) if f in pos], dtype=np.int64)
        if rows.size == 0:
            continue
        rows = rows[active_all[rows]]
        if rows.size < 3:
            continue
        vf = rows[ff["f0"][rows] > 0]
        use = vf if vf.size >= 3 else rows
        wts = np.clip(ff["level"][use] - active_floor + 1.0, 1.0, None)
        feats[i, :N_CEP] = (ff["cep"][use] * wts[:, None]).sum(axis=0) / wts.sum() - mean_cep
        if vf.size >= 3:
            logf0_all[i] = float(np.log(np.median(ff["f0"][vf])))
        valid[i] = True
    known = ~np.isnan(logf0_all)
    fill = float(np.median(logf0_all[known])) if known.any() else 0.0
    feats[:, N_CEP] = np.where(known, logf0_all, fill)
    return feats, valid


def standardise(feats: np.ndarray, valid: np.ndarray) -> np.ndarray:
    """Robust z-scores (median / MAD) over the valid rows, the pitch column weighted up."""
    out = np.zeros_like(feats)
    ref = feats[valid] if valid.any() else feats
    med = np.median(ref, axis=0)
    spread = 1.4826 * np.median(np.abs(ref - med), axis=0)
    spread = np.where(spread < 1e-6, ref.std(axis=0) + 1e-6, spread)
    out = (feats - med) / spread
    out[:, N_CEP] *= F0_WEIGHT
    return out


# ---------------------------------------------------------------- clustering

def _kmeans_micro(x: np.ndarray, k: int, iters: int = 6) -> tuple[np.ndarray, np.ndarray]:
    """Farthest-point initialised k-means: (centroids, assignment). Deterministic."""
    n = x.shape[0]
    cent = [x[0]]
    d = np.sum((x - cent[0]) ** 2, axis=1)
    for _ in range(1, k):
        i = int(np.argmax(d))
        cent.append(x[i])
        d = np.minimum(d, np.sum((x - x[i]) ** 2, axis=1))
    c = np.array(cent)
    assign = np.zeros(n, dtype=np.int64)
    for _ in range(iters):
        dist = ((x[:, None, :] - c[None, :, :]) ** 2).sum(axis=2)
        assign = dist.argmin(axis=1)
        for j in range(k):
            m = assign == j
            if m.any():
                c[j] = x[m].mean(axis=0)
    return c, assign


def agglomerate(points: np.ndarray, sizes: np.ndarray) -> tuple[list[tuple[int, int, float]], int]:
    """Average-linkage clustering of weighted points: the merges [(a, b, height), ...] in order (ids >= len(points) are earlier
    merges) and the number of points."""
    m = points.shape[0]
    d = np.sqrt(((points[:, None, :] - points[None, :, :]) ** 2).sum(axis=2))
    np.fill_diagonal(d, np.inf)
    ids = list(range(m))
    size = {i: float(sizes[i]) for i in range(m)}
    alive = np.ones(m, dtype=bool)
    merges: list[tuple[int, int, float]] = []
    nxt = m
    node = np.arange(m)  # row -> cluster id
    for _ in range(m - 1):
        masked = np.where(alive[:, None] & alive[None, :], d, np.inf)
        flat = int(np.argmin(masked))
        i, j = divmod(flat, m)
        h = float(masked[i, j])
        merges.append((int(node[i]), int(node[j]), h))
        si, sj = size[int(node[i])], size[int(node[j])]
        new = (si * d[i] + sj * d[j]) / (si + sj)
        d[i, :] = new
        d[:, i] = new
        d[i, i] = np.inf
        alive[j] = False
        size[nxt] = si + sj
        node[i] = nxt
        nxt += 1
    return merges, m


def cut_tree(merges: list[tuple[int, int, float]], m: int, k: int) -> np.ndarray:
    """Cluster index (0..k-1) of every original point when the tree is cut into ``k`` clusters."""
    parent = list(range(m + len(merges)))

    def find(a: int) -> int:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for step, (a, b, _) in enumerate(merges[: max(0, m - k)]):
        parent[find(a)] = m + step
        parent[find(b)] = m + step
    roots: dict[int, int] = {}
    out = np.zeros(m, dtype=np.int64)
    for i in range(m):
        out[i] = roots.setdefault(find(i), len(roots))
    return out


def separation(points: np.ndarray, labels: np.ndarray, k: int, min_words: int) -> float:
    """The weakest pairwise separation between the ``k`` clusters: centre distance over the sum of the clusters' radii (0 when a
    cluster is too small to be a voice). A voice split in two by chance scores about 1; two real voices score 2 or more."""
    cents, rad, ok = [], [], True
    for j in range(k):
        sel = labels == j
        if sel.sum() < min_words:
            ok = False
            break
        c = points[sel].mean(axis=0)
        cents.append(c)
        rad.append(float(np.sqrt(np.mean(np.sum((points[sel] - c) ** 2, axis=1)))))
    if not ok:
        return 0.0
    return min(float(np.linalg.norm(cents[a] - cents[b]) / (rad[a] + rad[b] + 1e-9)) for a in range(k) for b in range(a + 1, k))


def smooth_labels(labels: np.ndarray, d: np.ndarray, words: list[dict[str, Any]], max_gap_ms: int = 160) -> np.ndarray:
    """Relabel a word that differs from both neighbours when they agree, they are close in time and its own evidence is weak."""
    out = labels.copy()
    n = len(words)
    for i in range(1, n - 1):
        if out[i - 1] == out[i + 1] != out[i]:
            near = words[i]["t0"] - words[i - 1]["t1"] <= max_gap_ms and words[i + 1]["t0"] - words[i]["t1"] <= max_gap_ms
            order = np.sort(d[i])
            weak = order[0] > 0.0 and (order[1] - order[0]) / (order[1] + order[0] + 1e-9) < 0.18 if order.size > 1 else False
            short = words[i]["t1"] - words[i]["t0"] < 220
            if near and (weak or short) and d[i, out[i - 1]] <= 1.6 * d[i, out[i]]:
                out[i] = out[i - 1]
    return out


def cluster_words(x: np.ndarray, valid: np.ndarray, words: list[dict[str, Any]], *, num_speakers: Optional[int], max_speakers: int,
                  min_sep: float) -> dict[str, Any]:
    """Labels for every word (invalid words take their neighbours') from the standardised features ``x``."""
    n = len(words)
    idx = np.flatnonzero(valid)
    if idx.size == 0:
        return {"labels": np.zeros(n, dtype=np.int64), "k": 1, "confidence": 0.0, "heights": []}
    pts = x[idx]
    if idx.size > 220:
        cents, assign = _kmeans_micro(pts, 160)
        sizes = np.bincount(assign, minlength=cents.shape[0]).astype(np.float64)
        keep = sizes > 0
        remap = -np.ones(cents.shape[0], dtype=np.int64)
        remap[keep] = np.arange(int(keep.sum()))
        cents, sizes, assign = cents[keep], sizes[keep], remap[assign]
    else:
        cents, sizes, assign = pts.copy(), np.ones(pts.shape[0]), np.arange(pts.shape[0])
    merges, m = agglomerate(cents, sizes)
    info: dict[str, Any] = {"heights": []}
    if num_speakers:
        k = int(max(1, min(num_speakers, m, MAX_SPEAKERS)))
    else:
        k = 1
        min_words = max(3, int(0.05 * pts.shape[0]))
        for kk in range(2, min(max_speakers, MAX_SPEAKERS, m) + 1):
            sep = separation(pts, cut_tree(merges, m, kk)[assign], kk, min_words)
            info["heights"].append(round(sep, 2))
            if sep >= min_sep:
                k = kk
    micro_label = cut_tree(merges, m, k)
    lab = micro_label[assign]
    # re-assign every word to the nearest voice (centroids from the words, not from the micro clusters), twice
    cent = np.array([np.average(pts[lab == j], axis=0) if (lab == j).any() else pts.mean(axis=0) for j in range(k)])
    for _ in range(2):
        d_all = np.sqrt(((x[:, None, :] - cent[None, :, :]) ** 2).sum(axis=2))
        lab_all = d_all.argmin(axis=1)
        for j in range(k):
            sel = valid & (lab_all == j)
            if sel.any():
                cent[j] = x[sel].mean(axis=0)
    d_all = np.sqrt(((x[:, None, :] - cent[None, :, :]) ** 2).sum(axis=2))
    labels = d_all.argmin(axis=1)
    if k > 1:
        labels = smooth_labels(labels, d_all, words)
    # words without evidence: the nearest valid word in time
    if (~valid).any():
        for i in np.flatnonzero(~valid):
            j = idx[np.argmin(np.abs(idx - i))]
            labels[i] = labels[j]
    conf = 0.0
    if k > 1:
        two = np.sort(d_all[valid], axis=1)
        conf = float(np.mean((two[:, 1] - two[:, 0]) / (two[:, 1] + two[:, 0] + 1e-9)))
    return {"labels": labels, "k": k, "confidence": round(conf, 3), "heights": info.get("heights", [])}


# ---------------------------------------------------------------- optional embedding engines

_EMBEDDER: Any = False


def embedder_status() -> dict[str, Any]:
    """Which voice-embedding library is installed: speechbrain (ECAPA), resemblyzer or none."""
    for name in ("speechbrain", "resemblyzer"):
        try:
            __import__(name)
            return {"available": True, "engine": name}
        except Exception:  # noqa: BLE001 - not installed, or its dependencies (torch) are broken
            continue
    return {"available": False, "engine": None}


def _load_embedder() -> Optional[Callable[[np.ndarray], np.ndarray]]:
    global _EMBEDDER
    if _EMBEDDER is not False:
        return _EMBEDDER
    _EMBEDDER = None
    try:
        from speechbrain.inference.speaker import EncoderClassifier  # type: ignore
        import torch  # type: ignore

        model = EncoderClassifier.from_hparams(source="speechbrain/spkrec-ecapa-voxceleb", run_opts={"device": "cpu"})

        def embed(wav: np.ndarray) -> np.ndarray:
            with torch.no_grad():
                e = model.encode_batch(torch.from_numpy(wav.astype(np.float32))[None, :])
            return e.squeeze().cpu().numpy()

        _EMBEDDER = embed
        return _EMBEDDER
    except Exception as error:  # noqa: BLE001
        log.info("speechbrain is not usable (%s)", error)
    try:
        from resemblyzer import VoiceEncoder  # type: ignore

        enc = VoiceEncoder(device="cpu")
        _EMBEDDER = lambda wav: enc.embed_utterance(wav.astype(np.float32))  # noqa: E731
    except Exception as error:  # noqa: BLE001
        log.info("resemblyzer is not usable (%s)", error)
    return _EMBEDDER


def speech_chunks(words: list[dict[str, Any]], gap_ms: int = 350, max_ms: int = 8000) -> list[tuple[int, int]]:
    """Index ranges [a, b) of words that form one chunk of continuous speech (pause or length limit ends it)."""
    out: list[tuple[int, int]] = []
    a = 0
    for i in range(1, len(words) + 1):
        if i == len(words) or words[i]["t0"] - words[i - 1]["t1"] > gap_ms or words[i]["t1"] - words[a]["t0"] > max_ms:
            out.append((a, i))
            a = i
    return out


def _embedding_labels(audio: np.ndarray, words: list[dict[str, Any]], embed: Callable[[np.ndarray], np.ndarray], num_speakers: Optional[int],
                      max_speakers: int) -> Optional[dict[str, Any]]:
    chunks = speech_chunks(words)
    vecs, owners = [], []
    for a, b in chunks:
        t0, t1 = words[a]["t0"], words[b - 1]["t1"]
        if t1 - t0 < 400:
            continue
        wav = audio[int(t0 * RATE / 1000): int(t1 * RATE / 1000)]
        if wav.size < RATE // 3:
            continue
        v = np.asarray(embed(wav), dtype=np.float64).ravel()
        vecs.append(v / (np.linalg.norm(v) + 1e-9))
        owners.append((a, b))
    if len(vecs) < 2:
        return None
    emb = np.array(vecs)
    merges, m = agglomerate(emb, np.array([b - a for a, b in owners], dtype=np.float64))
    if num_speakers:
        k = max(1, min(num_speakers, m, MAX_SPEAKERS))
    else:
        # cosine distance of unit vectors: sqrt(2 * (1 - cos)); different voices sit above 0.9 (cosine below ~0.6)
        k = 1
        for kk in range(2, min(max_speakers, MAX_SPEAKERS, m) + 1):
            h = merges[m - kk][2] if m - kk < len(merges) else 0.0
            if h >= 1.0:
                k = kk
    lab = cut_tree(merges, m, k)
    labels = np.zeros(len(words), dtype=np.int64)
    centroids = [emb[lab == j].mean(axis=0) for j in range(k)]
    for (a, b), l in zip(owners, lab):
        labels[a:b] = l
    # words of chunks too short to embed: nearest embedded chunk
    covered = np.zeros(len(words), dtype=bool)
    for a, b in owners:
        covered[a:b] = True
    for i in np.flatnonzero(~covered):
        j = int(np.argmin([min(abs(i - a), abs(i - (b - 1))) for a, b in owners]))
        labels[i] = lab[j]
    sims = [float(np.max([np.dot(e, c) / (np.linalg.norm(c) + 1e-9) for c in centroids])) for e in emb]
    return {"labels": labels, "k": k, "confidence": round(float(np.mean(sims)), 3), "heights": []}


# ---------------------------------------------------------------- entry point

def diarize(audio: np.ndarray, words: list[dict[str, Any]], *, num_speakers: Optional[int] = None, max_speakers: int = 6,
            engine: str = "auto") -> dict[str, Any]:
    """Speaker index per word, ordered by first appearance. ``engine``: auto or embeddings (voice embeddings when a library is
    installed, else built in), builtin (always the built-in engine)."""
    if not words:
        return {"labels": [], "k": 0, "method": "none", "confidence": 0.0}
    if num_speakers is not None and num_speakers < 1:
        raise ValueError("num_speakers must be at least 1.")
    method = "builtin"
    res: Optional[dict[str, Any]] = None
    if engine in ("auto", "embeddings"):
        embed = _load_embedder()
        if embed is not None:
            try:
                res = _embedding_labels(audio, words, embed, num_speakers, max_speakers)
                method = "embeddings"
            except Exception as error:  # noqa: BLE001 - fall back rather than fail the job
                log.warning("embedding diarization failed (%s); using the built-in engine", error)
                res = None
    if res is None:
        method = "builtin"
        feats, valid = word_features(audio, words)
        x = standardise(feats, valid)
        res = cluster_words(x, valid, words, num_speakers=num_speakers, max_speakers=max_speakers, min_sep=MIN_SEPARATION)
    labels = np.asarray(res["labels"], dtype=np.int64)
    order: dict[int, int] = {}
    for l in labels:
        order.setdefault(int(l), len(order))
    mapped = [order[int(l)] for l in labels]
    return {"labels": mapped, "k": len(order), "method": method, "confidence": res["confidence"], "heights": res.get("heights", [])}


MIN_SEPARATION = 1.65  # clusters count as different voices when their centres are this far apart relative to their radii
