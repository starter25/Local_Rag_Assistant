import time
import unittest
import warnings
from types import SimpleNamespace
from unittest.mock import patch

warnings.filterwarnings(
    "ignore",
    message="Using `httpx` with `starlette.testclient` is deprecated.*",
)

from fastapi.testclient import TestClient

from app.config import NO_ANSWER_TEXT
from app.main import app as fastapi_app
from app.rag import ask_jobs, document_jobs, model_pull
from app.rag.answer_cleaner import clean_answer
from app.rag.answer_service import (
    ANSWER_MODE_HYBRID,
    answer_general_question,
    answer_question,
)
from app.rag.chat_context import compact_chat_history, get_history_policy
from app.rag.model_profiles import (
    RECOMMENDED_MODELS,
    get_chat_options,
    get_general_chat_options,
    get_general_system_prompt,
    get_prompt_guidance,
    normalize_chat_model,
)
from app.rag.ollama_client import list_ollama_models
from app.rag.query_rewriter import extract_json, unique_keep_order
from app.rag.retrieval_settings import normalize_retrieval_mode
from app.rag.retriever import retrieve
from app.rag.source_quality import summarize_source_quality
from app.rag.splitter import split_text


class RagCoreTests(unittest.TestCase):
    def test_split_text_handles_short_text(self):
        self.assertEqual(
            split_text("짧은 문서입니다.", chunk_size=100, overlap=10),
            ["짧은 문서입니다."],
        )

    def test_split_text_makes_progress_with_overlap(self):
        text = "가" * 250
        chunks = split_text(text, chunk_size=100, overlap=20)

        self.assertEqual(len(chunks), 3)
        self.assertTrue(all(chunk for chunk in chunks))

    def test_split_text_rejects_bad_overlap(self):
        with self.assertRaises(ValueError):
            split_text("abc", chunk_size=10, overlap=10)

    def test_extract_json_ignores_extra_text(self):
        data = extract_json('설명 {"queries":["원본","확장"]} 끝')

        self.assertEqual(data, {"queries": ["원본", "확장"]})

    def test_unique_keep_order(self):
        self.assertEqual(unique_keep_order(["a", "a", " b ", ""]), ["a", "b"])

    def test_clean_answer_removes_thinking_block(self):
        answer = clean_answer("<think>hidden</think>\n최종답변: 문서 기반 답변")

        self.assertEqual(answer, "문서 기반 답변")

    def test_unknown_mode_falls_back_to_balanced(self):
        self.assertEqual(normalize_retrieval_mode("unknown"), "balanced")

    def test_no_answer_text_is_stable(self):
        self.assertEqual(NO_ANSWER_TEXT, "문서에서 찾을 수 없습니다.")

    def test_chat_history_compaction_removes_invalid_items(self):
        history = [
            {"role": "system", "content": "ignore"},
            {"role": "user", "content": ""},
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
            "bad",
        ]

        compacted = compact_chat_history(history, policy="rag")

        self.assertEqual(
            compacted,
            [
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "hi"},
            ],
        )

    def test_chat_history_compaction_keeps_recent_messages(self):
        history = [
            {"role": "user", "content": f"user {i}"}
            for i in range(12)
        ]

        compacted = compact_chat_history(history, policy="retrieval")

        self.assertEqual(len(compacted), 4)
        self.assertEqual(compacted[0]["content"], "user 8")
        self.assertEqual(compacted[-1]["content"], "user 11")

    def test_chat_history_compaction_respects_character_budget(self):
        history = [
            {"role": "user", "content": "a" * 2000},
            {"role": "assistant", "content": "b" * 2000},
            {"role": "user", "content": "c" * 2000},
        ]

        compacted = compact_chat_history(history, policy="retrieval")

        self.assertLessEqual(sum(len(item["content"]) for item in compacted), 2400)
        self.assertLessEqual(max(len(item["content"]) for item in compacted), 800)

    def test_history_policy_changes_by_answer_mode(self):
        self.assertEqual(get_history_policy(use_rag=False), "general")
        self.assertEqual(get_history_policy(use_rag=True, answer_mode="hybrid"), "hybrid")
        self.assertEqual(get_history_policy(use_rag=True, answer_mode="strict_rag"), "rag")

    def test_source_quality_none_without_sources(self):
        quality = summarize_source_quality([])

        self.assertEqual(quality["quality"], "none")
        self.assertEqual(quality["source_count"], 0)
        self.assertIsNone(quality["best_distance"])

    def test_source_quality_strong_for_close_sources(self):
        quality = summarize_source_quality(
            [
                {"distance": 0.12},
                {"distance": 0.24},
            ]
        )

        self.assertEqual(quality["quality"], "strong")
        self.assertEqual(quality["best_distance"], 0.12)

    def test_source_quality_medium_for_mixed_sources(self):
        quality = summarize_source_quality(
            [
                {"distance": 0.32},
                {"distance": 0.48},
            ]
        )

        self.assertEqual(quality["quality"], "medium")

    def test_source_quality_weak_for_far_sources(self):
        quality = summarize_source_quality(
            [
                {"distance": 0.52},
                {"distance": 0.62},
            ]
        )

        self.assertEqual(quality["quality"], "weak")

    def test_normalize_chat_model_uses_default_for_blank(self):
        self.assertTrue(normalize_chat_model(""))

    def test_deepseek_profile_discourages_thinking_output(self):
        guidance = get_prompt_guidance("deepseek-r1:7b").lower()

        self.assertIn("think", guidance)

    def test_llama_profile_adjusts_prediction_limit(self):
        options = get_chat_options("llama3.2:3b")

        self.assertEqual(options["num_predict"], 260)

    def test_general_prompt_allows_non_rag_answers(self):
        prompt = get_general_system_prompt("qwen2.5:3b")

        self.assertIn("general questions", prompt)

    def test_general_options_allow_longer_answers(self):
        options = get_general_chat_options("qwen2.5:3b")

        self.assertEqual(options["num_ctx"], 4096)
        self.assertEqual(options["num_predict"], 900)

    def test_recommended_models_include_default_candidate(self):
        names = {model["name"] for model in RECOMMENDED_MODELS}

        self.assertIn("qwen2.5:3b", names)

    @patch("app.rag.ollama_client.requests.get")
    def test_model_list_hides_embedding_models_from_chat_selection(self, mock_get):
        mock_get.return_value = SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {
                "models": [
                    {
                        "name": "nomic-embed-text:latest",
                        "modified_at": "",
                        "size": 262,
                    },
                    {
                        "name": "qwen3:4b",
                        "modified_at": "",
                        "size": 2300,
                    },
                ]
            },
        )

        data = list_ollama_models()
        names = [model["name"] for model in data["models"]]

        self.assertEqual(names, ["qwen3:4b"])
        self.assertEqual(data["embedding_model"], "nomic-embed-text")

    @patch("app.rag.answer_service.generate_with_ollama")
    def test_general_answer_does_not_return_sources(self, mock_generate):
        mock_generate.return_value = "hello"
        stages = []

        result = answer_general_question(
            "say hello",
            model="qwen2.5:3b",
            progress=lambda stage, message: stages.append(stage),
        )

        self.assertEqual(result["answer"], "hello")
        self.assertEqual(result["sources"], [])
        self.assertFalse(result["use_rag"])
        self.assertIsNone(result["source_quality"])
        self.assertEqual(mock_generate.call_args.kwargs["options"]["num_predict"], 900)
        self.assertEqual(mock_generate.call_args.kwargs["chat_history"], [])
        self.assertEqual(stages, ["preparing_question", "generating_answer"])

    @patch("app.rag.answer_service.generate_with_ollama")
    def test_general_answer_sends_compacted_chat_history(self, mock_generate):
        mock_generate.return_value = "hello"
        history = [
            {"role": "user", "content": f"message {i}"}
            for i in range(12)
        ]

        answer_general_question(
            "continue",
            model="qwen2.5:3b",
            chat_history=history,
        )

        sent_history = mock_generate.call_args.kwargs["chat_history"]
        self.assertEqual(len(sent_history), 10)
        self.assertEqual(sent_history[0]["content"], "message 2")
        self.assertEqual(sent_history[-1]["content"], "message 11")

    @patch("app.rag.answer_service.generate_with_ollama")
    @patch("app.rag.answer_service.retrieve")
    def test_rag_answer_reports_search_and_generation_stages(
        self,
        mock_retrieve,
        mock_generate,
    ):
        stages = []
        mock_retrieve.return_value = [
            {
                "text": "근거",
                "source": "doc.txt",
                "page": "",
                "chunk_index": 0,
                "distance": 0.1,
            }
        ]
        mock_generate.return_value = "문서 답변"

        result = answer_question(
            "질문",
            model="qwen2.5:3b",
            progress=lambda stage, message: stages.append(stage),
        )

        self.assertEqual(result["answer"], "문서 답변")
        self.assertEqual(result["source_quality"]["quality"], "strong")
        self.assertIn("preparing_question", stages)
        self.assertIn("searching_documents", stages)
        self.assertIn("generating_answer", stages)
        self.assertNotIn("Previous conversation", mock_retrieve.call_args.args[0])
        self.assertEqual(mock_retrieve.call_args.kwargs["progress"].__class__.__name__, "function")
        self.assertEqual(mock_retrieve.call_args.kwargs["project_id"], "default")

    @patch("app.rag.answer_service.generate_with_ollama")
    @patch("app.rag.answer_service.retrieve")
    def test_rag_answer_uses_chat_history_for_followup_search(
        self,
        mock_retrieve,
        mock_generate,
    ):
        mock_retrieve.return_value = [
            {
                "text": "洹쇨굅",
                "source": "doc.txt",
                "page": "",
                "chunk_index": 0,
                "distance": 0.1,
            }
        ]
        mock_generate.return_value = "臾몄꽌 ?듬?"

        answer_question(
            "洹멸굅 ??寃???ㅻ챸?댁쨾",
            model="qwen2.5:3b",
            chat_history=[
                {"role": "user", "content": "ChromaDB ?숆린?뷀븯???대뼸寃??섏?"},
                {"role": "assistant", "content": "臾몄꽌 ?숆린???ㅻ챸"},
            ],
        )

        retrieval_question = mock_retrieve.call_args.args[0]
        generated_prompt = mock_generate.call_args.args[0]

        self.assertIn("Previous conversation", retrieval_question)
        self.assertIn("ChromaDB", retrieval_question)
        self.assertIn("Previous conversation", generated_prompt)
        self.assertIn("Use the previous conversation only", generated_prompt)

    @patch("app.rag.answer_service.generate_with_ollama")
    @patch("app.rag.answer_service.retrieve")
    def test_hybrid_answer_uses_sources_and_marks_answer_mode(
        self,
        mock_retrieve,
        mock_generate,
    ):
        stages = []
        mock_retrieve.return_value = [
            {
                "text": "문서 근거",
                "source": "doc.txt",
                "page": "",
                "chunk_index": 0,
                "distance": 0.1,
            }
        ]
        mock_generate.return_value = "문서에서 확인한 내용\n- 문서 근거\n\nAI 해석\n- 해석"

        result = answer_question(
            "질문",
            model="qwen2.5:3b",
            answer_mode=ANSWER_MODE_HYBRID,
            progress=lambda stage, message: stages.append(stage),
        )

        self.assertEqual(result["answer_mode"], ANSWER_MODE_HYBRID)
        self.assertTrue(result["use_rag"])
        self.assertEqual(result["source_quality"]["quality"], "strong")
        self.assertIn("generating_answer", stages)
        self.assertIn("options", mock_generate.call_args.kwargs)

    @patch("app.rag.answer_service.generate_with_ollama")
    @patch("app.rag.answer_service.retrieve")
    def test_rag_answer_passes_project_id_to_retriever(
        self,
        mock_retrieve,
        mock_generate,
    ):
        mock_retrieve.return_value = [
            {
                "text": "Project-specific evidence",
                "source": "doc.txt",
                "page": "",
                "chunk_index": 0,
                "distance": 0.1,
            }
        ]
        mock_generate.return_value = "Project answer"

        result = answer_question(
            "question",
            model="qwen2.5:3b",
            project_id="python-study",
        )

        self.assertEqual(result["project_id"], "python-study")
        self.assertEqual(mock_retrieve.call_args.kwargs["project_id"], "python-study")


class RetrieverProjectTests(unittest.TestCase):
    @patch("app.rag.retriever.get_collection")
    @patch("app.rag.retriever.get_project_context")
    def test_retrieve_uses_project_chroma_dir(
        self,
        mock_get_project_context,
        mock_get_collection,
    ):
        context = SimpleNamespace(chroma_dir="project-chroma")
        collection = mock_get_collection.return_value
        collection.count.return_value = 0
        mock_get_project_context.return_value = context

        result = retrieve("question", project_id="python-study")

        self.assertEqual(result, [])
        mock_get_project_context.assert_called_once_with("python-study")
        mock_get_collection.assert_called_once_with(
            reset=False,
            chroma_dir=context.chroma_dir,
        )


class ApiContractTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(fastapi_app)

    @patch("app.main.list_ollama_models")
    def test_models_endpoint_returns_installed_models(self, mock_list_models):
        mock_list_models.return_value = {
            "models": [
                {
                    "name": "qwen2.5:3b",
                    "modified_at": "",
                    "size": 123,
                }
            ],
            "default_model": "qwen2.5:3b",
            "embedding_model": "nomic-embed-text",
            "recommended_models": [
                {
                    "name": "qwen2.5:3b",
                    "label": "Qwen 2.5 3B",
                    "description": "test",
                    "size_hint": "test",
                    "installed": True,
                }
            ],
        }

        response = self.client.get("/models")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["models"][0]["name"], "qwen2.5:3b")
        self.assertTrue(response.json()["recommended_models"][0]["installed"])

    @patch("app.main.start_model_pull")
    def test_model_pull_endpoint_starts_job(self, mock_start_model_pull):
        mock_start_model_pull.return_value = {
            "job_id": "job-1",
            "model": "qwen2.5:3b",
            "status": "queued",
            "message": "Queued",
            "completed": 0,
            "total": 0,
            "progress": 0,
            "error": "",
        }

        response = self.client.post(
            "/models/pull",
            json={
                "model": "qwen2.5:3b",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["job_id"], "job-1")
        mock_start_model_pull.assert_called_once_with("qwen2.5:3b")

    def test_model_pull_endpoint_rejects_invalid_model_name(self):
        response = self.client.post(
            "/models/pull",
            json={
                "model": "../bad",
            },
        )

        self.assertEqual(response.status_code, 400)

    @patch("app.main.get_model_pull_job")
    def test_model_pull_status_endpoint_returns_job(self, mock_get_model_pull_job):
        mock_get_model_pull_job.return_value = {
            "job_id": "job-1",
            "model": "qwen2.5:3b",
            "status": "running",
            "message": "downloading",
            "completed": 50,
            "total": 100,
            "progress": 50,
            "error": "",
        }

        response = self.client.get("/models/pull/job-1")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["progress"], 50)

    @patch("app.main.get_model_pull_job")
    def test_model_pull_status_endpoint_404_for_missing_job(self, mock_get_model_pull_job):
        mock_get_model_pull_job.return_value = None

        response = self.client.get("/models/pull/missing")

        self.assertEqual(response.status_code, 404)

    @patch("app.main.answer_question")
    def test_ask_endpoint_passes_model_and_general_mode(self, mock_answer_question):
        mock_answer_question.return_value = {
            "answer": "general answer",
            "sources": [],
            "mode": "general",
            "model": "llama3.2:3b",
            "use_rag": False,
        }

        response = self.client.post(
            "/ask",
            json={
                "question": "간단히 설명해줘",
                "mode": "deep",
                "model": "llama3.2:3b",
                "use_rag": False,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["use_rag"])
        mock_answer_question.assert_called_once_with(
            "간단히 설명해줘",
            mode="deep",
            model="llama3.2:3b",
            use_rag=False,
            answer_mode=None,
            chat_history=None,
            project_id="default",
        )

    def test_ask_endpoint_rejects_blank_question(self):
        response = self.client.post(
            "/ask",
            json={
                "question": "  ",
                "use_rag": False,
            },
        )

        self.assertEqual(response.status_code, 400)

    @patch("app.main.start_ask_job")
    def test_ask_job_endpoint_starts_job(self, mock_start_ask_job):
        mock_start_ask_job.return_value = {
            "job_id": "job-1",
            "status": "queued",
            "stage": "queued",
            "message": "질문을 대기열에 넣는 중...",
            "elapsed_seconds": 0,
            "result": None,
            "error": "",
        }

        response = self.client.post(
            "/ask/jobs",
            json={
                "question": "문서 내용을 알려줘",
                "mode": "balanced",
                "model": "qwen2.5:3b",
                "use_rag": True,
                "answer_mode": "hybrid",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["job_id"], "job-1")
        mock_start_ask_job.assert_called_once_with(
            question="문서 내용을 알려줘",
            mode="balanced",
            model="qwen2.5:3b",
            use_rag=True,
            answer_mode="hybrid",
            chat_history=None,
            project_id="default",
        )

    @patch("app.main.get_ask_job")
    def test_ask_job_status_endpoint_returns_job(self, mock_get_ask_job):
        mock_get_ask_job.return_value = {
            "job_id": "job-1",
            "status": "running",
            "stage": "searching_documents",
            "message": "문서에서 관련 내용을 찾는 중...",
            "elapsed_seconds": 3,
            "result": None,
            "error": "",
        }

        response = self.client.get("/ask/jobs/job-1")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["stage"], "searching_documents")

    @patch("app.main.get_ask_job")
    def test_ask_job_status_endpoint_404_for_missing_job(self, mock_get_ask_job):
        mock_get_ask_job.return_value = None

        response = self.client.get("/ask/jobs/missing")

        self.assertEqual(response.status_code, 404)

    @patch("app.main.start_document_upload_job")
    def test_document_upload_endpoint_starts_job(self, mock_start_document_upload_job):
        mock_start_document_upload_job.return_value = {
            "job_id": "doc-job-1",
            "kind": "upload",
            "status": "queued",
            "stage": "queued",
            "message": "Document upload queued.",
            "elapsed_seconds": 0,
            "result": None,
            "error": "",
        }

        response = self.client.post(
            "/documents/upload",
            files={
                "files": (
                    "sample.txt",
                    b"hello document",
                    "text/plain",
                )
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["job_id"], "doc-job-1")
        self.assertEqual(response.json()["kind"], "upload")
        mock_start_document_upload_job.assert_called_once_with(
            ["sample.txt"],
            project_id="default",
        )

    @patch("app.main.start_document_sync_job")
    def test_document_sync_endpoint_starts_job(self, mock_start_document_sync_job):
        mock_start_document_sync_job.return_value = {
            "job_id": "doc-job-2",
            "kind": "sync",
            "status": "queued",
            "stage": "queued",
            "message": "Document sync queued.",
            "elapsed_seconds": 0,
            "result": None,
            "error": "",
        }

        response = self.client.post("/documents/sync")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["job_id"], "doc-job-2")
        self.assertEqual(response.json()["kind"], "sync")
        mock_start_document_sync_job.assert_called_once_with(project_id="default")

    @patch("app.main.get_document_job")
    def test_document_job_status_endpoint_returns_job(self, mock_get_document_job):
        mock_get_document_job.return_value = {
            "job_id": "doc-job-1",
            "kind": "upload",
            "status": "completed",
            "stage": "completed",
            "message": "Done",
            "elapsed_seconds": 1,
            "result": {"document_state": {"documents": []}},
            "error": "",
        }

        response = self.client.get("/documents/jobs/doc-job-1")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "completed")
        self.assertIn("document_state", response.json()["result"])

    @patch("app.main.get_document_job")
    def test_document_job_status_endpoint_404_for_missing_job(self, mock_get_document_job):
        mock_get_document_job.return_value = None

        response = self.client.get("/documents/jobs/missing")

        self.assertEqual(response.status_code, 404)

    @patch("app.main.list_saved_chats")
    @patch("app.main.get_project_context")
    def test_chats_endpoint_returns_saved_chats(
        self,
        mock_get_project_context,
        mock_list_saved_chats,
    ):
        context = SimpleNamespace(chat_store_file="project-chats.json")
        mock_get_project_context.return_value = context
        mock_list_saved_chats.return_value = [
            {
                "id": "chat-1",
                "title": "Test chat",
                "messages": [],
                "created_at": 1,
                "updated_at": 1,
            }
        ]

        response = self.client.get("/chats")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["chats"][0]["id"], "chat-1")
        mock_list_saved_chats.assert_called_once_with(store_file=context.chat_store_file)

    @patch("app.main.create_chat")
    @patch("app.main.get_project_context")
    def test_create_chat_endpoint_creates_chat(
        self,
        mock_get_project_context,
        mock_create_chat,
    ):
        context = SimpleNamespace(chat_store_file="project-chats.json")
        mock_get_project_context.return_value = context
        mock_create_chat.return_value = {
            "id": "chat-1",
            "title": "New chat",
            "messages": [],
            "created_at": 1,
            "updated_at": 1,
        }

        response = self.client.post("/chats", json={"title": "New chat"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["title"], "New chat")
        mock_create_chat.assert_called_once_with(
            "New chat",
            store_file=context.chat_store_file,
        )

    @patch("app.main.update_chat")
    @patch("app.main.get_project_context")
    def test_update_chat_endpoint_updates_chat(
        self,
        mock_get_project_context,
        mock_update_chat,
    ):
        context = SimpleNamespace(chat_store_file="project-chats.json")
        mock_get_project_context.return_value = context
        mock_update_chat.return_value = {
            "id": "chat-1",
            "title": "Saved",
            "messages": [{"role": "user", "content": "hello"}],
            "created_at": 1,
            "updated_at": 2,
        }

        response = self.client.put(
            "/chats/chat-1",
            json={
                "title": "Saved",
                "messages": [{"role": "user", "content": "hello"}],
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["messages"][0]["content"], "hello")
        mock_update_chat.assert_called_once_with(
            "chat-1",
            title="Saved",
            messages=[{"role": "user", "content": "hello"}],
            store_file=context.chat_store_file,
        )

    @patch("app.main.update_chat")
    @patch("app.main.get_project_context")
    def test_update_chat_endpoint_404_for_missing_chat(
        self,
        mock_get_project_context,
        mock_update_chat,
    ):
        mock_get_project_context.return_value = SimpleNamespace(
            chat_store_file="project-chats.json"
        )
        mock_update_chat.return_value = None

        response = self.client.put("/chats/missing", json={"title": "Saved"})

        self.assertEqual(response.status_code, 404)

    @patch("app.main.delete_saved_chat")
    @patch("app.main.get_project_context")
    def test_delete_chat_endpoint_deletes_chat(
        self,
        mock_get_project_context,
        mock_delete_saved_chat,
    ):
        context = SimpleNamespace(chat_store_file="project-chats.json")
        mock_get_project_context.return_value = context
        mock_delete_saved_chat.return_value = True

        response = self.client.delete("/chats/chat-1")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["chat_id"], "chat-1")
        mock_delete_saved_chat.assert_called_once_with(
            "chat-1",
            store_file=context.chat_store_file,
        )

    @patch("app.main.delete_saved_chat")
    @patch("app.main.get_project_context")
    def test_delete_chat_endpoint_404_for_missing_chat(
        self,
        mock_get_project_context,
        mock_delete_saved_chat,
    ):
        mock_get_project_context.return_value = SimpleNamespace(
            chat_store_file="project-chats.json"
        )
        mock_delete_saved_chat.return_value = False

        response = self.client.delete("/chats/missing")

        self.assertEqual(response.status_code, 404)


class JobConcurrencyTests(unittest.TestCase):
    def tearDown(self):
        with ask_jobs.ASK_JOBS_LOCK:
            ask_jobs.ASK_JOBS.clear()

        with document_jobs.DOCUMENT_JOBS_LOCK:
            document_jobs.DOCUMENT_JOBS.clear()

        with model_pull.PULL_JOBS_LOCK:
            model_pull.PULL_JOBS.clear()

    @patch("app.rag.ask_jobs.threading.Thread")
    def test_answer_job_snapshot_includes_project_id(self, mock_thread):
        job = ask_jobs.start_ask_job(
            question="hello",
            mode="fast",
            model="qwen2.5:3b",
            use_rag=False,
            project_id="python-study",
        )

        self.assertEqual(job["project_id"], "python-study")
        mock_thread.return_value.start.assert_called_once()

    def test_answer_jobs_reject_second_active_job(self):
        with ask_jobs.ASK_JOBS_LOCK:
            ask_jobs.ASK_JOBS["active"] = {
                "job_id": "active",
                "status": "running",
                "stage": "generating_answer",
                "message": "Running",
                "created_at": time.time(),
                "result": None,
                "error": "",
            }

        with self.assertRaises(RuntimeError):
            ask_jobs.start_ask_job(
                question="hello",
                mode="fast",
                model="qwen2.5:3b",
                use_rag=False,
            )

    def test_document_jobs_reject_second_active_job(self):
        with document_jobs.DOCUMENT_JOBS_LOCK:
            document_jobs.DOCUMENT_JOBS["active"] = {
                "job_id": "active",
                "kind": "sync",
                "status": "running",
                "stage": "scanning_documents",
                "message": "Running",
                "created_at": time.time(),
                "result": None,
                "error": "",
            }

        with self.assertRaises(RuntimeError):
            document_jobs.ensure_document_job_available()

    def test_model_pull_reuses_same_active_job(self):
        with model_pull.PULL_JOBS_LOCK:
            model_pull.PULL_JOBS["active"] = {
                "job_id": "active",
                "model": "qwen2.5:3b",
                "status": "running",
                "message": "Downloading",
                "completed": 0,
                "total": 0,
                "progress": 0,
                "error": "",
                "created_at": time.time(),
            }

        job = model_pull.start_model_pull("qwen2.5:3b")

        self.assertEqual(job["job_id"], "active")

    def test_model_pull_rejects_different_active_job(self):
        with model_pull.PULL_JOBS_LOCK:
            model_pull.PULL_JOBS["active"] = {
                "job_id": "active",
                "model": "qwen2.5:3b",
                "status": "running",
                "message": "Downloading",
                "completed": 0,
                "total": 0,
                "progress": 0,
                "error": "",
                "created_at": time.time(),
            }

        with self.assertRaises(RuntimeError):
            model_pull.start_model_pull("llama3.2:3b")


class ApiConflictTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(fastapi_app)

    @patch("app.main.start_model_pull")
    def test_model_pull_endpoint_returns_409_when_busy(self, mock_start_model_pull):
        mock_start_model_pull.side_effect = RuntimeError(
            "Another model install is already running."
        )

        response = self.client.post(
            "/models/pull",
            json={"model": "qwen2.5:3b"},
        )

        self.assertEqual(response.status_code, 409)

    @patch("app.main.start_ask_job")
    def test_ask_job_endpoint_returns_409_when_busy(self, mock_start_ask_job):
        mock_start_ask_job.side_effect = RuntimeError(
            "Another answer job is already running."
        )

        response = self.client.post(
            "/ask/jobs",
            json={"question": "hello", "use_rag": False},
        )

        self.assertEqual(response.status_code, 409)

    @patch("app.main.ensure_document_job_available")
    def test_document_upload_endpoint_returns_409_when_busy(self, mock_available):
        mock_available.side_effect = RuntimeError(
            "Another document job is already running."
        )

        response = self.client.post(
            "/documents/upload",
            files={"files": ("sample.txt", b"hello", "text/plain")},
        )

        self.assertEqual(response.status_code, 409)

    @patch("app.main.start_document_sync_job")
    def test_document_sync_endpoint_returns_409_when_busy(self, mock_start_sync):
        mock_start_sync.side_effect = RuntimeError(
            "Another document job is already running."
        )

        response = self.client.post("/documents/sync")

        self.assertEqual(response.status_code, 409)


if __name__ == "__main__":
    unittest.main()
