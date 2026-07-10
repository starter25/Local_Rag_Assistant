import os
from pathlib import Path


def _get_int(name: str, default: int) -> int:
    value = os.getenv(name)

    if value is None:
        return default

    try:
        return int(value)
    except ValueError:
        return default


def _get_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "on"}


OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/")

CHAT_MODEL = os.getenv("CHAT_MODEL", "qwen2.5:3b")
EMBED_MODEL = os.getenv("EMBED_MODEL", "nomic-embed-text")

BASE_DIR = Path(__file__).resolve().parents[1]

STORAGE_DIR = BASE_DIR / "storage"
DOCUMENT_DIR = STORAGE_DIR / "documents"
CHROMA_DIR = STORAGE_DIR / "chroma_db"

COLLECTION_NAME = "local_documents"

CHUNK_SIZE = _get_int("CHUNK_SIZE", 800)
CHUNK_OVERLAP = _get_int("CHUNK_OVERLAP", 120)
INGEST_BATCH_SIZE = _get_int("INGEST_BATCH_SIZE", 16)
MAX_UPLOAD_BYTES = _get_int("MAX_UPLOAD_BYTES", 50 * 1024 * 1024)

NO_ANSWER_TEXT = "문서에서 찾을 수 없습니다."

DEFAULT_RETRIEVAL_MODE = "balanced"

ENABLE_QUERY_REWRITE = _get_bool("ENABLE_QUERY_REWRITE", True)
QUERY_REWRITE_MODEL = CHAT_MODEL

RETRIEVAL_MODES = {
    "fast": {
        "candidate_k": 4,
        "final_k": 2,
        "distance_threshold": 0.40,
        "query_variant_k": 2,
    },
    "balanced": {
        "candidate_k": 8,
        "final_k": 4,
        "distance_threshold": 0.44,
        "query_variant_k": 3,
    },
    "deep": {
        "candidate_k": 12,
        "final_k": 6,
        "distance_threshold": 0.50,
        "query_variant_k": 4,
    },
}
