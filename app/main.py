from pathlib import Path
from typing import Any, List

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.chat_store import (
    create_chat,
    delete_chat as delete_saved_chat,
    list_chats as list_saved_chats,
    update_chat,
)
from app.config import (
    DEFAULT_PROJECT_ID,
    DOCUMENT_DIR,
    ENABLE_STATIC_FRONTEND,
    FRONTEND_DIR,
    MAX_UPLOAD_BYTES,
)
from app.project_store import (
    create_project as create_saved_project,
    get_project_context,
    list_projects as list_saved_projects,
)
from app.rag.answer_service import answer_question
from app.rag.ask_jobs import get_ask_job, start_ask_job
from app.rag.document_jobs import (
    ensure_document_job_available,
    get_document_job,
    start_document_sync_job,
    start_document_upload_job,
)
from app.rag.document_index import build_document_state, remove_document_record
from app.rag.document_loader import SUPPORTED_DOCUMENT_EXTENSIONS
from app.rag.model_profiles import normalize_chat_model
from app.rag.ollama_client import check_ollama, list_ollama_models
from app.rag.model_pull import get_model_pull_job, start_model_pull
from app.rag.vector_db import (
    delete_document_from_db,
    get_collection,
)


ALLOWED_EXTENSIONS = SUPPORTED_DOCUMENT_EXTENSIONS


# FastAPI 앱은 웹 UI, Tauri 셸, 테스트 클라이언트가 모두 공유하는 API 진입점입니다.
app = FastAPI(
    title="Local RAG Assistant API",
    description="Ollama + ChromaDB 기반 로컬 RAG 백엔드",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AskRequest(BaseModel):
    question: str
    mode: str = "fast"
    model: str | None = None
    use_rag: bool = True
    answer_mode: str | None = None
    chat_history: list[dict[str, Any]] | None = None
    project_id: str = DEFAULT_PROJECT_ID


class AskResponse(BaseModel):
    answer: str
    sources: list
    mode: str
    model: str | None = None
    use_rag: bool = True
    answer_mode: str | None = None
    source_quality: dict[str, Any] | None = None
    project_id: str = DEFAULT_PROJECT_ID


class ModelPullRequest(BaseModel):
    model: str


class ChatCreateRequest(BaseModel):
    title: str | None = None


class ChatUpdateRequest(BaseModel):
    title: str | None = None
    messages: list[dict[str, Any]] | None = None


class ProjectCreateRequest(BaseModel):
    name: str


def safe_filename(filename: str) -> str:
    """
    사용자가 업로드한 파일명에서 경로를 제거한다.
    예: ../../test.pdf 같은 경로 조작 방지.
    """
    safe_name = Path(filename or "").name.strip()

    if not safe_name:
        raise HTTPException(status_code=400, detail="파일명이 비어 있습니다.")

    return safe_name


# 업로드 가능한 파일 형식을 한 곳에서 검증해 문서 로더와 API 허용 목록을 맞춥니다.
def validate_extension(filename: str):
    suffix = Path(filename).suffix.lower()

    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"지원하지 않는 파일 형식이야: {suffix}",
        )


# 문서 패널에 보여줄 현재 ChromaDB 문서 상태를 구성합니다.
def get_document_list_data():
    collection = get_collection(reset=False)
    return build_document_state(collection)


def get_project_or_404(project_id: str = DEFAULT_PROJECT_ID):
    try:
        return get_project_context(project_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


def get_document_list_data_for_project(project_id: str = DEFAULT_PROJECT_ID):
    context = get_project_or_404(project_id)
    collection = get_collection(reset=False, chroma_dir=context.chroma_dir)
    return build_document_state(
        collection,
        document_dir=context.document_dir,
        index_file=context.document_index_file,
    )


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


@app.get("/projects")
def list_projects():
    return list_saved_projects()


@app.post("/projects")
def create_project(request: ProjectCreateRequest):
    try:
        return create_saved_project(request.name)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Project creation failed: {str(e)}",
        )


@app.get("/models")
def list_models():
    try:
        return list_ollama_models()

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Ollama model list failed: {str(e)}",
        )


@app.post("/models/pull")
def pull_model(request: ModelPullRequest):
    try:
        return start_model_pull(request.model)

    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Ollama model install failed to start: {str(e)}",
        )


@app.get("/models/pull/{job_id}")
def get_pull_status(job_id: str):
    job = get_model_pull_job(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Model install job not found.")

    return job


@app.post("/ask", response_model=AskResponse)
def ask(request: AskRequest):
    question = request.question.strip()

    if not question:
        raise HTTPException(status_code=400, detail="질문이 비어 있어.")

    try:
        context = get_project_or_404(request.project_id)
        selected_model = normalize_chat_model(request.model)
        result = answer_question(
            question,
            mode=request.mode,
            model=selected_model,
            use_rag=request.use_rag,
            answer_mode=request.answer_mode,
            chat_history=request.chat_history,
            project_id=context.id,
        )
        return result

    except HTTPException:
        raise

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"답변 생성 중 오류가 발생했어: {str(e)}",
        )


@app.post("/ask/jobs")
def create_ask_job(request: AskRequest):
    question = request.question.strip()

    if not question:
        raise HTTPException(status_code=400, detail="질문이 비어 있어.")

    try:
        context = get_project_or_404(request.project_id)
        selected_model = normalize_chat_model(request.model)
        return start_ask_job(
            question=question,
            mode=request.mode,
            model=selected_model,
            use_rag=request.use_rag,
            answer_mode=request.answer_mode,
            chat_history=request.chat_history,
            project_id=context.id,
        )

    except HTTPException:
        raise

    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"답변 작업을 시작하지 못했어: {str(e)}",
        )


@app.get("/ask/jobs/{job_id}")
def get_ask_job_status(job_id: str):
    job = get_ask_job(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="답변 작업을 찾지 못했어.")

    return job


@app.get("/chats")
def list_chat_history(project_id: str = DEFAULT_PROJECT_ID):
    context = get_project_or_404(project_id)
    return {"chats": list_saved_chats(store_file=context.chat_store_file)}


@app.post("/chats")
def create_chat_history(
    request: ChatCreateRequest,
    project_id: str = DEFAULT_PROJECT_ID,
):
    context = get_project_or_404(project_id)
    return create_chat(request.title, store_file=context.chat_store_file)


@app.put("/chats/{chat_id}")
def update_chat_history(
    chat_id: str,
    request: ChatUpdateRequest,
    project_id: str = DEFAULT_PROJECT_ID,
):
    context = get_project_or_404(project_id)
    chat = update_chat(
        chat_id,
        title=request.title,
        messages=request.messages,
        store_file=context.chat_store_file,
    )

    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found.")

    return chat


@app.delete("/chats/{chat_id}")
def delete_chat_history(chat_id: str, project_id: str = DEFAULT_PROJECT_ID):
    context = get_project_or_404(project_id)

    if not delete_saved_chat(chat_id, store_file=context.chat_store_file):
        raise HTTPException(status_code=404, detail="Chat not found.")

    return {
        "message": "Chat deleted",
        "chat_id": chat_id,
    }


@app.get("/documents")
def list_documents(project_id: str = DEFAULT_PROJECT_ID):
    try:
        return get_document_list_data_for_project(project_id)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"문서 목록 조회 중 오류가 발생했어: {str(e)}",
        )


@app.post("/documents/upload")
async def upload_documents(
    files: List[UploadFile] = File(...),
    project_id: str = DEFAULT_PROJECT_ID,
):
    # 파일은 먼저 storage/documents에 저장하고, 실제 벡터화는 백그라운드 작업으로 넘깁니다.
    if not files:
        raise HTTPException(status_code=400, detail="No files were uploaded.")

    context = get_project_or_404(project_id)

    try:
        ensure_document_job_available()
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))

    context.document_dir.mkdir(parents=True, exist_ok=True)
    saved_files = []

    for file in files:
        filename = safe_filename(file.filename)
        validate_extension(filename)

        save_path = context.document_dir / filename
        bytes_written = 0

        try:
            with save_path.open("wb") as output:
                while True:
                    chunk = await file.read(1024 * 1024)

                    if not chunk:
                        break

                    bytes_written += len(chunk)

                    if bytes_written > MAX_UPLOAD_BYTES:
                        raise HTTPException(
                            status_code=413,
                            detail=f"File is too large. Upload limit is {MAX_UPLOAD_BYTES // (1024 * 1024)}MB.",
                        )

                    output.write(chunk)
        except HTTPException:
            if save_path.exists():
                save_path.unlink()

            raise

        saved_files.append(filename)

    try:
        return start_document_upload_job(saved_files, project_id=project_id)

    except RuntimeError as e:
        for filename in saved_files:
            save_path = context.document_dir / filename

            if save_path.exists():
                save_path.unlink()

        raise HTTPException(status_code=409, detail=str(e))


@app.post("/documents/sync")
def sync_documents(project_id: str = DEFAULT_PROJECT_ID):
    # documents 폴더와 ChromaDB 상태를 맞추는 작업도 UI가 멈추지 않도록 job으로 실행합니다.
    try:
        get_project_or_404(project_id)
        return start_document_sync_job(project_id=project_id)

    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))


@app.get("/documents/jobs/{job_id}")
def get_document_job_status(job_id: str):
    job = get_document_job(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Document job not found.")

    return job


@app.delete("/documents/{filename}")
def delete_document(filename: str, project_id: str = DEFAULT_PROJECT_ID):
    # 원본 파일과 ChromaDB chunk를 함께 지워 문서 목록과 검색 결과가 어긋나지 않게 합니다.
    filename = safe_filename(filename)
    context = get_project_or_404(project_id)

    collection = get_collection(reset=False, chroma_dir=context.chroma_dir)
    deleted_chunks = delete_document_from_db(collection, filename)

    original_path = context.document_dir / filename
    deleted_file = False

    if original_path.exists():
        original_path.unlink()
        deleted_file = True

    deleted_record = remove_document_record(
        filename,
        index_file=context.document_index_file,
    )

    if deleted_chunks == 0 and not deleted_file and not deleted_record:
        raise HTTPException(
            status_code=404,
            detail=f"해당 문서를 찾지 못했어: {filename}",
        )

    return {
        "message": "문서 삭제 완료",
        "source": filename,
        "deleted_file": deleted_file,
        "deleted_record": deleted_record,
        "deleted_chunks": deleted_chunks,
        "document_state": get_document_list_data_for_project(project_id),
    }


# 프론트엔드 정적 파일 서빙
# http://localhost:8000 으로 접속하면 frontend/index.html이 뜬다.
if ENABLE_STATIC_FRONTEND and FRONTEND_DIR.exists():
    app.mount(
        "/",
        StaticFiles(directory=str(FRONTEND_DIR), html=True),
        name="frontend",
    )
