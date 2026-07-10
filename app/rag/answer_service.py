from app.config import DEFAULT_RETRIEVAL_MODE, NO_ANSWER_TEXT
from app.rag.answer_cleaner import clean_answer
from app.rag.ollama_client import generate_with_ollama
from app.rag.prompt_builder import build_prompt
from app.rag.retrieval_settings import normalize_retrieval_mode
from app.rag.retriever import retrieve


def answer_question(question: str, mode=DEFAULT_RETRIEVAL_MODE):
    mode = normalize_retrieval_mode(mode)

    retrieved_chunks = retrieve(question, mode=mode)

    if not retrieved_chunks:
        return {
            "answer": NO_ANSWER_TEXT,
            "sources": [],
            "mode": mode,
        }

    prompt = build_prompt(question, retrieved_chunks)

    raw_answer = generate_with_ollama(prompt)
    answer = clean_answer(raw_answer)

    if NO_ANSWER_TEXT in answer:
        return {
            "answer": NO_ANSWER_TEXT,
            "sources": [],
            "mode": mode,
        }

    return {
        "answer": answer,
        "sources": retrieved_chunks,
        "mode": mode,
    }
