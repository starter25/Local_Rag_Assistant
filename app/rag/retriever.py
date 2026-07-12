from app.config import DEFAULT_PROJECT_ID, DEFAULT_RETRIEVAL_MODE
from app.project_store import get_project_context
from app.rag.ollama_client import check_ollama, get_embedding
from app.rag.query_rewriter import rewrite_query_variants
from app.rag.retrieval_settings import get_retrieval_settings, normalize_retrieval_mode
from app.rag.vector_db import get_collection


# 질문을 여러 검색어로 확장하고 ChromaDB에서 관련 chunk를 찾아 최종 근거 목록을 반환합니다.
def retrieve(
    question: str,
    mode=DEFAULT_RETRIEVAL_MODE,
    model: str | None = None,
    progress=None,
    project_id: str = DEFAULT_PROJECT_ID,
):
    context = get_project_context(project_id)
    collection = get_collection(reset=False, chroma_dir=context.chroma_dir)

    db_count = collection.count()

    if db_count == 0:
        return []

    check_ollama()

    mode = normalize_retrieval_mode(mode)
    settings = get_retrieval_settings(mode)

    candidate_k = settings["candidate_k"]
    final_k = settings["final_k"]
    distance_threshold = settings["distance_threshold"]
    query_variant_k = settings.get("query_variant_k", 1)

    n_results = min(candidate_k, db_count)

    if progress:
        progress("rewriting_question", "질문을 검색하기 좋게 정리하는 중...")

    query_variants = rewrite_query_variants(
        question,
        max_variants=query_variant_k,
        model=model,
    )

    merged = {}

    # 여러 query variant에서 같은 chunk가 잡히면 가장 가까운 distance만 남깁니다.
    for query in query_variants:
        if progress:
            progress("embedding_question", "질문을 벡터로 변환하는 중...")

        question_embedding = get_embedding(query)

        if progress:
            progress("searching_vectors", "문서 벡터를 검색하는 중...")

        results = collection.query(
            query_embeddings=[question_embedding],
            n_results=n_results,
            include=["documents", "metadatas", "distances"],
        )

        docs = results["documents"][0]
        metas = results["metadatas"][0]
        distances = results["distances"][0]

        for doc, meta, distance in zip(docs, metas, distances):
            if distance > distance_threshold:
                continue

            source = meta.get("source", "")
            page = meta.get("page", "")
            chunk_index = meta.get("chunk_index", "")

            key = f"{source}-{page}-{chunk_index}"

            item = {
                "text": doc,
                "source": source,
                "page": page,
                "chunk_index": chunk_index,
                "distance": distance,
                "matched_query": query,
            }

            if key not in merged or distance < merged[key]["distance"]:
                merged[key] = item

    candidates = list(merged.values())
    candidates.sort(key=lambda item: item["distance"])

    return candidates[:final_k]
