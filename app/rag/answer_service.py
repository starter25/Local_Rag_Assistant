from app.config import DEFAULT_PROJECT_ID, DEFAULT_RETRIEVAL_MODE, NO_ANSWER_TEXT
from app.rag.answer_cleaner import clean_answer
from app.rag.chat_context import compact_chat_history, get_history_policy
from app.rag.model_profiles import get_general_chat_options, get_general_system_prompt
from app.rag.ollama_client import generate_with_ollama
from app.rag.prompt_builder import build_hybrid_prompt, build_prompt, format_chat_history
from app.rag.retrieval_settings import normalize_retrieval_mode
from app.rag.retriever import retrieve
from app.rag.source_quality import summarize_source_quality


ANSWER_MODE_STRICT_RAG = "strict_rag"
ANSWER_MODE_HYBRID = "hybrid"
ANSWER_MODE_GENERAL = "general"
ANSWER_MODES = {ANSWER_MODE_STRICT_RAG, ANSWER_MODE_HYBRID, ANSWER_MODE_GENERAL}


# 후속 질문이 "그거"처럼 이전 대화를 참조할 때 검색 질문에 최근 맥락을 붙입니다.
def build_retrieval_question(question: str, chat_history: list[dict] | None) -> str:
    history_text = format_chat_history(compact_chat_history(chat_history, policy="retrieval"))

    if not history_text:
        return question

    return f"""
Previous conversation for resolving follow-up references:
{history_text}

Current question:
{question}
""".strip()


# 프론트에서 넘어온 답변 모드를 백엔드가 사용하는 표준 모드로 정규화합니다.
def normalize_answer_mode(answer_mode: str | None, use_rag: bool = True) -> str:
    answer_mode = (answer_mode or "").strip().lower()

    if answer_mode in ANSWER_MODES:
        return answer_mode

    return ANSWER_MODE_STRICT_RAG if use_rag else ANSWER_MODE_GENERAL


# 문서 검색 없이 선택한 Ollama 모델에 바로 질문하는 일반 AI 경로입니다.
def answer_general_question(
    question: str,
    model: str | None = None,
    chat_history: list[dict] | None = None,
    progress=None,
    project_id: str = DEFAULT_PROJECT_ID,
):
    if progress:
        progress("preparing_question", "질문을 준비하는 중...")

    if progress:
        progress("generating_answer", "선택한 모델이 답변을 생성하는 중...")

    raw_answer = generate_with_ollama(
        question,
        model=model,
        system_prompt=get_general_system_prompt(model),
        options=get_general_chat_options(model),
        chat_history=compact_chat_history(chat_history, policy="general"),
    )
    answer = clean_answer(raw_answer)

    return {
        "answer": answer,
        "sources": [],
        "mode": "general",
        "model": model,
        "use_rag": False,
        "answer_mode": ANSWER_MODE_GENERAL,
        "source_quality": None,
        "project_id": project_id,
    }


# 질문 모드에 따라 General, strict RAG, Hybrid RAG 답변 경로를 선택하는 핵심 진입점입니다.
def answer_question(
    question: str,
    mode=DEFAULT_RETRIEVAL_MODE,
    model: str | None = None,
    use_rag: bool = True,
    answer_mode: str | None = None,
    chat_history: list[dict] | None = None,
    progress=None,
    project_id: str = DEFAULT_PROJECT_ID,
):
    resolved_answer_mode = normalize_answer_mode(answer_mode, use_rag=use_rag)
    history_policy = get_history_policy(use_rag=use_rag, answer_mode=resolved_answer_mode)
    compacted_history = compact_chat_history(chat_history, policy=history_policy)

    if resolved_answer_mode == ANSWER_MODE_GENERAL:
        return answer_general_question(
            question,
            model=model,
            chat_history=compacted_history,
            progress=progress,
            project_id=project_id,
        )

    if progress:
        if resolved_answer_mode == ANSWER_MODE_HYBRID:
            progress("preparing_question", "질문과 조언 방향을 정리하는 중...")
        else:
            progress("preparing_question", "질문을 정리하는 중...")

    mode = normalize_retrieval_mode(mode)

    if progress:
        progress("searching_documents", "문서에서 관련 내용을 찾는 중...")

    retrieval_question = build_retrieval_question(question, compacted_history)
    retrieved_chunks = retrieve(
        retrieval_question,
        mode=mode,
        model=model,
        progress=progress,
        project_id=project_id,
    )

    if not retrieved_chunks:
        if progress:
            progress("no_answer", "문서에서 답을 찾지 못했어.")

        return {
            "answer": NO_ANSWER_TEXT,
            "sources": [],
            "mode": mode,
            "model": model,
            "use_rag": True,
            "answer_mode": resolved_answer_mode,
            "source_quality": summarize_source_quality([]),
            "project_id": project_id,
        }

    source_quality = summarize_source_quality(retrieved_chunks)

    if resolved_answer_mode == ANSWER_MODE_HYBRID:
        prompt = build_hybrid_prompt(
            question,
            retrieved_chunks,
            model=model,
            chat_history=compacted_history,
        )
        generation_options = get_general_chat_options(model)
    else:
        prompt = build_prompt(
            question,
            retrieved_chunks,
            model=model,
            chat_history=compacted_history,
        )
        generation_options = None

    if progress:
        if resolved_answer_mode == ANSWER_MODE_HYBRID:
            progress("generating_answer", "문서 근거와 AI 해석을 함께 정리하는 중...")
        else:
            progress("generating_answer", "선택한 모델이 문서 근거로 답변을 생성하는 중...")

    raw_answer = generate_with_ollama(
        prompt,
        model=model,
        options=generation_options,
    )
    answer = clean_answer(raw_answer)

    if NO_ANSWER_TEXT in answer:
        return {
            "answer": NO_ANSWER_TEXT,
            "sources": [],
            "mode": mode,
            "model": model,
            "use_rag": True,
            "answer_mode": resolved_answer_mode,
            "source_quality": summarize_source_quality([]),
            "project_id": project_id,
        }

    return {
        "answer": answer,
        "sources": retrieved_chunks,
        "mode": mode,
        "model": model,
        "use_rag": True,
        "answer_mode": resolved_answer_mode,
        "source_quality": source_quality,
        "project_id": project_id,
    }
