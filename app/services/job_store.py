from __future__ import annotations

from copy import deepcopy
from threading import Lock


_JOBS: dict[str, dict] = {}
_LOCK = Lock()


def create_job(job_id: str, filename: str) -> None:
    with _LOCK:
        _JOBS[job_id] = {
            "job_id": job_id,
            "filename": filename,
            "status": "queued",
            "progress": 0,
            "message": "Arquivo recebido.",
            "result": None,
            "error": None,
        }


def update_job(job_id: str, **fields: object) -> None:
    with _LOCK:
        if job_id not in _JOBS:
            return
        _JOBS[job_id].update(fields)


def complete_job(job_id: str, result: dict) -> None:
    update_job(
        job_id,
        status="completed",
        progress=100,
        message="Transcricao concluida.",
        result=result,
        error=None,
    )


def fail_job(job_id: str, error_message: str) -> None:
    update_job(
        job_id,
        status="failed",
        message=error_message,
        error=error_message,
    )


def get_job(job_id: str) -> dict | None:
    with _LOCK:
        job = _JOBS.get(job_id)
        return deepcopy(job) if job else None
