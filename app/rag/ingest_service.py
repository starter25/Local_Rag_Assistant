import hashlib
from pathlib import Path

import time

from app.config import (
    CHROMA_DIR,
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    DOCUMENT_DIR,
    DOCUMENT_LOADER_VERSION,
    EMBED_MODEL,
    INGEST_BATCH_SIZE,
)
from app.rag.document_loader import SUPPORTED_DOCUMENT_EXTENSIONS, load_document
from app.rag.index_profile import get_current_index_profile
from app.rag.ollama_client import check_ollama, get_embeddings
from app.rag.splitter import split_text
from app.rag.vector_db import delete_document_from_db, get_collection


LOADER_VERSION = DOCUMENT_LOADER_VERSION


# 파일 내용이 바뀌었는지 판단하고 chunk 메타데이터에 저장할 해시를 계산합니다.
def file_sha256(path: Path):
    hash_obj = hashlib.sha256()

    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            hash_obj.update(block)

    return hash_obj.hexdigest()


# documents 폴더에서 현재 지원하는 파일만 골라 동기화 대상으로 사용합니다.
def get_document_files(document_dir: Path | None = None):
    target_dir = document_dir or DOCUMENT_DIR
    target_dir.mkdir(parents=True, exist_ok=True)

    return [
        p
        for p in target_dir.iterdir()
        if p.suffix.lower() in SUPPORTED_DOCUMENT_EXTENSIONS
    ]


# 같은 파일을 다시 처리해도 같은 chunk는 같은 id를 갖도록 결정적 id를 만듭니다.
def make_chunk_id(file_path: Path, page, chunk_index: int, text: str):
    raw = f"{file_path.name}-{page}-{chunk_index}-{text}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# embedding 요청과 ChromaDB upsert를 적당한 크기로 나누기 위한 배치 유틸입니다.
def batched(items, size: int):
    size = max(1, size)

    for start in range(0, len(items), size):
        yield items[start : start + size]


# 파일 하나를 텍스트 추출, chunk 분할, embedding, ChromaDB 저장까지 처리합니다.
def ingest_file(collection, file_path: Path, replace=True, progress=None):
    """
    문서 1개를 읽어서
    텍스트 추출 → chunk 분리 → embedding → ChromaDB 저장.
    """

    if replace:
        if progress:
            progress("deleting_old_chunks", "Removing old chunks from ChromaDB.")

        delete_document_from_db(collection, file_path.name)

    if progress:
        progress("hashing_file", "Calculating file hash.")

    file_hash = file_sha256(file_path)

    if progress:
        progress("reading_document", "Reading document text.")

    pages = load_document(file_path, progress=progress)
    indexed_at = int(time.time())
    character_count = sum(len((page_data.get("text") or "").strip()) for page_data in pages)

    total_chunks = 0
    page_count = len(pages)
    warnings = []
    ocr_used = any(bool(page_data.get("ocr_used")) for page_data in pages)
    ocr_engine = next((page_data.get("ocr_engine") for page_data in pages if page_data.get("ocr_engine")), "")
    ocr_pages = sum(1 for page_data in pages if page_data.get("ocr_used"))

    if not pages or character_count == 0:
        warnings.append("No extractable text was found.")

    for page_data in pages:
        for warning in page_data.get("warnings", []) or []:
            if warning and warning not in warnings:
                warnings.append(warning)

    for page_data in pages:
        text = page_data.get("text", "")
        page = page_data.get("page")

        if progress:
            progress("splitting_chunks", f"Splitting page {page if page is not None else ''} into chunks.")

        chunks = split_text(text)

        chunk_records = []

        for idx, chunk in enumerate(chunks):
            chunk_records.append(
                {
                    "id": make_chunk_id(file_path, page, idx, chunk),
                    "text": chunk,
                    "metadata": {
                        "source": file_path.name,
                        "page": page if page is not None else "",
                        "chunk_index": idx,
                        "file_hash": file_hash,
                        "loader_version": LOADER_VERSION,
                        "embedding_model": EMBED_MODEL,
                        "chunk_size": CHUNK_SIZE,
                        "chunk_overlap": CHUNK_OVERLAP,
                        "indexed_at": indexed_at,
                        "ocr_used": bool(page_data.get("ocr_used")),
                        "ocr_engine": page_data.get("ocr_engine", ""),
                    },
                }
            )

        for batch in batched(chunk_records, INGEST_BATCH_SIZE):
            documents = [item["text"] for item in batch]

            if progress:
                progress(
                    "embedding_chunks",
                    f"Embedding chunks {total_chunks + 1}-{total_chunks + len(batch)}.",
                )

            embeddings = get_embeddings(documents)

            if progress:
                progress("saving_vectors", "Saving vectors to ChromaDB.")

            collection.upsert(
                ids=[item["id"] for item in batch],
                documents=documents,
                embeddings=embeddings,
                metadatas=[item["metadata"] for item in batch],
            )

            total_chunks += len(batch)

    return {
        "chunks": total_chunks,
        "pages": page_count,
        "characters": character_count,
        "file_hash": file_hash,
        "warnings": warnings,
        "ocr_used": ocr_used,
        "ocr_engine": ocr_engine,
        "ocr_pages": ocr_pages,
        "index_profile": get_current_index_profile(),
    }


# CLI나 수동 동기화에서 documents 폴더 전체를 한 번에 벡터화할 때 사용합니다.
def ingest_documents(reset=False):
    check_ollama()

    collection = get_collection(reset=reset)
    files = get_document_files()

    if not files:
        print(f"문서가 없어. 먼저 여기에 파일을 넣어줘: {DOCUMENT_DIR}")
        return

    total_chunks = 0

    for file_path in files:
        print(f"\n문서 처리 중: {file_path.name}")

        result = ingest_file(collection, file_path, replace=True)
        chunk_count = result["chunks"]
        total_chunks += chunk_count

        print(f"완료: {file_path.name} / chunk 수: {chunk_count}")

    print(f"\nDB 저장 완료. 총 chunk 수: {total_chunks}")
    print(f"현재 ChromaDB 저장 위치: {CHROMA_DIR}")
