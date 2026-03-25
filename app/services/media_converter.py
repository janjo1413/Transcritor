from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from app.runtime_paths import bundled_binary


def convert_to_wav(source_path: Path, output_path: Path) -> Path:
    ffmpeg_path = resolve_binary_path("ffmpeg")
    if not ffmpeg_path:
        raise RuntimeError("FFmpeg nao encontrado. Instale o ffmpeg e tente novamente.")

    command = [
        ffmpeg_path,
        "-y",
        "-i",
        str(source_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "pcm_s16le",
        str(output_path),
    ]

    process = subprocess.run(command, capture_output=True, text=True, check=False)
    if process.returncode != 0:
        error_output = process.stderr.strip() or "Falha desconhecida ao converter o arquivo."
        raise RuntimeError(f"Erro ao converter a midia com FFmpeg: {error_output}")

    return output_path


def get_media_duration(source_path: Path) -> float:
    ffprobe_path = resolve_binary_path("ffprobe")
    if not ffprobe_path:
        raise RuntimeError("FFprobe nao encontrado. Instale o ffmpeg completo e tente novamente.")

    command = [
        ffprobe_path,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(source_path),
    ]
    process = subprocess.run(command, capture_output=True, text=True, check=False)
    if process.returncode != 0 or not process.stdout.strip():
        error_output = process.stderr.strip() or "Nao foi possivel ler a duracao da midia."
        raise RuntimeError(f"Erro ao analisar a midia com FFprobe: {error_output}")

    return float(process.stdout.strip())


def split_audio_chunks(source_path: Path, temp_dir: Path, chunk_seconds: int = 120) -> list[Path]:
    ffmpeg_path = resolve_binary_path("ffmpeg")
    if not ffmpeg_path:
        raise RuntimeError("FFmpeg nao encontrado. Instale o ffmpeg e tente novamente.")

    chunks_dir = temp_dir / "chunks"
    chunks_dir.mkdir(parents=True, exist_ok=True)
    output_pattern = chunks_dir / "chunk_%03d.wav"

    command = [
        ffmpeg_path,
        "-y",
        "-i",
        str(source_path),
        "-f",
        "segment",
        "-segment_time",
        str(chunk_seconds),
        "-c",
        "copy",
        str(output_pattern),
    ]

    process = subprocess.run(command, capture_output=True, text=True, check=False)
    if process.returncode != 0:
        error_output = process.stderr.strip() or "Falha ao dividir o audio em blocos."
        raise RuntimeError(f"Erro ao dividir a midia com FFmpeg: {error_output}")

    chunk_paths = sorted(chunks_dir.glob("chunk_*.wav"))
    if not chunk_paths:
        raise RuntimeError("Nenhum bloco foi criado a partir do audio normalizado.")

    return chunk_paths


def resolve_binary_path(binary_name: str) -> str | None:
    bundled_path = bundled_binary(binary_name)
    if bundled_path:
        return str(bundled_path)

    system_path = shutil.which(binary_name)
    if system_path:
        return system_path

    scripts_dir = Path(sys.executable).resolve().parent
    for candidate_name in (binary_name, f"{binary_name}.exe"):
        local_candidate = scripts_dir / candidate_name
        if local_candidate.exists():
            return str(local_candidate)

    ffmpeg_root = Path.home() / "AppData" / "Local" / "Microsoft" / "WinGet" / "Packages"
    winget_matches = sorted(ffmpeg_root.glob("Gyan.FFmpeg_*\\ffmpeg-*-full_build\\bin"))
    for match in reversed(winget_matches):
        for candidate_name in (binary_name, f"{binary_name}.exe"):
            candidate = match / candidate_name
            if candidate.exists():
                return str(candidate)

    return None
