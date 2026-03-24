from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def convert_to_wav(source_path: Path, output_path: Path) -> Path:
    ffmpeg_path = shutil.which("ffmpeg")
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
    ffprobe_path = shutil.which("ffprobe")
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
    ffmpeg_path = shutil.which("ffmpeg")
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
