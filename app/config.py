import os
from pathlib import Path


# 환경변수 숫자 설정이 잘못 들어오면 안전하게 기본값을 사용합니다.
def _get_int(name: str, default: int) -> int:
    value = os.getenv(name)

    if value is None:
        return default

    try:
        return int(value)
    except ValueError:
        return default


# true/false 계열 환경변수를 bool 값으로 읽습니다.
def _get_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "on"}


# 저장소와 프론트 경로를 환경변수로 바꿀 수 있게 Path로 정규화합니다.
def _get_path(name: str, default: Path) -> Path:
    value = os.getenv(name)

    if not value:
        return default

    return Path(value).expanduser().resolve()


OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/")

CHAT_MODEL = os.getenv("CHAT_MODEL", "qwen2.5:3b")
EMBED_MODEL = os.getenv("EMBED_MODEL", "nomic-embed-text")

BASE_DIR = _get_path(
    "LOCAL_RAG_BASE_DIR",
    Path(__file__).resolve().parents[1],
)
FRONTEND_DIR = _get_path("LOCAL_RAG_FRONTEND_DIR", BASE_DIR / "frontend")
STORAGE_DIR = _get_path("LOCAL_RAG_STORAGE_DIR", BASE_DIR / "storage")
DOCUMENT_DIR = STORAGE_DIR / "documents"
CHROMA_DIR = STORAGE_DIR / "chroma_db"
LOG_DIR = STORAGE_DIR / "logs"
CHAT_DIR = STORAGE_DIR / "chats"
CHAT_STORE_FILE = CHAT_DIR / "chats.json"
DOCUMENT_INDEX_FILE = STORAGE_DIR / "document_index.json"
DEFAULT_PROJECT_ID = "default"
PROJECTS_DIR = STORAGE_DIR / "projects"
PROJECT_STORE_FILE = STORAGE_DIR / "projects.json"

COLLECTION_NAME = "local_documents"

DOCUMENT_LOADER_VERSION = _get_int("DOCUMENT_LOADER_VERSION", 1)
CHUNK_SIZE = _get_int("CHUNK_SIZE", 800)
CHUNK_OVERLAP = _get_int("CHUNK_OVERLAP", 120)
INGEST_BATCH_SIZE = _get_int("INGEST_BATCH_SIZE", 16)
MAX_UPLOAD_BYTES = _get_int("MAX_UPLOAD_BYTES", 50 * 1024 * 1024)
ENABLE_OCR = _get_bool("ENABLE_OCR", True)
OCR_LANGUAGES = os.getenv("OCR_LANGUAGES", "eng+kor")
OCR_DPI = _get_int("OCR_DPI", 200)
OCR_MAX_PDF_PAGES = _get_int("OCR_MAX_PDF_PAGES", 30)
OCR_MIN_TEXT_CHARS = _get_int("OCR_MIN_TEXT_CHARS", 40)
TESSERACT_CMD = os.getenv("TESSERACT_CMD", "").strip()

NO_ANSWER_TEXT = "문서에서 찾을 수 없습니다."

DEFAULT_RETRIEVAL_MODE = "balanced"

ENABLE_QUERY_REWRITE = _get_bool("ENABLE_QUERY_REWRITE", True)
QUERY_REWRITE_MODEL = CHAT_MODEL
ENABLE_STATIC_FRONTEND = _get_bool("LOCAL_RAG_ENABLE_STATIC_FRONTEND", True)

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
