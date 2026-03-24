from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile


BASE_DIR = Path(__file__).resolve().parents[2]
INPUT_DIR = BASE_DIR / "input"
TEMP_DIR = BASE_DIR / "temp"
OUTPUT_DIR = BASE_DIR / "output"


def ensure_runtime_directories() -> None:
    for directory in (INPUT_DIR, TEMP_DIR, OUTPUT_DIR):
        directory.mkdir(parents=True, exist_ok=True)


@dataclass(slots=True)
class JobPaths:
    job_id: str
    input_dir: Path
    temp_dir: Path
    output_dir: Path
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


def create_job_paths(requested_output_dir: str | None = None) -> JobPaths:
    ensure_runtime_directories()
    job_id = uuid4().hex[:12]
    input_dir = INPUT_DIR / job_id
    temp_dir = TEMP_DIR / job_id
    output_root = Path(requested_output_dir).expanduser() if requested_output_dir else OUTPUT_DIR
    output_dir = output_root / job_id

    for directory in (input_dir, temp_dir, output_dir):
        directory.mkdir(parents=True, exist_ok=True)

    upload_path = input_dir / f"source_{job_id}"
    converted_audio_path = temp_dir / f"normalized_{job_id}.wav"

    return JobPaths(
        job_id=job_id,
        input_dir=input_dir,
        temp_dir=temp_dir,
        output_dir=output_dir,
        upload_path=upload_path,
        converted_audio_path=converted_audio_path,
    )


def remove_file_if_exists(path: Path) -> None:
    if path.exists():
        path.unlink()


def remove_directory_if_exists(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
