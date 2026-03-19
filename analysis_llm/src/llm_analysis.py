# llm_analysis.py
from __future__ import annotations

import json
import os
import time
from typing import Dict, Any, Tuple, List

try:
    import google.generativeai as genai
except ImportError:
    genai = None

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


PROMPT_TEMPLATE = """
You are an expert AI instructional analyst.
Your task is to analyze lecture-level heuristic results and evidence, then refine them into a final instructional quality report.

[Lecture Context Data]
{categories_json}

Your strict responsibility is to output ONLY a JSON document.
Do not write markdown blocks. Output raw JSON only.

--------------------------------------------------
### CORE EVALUATION PRINCIPLE (VERY IMPORTANT)

You are NOT evaluating surface signals.
You are evaluating **instructional quality (교육적 질)**.

For every item, judge:
- Does this actually help learning?
- Does it improve understanding, retention, or engagement?
- Or is it just superficial / habitual / weak?

--------------------------------------------------
### MANDATORY INTERPRETATION RULES

1. Heuristic score is the baseline, but not the verdict.
- Each item's `heuristic_score` is the rule-based baseline.
- Start from it, but DO NOT mechanically keep it.
- If pedagogical quality is clearly stronger or weaker than the heuristic baseline, adjust the score actively.
- Small but meaningful adjustment (±0.2 ~ ±0.7) is encouraged when evidence quality clearly supports it.
- Keep the score unchanged only when the evidence is genuinely ambiguous or mixed.
- Maximum adjustment per item: ±1.5
- Final score must stay within [1.0, 5.0]

2. Evidence must be interpreted with pedagogical context.
- Do NOT reward mere keyword presence.
- Judge whether the evidence actually performs the intended educational function.
- If evidence is vague, habitual, or filler-like → DO NOT over-score.

3. Labels are hints, text is truth.
- Parent/sub labels are priors only.
- If label and text conflict, prioritize text evidence.

4. Absence must be interpreted contextually.
- Missing 목표 안내 at the opening is severe.
- Missing 마무리 요약 at the ending is meaningful.
- Missing 예시 in explanation-heavy instruction is meaningful.
- Missing 실습 연결 in practice-oriented lecture is meaningful.

--------------------------------------------------
### FUNCTIONAL QUALITY EVALUATION CRITERIA (핵심)

You MUST evaluate quality, not existence.

Examples:

- 이해 확인 질문:
  BAD → "맞죠?", "되셨죠?" (형식적 확인)
  GOOD → 학습자가 실제로 생각/회상하도록 유도하는 질문

- 비유 및 예시:
  BAD → 개념과 연결이 약한 예시
  GOOD → 개념 이해를 명확하게 도와주는 예시

- 개념 정의:
  BAD → 모호하거나 순환적인 설명
  GOOD → 개념의 경계를 명확히 하는 구조적 정의

- 실습 연계:
  BAD → "해보세요"만 있고 구체성 없음
  GOOD → 실제 행동으로 이어지는 명확한 지시

- 반복 표현:
  BAD → 습관적 filler ("이제", "어", "그냥")
  GOOD → 의도적 강조로 학습에 기여

--------------------------------------------------
### ITEM INTERPRETATION RULE (중요)

Each item represents a **specific teaching function**.

You MUST:
- Understand what the item is trying to achieve pedagogically
- Evaluate whether the lecture actually achieves that function

DO NOT:
- Treat items as keyword detection
- Treat signals as direct truth

Signals = hints  
Evidence = partial proof  
Final judgement = YOUR responsibility

--------------------------------------------------
### CONTEXT INTERPRETATION RULE

- Do NOT interpret a sentence in isolation.
- Infer meaning using surrounding flow.
- Interpret short expressions ("맞죠?", "자") in context.

--------------------------------------------------
### OUTPUT LANGUAGE

- ALL output must be in natural Korean
- This includes:
  - overall_summary
  - category_summary
  - reason
  - adjustment_reason
  - strengths / weaknesses / improvements
  - improvement_tip

--------------------------------------------------
### SCORE STRUCTURE

- category:
  - heuristic_score
  - final_score

- item:
  - heuristic_score
  - final_score

--------------------------------------------------
### EVIDENCE HANDLING

- Use reranked evidence as primary support
- Select 2~3 key evidence lines
- If evidence implies absence:
  → explain naturally in Korean

### WEAK-EVIDENCE ITEM RULE

For some items, reranked text evidence may be only partially representative.
For those items, rely more on:
- aggregated_signals
- signal_subscores
- item_context
- overall pedagogical function

Especially do NOT over-rely on single evidence excerpts for:
- 발화 완결성
- 언어 일관성
- 발화 속도 적절성
- 설명 순서
- 이해 확인 질문
- 참여 유도
- 질문 응답 충분

For these items, use evidence as support, but let the final judgement depend more on functional quality and aggregate patterns.

--------------------------------------------------
### OUTPUT JSON SCHEMA

{{
  "overall_summary": "string",
  "category_results": [
    {{
      "category_name": "string",
      "heuristic_score": float,
      "final_score": float,
      "category_summary": "string",
      "items": [
        {{
          "item_name": "string",
          "heuristic_score": float,
          "final_score": float,
          "adjustment_reason": "string",
          "reason": "string",
          "selected_evidence": ["string"],
          "improvement_tip": "string"
        }}
      ],
      "strengths": ["string"],
      "weaknesses": ["string"],
      "improvements": ["string"]
    }}
  ],
  "overall_strengths": ["string"],
  "overall_weaknesses": ["string"],
  "priority_improvements": ["string"]
}}
"""


def clamp_score(score: float, min_val: float = 1.0, max_val: float = 5.0) -> float:
    return max(min_val, min(max_val, score))


def extract_json_from_text(text: str) -> str:
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()


def setup_gemini() -> bool:
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key or genai is None:
        return False

    genai.configure(api_key=api_key)
    return True


def _build_fallback_result(prompt_packet: Dict[str, Any]) -> Dict[str, Any]:
    categories = prompt_packet.get("categories", [])
    category_results = []

    overall_strengths = []
    overall_weaknesses = []
    priority_improvements = []

    for cat in categories:
        category_name = cat.get("category_name", "")
        heuristic_score = float(cat.get("category_context", {}).get("category_heuristic_score", 3.0))
        items_out = []

        strengths = []
        weaknesses = []
        improvements = []

        item_scores = []

        for item in cat.get("items", []):
            h = float(item.get("heuristic_score", 3.0))
            item_scores.append(h)

            evidence = item.get("top_evidence", [])[:3]
            if not evidence:
                evidence = ["근거 문장이 충분히 추출되지 않음"]

            if h >= 4.0:
                adjustment_reason = "정량 신호와 추출 근거가 전반적으로 일치하여 휴리스틱 점수를 유지함"
                reason = f"{item.get('item_name')} 항목은 관련 신호가 안정적으로 관찰되며, 추출된 근거도 기능 수행을 뒷받침함"
                strengths.append(f"{item.get('item_name')} 수행이 비교적 안정적임")
            elif h >= 3.0:
                adjustment_reason = "정량 신호는 보통 수준이며, 근거도 대체로 이에 부합하여 휴리스틱 점수를 유지함"
                reason = f"{item.get('item_name')} 항목은 기본 수준은 확보했지만 기능적 선명도는 더 보강될 여지가 있음"
                weaknesses.append(f"{item.get('item_name')}의 기능적 선명도가 다소 약함")
                improvements.append(f"{item.get('item_name')} 관련 표현을 더 명시적으로 제시하기")
            else:
                adjustment_reason = "정량 신호가 낮고 근거도 제한적이어서 낮은 점수를 유지함"
                reason = f"{item.get('item_name')} 항목은 관련 표현 또는 기능적 수행 근거가 충분하지 않음"
                weaknesses.append(f"{item.get('item_name')} 근거가 부족함")
                improvements.append(f"{item.get('item_name')}를 드러내는 설명 구조를 보강하기")

            items_out.append({
                "item_name": item.get("item_name"),
                "heuristic_score": round(h, 2),
                "final_score": round(clamp_score(h), 2),
                "adjustment_reason": adjustment_reason,
                "reason": reason,
                "selected_evidence": evidence,
                "improvement_tip": f"{item.get('item_name')}의 기능이 더 분명하게 드러나도록 구체적 표현과 구조를 보강해줘.",
            })

        final_score = round(sum(item_scores) / len(item_scores), 2) if item_scores else round(heuristic_score, 2)

        if not strengths:
            strengths = [f"{category_name}에서 일부 기본 요소는 확인됨"]
        if not weaknesses:
            weaknesses = [f"{category_name}의 세부 항목 간 편차를 추가 점검할 필요가 있음"]
        if not improvements:
            improvements = [f"{category_name}의 핵심 기능이 더 명시적으로 드러나도록 구성 보강이 필요함"]

        category_results.append({
            "category_name": category_name,
            "heuristic_score": round(heuristic_score, 2),
            "final_score": round(final_score, 2),
            "category_summary": f"{category_name}은 전반적으로 휴리스틱 기준과 유사한 수준으로 해석되며, 일부 항목은 표현의 명확성을 더 보강할 필요가 있음.",
            "items": items_out,
            "strengths": strengths[:3],
            "weaknesses": weaknesses[:3],
            "improvements": improvements[:3],
        })

        overall_strengths.extend(strengths[:1])
        overall_weaknesses.extend(weaknesses[:1])
        priority_improvements.extend(improvements[:1])

    return {
        "overall_summary": "강의 전반을 보면 일부 항목은 비교적 안정적으로 수행되지만, 구조적 안내와 기능적 명확성은 항목별 편차가 존재함.",
        "category_results": category_results,
        "overall_strengths": overall_strengths[:5] or ["일부 교수행동은 안정적으로 관찰됨"],
        "overall_weaknesses": overall_weaknesses[:5] or ["항목별 수행 편차가 존재함"],
        "priority_improvements": priority_improvements[:5] or ["핵심 구조와 설명 기능을 더 명시적으로 드러내기"],
    }


def _postprocess_result(prompt_packet: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
    input_categories = prompt_packet.get("categories", [])
    input_cat_map = {c.get("category_name"): c for c in input_categories}

    fixed_category_results = []

    for cat in result.get("category_results", []):
        category_name = cat.get("category_name", "")
        src_cat = input_cat_map.get(category_name, {})
        heuristic_score = float(src_cat.get("category_context", {}).get("category_heuristic_score", 3.0))

        src_items = {i.get("item_name"): i for i in src_cat.get("items", [])}
        fixed_items = []
        item_final_scores = []

        for item in cat.get("items", []):
            item_name = item.get("item_name", "")
            src_item = src_items.get(item_name, {})
            item_h = float(src_item.get("heuristic_score", item.get("heuristic_score", 3.0)))
            item_f = float(item.get("final_score", item.get("item_score", item_h)))
            item_f = clamp_score(item_f)

            # heuristic과 완전히 같을 때도 LLM reason이 강하면 소폭 조정 허용
            reason_text = str(item.get("reason", "")) + " " + str(item.get("adjustment_reason", ""))

            negative_cues = ["부족", "미흡", "형식적", "약함", "제한적", "불충분", "모호", "방해"]
            positive_cues = ["우수", "명확", "효과적", "안정적", "자연스럽", "충분", "도움"]

            if abs(item_f - item_h) < 0.01:
                neg_hit = sum(1 for cue in negative_cues if cue in reason_text)
                pos_hit = sum(1 for cue in positive_cues if cue in reason_text)

                if neg_hit >= 2 and item_h >= 2.0:
                    item_f = clamp_score(item_h - 0.3)
                elif pos_hit >= 2 and item_h <= 4.7:
                    item_f = clamp_score(item_h + 0.3)

            selected_evidence = item.get("selected_evidence") or src_item.get("top_evidence") or []
            if not isinstance(selected_evidence, list):
                selected_evidence = [str(selected_evidence)]

            fixed_items.append({
                "item_name": item_name,
                "heuristic_score": round(item_h, 2),
                "final_score": round(item_f, 2),
                "adjustment_reason": item.get("adjustment_reason", "휴리스틱 점수를 기준으로 근거를 검토해 조정 여부를 판단함"),
                "reason": item.get("reason", f"{item_name} 항목에 대한 기능적 수행을 근거 중심으로 평가함"),
                "selected_evidence": selected_evidence[:3],
                "improvement_tip": item.get("improvement_tip", f"{item_name} 관련 표현과 구조를 더 명확히 보강해줘."),
            })
            item_final_scores.append(item_f)

        category_final = float(cat.get("final_score", cat.get("category_score", 0.0)))
        if not category_final:
            category_final = sum(item_final_scores) / len(item_final_scores) if item_final_scores else heuristic_score
        category_final = clamp_score(category_final)

        strengths = cat.get("strengths", [])
        weaknesses = cat.get("weaknesses", [])
        improvements = cat.get("improvements", [])

        if isinstance(strengths, str):
            strengths = [strengths]
        if isinstance(weaknesses, str):
            weaknesses = [weaknesses]
        if isinstance(improvements, str):
            improvements = [improvements]

        fixed_category_results.append({
            "category_name": category_name,
            "heuristic_score": round(heuristic_score, 2),
            "final_score": round(category_final, 2),
            "category_summary": cat.get("category_summary", cat.get("summary", f"{category_name}에 대한 종합 평가")),
            "items": fixed_items,
            "strengths": strengths[:3],
            "weaknesses": weaknesses[:3],
            "improvements": improvements[:3],
        })

    return {
        "overall_summary": result.get("overall_summary", "강의 전반에 대한 종합 평가"),
        "category_results": fixed_category_results,
        "overall_strengths": result.get("overall_strengths", [])[:5],
        "overall_weaknesses": result.get("overall_weaknesses", [])[:5],
        "priority_improvements": result.get("priority_improvements", [])[:5],
    }


def analyze_with_llm(prompt_packet: Dict[str, Any], max_retries: int = 2) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    debug_raw_responses: List[str] = []

    if not setup_gemini():
        fallback = _build_fallback_result(prompt_packet)
        return fallback, {
            "success": False,
            "error": "LLM_NOT_CONFIGURED",
            "raw_responses": debug_raw_responses,
        }

    model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    model = genai.GenerativeModel(
        model_name,
        generation_config={"response_mime_type": "application/json"},
    )

    prompt = PROMPT_TEMPLATE.format(
        categories_json=json.dumps(prompt_packet.get("categories", []), ensure_ascii=False, indent=2)
    )

    for attempt in range(max_retries + 1):
        try:
            response = model.generate_content(prompt)
            raw_text = response.text
            debug_raw_responses.append(raw_text)

            clean_json = extract_json_from_text(raw_text)
            parsed_data = json.loads(clean_json)
            final_result = _postprocess_result(prompt_packet, parsed_data)

            return final_result, {
                "success": True,
                "raw_responses": debug_raw_responses,
                "model_name": model_name,
            }

        except Exception as e:
            debug_raw_responses.append(f"[attempt {attempt+1} error] {str(e)}")
            if attempt < max_retries:
                time.sleep(2)

    fallback = _build_fallback_result(prompt_packet)
    return fallback, {
        "success": False,
        "error": "LLM_MAX_RETRIES_EXCEEDED",
        "raw_responses": debug_raw_responses,
    }