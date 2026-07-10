from app.config import DEFAULT_RETRIEVAL_MODE, RETRIEVAL_MODES


def normalize_retrieval_mode(mode: str):
    if mode not in RETRIEVAL_MODES:
        return DEFAULT_RETRIEVAL_MODE

    return mode


def get_retrieval_settings(mode: str):
    return RETRIEVAL_MODES[normalize_retrieval_mode(mode)]
