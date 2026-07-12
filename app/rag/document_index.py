import json
import time
from pathlib import Path

from app.config import DOCUMENT_DIR, DOCUMENT_INDEX_FILE
from app.rag.document_loader import SUPPORTED_DOCUMENT_EXTENSIONS
from app.rag.index_profile import get_reindex_reasons
from app.rag.vector_db import get_db_sources


STATUS_INDEXED = "indexed"
STATUS_PROCESSING = "processing"
STATUS_EMPTY = "empty"
STATUS_FAILED = "failed"
STATUS_NEEDS_SYNC = "needs_sync"
STATUS_MISSING_FILE = "missing_file"
STATUS_UNSUPPORTED = "unsupported"

STATUS_LABELS = {
    STATUS_INDEXED: "Indexed",
    STATUS_PROCESSING: "Processing",
    STATUS_EMPTY: "No text",
    STATUS_FAILED: "Failed",
    STATUS_NEEDS_SYNC: "Needs sync",
    STATUS_MISSING_FILE: "Missing file",
    STATUS_UNSUPPORTED: "Unsupported",
}


def load_document_index(index_file: Path | None = None) -> dict:
    target_file = index_file or DOCUMENT_INDEX_FILE

    if not target_file.exists():
        return {}

    try:
        data = json.loads(target_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

    return data if isinstance(data, dict) else {}


def save_document_index(index: dict, index_file: Path | None = None):
    target_file = index_file or DOCUMENT_INDEX_FILE
    target_file.parent.mkdir(parents=True, exist_ok=True)
    target_file.write_text(
        json.dumps(index, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def get_file_metadata(path: Path) -> dict:
    stat = path.stat()

    return {
        "source": path.name,
        "extension": path.suffix.lower(),
        "size_bytes": stat.st_size,
        "modified_at": int(stat.st_mtime),
    }


def _update_document_record(source: str, updates: dict, index_file: Path | None = None) -> dict:
    index = load_document_index(index_file=index_file)
    record = {
        **index.get(source, {}),
        **updates,
        "source": source,
        "updated_at": int(time.time()),
    }
    index[source] = record
    save_document_index(index, index_file=index_file)
    return record


def mark_document_processing(path: Path, index_file: Path | None = None) -> dict:
    return _update_document_record(
        path.name,
        {
            **get_file_metadata(path),
            "status": STATUS_PROCESSING,
            "error": "",
            "warnings": [],
        },
        index_file=index_file,
    )


def mark_document_indexed(path: Path, stats: dict, index_file: Path | None = None) -> dict:
    previous = load_document_index(index_file=index_file).get(path.name, {})
    return _update_document_record(
        path.name,
        {
            **get_file_metadata(path),
            "status": STATUS_INDEXED,
            "chunks": stats.get("chunks", previous.get("chunks", 0)),
            "pages": stats.get("pages", previous.get("pages", 0)),
            "characters": stats.get("characters", previous.get("characters", 0)),
            "file_hash": stats.get("file_hash", previous.get("file_hash", "")),
            "ocr_used": stats.get("ocr_used", previous.get("ocr_used", False)),
            "ocr_engine": stats.get("ocr_engine", previous.get("ocr_engine", "")),
            "ocr_pages": stats.get("ocr_pages", previous.get("ocr_pages", 0)),
            "index_profile": stats.get("index_profile", previous.get("index_profile", {})),
            "indexed_at": int(time.time()),
            "error": "",
            "warnings": stats.get("warnings", previous.get("warnings", [])),
        },
        index_file=index_file,
    )


def mark_document_empty(path: Path, stats: dict | None = None, index_file: Path | None = None) -> dict:
    stats = stats or {}
    return _update_document_record(
        path.name,
        {
            **get_file_metadata(path),
            "status": STATUS_EMPTY,
            "chunks": stats.get("chunks", 0),
            "pages": stats.get("pages", 0),
            "characters": stats.get("characters", 0),
            "file_hash": stats.get("file_hash", ""),
            "ocr_used": stats.get("ocr_used", False),
            "ocr_engine": stats.get("ocr_engine", ""),
            "ocr_pages": stats.get("ocr_pages", 0),
            "index_profile": stats.get("index_profile", {}),
            "indexed_at": int(time.time()),
            "error": "",
            "warnings": stats.get("warnings", ["No extractable text was found."]),
        },
        index_file=index_file,
    )


def mark_document_failed(path: Path, error: str, index_file: Path | None = None) -> dict:
    metadata = get_file_metadata(path) if path.exists() else {"source": path.name}
    return _update_document_record(
        path.name,
        {
            **metadata,
            "status": STATUS_FAILED,
            "chunks": 0,
            "error": error,
            "warnings": [],
        },
        index_file=index_file,
    )


def remove_document_record(source: str, index_file: Path | None = None):
    index = load_document_index(index_file=index_file)

    if source in index:
        del index[source]
        save_document_index(index, index_file=index_file)
        return True

    return False


def _file_changed(path: Path, record: dict) -> bool:
    if not record:
        return True

    try:
        metadata = get_file_metadata(path)
    except OSError:
        return False

    return (
        metadata["size_bytes"] != record.get("size_bytes")
        or metadata["modified_at"] != record.get("modified_at")
    )


def _record_to_document(
    source: str,
    record: dict,
    db_info: dict,
    exists: bool,
    reindex_reasons: list[str] | None = None,
) -> dict:
    status = record.get("status") or STATUS_INDEXED
    warnings = record.get("warnings") or []
    reindex_reasons = reindex_reasons or []

    return {
        "source": source,
        "status": status,
        "status_label": STATUS_LABELS.get(status, status),
        "chunks": db_info.get("chunks", record.get("chunks", 0)),
        "pages": record.get("pages", 0),
        "characters": record.get("characters", 0),
        "file_hash": record.get("file_hash") or db_info.get("file_hash", ""),
        "ocr_used": bool(record.get("ocr_used")),
        "ocr_engine": record.get("ocr_engine", ""),
        "ocr_pages": record.get("ocr_pages", 0),
        "extension": record.get("extension") or Path(source).suffix.lower(),
        "size_bytes": record.get("size_bytes", 0),
        "modified_at": record.get("modified_at", 0),
        "indexed_at": record.get("indexed_at", 0),
        "exists_in_documents": exists,
        "needs_sync": status == STATUS_NEEDS_SYNC,
        "needs_reindex": bool(reindex_reasons),
        "reindex_reasons": reindex_reasons,
        "error": record.get("error", ""),
        "warnings": warnings if isinstance(warnings, list) else [],
    }


def build_document_state(
    collection,
    document_dir: Path | None = None,
    index_file: Path | None = None,
) -> dict:
    target_document_dir = document_dir or DOCUMENT_DIR
    target_document_dir.mkdir(parents=True, exist_ok=True)

    db_sources = get_db_sources(collection)
    index = load_document_index(index_file=index_file)
    document_files = {
        path.name: path
        for path in target_document_dir.iterdir()
        if path.is_file()
    }
    all_sources = set(db_sources) | set(index) | set(document_files)
    documents = []

    for source in sorted(all_sources):
        path = document_files.get(source)
        exists = path is not None
        db_info = db_sources.get(source, {})
        record = index.get(source, {})
        reindex_reasons = []

        if exists and path.suffix.lower() not in SUPPORTED_DOCUMENT_EXTENSIONS:
            status = STATUS_UNSUPPORTED
            record = {
                **record,
                **get_file_metadata(path),
                "status": status,
                "warnings": ["This file extension is not supported yet."],
            }
        elif not exists:
            status = STATUS_MISSING_FILE
            record = {
                **record,
                "status": status,
                "warnings": ["The original file is missing from the documents folder."],
            }
        elif not db_info:
            if (
                record.get("status") in {STATUS_EMPTY, STATUS_FAILED, STATUS_PROCESSING}
                and not _file_changed(path, record)
            ):
                status = record.get("status")
                if status == STATUS_EMPTY:
                    reindex_reasons = get_reindex_reasons(record.get("index_profile"))

                if reindex_reasons:
                    status = STATUS_NEEDS_SYNC
                    warnings = list(record.get("warnings") or [])
                    warning = f"Reindex needed: {reindex_reasons[0]}"

                    if warning not in warnings:
                        warnings.append(warning)

                    record = {
                        **record,
                        "status": status,
                        "warnings": warnings,
                    }
                else:
                    record = {
                        **record,
                        "status": status,
                    }
            else:
                status = STATUS_NEEDS_SYNC
                record = {
                    **record,
                    **get_file_metadata(path),
                    "status": status,
                    "warnings": ["This file has not been indexed yet."],
                }
        elif _file_changed(path, record):
            status = STATUS_NEEDS_SYNC
            record = {
                **record,
                **get_file_metadata(path),
                "status": status,
                "warnings": ["The file changed after the last index."],
            }
        else:
            status = record.get("status") or STATUS_INDEXED
            if status in {STATUS_INDEXED, STATUS_EMPTY}:
                reindex_reasons = get_reindex_reasons(record.get("index_profile"))

            if reindex_reasons:
                status = STATUS_NEEDS_SYNC
                warnings = list(record.get("warnings") or [])
                warning = f"Reindex needed: {reindex_reasons[0]}"

                if warning not in warnings:
                    warnings.append(warning)

                record = {
                    **record,
                    "status": status,
                    "warnings": warnings,
                }
            else:
                record = {
                    **record,
                    "status": status,
                }

        documents.append(_record_to_document(source, record, db_info, exists, reindex_reasons))

    return {
        "documents": documents,
        "total_documents": len(documents),
        "total_chunks": collection.count(),
    }
