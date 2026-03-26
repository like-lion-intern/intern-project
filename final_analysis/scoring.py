from __future__ import annotations


LABEL_BASE_SCORE = {"strong": 4.5, "neutral": 3.0, "weak": 2.5}
LABEL_ADJUSTMENT = {"strong": +1.0, "neutral": 0.0, "weak": -1.2}

ITEM_WEIGHT = {
    "불필요한 반복 표현": 3,
    "발화 완결성": 2,
    "언어 일관성": 2,
    "학습 목표 안내": 2,
    "전날 복습 연계": 2,
    "설명 순서": 1,
    "핵심 내용 강조": 2,
    "마무리 요약": 0.5,
    "개념 정의": 2,
    "비유 및 예시 활용": 2,
    "선행 개념 확인": 1,
    "발화 속도 적절성": 3,
    "예시 적절성": 3,
    "실습 연계": 3,
    "오류 대응": 2,
    "이해 확인 질문": 3,
    "참여 유도": 3,
    "질문 응답 충분성": 2,
}

CATEGORY_ITEMS = {
    "언어 표현 품질": ["불필요한 반복 표현", "발화 완결성", "언어 일관성"],
    "강의 도입 및 구조": ["학습 목표 안내", "전날 복습 연계", "설명 순서", "핵심 내용 강조", "마무리 요약"],
    "개념 설명 명확성": ["개념 정의", "비유 및 예시 활용", "선행 개념 확인", "발화 속도 적절성"],
    "예시 및 실습 연계": ["예시 적절성", "실습 연계", "오류 대응"],
    "수강생 상호작용": ["이해 확인 질문", "참여 유도", "질문 응답 충분성"],
}

# item별 heuristic vs LLM 비중
# 수치 측정 가능 0.5:0.5 / 애매 0.3:0.7 / 발화 맥락 핵심 0.2:0.8
ITEM_HEURISTIC_WEIGHT = {
    "불필요한 반복 표현": 0.5,
    "발화 속도 적절성":   0.5,
    "발화 완결성":        0.3,
    "언어 일관성":        0.3,
    "학습 목표 안내":     0.3,
    "전날 복습 연계":     0.3,
    "설명 순서":          0.3,
    "개념 정의":          0.3,
    "선행 개념 확인":     0.3,
    "이해 확인 질문":     0.3,
    "핵심 내용 강조":     0.2,
    "마무리 요약":        0.2,
    "비유 및 예시 활용":  0.2,
    "예시 적절성":        0.2,
    "실습 연계":          0.2,
    "오류 대응":          0.2,
    "참여 유도":          0.2,
    "질문 응답 충분성":   0.2,
}


def _parse_ts_to_seconds(ts_str: str) -> float:
    """
    "HH:MM:SS" 형식 → 초 변환. 파싱 실패 시 0.0 반환.
    """
    try:
        parts = ts_str.strip().split(":")
        h, m, s = int(parts[0]), int(parts[1]), int(parts[2])
        return h * 3600 + m * 60 + s
    except Exception:
        return 0.0


def calc_final_score(heuristic_score: float, label: str, confidence: float, item_name: str = "") -> float:
    label_base = LABEL_BASE_SCORE.get(label, 3.0)
    label_adj = LABEL_ADJUSTMENT.get(label, 0.0)
    llm_score = label_base + label_adj * confidence
    llm_score = max(1.0, min(5.0, llm_score))
    h_weight = ITEM_HEURISTIC_WEIGHT.get(item_name, 0.4)
    l_weight = round(1.0 - h_weight, 1)
    final = heuristic_score * h_weight + llm_score * l_weight
    return round(max(1.0, min(5.0, final)), 2)


def make_adjustment_reason(heuristic_score: float, label: str, confidence: float, final_score: float) -> str:
    return f"heuristic {heuristic_score} → label={label}(conf={round(confidence, 2)}) → final {final_score}"


def calc_weighted_avg(items_scored: list, score_key: str) -> float:
    total_weight = sum(ITEM_WEIGHT[item["item_name"]] for item in items_scored)
    weighted_sum = sum(item[score_key] * ITEM_WEIGHT[item["item_name"]] for item in items_scored)
    return round(weighted_sum / total_weight, 2) if total_weight > 0 else 3.0


def run_scoring(
    features_data: dict,
    signals_output: dict,
    analysis_result: dict,
    chunks: list,
) -> dict:
    first_start_ts = chunks[0]["start_ts"] if chunks else "00:00:00"
    last_end_ts = chunks[-1]["end_ts"] if chunks else "00:00:00"
    start_sec = _parse_ts_to_seconds(first_start_ts)
    end_sec = _parse_ts_to_seconds(last_end_ts)
    duration_min = max((end_sec - start_sec) / 60.0, 1.0)
    token_count = features_data.get("features", {}).get("token_count", 0)
    words_per_minute = token_count / duration_min

    features = features_data.get("features", {})
    ls = signals_output.get("lecture_signals", {})

    heuristic_scores = {}

    discourse_markers = features.get("discourse_marker_per_1k_tokens", {})
    filler_keys = ["이제", "그래서", "어", "음", "자", "일단", "그러면"]
    filler_total = sum(float(discourse_markers.get(k, 0.0)) for k in filler_keys)
    repetition_count = features.get("repetition_count", 0)
    token_count_f = features.get("token_count", 1)

    if filler_total >= 100:
        base = 1.0
    elif filler_total >= 60:
        base = 2.0
    elif filler_total >= 30:
        base = 3.0
    elif filler_total >= 10:
        base = 4.0
    else:
        base = 5.0

    repeated_per_1k = (repetition_count / max(token_count_f, 1)) * 1000
    if repeated_per_1k >= 10:
        base -= 0.5

    heuristic_scores["불필요한 반복 표현"] = max(1.0, min(5.0, base))

    sentence_completion_ratio = ls.get("sentence_completion_ratio", 0.5)
    truncated_ratio = ls.get("truncated_utterance_ratio", 0.0)
    base = sentence_completion_ratio * 5.0 - truncated_ratio * 2.0
    heuristic_scores["발화 완결성"] = max(1.0, min(5.0, round(base, 2)))

    speech_style_consistency = ls.get("speech_style_consistency", 0.85)
    style_shift_ratio = ls.get("style_shift_ratio", 0.02)
    base = speech_style_consistency * 5.0 - style_shift_ratio * 3.0
    heuristic_scores["언어 일관성"] = max(1.0, min(5.0, round(base, 2)))

    objective_intro_presence = ls.get("objective_intro_presence", 0)
    objective_intro_count = ls.get("objective_intro_count", 0)
    if objective_intro_presence == 0:
        base = 1.5
    elif objective_intro_count >= 3:
        base = 5.0
    elif objective_intro_count == 2:
        base = 4.0
    else:
        base = 3.0
    heuristic_scores["학습 목표 안내"] = max(1.0, min(5.0, base))

    review_bridge_presence = ls.get("review_bridge_presence", 0)
    review_bridge_count = ls.get("review_bridge_count", 0)
    if review_bridge_presence == 0:
        base = 1.5
    elif review_bridge_count >= 2:
        base = 4.5
    else:
        base = 3.5
    heuristic_scores["전날 복습 연계"] = max(1.0, min(5.0, base))

    concept_example_practice_flow = ls.get("concept_example_practice_flow", 0.0)
    structure_transition_clarity = ls.get("structure_transition_clarity", 0.0)
    base = concept_example_practice_flow * 3.0 + structure_transition_clarity * 2.0
    heuristic_scores["설명 순서"] = max(1.0, min(5.0, round(base, 2)))

    emphasis_count = ls.get("emphasis_count", 0)
    emphasis_density = ls.get("emphasis_density", 0.0)
    if emphasis_density >= 5.0:
        base = 5.0
    elif emphasis_density >= 3.0:
        base = 4.0
    elif emphasis_density >= 1.0:
        base = 3.0
    elif emphasis_count >= 1:
        base = 2.0
    else:
        base = 1.5
    heuristic_scores["핵심 내용 강조"] = max(1.0, min(5.0, base))

    closing_summary_presence = ls.get("closing_summary_presence", 0)
    closing_summary_count = ls.get("closing_summary_count", 0)
    if closing_summary_presence == 0:
        base = 1.5
    elif closing_summary_count >= 3:
        base = 5.0
    elif closing_summary_count >= 2:
        base = 4.0
    else:
        base = 3.0
    heuristic_scores["마무리 요약"] = max(1.0, min(5.0, base))

    definition_density = ls.get("definition_density", 0.0)
    if definition_density >= 10.0:
        base = 5.0
    elif definition_density >= 5.0:
        base = 4.0
    elif definition_density >= 2.0:
        base = 3.0
    elif definition_density >= 0.5:
        base = 2.0
    else:
        base = 1.5
    heuristic_scores["개념 정의"] = max(1.0, min(5.0, base))

    example_density = ls.get("example_density", 0.0)
    analogy_density = ls.get("analogy_density", 0.0)
    example_count = features.get("example_count", 0)
    combined = example_density + analogy_density * 1.5
    if combined >= 5.0 or example_count >= 5:
        base = 5.0
    elif combined >= 3.0 or example_count >= 3:
        base = 4.0
    elif combined >= 1.0 or example_count >= 1:
        base = 3.0
    else:
        base = 2.0
    heuristic_scores["비유 및 예시 활용"] = max(1.0, min(5.0, base))

    prerequisite_bridge_presence = ls.get("prerequisite_bridge_presence", 0)
    prerequisite_bridge_count = ls.get("prerequisite_bridge_count", 0)
    if prerequisite_bridge_presence == 0:
        base = 2.0
    elif prerequisite_bridge_count >= 3:
        base = 5.0
    elif prerequisite_bridge_count >= 2:
        base = 4.0
    else:
        base = 3.0
    heuristic_scores["선행 개념 확인"] = max(1.0, min(5.0, base))

    if 100 <= words_per_minute <= 160:
        base = 5.0
    elif (80 <= words_per_minute < 100) or (160 < words_per_minute <= 190):
        base = 4.0
    elif (60 <= words_per_minute < 80) or (190 < words_per_minute <= 220):
        base = 3.0
    elif (40 <= words_per_minute < 60) or (220 < words_per_minute <= 250):
        base = 2.0
    else:
        base = 1.5
    heuristic_scores["발화 속도 적절성"] = max(1.0, min(5.0, base))

    practical_example_density = ls.get("practical_example_density", 0.0)
    if practical_example_density >= 5.0:
        base = 5.0
    elif practical_example_density >= 3.0:
        base = 4.0
    elif practical_example_density >= 1.0:
        base = 3.0
    elif practical_example_density > 0:
        base = 2.0
    else:
        base = 1.5
    heuristic_scores["예시 적절성"] = max(1.0, min(5.0, base))

    practice_transition_density = ls.get("practice_transition_density", 0.0)
    practice_directive_ratio = features.get("practice_directive_ratio", 0.0)
    base = practice_transition_density * 0.4 + practice_directive_ratio * 100 * 0.04
    if base >= 4.0:
        base = 5.0
    elif base >= 3.0:
        base = 4.0
    elif base >= 1.5:
        base = 3.0
    elif base >= 0.5:
        base = 2.0
    else:
        base = 1.5
    heuristic_scores["실습 연계"] = max(1.0, min(5.0, round(base, 2)))

    error_response_density = ls.get("error_response_density", 0.0)
    if error_response_density >= 5.0:
        base = 5.0
    elif error_response_density >= 2.0:
        base = 4.0
    elif error_response_density >= 0.5:
        base = 3.0
    elif error_response_density > 0:
        base = 2.0
    else:
        base = 2.0
    heuristic_scores["오류 대응"] = max(1.0, min(5.0, base))

    understanding_check_density = ls.get("understanding_check_density", 0.0)
    question_count = features.get("question_count", 0)
    base_density = understanding_check_density
    base_count = min(question_count / 10.0, 2.0)
    base = base_density * 0.5 + base_count
    if base >= 4.0:
        base = 5.0
    elif base >= 3.0:
        base = 4.0
    elif base >= 2.0:
        base = 3.0
    elif base >= 1.0:
        base = 2.0
    else:
        base = 1.5
    heuristic_scores["이해 확인 질문"] = max(1.0, min(5.0, round(base, 2)))

    engagement_density = ls.get("engagement_density", 0.0)
    if engagement_density >= 8.0:
        base = 5.0
    elif engagement_density >= 5.0:
        base = 4.0
    elif engagement_density >= 2.0:
        base = 3.0
    elif engagement_density >= 0.5:
        base = 2.0
    else:
        base = 1.5
    heuristic_scores["참여 유도"] = max(1.0, min(5.0, base))

    qa_response_density = ls.get("qa_response_density", 0.0)
    question_count = features.get("question_count", 0)
    base = qa_response_density
    if question_count >= 20:
        base += 1.0
    elif question_count >= 10:
        base += 0.5
    if base >= 4.0:
        base = 5.0
    elif base >= 3.0:
        base = 4.0
    elif base >= 1.5:
        base = 3.0
    elif base >= 0.5:
        base = 2.0
    else:
        base = 1.5
    heuristic_scores["질문 응답 충분성"] = max(1.0, min(5.0, round(base, 2)))

    analysis_map = {}
    for item in analysis_result.get("item_results", []):
        analysis_map[item.get("item_name")] = item

    item_results_scored = []
    for item_name in ITEM_WEIGHT:
        analysis_item = analysis_map.get(item_name, {})
        label = analysis_item.get("label", "neutral")
        confidence = float(analysis_item.get("confidence", 0.5))
        evidence = analysis_item.get("evidence", [])
        heuristic_score = heuristic_scores.get(item_name, 3.0)
        final_score = calc_final_score(heuristic_score, label, confidence, item_name)

        selected_evidence = None
        for ev in evidence:
            if ev.get("reason"):
                selected_evidence = {
                    "span_text": ev.get("span_text", ""),
                    "context_before": ev.get("context_before", []),
                }
                break

        reason = ""
        if evidence and isinstance(evidence[0], dict):
            reason = evidence[0].get("reason", "")

        item_results_scored.append({
            "item_name": item_name,
            "heuristic_score": heuristic_score,
            "final_score": final_score,
            "reason": reason,
            "selected_evidence": selected_evidence,
            "confidence": confidence,
            "evidence": evidence,
        })

    category_results = []
    for category_name, item_names in CATEGORY_ITEMS.items():
        items_scored = [item for item in item_results_scored if item["item_name"] in item_names]
        heuristic_score = calc_weighted_avg(items_scored, "heuristic_score")
        final_score = calc_weighted_avg(items_scored, "final_score")

        best_item = None
        for item in items_scored:
            if best_item is None or item["confidence"] > best_item["confidence"]:
                best_item = item

        if best_item and best_item["evidence"] and best_item["evidence"][0].get("reason"):
            reason = best_item["evidence"][0]["reason"]
        else:
            reason = f"{category_name}: 분석 근거 없음"

        top_items = []
        for item_name in item_names:
            for item in items_scored:
                if item["item_name"] == item_name:
                    top_items.append({
                        "item_name": item["item_name"],
                        "heuristic_score": item["heuristic_score"],
                        "final_score": item["final_score"],
                        "reason": item["reason"],
                        "selected_evidence": item["selected_evidence"],
                    })
                    break

        category_results.append({
            "category_name": category_name,
            "heuristic_score": heuristic_score,
            "final_score": final_score,
            "reason": reason,
            "top_items": top_items,
        })

    overall_weak_categories = [
        category["category_name"]
        for category in sorted(
            [category for category in category_results if category["final_score"] < 2.8],
            key=lambda x: x["final_score"],
        )
    ]

    return {
        "lecture_summary": {
            "overall_weak_categories": overall_weak_categories,
        },
        "category_results": category_results,
    }