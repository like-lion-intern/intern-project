from __future__ import annotations

import re
from typing import Any, Dict, List

from rerank import rerank_evidence


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text)).strip()


ITEM_EVIDENCE_RULES: Dict[str, Dict[str, Any]] = {
    "불필요한 반복 표현": {
        "query": "군더더기 표현이나 불필요한 반복 발화가 실제로 드러나는 문장",
        "supporting": [],
        "contrary": ["filler_spans", "repetition_spans", "language_expression_evidence"],
    },
    "발화 완결성": {
        "query": "문장이 자연스럽게 끝나거나 중간에 끊기는 발화",
        "supporting": ["completion_evidence"],
        "contrary": ["incomplete_sentence_spans"],
    },
    "언어 일관성": {
        "query": "말투가 일관되거나 갑자기 흔들리는 발화",
        "supporting": ["speech_style_evidence"],
        "contrary": ["style_shift_spans"],
    },
    "학습 목표 안내": {
        "query": "수업 목표나 진행 순서를 직접 안내하는 발화",
        "supporting": ["objective_intro_spans", "intro_evidence"],
        "contrary": [],
    },
    "전날 복습 연계": {
        "query": "이전 수업 내용과 연결하거나 복습을 언급하는 발화",
        "supporting": ["review_bridge_spans", "bridge_evidence"],
        "contrary": [],
    },
    "설명 순서": {
        "query": "개념에서 예시나 실습으로 자연스럽게 넘어가는 발화",
        "supporting": ["structure_flow_spans", "transition_evidence", "structure_evidence"],
        "contrary": [],
    },
    "핵심 내용 강조": {
        "query": "핵심이나 중요 포인트를 직접 강조하는 발화",
        "supporting": ["emphasis_spans", "highlight_evidence"],
        "contrary": [],
    },
    "마무리 요약": {
        "query": "수업 말미에 핵심을 요약하거나 정리하는 발화",
        "supporting": ["closing_summary_spans", "summary_evidence"],
        "contrary": [],
    },
    "개념 정의": {
        "query": "핵심 개념의 의미나 정의를 직접 설명하는 발화",
        "supporting": ["definition_spans", "concept_definition_evidence"],
        "contrary": [],
    },
    "비유 및 예시 활용": {
        "query": "비유나 예시를 통해 개념을 풀어 설명하는 발화",
        "supporting": ["example_spans", "example_evidence", "analogy_spans"],
        "contrary": [],
    },
    "선행 개념 확인": {
        "query": "이전에 알아야 할 내용이나 선행 개념을 짚어주는 발화",
        "supporting": ["prerequisite_bridge_spans", "prerequisite_evidence"],
        "contrary": [],
    },
    "발화 속도 적절성": {
        "query": "설명 속도가 안정적이거나 전환이 너무 빠른 발화",
        "supporting": ["pace_evidence"],
        "contrary": ["rapid_transition_spans"],
    },
    "예시 적절성": {
        "query": "실무적이거나 실제 맥락에 맞는 예시를 제시하는 발화",
        "supporting": ["practical_example_spans", "practical_example_evidence"],
        "contrary": [],
    },
    "실습 연계": {
        "query": "설명을 실습 행동으로 자연스럽게 연결하는 발화",
        "supporting": ["practice_transition_spans", "practice_evidence"],
        "contrary": [],
    },
    "오류 대응": {
        "query": "오류나 에러 상황을 설명하거나 해결해 주는 발화",
        "supporting": ["error_response_spans", "error_evidence"],
        "contrary": [],
    },
    "이해 확인 질문": {
        "query": "수강생 이해 여부를 확인하는 질문성 발화",
        "supporting": ["understanding_check_spans", "question_spans", "interaction_evidence"],
        "contrary": [],
    },
    "참여 유도": {
        "query": "수강생이 직접 따라 하거나 참여하도록 유도하는 발화",
        "supporting": ["engagement_spans", "interaction_prompt_spans", "engagement_evidence"],
        "contrary": [],
    },
    "질문 응답 충분성": {
        "query": "질문에 답하거나 추가 설명으로 보완하는 발화",
        "supporting": ["qa_response_spans", "qa_evidence", "followup_spans"],
        "contrary": [],
    },
}

ITEM_EVIDENCE_KEYS: Dict[str, List[str]] = {
    item_name: rule["supporting"] + rule["contrary"] for item_name, rule in ITEM_EVIDENCE_RULES.items()
}


def _ensure_entry(entry: Any, seg: Dict[str, Any], evidence_type: str, polarity: str) -> Dict[str, Any] | None:
    if isinstance(entry, dict):
        span_text = _normalize_text(entry.get("span_text", ""))
        if not span_text:
            return None
        normalized = dict(entry)
        normalized["span_text"] = span_text
        normalized.setdefault("evidence_type", evidence_type)
        normalized.setdefault("evidence_types", [evidence_type])
        normalized.setdefault("polarity", polarity)
        normalized.setdefault("matched_keywords", [])
        normalized.setdefault("segment_id", seg.get("segment_id"))
        normalized.setdefault("chunk_id", seg.get("chunk_id"))
        normalized.setdefault("start_ts", seg.get("start_ts"))
        normalized.setdefault("end_ts", seg.get("end_ts"))
        normalized.setdefault("parent_label", seg.get("parent_label"))
        normalized.setdefault("sub_label", seg.get("sub_label"))
        normalized.setdefault("local_score", 0.0)
        return normalized

    span_text = _normalize_text(entry)
    if not span_text:
        return None
    return {
        "span_text": span_text,
        "evidence_type": evidence_type,
        "evidence_types": [evidence_type],
        "polarity": polarity,
        "matched_keywords": [],
        "segment_id": seg.get("segment_id"),
        "chunk_id": seg.get("chunk_id"),
        "start_ts": seg.get("start_ts"),
        "end_ts": seg.get("end_ts"),
        "parent_label": seg.get("parent_label"),
        "sub_label": seg.get("sub_label"),
        "local_score": 0.0,
    }


def _collect_candidates(
    segments: List[Dict[str, Any]],
    evidence_keys: List[str],
    polarity: str,
) -> List[Dict[str, Any]]:
    deduped: Dict[str, Dict[str, Any]] = {}

    for seg in segments:
        seg_evidence = seg.get("evidence", {})
        for evidence_key in evidence_keys:
            for raw_entry in seg_evidence.get(evidence_key, []):
                entry = _ensure_entry(raw_entry, seg, evidence_key, polarity)
                if entry is None:
                    continue

                dedupe_key = "||".join(
                    [
                        _normalize_text(entry.get("span_text", "")),
                        str(entry.get("segment_id", "")),
                        polarity,
                    ]
                )
                existing = deduped.get(dedupe_key)
                if existing is None:
                    deduped[dedupe_key] = entry
                    continue

                existing_types = existing.get("evidence_types", [existing.get("evidence_type", evidence_key)])
                merged_types = []
                for candidate_type in existing_types + [evidence_key]:
                    if candidate_type and candidate_type not in merged_types:
                        merged_types.append(candidate_type)
                existing["evidence_types"] = merged_types
                existing["evidence_type"] = ", ".join(merged_types)

                merged_keywords = []
                for keyword in existing.get("matched_keywords", []) + entry.get("matched_keywords", []):
                    if keyword and keyword not in merged_keywords:
                        merged_keywords.append(keyword)
                existing["matched_keywords"] = merged_keywords

                if float(entry.get("local_score", 0.0)) > float(existing.get("local_score", 0.0)):
                    existing["local_score"] = entry.get("local_score", 0.0)
                    existing["context_before_hint"] = entry.get("context_before_hint", existing.get("context_before_hint", ""))

    return list(deduped.values())


def _build_context(entry: Dict[str, Any], chunk_lookup: Dict[str, str]) -> List[str]:
    context_before_hint = _normalize_text(entry.get("context_before_hint", ""))
    if context_before_hint:
        return [context_before_hint]

    chunk_id = entry.get("chunk_id")
    if chunk_id and chunk_id in chunk_lookup:
        return [chunk_lookup[chunk_id]]

    return []


def extract_evidence(
    item_name: str,
    chunks: List[Dict[str, Any]],
    signals_output: Dict[str, Any],
) -> Dict[str, List[Dict[str, Any]]]:
    """
    item_name에 해당하는 evidence를 추출하여 반환.
    supporting/contrary evidence를 분리해서 유지한다.
    """
    rule = ITEM_EVIDENCE_RULES.get(item_name, {"query": item_name, "supporting": [], "contrary": []})
    segments = signals_output.get("segments", [])

    chunk_lookup: Dict[str, str] = {}
    previous_chunk_text = ""
    for chunk in chunks:
        chunk_id = chunk.get("chunk_id")
        if chunk_id:
            chunk_lookup[chunk_id] = _normalize_text(previous_chunk_text)
        previous_chunk_text = chunk.get("text_preview", "")

    supporting_candidates = _collect_candidates(segments, rule["supporting"], "supporting")
    contrary_candidates = _collect_candidates(segments, rule["contrary"], "contrary")

    supporting_ranked = rerank_evidence(rule["query"], supporting_candidates, top_k=2)
    contrary_ranked = rerank_evidence(rule["query"], contrary_candidates, top_k=2)

    def finalize(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        result = []
        for entry in entries:
            result.append(
                {
                    "span_text": entry.get("span_text", ""),
                    "context_before": _build_context(entry, chunk_lookup),
                    "evidence_type": entry.get("evidence_type", ""),
                    "evidence_types": entry.get("evidence_types", []),
                    "polarity": entry.get("polarity", ""),
                    "matched_keywords": entry.get("matched_keywords", []),
                    "segment_id": entry.get("segment_id"),
                    "chunk_id": entry.get("chunk_id"),
                    "start_ts": entry.get("start_ts"),
                    "end_ts": entry.get("end_ts"),
                    "parent_label": entry.get("parent_label"),
                    "sub_label": entry.get("sub_label"),
                    "local_score": round(float(entry.get("local_score", 0.0)), 4),
                    "rerank_score": round(float(entry.get("rerank_score", 0.0)), 4),
                }
            )
        return result

    return {
        "supporting_evidence": finalize(supporting_ranked),
        "contrary_evidence": finalize(contrary_ranked),
    }
