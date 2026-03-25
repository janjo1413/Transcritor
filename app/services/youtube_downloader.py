from __future__ import annotations

import shutil
import sys
from pathlib import Path
from urllib.parse import urlparse

from app.services.media_converter import resolve_binary_path
from yt_dlp import DownloadError, YoutubeDL


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

    ffmpeg_path = resolve_binary_path("ffmpeg")
    if not ffmpeg_path:
        raise RuntimeError("FFmpeg nao encontrado. Instale o ffmpeg e tente novamente.")

    destination_dir.mkdir(parents=True, exist_ok=True)
    output_template = destination_dir / f"{output_stem}.%(ext)s"

    options = {
        "paths": {"home": str(destination_dir)},
        "outtmpl": {"default": str(output_template)},
        "noplaylist": True,
        "format": "bestaudio/best",
        "quiet": True,
        "no_warnings": False,
        "ffmpeg_location": str(Path(ffmpeg_path).parent),
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ],
    }

    try:
        with YoutubeDL(options) as downloader:
            downloader.download([url])
    except DownloadError as exc:
        detail = str(exc).strip() or "Falha ao baixar o audio do YouTube."
        raise RuntimeError(f"Erro no download do YouTube: {detail}") from exc
    except Exception as exc:
        raise RuntimeError(f"Erro ao executar yt-dlp: {exc}") from exc

    matches = sorted(destination_dir.glob(f"{output_stem}.*"))
    for candidate in matches:
        if candidate.is_file():
            return candidate

    raise RuntimeError("O download do YouTube foi concluido, mas nenhum arquivo de audio foi encontrado.")


def resolve_yt_dlp_path() -> str | None:
    system_path = shutil.which("yt-dlp")
    if system_path:
        return system_path

    scripts_dir = Path(sys.executable).resolve().parent
    for candidate_name in ("yt-dlp", "yt-dlp.exe"):
        venv_candidate = scripts_dir / candidate_name
        if venv_candidate.exists():
            return str(venv_candidate)

    project_root = Path(__file__).resolve().parents[2]
    for relative_path in (
        Path(".venv") / "Scripts" / "yt-dlp.exe",
        Path(".venv") / "Scripts" / "yt-dlp",
        Path(".venv") / "bin" / "yt-dlp",
    ):
        project_candidate = project_root / relative_path
        if project_candidate.exists():
            return str(project_candidate)

    return None
