from __future__ import annotations

import json
from pathlib import Path


def export_transcription(transcript: dict, original_name: str, destination_dir: Path) -> dict:
    destination_dir.mkdir(parents=True, exist_ok=True)
    original_stem = Path(original_name).stem if original_name else "transcricao"
    base_name = f"{sanitize_filename(original_stem)}-transcricao"

    txt_path = destination_dir / f"{base_name}.txt"
    srt_path = destination_dir / f"{base_name}.srt"
    json_path = destination_dir / f"{base_name}.json"

    txt_path.write_text(transcript["text"], encoding="utf-8")
    srt_path.write_text(build_srt(transcript["segments"]), encoding="utf-8")
    json_path.write_text(json.dumps(transcript, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "txt": str(txt_path.resolve()),
        "srt": str(srt_path.resolve()),
        "json": str(json_path.resolve()),
    }


def export_text_artifact(text: str, original_name: str, destination_dir: Path, suffix: str) -> str:
    destination_dir.mkdir(parents=True, exist_ok=True)
    original_stem = Path(original_name).stem if original_name else "transcricao"
    base_name = f"{sanitize_filename(original_stem)}-{suffix}"
    output_path = destination_dir / f"{base_name}.md"
    output_path.write_text(text, encoding="utf-8")
    return str(output_path.resolve())


def build_srt(segments: list[dict]) -> str:
    lines = []
    for index, segment in enumerate(segments, start=1):
        lines.append(str(index))
        lines.append(f"{format_timestamp(segment['start'])} --> {format_timestamp(segment['end'])}")
        lines.append(segment["text"])
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def format_timestamp(seconds: float) -> str:
    total_milliseconds = int(seconds * 1000)
    hours = total_milliseconds // 3_600_000
    minutes = (total_milliseconds % 3_600_000) // 60_000
    secs = (total_milliseconds % 60_000) // 1000
    milliseconds = total_milliseconds % 1000
    return f"{hours:02}:{minutes:02}:{secs:02},{milliseconds:03}"


def sanitize_filename(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value)
    return cleaned.strip("_") or "transcricao"
