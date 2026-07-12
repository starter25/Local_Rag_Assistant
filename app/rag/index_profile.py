from app.config import (
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    DOCUMENT_LOADER_VERSION,
    EMBED_MODEL,
    ENABLE_OCR,
    OCR_DPI,
    OCR_LANGUAGES,
    OCR_MIN_TEXT_CHARS,
)


PROFILE_REASON_LABELS = {
    "loader_version": "document parser changed",
    "embedding_model": "embedding model changed",
    "chunk_size": "chunk size changed",
    "chunk_overlap": "chunk overlap changed",
    "ocr_enabled": "OCR setting changed",
    "ocr_languages": "OCR language setting changed",
    "ocr_dpi": "OCR DPI changed",
    "ocr_min_text_chars": "OCR text threshold changed",
}


def get_current_index_profile() -> dict:
    return {
        "loader_version": DOCUMENT_LOADER_VERSION,
        "embedding_model": EMBED_MODEL,
        "chunk_size": CHUNK_SIZE,
        "chunk_overlap": CHUNK_OVERLAP,
        "ocr_enabled": ENABLE_OCR,
        "ocr_languages": OCR_LANGUAGES,
        "ocr_dpi": OCR_DPI,
        "ocr_min_text_chars": OCR_MIN_TEXT_CHARS,
    }


def get_reindex_reasons(stored_profile: dict | None, current_profile: dict | None = None) -> list[str]:
    if not stored_profile:
        return ["legacy index metadata"]

    current_profile = current_profile or get_current_index_profile()
    reasons = []

    for key, current_value in current_profile.items():
        if stored_profile.get(key) != current_value:
            reasons.append(PROFILE_REASON_LABELS.get(key, f"{key} changed"))

    return reasons


def needs_reindex(stored_profile: dict | None, current_profile: dict | None = None) -> bool:
    return bool(get_reindex_reasons(stored_profile, current_profile=current_profile))
