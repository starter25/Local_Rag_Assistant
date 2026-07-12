import json
import re
import threading
import time
import uuid

import requests

from app.config import OLLAMA_URL
from app.rag.job_registry import cleanup_jobs, count_active_jobs, mark_terminal


MODEL_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}$")
PULL_JOBS = {}
PULL_JOBS_LOCK = threading.Lock()
PULL_JOB_TTL_SECONDS = 30 * 60
PULL_JOB_MAX_JOBS = 100
PULL_JOB_ACTIVE_TIMEOUT_SECONDS = 6 * 60 * 60


# 모델 설치 job도 일정 시간이 지나면 정리해 메모리에 계속 쌓이지 않게 합니다.
def _cleanup_locked():
    cleanup_jobs(
        PULL_JOBS,
        terminal_ttl_seconds=PULL_JOB_TTL_SECONDS,
        max_jobs=PULL_JOB_MAX_JOBS,
        active_timeout_seconds=PULL_JOB_ACTIVE_TIMEOUT_SECONDS,
    )


# Ollama 모델명만 허용해 경로/명령 주입 형태의 입력을 막습니다.
def validate_model_name(model: str) -> str:
    model = (model or "").strip()

    if not MODEL_NAME_RE.match(model):
        raise ValueError("Invalid Ollama model name.")

    return model


# 설치 진행률 UI에 필요한 필드만 반환합니다.
def _job_snapshot(job: dict) -> dict:
    return {
        "job_id": job["job_id"],
        "model": job["model"],
        "status": job["status"],
        "message": job["message"],
        "completed": job.get("completed", 0),
        "total": job.get("total", 0),
        "progress": job.get("progress", 0),
        "error": job.get("error", ""),
    }


# 모델 설치 polling 엔드포인트가 사용하는 상태 조회 함수입니다.
def get_model_pull_job(job_id: str) -> dict | None:
    with PULL_JOBS_LOCK:
        _cleanup_locked()
        job = PULL_JOBS.get(job_id)

        if not job:
            return None

        return _job_snapshot(job)


# 같은 모델 설치 요청은 기존 job을 재사용하고, 다른 모델 동시 설치는 막습니다.
def start_model_pull(model: str) -> dict:
    model = validate_model_name(model)

    with PULL_JOBS_LOCK:
        _cleanup_locked()

        for job in PULL_JOBS.values():
            if job["model"] == model and job["status"] in {"queued", "running"}:
                return _job_snapshot(job)

        if count_active_jobs(PULL_JOBS) > 0:
            raise RuntimeError("Another model install is already running.")

        job_id = str(uuid.uuid4())
        job = {
            "job_id": job_id,
            "model": model,
            "status": "queued",
            "message": "Queued",
            "completed": 0,
            "total": 0,
            "progress": 0,
            "error": "",
            "created_at": time.time(),
        }
        PULL_JOBS[job_id] = job

    thread = threading.Thread(target=_run_model_pull, args=(job_id,), daemon=True)
    thread.start()

    return _job_snapshot(job)


# Ollama stream 응답에서 받은 진행률을 job 상태에 반영합니다.
def _update_job(job_id: str, **updates):
    with PULL_JOBS_LOCK:
        job = PULL_JOBS.get(job_id)

        if not job:
            return

        status = updates.get("status")

        if status in {"completed", "failed", "cancelled"}:
            mark_terminal(
                job,
                status,
                updates.get("message", job.get("message", "")),
                error=updates.get("error", ""),
            )

            if "progress" in updates:
                job["progress"] = updates["progress"]

            return

        job.update(updates)


# Ollama /api/pull stream을 읽어 모델 다운로드 진행 상황을 추적합니다.
def _run_model_pull(job_id: str):
    with PULL_JOBS_LOCK:
        job = PULL_JOBS.get(job_id)

        if not job:
            return

        model = job["model"]

    _update_job(job_id, status="running", message="Connecting to Ollama")

    try:
        response = requests.post(
            f"{OLLAMA_URL}/api/pull",
            json={
                "name": model,
                "stream": True,
            },
            stream=True,
            timeout=(5, 300),
        )
        response.raise_for_status()

        for line in response.iter_lines(decode_unicode=True):
            if not line:
                continue

            data = json.loads(line)
            status_text = data.get("status") or "Downloading"
            completed = int(data.get("completed") or 0)
            total = int(data.get("total") or 0)
            progress = 0

            if total > 0:
                progress = min(99, int((completed / total) * 100))

            _update_job(
                job_id,
                status="running",
                message=status_text,
                completed=completed,
                total=total,
                progress=progress,
            )

        _update_job(
            job_id,
            status="completed",
            message="Model installed",
            progress=100,
        )

    except Exception as exc:
        _update_job(
            job_id,
            status="failed",
            message="Model install failed",
            error=str(exc),
        )
