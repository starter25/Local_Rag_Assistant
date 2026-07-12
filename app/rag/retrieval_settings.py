from app.config import DEFAULT_RETRIEVAL_MODE, RETRIEVAL_MODES


# 알 수 없는 검색 모드가 들어오면 기본 balanced 설정으로 되돌립니다.
def normalize_retrieval_mode(mode: str):
    if mode not in RETRIEVAL_MODES:
        return DEFAULT_RETRIEVAL_MODE

    return mode


# Fast/Balanced/Deep 모드별 candidate 수와 distance threshold를 반환합니다.
def get_retrieval_settings(mode: str):
    return RETRIEVAL_MODES[normalize_retrieval_mode(mode)]
