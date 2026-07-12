import json
import re

from app.config import ENABLE_QUERY_REWRITE


# LLM이 같은 검색어를 여러 번 내도 순서를 유지하면서 중복을 제거합니다.
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


# 모델 응답에 설명이 섞여도 첫 JSON 객체만 최대한 추출합니다.
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


# 원 질문과 LLM이 만든 검색어 변형을 합쳐 벡터 검색 후보를 만듭니다.
def rewrite_query_variants(question: str, max_variants=3, model: str | None = None):
    question = question.strip()

    if not question:
        return []

    variants = [question]

    if not ENABLE_QUERY_REWRITE:
        return variants[:max_variants]

    try:
        from app.rag.ollama_client import rewrite_query_with_ollama

        raw = rewrite_query_with_ollama(question, model=model)
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
