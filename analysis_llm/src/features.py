# features.py
from __future__ import annotations

import re
from typing import Dict, Any, List


def _safe_div(a: float, b: float) -> float:
    return a / b if b else 0.0


def _count_keywords(text: str, keywords: List[str]) -> int:
    if not text:
        return 0
    total = 0
    for kw in keywords:
        total += text.count(kw)
    return total


def _contains_any(text: str, keywords: List[str]) -> bool:
    return _count_keywords(text, keywords) > 0


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text)).strip()


def _calc_sentence_completion_ratio(text: str) -> float:
    """
    매우 러프한 휴리스틱:
    종결 어미/문장부호가 있으면 완결 문장 비율이 높다고 본다.
    """
    text = _normalize_text(text)
    if not text:
        return 0.0

    endings = [
        "입니다", "합니다", "해요", "됩니다", "있습니다", "보겠습니다",
        "할게요", "합니다.", "해요.", "입니다.", "죠.", "요.", "다."
    ]
    punctuation_count = text.count(".") + text.count("?") + text.count("!")
    ending_hits = sum(text.count(e) for e in endings)

    rough_sentence_units = max(1, punctuation_count + text.count("요 ") + text.count("다 "))
    completion_proxy = min(1.0, (ending_hits + punctuation_count) / rough_sentence_units)
    return round(completion_proxy, 4)


def _calc_speech_style_consistency(text: str) -> float:
    """
    formal vs informal 비율의 max / total
    """
    text = _normalize_text(text)
    if not text:
        return 0.0

    formal_markers = [
        "습니다", "합니다", "입니다", "해요", "보겠습니다",
        "하시죠", "되겠습니다", "주세요"
    ]
    informal_markers = [
        "해라", "하자", "봐", "해", "되는 거야", "거든", "있죠", "맞죠"
    ]

    formal = _count_keywords(text, formal_markers)
    informal = _count_keywords(text, informal_markers)
    total = formal + informal

    if total == 0:
        return 0.85
    return round(max(formal, informal) / total, 4)


def _calc_truncated_ratio(text: str) -> float:
    """
    말 끊김/비완결 러프 추정
    """
    text = _normalize_text(text)
    if not text:
        return 0.0

    truncated_markers = ["...", "..", "어...", "음...", "그러니까...", "뭐...", "그..."]
    truncated = _count_keywords(text, truncated_markers)
    base = max(1, len(text.split()) / 20)
    return round(min(1.0, truncated / base), 4)


def _calc_style_shift_ratio(text: str) -> float:
    """
    formal/informal 섞임이 심할수록 증가
    """
    text = _normalize_text(text)
    if not text:
        return 0.0

    formal_markers = ["습니다", "합니다", "입니다", "해요"]
    informal_markers = ["해", "하자", "봐", "맞죠", "거든"]

    formal = _count_keywords(text, formal_markers)
    informal = _count_keywords(text, informal_markers)
    total = formal + informal
    if total == 0:
        return 0.02

    minority = min(formal, informal)
    return round(minority / total, 4)


def _density_per_1k(count: float, token_count: float) -> float:
    return round(_safe_div(count, max(token_count, 1)) * 1000, 4)


def calculate_signals(features_data: Dict[str, Any], chunks_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    scoring.py가 기대하는 lecture_signals + segments 구조를 최대한 맞춘다.
    현재 입력 JSON 구조(features.json, semantic_chunks.json)에 맞춰
    lecture-level signal과 segment-level signal/evidence를 함께 생성한다.
    """
    features = features_data.get("features", {}) or {}
    chunks = chunks_data.get("chunks", []) or []

    token_count = features.get("token_count", 0) or 0
    utterance_count = features.get("utterance_count", 0) or 0
    question_count = features.get("question_count", 0) or 0
    example_count = features.get("example_count", 0) or 0
    practice_directive_ratio = features.get("practice_directive_ratio", 0.0) or 0.0
    repetition_count = features.get("repetition_count", 0) or 0

    discourse_markers = features.get("discourse_marker_per_1k_tokens", {}) or {}

    filler_markers = ["이제", "그래서", "약간", "그냥", "어", "음", "자", "일단", "보시면", "그러면"]
    filler_ratio = sum(float(discourse_markers.get(k, 0.0)) for k in filler_markers if k in discourse_markers)

    # 전체 텍스트(semantic chunk preview 기반)
    all_text = " ".join(_normalize_text(c.get("text_preview", "")) for c in chunks if c.get("text_preview"))
    intro_chunks = chunks[:max(1, min(3, len(chunks)))]
    tail_chunks = chunks[-max(1, min(3, len(chunks))):] if chunks else []

    intro_text = " ".join(_normalize_text(c.get("text_preview", "")) for c in intro_chunks)
    tail_text = " ".join(_normalize_text(c.get("text_preview", "")) for c in tail_chunks)

    # 키워드 사전
    objective_keywords = ["오늘", "목표", "진행", "순서", "배워", "살펴보", "학습", "보겠습니다", "나눠서"]
    review_keywords = ["어제", "지난 시간", "이전", "복습", "앞서", "저번 시간"]
    summary_keywords = ["정리", "요약", "마무리", "여기까지", "끝내", "정리하면", "수고하셨", "마치겠습니다", "쉬겠습니다", "끝입니다", "마칩니다", "이상입니다"]
    definition_keywords = ["의미", "정의", "란", "라고 하는", "개념", "무엇인가"]
    example_keywords = ["예를 들어", "예를 들면", "예시", "가령"]
    analogy_keywords = ["마치", "비슷하게", "처럼", "비유하자면"]
    prerequisite_keywords = ["먼저", "기본적으로", "앞서", "이전에", "기존", "먼저 알아야"]
    emphasis_keywords = ["중요", "핵심", "꼭", "반드시", "포인트"]
    practical_example_keywords = ["실무", "업무", "프로젝트", "현업", "실제"]
    practice_keywords = [
        "실습", "해보", "따라", "눌러보", "직접", "구현", "해봅시다",
        "실행", "작성", "풀어", "해보세요", "한번 해보", "작성해",
        "코딩", "쿼리", "입력해", "써봐", "구현해",
    ]
    error_keywords = ["오류", "에러", "안 되", "문제", "다시 확인", "막히", "실패", "예외"]
    understanding_keywords = ["됐어요", "이해", "괜찮죠", "아시겠죠", "맞죠", "보이시죠"]
    engagement_keywords = ["같이", "해보세요", "직접", "눌러보세요", "따라", "한번 해보", "여러분도"]
    qa_keywords = ["질문", "답변", "설명드리", "물어보", "문의", "질문 있", "질문하면"]
    transition_keywords = ["이제", "그다음", "다음으로", "그러면", "이어서", "넘어가서"]

    # lecture-level signals
    lecture_signals = {
        "filler_ratio": round(filler_ratio, 4),
        "repeated_phrase_ratio": _density_per_1k(repetition_count, token_count),
        "token_count": token_count,
        "utterance_count": utterance_count,
        "question_count": question_count,
        "example_count": example_count,
        "practice_directive_ratio": round(float(practice_directive_ratio), 4),

        "sentence_completion_ratio": _calc_sentence_completion_ratio(all_text),
        "speech_style_consistency": _calc_speech_style_consistency(all_text),
        "truncated_utterance_ratio": _calc_truncated_ratio(all_text),
        "style_shift_ratio": _calc_style_shift_ratio(all_text),

        "objective_intro_count": _count_keywords(intro_text, objective_keywords),
        "objective_intro_presence": 1 if _contains_any(intro_text, objective_keywords) else 0,
        "review_bridge_count": _count_keywords(intro_text, review_keywords),
        "review_bridge_presence": 1 if _contains_any(intro_text, review_keywords) else 0,

        "concept_example_practice_flow": 0.0,   # 아래에서 보정
        "structure_transition_clarity": 0.0,    # 아래에서 보정

        "emphasis_count": _count_keywords(all_text, emphasis_keywords),
        "emphasis_density": _density_per_1k(_count_keywords(all_text, emphasis_keywords), token_count),

        "closing_summary_presence": 1 if _contains_any(tail_text, summary_keywords) else 0,
        "closing_summary_count": _count_keywords(tail_text, summary_keywords),

        "definition_density": _density_per_1k(_count_keywords(all_text, definition_keywords), token_count),

        "example_density": _density_per_1k(_count_keywords(all_text, example_keywords), token_count),
        "analogy_density": _density_per_1k(_count_keywords(all_text, analogy_keywords), token_count),

        "prerequisite_bridge_presence": 1 if _contains_any(all_text, prerequisite_keywords) else 0,
        "prerequisite_bridge_count": _count_keywords(all_text, prerequisite_keywords),

        "practical_example_density": _density_per_1k(_count_keywords(all_text, practical_example_keywords), token_count),

        "practice_transition_density": _density_per_1k(_count_keywords(all_text, practice_keywords), token_count),

        "error_response_density": _density_per_1k(_count_keywords(all_text, error_keywords), token_count),

        "understanding_check_density": _density_per_1k(_count_keywords(all_text, understanding_keywords), token_count),
        "engagement_density": _density_per_1k(_count_keywords(all_text, engagement_keywords), token_count),
        "qa_response_density": _density_per_1k(_count_keywords(all_text, qa_keywords), token_count),
    }

    # concept_example_practice_flow 보정
    intro_has_definition = _contains_any(intro_text, definition_keywords)
    mid_chunks = chunks[1:-1] if len(chunks) > 2 else chunks
    mid_text = " ".join(_normalize_text(c.get("text_preview", "")) for c in mid_chunks)
    mid_has_example = _contains_any(mid_text, example_keywords)
    has_practice = _contains_any(all_text, practice_keywords)

    if intro_has_definition and mid_has_example and has_practice:
        lecture_signals["concept_example_practice_flow"] = 1.0
    elif (intro_has_definition and mid_has_example) or (mid_has_example and has_practice):
        lecture_signals["concept_example_practice_flow"] = 0.5
    else:
        lecture_signals["concept_example_practice_flow"] = 0.0

    transition_count = _count_keywords(all_text, transition_keywords)
    lecture_signals["structure_transition_clarity"] = round(
        min(1.0, transition_count / max(len(chunks), 1)),
        4
    )

    segments = []

    for i, chunk in enumerate(chunks):
        # ★ 수정: normalize_text 적용해서 저장 — extract_evidence의 chunk_texts와 일치시킴
        text = _normalize_text(chunk.get("text_preview", ""))
        sub_label = chunk.get("sub_label", "") or ""
        parent_label = chunk.get("parent_label", "") or ""
        seg_token_proxy = max(1, len(text.split()))

        is_intro = i < max(1, min(3, len(chunks)))
        is_tail = i >= max(0, len(chunks) - max(1, min(3, len(chunks))))

        objective_intro_count = _count_keywords(text, objective_keywords) if is_intro else 0
        review_bridge_count = _count_keywords(text, review_keywords) if is_intro else 0
        summary_count = _count_keywords(text, summary_keywords) if is_tail else 0
        definition_count = _count_keywords(text, definition_keywords)
        example_count_seg = _count_keywords(text, example_keywords)
        analogy_count_seg = _count_keywords(text, analogy_keywords)
        prerequisite_count = _count_keywords(text, prerequisite_keywords)
        emphasis_count_seg = _count_keywords(text, emphasis_keywords)
        practice_count = _count_keywords(text, practice_keywords)
        practical_example_count = _count_keywords(text, practical_example_keywords)
        error_count = _count_keywords(text, error_keywords)
        understanding_count = _count_keywords(text, understanding_keywords)
        engagement_count = _count_keywords(text, engagement_keywords)
        qa_count = _count_keywords(text, qa_keywords)
        transition_count_seg = _count_keywords(text, transition_keywords)
        filler_count_seg = _count_keywords(text, filler_markers)

        # label 힌트도 반영
        if "example" in sub_label:
            example_count_seg += 1
            practical_example_count += 1
        if "instruction" in sub_label or "practice" in sub_label:
            practice_count += 1
            engagement_count += 1
            transition_count_seg += 1
        if "explanation" in sub_label:
            definition_count += 1
            prerequisite_count += 1

        seg_signals = {
            "objective_intro_presence": 1 if objective_intro_count > 0 else 0,
            "objective_intro_count": objective_intro_count,

            "review_bridge_presence": 1 if review_bridge_count > 0 else 0,
            "review_bridge_count": review_bridge_count,

            "concept_example_practice_flow": 1.0 if (definition_count > 0 and example_count_seg > 0 and practice_count > 0)
            else 0.5 if ((definition_count > 0 and example_count_seg > 0) or (example_count_seg > 0 and practice_count > 0))
            else 0.0,

            "structure_transition_clarity": round(min(1.0, transition_count_seg / 3), 4),

            "emphasis_density": _density_per_1k(emphasis_count_seg, seg_token_proxy),
            "emphasis_count": emphasis_count_seg,

            "closing_summary_presence": 1 if summary_count > 0 else 0,
            "closing_summary_count": summary_count,

            "definition_density": _density_per_1k(definition_count, seg_token_proxy),
            "definition_count": definition_count,

            "example_density": _density_per_1k(example_count_seg, seg_token_proxy),
            "analogy_density": _density_per_1k(analogy_count_seg, seg_token_proxy),

            "prerequisite_bridge_presence": 1 if prerequisite_count > 0 else 0,
            "prerequisite_bridge_count": prerequisite_count,

            "practical_example_density": _density_per_1k(practical_example_count, seg_token_proxy),
            "practice_transition_density": _density_per_1k(practice_count, seg_token_proxy),
            "practice_transition_count": practice_count,

            "error_response_density": _density_per_1k(error_count, seg_token_proxy),
            "error_response_count": error_count,

            "understanding_check_density": _density_per_1k(understanding_count, seg_token_proxy),
            "engagement_density": _density_per_1k(engagement_count, seg_token_proxy),
            "qa_response_density": _density_per_1k(qa_count, seg_token_proxy),

            "question_quality_proxy": round(min(1.0, (understanding_count + qa_count + transition_count_seg) / 5), 4),
            "check_question_ratio": round(min(1.0, _safe_div(understanding_count, max(1, qa_count + understanding_count))), 4),
            "interaction_prompt_count": engagement_count,
            "followup_presence": 1 if _contains_any(text, ["추가로", "다시", "보충해서", "한번 더"]) else 0,

            # lecture-level 일부 signal은 segment에서도 보조로 유지
            "sentence_completion_ratio": _calc_sentence_completion_ratio(text),
            "speech_style_consistency": _calc_speech_style_consistency(text),
            "truncated_utterance_ratio": _calc_truncated_ratio(text),
            "style_shift_ratio": _calc_style_shift_ratio(text),

            "rapid_transition_ratio": round(min(1.0, transition_count_seg / 5), 4),
        }

        evidence = {
            "objective_intro_spans": [text] if objective_intro_count > 0 else [],
            "intro_evidence": [text] if objective_intro_count > 0 else [],

            "review_bridge_spans": [text] if review_bridge_count > 0 else [],
            "bridge_evidence": [text] if review_bridge_count > 0 else [],

            "structure_flow_spans": [text] if seg_signals["concept_example_practice_flow"] > 0 else [],
            "transition_evidence": [text] if transition_count_seg > 0 else [],
            "structure_evidence": [text] if seg_signals["structure_transition_clarity"] > 0 else [],

            "emphasis_spans": [text] if emphasis_count_seg > 0 else [],
            "highlight_evidence": [text] if emphasis_count_seg > 0 else [],

            "closing_summary_spans": [text] if summary_count > 0 else [],
            "summary_evidence": [text] if summary_count > 0 else [],

            "definition_spans": [text] if definition_count > 0 else [],
            "concept_definition_evidence": [text] if definition_count > 0 else [],

            "example_spans": [text] if example_count_seg > 0 else [],
            "example_evidence": [text] if example_count_seg > 0 else [],

            "analogy_spans": [text] if analogy_count_seg > 0 else [],

            "prerequisite_bridge_spans": [text] if prerequisite_count > 0 else [],
            "prerequisite_evidence": [text] if prerequisite_count > 0 else [],

            "practical_example_spans": [text] if practical_example_count > 0 else [],
            "practical_example_evidence": [text] if practical_example_count > 0 else [],

            "practice_transition_spans": [text] if practice_count > 0 else [],
            "practice_evidence": [text] if practice_count > 0 else [],

            "error_response_spans": [text] if error_count > 0 else [],
            "error_evidence": [text] if error_count > 0 else [],

            "understanding_check_spans": [text] if understanding_count > 0 else [],
            "question_spans": [text] if (understanding_count > 0 or qa_count > 0) else [],
            "interaction_evidence": [text] if (understanding_count > 0 or engagement_count > 0) else [],

            "engagement_spans": [text] if engagement_count > 0 else [],
            "interaction_prompt_spans": [text] if engagement_count > 0 else [],
            "engagement_evidence": [text] if engagement_count > 0 else [],

            "qa_response_spans": [text] if qa_count > 0 else [],
            "qa_evidence": [text] if qa_count > 0 else [],
            "followup_spans": [text] if seg_signals["followup_presence"] > 0 else [],

            "pace_evidence": [text] if len(text.split()) > 20 else [],
            "rapid_transition_spans": [text] if seg_signals["rapid_transition_ratio"] > 0.2 else [],

            "incomplete_sentence_spans": [text] if seg_signals["sentence_completion_ratio"] < 0.5 else [],
            "completion_evidence": [text] if seg_signals["sentence_completion_ratio"] >= 0.5 else [],

            "style_shift_spans": [text] if seg_signals["style_shift_ratio"] > 0.2 else [],
            "speech_style_evidence": [text] if seg_signals["speech_style_consistency"] > 0.5 else [],

            # ★ 수정: filler 자체가 있으면 filler_spans에 포함 (lecture-level repetition_count 의존 제거)
            "filler_spans": [text] if filler_count_seg > 0 else [],
            # ★ 수정: repetition_spans — filler가 많은 청크를 반복 표현 후보로 봄 (이중 조건 제거)
            "repetition_spans": [text] if filler_count_seg >= 3 else [],
            "language_expression_evidence": [text] if filler_count_seg > 0 else [],
        }

        segments.append({
            "segment_id": chunk.get("segment_id"),
            "chunk_id": chunk.get("chunk_id"),
            "weight": chunk.get("utterance_count", 1) or 1,
            "signals": seg_signals,
            "evidence": evidence,
            "start_ts": chunk.get("start_ts"),
            "end_ts": chunk.get("end_ts"),
            "parent_label": parent_label,
            "sub_label": sub_label,
            "text_preview": text,  # ★ normalize_text 적용된 text 저장
        })

    return {
        "lecture_signals": lecture_signals,
        "segments": segments,
    }