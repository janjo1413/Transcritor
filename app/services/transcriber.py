from __future__ import annotations

import os
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable

import ctranslate2
from faster_whisper import WhisperModel

from app.services.media_converter import get_media_duration, split_audio_chunks


SUPPORTED_MODELS = ("tiny", "base", "small", "medium", "large-v3")
LONG_AUDIO_THRESHOLD_SECONDS = 10 * 60
CHUNK_SECONDS = 120
MAX_PARALLEL_WORKERS = 4
THREAD_STATE = threading.local()
ProgressCallback = Callable[[int, str], None]


def available_models() -> tuple[str, ...]:
    return SUPPORTED_MODELS


def build_model(model_size: str) -> WhisperModel:
    if model_size not in SUPPORTED_MODELS:
        raise ValueError(f"Modelo invalido: {model_size}")

    return WhisperModel(model_size, device="auto", compute_type="default")


def get_thread_model(model_size: str) -> WhisperModel:
    cached_models = getattr(THREAD_STATE, "models", None)
    if cached_models is None:
        cached_models = {}
        THREAD_STATE.models = cached_models

    if model_size not in cached_models:
        cached_models[model_size] = build_model(model_size)

    return cached_models[model_size]


def detect_runtime_device() -> str:
    try:
        if ctranslate2.get_cuda_device_count() > 0:
            return "gpu"
    except Exception:
        pass
    return "cpu"


def choose_model_for_duration(duration_seconds: float, device: str) -> str:
    if device == "gpu":
        return "medium" if duration_seconds <= 2 * 60 * 60 else "small"
    if duration_seconds <= 20 * 60:
        return "small"
    return "base"


def transcribe_single_file(audio_path: Path, model_size: str = "small", start_offset: float = 0.0) -> dict:
    model = get_thread_model(model_size)
    segments, info = model.transcribe(
        str(audio_path),
        beam_size=5,
        vad_filter=True,
    )

    parsed_segments = []
    full_text_parts = []
    for segment in segments:
        text = segment.text.strip()
        parsed_segments.append(
            {
                "start": round(start_offset + segment.start, 2),
                "end": round(start_offset + segment.end, 2),
                "text": text,
            }
        )
        if text:
            full_text_parts.append(text)

    return {
        "device": detect_runtime_device(),
        "language": info.language,
        "duration": round(info.duration, 2) if info.duration else None,
        "segments": parsed_segments,
        "text": " ".join(full_text_parts).strip(),
    }


def transcribe_file(audio_path: Path, progress_callback: ProgressCallback | None = None) -> dict:
    duration = get_media_duration(audio_path)
    device = detect_runtime_device()
    model_size = choose_model_for_duration(duration, device)

    if progress_callback:
        progress_callback(38, "Audio convertido. Preparando transcricao automatica.")

    if duration <= LONG_AUDIO_THRESHOLD_SECONDS:
        if progress_callback:
            progress_callback(55, f"Transcrevendo arquivo completo com modelo {model_size}.")

        result = transcribe_single_file(audio_path, model_size=model_size)
        result["model"] = model_size
        return result

    chunk_paths = split_audio_chunks(audio_path, audio_path.parent, chunk_seconds=CHUNK_SECONDS)
    if progress_callback:
        progress_callback(
            52,
            f"Arquivo longo detectado. Dividindo em {len(chunk_paths)} blocos para transcricao paralela.",
        )

    worker_cap = 2 if device == "gpu" else MAX_PARALLEL_WORKERS
    workers = max(1, min(len(chunk_paths), worker_cap, os.cpu_count() or 1))

    partial_results = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [
            executor.submit(
                transcribe_single_file,
                chunk_path,
                model_size,
                index * CHUNK_SECONDS,
            )
            for index, chunk_path in enumerate(chunk_paths)
        ]
        for index, future in enumerate(futures, start=1):
            partial_results.append(future.result())
            if progress_callback:
                chunk_progress = 55 + int((index / len(chunk_paths)) * 35)
                progress_callback(
                    chunk_progress,
                    f"Transcrevendo blocos em paralelo: {index}/{len(chunk_paths)} concluidos com modelo {model_size}.",
                )

    merged_segments = []
    merged_text_parts = []
    language = partial_results[0]["language"] if partial_results else None
    for result in partial_results:
        merged_segments.extend(result["segments"])
        if result["text"]:
            merged_text_parts.append(result["text"])

    return {
        "device": device,
        "language": language,
        "model": model_size,
        "duration": round(duration, 2),
        "segments": merged_segments,
        "text": " ".join(merged_text_parts).strip(),
    }
