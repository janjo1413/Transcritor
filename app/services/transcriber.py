from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Lock
from time import perf_counter
from typing import Callable

import ctranslate2
from faster_whisper import WhisperModel

from app.services.media_converter import get_media_duration, split_audio_chunks


SUPPORTED_MODELS = ("tiny", "base", "small", "medium", "large-v3")
TRANSCRIPTION_MODES = ("fast", "quality")
LONG_AUDIO_THRESHOLD_SECONDS = int(os.getenv("TRANSCRIBE_LONG_AUDIO_SECONDS", str(10 * 60)))
GPU_LONG_AUDIO_THRESHOLD_SECONDS = int(os.getenv("TRANSCRIBE_GPU_LONG_AUDIO_SECONDS", str(20 * 60)))
CHUNK_SECONDS = int(os.getenv("TRANSCRIBE_CHUNK_SECONDS", "180"))
MAX_PARALLEL_WORKERS = int(
    os.getenv("TRANSCRIBE_MAX_WORKERS", str(min(8, os.cpu_count() or 1)))
)
DEFAULT_CPU_MODEL = os.getenv("WHISPER_DEFAULT_CPU_MODEL", "base")
DEFAULT_GPU_MODEL = os.getenv("WHISPER_DEFAULT_GPU_MODEL", "base")
FAST_CPU_MODEL = os.getenv("WHISPER_FAST_CPU_MODEL", "tiny")
FAST_GPU_MODEL = os.getenv("WHISPER_FAST_GPU_MODEL", "base")
MODEL_CACHE: dict[tuple[str, str, int], WhisperModel] = {}
MODEL_CACHE_LOCK = Lock()
ProgressCallback = Callable[[int, str], None]


def available_models() -> tuple[str, ...]:
    return SUPPORTED_MODELS


def build_model(model_size: str, device: str, workers: int) -> WhisperModel:
    if model_size not in SUPPORTED_MODELS:
        raise ValueError(f"Modelo invalido: {model_size}")

    compute_type = "float16" if device == "gpu" else os.getenv("WHISPER_CPU_COMPUTE_TYPE", "int8")
    total_cpus = os.cpu_count() or 1
    cpu_threads = 1 if device == "gpu" else max(1, total_cpus // max(1, workers))

    try:
        return WhisperModel(
            model_size,
            device=device,
            compute_type=compute_type,
            cpu_threads=cpu_threads,
            num_workers=1,
        )
    except Exception as exc:
        if device != "gpu" or "unsupported device gpu" not in str(exc).lower():
            raise

    fallback_compute_type = os.getenv("WHISPER_CPU_COMPUTE_TYPE", "int8")
    total_cpus = os.cpu_count() or 1
    fallback_threads = max(1, total_cpus // max(1, workers))
    return WhisperModel(
        model_size,
        device="cpu",
        compute_type=fallback_compute_type,
        cpu_threads=fallback_threads,
        num_workers=1,
    )


def get_thread_model(model_size: str, device: str, workers: int) -> WhisperModel:
    cache_key = (model_size, device, workers)
    with MODEL_CACHE_LOCK:
        if cache_key not in MODEL_CACHE:
            MODEL_CACHE[cache_key] = build_model(model_size, device, workers)
        return MODEL_CACHE[cache_key]


def detect_runtime_device() -> str:
    forced_device = os.getenv("WHISPER_DEVICE", "").strip().lower()
    if forced_device in {"cpu", "gpu"}:
        return forced_device

    try:
        if ctranslate2.get_cuda_device_count() > 0:
            return "gpu"
    except Exception:
        pass
    return "cpu"


def detect_transcription_mode(duration_seconds: float, device: str) -> str:
    if duration_seconds >= 45 * 60:
        return "fast"
    if device == "cpu" and duration_seconds >= 20 * 60:
        return "fast"
    return "quality"


def should_chunk_audio(duration_seconds: float, device: str) -> bool:
    threshold_seconds = GPU_LONG_AUDIO_THRESHOLD_SECONDS if device == "gpu" else LONG_AUDIO_THRESHOLD_SECONDS
    return duration_seconds > threshold_seconds


def resolve_model_choice(duration_seconds: float, device: str, detected_mode: str) -> str:
    if detected_mode not in TRANSCRIPTION_MODES:
        raise ValueError(f"Modo de transcricao invalido: {detected_mode}")

    if detected_mode == "fast":
        return FAST_GPU_MODEL if device == "gpu" else FAST_CPU_MODEL
    return DEFAULT_GPU_MODEL if device == "gpu" else DEFAULT_CPU_MODEL


def transcribe_single_file(
    audio_path: Path,
    model_size: str = "small",
    start_offset: float = 0.0,
    device: str = "cpu",
    workers: int = 1,
    beam_size: int = 5,
) -> dict:
    effective_device = device
    try:
        model = get_thread_model(model_size, device, workers)
    except Exception as exc:
        if device != "gpu" or "unsupported device gpu" not in str(exc).lower():
            raise
        effective_device = "cpu"
        model = get_thread_model(model_size, effective_device, workers)

    segments, info = model.transcribe(
        str(audio_path),
        beam_size=beam_size,
        vad_filter=True,
        condition_on_previous_text=False,
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
        "device": effective_device,
        "language": info.language,
        "duration": round(info.duration, 2) if info.duration else None,
        "segments": parsed_segments,
        "text": " ".join(full_text_parts).strip(),
    }


def transcribe_chunk(
    chunk_path: Path,
    model_size: str,
    chunk_index: int,
    device: str,
    workers: int,
    beam_size: int,
) -> dict:
    started_at = perf_counter()
    result = transcribe_single_file(
        chunk_path,
        model_size=model_size,
        start_offset=chunk_index * CHUNK_SECONDS,
        device=device,
        workers=workers,
        beam_size=beam_size,
    )
    result["chunk_index"] = chunk_index
    result["chunk_name"] = chunk_path.name
    result["elapsed_seconds"] = round(perf_counter() - started_at, 2)
    return result


def transcribe_file(
    audio_path: Path,
    progress_callback: ProgressCallback | None = None,
) -> dict:
    duration = get_media_duration(audio_path)
    device = detect_runtime_device()
    transcription_mode = detect_transcription_mode(duration, device)
    model_size = resolve_model_choice(duration, device, transcription_mode)
    beam_size = 1

    if progress_callback:
        progress_callback(38, f"Audio convertido. Preparando transcricao no modo {transcription_mode}.")

    if not should_chunk_audio(duration, device):
        if progress_callback:
            progress_callback(55, f"Transcrevendo arquivo completo com modelo {model_size}.")

        result = transcribe_single_file(
            audio_path,
            model_size=model_size,
            device=device,
            workers=1,
            beam_size=beam_size,
        )
        result["model"] = model_size
        result["transcription_mode"] = transcription_mode
        return result

    chunk_paths = split_audio_chunks(audio_path, audio_path.parent, chunk_seconds=CHUNK_SECONDS)
    if progress_callback:
        progress_callback(
            52,
            (
                f"Arquivo longo detectado. Dividindo em {len(chunk_paths)} blocos para transcricao "
                f"{'paralela na GPU' if device == 'gpu' else 'paralela'}."
            ),
        )

    worker_cap = 2 if device == "gpu" else MAX_PARALLEL_WORKERS
    workers = max(1, min(len(chunk_paths), worker_cap, os.cpu_count() or 1))

    partial_results = []
    chunk_metrics = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(transcribe_chunk, chunk_path, model_size, index, device, workers, beam_size): index
            for index, chunk_path in enumerate(chunk_paths)
        }
        completed = 0
        for future in as_completed(futures):
            result = future.result()
            partial_results.append(result)
            chunk_metrics.append(
                {
                    "chunk_index": result["chunk_index"],
                    "chunk_name": result["chunk_name"],
                    "elapsed_seconds": result["elapsed_seconds"],
                }
            )
            completed += 1
            if progress_callback:
                chunk_progress = 55 + int((completed / len(chunk_paths)) * 35)
                progress_callback(
                    chunk_progress,
                    (
                        f"Transcrevendo blocos em paralelo: {completed}/{len(chunk_paths)} concluidos "
                        f"com modelo {model_size} em {workers} workers."
                    ),
                )

    partial_results.sort(key=lambda item: item["chunk_index"])
    chunk_metrics.sort(key=lambda item: item["chunk_index"])

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
        "transcription_mode": transcription_mode,
        "duration": round(duration, 2),
        "parallel_workers": workers,
        "chunk_count": len(chunk_paths),
        "chunk_metrics": chunk_metrics,
        "segments": merged_segments,
        "text": " ".join(merged_text_parts).strip(),
    }
