# 검색된 chunk의 distance 값을 요약해 UI에 보여줄 근거 품질 배지를 만듭니다.
def summarize_source_quality(chunks: list[dict] | None) -> dict:
    distances = []

    for chunk in chunks or []:
        try:
            distances.append(float(chunk.get("distance")))
        except (TypeError, ValueError):
            continue

    source_count = len(chunks or [])

    if not distances:
        return {
            "quality": "none",
            "source_count": source_count,
            "best_distance": None,
            "average_distance": None,
            "message": "문서 근거를 찾지 못했어요.",
        }

    best_distance = min(distances)
    average_distance = sum(distances) / len(distances)

    if best_distance <= 0.25 and average_distance <= 0.35:
        quality = "strong"
        message = "질문과 가까운 문서 근거를 찾았어요."
    elif best_distance <= 0.40 and average_distance <= 0.50:
        quality = "medium"
        message = "관련 문서 근거를 찾았지만 일부 확인이 필요해요."
    else:
        quality = "weak"
        message = "문서 근거가 약해요. 답변을 확인해보세요."

    return {
        "quality": quality,
        "source_count": source_count,
        "best_distance": round(best_distance, 4),
        "average_distance": round(average_distance, 4),
        "message": message,
    }
