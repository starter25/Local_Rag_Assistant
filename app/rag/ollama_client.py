import requests

from app.config import CHAT_MODEL, EMBED_MODEL, OLLAMA_URL, QUERY_REWRITE_MODEL
from app.rag.model_profiles import (
    RECOMMENDED_MODELS,
    get_chat_options,
    get_system_prompt,
    normalize_chat_model,
)


# Ollama 서버가 살아 있는지 빠르게 확인합니다.
def _model_base_name(name: str) -> str:
    return str(name or "").split(":", 1)[0].lower()


def _is_chat_model_name(name: str) -> bool:
    base_name = _model_base_name(name)
    embed_base_name = _model_base_name(EMBED_MODEL)

    if not base_name:
        return False

    if base_name == embed_base_name:
        return False

    return "embed" not in base_name and "embedding" not in base_name


def check_ollama():
    try:
        response = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        response.raise_for_status()
    except Exception as e:
        raise RuntimeError(
            "Ollama is not running or is not reachable. "
            "Run `ollama list` in PowerShell first."
        ) from e


# 설치된 Ollama 모델과 앱이 추천하는 모델 설치 상태를 함께 반환합니다.
def list_ollama_models():
    response = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
    response.raise_for_status()

    models = []

    for item in response.json().get("models", []):
        name = item.get("name") or item.get("model")

        if not name:
            continue

        if not _is_chat_model_name(name):
            continue

        models.append(
            {
                "name": name,
                "modified_at": item.get("modified_at", ""),
                "size": item.get("size", 0),
            }
        )

    models.sort(key=lambda item: item["name"].lower())
    installed_names = {item["name"] for item in models}
    recommended_models = []

    for model in RECOMMENDED_MODELS:
        recommended_models.append(
            {
                **model,
                "installed": model["name"] in installed_names,
            }
        )

    return {
        "models": models,
        "default_model": CHAT_MODEL,
        "embedding_model": EMBED_MODEL,
        "recommended_models": recommended_models,
    }


# 단일 텍스트를 embedding 벡터로 변환합니다.
def get_embedding(text: str):
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


# 여러 chunk embedding을 한 번에 시도하고, 실패하면 단건 호출로 fallback합니다.
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


# Ollama chat API로 최종 답변을 생성합니다.
def generate_with_ollama(
    prompt: str,
    model: str | None = None,
    system_prompt: str | None = None,
    options: dict | None = None,
    chat_history: list[dict] | None = None,
):
    selected_model = normalize_chat_model(model)
    system_prompt = system_prompt or get_system_prompt(selected_model)
    chat_options = get_chat_options(selected_model) if options is None else options
    messages = [
        {
            "role": "system",
            "content": system_prompt,
        }
    ]

    for item in chat_history or []:
        role = item.get("role")
        content = str(item.get("content") or "").strip()

        if role not in {"user", "assistant"} or not content:
            continue

        messages.append(
            {
                "role": role,
                "content": content[:4000],
            }
        )

    messages.append(
        {
            "role": "user",
            "content": prompt,
        }
    )

    response = requests.post(
        f"{OLLAMA_URL}/api/chat",
        json={
            "model": selected_model,
            "messages": messages,
            "stream": False,
            "keep_alive": "10m",
            "options": chat_options,
        },
        timeout=180,
    )

    response.raise_for_status()
    data = response.json()

    return data.get("message", {}).get("content", "")


# RAG 검색 품질을 높이기 위해 사용자 질문을 검색어 후보 JSON으로 재작성합니다.
def rewrite_query_with_ollama(question: str, model: str | None = None):
    selected_model = normalize_chat_model(model) if model else QUERY_REWRITE_MODEL

    response = requests.post(
        f"{OLLAMA_URL}/api/chat",
        json={
            "model": selected_model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You rewrite Korean RAG search queries. Return JSON only. "
                        "Do not answer the user question."
                    ),
                },
                {
                    "role": "user",
                    "content": f"""
User question:
{question}

Task:
Rewrite the user question into 2 to 4 Korean search queries suitable for document retrieval.

Rules:
- Preserve the user's original intent.
- Do not answer the question.
- Do not add unsupported facts.
- Do not turn the question into a recommendation request.
- Prefer concrete search phrases that are likely to appear in documents.
- Return JSON only.

Output format:
{{"queries":["search query 1","search query 2","search query 3"]}}
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
