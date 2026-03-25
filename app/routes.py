import threading
from time import perf_counter
from pathlib import Path
from typing import Callable, Any

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.services.cache_store import (
    get_cached_transcript,
    get_cached_youtube_audio,
    save_cached_transcript,
    save_youtube_audio,
)
from app.services.exporter import export_text_artifact, export_transcription
from app.services.file_manager import (
    INPUT_DIR,
    TEMP_DIR,
    JobPaths,
    create_job_paths,
    remove_directory_if_exists,
)
from app.services.job_store import complete_job, create_job, fail_job, get_job, update_job
from app.services.media_converter import convert_to_wav
from app.services.ollama_prompt import OllamaProviderError, run_prompt_with_ollama
from app.services.performance_store import (
    estimate_ollama_seconds,
    estimate_transcription_seconds,
    record_ollama_run,
    record_transcription_run,
)
from app.services.transcriber import transcribe_file
from app.services.validators import (
    validate_summary_files,
    validate_transcription_source,
    validate_upload,
)
from app.services.youtube_downloader import download_youtube_audio, validate_youtube_url


router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def run_with_heartbeat(
    job_id: str,
    progress: int,
    start_message: str,
    heartbeat_message: str | Callable[[], str],
    action: Callable[[], Any],
    interval_seconds: float = 2.5,
) -> Any:
    update_job(job_id, progress=progress, status="running", message=start_message)

    state: dict[str, object] = {"done": False, "result": None, "error": None}

    def target() -> None:
        try:
            state["result"] = action()
        except Exception as exc:  # pragma: no cover - passthrough helper
            state["error"] = exc
        finally:
            state["done"] = True

    worker = threading.Thread(target=target, daemon=True)
    worker.start()

    heartbeat_count = 0
    while not state["done"]:
        worker.join(timeout=interval_seconds)
        if state["done"]:
            break
        heartbeat_count += 1
        resolved_heartbeat_message = (
            heartbeat_message()
            if callable(heartbeat_message)
            else heartbeat_message
        )
        update_job(
            job_id,
            progress=progress,
            status="running",
            message=f"{resolved_heartbeat_message} Sinal de atividade {heartbeat_count}.",
        )

    if state["error"] is not None:
        raise state["error"]  # type: ignore[misc]
    return state["result"]


@router.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        name="index.html",
        request=request,
        context={"default_output_dir": str(Path("output").resolve())},
    )


def run_transcription_job(
    job_id: str,
    original_filename: str,
    job_paths: JobPaths,
    youtube_url: str = "",
) -> None:
    started_at = perf_counter()
    timings: dict[str, float] = {}
    try:
        transcript = None
        if youtube_url:
            cached_transcript = get_cached_transcript(youtube_url, "auto")
            if cached_transcript:
                timings["cache_hit"] = True
                timings["total_seconds"] = round(perf_counter() - started_at, 2)
                exports = export_transcription(
                    transcript=cached_transcript,
                    original_name=Path(cached_transcript.get("source_name", f"youtube_{job_id}")).stem,
                    destination_dir=job_paths.output_dir,
                )
                complete_job(
                    job_id,
                    {
                        "filename": cached_transcript.get("filename", f"youtube_{job_id}.audio"),
                        "source_type": "youtube",
                        "source_url": youtube_url,
                        "model": cached_transcript["model"],
                        "device": cached_transcript["device"],
                        "text": cached_transcript["text"],
                        "segments": cached_transcript["segments"],
                        "files": exports,
                        "timings": timings,
                        "output_dir": str(job_paths.output_dir.resolve()),
                    },
                )
                return

            cached_audio = get_cached_youtube_audio(youtube_url)
            if cached_audio:
                update_job(job_id, progress=8, status="running", message="Reutilizando audio do YouTube em cache.")
                source_path = job_paths.input_dir / f"youtube_{job_id}{cached_audio.suffix.lower()}"
                source_path.write_bytes(cached_audio.read_bytes())
                timings["download_cache_hit"] = True
            else:
                download_started_at = perf_counter()
                update_job(job_id, progress=8, status="running", message="Baixando audio do YouTube.")
                source_path = download_youtube_audio(youtube_url, job_paths.input_dir, f"youtube_{job_id}")
                timings["download_seconds"] = round(perf_counter() - download_started_at, 2)
                save_youtube_audio(youtube_url, source_path)
        else:
            source_path = job_paths.input_dir / original_filename

        conversion_started_at = perf_counter()
        wav_path = run_with_heartbeat(
            job_id,
            progress=20,
            start_message="Etapa 1/4: convertendo midia com FFmpeg.",
            heartbeat_message="Etapa 1/4: FFmpeg ainda esta convertendo a midia.",
            action=lambda: convert_to_wav(source_path, job_paths.converted_audio_path),
        )
        timings["conversion_seconds"] = round(perf_counter() - conversion_started_at, 2)

        from app.services.media_converter import get_media_duration
        audio_duration = get_media_duration(wav_path)
        predicted_device = transcript["device"] if transcript else None
        estimated_transcription_seconds = None
        if not predicted_device:
            from app.services.transcriber import detect_runtime_device, detect_transcription_mode

            predicted_device = detect_runtime_device()
            predicted_mode = detect_transcription_mode(audio_duration, predicted_device)
            estimated_transcription_seconds = estimate_transcription_seconds(
                predicted_device,
                predicted_mode,
                audio_duration,
            )
            eta_suffix = (
                f" ETA aprox.: {int(estimated_transcription_seconds)}s."
                if estimated_transcription_seconds
                else ""
            )
            update_job(
                job_id,
                progress=38,
                status="running",
                message=(
                    f"Etapa 2/4: audio convertido. Duracao detectada: {int(audio_duration)}s."
                    f"{eta_suffix}"
                ),
            )

        transcription_started_at = perf_counter()
        last_transcription_update = {"message": "Etapa 2/4: aguardando inicio da transcricao."}

        def transcription_progress(progress: int, message: str) -> None:
            composed_message = f"Etapa 2/4: {message}"
            last_transcription_update["message"] = composed_message
            update_job(
                job_id,
                progress=progress,
                status="running",
                message=composed_message,
            )

        transcript = run_with_heartbeat(
            job_id,
            progress=42,
            start_message="Etapa 2/4: preparando transcricao.",
            heartbeat_message=lambda: (
                "Etapa 2/4: transcricao em andamento. "
                f"Ultima subetapa conhecida: {last_transcription_update['message']}"
            ),
            action=lambda: transcribe_file(
                wav_path,
                progress_callback=transcription_progress,
            ),
        )
        timings["transcription_seconds"] = round(perf_counter() - transcription_started_at, 2)
        record_transcription_run(
            device=transcript["device"],
            transcription_mode=transcript.get("transcription_mode", "quality"),
            duration_seconds=audio_duration,
            elapsed_seconds=timings["transcription_seconds"],
        )
        if youtube_url:
            save_cached_transcript(
                youtube_url,
                "auto",
                {
                    **transcript,
                    "filename": source_path.name,
                    "source_name": source_path.stem,
                },
            )
        update_job(job_id, progress=94, status="running", message="Etapa 3/4: gerando arquivos de saida.")
        exports = export_transcription(
            transcript=transcript,
            original_name=source_path.stem,
            destination_dir=job_paths.output_dir,
        )
        timings["total_seconds"] = round(perf_counter() - started_at, 2)

        complete_job(
            job_id,
            {
                "filename": source_path.name,
                "source_type": "youtube" if youtube_url else "upload",
                "source_url": youtube_url or None,
                "model": transcript["model"],
                "transcription_mode": transcript.get("transcription_mode"),
                "device": transcript["device"],
                "parallel_workers": transcript.get("parallel_workers"),
                "chunk_count": transcript.get("chunk_count"),
                "chunk_metrics": transcript.get("chunk_metrics"),
                "text": transcript["text"],
                "segments": transcript["segments"],
                "files": exports,
                "timings": timings,
                "output_dir": str(job_paths.output_dir.resolve()),
            },
        )
    except Exception as exc:
        fail_job(job_id, str(exc))
    finally:
        remove_directory_if_exists(job_paths.input_dir)
        remove_directory_if_exists(job_paths.temp_dir)


def run_summary_job(
    job_id: str,
    source_name: str,
    output_dir: str,
    transcript_text: str,
    summary_prompt: str,
    summary_model: str = "",
    summary_attachment_paths: list[Path] | None = None,
) -> None:
    started_at = perf_counter()
    try:
        update_job(job_id, progress=12, status="running", message="Etapa 1/3: preparando contexto local para o Ollama.")
        estimated_ollama_seconds = estimate_ollama_seconds(
            model=summary_model or "default",
            transcript_chars=len(transcript_text or ""),
            context_strategy="full",
        )
        update_job(
            job_id,
            progress=24,
            status="running",
            message=(
                "Etapa 2/3: processando prompt no Ollama."
                + (
                    f" ETA aprox.: {int(estimated_ollama_seconds)}s."
                    if estimated_ollama_seconds
                    else " Transcricoes longas podem levar mais tempo."
                )
            ),
        )
        response_result = run_with_heartbeat(
            job_id,
            progress=24,
            start_message="Etapa 2/3: enviando contexto para o Ollama.",
            heartbeat_message="Etapa 2/3: Ollama ainda esta processando o prompt.",
            action=lambda: run_prompt_with_ollama(
                transcript_text=transcript_text,
                user_prompt=summary_prompt,
                attachment_paths=summary_attachment_paths or [],
                model=summary_model or None,
            ),
        )

        update_job(job_id, progress=92, status="running", message="Etapa 3/3: salvando resposta do Ollama.")
        response_path = export_text_artifact(
            text=response_result["text"],
            original_name=source_name,
            destination_dir=Path(output_dir),
            suffix="resposta_ollama",
        )
        complete_job(
            job_id,
            {
                "summary": response_result,
                "summary_warning": response_result.get("warnings"),
                "summary_used_fallback": False,
                "files": {"ollama_response": response_path},
                "timings": {
                    "summary_seconds": round(perf_counter() - started_at, 2),
                    "ollama_metrics": response_result.get("metrics"),
                },
                "output_dir": str(Path(output_dir).resolve()),
            },
        )
        record_ollama_run(
            model=response_result.get("model", summary_model or "default"),
            context_strategy=response_result.get("context_strategy", "full"),
            transcript_chars=len(transcript_text or ""),
            elapsed_seconds=round(perf_counter() - started_at, 2),
        )
    except OllamaProviderError as exc:
        fail_job(job_id, str(exc))
    except Exception as exc:
        fail_job(job_id, f"Falha ao executar prompt no Ollama: {exc}")
    finally:
        remove_directory_if_exists(INPUT_DIR / job_id)
        remove_directory_if_exists(TEMP_DIR / job_id)


@router.post("/transcribe")
async def transcribe_media(
    media_file: UploadFile | None = File(None),
    youtube_url: str = Form(""),
    output_dir: str = Form(""),
) -> dict:
    validate_transcription_source(media_file, youtube_url)

    normalized_youtube_url = ""
    if media_file is not None and media_file.filename:
        validate_upload(media_file)
    else:
        try:
            normalized_youtube_url = validate_youtube_url(youtube_url)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    job_paths = create_job_paths(output_dir or None)

    try:
        source_name = media_file.filename if media_file is not None and media_file.filename else normalized_youtube_url
        create_job(job_paths.job_id, source_name)

        source_path = None
        if media_file is not None and media_file.filename:
            source_path = job_paths.save_upload(media_file)

        initial_message = (
            "Upload concluido. Aguardando processamento."
            if source_path
            else "URL recebida. Aguardando inicio do download do YouTube."
        )
        update_job(job_paths.job_id, progress=12, message=initial_message)
        worker = threading.Thread(
            target=run_transcription_job,
            args=(job_paths.job_id, source_path.name if source_path else "", job_paths),
            kwargs={
                "youtube_url": normalized_youtube_url,
            },
            daemon=True,
        )
        worker.start()
        return {
            "job_id": job_paths.job_id,
            "filename": source_name,
            "status": "queued",
        }
    except Exception as exc:
        remove_directory_if_exists(job_paths.input_dir)
        remove_directory_if_exists(job_paths.temp_dir)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/summarize")
async def summarize_transcription(
    source_name: str = Form(...),
    output_dir: str = Form(...),
    transcript_text: str = Form(...),
    summary_prompt: str = Form(...),
    summary_model: str = Form(""),
    summary_files: list[UploadFile] | None = File(None),
) -> dict:
    attachments = validate_summary_files(summary_files)
    job_paths = create_job_paths(output_dir, isolate_output_dir=False)

    try:
        create_job(job_paths.job_id, source_name)
        update_job(job_paths.job_id, progress=5, message="Resumo solicitado. Aguardando processamento.")
        saved_attachment_paths = [
            job_paths.save_attachment(upload, index)
            for index, upload in enumerate(attachments, start=1)
        ]
        worker = threading.Thread(
            target=run_summary_job,
            args=(job_paths.job_id, source_name, output_dir, transcript_text, summary_prompt),
            kwargs={
                "summary_model": summary_model,
                "summary_attachment_paths": saved_attachment_paths,
            },
            daemon=True,
        )
        worker.start()
        return {
            "job_id": job_paths.job_id,
            "filename": source_name,
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
