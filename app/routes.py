import threading
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.services.exporter import export_transcription
from app.services.file_manager import JobPaths, create_job_paths, remove_directory_if_exists
from app.services.job_store import complete_job, create_job, fail_job, get_job, update_job
from app.services.media_converter import convert_to_wav
from app.services.transcriber import transcribe_file
from app.services.validators import validate_upload


router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        name="index.html",
        request=request,
        context={"default_output_dir": str(Path("output").resolve())},
    )


def run_transcription_job(job_id: str, original_filename: str, job_paths: JobPaths) -> None:
    try:
        source_path = job_paths.input_dir / original_filename
        update_job(job_id, progress=20, status="running", message="Convertendo midia com FFmpeg.")
        wav_path = convert_to_wav(source_path, job_paths.converted_audio_path)
        transcript = transcribe_file(
            wav_path,
            progress_callback=lambda progress, message: update_job(
                job_id,
                progress=progress,
                status="running",
                message=message,
            ),
        )
        update_job(job_id, progress=94, status="running", message="Gerando arquivos de saida.")
        exports = export_transcription(
            transcript=transcript,
            original_name=source_path.stem,
            destination_dir=job_paths.output_dir,
        )
        complete_job(
            job_id,
            {
                "filename": original_filename,
                "model": transcript["model"],
                "device": transcript["device"],
                "text": transcript["text"],
                "segments": transcript["segments"],
                "files": exports,
                "output_dir": str(job_paths.output_dir.resolve()),
            },
        )
    except Exception as exc:
        fail_job(job_id, str(exc))
    finally:
        remove_directory_if_exists(job_paths.input_dir)
        remove_directory_if_exists(job_paths.temp_dir)


@router.post("/transcribe")
async def transcribe_media(
    media_file: UploadFile = File(...),
    output_dir: str = Form(""),
) -> dict:
    validate_upload(media_file)
    job_paths = create_job_paths(output_dir or None)

    try:
        source_path = job_paths.save_upload(media_file)
        create_job(job_paths.job_id, media_file.filename)
        update_job(job_paths.job_id, progress=12, message="Upload concluido. Aguardando processamento.")
        worker = threading.Thread(
            target=run_transcription_job,
            args=(job_paths.job_id, source_path.name, job_paths),
            daemon=True,
        )
        worker.start()
        return {
            "job_id": job_paths.job_id,
            "filename": media_file.filename,
            "status": "queued",
        }
    except Exception as exc:
        remove_directory_if_exists(job_paths.input_dir)
        remove_directory_if_exists(job_paths.temp_dir)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/jobs/{job_id}")
async def get_transcription_job(job_id: str) -> dict:
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job nao encontrado.")
    return job
