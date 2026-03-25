from __future__ import annotations

import base64
import mimetypes
import os
from pathlib import Path
import re

import requests


DEFAULT_OLLAMA_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
DEFAULT_OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
FAST_OLLAMA_MODEL = os.getenv("OLLAMA_FAST_MODEL", "llama3.2:1b")
COMPLEX_PROMPT_THRESHOLD = 280
COMPLEX_CONTEXT_THRESHOLD = 12_000
DEFAULT_TIMEOUT_SECONDS = 300
TEXTUAL_MIME_PREFIXES = ("text/",)
TEXTUAL_EXTENSIONS = {
    ".txt",
    ".md",
    ".csv",
    ".json",
    ".yml",
    ".yaml",
    ".xml",
    ".html",
    ".htm",
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".css",
    ".log",
}
MAX_ATTACHMENT_TEXT_CHARS = 20_000
MAX_TRANSCRIPT_CHARS = 24_000
MAX_PROMPT_KEYWORDS = 12


class OllamaProviderError(RuntimeError):
    def __init__(self, message: str, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code


def run_prompt_with_ollama(
    transcript_text: str,
    user_prompt: str,
    attachment_paths: list[Path] | None = None,
    model: str | None = None,
) -> dict:
    normalized_prompt = (user_prompt or "").strip()
    if not normalized_prompt:
        raise OllamaProviderError("Prompt vazio para o Ollama.", code="missing_prompt")

    attachment_context, images, warnings = build_attachment_context(attachment_paths or [])
    prepared_transcript, transcript_strategy = prepare_transcript_context(transcript_text, normalized_prompt)
    message_content = build_message_content(normalized_prompt, prepared_transcript, attachment_context)
    selected_model, selection_reason = select_ollama_model(
        explicit_model=model,
        user_prompt=normalized_prompt,
        transcript_context=prepared_transcript,
        attachment_count=len(attachment_paths or []),
        has_images=bool(images),
    )

    payload = {
        "model": selected_model,
        "stream": False,
        "messages": [
            {
                "role": "user",
                "content": message_content,
                "images": images,
            }
        ],
    }

    try:
        response = requests.post(
            f"{DEFAULT_OLLAMA_URL}/api/chat",
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=DEFAULT_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        raise OllamaProviderError(
            "Nao foi possivel conectar ao Ollama local. Verifique se o servidor esta rodando.",
            code="ollama_unavailable",
        ) from exc

    if response.status_code >= 400:
        detail = response.text.strip() or "Falha desconhecida no Ollama."
        raise OllamaProviderError(f"Erro ao executar prompt no Ollama: {detail}", code="ollama_error")

    body = response.json()
    message = body.get("message", {})
    content = (message.get("content") or "").strip()
    if not content:
        raise OllamaProviderError("Ollama nao retornou texto.", code="empty_response")

    return {
        "model": body.get("model", selected_model),
        "text": content,
        "response_id": None,
        "provider": "ollama",
        "warnings": warnings,
        "context_strategy": transcript_strategy,
        "model_strategy": selection_reason,
        "metrics": {
            "total_duration": body.get("total_duration"),
            "load_duration": body.get("load_duration"),
            "prompt_eval_count": body.get("prompt_eval_count"),
            "eval_count": body.get("eval_count"),
        },
    }


def build_message_content(user_prompt: str, transcript_text: str, attachment_context: str) -> str:
    sections = [
        "Voce vai responder ao prompt do usuario usando a transcricao como contexto principal.",
        "Siga o pedido do usuario com precisao e seja objetivo.",
        "## Prompt do usuario",
        user_prompt,
        "## Transcricao",
        transcript_text.strip() or "(transcricao vazia)",
    ]
    if attachment_context:
        sections.extend(["## Contexto adicional de anexos", attachment_context])
    return "\n\n".join(sections).strip()


def select_ollama_model(
    explicit_model: str | None,
    user_prompt: str,
    transcript_context: str,
    attachment_count: int,
    has_images: bool,
) -> tuple[str, str]:
    normalized_explicit = (explicit_model or "").strip()
    if normalized_explicit:
        return normalized_explicit, "manual"

    prompt_length = len(user_prompt)
    context_length = len(transcript_context)
    complex_prompt = prompt_length >= COMPLEX_PROMPT_THRESHOLD
    complex_context = context_length >= COMPLEX_CONTEXT_THRESHOLD
    has_many_attachments = attachment_count >= 2

    if has_images or has_many_attachments or complex_prompt or complex_context:
        return DEFAULT_OLLAMA_MODEL, "quality_auto"

    return FAST_OLLAMA_MODEL, "fast_auto"


def prepare_transcript_context(transcript_text: str, user_prompt: str) -> tuple[str, str]:
    normalized = normalize_whitespace(transcript_text)
    if len(normalized) <= MAX_TRANSCRIPT_CHARS:
        return normalized, "full"

    prompt_keywords = extract_prompt_keywords(user_prompt)
    chunks = split_text_chunks(normalized, chunk_size=3500, overlap=350)
    scored_chunks = [
        (score_chunk(chunk, prompt_keywords, index, len(chunks)), index, chunk)
        for index, chunk in enumerate(chunks)
    ]
    scored_chunks.sort(key=lambda item: item[0], reverse=True)

    selected_chunks = []
    selected_indexes = set()

    for _, index, chunk in scored_chunks[:4]:
        selected_chunks.append((index, chunk))
        selected_indexes.add(index)

    for index in (0, len(chunks) - 1):
        if index not in selected_indexes and 0 <= index < len(chunks):
            selected_chunks.append((index, chunks[index]))
            selected_indexes.add(index)

    selected_chunks.sort(key=lambda item: item[0])
    combined = "\n\n".join(
        f"[Trecho {index + 1}/{len(chunks)}]\n{chunk}"
        for index, chunk in selected_chunks
    )

    header = (
        "A transcricao original era muito longa e foi reduzida para os trechos mais relevantes ao prompt, "
        "alem do inicio e do final do conteudo.\n\n"
    )
    return header + combined, "relevant_chunks"


def build_attachment_context(attachment_paths: list[Path]) -> tuple[str, list[str], list[str]]:
    sections: list[str] = []
    images: list[str] = []
    warnings: list[str] = []

    for attachment_path in attachment_paths:
        mime_type = mimetypes.guess_type(attachment_path.name)[0] or "application/octet-stream"
        if mime_type.startswith("image/"):
            images.append(base64.b64encode(attachment_path.read_bytes()).decode("ascii"))
            sections.append(f"[imagem anexada] {attachment_path.name}")
            continue

        if is_textual_attachment(attachment_path, mime_type):
            text = extract_text_attachment(attachment_path)
            sections.append(f"### {attachment_path.name}\n{text}")
            continue

        warnings.append(f"Anexo nao convertido automaticamente: {attachment_path.name}")
        sections.append(f"[anexo nao convertido automaticamente] {attachment_path.name}")

    return "\n\n".join(sections).strip(), images, warnings


def is_textual_attachment(path: Path, mime_type: str) -> bool:
    if any(mime_type.startswith(prefix) for prefix in TEXTUAL_MIME_PREFIXES):
        return True
    return path.suffix.lower() in TEXTUAL_EXTENSIONS


def extract_text_attachment(path: Path) -> str:
    raw = path.read_text(encoding="utf-8", errors="ignore").strip()
    if len(raw) <= MAX_ATTACHMENT_TEXT_CHARS:
        return raw
    return raw[:MAX_ATTACHMENT_TEXT_CHARS].rstrip() + "\n\n[conteudo truncado]"


def normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "")).strip()


def extract_prompt_keywords(prompt: str) -> set[str]:
    words = re.findall(r"[a-zA-Z0-9_]{4,}", prompt.lower())
    unique_words: list[str] = []
    for word in words:
        if word not in unique_words:
            unique_words.append(word)
        if len(unique_words) >= MAX_PROMPT_KEYWORDS:
            break
    return set(unique_words)


def split_text_chunks(text: str, chunk_size: int, overlap: int) -> list[str]:
    if len(text) <= chunk_size:
        return [text]

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + chunk_size)
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = max(0, end - overlap)
    return chunks


def score_chunk(chunk: str, keywords: set[str], index: int, total_chunks: int) -> int:
    lowered = chunk.lower()
    keyword_hits = sum(1 for keyword in keywords if keyword in lowered)
    edge_bonus = 1 if index in {0, total_chunks - 1} else 0
    return keyword_hits * 10 + edge_bonus
