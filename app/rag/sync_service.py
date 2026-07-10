from app.rag.ingest_service import file_sha256, get_document_files, ingest_file
from app.rag.ollama_client import check_ollama
from app.rag.vector_db import (
    delete_document_from_db,
    get_collection,
    get_db_sources,
)


def list_documents():
    collection = get_collection(reset=False)
    sources = get_db_sources(collection)

    if not sources:
        print("ChromaDB에 저장된 문서가 없어.")
        return

    print("\n========== 저장된 문서 목록 ==========\n")

    for source, info in sorted(sources.items()):
        file_hash = info.get("file_hash", "")
        short_hash = file_hash[:10] if file_hash else "no-hash"

        print(f"- {source}")
        print(f"  chunk 수: {info['chunks']}")
        print(f"  file_hash: {short_hash}")
        print()

    print(f"총 문서 수: {len(sources)}")
    print(f"총 chunk 수: {collection.count()}")


def sync_documents():
    """
    storage/documents 폴더와 ChromaDB를 동기화한다.

    1. documents에서 사라진 파일은 ChromaDB에서도 삭제
    2. 새로 추가된 파일은 벡터화해서 추가
    3. 내용이 변경된 파일은 기존 chunk 삭제 후 다시 벡터화
    4. 변경 없는 파일은 skip
    """

    check_ollama()

    collection = get_collection(reset=False)

    files = {p.name: p for p in get_document_files()}
    db_sources = get_db_sources(collection)

    deleted = 0
    added = 0
    updated = 0
    skipped = 0
    total_new_chunks = 0

    for source in list(db_sources.keys()):
        if source not in files:
            deleted_chunks = delete_document_from_db(collection, source)
            deleted += 1
            print(f"DB에서 삭제됨: {source} / 삭제 chunk 수: {deleted_chunks}")

    for source, file_path in files.items():
        current_hash = file_sha256(file_path)
        db_info = db_sources.get(source)

        if db_info and db_info.get("file_hash") == current_hash:
            skipped += 1
            print(f"변경 없음, 건너뜀: {source}")
            continue

        print(f"동기화 중: {source}")

        chunk_count = ingest_file(collection, file_path, replace=True)
        total_new_chunks += chunk_count

        if db_info:
            updated += 1
            print(f"업데이트 완료: {source} / chunk 수: {chunk_count}")
        else:
            added += 1
            print(f"추가 완료: {source} / chunk 수: {chunk_count}")

    print("\n========== 동기화 완료 ==========\n")
    print(f"추가 문서 수: {added}")
    print(f"업데이트 문서 수: {updated}")
    print(f"삭제 문서 수: {deleted}")
    print(f"변경 없음: {skipped}")
    print(f"새로 생성된 chunk 수: {total_new_chunks}")
    print(f"현재 DB 전체 chunk 수: {collection.count()}")


def delete_document(source: str):
    collection = get_collection(reset=False)

    deleted_chunks = delete_document_from_db(collection, source)

    if deleted_chunks == 0:
        print(f"DB에서 해당 문서를 찾지 못했어: {source}")
        return

    print(f"DB에서 삭제 완료: {source}")
    print(f"삭제된 chunk 수: {deleted_chunks}")