import time
import unittest

from app.rag.job_registry import cleanup_jobs, count_active_jobs, mark_terminal


class JobRegistryTests(unittest.TestCase):
    def test_cleanup_removes_expired_terminal_jobs(self):
        jobs = {
            "old": {
                "job_id": "old",
                "status": "completed",
                "created_at": time.time() - 100,
                "finished_at": time.time() - 100,
            },
            "new": {
                "job_id": "new",
                "status": "completed",
                "created_at": time.time(),
                "finished_at": time.time(),
            },
        }

        cleanup_jobs(
            jobs,
            terminal_ttl_seconds=10,
            max_jobs=100,
            active_timeout_seconds=100,
        )

        self.assertNotIn("old", jobs)
        self.assertIn("new", jobs)

    def test_cleanup_marks_stale_active_job_failed(self):
        jobs = {
            "active": {
                "job_id": "active",
                "status": "running",
                "stage": "running",
                "message": "Running",
                "created_at": time.time() - 100,
            }
        }

        cleanup_jobs(
            jobs,
            terminal_ttl_seconds=100,
            max_jobs=100,
            active_timeout_seconds=10,
        )

        self.assertEqual(jobs["active"]["status"], "failed")
        self.assertEqual(jobs["active"]["stage"], "failed")
        self.assertIn("finished_at", jobs["active"])

    def test_cleanup_enforces_max_jobs_using_terminal_jobs(self):
        now = time.time()
        jobs = {
            "old": {
                "job_id": "old",
                "status": "completed",
                "created_at": now - 30,
                "finished_at": now - 30,
            },
            "new": {
                "job_id": "new",
                "status": "completed",
                "created_at": now - 10,
                "finished_at": now - 10,
            },
            "active": {
                "job_id": "active",
                "status": "running",
                "created_at": now,
            },
        }

        cleanup_jobs(
            jobs,
            terminal_ttl_seconds=100,
            max_jobs=2,
            active_timeout_seconds=100,
        )

        self.assertNotIn("old", jobs)
        self.assertIn("new", jobs)
        self.assertIn("active", jobs)

    def test_mark_terminal_and_count_active_jobs(self):
        job = {
            "job_id": "job-1",
            "status": "running",
            "stage": "running",
            "message": "Running",
            "created_at": time.time(),
        }
        mark_terminal(job, "completed", "Done", result={"ok": True})

        self.assertEqual(job["status"], "completed")
        self.assertEqual(job["stage"], "completed")
        self.assertEqual(job["result"], {"ok": True})
        self.assertEqual(count_active_jobs({"job-1": job}), 0)


if __name__ == "__main__":
    unittest.main()
