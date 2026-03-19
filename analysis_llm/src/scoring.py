from __future__ import annotations

import copy
import json
from dataclasses import dataclass, asdict
from statistics import mean
from typing import Any, Dict, Iterable, List, Optional, Tuple


# ==============================
# Core helpers
# ==============================

def clamp_score(score: float, min_val: float = 1.0, max_val: float = 5.0) -> float:
    return max(min_val, min(max_val, score))


def clamp_item_score(score: float, min_cap: float = 1.3, max_cap: float = 4.85) -> float:
    return max(min_cap, min(max_cap, score))


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def weighted_mean(values: Iterable[Tuple[float, float]], default: float = 0.0) -> float:
    total_weight = 0.0
    total_value = 0.0
    for value, weight in values:
        if weight <= 0:
            continue
        total_weight += weight
        total_value += value * weight
    if total_weight == 0:
        return default
    return total_value / total_weight


def dedupe_texts(texts: Iterable[str]) -> List[str]:
    seen = set()
    output: List[str] = []
    for text in texts:
        if not text:
            continue
        key = " ".join(str(text).split())
        if not key or key in seen:
            continue
        seen.add(key)
        output.append(str(text).strip())
    return output


# ==============================
# Configuration
# ==============================

@dataclass
class SignalRule:
    name: str
    direction: str  # 'higher_better', 'lower_better', 'presence_better', 'range_best'
    weight: float
    low: Optional[float] = None
    high: Optional[float] = None
    ideal_low: Optional[float] = None
    ideal_high: Optional[float] = None
    description: str = ""


@dataclass
class ItemConfig:
    item_name: str
    category_name: str
    signal_rules: List[SignalRule]
    evidence_keys: List[str]
    absence_evidence_message: str
    item_context: str
    min_cap: float = 1.3
    max_cap: float = 4.85


CATEGORY_ITEM_CONFIGS: Dict[str, List[ItemConfig]] = {
    "언어 표현 품질": [
        ItemConfig(
            item_name="불필요한 반복 표현",
            category_name="언어 표현 품질",
            signal_rules=[
                SignalRule("filler_ratio", "lower_better", 1.0, low=2.0, high=18.0, description="군더더기 표현 비율"),
                SignalRule("repeated_phrase_ratio", "lower_better", 0.6, low=1.0, high=10.0, description="반복 구문 비율"),
            ],
            evidence_keys=["filler_spans", "repetition_spans", "language_expression_evidence"],
            absence_evidence_message="군더더기 표현이 두드러지게 반복된 구간은 상대적으로 적음",
            item_context="설명 전달을 방해하는 습관적 반복 표현이 얼마나 많은지 평가",
        ),
        ItemConfig(
            item_name="발화 완결성",
            category_name="언어 표현 품질",
            signal_rules=[
                SignalRule("sentence_completion_ratio", "higher_better", 1.0, low=0.50, high=0.95, description="문장 완결 비율"),
                SignalRule("truncated_utterance_ratio", "lower_better", 0.5, low=0.02, high=0.25, description="중간 끊김 비율"),
            ],
            evidence_keys=["incomplete_sentence_spans", "completion_evidence"],
            absence_evidence_message="비완결 발화가 반복적으로 관찰되지는 않음",
            item_context="문장이 끝까지 전달되어 학습자가 의미를 따라갈 수 있는지 평가",
            min_cap=1.5,
            max_cap=4.7,
        ),
        ItemConfig(
            item_name="언어 일관성",
            category_name="언어 표현 품질",
            signal_rules=[
                SignalRule("speech_style_consistency", "higher_better", 1.0, low=0.45, high=0.95, description="어체 일관성"),
                SignalRule("style_shift_ratio", "lower_better", 0.5, low=0.01, high=0.20, description="어체 급변 비율"),
            ],
            evidence_keys=["style_shift_spans", "speech_style_evidence"],
            absence_evidence_message="어체가 급격히 흔들리는 구간은 많지 않음",
            item_context="격식/비격식, 설명 말투의 톤이 안정적으로 유지되는지 평가",
        ),
    ],
    "강의 도입 및 구조": [
        ItemConfig(
            item_name="학습 목표 안내",
            category_name="강의 도입 및 구조",
            signal_rules=[
                SignalRule("objective_intro_presence", "presence_better", 1.0, description="목표 안내 존재 여부"),
                SignalRule("objective_intro_count", "higher_better", 0.4, low=0.0, high=3.0, description="목표 안내 표현 수"),
            ],
            evidence_keys=["objective_intro_spans", "intro_evidence"],
            absence_evidence_message="학습 목표나 오늘의 흐름을 명시적으로 안내하는 표현이 뚜렷하지 않음",
            item_context="도입에서 학습 목표나 진행 흐름을 명확히 안내하는지 평가",
        ),
        ItemConfig(
            item_name="전날 복습 연계",
            category_name="강의 도입 및 구조",
            signal_rules=[
                SignalRule("review_bridge_presence", "presence_better", 1.0, description="복습 연계 존재 여부"),
                SignalRule("review_bridge_count", "higher_better", 0.4, low=0.0, high=3.0, description="복습 연계 표현 수"),
            ],
            evidence_keys=["review_bridge_spans", "bridge_evidence"],
            absence_evidence_message="앞선 수업이나 이전 개념을 되짚는 복습 연결 표현이 거의 없음",
            item_context="이전 학습 내용과 자연스럽게 이어주는 복습 브리지가 있는지 평가",
        ),
        ItemConfig(
            item_name="설명 순서",
            category_name="강의 도입 및 구조",
            signal_rules=[
                SignalRule("concept_example_practice_flow", "higher_better", 1.0, low=0.20, high=0.90, description="정의-예시-실습 흐름 점수"),
                SignalRule("structure_transition_clarity", "higher_better", 0.5, low=0.20, high=0.90, description="전환 명확성"),
            ],
            evidence_keys=["structure_flow_spans", "transition_evidence", "structure_evidence"],
            absence_evidence_message="설명 흐름을 분명히 보여주는 전환 표현이나 구조 신호가 제한적임",
            item_context="개념 설명, 예시, 실습으로 이어지는 순서가 자연스럽고 예측 가능하게 전개되는지 평가",
            min_cap=1.5,
            max_cap=4.7,
        ),
        ItemConfig(
            item_name="핵심 내용 강조",
            category_name="강의 도입 및 구조",
            signal_rules=[
                SignalRule("emphasis_density", "higher_better", 1.0, low=0.20, high=3.00, description="핵심 강조 밀도"),
                SignalRule("emphasis_count", "higher_better", 0.4, low=0.0, high=8.0, description="강조 표현 수"),
            ],
            evidence_keys=["emphasis_spans", "highlight_evidence"],
            absence_evidence_message="핵심 포인트를 짚어 주는 강조 표현이 충분히 드러나지 않음",
            item_context="중요 개념이나 주의 포인트를 학습자가 인지할 수 있게 강조하는지 평가",
        ),
        ItemConfig(
            item_name="마무리 요약",
            category_name="강의 도입 및 구조",
            signal_rules=[
                SignalRule("closing_summary_presence", "presence_better", 1.0, description="마무리 요약 존재 여부"),
                SignalRule("closing_summary_count", "higher_better", 0.4, low=0.0, high=3.0, description="마무리 요약 표현 수"),
            ],
            evidence_keys=["closing_summary_spans", "summary_evidence"],
            absence_evidence_message="마지막에 핵심을 정리해 주는 명시적 요약 구간이 부족함",
            item_context="세그먼트나 강의 말미에 핵심 내용을 정리해 주는지 평가",
        ),
    ],
    "개념 설명 명확성": [
        ItemConfig(
            item_name="개념 정의",
            category_name="개념 설명 명확성",
            signal_rules=[
                SignalRule("definition_density", "higher_better", 1.0, low=0.10, high=3.00, description="개념 정의 밀도"),
                SignalRule("definition_count", "higher_better", 0.4, low=0.0, high=10.0, description="개념 정의 수"),
            ],
            evidence_keys=["definition_spans", "concept_definition_evidence"],
            absence_evidence_message="개념을 명시적으로 정의하는 표현이 상대적으로 적음",
            item_context="핵심 개념을 구조적으로 정의하고 출발점을 분명히 제시하는지 평가",
        ),
        ItemConfig(
            item_name="비유 및 예시 활용",
            category_name="개념 설명 명확성",
            signal_rules=[
                SignalRule("example_density", "higher_better", 1.0, low=0.10, high=2.50, description="예시 밀도"),
                SignalRule("analogy_density", "higher_better", 0.6, low=0.0, high=1.20, description="비유 밀도"),
            ],
            evidence_keys=["example_spans", "analogy_spans", "example_evidence"],
            absence_evidence_message="추상적 설명을 구체화하는 예시나 비유가 충분히 드러나지 않음",
            item_context="추상적인 개념을 실제 사례, 비유, 예시로 풀어 설명하는지 평가",
        ),
        ItemConfig(
            item_name="선행 개념 확인",
            category_name="개념 설명 명확성",
            signal_rules=[
                SignalRule("prerequisite_bridge_presence", "presence_better", 1.0, description="선행 개념 연결 존재 여부"),
                SignalRule("prerequisite_bridge_count", "higher_better", 0.5, low=0.0, high=5.0, description="선행 개념 연결 수"),
            ],
            evidence_keys=["prerequisite_bridge_spans", "prerequisite_evidence"],
            absence_evidence_message="앞선 개념이나 기초 지식을 확인하며 연결하는 설명이 제한적임",
            item_context="새 개념을 설명할 때 기존 지식과 연결해 이해 다리를 놓는지 평가",
            min_cap=1.5,
            max_cap=4.7,
        ),
        ItemConfig(
            item_name="발화 속도 적절성",
            category_name="개념 설명 명확성",
            signal_rules=[
                SignalRule("words_per_minute", "range_best", 1.0, ideal_low=120.0, ideal_high=185.0, low=90.0, high=220.0, description="분당 어절 수"),
                SignalRule("rapid_transition_ratio", "lower_better", 0.4, low=0.02, high=0.25, description="빠른 전환 비율"),
            ],
            evidence_keys=["pace_evidence", "rapid_transition_spans"],
            absence_evidence_message="과도하게 빠른 전환 신호는 제한적이며 속도는 대체로 안정적임",
            item_context="설명 속도가 이해를 방해하지 않는 범위에서 유지되는지 평가",
        ),
    ],
    "예시 및 실습 연계": [
        ItemConfig(
            item_name="예시 적절성",
            category_name="예시 및 실습 연계",
            signal_rules=[
                SignalRule("practical_example_density", "higher_better", 1.0, low=0.10, high=2.00, description="실무 예시 밀도"),
                SignalRule("example_density", "higher_better", 0.4, low=0.10, high=2.50, description="일반 예시 밀도"),
            ],
            evidence_keys=["practical_example_spans", "example_spans", "practical_example_evidence"],
            absence_evidence_message="실제 적용 맥락을 보여주는 예시가 충분히 드러나지 않음",
            item_context="학습 내용을 실제 상황이나 적용 맥락과 연결하는 예시가 적절한지 평가",
        ),
        ItemConfig(
            item_name="실습 연계",
            category_name="예시 및 실습 연계",
            signal_rules=[
                SignalRule("practice_transition_density", "higher_better", 1.0, low=0.05, high=1.50, description="실습 전환 밀도"),
                SignalRule("practice_transition_count", "higher_better", 0.5, low=0.0, high=6.0, description="실습 유도 수"),
            ],
            evidence_keys=["practice_transition_spans", "practice_evidence"],
            absence_evidence_message="설명에서 실습으로 이어지는 전환 표현이 뚜렷하지 않음",
            item_context="설명 내용을 직접 해보는 활동으로 자연스럽게 연결하는지 평가",
        ),
        ItemConfig(
            item_name="오류 대응",
            category_name="예시 및 실습 연계",
            signal_rules=[
                SignalRule("error_response_density", "higher_better", 1.0, low=0.0, high=1.20, description="오류 대응 밀도"),
                SignalRule("error_response_count", "higher_better", 0.5, low=0.0, high=5.0, description="오류 대응 수"),
            ],
            evidence_keys=["error_response_spans", "error_evidence"],
            absence_evidence_message="오류 상황이나 막히는 지점에 대한 대응 안내가 뚜렷하지 않음",
            item_context="실습 중 발생 가능한 오류나 문제 상황에 어떻게 대응하는지 평가",
        ),
    ],
    "수강생 상호작용": [
        ItemConfig(
            item_name="이해 확인 질문",
            category_name="수강생 상호작용",
            signal_rules=[
                SignalRule("understanding_check_density", "higher_better", 0.7, low=0.05, high=1.20, description="이해 확인 표현 밀도"),
                SignalRule("question_quality_proxy", "higher_better", 1.0, low=0.10, high=0.90, description="질문 질 프록시"),
                SignalRule("check_question_ratio", "higher_better", 0.5, low=0.05, high=0.60, description="확인 질문 비율"),
            ],
            evidence_keys=["understanding_check_spans", "question_spans", "interaction_evidence"],
            absence_evidence_message="학습자의 이해를 점검하는 질문이 충분히 드러나지 않음",
            item_context="형식적 확인을 넘어서 학습자의 이해를 실제로 점검하는 질문이 있는지 평가",
        ),
        ItemConfig(
            item_name="참여 유도",
            category_name="수강생 상호작용",
            signal_rules=[
                SignalRule("engagement_density", "higher_better", 1.0, low=0.05, high=1.50, description="참여 유도 밀도"),
                SignalRule("interaction_prompt_count", "higher_better", 0.5, low=0.0, high=8.0, description="참여 유도 수"),
            ],
            evidence_keys=["engagement_spans", "interaction_prompt_spans", "engagement_evidence"],
            absence_evidence_message="학습자에게 직접 행동이나 사고를 요청하는 참여 유도 표현이 제한적임",
            item_context="학습자가 생각하거나 직접 따라 하도록 유도하는 발화가 있는지 평가",
        ),
        ItemConfig(
            item_name="질문 응답 충분",
            category_name="수강생 상호작용",
            signal_rules=[
                SignalRule("qa_response_density", "higher_better", 1.0, low=0.0, high=1.20, description="질문 응답 밀도"),
                SignalRule("followup_presence", "presence_better", 0.6, description="후속 응답 존재 여부"),
            ],
            evidence_keys=["qa_response_spans", "followup_spans", "qa_evidence"],
            absence_evidence_message="질문 이후 충분한 응답이나 후속 설명이 뚜렷하게 드러나지 않음",
            item_context="학습자 질문이나 반응에 대해 충분히 설명하고 후속 대응하는지 평가",
        ),
    ],
}


# ==============================
# Normalization / scoring
# ==============================

def _linear_score_higher_better(value: float, low: float, high: float) -> float:
    if high <= low:
        return 3.0
    if value <= low:
        return 1.0
    if value >= high:
        return 5.0
    ratio = (value - low) / (high - low)
    return 1.0 + ratio * 4.0



def _linear_score_lower_better(value: float, low: float, high: float) -> float:
    if high <= low:
        return 3.0
    if value <= low:
        return 5.0
    if value >= high:
        return 1.0
    ratio = (value - low) / (high - low)
    return 5.0 - ratio * 4.0



def _presence_score(value: float) -> float:
    return 5.0 if value > 0 else 1.5



def _range_best_score(value: float, ideal_low: float, ideal_high: float, low: float, high: float) -> float:
    if ideal_low <= value <= ideal_high:
        return 5.0
    if value <= low or value >= high:
        return 1.0
    if value < ideal_low:
        ratio = (value - low) / max(ideal_low - low, 1e-8)
        return 1.0 + ratio * 4.0
    ratio = (high - value) / max(high - ideal_high, 1e-8)
    return 1.0 + ratio * 4.0



def score_signal(rule: SignalRule, value: Any) -> float:
    numeric = safe_float(value)
    if rule.direction == "higher_better":
        return clamp_score(_linear_score_higher_better(numeric, rule.low or 0.0, rule.high or 1.0))
    if rule.direction == "lower_better":
        return clamp_score(_linear_score_lower_better(numeric, rule.low or 0.0, rule.high or 1.0))
    if rule.direction == "presence_better":
        return clamp_score(_presence_score(numeric))
    if rule.direction == "range_best":
        return clamp_score(
            _range_best_score(
                numeric,
                rule.ideal_low if rule.ideal_low is not None else (rule.low or 0.0),
                rule.ideal_high if rule.ideal_high is not None else (rule.high or 1.0),
                rule.low or 0.0,
                rule.high or 1.0,
            )
        )
    return 3.0


# ==============================
# Feature extraction adapters
# ==============================

def _infer_segment_weight(segment: Dict[str, Any]) -> float:
    for key in ("utterance_count", "duration_sec", "word_count", "token_count"):
        value = safe_float(segment.get(key), 0.0)
        if value > 0:
            return value
    return 1.0



def _get_nested(d: Dict[str, Any], *keys: str) -> Any:
    current = d
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current



def normalize_feature_bundle(feature_bundle: Dict[str, Any]) -> Dict[str, Any]:
    """
    입력 형태가 약간 달라도 scoring 단계에서 공통으로 쓸 수 있게 정리한다.

    기대 출력 형식:
    {
      "lecture": {signal_name: value, ...},
      "segments": [
         {
            "segment_id": ...,
            "parent_label": ...,
            "sub_label": ...,
            "weight": ...,
            "signals": {...},
            "evidence": {...}
         }
      ]
    }
    """
    lecture_signals = feature_bundle.get("lecture_signals") or feature_bundle.get("signals") or feature_bundle.get("lecture") or {}

    raw_segments = feature_bundle.get("segment_results") or feature_bundle.get("segments") or []
    normalized_segments: List[Dict[str, Any]] = []

    for seg in raw_segments:
        if not isinstance(seg, dict):
            continue
        signals = seg.get("signals") or seg.get("features") or {}
        evidence = seg.get("evidence") or seg.get("evidence_map") or {}
        normalized_segments.append(
            {
                "segment_id": seg.get("segment_id") or seg.get("id"),
                "parent_label": seg.get("parent_label"),
                "sub_label": seg.get("sub_label"),
                "start_ts": seg.get("start_ts"),
                "end_ts": seg.get("end_ts"),
                "weight": _infer_segment_weight(seg),
                "signals": signals,
                "evidence": evidence,
            }
        )

    return {
        "lecture": lecture_signals,
        "segments": normalized_segments,
    }


# ==============================
# Aggregation
# ==============================

def aggregate_signal_value(signal_name: str, normalized: Dict[str, Any]) -> float:
    lecture_signals = normalized.get("lecture", {})
    if signal_name in lecture_signals:
        return safe_float(lecture_signals.get(signal_name))

    segments = normalized.get("segments", [])
    values: List[Tuple[float, float]] = []
    has_presence = False
    for seg in segments:
        value = safe_float(_get_nested(seg, "signals", signal_name), default=0.0)
        weight = safe_float(seg.get("weight"), 1.0)
        values.append((value, weight))
        has_presence = has_presence or (value > 0)

    if signal_name.endswith("_count"):
        return sum(value for value, _ in values)
    if signal_name.endswith("_presence"):
        return 1.0 if has_presence else 0.0
    return weighted_mean(values)



def collect_item_evidence(item_cfg: ItemConfig, normalized: Dict[str, Any], max_items: int = 3) -> List[str]:
    candidates: List[str] = []
    for seg in normalized.get("segments", []):
        seg_prefix = ""
        seg_id = seg.get("segment_id")
        if seg_id is not None:
            seg_prefix = f"[segment {seg_id}] "
        evidence_map = seg.get("evidence", {}) or {}
        for key in item_cfg.evidence_keys:
            value = evidence_map.get(key)
            if value is None:
                continue
            if isinstance(value, list):
                for text in value:
                    if isinstance(text, str):
                        candidates.append(seg_prefix + text.strip())
                    elif isinstance(text, dict) and text.get("text"):
                        candidates.append(seg_prefix + str(text["text"]).strip())
            elif isinstance(value, str):
                candidates.append(seg_prefix + value.strip())

    deduped = dedupe_texts(candidates)
    if deduped:
        return deduped[:max_items]
    return [item_cfg.absence_evidence_message]



def heuristic_score_for_item(item_cfg: ItemConfig, normalized: Dict[str, Any]) -> Tuple[float, Dict[str, Any], Dict[str, float]]:
    aggregated_signals: Dict[str, Any] = {}
    signal_subscores: Dict[str, float] = {}

    weighted_scores: List[Tuple[float, float]] = []
    for rule in item_cfg.signal_rules:
        value = aggregate_signal_value(rule.name, normalized)
        aggregated_signals[rule.name] = round(value, 4)
        subscore = score_signal(rule, value)
        signal_subscores[rule.name] = round(subscore, 4)
        weighted_scores.append((subscore, rule.weight))

    total_weight = sum(rule.weight for rule in item_cfg.signal_rules) or 1.0
    score = sum(score * weight for score, weight in weighted_scores) / total_weight
    score = clamp_item_score(score, item_cfg.min_cap, item_cfg.max_cap)
    return round(score, 2), aggregated_signals, signal_subscores



from rerank import rerank_evidence

def build_item_packet(item_cfg: ItemConfig, normalized: Dict[str, Any]) -> Dict[str, Any]:
    heuristic_score, aggregated_signals, signal_subscores = heuristic_score_for_item(item_cfg, normalized)
    
    # Collect all candidates first (max_items increased to provide candidates for reranking)
    candidates = collect_item_evidence(item_cfg, normalized, max_items=10)
    
    # Rerank using E5
    if candidates and "뚜렷하지 않음" not in candidates[0] and "적음" not in candidates[0]:
        selected_evidence = rerank_evidence(item_cfg.item_context, candidates, top_k=3)
    else:
        selected_evidence = candidates[:3]

    return {
        "item_name": item_cfg.item_name,
        "heuristic_score": heuristic_score,
        "aggregated_signals": aggregated_signals,
        "signal_subscores": signal_subscores,
        "top_evidence": selected_evidence,
        "item_context": item_cfg.item_context,
    }



def build_category_packets(feature_bundle: Dict[str, Any]) -> List[Dict[str, Any]]:
    normalized = normalize_feature_bundle(feature_bundle)
    category_packets: List[Dict[str, Any]] = []

    for category_name, item_cfgs in CATEGORY_ITEM_CONFIGS.items():
        items = [build_item_packet(item_cfg, normalized) for item_cfg in item_cfgs]
        heuristic_scores = [item["heuristic_score"] for item in items]
        category_packets.append(
            {
                "category_name": category_name,
                "category_context": {
                    "item_count": len(items),
                    "category_heuristic_score": round(mean(heuristic_scores), 2) if heuristic_scores else 0.0,
                    "note": "item 간 관계를 함께 해석해 category summary를 생성해야 함",
                },
                "items": items,
            }
        )

    return category_packets



def build_prompt_packet(
    lecture_id: str,
    feature_bundle: Dict[str, Any],
    lecture_meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    lecture_meta = lecture_meta or {}
    categories = build_category_packets(feature_bundle)
    return {
        "lecture_id": lecture_id,
        "lecture_meta": lecture_meta,
        "categories": categories,
    }



def build_debug_payload(lecture_id: str, feature_bundle: Dict[str, Any]) -> Dict[str, Any]:
    normalized = normalize_feature_bundle(feature_bundle)
    packet = build_prompt_packet(lecture_id=lecture_id, feature_bundle=feature_bundle)
    return {
        "lecture_id": lecture_id,
        "normalized_features": normalized,
        "prompt_packet": packet,
    }


if __name__ == "__main__":
    # 간단한 로컬 확인용
    sample = {
        "lecture_signals": {
            "filler_ratio": 8.2,
            "sentence_completion_ratio": 0.87,
            "speech_style_consistency": 0.92,
            "objective_intro_presence": 1,
            "review_bridge_presence": 0,
            "definition_density": 1.8,
            "example_density": 0.4,
            "words_per_minute": 178,
        },
        "segments": [
            {
                "segment_id": 1,
                "utterance_count": 12,
                "signals": {"objective_intro_presence": 1, "objective_intro_count": 1},
                "evidence": {"objective_intro_spans": ["오늘은 임베딩의 기본 개념과 활용 흐름을 보겠습니다."]},
            },
            {
                "segment_id": 2,
                "utterance_count": 30,
                "signals": {"definition_density": 2.1, "example_density": 0.2},
                "evidence": {
                    "definition_spans": ["임베딩은 텍스트를 벡터 공간에 표현하는 방식입니다."],
                    "example_spans": ["예를 들어 비슷한 의미의 단어는 가까운 벡터로 나타납니다."],
                },
            },
        ],
    }
    print(json.dumps(build_prompt_packet("demo_lecture", sample), ensure_ascii=False, indent=2))
