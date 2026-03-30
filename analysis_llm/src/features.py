# features.py
from __future__ import annotations

import re
from typing import Any, Dict, List


_PUNCT_SPLIT_RE = re.compile(r"(?<=[\.\?!])\s+|\n+")
_QUESTION_FORM_RE = re.compile(r"(\?|나요|니요|죠|습니까|있나요|됐나요|되셨죠|아시겠죠|보이시죠|괜찮죠|볼 사람|할 사람|말해볼래요)$")
_PARTICIPATION_FORM_RE = re.compile(r"(해보세요|해봅시다|써보세요|적어보세요|입력해보세요|실행해보세요|말해볼래요|답해볼 사람|생각해보세요|따라와 보세요)")
_DEFINITION_FORM_RE = re.compile(r"(란|는 .*이다|라고 보면|라고 부른다|의 역할은|의 의미는|정확히는|쉽게 말하면)")


KEYWORD_RULES = {
    "불필요한 반복 표현": {
        "strong": ["그러면 이제", "약간 이제", "이런 식으로", "그치", "그렇죠", "그러니까", "음...", "어..."],
        "weak": ["이제", "그래서", "약간", "그냥", "어", "음", "자", "일단", "보시면", "그러면"],
        "remove_single": [],
    },
    "발화 완결성": {
        "positive_strong": ["입니다", "합니다", "해요", "됩니다", "있습니다", "보겠습니다"],
        "positive_weak": [".", "?", "!"],
        "negative_strong": ["...", "..", "어...", "음...", "그러니까...", "뭐...", "그..."],
        "negative_weak": [],
        "remove_single": [],
    },
    "언어 일관성": {
        "formal_strong": ["하겠습니다", "드립니다", "보겠습니다", "해주세요", "되겠습니다"],
        "formal_weak": ["습니다", "합니다", "입니다", "해요", "주세요"],
        "informal_strong": ["해봐", "하지", "되는 거야", "거든"],
        "informal_weak": ["해라", "하자", "봐", "있죠", "맞죠", "해"],
        "remove_single": [],
    },
    "학습 목표 안내": {
        "strong": ["오늘은", "이번 시간", "오늘 할", "해볼 거예요", "다룰 거예요", "배울 거예요", "세 가지 섹션", "먼저", "다음", "마지막으로"],
        "weak": ["오늘", "목표", "진행", "순서", "배워", "살펴보", "학습", "보겠습니다", "나눠서"],
        "remove_single": ["학습"],
    },
    "전날 복습 연계": {
        "strong": ["지난 시간에", "저번 시간", "지난주", "아까 했던", "이전에 배운", "복습하면", "기억나죠"],
        "weak": ["어제", "지난 시간", "이전", "복습", "앞서", "저번 시간"],
        "remove_single": ["앞서"],
    },
    "설명 순서": {
        "strong": ["먼저", "그다음", "다음으로", "이어서", "그 후", "마지막으로", "정리하면"],
        "weak": ["이제", "그러면", "넘어가서"],
        "remove_single": ["이제", "그러면"],
    },
    "핵심 내용 강조": {
        "strong": ["중요한 건", "핵심은", "꼭 기억", "주의할 점", "포인트는", "시험에", "실무에서 중요"],
        "weak": ["중요", "핵심", "꼭", "반드시", "포인트"],
        "remove_single": [],
    },
    "마무리 요약": {
        "strong": ["오늘 배운", "정리하면", "요약하면", "오늘 핵심은", "다시 보면", "다음 시간에는"],
        "weak": ["정리", "요약", "마무리", "여기까지", "끝내", "정리하면", "마치겠습니다"],
        "remove_single": ["쉬겠습니다", "수고하셨", "끝입니다", "마칩니다", "이상입니다"],
    },
    "개념 정의": {
        "strong": ["란", "라고 보면", "라고 부른다", "의 역할은", "의 의미는", "정확히는", "쉽게 말하면"],
        "weak": ["정의", "무엇인가", "라고 하는"],
        "remove_single": ["의미", "개념", "는", "이다"],
    },
    "비유 및 예시 활용": {
        "analogy_strong": ["마치", "비슷하게", "비유하자면", "쉽게 말해", "와 같다"],
        "analogy_weak": [],
        "example_strong": ["예를 들어", "예를 들면", "가령", "예를 하나 들면", "케이스로 보면"],
        "example_weak": ["예시"],
        "remove_single": ["처럼"],
    },
    "선행 개념 확인": {
        "strong": ["알고 있어야", "전제", "기본 개념", "기억나죠", "먼저 알아야", "알고 있다고 보고"],
        "weak": ["먼저", "기본적으로", "앞서", "이전에", "기존"],
        "remove_single": ["먼저", "기본적으로"],
    },
    "발화 속도 적절성": {
        "positive_strong": ["천천히 볼게요", "하나씩 볼게요"],
        "negative_strong": ["빨리 넘어갈게요", "급하게", "후루룩"],
        "weak": ["이제", "그다음", "다음으로", "그러면", "이어서", "넘어가서"],
        "remove_single": ["이제", "그러면"],
    },
    "예시 적절성": {
        "strong": ["실제로", "실무에서", "프로젝트에서", "현업에서는", "상황을 가정하면", "케이스"],
        "weak": ["실무", "업무", "프로젝트", "현업"],
        "remove_single": ["실제"],
    },
    "실습 연계": {
        "strong": ["직접 해보세요", "따라와 보세요", "실행해보세요", "입력해보세요", "구현해보세요", "방금 코드에서", "바꿔보세요", "같이 해봅시다"],
        "weak": ["실습", "해보", "따라", "눌러보", "직접", "구현", "해봅시다", "실행", "작성", "풀어", "해보세요", "한번 해보", "작성해", "코딩", "쿼리", "입력해", "써봐", "구현해"],
        "remove_single": ["구현", "풀어", "직접"],
    },
    "오류 대응": {
        "strong": ["오류가 나면", "에러가 나면", "안 될 때", "왜 안 되냐면", "원인은", "해결하려면", "고치려면", "로그를 보면", "다시 실행"],
        "weak": ["오류", "에러", "안 되", "문제", "다시 확인", "막히", "실패", "예외"],
        "remove_single": ["문제"],
    },
    "이해 확인 질문": {
        "strong": ["이해됐나요", "이해되셨죠", "여기까지 괜찮죠", "왜 그런지", "설명해볼 사람", "질문 있나요", "보이시죠", "아시겠죠"],
        "weak": ["됐어요", "괜찮죠", "아시겠죠", "맞죠", "보이시죠"],
        "remove_single": ["이해"],
    },
    "참여 유도": {
        "strong": ["직접 해보세요", "한번 써보세요", "같이 해봅시다", "누가 말해볼래요", "답해볼 사람", "적어보세요", "채팅에 써보세요", "생각해보세요"],
        "weak": ["해보세요", "눌러보세요", "따라", "한번 해보", "여러분도"],
        "remove_single": ["같이", "직접"],
    },
    "질문 응답 충분성": {
        "strong": ["좋은 질문", "질문하신", "답은", "그 이유는", "다시 설명하면", "정리해서 말하면", "질문에 대한 답", "왜냐하면"],
        "weak": ["질문", "답변", "설명드리", "물어보", "문의", "질문 있", "질문하면", "추가로", "보충해서", "한번 더"],
        "remove_single": ["다시"],
    },
}


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


def _dedupe_preserve(items: List[str]) -> List[str]:
    seen = set()
    result = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _split_long_span(span: str, max_tokens: int = 28) -> List[str]:
    tokens = span.split()
    if len(tokens) <= max_tokens:
        return [span]

    parts = []
    for start in range(0, len(tokens), max_tokens):
        chunk = " ".join(tokens[start : start + max_tokens]).strip()
        if chunk:
            parts.append(chunk)
    return parts or [span]


def _split_into_sentence_spans(text: str) -> List[str]:
    text = _normalize_text(text)
    if not text:
        return []

    rough_parts = [part.strip() for part in _PUNCT_SPLIT_RE.split(text) if part.strip()]
    if not rough_parts:
        rough_parts = [text]

    spans: List[str] = []
    for part in rough_parts:
        spans.extend(_split_long_span(part))
    return spans


def _matched_keywords(text: str, keywords: List[str]) -> List[str]:
    return _dedupe_preserve([kw for kw in keywords if kw and kw in text])


def _rule_keywords(rule_name: str, *groups: str) -> List[str]:
    rule = KEYWORD_RULES[rule_name]
    keywords: List[str] = []
    for group in groups:
        keywords.extend(rule.get(group, []))
    remove_single = set(rule.get("remove_single", []))
    return [kw for kw in _dedupe_preserve(keywords) if kw not in remove_single]


def _match_rule(text: str, rule_name: str, *groups: str) -> tuple[List[str], int, int]:
    rule = KEYWORD_RULES[rule_name]
    strong_pool: List[str] = []
    weak_pool: List[str] = []
    for group_name, values in rule.items():
        if not isinstance(values, list):
            continue
        if group_name == "strong" or group_name.endswith("_strong"):
            strong_pool.extend(values)
        if group_name == "weak" or group_name.endswith("_weak"):
            weak_pool.extend(values)

    strong_keywords = [kw for kw in _rule_keywords(rule_name, *groups) if kw in set(strong_pool)]
    weak_keywords = [kw for kw in _rule_keywords(rule_name, *groups) if kw not in strong_keywords]
    matched_strong = _matched_keywords(text, strong_keywords)
    matched_weak = _matched_keywords(text, weak_keywords)
    matched = _dedupe_preserve(matched_strong + matched_weak)
    return matched, len(matched_strong), len(matched_weak)


def _evaluate_rule(text: str, rule_name: str, *groups: str) -> tuple[bool, List[str], float, str]:
    matched, strong_count, weak_count = _match_rule(text, rule_name, *groups)
    if strong_count == 0 and weak_count == 0:
        return False, [], 0.0, "none"
    tier = "strong" if strong_count >= 1 else "weak"
    score = strong_count * 3.0 + weak_count * 1.2
    return True, matched, score, tier


def _is_question_like(text: str, matched_keywords: List[str]) -> bool:
    text = _normalize_text(text)
    return bool(_QUESTION_FORM_RE.search(text)) or ("?" in text)


def _is_participation_prompt(text: str, matched_keywords: List[str]) -> bool:
    return bool(_PARTICIPATION_FORM_RE.search(_normalize_text(text)))


def _is_question_answer_like(text: str, matched_keywords: List[str]) -> bool:
    text = _normalize_text(text)
    has_question = any(token in text for token in ["질문", "질문하신", "문의"])
    has_answer = any(token in text for token in ["답은", "그 이유는", "왜냐하면", "설명", "정리해서"])
    return has_answer or (has_question and ("답" in text or "설명" in text))


def _is_step_sequence(text: str, matched_keywords: List[str]) -> bool:
    step_markers = ["먼저", "그다음", "다음으로", "이어서", "그 후", "마지막으로", "정리하면"]
    return len(_matched_keywords(text, step_markers)) >= 2


def _is_summary_like(text: str, matched_keywords: List[str]) -> bool:
    text = _normalize_text(text)
    return any(token in text for token in ["오늘 배운", "오늘 핵심은", "정리하면", "요약하면", "다시 보면", "다음 시간에는"])


def _is_definition_like(text: str, matched_keywords: List[str]) -> bool:
    return bool(_DEFINITION_FORM_RE.search(_normalize_text(text)))


def _style_counts(text: str, formal_markers: List[str], informal_markers: List[str]) -> tuple[int, int]:
    text = _normalize_text(text)
    return _count_keywords(text, formal_markers), _count_keywords(text, informal_markers)


def _classify_style(formal_count: int, informal_count: int) -> str:
    if formal_count <= 0 and informal_count <= 0:
        return "none"
    if formal_count > 0 and informal_count <= 0:
        return "formal"
    if informal_count > 0 and formal_count <= 0:
        return "informal"
    return "mixed"


def _style_score(formal_count: int, informal_count: int) -> float:
    total = formal_count + informal_count
    if total <= 0:
        return 0.0
    return round(max(formal_count, informal_count) / total, 4)


def _build_style_entries(
    span_texts: List[str],
    segment_meta: Dict[str, Any],
    formal_markers: List[str],
    informal_markers: List[str],
    max_entries_per_label: int = 2,
) -> Dict[str, List[Dict[str, Any]]]:
    buckets: Dict[str, List[tuple[float, int, str, List[str], int, int]]] = {
        "formal": [],
        "informal": [],
        "mixed": [],
    }

    for idx, span_text in enumerate(span_texts):
        span_text = _normalize_text(span_text)
        if not span_text:
            continue
        formal_matches = _matched_keywords(span_text, formal_markers)
        informal_matches = _matched_keywords(span_text, informal_markers)
        formal_count = len(formal_matches)
        informal_count = len(informal_matches)
        style_label = _classify_style(formal_count, informal_count)
        if style_label == "none":
            continue
        matched_keywords = _dedupe_preserve(formal_matches + informal_matches)
        score = formal_count * 1.8 + informal_count * 1.8 + min(len(span_text.split()) / 16.0, 1.2)
        buckets[style_label].append((score, idx, span_text, matched_keywords, formal_count, informal_count))

    entries: Dict[str, List[Dict[str, Any]]] = {}
    for style_label, bucket in buckets.items():
        bucket.sort(key=lambda item: (-item[0], item[1]))
        entries[style_label] = [
            {
                "span_text": span_text,
                "evidence_type": "speech_style_evidence" if style_label != "mixed" else "style_shift_spans",
                "polarity": "supporting" if style_label != "mixed" else "contrary",
                "matched_keywords": matched_keywords,
                "sentence_index": idx,
                "local_score": round(score, 4),
                "context_before_hint": span_texts[idx - 1] if idx > 0 else "",
                "style_label": style_label,
                "formal_count": formal_count,
                "informal_count": informal_count,
                **segment_meta,
            }
            for score, idx, span_text, matched_keywords, formal_count, informal_count in bucket[:max_entries_per_label]
        ]
    return entries


def _dedupe_style_entries(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    deduped: List[Dict[str, Any]] = []
    seen = set()
    for entry in entries:
        key = (
            entry.get("span_text"),
            entry.get("segment_id"),
            entry.get("style_label"),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(entry)
    return deduped


def _relabel_style_entries(entries: List[Dict[str, Any]], evidence_type: str, polarity: str) -> List[Dict[str, Any]]:
    relabeled: List[Dict[str, Any]] = []
    for entry in entries:
        cloned = dict(entry)
        cloned["evidence_type"] = evidence_type
        cloned["polarity"] = polarity
        relabeled.append(cloned)
    return relabeled


def _make_entries(
    span_texts: List[str],
    evidence_type: str,
    polarity: str,
    segment_meta: Dict[str, Any],
    keywords: List[str] | None = None,
    rule_name: str | None = None,
    rule_groups: List[str] | None = None,
    validator=None,
    allow_weak_fallback: bool = True,
    require_keyword: bool = True,
    max_entries: int = 2,
) -> List[Dict[str, Any]]:
    scored = []
    fallback_scored = []

    for idx, span_text in enumerate(span_texts):
        span_text = _normalize_text(span_text)
        if not span_text:
            continue

        matched_keywords: List[str] = []
        keyword_score = 0.0
        candidate_tier = "none"
        if rule_name:
            matched_any, matched_keywords, keyword_score, candidate_tier = _evaluate_rule(
                span_text,
                rule_name,
                *(rule_groups or []),
            )
            if require_keyword and not matched_any:
                continue
        else:
            matched_keywords = _matched_keywords(span_text, keywords or [])
            if require_keyword and not matched_keywords:
                continue
            keyword_score = len(matched_keywords) * 2.0
            candidate_tier = "keyword" if matched_keywords else "none"

        validator_passed = True
        if validator and require_keyword:
            validator_passed = validator(span_text, matched_keywords)

        score = keyword_score + min(len(span_text.split()) / 16.0, 1.5)
        payload = (score, idx, span_text, matched_keywords)
        if validator_passed:
            scored.append(payload)
        elif rule_name and allow_weak_fallback and candidate_tier == "weak":
            fallback_scored.append(payload)

    if not scored and not require_keyword:
        for idx, span_text in enumerate(span_texts):
            span_text = _normalize_text(span_text)
            if not span_text:
                continue
            score = min(len(span_text.split()) / 16.0, 1.5)
            scored.append((score, idx, span_text, []))

    if not scored and fallback_scored:
        fallback_scored.sort(key=lambda item: (-item[0], item[1]))
        scored = fallback_scored[:1]

    scored.sort(key=lambda item: (-item[0], item[1]))

    entries: List[Dict[str, Any]] = []
    for score, idx, span_text, matched_keywords in scored[:max_entries]:
        entries.append(
            {
                "span_text": span_text,
                "evidence_type": evidence_type,
                "polarity": polarity,
                "matched_keywords": matched_keywords,
                "sentence_index": idx,
                "local_score": round(score, 4),
                "context_before_hint": span_texts[idx - 1] if idx > 0 else "",
                **segment_meta,
            }
        )
    return entries


def _calc_sentence_completion_ratio(text: str) -> float:
    """
    매우 러프한 휴리스틱:
    종결 어미/문장부호가 있으면 완결 문장 비율이 높다고 본다.
    """
    text = _normalize_text(text)
    if not text:
        return 0.0

    endings = [
        "입니다",
        "합니다",
        "해요",
        "됩니다",
        "있습니다",
        "보겠습니다",
        "할게요",
        "합니다.",
        "해요.",
        "입니다.",
        "죠.",
        "요.",
        "다.",
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
        "습니다",
        "합니다",
        "입니다",
        "해요",
        "보겠습니다",
        "하시죠",
        "되겠습니다",
        "주세요",
    ]
    informal_markers = [
        "해라",
        "하자",
        "봐",
        "해",
        "되는 거야",
        "거든",
        "있죠",
        "맞죠",
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

    filler_markers = _rule_keywords("불필요한 반복 표현", "strong", "weak")
    truncated_markers = _rule_keywords("발화 완결성", "negative_strong", "negative_weak")
    formal_markers = _rule_keywords("언어 일관성", "formal_strong", "formal_weak")
    informal_markers = _rule_keywords("언어 일관성", "informal_strong", "informal_weak")
    completion_markers = _rule_keywords("발화 완결성", "positive_strong", "positive_weak")
    filler_ratio = sum(float(discourse_markers.get(k, 0.0)) for k in filler_markers if k in discourse_markers)

    # 전체 텍스트(semantic chunk preview 기반)
    all_text = " ".join(_normalize_text(c.get("text_preview", "")) for c in chunks if c.get("text_preview"))
    intro_chunks = chunks[: max(1, min(3, len(chunks)))]
    tail_chunks = chunks[-max(1, min(3, len(chunks))) :] if chunks else []

    intro_text = " ".join(_normalize_text(c.get("text_preview", "")) for c in intro_chunks)
    tail_text = " ".join(_normalize_text(c.get("text_preview", "")) for c in tail_chunks)

    # 키워드 사전
    objective_keywords = _rule_keywords("학습 목표 안내", "strong", "weak")
    review_keywords = _rule_keywords("전날 복습 연계", "strong", "weak")
    summary_keywords = _rule_keywords("마무리 요약", "strong", "weak")
    definition_keywords = _rule_keywords("개념 정의", "strong", "weak")
    example_keywords = _rule_keywords("비유 및 예시 활용", "example_strong", "example_weak")
    analogy_keywords = _rule_keywords("비유 및 예시 활용", "analogy_strong", "analogy_weak")
    prerequisite_keywords = _rule_keywords("선행 개념 확인", "strong", "weak")
    emphasis_keywords = _rule_keywords("핵심 내용 강조", "strong", "weak")
    practical_example_keywords = _rule_keywords("예시 적절성", "strong", "weak")
    practice_keywords = _rule_keywords("실습 연계", "strong", "weak")
    error_keywords = _rule_keywords("오류 대응", "strong", "weak")
    understanding_keywords = _rule_keywords("이해 확인 질문", "strong", "weak")
    engagement_keywords = _rule_keywords("참여 유도", "strong", "weak")
    qa_keywords = _rule_keywords("질문 응답 충분성", "strong", "weak")
    transition_keywords = _rule_keywords("설명 순서", "strong", "weak")
    followup_keywords = ["추가로", "다시", "보충해서", "한번 더"]

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
        "speech_style_consistency": 0.85,
        "truncated_utterance_ratio": _calc_truncated_ratio(all_text),
        "style_shift_ratio": 0.02,
        "objective_intro_count": _count_keywords(intro_text, objective_keywords),
        "objective_intro_presence": 1 if _contains_any(intro_text, objective_keywords) else 0,
        "review_bridge_count": _count_keywords(intro_text, review_keywords),
        "review_bridge_presence": 1 if _contains_any(intro_text, review_keywords) else 0,
        "concept_example_practice_flow": 0.0,
        "structure_transition_clarity": 0.0,
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
    lecture_signals["structure_transition_clarity"] = round(min(1.0, transition_count / max(len(chunks), 1)), 4)

    segments = []
    segment_style_labels: List[str] = []
    segment_style_profiles: List[Dict[str, Any]] = []

    for i, chunk in enumerate(chunks):
        text = _normalize_text(chunk.get("text_preview", ""))
        sub_label = chunk.get("sub_label", "") or ""
        parent_label = chunk.get("parent_label", "") or ""
        seg_token_proxy = max(1, len(text.split()))
        sentence_spans = _split_into_sentence_spans(text)
        seg_formal_count, seg_informal_count = _style_counts(text, formal_markers, informal_markers)
        seg_style_label = _classify_style(seg_formal_count, seg_informal_count)
        seg_style_score = _style_score(seg_formal_count, seg_informal_count)

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
            "concept_example_practice_flow": 1.0
            if (definition_count > 0 and example_count_seg > 0 and practice_count > 0)
            else 0.5
            if ((definition_count > 0 and example_count_seg > 0) or (example_count_seg > 0 and practice_count > 0))
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
            "followup_presence": 1 if _contains_any(text, followup_keywords) else 0,
            "sentence_completion_ratio": _calc_sentence_completion_ratio(text),
            "speech_style_consistency": seg_style_score if seg_style_label != "none" else 0.85,
            "truncated_utterance_ratio": _calc_truncated_ratio(text),
            "style_shift_ratio": 1.0 if seg_style_label == "mixed" else 0.0,
            "rapid_transition_ratio": round(min(1.0, transition_count_seg / 5), 4),
            "style_label": seg_style_label,
            "formal_count": seg_formal_count,
            "informal_count": seg_informal_count,
        }

        segment_meta = {
            "segment_id": chunk.get("segment_id"),
            "chunk_id": chunk.get("chunk_id"),
            "start_ts": chunk.get("start_ts"),
            "end_ts": chunk.get("end_ts"),
            "parent_label": parent_label,
            "sub_label": sub_label,
        }
        style_entries_by_label = _build_style_entries(sentence_spans, segment_meta, formal_markers, informal_markers)

        objective_entries = _make_entries(
            sentence_spans,
            "objective_intro_spans",
            "supporting",
            segment_meta,
            rule_name="학습 목표 안내",
            rule_groups=["strong", "weak"],
        )
        review_entries = _make_entries(
            sentence_spans,
            "review_bridge_spans",
            "supporting",
            segment_meta,
            rule_name="전날 복습 연계",
            rule_groups=["strong", "weak"],
        )
        structure_flow_entries = _make_entries(
            sentence_spans,
            "structure_flow_spans",
            "supporting",
            segment_meta,
            keywords=_dedupe_preserve(transition_keywords + definition_keywords + example_keywords + practice_keywords),
            validator=_is_step_sequence,
        )
        transition_entries = _make_entries(
            sentence_spans,
            "transition_evidence",
            "supporting",
            segment_meta,
            rule_name="설명 순서",
            rule_groups=["strong", "weak"],
            validator=_is_step_sequence,
            allow_weak_fallback=True,
        )
        emphasis_entries = _make_entries(
            sentence_spans,
            "emphasis_spans",
            "supporting",
            segment_meta,
            rule_name="핵심 내용 강조",
            rule_groups=["strong", "weak"],
        )
        summary_entries = _make_entries(
            sentence_spans,
            "closing_summary_spans",
            "supporting",
            segment_meta,
            rule_name="마무리 요약",
            rule_groups=["strong", "weak"],
            validator=_is_summary_like,
            allow_weak_fallback=True,
        )
        definition_entries = _make_entries(
            sentence_spans,
            "definition_spans",
            "supporting",
            segment_meta,
            rule_name="개념 정의",
            rule_groups=["strong", "weak"],
            validator=_is_definition_like,
            allow_weak_fallback=True,
        )
        example_entries = _make_entries(
            sentence_spans,
            "example_spans",
            "supporting",
            segment_meta,
            rule_name="비유 및 예시 활용",
            rule_groups=["example_strong", "example_weak"],
        )
        analogy_entries = _make_entries(
            sentence_spans,
            "analogy_spans",
            "supporting",
            segment_meta,
            rule_name="비유 및 예시 활용",
            rule_groups=["analogy_strong", "analogy_weak"],
        )
        prerequisite_entries = _make_entries(
            sentence_spans,
            "prerequisite_bridge_spans",
            "supporting",
            segment_meta,
            rule_name="선행 개념 확인",
            rule_groups=["strong", "weak"],
        )
        practical_example_entries = _make_entries(
            sentence_spans,
            "practical_example_spans",
            "supporting",
            segment_meta,
            rule_name="예시 적절성",
            rule_groups=["strong", "weak"],
        )
        practice_entries = _make_entries(
            sentence_spans,
            "practice_transition_spans",
            "supporting",
            segment_meta,
            rule_name="실습 연계",
            rule_groups=["strong", "weak"],
            validator=_is_participation_prompt,
            allow_weak_fallback=True,
        )
        error_entries = _make_entries(
            sentence_spans,
            "error_response_spans",
            "supporting",
            segment_meta,
            rule_name="오류 대응",
            rule_groups=["strong", "weak"],
        )
        understanding_entries = _make_entries(
            sentence_spans,
            "understanding_check_spans",
            "supporting",
            segment_meta,
            rule_name="이해 확인 질문",
            rule_groups=["strong", "weak"],
            validator=_is_question_like,
            allow_weak_fallback=False,
        )
        question_entries = _make_entries(
            sentence_spans,
            "question_spans",
            "supporting",
            segment_meta,
            keywords=_dedupe_preserve(understanding_keywords + qa_keywords),
            validator=_is_question_like,
        )
        engagement_entries = _make_entries(
            sentence_spans,
            "engagement_spans",
            "supporting",
            segment_meta,
            rule_name="참여 유도",
            rule_groups=["strong", "weak"],
            validator=_is_participation_prompt,
            allow_weak_fallback=False,
        )
        qa_entries = _make_entries(
            sentence_spans,
            "qa_response_spans",
            "supporting",
            segment_meta,
            rule_name="질문 응답 충분성",
            rule_groups=["strong", "weak"],
            validator=_is_question_answer_like,
            allow_weak_fallback=False,
        )
        followup_entries = _make_entries(
            sentence_spans,
            "followup_spans",
            "supporting",
            segment_meta,
            keywords=followup_keywords,
            validator=_is_question_answer_like,
        )
        pace_entries = _make_entries(
            sentence_spans,
            "pace_evidence",
            "supporting",
            segment_meta,
            require_keyword=False,
            max_entries=1,
        )
        completion_entries = _make_entries(
            sentence_spans,
            "completion_evidence",
            "supporting",
            segment_meta,
            rule_name="발화 완결성",
            rule_groups=["positive_strong", "positive_weak"],
        )
        incomplete_entries = _make_entries(
            sentence_spans,
            "incomplete_sentence_spans",
            "contrary",
            segment_meta,
            rule_name="발화 완결성",
            rule_groups=["negative_strong", "negative_weak"],
        )
        style_support_entries = []
        style_shift_entries = list(style_entries_by_label.get("mixed", []))
        filler_entries = _make_entries(
            sentence_spans,
            "filler_spans",
            "contrary",
            segment_meta,
            rule_name="불필요한 반복 표현",
            rule_groups=["strong", "weak"],
        )
        repetition_entries = _make_entries(
            sentence_spans,
            "repetition_spans",
            "contrary",
            segment_meta,
            rule_name="불필요한 반복 표현",
            rule_groups=["strong", "weak"],
        )
        rapid_transition_entries = _make_entries(
            sentence_spans,
            "rapid_transition_spans",
            "contrary",
            segment_meta,
            rule_name="발화 속도 적절성",
            rule_groups=["negative_strong", "weak"],
        )

        if objective_intro_count <= 0:
            objective_entries = []
        if review_bridge_count <= 0:
            review_entries = []
        if seg_signals["concept_example_practice_flow"] <= 0:
            structure_flow_entries = []
        if transition_count_seg <= 0:
            transition_entries = []
        if emphasis_count_seg <= 0:
            emphasis_entries = []
        if summary_count <= 0:
            summary_entries = []
        if definition_count <= 0:
            definition_entries = []
        if example_count_seg <= 0:
            example_entries = []
        if analogy_count_seg <= 0:
            analogy_entries = []
        if prerequisite_count <= 0:
            prerequisite_entries = []
        if practical_example_count <= 0:
            practical_example_entries = []
        if practice_count <= 0:
            practice_entries = []
        if error_count <= 0:
            error_entries = []
        if understanding_count <= 0:
            understanding_entries = []
        if understanding_count <= 0 and qa_count <= 0:
            question_entries = []
        if understanding_count <= 0 and engagement_count <= 0:
            interaction_entries: List[Dict[str, Any]] = []
        else:
            interaction_entries = _make_entries(
                sentence_spans,
                "interaction_evidence",
                "supporting",
                segment_meta,
                keywords=_dedupe_preserve(understanding_keywords + engagement_keywords),
                validator=lambda text, matched: _is_question_like(text, matched) or _is_participation_prompt(text, matched),
            )
        if engagement_count <= 0:
            engagement_entries = []
        if qa_count <= 0:
            qa_entries = []
        if seg_signals["followup_presence"] <= 0:
            followup_entries = []
        if len(text.split()) <= 20:
            pace_entries = []
        if seg_signals["rapid_transition_ratio"] <= 0.2:
            rapid_transition_entries = []
        if seg_signals["sentence_completion_ratio"] >= 0.5:
            incomplete_entries = []
        if seg_signals["sentence_completion_ratio"] < 0.5:
            completion_entries = []
        if seg_signals["style_shift_ratio"] <= 0.2:
            style_shift_entries = []
        if seg_signals["speech_style_consistency"] <= 0.5:
            style_support_entries = []
        if filler_count_seg <= 0:
            filler_entries = []
        if filler_count_seg < 3:
            repetition_entries = []

        evidence = {
            "objective_intro_spans": objective_entries,
            "intro_evidence": objective_entries,
            "review_bridge_spans": review_entries,
            "bridge_evidence": review_entries,
            "structure_flow_spans": structure_flow_entries,
            "transition_evidence": transition_entries,
            "structure_evidence": transition_entries,
            "emphasis_spans": emphasis_entries,
            "highlight_evidence": emphasis_entries,
            "closing_summary_spans": summary_entries,
            "summary_evidence": summary_entries,
            "definition_spans": definition_entries,
            "concept_definition_evidence": definition_entries,
            "example_spans": example_entries,
            "example_evidence": example_entries,
            "analogy_spans": analogy_entries,
            "prerequisite_bridge_spans": prerequisite_entries,
            "prerequisite_evidence": prerequisite_entries,
            "practical_example_spans": practical_example_entries,
            "practical_example_evidence": practical_example_entries,
            "practice_transition_spans": practice_entries,
            "practice_evidence": practice_entries,
            "error_response_spans": error_entries,
            "error_evidence": error_entries,
            "understanding_check_spans": understanding_entries,
            "question_spans": question_entries,
            "interaction_evidence": interaction_entries,
            "engagement_spans": engagement_entries,
            "interaction_prompt_spans": engagement_entries,
            "engagement_evidence": engagement_entries,
            "qa_response_spans": qa_entries,
            "qa_evidence": qa_entries,
            "followup_spans": followup_entries,
            "pace_evidence": pace_entries,
            "rapid_transition_spans": rapid_transition_entries,
            "incomplete_sentence_spans": incomplete_entries,
            "completion_evidence": completion_entries,
            "style_shift_spans": style_shift_entries,
            "speech_style_evidence": style_support_entries,
            "filler_spans": filler_entries,
            "repetition_spans": repetition_entries,
            "language_expression_evidence": filler_entries,
        }

        segments.append(
            {
                "segment_id": chunk.get("segment_id"),
                "chunk_id": chunk.get("chunk_id"),
                "weight": chunk.get("utterance_count", 1) or 1,
                "signals": seg_signals,
                "evidence": evidence,
                "start_ts": chunk.get("start_ts"),
                "end_ts": chunk.get("end_ts"),
                "parent_label": parent_label,
                "sub_label": sub_label,
                "text_preview": text,
                "sentence_spans": sentence_spans,
            }
        )
        segment_style_labels.append(seg_style_label)
        segment_style_profiles.append(
            {
                "style_label": seg_style_label,
                "formal_count": seg_formal_count,
                "informal_count": seg_informal_count,
                "style_entries": style_entries_by_label,
            }
        )

    styled_labels = [label for label in segment_style_labels if label != "none"]
    formal_segments = sum(1 for label in styled_labels if label == "formal")
    informal_segments = sum(1 for label in styled_labels if label == "informal")
    mixed_segments = sum(1 for label in styled_labels if label == "mixed")
    styled_segments = len(styled_labels)

    if formal_segments >= informal_segments and formal_segments > 0:
        dominant_style = "formal"
        dominant_segments = formal_segments
    elif informal_segments > 0:
        dominant_style = "informal"
        dominant_segments = informal_segments
    else:
        dominant_style = "none"
        dominant_segments = 0

    major_style_ratio = round(_safe_div(dominant_segments, styled_segments), 4) if styled_segments else 0.85
    mixed_ratio = round(_safe_div(mixed_segments, styled_segments), 4) if styled_segments else 0.0
    style_switches = sum(1 for prev, curr in zip(styled_labels, styled_labels[1:]) if prev != curr)
    switch_ratio = round(_safe_div(style_switches, max(len(styled_labels) - 1, 1)), 4) if styled_labels else 0.0

    lecture_signals["speech_style_consistency"] = major_style_ratio
    lecture_signals["style_shift_ratio"] = round(min(1.0, mixed_ratio * 0.6 + switch_ratio * 0.4), 4)
    lecture_signals["style_major_ratio"] = major_style_ratio
    lecture_signals["style_mixed_ratio"] = mixed_ratio
    lecture_signals["style_switch_ratio"] = switch_ratio
    lecture_signals["dominant_style"] = dominant_style
    lecture_signals["formal_segment_ratio"] = round(_safe_div(formal_segments, styled_segments), 4) if styled_segments else 0.0
    lecture_signals["informal_segment_ratio"] = round(_safe_div(informal_segments, styled_segments), 4) if styled_segments else 0.0
    lecture_signals["mixed_segment_ratio"] = mixed_ratio

    for seg, style_profile in zip(segments, segment_style_profiles):
        style_entries = style_profile["style_entries"]
        style_label = style_profile["style_label"]
        supporting_style_entries: List[Dict[str, Any]] = []
        contrary_style_entries: List[Dict[str, Any]] = []

        if dominant_style in ("formal", "informal"):
            supporting_style_entries.extend(
                _relabel_style_entries(list(style_entries.get(dominant_style, []))[:1], "speech_style_evidence", "supporting")
            )
            contrary_style_entries.extend(
                _relabel_style_entries(list(style_entries.get("mixed", []))[:1], "style_shift_spans", "contrary")
            )
            opposite_style = "informal" if dominant_style == "formal" else "formal"
            contrary_style_entries.extend(
                _relabel_style_entries(list(style_entries.get(opposite_style, []))[:1], "style_shift_spans", "contrary")
            )
        else:
            contrary_style_entries.extend(
                _relabel_style_entries(list(style_entries.get("mixed", []))[:1], "style_shift_spans", "contrary")
            )

        seg["evidence"]["speech_style_evidence"] = _dedupe_style_entries(supporting_style_entries)
        seg["evidence"]["style_shift_spans"] = _dedupe_style_entries(contrary_style_entries)
        seg["signals"]["dominant_style"] = dominant_style
        seg["signals"]["style_major_ratio"] = major_style_ratio
        seg["signals"]["speech_style_consistency"] = _style_score(
            style_profile["formal_count"],
            style_profile["informal_count"],
        ) if style_label != "none" else major_style_ratio
        seg["signals"]["style_shift_ratio"] = 1.0 if style_label == "mixed" else (
            1.0 if dominant_style in ("formal", "informal") and style_label not in ("none", dominant_style) else 0.0
        )

    return {
        "lecture_signals": lecture_signals,
        "segments": segments,
    }
