from pathlib import Path

import chromadb

from app.config import CHROMA_DIR, COLLECTION_NAME


# Persistent ChromaDB collection을 열고 필요하면 컬렉션을 초기화합니다.
def get_collection(reset=False, chroma_dir: Path | None = None):
    target_dir = chroma_dir or CHROMA_DIR
    target_dir.mkdir(parents=True, exist_ok=True)

    client = chromadb.PersistentClient(path=str(target_dir))

    if reset:
        try:
            client.delete_collection(COLLECTION_NAME)
        except Exception:
            pass

    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )

    return collection


# ChromaDB metadata를 훑어 문서별 chunk 수와 file_hash를 집계합니다.
def get_db_sources(collection):
    """
    ChromaDB에 저장된 문서 source 목록을 가져온다.
    source별 chunk 개수와 file_hash를 정리한다.
    """

    data = collection.get(include=["metadatas"])
    metadatas = data.get("metadatas", [])

    sources = {}

    for meta in metadatas:
        if not meta:
            continue

        source = meta.get("source", "")

        if not source:
            continue

        if source not in sources:
            sources[source] = {
                "chunks": 0,
                "file_hash": meta.get("file_hash", ""),
            }

        sources[source]["chunks"] += 1

        if meta.get("file_hash"):
            sources[source]["file_hash"] = meta.get("file_hash")

    return sources


# 특정 source 파일명에 해당하는 모든 chunk를 ChromaDB에서 삭제합니다.
def delete_document_from_db(collection, source: str):
    before_count = collection.count()
    collection.delete(where={"source": source})
    after_count = collection.count()

    deleted_count = before_count - after_count
    return deleted_count
