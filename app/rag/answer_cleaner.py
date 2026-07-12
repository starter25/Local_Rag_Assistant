import re


# DeepSeek 계열처럼 reasoning 흔적을 내보내는 모델의 답변을 최종 답변만 남기도록 정리합니다.
def clean_answer(text: str):
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    text = text.replace("Thinking...", "").replace("...done thinking.", "").strip()

    # 모델이 지시를 잘 따른 경우: 최종답변 뒤만 사용
    if "최종답변:" in text:
        text = text.split("최종답변:", 1)[1].strip()

    # 혹시 영어 추론 후 답변 형식으로 나온 경우를 보정
    if "정답은" in text and "Okay" in text:
        text = text[text.rfind("정답은") :].strip()

    return text.strip()
