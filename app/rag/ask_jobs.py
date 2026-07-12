import threading
import time
import uuid

from app.config import DEFAULT_PROJECT_ID
from app.rag.answer_service import answer_question
from app.rag.job_registry import cleanup_jobs, count_active_jobs, mark_terminal


ASK_JOBS = {}
ASK_JOBS_LOCK = threading.Lock()
ASK_JOB_TTL_SECONDS = 30 * 60
ASK_JOB_MAX_JOBS = 100
ASK_JOB_ACTIVE_TIMEOUT_SECONDS = 30 * 60


# 오래된 완료 작업과 멈춘 작업을 정리한 뒤 job dict를 사용해야 합니다.
def _cleanup_locked():
    cleanup_jobs(
        ASK_JOBS,
        terminal_ttl_seconds=ASK_JOB_TTL_SECONDS,
        max_jobs=ASK_JOB_MAX_JOBS,
        active_timeout_seconds=ASK_JOB_ACTIVE_TIMEOUT_SECONDS,
    )


# 프론트 polling에 필요한 필드만 복사해 내부 상태 dict를 직접 노출하지 않습니다.
def _job_snapshot(job: dict) -> dict:
    return {
        "job_id": job["job_id"],
        "status": job["status"],
        "stage": job["stage"],
        "message": job["message"],
        "project_id": job.get("project_id", DEFAULT_PROJECT_ID),
        "elapsed_seconds": max(0, int(time.time() - job["created_at"])),
        "result": job.get("result"),
        "error": job.get("error", ""),
    }


# 특정 답변 job의 현재 상태를 조회합니다.
def get_ask_job(job_id: str) -> dict | None:
    with ASK_JOBS_LOCK:
        _cleanup_locked()
        job = ASK_JOBS.get(job_id)

        if not job:
            return None

        return _job_snapshot(job)


# 답변 생성은 오래 걸릴 수 있으므로 백그라운드 스레드로 실행합니다.
def start_ask_job(
    question: str,
    mode: str,
    model: str,
    use_rag: bool,
    answer_mode: str | None = None,
    chat_history: list[dict] | None = None,
    project_id: str = DEFAULT_PROJECT_ID,
) -> dict:
    with ASK_JOBS_LOCK:
        _cleanup_locked()

        if count_active_jobs(ASK_JOBS) > 0:
            raise RuntimeError("Another answer job is already running.")

        job_id = str(uuid.uuid4())
        job = {
            "job_id": job_id,
            "status": "queued",
            "stage": "queued",
            "message": "질문을 대기열에 넣는 중...",
            "project_id": project_id,
            "created_at": time.time(),
            "result": None,
            "error": "",
        }
        ASK_JOBS[job_id] = job

    thread = threading.Thread(
        target=_run_ask_job,
        args=(job_id, question, mode, model, use_rag, answer_mode, chat_history, project_id),
        daemon=True,
    )
    thread.start()

    return _job_snapshot(job)


# terminal 상태는 finished_at을 남겨 나중에 자동 정리될 수 있게 합니다.
def _update_job(job_id: str, **updates):
    with ASK_JOBS_LOCK:
        job = ASK_JOBS.get(job_id)

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


# 실제 RAG/일반 답변 생성 작업을 수행하고 progress callback으로 단계를 갱신합니다.
def _run_ask_job(
    job_id: str,
    question: str,
    mode: str,
    model: str,
    use_rag: bool,
    answer_mode: str | None,
    chat_history: list[dict] | None,
    project_id: str,
):
    def progress(stage: str, message: str):
        _update_job(
            job_id,
            status="running",
            stage=stage,
            message=message,
        )

    try:
        progress("starting", "질문 처리를 시작하는 중...")
        result = answer_question(
            question,
            mode=mode,
            model=model,
            use_rag=use_rag,
            answer_mode=answer_mode,
            chat_history=chat_history,
            progress=progress,
            project_id=project_id,
        )
        _update_job(
            job_id,
            status="completed",
            stage="completed",
            message="답변 생성이 완료됐어.",
            result=result,
        )

    except Exception as exc:
        _update_job(
            job_id,
            status="failed",
            stage="failed",
            message="답변 생성 중 오류가 발생했어.",
            error=str(exc),
        )
