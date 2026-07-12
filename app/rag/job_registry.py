import time


TERMINAL_STATUSES = {"completed", "failed", "cancelled"}


# 완료/실패/취소처럼 더 이상 진행되지 않는 job인지 확인합니다.
def is_terminal(job: dict) -> bool:
    return job.get("status") in TERMINAL_STATUSES


# queued/running 등 아직 사용자에게 진행 중으로 보여야 하는 job인지 확인합니다.
def is_active(job: dict) -> bool:
    return not is_terminal(job)


# 같은 종류의 작업을 동시에 몇 개 실행 중인지 계산합니다.
def count_active_jobs(jobs: dict) -> int:
    return sum(1 for job in jobs.values() if is_active(job))


# job을 terminal 상태로 바꾸고 정리 기준이 되는 finished_at을 남깁니다.
def mark_terminal(
    job: dict,
    status: str,
    message: str,
    result=None,
    error: str = "",
):
    job["status"] = status
    job["message"] = message

    if "stage" in job:
        job["stage"] = status

    if result is not None:
        job["result"] = result

    if error:
        job["error"] = error

    job.setdefault("finished_at", time.time())


# 오래된 terminal job을 제거하고, 너무 오래 active인 job은 실패 처리합니다.
def cleanup_jobs(
    jobs: dict,
    terminal_ttl_seconds: int,
    max_jobs: int,
    active_timeout_seconds: int,
):
    now = time.time()

    for job in jobs.values():
        if is_active(job) and now - job.get("created_at", now) > active_timeout_seconds:
            mark_terminal(
                job,
                "failed",
                "Job timed out.",
                error="Job timed out.",
            )

    expired_ids = [
        job_id
        for job_id, job in jobs.items()
        if is_terminal(job)
        and now - job.get("finished_at", job.get("created_at", now)) > terminal_ttl_seconds
    ]

    for job_id in expired_ids:
        jobs.pop(job_id, None)

    if len(jobs) <= max_jobs:
        return

    removable = sorted(
        (
            (job.get("finished_at", job.get("created_at", now)), job_id)
            for job_id, job in jobs.items()
            if is_terminal(job)
        ),
        key=lambda item: item[0],
    )

    while len(jobs) > max_jobs and removable:
        _, job_id = removable.pop(0)
        jobs.pop(job_id, None)
