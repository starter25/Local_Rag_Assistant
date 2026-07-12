import json
import threading
import time
import uuid
from pathlib import Path

from app.config import CHAT_DIR, CHAT_STORE_FILE


CHAT_STORE_LOCK = threading.Lock()


# 저장 파일에 기록할 Unix timestamp를 통일합니다.
def _now() -> float:
    return time.time()


# 채팅 저장 파일이 없거나 깨졌을 때 사용할 기본 구조입니다.
def _empty_store() -> dict:
    return {
        "version": 1,
        "chats": [],
    }


# storage/chats 폴더가 없으면 생성합니다.
def _resolve_store_file(store_file: Path | None = None) -> Path:
    return Path(store_file) if store_file else CHAT_STORE_FILE


def _ensure_store_dir(store_file: Path | None = None):
    if store_file:
        Path(store_file).parent.mkdir(parents=True, exist_ok=True)
        return

    CHAT_DIR.mkdir(parents=True, exist_ok=True)


# JSON 저장소를 읽고 형식이 이상하면 빈 저장소로 복구합니다.
def _read_store(store_file: Path | None = None) -> dict:
    resolved_store_file = _resolve_store_file(store_file)
    _ensure_store_dir(resolved_store_file)

    if not resolved_store_file.exists():
        return _empty_store()

    try:
        with resolved_store_file.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except Exception:
        return _empty_store()

    if not isinstance(data, dict):
        return _empty_store()

    chats = data.get("chats")

    if not isinstance(chats, list):
        data["chats"] = []

    data.setdefault("version", 1)

    return data


# 임시 파일에 쓴 뒤 교체해 저장 중 파일이 깨질 가능성을 줄입니다.
def _write_store(data: dict, store_file: Path | None = None):
    resolved_store_file = _resolve_store_file(store_file)
    _ensure_store_dir(resolved_store_file)
    temp_path = Path(str(resolved_store_file) + ".tmp")

    with temp_path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)

    temp_path.replace(resolved_store_file)


# 오래된 저장 데이터나 누락 필드를 현재 앱이 기대하는 채팅 구조로 맞춥니다.
def _normalize_chat(chat: dict) -> dict:
    return {
        "id": str(chat.get("id") or uuid.uuid4()),
        "title": str(chat.get("title") or "새 채팅"),
        "messages": chat.get("messages") if isinstance(chat.get("messages"), list) else [],
        "created_at": float(chat.get("created_at") or _now()),
        "updated_at": float(chat.get("updated_at") or _now()),
    }


# 최근 수정된 채팅이 먼저 보이도록 정렬해서 반환합니다.
def list_chats(store_file: Path | None = None) -> list[dict]:
    with CHAT_STORE_LOCK:
        store = _read_store(store_file)
        chats = [_normalize_chat(chat) for chat in store["chats"]]

    chats.sort(key=lambda chat: chat["updated_at"], reverse=True)

    return chats


# 새 대화방을 만들고 빈 messages 배열로 저장합니다.
def create_chat(title: str | None = None, store_file: Path | None = None) -> dict:
    now = _now()
    chat = {
        "id": str(uuid.uuid4()),
        "title": (title or "새 채팅").strip() or "새 채팅",
        "messages": [],
        "created_at": now,
        "updated_at": now,
    }

    with CHAT_STORE_LOCK:
        store = _read_store(store_file)
        store["chats"].append(chat)
        _write_store(store, store_file)

    return chat


# 채팅 제목이나 메시지 목록을 저장하고 updated_at을 갱신합니다.
def update_chat(
    chat_id: str,
    title: str | None = None,
    messages: list | None = None,
    store_file: Path | None = None,
) -> dict | None:
    with CHAT_STORE_LOCK:
        store = _read_store(store_file)

        for index, chat in enumerate(store["chats"]):
            normalized = _normalize_chat(chat)

            if normalized["id"] != chat_id:
                continue

            if title is not None:
                normalized["title"] = title.strip() or "새 채팅"

            if messages is not None:
                normalized["messages"] = messages if isinstance(messages, list) else []

            normalized["updated_at"] = _now()
            store["chats"][index] = normalized
            _write_store(store, store_file)

            return normalized

    return None


# 채팅 id로 저장소에서 대화를 제거합니다.
def delete_chat(chat_id: str, store_file: Path | None = None) -> bool:
    with CHAT_STORE_LOCK:
        store = _read_store(store_file)
        original_count = len(store["chats"])
        store["chats"] = [
            chat for chat in store["chats"] if _normalize_chat(chat)["id"] != chat_id
        ]

        if len(store["chats"]) == original_count:
            return False

        _write_store(store, store_file)

    return True
