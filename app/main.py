from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.routes import router
from app.runtime_paths import static_dir
from app.services.file_manager import ensure_runtime_directories


ensure_runtime_directories()

app = FastAPI(
    title="Transcritor Local",
    description="Aplicacao local para transcrever audio e video em texto.",
    version="0.1.0",
)

app.mount("/static", StaticFiles(directory=str(static_dir())), name="static")
app.include_router(router)
