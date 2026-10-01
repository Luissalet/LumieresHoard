"""Speech to text with word timestamps (faster-whisper, local), filler words and repeated words."""

from __future__ import annotations

import logging
import re
import unicodedata
from pathlib import Path
from typing import Any, Callable, Optional

from ..errors import TranscriberUnavailable

log = logging.getLogger("lumiere.speech")

FILLERS = {
    "es": ["eh", "ehh", "em", "emm", "mm", "mmm", "este", "esto", "o sea", "pues", "bueno", "vale", "en plan", "tipo", "digamos",
           "a ver", "osea", "ah", "uh", "um", "ehm"],
    "en": ["um", "uh", "uhm", "umm", "er", "erm", "ah", "hmm", "mm", "like", "you know", "i mean", "sort of", "kind of", "basically",
           "actually", "literally", "so yeah"],
}
# words that only count as fillers when they stand alone between pauses (they are also real words)
SOFT = {"este", "esto", "pues", "bueno", "vale", "tipo", "like", "so", "actually", "basically", "literally", "en plan", "digamos",
        "a ver", "sort of", "kind of", "i mean", "you know", "so yeah"}


def norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^\w\s']", "", text).strip()


def engine_status() -> dict[str, Any]:
    try:
        import faster_whisper  # type: ignore  # noqa: F401
    except Exception as error:  # noqa: BLE001
        return {"available": False, "engine": None, "reason": f"faster-whisper is not installed ({type(error).__name__})."}
    cuda = 0
    try:
        import ctranslate2  # type: ignore

        cuda = ctranslate2.get_cuda_device_count()
    except Exception:  # noqa: BLE001
        cuda = 0
    return {"available": True, "engine": "faster-whisper", "cuda_devices": cuda}


def transcribe(path: Path, *, model: str = "", language: str = "", device: str = "auto", gpu: Optional[int] = None,
               progress: Optional[Callable[[float, str], None]] = None, duration_ms: int = 0, cancelled: Callable[[], bool] = lambda: False,
               initial_prompt: str = "") -> dict[str, Any]:
    """Words [{id, t0, t1, text, p}], segments [{t0, t1, text}] and the language. ``path`` should be a 16 kHz mono WAV or any
    file ffmpeg reads."""
    status = engine_status()
    if not status["available"]:
        raise TranscriberUnavailable(status["reason"] + " Install it with: pip install faster-whisper")
    from faster_whisper import WhisperModel  # type: ignore

    use_cuda = device == "cuda" or (device == "auto" and status.get("cuda_devices", 0) > 0)
    name = model or ("large-v3-turbo" if use_cuda else "small")
    attempts = [("cuda", "float16"), ("cpu", "int8")] if use_cuda else [("cpu", "int8")]
    last: Optional[Exception] = None
    wm = None
    used = ("cpu", "int8")
    for dev, ct in attempts:
        try:
            kwargs: dict[str, Any] = {"device": dev, "compute_type": ct}
            if dev == "cuda" and gpu is not None:
                kwargs["device_index"] = gpu
            wm = WhisperModel(name, **kwargs)
            used = (dev, ct)
            break
        except Exception as error:  # noqa: BLE001
            last = error
            log.warning("whisper %s on %s failed: %s", name, dev, error)
    if wm is None:
        raise TranscriberUnavailable(f"Could not load the speech model {name}: {last}")
    if progress:
        progress(0.02, f"{name} on {used[0]}")
    segments, info = wm.transcribe(_load_audio(path), language=language or None, word_timestamps=True, vad_filter=True,
                                   vad_parameters={"min_silence_duration_ms": 300}, beam_size=5, condition_on_previous_text=False,
                                   initial_prompt=initial_prompt or None)
    words: list[dict[str, Any]] = []
    segs: list[dict[str, Any]] = []
    n = 0
    for seg in segments:
        if cancelled():
            break
        segs.append({"t0": int(round(seg.start * 1000)), "t1": int(round(seg.end * 1000)), "text": seg.text.strip()})
        for w in seg.words or []:
            text = w.word.strip()
            if not text:
                continue
            n += 1
            words.append({"id": f"w{n}", "t0": int(round(w.start * 1000)), "t1": int(round(max(w.end, w.start + 0.02) * 1000)), "text": text,
                          "p": round(float(w.probability or 0), 3)})
        if progress and duration_ms:
            progress(min(0.98, seg.end * 1000 / duration_ms), f"{len(words)} words")
    return {"language": info.language, "language_p": round(float(info.language_probability or 0), 3), "model": name, "device": used[0],
            "words": words, "segments": segs}


def _load_audio(path: Path):
    """16 kHz mono float32 samples. A 16-bit mono WAV at 16 kHz (what the app prepares) is read directly, so the
    transcriber never decodes media itself (its decoder depends on a media library whose API changes between versions)."""
    import wave

    import numpy as np

    with wave.open(str(path), "rb") as w:
        if w.getframerate() != 16000 or w.getnchannels() != 1 or w.getsampwidth() != 2:
            raise TranscriberUnavailable("The speech audio must be 16 kHz mono 16-bit WAV.")
        data = w.readframes(w.getnframes())
    return np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0


def find_fillers(words: list[dict[str, Any]], language: str = "es", extra: Optional[list[str]] = None, repeats: bool = True,
                 strict: bool = False) -> list[dict[str, Any]]:
    """Word runs to remove: [{ids, t0, t1, text, reason}]. Soft fillers ('bueno', 'like') only count when isolated by pauses
    unless strict=True; immediate repeats ('que que') are reported too."""
    vocab = [norm(x) for x in (FILLERS.get(language[:2], []) + FILLERS["en"] * (language[:2] != "en") + (extra or []))]
    multi = sorted({v for v in vocab if " " in v}, key=lambda v: -len(v.split()))
    single = {v for v in vocab if " " not in v}
    soft = {norm(x) for x in SOFT}
    out: list[dict[str, Any]] = []
    i = 0
    n = len(words)
    while i < n:
        matched = 0
        for phrase in multi:
            parts = phrase.split()
            if i + len(parts) <= n and [norm(words[i + k]["text"]) for k in range(len(parts))] == parts:
                matched = len(parts)
                text = phrase
                break
        if not matched and norm(words[i]["text"]) in single:
            matched, text = 1, norm(words[i]["text"])
        if matched:
            run = words[i: i + matched]
            before = words[i - 1]["t1"] if i > 0 else -10_000
            after = words[i + matched]["t0"] if i + matched < n else 10 ** 9
            isolated = run[0]["t0"] - before >= 250 or after - run[-1]["t1"] >= 250
            if text not in soft or strict or isolated:
                out.append({"ids": [w["id"] for w in run], "t0": run[0]["t0"], "t1": run[-1]["t1"], "text": " ".join(w["text"] for w in run),
                            "reason": "filler"})
            i += matched
            continue
        if repeats and i + 1 < n and norm(words[i]["text"]) and norm(words[i]["text"]) == norm(words[i + 1]["text"]) \
                and words[i + 1]["t0"] - words[i]["t1"] < 600 and len(norm(words[i]["text"])) > 1:
            out.append({"ids": [words[i]["id"]], "t0": words[i]["t0"], "t1": words[i]["t1"], "text": words[i]["text"], "reason": "repeat"})
        i += 1
    return out


def cut_ranges_for_words(words: list[dict[str, Any]], ids: set[str]) -> list[list[int]]:
    """Source ranges that remove the given words with half of the pauses around them, so the words that stay keep a
    natural rhythm (consecutive words become one range)."""
    out: list[list[int]] = []
    n = len(words)
    i = 0
    while i < n:
        if words[i]["id"] not in ids:
            i += 1
            continue
        j = i
        while j + 1 < n and words[j + 1]["id"] in ids:
            j += 1
        prev_end = words[i - 1]["t1"] if i > 0 else None
        next_start = words[j + 1]["t0"] if j + 1 < n else None
        a = words[i]["t0"] if prev_end is None else max(prev_end, words[i]["t0"] - min(120, (words[i]["t0"] - prev_end) // 2))
        b = words[j]["t1"] if next_start is None else min(next_start, words[j]["t1"] + max(0, (next_start - words[j]["t1"]) // 2))
        if prev_end is not None and next_start is not None:
            # also close up the gap so the cut does not leave two pauses back to back
            a = max(prev_end + 40, min(a, words[i]["t0"]))
        if b > a:
            out.append([int(a), int(b)])
        i = j + 1
    return out
