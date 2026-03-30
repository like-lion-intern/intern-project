from __future__ import annotations

import json
import os
import re
import sys

from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

_api_key = os.getenv("GOOGLE_API_KEY")
if not _api_key:
    raise ValueError("GOOGLE_API_KEY가 .env에 설정되어 있지 않습니다.")

client = genai.Client(api_key=_api_key)
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

VALID_LABELS = {"strong", "neutral", "weak"}

SYSTEM_PROMPT = """당신은 강의 품질 진단 전문가입니다.

반드시 한국어만 사용하십시오.
응답의 모든 자연어 텍스트는 한국어여야 합니다.

절대 금지:
- 영어, 벵골어, 일본어, 중국어 등 외국어 문장
- 로마자 기반 설명 (e.g., "this shows", "it indicates")
- 번역투 어색한 문장

허용되는 예외:
1) JSON 키 이름
2) label 값: strong, neutral, weak
3) item_name (고정 항목명)
4) span_text (입력 원문 인용)

중요:
- reason 필드는 반드시 자연스러운 한국어 문장으로 작성
- 외국어가 한 글자라도 섞이면 실패한 응답

출력 규칙:
- 반드시 JSON 객체만 반환
- 마크다운, 코드블록, 설명문 절대 금지"""

ALL_ITEMS = [
    "불필요한 반복 표현", "발화 완결성", "언어 일관성",
    "학습 목표 안내", "전날 복습 연계", "설명 순서", "핵심 내용 강조", "마무리 요약",
    "개념 정의", "비유 및 예시 활용", "선행 개념 확인", "발화 속도 적절성",
    "예시 적절성", "실습 연계", "오류 대응",
    "이해 확인 질문", "참여 유도", "질문 응답 충분성",
]

FALLBACK = {
    "item_results": [
        {"item_name": name, "label": "neutral", "confidence": 0.5, "evidence": []}
        for name in ALL_ITEMS
    ]
}


FEATURE_KEY_KO = {
    "token_count": "전체 토큰 수",
    "utterance_count": "전체 발화 수",
    "question_count": "질문 수",
    "example_count": "예시 수",
    "practice_directive_ratio": "실습 지시 비율",
    "repetition_count": "반복 구문 횟수",
    "discourse_marker_per_1k_tokens": "담화표지어 밀도(1000토큰당)",

    "filler_ratio": "군더더기 표현 밀도",
    "repeated_phrase_ratio": "반복 표현 밀도",
    "sentence_completion_ratio": "문장 완결성 비율",
    "speech_style_consistency": "말투 일관성",
    "truncated_utterance_ratio": "말 끊김 비율",
    "style_shift_ratio": "말투 전환 비율",

    "objective_intro_count": "도입부 목표 안내 횟수",
    "objective_intro_presence": "도입부 목표 안내 존재 여부",
    "review_bridge_count": "복습 연계 횟수",
    "review_bridge_presence": "복습 연계 존재 여부",

    "concept_example_practice_flow": "개념-예시-실습 흐름 점수",
    "structure_transition_clarity": "구조 전환 명확성",

    "emphasis_count": "강조 표현 횟수",
    "emphasis_density": "강조 표현 밀도",

    "closing_summary_presence": "마무리 요약 존재 여부",
    "closing_summary_count": "마무리 요약 횟수",

    "definition_density": "정의 표현 밀도",
    "example_density": "예시 표현 밀도",
    "analogy_density": "비유 표현 밀도",

    "prerequisite_bridge_presence": "선행 개념 연결 존재 여부",
    "prerequisite_bridge_count": "선행 개념 연결 횟수",

    "practical_example_density": "실무 예시 밀도",
    "practice_transition_density": "실습 전환 밀도",

    "error_response_density": "오류 대응 밀도",
    "understanding_check_density": "이해 확인 밀도",
    "engagement_density": "참여 유도 밀도",
    "qa_response_density": "질문 응답 밀도",

    "question_quality_proxy": "질문 품질 추정치",
    "check_question_ratio": "이해 확인 질문 비율",
    "interaction_prompt_count": "상호작용 유도 횟수",
    "followup_presence": "추가 설명 존재 여부",
    "rapid_transition_ratio": "빠른 전환 비율",
}


def localize_keys(obj):
    if isinstance(obj, dict):
        localized = {}
        for k, v in obj.items():
            ko_key = FEATURE_KEY_KO.get(k, k)
            localized[ko_key] = localize_keys(v)
        return localized
    elif isinstance(obj, list):
        return [localize_keys(x) for x in obj]
    else:
        return obj


ALLOWED_ENGLISH_TOKENS = {"strong", "neutral", "weak"}

def sanitize_reason(text: str) -> str:
    if not text:
        return ""

    allowed_punct = set(" \t\n\r.,!?;:()[]{}-–—_/&%+*=~<>|@#`'\"·…")
    cleaned = []
    for ch in text:
        code = ord(ch)
        if 0xAC00 <= code <= 0xD7A3:  # Hangul
            cleaned.append(ch)
        elif 0x0041 <= code <= 0x005A or 0x0061 <= code <= 0x007A:  # English
            cleaned.append(ch)
        elif 0x0030 <= code <= 0x0039:  # number
            cleaned.append(ch)
        elif ch in allowed_punct:
            cleaned.append(ch)
        else:
            cleaned.append(" ")

    return " ".join("".join(cleaned).split())


def is_korean_text(text: str) -> bool:
    if not text or not text.strip():
        return True

    normalized = sanitize_reason(text).lower()

    # 허용된 영어 토큰만 제거
    for token in ALLOWED_ENGLISH_TOKENS:
        normalized = normalized.replace(token, "")

    cleaned = re.sub(r"[0-9\s\.,:;!\?\-\(\)\"'/%~·…]+", "", normalized)

    if not cleaned:
        return True

    total = len(cleaned)
    korean = len(re.findall(r"[가-힣ㄱ-ㅎㅏ-ㅣ]", cleaned))
    english = len(re.findall(r"[A-Za-z]", cleaned))
    korean_ratio = korean / total
    english_ratio = english / total

    return korean_ratio >= 0.8 and english_ratio <= 0.15


def safe_parse_json_object(raw_text: str) -> dict:
    raw_text = strip_markdown_codeblock(raw_text).strip()
    try:
        return json.loads(raw_text)
    except Exception:
        pass

    start = raw_text.find("{")
    end = raw_text.rfind("}")
    if start != -1:
        candidate = raw_text[start : end + 1] if (end != -1 and end > start) else (raw_text[start:] + "}")
        try:
            return json.loads(candidate)
        except Exception:
            if candidate.count('"') % 2 != 0:
                candidate = raw_text[start:] + '"}'
                return json.loads(candidate)
    raise ValueError(f"JSON object not found or invalid in response: {raw_text}")


def strip_markdown_codeblock(raw_text: str) -> str:
    raw_text = raw_text.strip()

    if raw_text.startswith("```"):
        lines = raw_text.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        raw_text = "\n".join(lines).strip()

    return raw_text


def _extract_json_object(raw_text: str) -> str:
    raw_text = strip_markdown_codeblock(raw_text).strip()
    if not raw_text:
        raise ValueError("empty response")

    start = raw_text.find("{")
    if start < 0:
        raise ValueError("json object start not found")

    depth = 0
    in_string = False
    escaped = False

    for idx in range(start, len(raw_text)):
        ch = raw_text[idx]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return raw_text[start : idx + 1]

    # 닫는 괄호를 못 찾았으면 마지막 JSON 시작부터 끝까지라도 반환해 후속 보정 시도
    return raw_text[start:].strip()


def _parse_curriculum_match_response(raw_text: str) -> dict:
    json_text = _extract_json_object(raw_text)

    try:
        parsed = json.loads(json_text)
    except json.JSONDecodeError:
        # 가장 흔한 실패는 reason 문자열이 길어져 일부가 잘린 경우다.
        score_match = re.search(r'"score"\s*:\s*(\d+)', json_text)
        reason_match = re.search(r'"reason"\s*:\s*"([\s\S]*)', json_text)
        if not score_match:
            raise

        reason = ""
        if reason_match:
            reason = reason_match.group(1)
            reason = reason.replace('\\"', '"').replace("\\n", " ")
            reason = reason.split('"}', 1)[0].strip()
            reason = reason.rstrip('",} ')

        parsed = {
            "score": int(score_match.group(1)),
            "reason": reason or "응답 파싱 보정",
        }

    if not isinstance(parsed, dict):
        raise ValueError("curriculum response is not a dict")
    if "score" not in parsed:
        raise ValueError("curriculum response missing score")
    if "reason" not in parsed:
        raise ValueError("curriculum response missing reason")

    return parsed


def generate_analysis_response(prompt: str):
    return client.models.generate_content(
        model=MODEL_NAME,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            temperature=0.1,
            max_output_tokens=16384,
        ),
    )


def analyze_items(
    features_data: dict,
    signals_output: dict,
    evidence_by_item: dict,
) -> dict:
    localized_features = localize_keys(features_data.get("features", {}))
    localized_lecture_signals = localize_keys(signals_output.get("lecture_signals", {}))

    features_json = json.dumps(
        localized_features,
        ensure_ascii=False,
        indent=2,
    )

    segments_json = json.dumps(
        [
            {
                "segment_id": seg.get("segment_id"),
                "parent_label": seg.get("parent_label"),
                "sub_label": seg.get("sub_label"),
                "utterance_count": seg.get("weight"),
                "text_preview": (seg.get("text_preview") or "")[:150],
            }
            for seg in signals_output.get("segments", [])
        ],
        ensure_ascii=False,
        indent=2,
    )

    # 프롬프트 크기 절감: evidence를 polarity별로 유지하되 각 그룹 상위 1개만 남긴다.
    trimmed_evidence = {}
    for item_name, evs in evidence_by_item.items():
        if isinstance(evs, dict):
            trimmed_evidence[item_name] = {
                "supporting_evidence": [
                    {
                        "span_text": ev.get("span_text", "")[:100],
                        "context_before": ev.get("context_before", [])[-1:],
                        "evidence_type": ev.get("evidence_type", ""),
                        "evidence_types": ev.get("evidence_types", []),
                        "polarity": ev.get("polarity", ""),
                        "rerank_score": ev.get("rerank_score", 0.0),
                    }
                    for ev in evs.get("supporting_evidence", [])[:1]
                ],
                "contrary_evidence": [
                    {
                        "span_text": ev.get("span_text", "")[:100],
                        "context_before": ev.get("context_before", [])[-1:],
                        "evidence_type": ev.get("evidence_type", ""),
                        "evidence_types": ev.get("evidence_types", []),
                        "polarity": ev.get("polarity", ""),
                        "rerank_score": ev.get("rerank_score", 0.0),
                    }
                    for ev in evs.get("contrary_evidence", [])[:1]
                ],
            }
        else:
            trimmed_evidence[item_name] = [
                {
                    "span_text": ev.get("span_text", "")[:100],
                    "context_before": ev.get("context_before", [])[-1:],
                }
                for ev in evs[:1]
            ]

    evidence_json = json.dumps(
        trimmed_evidence,
        ensure_ascii=False,
        indent=2,
    )

    lecture_signals_json = json.dumps(
        localized_lecture_signals,
        ensure_ascii=False,
        indent=2,
    )

    prompt = f"""[블록 1 — 정량적 피쳐 원본]
{features_json}

[블록 2 — 평가 항목 목록]
평가 항목 목록 (가중치: 높음=3, 중간=2, 낮음=1, 해당없음=0.5):
카테고리: 언어 표현 품질
  - 불필요한 반복 표현 (가중치 3)
  - 발화 완결성 (가중치 2)
  - 언어 일관성 (가중치 2)
카테고리: 강의 도입 및 구조
  - 학습 목표 안내 (가중치 2)
  - 전날 복습 연계 (가중치 2)
  - 설명 순서 (가중치 1)
  - 핵심 내용 강조 (가중치 2)
  - 마무리 요약 (가중치 0.5)
카테고리: 개념 설명 명확성
  - 개념 정의 (가중치 2)
  - 비유 및 예시 활용 (가중치 2)
  - 선행 개념 확인 (가중치 1)
  - 발화 속도 적절성 (가중치 3)
카테고리: 예시 및 실습 연계
  - 예시 적절성 (가중치 3)
  - 실습 연계 (가중치 3)
  - 오류 대응 (가중치 2)
카테고리: 수강생 상호작용
  - 이해 확인 질문 (가중치 3)
  - 참여 유도 (가중치 3)
  - 질문 응답 충분성 (가중치 2)

[블록 3 — segments 전체]
{segments_json}

[블록 4 — item별 evidence]
{evidence_json}

[블록 5 — 시그널 힌트]
이 값은 보조 힌트입니다.
{lecture_signals_json}

다음 지침에 따라 각 item을 분석하십시오:

1. 분석의 주된 근거는 정량적 피쳐(features)와 실제 발화 텍스트(evidence의 span_text, context)입니다.
   시그널(signals)은 수치 힌트로만 참고하고, 최종 판단은 실제 발화 내용과 정량 피쳐를 우선합니다.
   supporting_evidence는 긍정 근거, contrary_evidence는 문제 근거이므로 polarity를 구분해서 해석하십시오.

2. 정량적 피쳐에서 아래 수치를 반드시 확인하고 분석에 반영합니다:
   - 담화표지어 밀도(1000토큰당): 높을수록 불필요한 반복 표현 취약
   - 반복 구문 횟수: 높을수록 불필요한 반복 표현 취약
   - 질문 수: 낮을수록 이해 확인 질문·참여 유도 취약
   - 예시 수: 낮을수록 비유 및 예시 활용·예시 적절성 취약
   - 실습 지시 비율: 낮을수록 실습 연계 취약

3. sub_label에 따라 분석 비중을 다르게 적용합니다:

   [practice_explanation — 설명하며 실습 유도하는 구간]
   중점 item: 불필요한 반복 표현, 발화 완결성, 개념 정의, 비유 및 예시 활용, 핵심 내용 강조, 발화 속도 적절성

   [practice_instruction — 수강생에게 직접 실습 지시하는 구간]
   중점 item: 실습 연계, 참여 유도, 이해 확인 질문, 오류 대응, 질문 응답 충분성

   [practice_example — 강사가 예시를 직접 시연하는 구간]
   중점 item: 예시 적절성, 비유 및 예시 활용, 실습 연계

   [도입부 — seg_01, seg_02]
   추가 중점: 학습 목표 안내, 전날 복습 연계

   [마무리부 — 마지막 segment]
   추가 중점: 마무리 요약
   단, 마지막 segment의 실제 발화가 DB 설치 안내로 전환된 경우 명시적 요약이 없을 수 있음.
   억지로 요약 발화를 찾지 말고 실제 발화 내용 그대로 평가.

   [평가 의미가 낮은 item]
   - 설명 순서: 전체가 실습 유도 흐름이므로 개념→예시→실습 순서 분리가 불명확. 이 점을 반드시 고려.
   - 선행 개념 확인: 실습 중심 강의에서 없다고 해서 무조건 weak로 판단하지 않음.
   - 마무리 요약: 이 강의 구조에서 평가가 어려움.

4. label 결정 기준:
   - "weak":
     다음 중 하나라도 해당하면 우선적으로 부여합니다.
     1) 핵심 정량 지표가 명확히 취약함
     2) evidence에서 실제 문제 발화, 부족한 설명, 상호작용 부족, 반복 표현 등이 확인됨
     3) 해당 item이 이 강의 맥락에서 중요한 항목인데 긍정 근거가 거의 없음

   - "neutral":
     긍정과 부정이 혼재하거나, 근거가 부족하여 weak 또는 strong으로 단정하기 어려운 경우에만 부여합니다.
     neutral은 소극적으로 사용하십시오.

   - "strong":
     긍정 신호가 분명하고 evidence에서도 실제로 잘 수행된 발화가 확인되는 경우에만 부여합니다.

   - 가중치가 높은 항목(가중치 3)은 문제 신호가 확인되면 neutral보다 weak를 우선 검토하십시오.
   - 특히 불필요한 반복 표현, 예시 적절성, 실습 연계, 이해 확인 질문, 참여 유도는
     부정 신호가 확인될 경우 더 엄격하게 평가하십시오.

5. confidence: 0.0 ~ 1.0, 해당 label 판단의 확신 정도

6. language rules:
   - reason은 반드시 한국어로만 작성합니다.
   - label 값으로 사용하는 strong, neutral, weak 외의 영어, 벵골어, 일본어, 중국어 등 다른 언어를 절대 혼용하지 마십시오.
   - 정량적 피쳐에 명시된 수치를 인용할 때는 반드시 features 블록에 있는 값 그대로만 사용하고 임의로 수치를 만들지 마십시오.
   - reason에서는 영문 feature key를 그대로 쓰지 말고 반드시 한국어 표현으로 풀어 쓰십시오.
   - 예:
     "question_count가 낮다" 대신 "질문 수가 적다"
     "example_count가 낮다" 대신 "예시 수가 적다"
     "practice_directive_ratio가 낮다" 대신 "실습 지시 비율이 낮다"
     "discourse_marker_per_1k_tokens가 높다" 대신 "담화표지어 밀도가 높다"
   - span_text, context_before는 원문 인용이므로 비한국어가 포함될 수 있으나,
     반드시 reason만큼은 100% 한국어 문장이어야 합니다.
   - reason에 strong, neutral, weak를 제외한 영문 표현이 들어가면 실패입니다.
   - reason은 어색한 번역투 문장보다 자연스러운 한국어 설명문으로 작성하십시오.

7. 응답은 아래 JSON 구조만 반환합니다. support_strength 필드는 절대 포함하지 않습니다:
{{
  "item_results": [
    {{
      "item_name": "...",
      "label": "weak",
      "confidence": 0.78,
      "evidence": [
        {{
          "span_text": "...",
          "context_before": ["..."],
          "reason": "..."
        }}
      ]
    }}
  ]
}}"""

    last_error = None
    working_prompt = prompt

    for attempt in range(2):
        try:
            response = generate_analysis_response(working_prompt)
            parsed = safe_parse_json_object(response.text)

            if not isinstance(parsed, dict):
                raise ValueError("LLM output is not a dict")
            if "item_results" not in parsed or not isinstance(parsed["item_results"], list):
                raise ValueError("LLM output missing item_results")

            result_map = {}

            for item in parsed["item_results"]:
                if not isinstance(item, dict):
                    raise ValueError("LLM item is not a dict")

                item_name = item.get("item_name")
                label = item.get("label")
                confidence = item.get("confidence")
                evidence = item.get("evidence", [])

                if item_name not in ALL_ITEMS:
                    raise ValueError(f"Unknown item_name in LLM output: {item_name}")
                if label not in VALID_LABELS:
                    raise ValueError(f"Invalid label in LLM output: {label}")
                if not isinstance(confidence, (int, float)):
                    raise ValueError("Invalid confidence in LLM output")
                if not isinstance(evidence, list):
                    raise ValueError("Invalid evidence in LLM output")

                cleaned_evidence = []
                for ev in evidence[:3]:
                    if not isinstance(ev, dict):
                        raise ValueError("Evidence entry is not a dict")
                    if "support_strength" in ev:
                        raise ValueError("support_strength is not allowed")

                    reason = sanitize_reason(str(ev.get("reason", "")))
                    if not is_korean_text(reason):
                        raise ValueError(f"Non-Korean reason detected: {reason}")

                    cleaned_evidence.append({
                        "span_text": ev.get("span_text", ""),
                        "context_before": ev.get("context_before", []),
                        "reason": reason,
                    })

                result_map[item_name] = {
                    "item_name": item_name,
                    "label": label,
                    "confidence": float(confidence),
                    "evidence": cleaned_evidence,
                }

            if len(result_map) != len(ALL_ITEMS):
                raise ValueError(
                    f"Missing items in LLM output: got {len(result_map)}, expected {len(ALL_ITEMS)}"
                )

            return {
                "item_results": [result_map[item_name] for item_name in ALL_ITEMS]
            }

        except Exception as e:
            last_error = e
            working_prompt += """

[재강조]
이전 응답은 언어 규칙 또는 출력 형식을 위반했습니다.
모든 reason은 반드시 한국어 완전한 문장으로 작성하십시오.
영어, 벵골어, 일본어, 중국어 등 한국어 이외의 문자가 포함되면 실패입니다.
영문 feature key를 그대로 쓰지 말고 반드시 한국어 표현으로 바꿔 설명하십시오.
JSON 객체만 반환하십시오.
"""

    raise last_error


def analyze_curriculum_match(
    curriculum: dict,
    signals_output: dict,
) -> dict:
    """
    커리큘럼 content와 실제 강의 segment 내용의 일치도를 LLM으로 분석.
    반환: {"score": int(0~100), "reason": str}
    curriculum이 None이면 {"score": None, "reason": "커리큘럼 정보 없음"} 반환.
    """
    if not curriculum:
        return {"score": None, "reason": "커리큘럼 정보 없음"}

    contents_str = ", ".join(curriculum.get("contents", []))
    subject = curriculum.get("subject", "")
    course_name = curriculum.get("course_name", "")

    segments_json = json.dumps(
        [
            {
                "segment_id": seg.get("segment_id"),
                "sub_label": seg.get("sub_label"),
                "text_preview": (seg.get("text_preview") or "")[:150],
            }
            for seg in signals_output.get("segments", [])
        ],
        ensure_ascii=False,
        indent=2,
    )

    prompt = f"""당신은 강의 품질 진단 전문가입니다.

아래는 이 강의의 커리큘럼 계획입니다:
- 과정명: {course_name}
- 과목: {subject}
- 계획된 학습 내용: {contents_str}

아래는 실제 강의에서 발화된 내용 (segment별 텍스트 미리보기)입니다:
{segments_json}

위 실제 강의 내용이 커리큘럼에서 계획한 학습 내용과 얼마나 일치하는지 평가하십시오.

평가 기준:
- 90~100점: 계획된 내용이 강의에서 충실히 다뤄짐
- 70~89점: 대부분 일치하나 일부 내용 누락 또는 약간 벗어남
- 50~69점: 절반 정도 일치, 관련 있으나 다른 내용도 상당히 포함
- 30~49점: 커리큘럼과 부분적으로만 연관, 다른 내용이 많음
- 0~29점: 커리큘럼과 거의 관련 없는 내용이 강의됨

반드시 아래 JSON 형식으로만 응답하십시오. 마크다운 코드블록 없이:
{{"score": 85, "reason": "한국어로 작성된 이유. 어떤 내용이 일치하고 어떤 내용이 다른지 구체적으로 서술."}}"""

    last_error = None
    working_prompt = prompt

    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=working_prompt,
                config=types.GenerateContentConfig(
                    temperature=0.1,
                    max_output_tokens=512,
                    response_mime_type="application/json",
                ),
            )
            parsed = _parse_curriculum_match_response(response.text)

            score = int(parsed.get("score", 0))
            reason = str(parsed.get("reason", "")).strip()

            if not reason:
                reason = "일치도 판단 사유가 비어 있습니다."

            return {
                "score": max(0, min(100, score)),
                "reason": reason,
            }
        except Exception as e:
            last_error = e
            working_prompt += """

[재강조]
이전 응답은 JSON 형식이 깨졌습니다.
반드시 아래 형식의 JSON 객체 하나만 반환하십시오.
{"score": 85, "reason": "한국어 설명"}
추가 설명, 코드블록, 줄바꿈 설명문을 넣지 마십시오.
"""

    try:
        print(
            f"[llm_analysis] 커리큘럼 일치도 분석 실패: {type(last_error).__name__}: {last_error}",
            file=sys.stderr,
        )
    except Exception:
        pass
    return {"score": None, "reason": "분석 실패"}


def run_analysis(
    features_data: dict,
    signals_output: dict,
    evidence_by_item: dict,
) -> dict:
    try:
        return analyze_items(features_data, signals_output, evidence_by_item)
    except Exception as e:
        print(
            f"[llm_analysis] LLM 분석 실패, fallback 사용: {type(e).__name__}: {e}",
            file=sys.stderr,
        )
        return {
            "item_results": [
                {
                    "item_name": item["item_name"],
                    "label": item["label"],
                    "confidence": item["confidence"],
                    "evidence": item["evidence"],
                }
                for item in FALLBACK["item_results"]
            ]
        }
