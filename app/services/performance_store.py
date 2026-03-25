from __future__ import annotations

import json
from pathlib import Path
from threading import Lock

from app.services.file_manager import CACHE_DIR, ensure_runtime_directories


PERFORMANCE_HISTORY_PATH = CACHE_DIR / "performance_history.json"
_LOCK = Lock()
MAX_SAMPLES = 20


def estimate_transcription_seconds(device: str, transcription_mode: str, duration_seconds: float) -> float | None:
    history = _load_history()
    key = f"{device}:{transcription_mode}"
    samples = history.get("transcription", {}).get(key, [])
    if not samples or duration_seconds <= 0:
        return None

    avg_ratio = sum(samples) / len(samples)
    return round(avg_ratio * duration_seconds, 1)


def record_transcription_run(
    device: str,
    transcription_mode: str,
    duration_seconds: float,
    elapsed_seconds: float,
) -> None:
    if duration_seconds <= 0 or elapsed_seconds <= 0:
        return

    ratio = elapsed_seconds / duration_seconds
    with _LOCK:
        history = _load_history()
        key = f"{device}:{transcription_mode}"
        samples = history.setdefault("transcription", {}).setdefault(key, [])
        samples.append(ratio)
        history["transcription"][key] = samples[-MAX_SAMPLES:]
        _write_history(history)


def _load_history() -> dict:
    ensure_runtime_directories()
    if not PERFORMANCE_HISTORY_PATH.exists():
        return {}
    try:
        return json.loads(PERFORMANCE_HISTORY_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_history(history: dict) -> None:
    ensure_runtime_directories()
    PERFORMANCE_HISTORY_PATH.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
