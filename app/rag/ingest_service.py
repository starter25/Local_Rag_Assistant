import hashlib
from pathlib import Path

from app.config import CHROMA_DIR, DOCUMENT_DIR, INGEST_BATCH_SIZE
from app.rag.document_loader import load_document
from app.rag.ollama_client import check_ollama, get_embeddings
from app.rag.splitter import split_text
from app.rag.vector_db import delete_document_from_db, get_collection


def file_sha256(path: Path):
    hash_obj = hashlib.sha256()

    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            hash_obj.update(block)

    return hash_obj.hexdigest()


def get_document_files():
    DOCUMENT_DIR.mkdir(parents=True, exist_ok=True)

    return [
        p
        for p in DOCUMENT_DIR.iterdir()
        if p.suffix.lower() in [".txt", ".md", ".pdf", ".docx"]
    ]


def make_chunk_id(file_path: Path, page, chunk_index: int, text: str):
    raw = f"{file_path.name}-{page}-{chunk_index}-{text}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def batched(items, size: int):
    size = max(1, size)

    for start in range(0, len(items), size):
        yield items[start : start + size]


def ingest_file(collection, file_path: Path, replace=True):
    """
    문서 1개를 읽어서
    텍스트 추출 → chunk 분리 → embedding → ChromaDB 저장.
    """

    if replace:
        delete_document_from_db(collection, file_path.name)

    file_hash = file_sha256(file_path)
    pages = load_document(file_path)

    total_chunks = 0

    for page_data in pages:
        text = page_data["text"]
        page = page_data["page"]

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
                    },
                }
            )

        for batch in batched(chunk_records, INGEST_BATCH_SIZE):
            documents = [item["text"] for item in batch]
            embeddings = get_embeddings(documents)

            collection.upsert(
                ids=[item["id"] for item in batch],
                documents=documents,
                embeddings=embeddings,
                metadatas=[item["metadata"] for item in batch],
            )

            total_chunks += len(batch)

    return total_chunks


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

        chunk_count = ingest_file(collection, file_path, replace=True)
        total_chunks += chunk_count

        print(f"완료: {file_path.name} / chunk 수: {chunk_count}")

    print(f"\nDB 저장 완료. 총 chunk 수: {total_chunks}")
    print(f"현재 ChromaDB 저장 위치: {CHROMA_DIR}")
