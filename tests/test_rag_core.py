import unittest

from app.config import NO_ANSWER_TEXT
from app.rag.answer_cleaner import clean_answer
from app.rag.query_rewriter import extract_json, unique_keep_order
from app.rag.retrieval_settings import normalize_retrieval_mode
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


if __name__ == "__main__":
    unittest.main()
