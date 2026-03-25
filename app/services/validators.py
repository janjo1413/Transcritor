from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException, UploadFile


ALLOWED_EXTENSIONS = {
    ".mp3",
    ".wav",
    ".m4a",
    ".aac",
    ".flac",
    ".ogg",
    ".wma",
    ".webm",
    ".mp4",
    ".mkv",
    ".mov",
    ".avi",
    ".wmv",
    ".mpeg",
    ".mpg",
}
MAX_FILE_SIZE = 1024 * 1024 * 1024


def validate_upload(upload: UploadFile) -> None:
    if not upload.filename:
        raise HTTPException(status_code=400, detail="Nenhum arquivo foi enviado.")

    suffix = Path(upload.filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="Formato nao suportado. Envie um arquivo de audio ou video compativel com FFmpeg.",
        )

    upload.file.seek(0, 2)
    size = upload.file.tell()
    upload.file.seek(0)
    if size > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="Arquivo muito grande. Limite atual: 1 GB.")


def validate_transcription_source(media_file: UploadFile | None, youtube_url: str) -> None:
    has_file = media_file is not None and bool(media_file.filename)
    has_url = bool((youtube_url or "").strip())

    if has_file == has_url:
        raise HTTPException(
            status_code=400,
            detail="Envie um arquivo ou um link do YouTube. Escolha apenas uma fonte por vez.",
        )
