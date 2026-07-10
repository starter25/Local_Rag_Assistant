from pathlib import Path
from typing import List

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.config import BASE_DIR, DOCUMENT_DIR, MAX_UPLOAD_BYTES
from app.rag.answer_service import answer_question
from app.rag.ingest_service import file_sha256, get_document_files, ingest_file
from app.rag.ollama_client import check_ollama
from app.rag.vector_db import (
    delete_document_from_db,
    get_collection,
    get_db_sources,
)


ALLOWED_EXTENSIONS = {".pdf", ".txt", ".md", ".docx"}


app = FastAPI(
    title="Local RAG Assistant API",
    description="Ollama + ChromaDB 기반 로컬 RAG 백엔드",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AskRequest(BaseModel):
    question: str
    mode: str = "fast"


class AskResponse(BaseModel):
    answer: str
    sources: list
    mode: str


def safe_filename(filename: str) -> str:
    """
    사용자가 업로드한 파일명에서 경로를 제거한다.
    예: ../../test.pdf 같은 경로 조작 방지.
    """
    safe_name = Path(filename or "").name.strip()

    if not safe_name:
        raise HTTPException(status_code=400, detail="파일명이 비어 있습니다.")

    return safe_name


def validate_extension(filename: str):
    suffix = Path(filename).suffix.lower()

    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"지원하지 않는 파일 형식이야: {suffix}",
        )


def get_document_list_data():
    collection = get_collection(reset=False)
    sources = get_db_sources(collection)

    documents = []

    for source, info in sorted(sources.items()):
        original_path = DOCUMENT_DIR / source

        documents.append(
            {
                "source": source,
                "chunks": info.get("chunks", 0),
                "file_hash": info.get("file_hash", ""),
                "exists_in_documents": original_path.exists(),
            }
        )

    return {
        "documents": documents,
        "total_documents": len(documents),
        "total_chunks": collection.count(),
    }


@app.get("/health")
def health_check():
    try:
        check_ollama()
        ollama_status = "ok"
    except Exception:
        ollama_status = "error"

    return {
        "status": "ok",
        "ollama": ollama_status,
    }


@app.get("/ready")
def ready_check():
    return {
        "status": "ok",
        "app": "local-rag-assistant",
    }


@app.post("/ask", response_model=AskResponse)
def ask(request: AskRequest):
    question = request.question.strip()

    if not question:
        raise HTTPException(status_code=400, detail="질문이 비어 있어.")

    try:
        result = answer_question(question, mode=request.mode)
        return result

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"답변 생성 중 오류가 발생했어: {str(e)}",
        )


@app.get("/documents")
def list_documents():
    try:
        return get_document_list_data()

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"문서 목록 조회 중 오류가 발생했어: {str(e)}",
        )


@app.post("/documents/upload")
async def upload_documents(files: List[UploadFile] = File(...)):
    if not files:
        raise HTTPException(status_code=400, detail="업로드할 파일이 없어.")

    try:
        check_ollama()
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Ollama가 실행 중인지 확인해줘: {str(e)}",
        )

    DOCUMENT_DIR.mkdir(parents=True, exist_ok=True)
    collection = get_collection(reset=False)

    uploaded = []

    for file in files:
        filename = safe_filename(file.filename)
        validate_extension(filename)

        save_path = DOCUMENT_DIR / filename

        content = await file.read()

        if len(content) > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"파일이 너무 큽니다. 최대 {MAX_UPLOAD_BYTES // (1024 * 1024)}MB까지 업로드할 수 있습니다.",
            )

        with save_path.open("wb") as f:
            f.write(content)

        chunk_count = ingest_file(collection, save_path, replace=True)

        uploaded.append(
            {
                "source": filename,
                "chunks": chunk_count,
                "file_hash": file_sha256(save_path),
            }
        )

    return {
        "message": "파일 업로드 및 벡터화 완료",
        "uploaded": uploaded,
        "document_state": get_document_list_data(),
    }


@app.post("/documents/sync")
def sync_documents():
    try:
        check_ollama()
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Ollama가 실행 중인지 확인해줘: {str(e)}",
        )

    collection = get_collection(reset=False)

    files = {p.name: p for p in get_document_files()}
    db_sources = get_db_sources(collection)

    deleted = []
    added = []
    updated = []
    skipped = []

    total_new_chunks = 0

    for source in list(db_sources.keys()):
        if source not in files:
            deleted_chunks = delete_document_from_db(collection, source)

            deleted.append(
                {
                    "source": source,
                    "deleted_chunks": deleted_chunks,
                }
            )

    for source, file_path in files.items():
        current_hash = file_sha256(file_path)
        db_info = db_sources.get(source)

        if db_info and db_info.get("file_hash") == current_hash:
            skipped.append(source)
            continue

        chunk_count = ingest_file(collection, file_path, replace=True)
        total_new_chunks += chunk_count

        item = {
            "source": source,
            "chunks": chunk_count,
            "file_hash": current_hash,
        }

        if db_info:
            updated.append(item)
        else:
            added.append(item)

    return {
        "message": "동기화 완료",
        "added": added,
        "updated": updated,
        "deleted": deleted,
        "skipped": skipped,
        "summary": {
            "added_count": len(added),
            "updated_count": len(updated),
            "deleted_count": len(deleted),
            "skipped_count": len(skipped),
            "new_chunks": total_new_chunks,
            "total_chunks": collection.count(),
        },
        "document_state": get_document_list_data(),
    }


@app.delete("/documents/{filename}")
def delete_document(filename: str):
    filename = safe_filename(filename)

    collection = get_collection(reset=False)
    deleted_chunks = delete_document_from_db(collection, filename)

    original_path = DOCUMENT_DIR / filename
    deleted_file = False

    if original_path.exists():
        original_path.unlink()
        deleted_file = True

    if deleted_chunks == 0 and not deleted_file:
        raise HTTPException(
            status_code=404,
            detail=f"해당 문서를 찾지 못했어: {filename}",
        )

    return {
        "message": "문서 삭제 완료",
        "source": filename,
        "deleted_file": deleted_file,
        "deleted_chunks": deleted_chunks,
        "document_state": get_document_list_data(),
    }


# 프론트엔드 정적 파일 서빙
# http://localhost:8000 으로 접속하면 frontend/index.html이 뜬다.
frontend_dir = BASE_DIR / "frontend"

if frontend_dir.exists():
    app.mount(
        "/",
        StaticFiles(directory=str(frontend_dir), html=True),
        name="frontend",
    )
