HISTORY_POLICIES = {
    "retrieval": {
        "max_messages": 4,
        "max_chars": 2400,
        "max_single_message_chars": 800,
    },
    "rag": {
        "max_messages": 6,
        "max_chars": 3600,
        "max_single_message_chars": 1000,
    },
    "hybrid": {
        "max_messages": 8,
        "max_chars": 5000,
        "max_single_message_chars": 1200,
    },
    "general": {
        "max_messages": 10,
        "max_chars": 7000,
        "max_single_message_chars": 1500,
    },
}


# 답변 모드에 따라 모델에 넘길 이전 대화 길이 정책을 선택합니다.
def get_history_policy(use_rag: bool = True, answer_mode: str | None = None) -> str:
    answer_mode = (answer_mode or "").strip().lower()

    if not use_rag or answer_mode == "general":
        return "general"

    if answer_mode == "hybrid":
        return "hybrid"

    return "rag"


# 저장된 전체 대화 중 모델 입력에 적합한 최근 메시지만 남깁니다.
def compact_chat_history(
    chat_history: list[dict] | None,
    policy: str = "rag",
    limit: int | None = None,
) -> list[dict]:
    settings = HISTORY_POLICIES.get(policy, HISTORY_POLICIES["rag"])
    max_messages = limit or settings["max_messages"]
    max_chars = settings["max_chars"]
    max_single_message_chars = settings["max_single_message_chars"]
    compacted = []
    used_chars = 0

    for item in reversed(chat_history or []):
        if len(compacted) >= max_messages:
            break

        if not isinstance(item, dict):
            continue

        role = item.get("role")
        content = str(item.get("content") or "").strip()

        if role not in {"user", "assistant"} or not content:
            continue

        remaining_chars = max_chars - used_chars

        if remaining_chars <= 0:
            break

        content = content[: min(max_single_message_chars, remaining_chars)]

        compacted.append(
            {
                "role": role,
                "content": content,
            }
        )
        used_chars += len(content)

    compacted.reverse()
    return compacted
