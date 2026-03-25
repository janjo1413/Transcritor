from __future__ import annotations

import json
import shutil
from hashlib import sha256
from pathlib import Path

from app.services.file_manager import TRANSCRIPT_CACHE_DIR, YOUTUBE_CACHE_DIR, ensure_runtime_directories


def get_cached_youtube_audio(url: str) -> Path | None:
    cache_dir = _youtube_cache_dir(url)
    matches = sorted(cache_dir.glob("audio.*"))
    return matches[0] if matches else None


def save_youtube_audio(url: str, source_path: Path) -> Path:
    cache_dir = _youtube_cache_dir(url)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cached_path = cache_dir / f"audio{source_path.suffix.lower()}"
    shutil.copy2(source_path, cached_path)

    metadata = {
        "source_url": url,
        "original_name": source_path.name,
    }
    (cache_dir / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return cached_path


def get_cached_transcript(url: str, transcription_mode: str) -> dict | None:
    cache_path = _transcript_cache_path(url, transcription_mode)
    if not cache_path.exists():
        return None
    return json.loads(cache_path.read_text(encoding="utf-8"))


def save_cached_transcript(url: str, transcription_mode: str, transcript: dict) -> None:
    cache_path = _transcript_cache_path(url, transcription_mode)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(transcript, ensure_ascii=False, indent=2), encoding="utf-8")


def _youtube_cache_dir(url: str) -> Path:
    ensure_runtime_directories()
    return YOUTUBE_CACHE_DIR / _hash_value(url)


def _transcript_cache_path(url: str, transcription_mode: str) -> Path:
    ensure_runtime_directories()
    cache_key = _hash_value(f"{url}|{transcription_mode}")
    return TRANSCRIPT_CACHE_DIR / f"{cache_key}.json"


def _hash_value(value: str) -> str:
    return sha256(value.strip().encode("utf-8")).hexdigest()
