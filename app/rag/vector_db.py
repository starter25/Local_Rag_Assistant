import chromadb

from app.config import CHROMA_DIR, COLLECTION_NAME


def get_collection(reset=False):
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)

    client = chromadb.PersistentClient(path=str(CHROMA_DIR))

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


def delete_document_from_db(collection, source: str):
    before_count = collection.count()
    collection.delete(where={"source": source})
    after_count = collection.count()

    deleted_count = before_count - after_count
    return deleted_count