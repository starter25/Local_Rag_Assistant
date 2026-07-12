import tempfile
import unittest
import warnings
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch

warnings.filterwarnings(
    "ignore",
    message="Using `httpx` with `starlette.testclient` is deprecated.*",
)

from fastapi.testclient import TestClient

from app.main import app as fastapi_app
from app import project_store


class ProjectStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.storage_dir = self.root / "storage"
        self.patches = [
            patch.object(project_store, "PROJECT_STORE_FILE", self.storage_dir / "projects.json"),
            patch.object(project_store, "PROJECTS_DIR", self.storage_dir / "projects"),
            patch.object(project_store, "DOCUMENT_DIR", self.storage_dir / "documents"),
            patch.object(project_store, "CHROMA_DIR", self.storage_dir / "chroma_db"),
            patch.object(project_store, "DOCUMENT_INDEX_FILE", self.storage_dir / "document_index.json"),
            patch.object(project_store, "CHAT_STORE_FILE", self.storage_dir / "chats" / "chats.json"),
        ]

        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()

        self.temp_dir.cleanup()

    def test_list_projects_creates_default_project(self):
        store = project_store.list_projects()

        self.assertEqual(store["active_project_id"], "default")
        self.assertEqual(store["projects"][0]["id"], "default")
        self.assertTrue((self.storage_dir / "projects.json").exists())

    def test_default_context_uses_existing_storage_paths(self):
        context = project_store.get_project_context("default")

        self.assertEqual(context.base_dir, self.storage_dir)
        self.assertEqual(context.document_dir, self.storage_dir / "documents")
        self.assertEqual(context.chroma_dir, self.storage_dir / "chroma_db")
        self.assertEqual(context.document_index_file, self.storage_dir / "document_index.json")
        self.assertEqual(context.chat_store_file, self.storage_dir / "chats" / "chats.json")

    def test_create_project_generates_safe_unique_id(self):
        first = project_store.create_project("Python Study")
        second = project_store.create_project("Python Study")

        self.assertEqual(first["id"], "python-study")
        self.assertEqual(second["id"], "python-study-2")

    def test_new_project_context_uses_project_directory(self):
        project = project_store.create_project("Client A")
        context = project_store.get_project_context(project["id"])
        base_dir = self.storage_dir / "projects" / "client-a"

        self.assertEqual(context.base_dir, base_dir)
        self.assertEqual(context.document_dir, base_dir / "documents")
        self.assertEqual(context.chroma_dir, base_dir / "chroma_db")
        self.assertEqual(context.document_index_file, base_dir / "document_index.json")
        self.assertEqual(context.chat_store_file, base_dir / "chats" / "chats.json")
        self.assertTrue(context.document_dir.exists())
        self.assertTrue(context.chroma_dir.exists())
        self.assertTrue(context.chat_store_file.parent.exists())

    def test_missing_project_context_raises(self):
        with self.assertRaises(ValueError):
            project_store.get_project_context("missing")


class ProjectApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(fastapi_app)

    @patch("app.main.list_saved_projects")
    def test_projects_endpoint_lists_projects(self, mock_list_projects):
        mock_list_projects.return_value = {
            "version": 1,
            "active_project_id": "default",
            "projects": [
                {
                    "id": "default",
                    "name": "Default",
                    "created_at": 1,
                    "updated_at": 1,
                }
            ],
        }

        response = self.client.get("/projects")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["active_project_id"], "default")
        self.assertEqual(response.json()["projects"][0]["id"], "default")

    @patch("app.main.create_saved_project")
    def test_projects_endpoint_creates_project(self, mock_create_project):
        mock_create_project.return_value = {
            "id": "python-study",
            "name": "Python Study",
            "created_at": 1,
            "updated_at": 1,
        }

        response = self.client.post("/projects", json={"name": "Python Study"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], "python-study")
        mock_create_project.assert_called_once_with("Python Study")

    @patch("app.main.create_saved_project")
    def test_projects_endpoint_rejects_blank_name(self, mock_create_project):
        mock_create_project.side_effect = ValueError("Project name is required.")

        response = self.client.post("/projects", json={"name": ""})

        self.assertEqual(response.status_code, 400)

    @patch("app.main.build_document_state")
    @patch("app.main.get_collection")
    @patch("app.main.get_project_context")
    def test_documents_endpoint_uses_project_context(
        self,
        mock_get_project_context,
        mock_get_collection,
        mock_build_document_state,
    ):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            context = SimpleNamespace(
                chroma_dir=root / "chroma_db",
                document_dir=root / "documents",
                document_index_file=root / "document_index.json",
            )
            mock_get_project_context.return_value = context
            mock_get_collection.return_value = object()
            mock_build_document_state.return_value = {
                "documents": [],
                "total_documents": 0,
                "total_chunks": 0,
            }

            response = self.client.get("/documents?project_id=python-study")

        self.assertEqual(response.status_code, 200)
        mock_get_project_context.assert_called_once_with("python-study")
        mock_get_collection.assert_called_once_with(
            reset=False,
            chroma_dir=context.chroma_dir,
        )
        mock_build_document_state.assert_called_once_with(
            mock_get_collection.return_value,
            document_dir=context.document_dir,
            index_file=context.document_index_file,
        )

    @patch("app.main.get_project_context")
    def test_documents_endpoint_404_for_missing_project(self, mock_get_project_context):
        mock_get_project_context.side_effect = ValueError("Project not found: missing")

        response = self.client.get("/documents?project_id=missing")

        self.assertEqual(response.status_code, 404)

    @patch("app.main.start_document_upload_job")
    @patch("app.main.get_project_context")
    def test_document_upload_passes_project_id(
        self,
        mock_get_project_context,
        mock_start_document_upload_job,
    ):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            mock_get_project_context.return_value = SimpleNamespace(
                document_dir=root / "documents",
            )
            mock_start_document_upload_job.return_value = {
                "job_id": "doc-job-project",
                "kind": "upload",
                "project_id": "python-study",
                "status": "queued",
                "stage": "queued",
                "message": "Document upload queued.",
                "elapsed_seconds": 0,
                "result": None,
                "error": "",
            }

            response = self.client.post(
                "/documents/upload?project_id=python-study",
                files={"files": ("sample.txt", b"hello", "text/plain")},
            )

        self.assertEqual(response.status_code, 200)
        mock_start_document_upload_job.assert_called_once_with(
            ["sample.txt"],
            project_id="python-study",
        )

    @patch("app.main.start_document_sync_job")
    @patch("app.main.get_project_context")
    def test_document_sync_passes_project_id(
        self,
        mock_get_project_context,
        mock_start_document_sync_job,
    ):
        mock_get_project_context.return_value = SimpleNamespace()
        mock_start_document_sync_job.return_value = {
            "job_id": "doc-job-project",
            "kind": "sync",
            "project_id": "python-study",
            "status": "queued",
            "stage": "queued",
            "message": "Document sync queued.",
            "elapsed_seconds": 0,
            "result": None,
            "error": "",
        }

        response = self.client.post("/documents/sync?project_id=python-study")

        self.assertEqual(response.status_code, 200)
        mock_start_document_sync_job.assert_called_once_with(project_id="python-study")

    @patch("app.main.answer_question")
    @patch("app.main.get_project_context")
    def test_ask_passes_project_id(
        self,
        mock_get_project_context,
        mock_answer_question,
    ):
        mock_get_project_context.return_value = SimpleNamespace(id="python-study")
        mock_answer_question.return_value = {
            "answer": "project answer",
            "sources": [],
            "mode": "balanced",
            "model": "qwen2.5:3b",
            "use_rag": True,
            "answer_mode": "strict_rag",
            "source_quality": None,
            "project_id": "python-study",
        }

        response = self.client.post(
            "/ask",
            json={
                "question": "Project question",
                "model": "qwen2.5:3b",
                "project_id": "python-study",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["project_id"], "python-study")
        mock_get_project_context.assert_called_once_with("python-study")
        self.assertEqual(mock_answer_question.call_args.kwargs["project_id"], "python-study")

    @patch("app.main.start_ask_job")
    @patch("app.main.get_project_context")
    def test_ask_job_passes_project_id(
        self,
        mock_get_project_context,
        mock_start_ask_job,
    ):
        mock_get_project_context.return_value = SimpleNamespace(id="python-study")
        mock_start_ask_job.return_value = {
            "job_id": "ask-job-project",
            "project_id": "python-study",
            "status": "queued",
            "stage": "queued",
            "message": "Answer queued.",
            "elapsed_seconds": 0,
            "result": None,
            "error": "",
        }

        response = self.client.post(
            "/ask/jobs",
            json={
                "question": "Project question",
                "model": "qwen2.5:3b",
                "project_id": "python-study",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["project_id"], "python-study")
        mock_start_ask_job.assert_called_once()
        self.assertEqual(mock_start_ask_job.call_args.kwargs["project_id"], "python-study")

    @patch("app.main.answer_question")
    @patch("app.main.get_project_context")
    def test_ask_404_for_missing_project(
        self,
        mock_get_project_context,
        mock_answer_question,
    ):
        mock_get_project_context.side_effect = ValueError("Project not found: missing")

        response = self.client.post(
            "/ask",
            json={
                "question": "Project question",
                "project_id": "missing",
            },
        )

        self.assertEqual(response.status_code, 404)
        mock_answer_question.assert_not_called()

    @patch("app.main.start_ask_job")
    @patch("app.main.get_project_context")
    def test_ask_job_404_for_missing_project(
        self,
        mock_get_project_context,
        mock_start_ask_job,
    ):
        mock_get_project_context.side_effect = ValueError("Project not found: missing")

        response = self.client.post(
            "/ask/jobs",
            json={
                "question": "Project question",
                "project_id": "missing",
            },
        )

        self.assertEqual(response.status_code, 404)
        mock_start_ask_job.assert_not_called()

    @patch("app.main.list_saved_chats")
    @patch("app.main.get_project_context")
    def test_chats_endpoint_uses_project_chat_store(
        self,
        mock_get_project_context,
        mock_list_saved_chats,
    ):
        with tempfile.TemporaryDirectory() as temp_dir:
            context = SimpleNamespace(
                chat_store_file=Path(temp_dir) / "projects" / "python-study" / "chats.json"
            )
            mock_get_project_context.return_value = context
            mock_list_saved_chats.return_value = []

            response = self.client.get("/chats?project_id=python-study")

        self.assertEqual(response.status_code, 200)
        mock_get_project_context.assert_called_once_with("python-study")
        mock_list_saved_chats.assert_called_once_with(store_file=context.chat_store_file)

    @patch("app.main.create_chat")
    @patch("app.main.get_project_context")
    def test_create_chat_uses_project_chat_store(
        self,
        mock_get_project_context,
        mock_create_chat,
    ):
        with tempfile.TemporaryDirectory() as temp_dir:
            context = SimpleNamespace(
                chat_store_file=Path(temp_dir) / "projects" / "python-study" / "chats.json"
            )
            mock_get_project_context.return_value = context
            mock_create_chat.return_value = {
                "id": "chat-project",
                "title": "Project chat",
                "messages": [],
                "created_at": 1,
                "updated_at": 1,
            }

            response = self.client.post(
                "/chats?project_id=python-study",
                json={"title": "Project chat"},
            )

        self.assertEqual(response.status_code, 200)
        mock_create_chat.assert_called_once_with(
            "Project chat",
            store_file=context.chat_store_file,
        )

    @patch("app.main.update_chat")
    @patch("app.main.get_project_context")
    def test_update_chat_uses_project_chat_store(
        self,
        mock_get_project_context,
        mock_update_chat,
    ):
        with tempfile.TemporaryDirectory() as temp_dir:
            context = SimpleNamespace(
                chat_store_file=Path(temp_dir) / "projects" / "python-study" / "chats.json"
            )
            mock_get_project_context.return_value = context
            mock_update_chat.return_value = {
                "id": "chat-project",
                "title": "Saved",
                "messages": [],
                "created_at": 1,
                "updated_at": 2,
            }

            response = self.client.put(
                "/chats/chat-project?project_id=python-study",
                json={"title": "Saved"},
            )

        self.assertEqual(response.status_code, 200)
        mock_update_chat.assert_called_once_with(
            "chat-project",
            title="Saved",
            messages=None,
            store_file=context.chat_store_file,
        )

    @patch("app.main.delete_saved_chat")
    @patch("app.main.get_project_context")
    def test_delete_chat_uses_project_chat_store(
        self,
        mock_get_project_context,
        mock_delete_saved_chat,
    ):
        with tempfile.TemporaryDirectory() as temp_dir:
            context = SimpleNamespace(
                chat_store_file=Path(temp_dir) / "projects" / "python-study" / "chats.json"
            )
            mock_get_project_context.return_value = context
            mock_delete_saved_chat.return_value = True

            response = self.client.delete("/chats/chat-project?project_id=python-study")

        self.assertEqual(response.status_code, 200)
        mock_delete_saved_chat.assert_called_once_with(
            "chat-project",
            store_file=context.chat_store_file,
        )

    @patch("app.main.list_saved_chats")
    @patch("app.main.get_project_context")
    def test_chats_endpoint_404_for_missing_project(
        self,
        mock_get_project_context,
        mock_list_saved_chats,
    ):
        mock_get_project_context.side_effect = ValueError("Project not found: missing")

        response = self.client.get("/chats?project_id=missing")

        self.assertEqual(response.status_code, 404)
        mock_list_saved_chats.assert_not_called()


if __name__ == "__main__":
    unittest.main()
