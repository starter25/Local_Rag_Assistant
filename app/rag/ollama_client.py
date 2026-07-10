import requests

from app.config import CHAT_MODEL, EMBED_MODEL, OLLAMA_URL, QUERY_REWRITE_MODEL


def check_ollama():
    try:
        response = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        response.raise_for_status()
    except Exception as e:
        raise RuntimeError(
            "Ollama가 실행 중인지 확인해줘. "
            "PowerShell에서 `ollama list`가 되는지 먼저 확인하면 돼."
        ) from e


def get_embedding(text: str):
    """
    Ollama embedding API 호출.
    최신 /api/embed을 먼저 시도하고,
    안 되면 구형 /api/embeddings로 fallback.
    """

    try:
        response = requests.post(
            f"{OLLAMA_URL}/api/embed",
            json={
                "model": EMBED_MODEL,
                "input": text,
            },
            timeout=60,
        )

        if response.status_code == 200:
            data = response.json()
            embeddings = data.get("embeddings")

            if isinstance(embeddings, list) and len(embeddings) > 0:
                return embeddings[0]

    except Exception:
        pass

    response = requests.post(
        f"{OLLAMA_URL}/api/embeddings",
        json={
            "model": EMBED_MODEL,
            "prompt": text,
        },
        timeout=60,
    )
    response.raise_for_status()

    data = response.json()
    return data["embedding"]


def get_embeddings(texts):
    texts = [text for text in texts if text]

    if not texts:
        return []

    try:
        response = requests.post(
            f"{OLLAMA_URL}/api/embed",
            json={
                "model": EMBED_MODEL,
                "input": texts,
            },
            timeout=120,
        )

        if response.status_code == 200:
            data = response.json()
            embeddings = data.get("embeddings")

            if isinstance(embeddings, list) and len(embeddings) == len(texts):
                return embeddings

    except Exception:
        pass

    return [get_embedding(text) for text in texts]


def generate_with_ollama(prompt: str):
    response = requests.post(
        f"{OLLAMA_URL}/api/chat",
        json={
            "model": CHAT_MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "너는 사용자가 제공한 참고 자료를 바탕으로 답변하는 한국어 AI 어시스턴트다. "
                        "답변은 짧고 명확하게 작성한다."
                    ),
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            "stream": False,
            "keep_alive": "10m",
            "options": {
                "temperature": 0.0,
                "num_ctx": 2048,
                "num_predict": 300,
            },
        },
        timeout=180,
    )

    response.raise_for_status()
    data = response.json()

    return data.get("message", {}).get("content", "")


def rewrite_query_with_ollama(question: str):
    response = requests.post(
        f"{OLLAMA_URL}/api/chat",
        json={
            "model": QUERY_REWRITE_MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "너는 RAG 검색어 재작성기다. "
                        "사용자 질문을 문서 검색에 유리한 한국어 검색 질문들로 바꿔라. "
                        "답변하지 말고 JSON만 출력해라."
                    ),
                },
                {
                    "role": "user",
                    "content": f"""
사용자 질문:
{question}

작업:
사용자 질문을 문서 검색에 적합한 한국어 검색 질문 2~4개로 바꿔라.

규칙:
- 원래 질문의 의도를 유지해라.
- 질문을 답변하지 마라.
- 새로운 사실을 추가하지 마라.
- 추천, 제안, 판단 요청이 아닌 질문을 추천 질문으로 바꾸지 마라.
- 대명사나 지시어는 문서 검색에 더 명확한 표현으로 바꿔라.
- 너무 짧거나 모호한 질문은 검색 가능한 구체적인 질문으로 바꿔라.
- 반드시 JSON만 출력해라.

출력 형식:
{{"queries":["검색 질문 1","검색 질문 2","검색 질문 3"]}}
""".strip(),
                },
            ],
            "stream": False,
            "keep_alive": "10m",
            "options": {
                "temperature": 0.0,
                "num_ctx": 1024,
                "num_predict": 160,
            },
        },
        timeout=60,
    )

    response.raise_for_status()
    data = response.json()

    return data.get("message", {}).get("content", "")
