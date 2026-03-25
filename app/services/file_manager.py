from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile
from app.runtime_paths import project_root


BASE_DIR = project_root()
INPUT_DIR = BASE_DIR / "input"
TEMP_DIR = BASE_DIR / "temp"
OUTPUT_DIR = BASE_DIR / "output"
CACHE_DIR = BASE_DIR / "cache"
YOUTUBE_CACHE_DIR = CACHE_DIR / "youtube"
TRANSCRIPT_CACHE_DIR = CACHE_DIR / "transcripts"


def ensure_runtime_directories() -> None:
    for directory in (INPUT_DIR, TEMP_DIR, OUTPUT_DIR, CACHE_DIR, YOUTUBE_CACHE_DIR, TRANSCRIPT_CACHE_DIR):
        directory.mkdir(parents=True, exist_ok=True)


@dataclass(slots=True)
class JobPaths:
    job_id: str
    input_dir: Path
    temp_dir: Path
    output_dir: Path
    attachments_dir: Path
    upload_path: Path
    converted_audio_path: Path

    def save_upload(self, upload: UploadFile) -> Path:
        suffix = Path(upload.filename or "").suffix.lower()
        final_path = self.upload_path.with_suffix(suffix)
        with final_path.open("wb") as buffer:
            while chunk := upload.file.read(1024 * 1024):
                buffer.write(chunk)
        self.upload_path = final_path
        return final_path

    def save_attachment(self, upload: UploadFile, index: int) -> Path:
        filename = Path(upload.filename or f"attachment_{index}").name
        destination = self.attachments_dir / f"{index:02d}_{filename}"
        with destination.open("wb") as buffer:
            while chunk := upload.file.read(1024 * 1024):
                buffer.write(chunk)
        upload.file.seek(0)
        return destination


def create_job_paths(requested_output_dir: str | None = None, isolate_output_dir: bool = True) -> JobPaths:
    ensure_runtime_directories()
    job_id = uuid4().hex[:12]
    input_dir = INPUT_DIR / job_id
    temp_dir = TEMP_DIR / job_id
    attachments_dir = input_dir / "attachments"
    output_root = Path(requested_output_dir).expanduser() if requested_output_dir else OUTPUT_DIR
    output_dir = output_root / job_id if isolate_output_dir else output_root

    for directory in (input_dir, temp_dir, output_dir, attachments_dir):
        directory.mkdir(parents=True, exist_ok=True)

    upload_path = input_dir / f"source_{job_id}"
    converted_audio_path = temp_dir / f"normalized_{job_id}.wav"

    return JobPaths(
        job_id=job_id,
        input_dir=input_dir,
        temp_dir=temp_dir,
        output_dir=output_dir,
        attachments_dir=attachments_dir,
        upload_path=upload_path,
        converted_audio_path=converted_audio_path,
    )


def remove_file_if_exists(path: Path) -> None:
    if path.exists():
        path.unlink()


def remove_directory_if_exists(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
