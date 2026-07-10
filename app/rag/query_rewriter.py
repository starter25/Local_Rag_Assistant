import json
import re

from app.config import ENABLE_QUERY_REWRITE


def unique_keep_order(items):
    seen = set()
    result = []

    for item in items:
        item = str(item).strip()

        if not item:
            continue

        if item in seen:
            continue

        seen.add(item)
        result.append(item)

    return result


def extract_json(text: str):
    """
    모델이 JSON 앞뒤에 불필요한 말을 붙였을 때도 최대한 JSON 부분만 뽑는다.
    """

    text = text.strip()

    try:
        return json.loads(text)
    except Exception:
        pass

    match = re.search(r"\{.*\}", text, flags=re.DOTALL)

    if not match:
        return None

    try:
        return json.loads(match.group(0))
    except Exception:
        return None


def rewrite_query_variants(question: str, max_variants=3):
    question = question.strip()

    if not question:
        return []

    variants = [question]

    if not ENABLE_QUERY_REWRITE:
        return variants[:max_variants]

    try:
        from app.rag.ollama_client import rewrite_query_with_ollama

        raw = rewrite_query_with_ollama(question)
        data = extract_json(raw)

        if isinstance(data, dict):
            queries = data.get("queries", [])

            if isinstance(queries, list):
                variants.extend(queries)

    except Exception:
        # query rewrite 실패해도 원래 질문으로 검색은 가능해야 함
        pass

    variants = unique_keep_order(variants)

    return variants[:max_variants]
