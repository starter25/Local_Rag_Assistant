import threading
import time
import uuid
from pathlib import Path

from app.config import DEFAULT_PROJECT_ID
from app.project_store import get_project_context
from app.rag.document_index import (
    build_document_state,
    load_document_index,
    mark_document_empty,
    mark_document_failed,
    mark_document_indexed,
    mark_document_processing,
    remove_document_record,
)
from app.rag.ingest_service import file_sha256, get_document_files, ingest_file
from app.rag.index_profile import get_reindex_reasons
from app.rag.job_registry import cleanup_jobs, count_active_jobs, mark_terminal
from app.rag.ollama_client import check_ollama
from app.rag.vector_db import delete_document_from_db, get_collection, get_db_sources


DOCUMENT_JOBS = {}
DOCUMENT_JOBS_LOCK = threading.Lock()
DOCUMENT_INGEST_LOCK = threading.Lock()
DOCUMENT_JOB_TTL_SECONDS = 30 * 60
DOCUMENT_JOB_MAX_JOBS = 100
DOCUMENT_JOB_ACTIVE_TIMEOUT_SECONDS = 2 * 60 * 60


# 문서 작업 목록이 계속 커지거나 멈춘 job이 남지 않도록 정리합니다.
def _cleanup_locked():
    cleanup_jobs(
        DOCUMENT_JOBS,
        terminal_ttl_seconds=DOCUMENT_JOB_TTL_SECONDS,
        max_jobs=DOCUMENT_JOB_MAX_JOBS,
        active_timeout_seconds=DOCUMENT_JOB_ACTIVE_TIMEOUT_SECONDS,
    )


# 문서 job 상태를 프론트 polling 응답 형태로 변환합니다.
def _job_snapshot(job: dict) -> dict:
    return {
        "job_id": job["job_id"],
        "kind": job["kind"],
        "project_id": job.get("project_id", DEFAULT_PROJECT_ID),
        "status": job["status"],
        "stage": job["stage"],
        "message": job["message"],
        "elapsed_seconds": max(0, int(time.time() - job["created_at"])),
        "result": job.get("result"),
        "error": job.get("error", ""),
    }


# 업로드/동기화 job 상태를 조회합니다.
def get_document_job(job_id: str) -> dict | None:
    with DOCUMENT_JOBS_LOCK:
        _cleanup_locked()
        job = DOCUMENT_JOBS.get(job_id)

        if not job:
            return None

        return _job_snapshot(job)


# 문서 작업은 ChromaDB를 공유하므로 동시에 하나만 만들 수 있게 제한합니다.
def _create_job(kind: str, message: str, project_id: str = DEFAULT_PROJECT_ID) -> dict:
    job_id = str(uuid.uuid4())
    job = {
        "job_id": job_id,
        "kind": kind,
        "project_id": project_id,
        "status": "queued",
        "stage": "queued",
        "message": message,
        "created_at": time.time(),
        "result": None,
        "error": "",
    }

    with DOCUMENT_JOBS_LOCK:
        _cleanup_locked()

        if count_active_jobs(DOCUMENT_JOBS) > 0:
            raise RuntimeError("Another document job is already running.")

        DOCUMENT_JOBS[job_id] = job

    return job


# 파일 저장 전에 문서 작업이 가능한지 확인해 실패 시 원본 파일이 남지 않게 합니다.
def ensure_document_job_available():
    with DOCUMENT_JOBS_LOCK:
        _cleanup_locked()

        if count_active_jobs(DOCUMENT_JOBS) > 0:
            raise RuntimeError("Another document job is already running.")


# job 상태 갱신을 한 곳으로 모아 terminal 상태 처리 방식을 통일합니다.
def _update_job(job_id: str, **updates):
    with DOCUMENT_JOBS_LOCK:
        job = DOCUMENT_JOBS.get(job_id)

        if not job:
            return

        status = updates.get("status")

        if status in {"completed", "failed", "cancelled"}:
            mark_terminal(
                job,
                status,
                updates.get("message", job.get("message", "")),
                result=updates.get("result"),
                error=updates.get("error", ""),
            )
            return

        job.update(updates)


# 작업 완료 후 UI가 문서 목록을 바로 갱신할 수 있도록 현재 DB 상태를 함께 반환합니다.
def _document_state(collection, context) -> dict:
    return build_document_state(
        collection,
        document_dir=context.document_dir,
        index_file=context.document_index_file,
    )


# 업로드된 파일 목록을 백그라운드 벡터화 작업으로 넘깁니다.
def start_document_upload_job(
    saved_files: list[str],
    project_id: str = DEFAULT_PROJECT_ID,
) -> dict:
    job = _create_job("upload", "Document upload queued.", project_id=project_id)

    thread = threading.Thread(
        target=_run_upload_job,
        args=(job["job_id"], saved_files, project_id),
        daemon=True,
    )
    thread.start()

    return _job_snapshot(job)


# documents 폴더와 ChromaDB의 추가/수정/삭제 상태를 맞추는 job을 시작합니다.
def start_document_sync_job(project_id: str = DEFAULT_PROJECT_ID) -> dict:
    job = _create_job("sync", "Document sync queued.", project_id=project_id)

    thread = threading.Thread(
        target=_run_sync_job,
        args=(job["job_id"], project_id),
        daemon=True,
    )
    thread.start()

    return _job_snapshot(job)


# 문서 처리 단계 메시지를 프론트 loading UI에 전달합니다.
def _progress(job_id: str, stage: str, message: str):
    _update_job(
        job_id,
        status="running",
        stage=stage,
        message=message,
    )


# 업로드된 파일을 하나씩 읽고 기존 chunk를 교체한 뒤 새 embedding을 저장합니다.
def _run_upload_job(job_id: str, saved_files: list[str], project_id: str):
    try:
        with DOCUMENT_INGEST_LOCK:
            context = get_project_context(project_id)
            _progress(job_id, "checking_ollama", "Ollama connection is being checked.")
            check_ollama()

            collection = get_collection(reset=False, chroma_dir=context.chroma_dir)
            uploaded = []
            failed = []
            empty = []

            for filename in saved_files:
                file_path = context.document_dir / Path(filename).name

                if not file_path.exists():
                    failed.append(
                        {
                            "source": file_path.name,
                            "error": f"Uploaded file is missing: {file_path.name}",
                        }
                    )
                    continue

                _progress(job_id, "reading_document", f"Reading document: {file_path.name}")
                mark_document_processing(file_path, index_file=context.document_index_file)

                try:
                    ingest_result = ingest_file(
                        collection,
                        file_path,
                        replace=True,
                        progress=lambda stage, message, name=file_path.name: _progress(
                            job_id,
                            stage,
                            f"{name}: {message}",
                        ),
                    )
                except Exception as exc:
                    mark_document_failed(file_path, str(exc), index_file=context.document_index_file)
                    failed.append(
                        {
                            "source": file_path.name,
                            "error": str(exc),
                        }
                    )
                    continue

                chunk_count = ingest_result["chunks"]

                if chunk_count == 0:
                    mark_document_empty(
                        file_path,
                        ingest_result,
                        index_file=context.document_index_file,
                    )
                    empty.append(
                        {
                            "source": file_path.name,
                            "chunks": 0,
                            "file_hash": ingest_result["file_hash"],
                        }
                    )
                else:
                    mark_document_indexed(
                        file_path,
                        ingest_result,
                        index_file=context.document_index_file,
                    )

                uploaded.append(
                    {
                        "source": file_path.name,
                        "chunks": chunk_count,
                        "file_hash": ingest_result["file_hash"],
                    }
                )

            _update_job(
                job_id,
                status="completed",
                stage="completed",
                message="Document upload and vectorization completed.",
                result={
                    "message": "Document upload and vectorization completed.",
                    "uploaded": uploaded,
                    "failed": failed,
                    "empty": empty,
                    "document_state": _document_state(collection, context),
                },
            )

    except Exception as exc:
        _update_job(
            job_id,
            status="failed",
            stage="failed",
            message="Document upload failed.",
            error=str(exc),
        )


# 폴더 스캔 결과와 DB 메타데이터를 비교해 삭제/추가/수정/스킵을 결정합니다.
def _run_sync_job(job_id: str, project_id: str):
    try:
        with DOCUMENT_INGEST_LOCK:
            context = get_project_context(project_id)
            _progress(job_id, "checking_ollama", "Ollama connection is being checked.")
            check_ollama()

            collection = get_collection(reset=False, chroma_dir=context.chroma_dir)

            _progress(job_id, "scanning_documents", "Scanning document folder.")
            files = {p.name: p for p in get_document_files(context.document_dir)}
            db_sources = get_db_sources(collection)
            document_index = load_document_index(index_file=context.document_index_file)

            deleted = []
            added = []
            updated = []
            failed = []
            empty = []
            skipped = []
            total_new_chunks = 0

            for source in list(db_sources.keys()):
                if source not in files:
                    _progress(job_id, "deleting_removed_documents", f"Removing stale document: {source}")
                    deleted_chunks = delete_document_from_db(collection, source)
                    remove_document_record(source, index_file=context.document_index_file)
                    deleted.append(
                        {
                            "source": source,
                            "deleted_chunks": deleted_chunks,
                        }
                    )

            for source, file_path in files.items():
                _progress(job_id, "checking_hashes", f"Checking document: {source}")
                current_hash = file_sha256(file_path)
                db_info = db_sources.get(source)
                reindex_reasons = get_reindex_reasons(
                    document_index.get(source, {}).get("index_profile")
                )

                if db_info and db_info.get("file_hash") == current_hash and not reindex_reasons:
                    mark_document_indexed(
                        file_path,
                        {
                            "chunks": db_info.get("chunks", 0),
                            "file_hash": current_hash,
                            "index_profile": document_index.get(source, {}).get("index_profile", {}),
                        },
                        index_file=context.document_index_file,
                    )
                    skipped.append(source)
                    continue

                mark_document_processing(file_path, index_file=context.document_index_file)

                try:
                    ingest_result = ingest_file(
                        collection,
                        file_path,
                        replace=True,
                        progress=lambda stage, message, name=source: _progress(
                            job_id,
                            stage,
                            f"{name}: {message}",
                        ),
                    )
                except Exception as exc:
                    mark_document_failed(file_path, str(exc), index_file=context.document_index_file)
                    failed.append(
                        {
                            "source": source,
                            "error": str(exc),
                        }
                    )
                    continue

                chunk_count = ingest_result["chunks"]
                total_new_chunks += chunk_count

                if chunk_count == 0:
                    mark_document_empty(
                        file_path,
                        ingest_result,
                        index_file=context.document_index_file,
                    )
                    empty.append(
                        {
                            "source": source,
                            "chunks": 0,
                            "file_hash": current_hash,
                        }
                    )
                else:
                    mark_document_indexed(
                        file_path,
                        ingest_result,
                        index_file=context.document_index_file,
                    )

                item = {
                    "source": source,
                    "chunks": chunk_count,
                    "file_hash": ingest_result["file_hash"],
                }

                if db_info:
                    updated.append(item)
                else:
                    added.append(item)

            _update_job(
                job_id,
                status="completed",
                stage="completed",
                message="Document sync completed.",
                result={
                    "message": "Document sync completed.",
                    "added": added,
                    "updated": updated,
                    "deleted": deleted,
                    "failed": failed,
                    "empty": empty,
                    "skipped": skipped,
                    "summary": {
                        "added_count": len(added),
                        "updated_count": len(updated),
                        "deleted_count": len(deleted),
                        "failed_count": len(failed),
                        "empty_count": len(empty),
                        "skipped_count": len(skipped),
                        "new_chunks": total_new_chunks,
                        "total_chunks": collection.count(),
                    },
                    "document_state": _document_state(collection, context),
                },
            )

    except Exception as exc:
        _update_job(
            job_id,
            status="failed",
            stage="failed",
            message="Document sync failed.",
            error=str(exc),
        )
