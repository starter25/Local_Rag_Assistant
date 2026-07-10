from app.config import DEFAULT_RETRIEVAL_MODE
from app.rag.ollama_client import check_ollama, get_embedding
from app.rag.query_rewriter import rewrite_query_variants
from app.rag.retrieval_settings import get_retrieval_settings, normalize_retrieval_mode
from app.rag.vector_db import get_collection


def retrieve(question: str, mode=DEFAULT_RETRIEVAL_MODE):
    collection = get_collection(reset=False)

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

    query_variants = rewrite_query_variants(
        question,
        max_variants=query_variant_k,
    )

    merged = {}

    for query in query_variants:
        question_embedding = get_embedding(query)

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
