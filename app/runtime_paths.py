from __future__ import annotations

import sys
from pathlib import Path


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def project_root() -> Path:
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def resource_root() -> Path:
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        return Path(bundle_root)
    return project_root()


def app_dir() -> Path:
    return resource_root() / "app"


def static_dir() -> Path:
    return app_dir() / "static"


def templates_dir() -> Path:
    return app_dir() / "templates"


def bundled_binary(binary_name: str) -> Path | None:
    base_dir = project_root()
    for candidate_name in (binary_name, f"{binary_name}.exe"):
        candidate = base_dir / candidate_name
        if candidate.exists():
            return candidate
    return None
