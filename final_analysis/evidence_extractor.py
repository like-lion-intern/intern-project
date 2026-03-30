from __future__ import annotations

import re
from typing import List, Dict, Any

from rerank import rerank_evidence


def _normalize_text(text: str) -> str:
    """features.py와 동일한 normalize 함수 — chunk_texts 매칭 일치를 위해 필요"""
    return re.sub(r"\s+", " ", str(text)).strip()


ITEM_EVIDENCE_KEYS: Dict[str, List[str]] = {
    "불필요한 반복 표현": ["filler_spans", "repetition_spans", "language_expression_evidence"],
    "발화 완결성": ["incomplete_sentence_spans", "completion_evidence"],
    "언어 일관성": ["style_shift_spans", "speech_style_evidence"],
    "학습 목표 안내": ["objective_intro_spans", "intro_evidence"],
    "전날 복습 연계": ["review_bridge_spans", "bridge_evidence"],
    "설명 순서": ["structure_flow_spans", "transition_evidence", "structure_evidence"],
    "핵심 내용 강조": ["emphasis_spans", "highlight_evidence"],
    "마무리 요약": ["closing_summary_spans", "summary_evidence"],
    "개념 정의": ["definition_spans", "concept_definition_evidence"],
    "비유 및 예시 활용": ["example_spans", "example_evidence", "analogy_spans"],
    "선행 개념 확인": ["prerequisite_bridge_spans", "prerequisite_evidence"],
    "발화 속도 적절성": ["pace_evidence", "rapid_transition_spans"],
    "예시 적절성": ["practical_example_spans", "practical_example_evidence"],
    "실습 연계": ["practice_transition_spans", "practice_evidence"],
    "오류 대응": ["error_response_spans", "error_evidence"],
    "이해 확인 질문": ["understanding_check_spans", "question_spans", "interaction_evidence"],
    "참여 유도": ["engagement_spans", "interaction_prompt_spans", "engagement_evidence"],
    "질문 응답 충분성": ["qa_response_spans", "qa_evidence", "followup_spans"],
}


def extract_evidence(
    item_name: str,
    chunks: List[Dict[str, Any]],
    signals_output: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    item_name에 해당하는 evidence를 추출하여 반환.
    반환 형태:
    [
        {
            "span_text": str,
            "context_before": [str],  # 앞 1개 chunk text_preview
        },
        ...  # 최대 2개
    ]
    """
    evidence_keys = ITEM_EVIDENCE_KEYS.get(item_name, [])
    segments = signals_output.get("segments", [])

    candidates_with_idx: List[tuple] = []
    seen_texts = set()

    for seg in segments:
        seg_evidence = seg.get("evidence", {})
        seg_text = seg.get("text_preview", "")
        if not seg_text:
            continue

        matched = False
        for key in evidence_keys:
            spans = seg_evidence.get(key, [])
            if spans:
                matched = True
                break

        if matched and seg_text not in seen_texts:
            seen_texts.add(seg_text)
            candidates_with_idx.append(seg_text)

    if not candidates_with_idx:
        return []

    # ★ top_k=2로 변경
    top_texts = rerank_evidence(item_name, candidates_with_idx, top_k=2)

    result = []

    # ★ normalize_text 적용해서 chunk_texts 만들기 — features.py와 일치시킴
    chunk_texts_normalized = [_normalize_text(c.get("text_preview", "")) for c in chunks]

    for span_text in top_texts:
        chunk_idx = None
        for i, ct in enumerate(chunk_texts_normalized):
            if ct == span_text:
                chunk_idx = i
                break

        # normalize 후에도 못 찾으면 부분 매칭 시도
        if chunk_idx is None:
            for i, ct in enumerate(chunk_texts_normalized):
                if span_text and ct and span_text[:50] in ct:
                    chunk_idx = i
                    break

        if chunk_idx is None:
            result.append({
                "span_text": span_text,
                "context_before": []
            })
            continue

        # ★ context_before 1개만
        context_before = chunk_texts_normalized[max(0, chunk_idx - 1):chunk_idx]

        result.append({
            "span_text": span_text,
            "context_before": context_before
        })

    return result