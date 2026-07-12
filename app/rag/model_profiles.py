from app.config import CHAT_MODEL


BASE_CHAT_OPTIONS = {
    "temperature": 0.0,
    "num_ctx": 2048,
    "num_predict": 300,
}


GENERAL_CHAT_OPTIONS = {
    "temperature": 0.2,
    "num_ctx": 4096,
    "num_predict": 900,
}


DEFAULT_SYSTEM_PROMPT = (
    "You are a Korean RAG assistant. Answer only from the provided reference "
    "material. Be concise, factual, and clear. If the reference material does "
    "not contain the answer, say that the document does not contain the answer."
)

GENERAL_SYSTEM_PROMPT = (
    "You are a helpful local AI assistant. Answer in Korean by default unless "
    "the user asks for another language. You may answer general questions, help "
    "with coding, explain concepts, and reason normally. Be clear, practical, "
    "and honest about uncertainty."
)


RECOMMENDED_MODELS = [
    {
        "name": "qwen2.5:3b",
        "label": "Qwen 2.5 3B",
        "description": "균형 잡힌 한국어 답변과 일반 질문에 적합합니다.",
        "size_hint": "약 2GB",
    },
    {
        "name": "llama3.2:3b",
        "label": "Llama 3.2 3B",
        "description": "가볍고 빠른 일반 답변에 적합합니다.",
        "size_hint": "약 2GB",
    },
    {
        "name": "gemma3:4b",
        "label": "Gemma 3 4B",
        "description": "보수적인 문서 기반 답변과 요약에 적합합니다.",
        "size_hint": "약 3GB",
    },
    {
        "name": "deepseek-r1:7b",
        "label": "DeepSeek R1 7B",
        "description": "추론형 질문에 강하지만 응답 전 정리가 더 필요할 수 있습니다.",
        "size_hint": "약 5GB",
    },
]


MODEL_PROFILES = [
    {
        "patterns": ("deepseek",),
        "system_prompt": (
            "You are a Korean RAG assistant. Use only the provided reference "
            "material. Do not reveal hidden reasoning or thinking steps. Return "
            "only the final answer in Korean. If the answer is not supported by "
            "the references, say that the document does not contain the answer."
        ),
        "prompt_guidance": (
            "Do not output <think> blocks or reasoning traces. Provide only the "
            "final Korean answer grounded in the references."
        ),
        "options": {
            "num_predict": 350,
        },
    },
    {
        "patterns": ("qwen",),
        "system_prompt": (
            "You are a Korean document QA assistant. Follow the user's Korean "
            "instructions carefully. Use only the references and do not infer "
            "unsupported facts."
        ),
        "prompt_guidance": (
            "Keep the answer in Korean, direct, and strictly tied to the cited "
            "document chunks."
        ),
        "options": {},
    },
    {
        "patterns": ("llama",),
        "system_prompt": (
            "You are a concise Korean RAG assistant. Answer directly from the "
            "references. Do not speculate."
        ),
        "prompt_guidance": (
            "Prefer short, direct Korean sentences. Do not add information that "
            "is not present in the references."
        ),
        "options": {
            "num_predict": 260,
        },
    },
    {
        "patterns": ("gemma",),
        "system_prompt": (
            "You are a Korean RAG assistant. Be conservative: if the references "
            "are ambiguous or incomplete, say that the document does not contain "
            "enough information."
        ),
        "prompt_guidance": (
            "If the reference chunks do not clearly support the answer, refuse "
            "with the configured no-answer sentence."
        ),
        "options": {},
    },
]


# 빈 모델 선택은 환경변수/기본 설정의 CHAT_MODEL로 대체합니다.
def normalize_chat_model(model: str | None) -> str:
    model = (model or "").strip()

    if model:
        return model

    return CHAT_MODEL


# 모델 이름 패턴에 맞는 system prompt와 옵션 프로필을 찾습니다.
def get_model_profile(model: str | None):
    model_name = normalize_chat_model(model).lower()

    for profile in MODEL_PROFILES:
        if any(pattern in model_name for pattern in profile["patterns"]):
            return profile

    return {
        "patterns": (),
        "system_prompt": DEFAULT_SYSTEM_PROMPT,
        "prompt_guidance": "",
        "options": {},
    }


# RAG 답변에 사용할 모델별 system prompt를 반환합니다.
def get_system_prompt(model: str | None) -> str:
    return get_model_profile(model)["system_prompt"]


# 일반 AI 모드에서는 문서 제한이 없는 별도 system prompt를 사용합니다.
def get_general_system_prompt(model: str | None) -> str:
    model_name = normalize_chat_model(model).lower()

    if "deepseek" in model_name:
        return (
            GENERAL_SYSTEM_PROMPT
            + " Do not reveal hidden reasoning or <think> blocks. Return only the final answer."
        )

    return GENERAL_SYSTEM_PROMPT


# 프롬프트 본문에 추가할 모델별 주의사항을 반환합니다.
def get_prompt_guidance(model: str | None) -> str:
    return get_model_profile(model).get("prompt_guidance", "")


# strict RAG 모드의 생성 옵션을 모델 프로필과 합칩니다.
def get_chat_options(model: str | None) -> dict:
    options = dict(BASE_CHAT_OPTIONS)
    options.update(get_model_profile(model).get("options", {}))
    return options


# General/Hybrid처럼 답변이 길어질 수 있는 모드의 생성 옵션입니다.
def get_general_chat_options(model: str | None) -> dict:
    options = dict(GENERAL_CHAT_OPTIONS)

    if "deepseek" in normalize_chat_model(model).lower():
        options["num_predict"] = 700

    return options
