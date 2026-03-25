from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse


YOUTUBE_HOST_FRAGMENTS = (
    "youtube.com",
    "youtu.be",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
)


def validate_youtube_url(url: str) -> str:
    normalized = (url or "").strip()
    if not normalized:
        raise ValueError("Informe um link do YouTube.")

    parsed = urlparse(normalized)
    hostname = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"} or not any(fragment in hostname for fragment in YOUTUBE_HOST_FRAGMENTS):
        raise ValueError("Informe uma URL valida do YouTube.")

    return normalized


def download_youtube_audio(url: str, destination_dir: Path, output_stem: str) -> Path:
    yt_dlp_path = resolve_yt_dlp_path()
    if not yt_dlp_path:
        raise RuntimeError("yt-dlp nao encontrado. Instale a dependencia e tente novamente.")

    destination_dir.mkdir(parents=True, exist_ok=True)
    output_template = destination_dir / f"{output_stem}.%(ext)s"

    command = [
        yt_dlp_path,
        "--no-playlist",
        "--extract-audio",
        "--audio-format",
        "mp3",
        "--output",
        str(output_template),
        url,
    ]

    process = subprocess.run(command, capture_output=True, text=True, check=False)
    if process.returncode != 0:
        error_output = process.stderr.strip() or process.stdout.strip() or "Falha ao baixar o audio do YouTube."
        raise RuntimeError(f"Erro no download do YouTube: {error_output}")

    matches = sorted(destination_dir.glob(f"{output_stem}.*"))
    for candidate in matches:
        if candidate.is_file():
            return candidate

    raise RuntimeError("O download do YouTube foi concluido, mas nenhum arquivo de audio foi encontrado.")


def resolve_yt_dlp_path() -> str | None:
    system_path = shutil.which("yt-dlp")
    if system_path:
        return system_path

    venv_candidate = Path(sys.executable).resolve().parent / "yt-dlp"
    if venv_candidate.exists():
        return str(venv_candidate)

    project_candidate = Path(__file__).resolve().parents[2] / ".venv" / "bin" / "yt-dlp"
    if project_candidate.exists():
        return str(project_candidate)

    return None
