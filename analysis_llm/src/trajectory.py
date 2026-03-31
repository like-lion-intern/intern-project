import os
import re
import json
import csv
import sys
import argparse

from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

_api_key = os.getenv("GOOGLE_API_KEY")
if not _api_key:
    raise ValueError("GOOGLE_API_KEY가 .env에 설정되어 있지 않습니다.")

client = genai.Client(api_key=_api_key)
TRAJECTORY_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

SYSTEM_PROMPT = """당신은 강의 품질 분석 전문가입니다.

주어진 전체 강의 날짜별 분석 데이터를 바탕으로 강사의 강의 궤적을 분석합니다.

반드시 한국어만 사용하십시오.
반드시 JSON 객체만 반환하십시오. 마크다운, 코드블록, 설명문을 포함하지 마십시오."""

ANALYSIS_GUIDELINES = """위 데이터를 바탕으로 아래 4가지를 분석하십시오.

[분석 1] 강사 취약 패턴
- 전체 날짜에 걸쳐 label이 weak로 반복되는 item을 찾습니다.
- 단순히 weak 횟수가 많은 item뿐 아니라, confidence가 높은 weak (0.7 이상)를 더 심각하게 봅니다.
- 날짜에 무관하게 지속적으로 weak인 item은 구조적 취약점으로 분류합니다.
- 각 취약 item에 대해: item_name, weak_count(전체 날짜 중 weak인 날짜 수), avg_confidence, pattern_description(한국어 설명)을 포함합니다.

[분석 2] 성장/퇴보 추이
- 날짜 순서대로 category_scores의 변화를 추적합니다.
- 특정 카테고리가 지속적으로 개선되거나 악화되는 패턴을 찾습니다.
- item 수준에서도 label 변화(예: weak → neutral → strong)를 추적합니다.
- 개선된 케이스에는 어떤 강의(날짜/subject)에서 전환이 일어났는지 명시합니다.
- 각 카테고리에 대해: trend("improving"/"declining"/"stable"/"fluctuating"), score_range([최솟값, 최댓값]), notable_changes(주목할 변화 한국어 설명)를 포함합니다.

[분석 3] 커리큘럼 일치도 추이
- 날짜별 curriculum_match_score의 변화를 추적합니다.
- score가 특히 낮은 날짜(50 미만)와 그 이유를 명시합니다.
- 일치도가 낮은 날짜가 특정 subject 구간에 몰려 있는지 분석합니다.
- curriculum_match_score가 None인 날짜는 "데이터 없음"으로 처리합니다.

[분석 4] subject 전환 시 변화
- subject가 바뀌는 시점(예: 객체지향 프로그래밍 → Front-End Programming → Back-End Programming)을 찾습니다.
- 전환 직전 3개 날짜와 전환 직후 3개 날짜의 category_scores 평균을 비교합니다.
- 전환 시 어떤 카테고리가 크게 변했는지, 강사가 새로운 subject에 적응하는 데 걸린 시간을 분석합니다.
- subject가 1개뿐이거나 전환이 없으면 해당 항목은 "전환 없음"으로 처리합니다.

반드시 전체 JSON 길이를 짧게 유지하십시오.
- weak_patterns는 최대 5개만 반환
- growth_trends는 카테고리별 설명을 1문장으로 제한
- low_score_dates는 최대 3개만 반환
- subject_transitions는 최대 2개만 반환
- 모든 설명문은 80자 이내로 작성

출력 JSON 구조:
{
  "analysis_period": {
    "start_date": "YYYY-MM-DD",
    "end_date": "YYYY-MM-DD",
    "total_lectures": 0
  },
  "weak_patterns": [
    {
      "item_name": "...",
      "weak_count": 0,
      "total_count": 0,
      "avg_confidence": 0.0,
      "pattern_description": "한국어 설명"
    }
  ],
  "growth_trends": [
    {
      "category_name": "...",
      "trend": "improving",
      "score_range": [0, 0],
      "notable_changes": "한국어 설명"
    }
  ],
  "curriculum_alignment": {
    "avg_score": 0.0,
    "low_score_dates": [
      {
        "date": "YYYY-MM-DD",
        "score": 0,
        "reason": "한국어 설명"
      }
    ],
    "overall_pattern": "한국어 설명"
  },
  "subject_transitions": [
    {
      "from_subject": "...",
      "to_subject": "...",
      "transition_date": "YYYY-MM-DD",
      "score_change": {
        "카테고리명": {"before_avg": 0.0, "after_avg": 0.0, "delta": 0.0}
      },
      "adaptation_note": "한국어 설명"
    }
  ]
}"""

def collect_dates(output_path: str) -> list[str]:
    """
    output/ 디렉토리에서 *_result.json 파일을 찾아 날짜 목록을 오름차순으로 반환.
    날짜 형식: YYYY-MM-DD
    """
    dates = []
    pattern = re.compile(r"^(\d{4}-\d{2}-\d{2})_result\.json$")
    for fname in os.listdir(output_path):
        m = pattern.match(fname)
        if m:
            dates.append(m.group(1))
    return sorted(dates)

def compress_lecture(date: str, output_path: str) -> dict | None:
    """
    {date}_analysis.json + {date}_result.json을 로드하여 compressed_lecture 구조로 반환.
    파일이 없으면 None 반환.
    """
    analysis_path = os.path.join(output_path, f"{date}_analysis.json")
    result_path = os.path.join(output_path, f"{date}_result.json")

    if not os.path.exists(analysis_path) or not os.path.exists(result_path):
        return None

    with open(analysis_path, encoding="utf-8") as f:
        analysis = json.load(f)
    with open(result_path, encoding="utf-8") as f:
        result = json.load(f)

    # category_scores 추출
    category_scores = {
        cat["category_name"]: cat["final_score"]
        for cat in result.get("category_results", [])
    }

    # curriculum_match 추출
    curriculum_match = result.get("lecture_summary", {}).get("curriculum_match", {})
    curriculum_match_score = curriculum_match.get("score")
    curriculum_match_reason = (curriculum_match.get("reason") or "")[:30]

    # item_results 추출 — 입력 데이터 최소화를 위해 reason 제거
    item_results = {}
    for item in analysis.get("item_results", []):
        item_name = item.get("item_name")
        if not item_name:
            continue

        item_results[item_name] = {
            "label": item.get("label", "neutral"),
            "confidence": item.get("confidence", 0.5),
        }

    return {
        "date": date,
        "subject": None,       # STEP 3에서 메타데이터로 채움
        "contents": [],        # STEP 3에서 메타데이터로 채움
        "curriculum_match_score": curriculum_match_score,
        "curriculum_match_reason": curriculum_match_reason,
        "category_scores": category_scores,
        "item_results": item_results,
    }

def load_metadata_by_date(base_path: str) -> dict[str, dict]:
    """
    강의 메타데이터.csv를 로드하여 {date: {subject, contents}} 딕셔너리 반환.
    같은 날짜에 여러 row가 있으면 subject는 첫 번째, contents는 중복 제거 후 합산.
    파일이 없으면 빈 딕셔너리 반환.
    """
    candidates = [
        os.path.join(base_path, "강의 메타데이터.csv"),
        os.path.join(base_path, "강의_메타데이터.csv"),
        os.path.join(base_path, "강의 스크립트", "강의 메타데이터.csv"),
        os.path.join(base_path, "강의 스크립트", "강의_메타데이터.csv"),
        os.path.join(base_path, "..", "강의 메타데이터.csv"),
        os.path.join(base_path, "..", "강의_메타데이터.csv"),
    ]
    csv_path = next((path for path in candidates if os.path.exists(path)), None)
    if not csv_path:
        return {}

    result = {}
    with open(csv_path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            date = row.get("date", "").strip()
            subject = row.get("subject", "").strip()
            content = row.get("content", "").strip()
            if not date:
                continue
            if date not in result:
                result[date] = {"subject": subject, "contents": []}
            if content and content not in result[date]["contents"]:
                result[date]["contents"].append(content)
    return result

def safe_parse_json_object(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```json\s*", "", text)
        text = re.sub(r"^```\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        text = text.strip()

    try:
        return json.loads(text)
    except Exception:
        pass

    start = text.find("{")
    end = text.rfind("}")
    
    if start != -1:
        if end != -1 and end > start:
            candidate = text[start:end+1]
        else:
            candidate = text[start:] + "}"
        try:
            return json.loads(candidate)
        except Exception:
            if candidate.count('"') % 2 != 0:
                candidate = text[start:] + '"}'
                try:
                    return json.loads(candidate)
                except Exception:
                    pass

    raise ValueError(f"JSON object not found or invalid in response: {text}")

def run_trajectory_analysis(compressed_lectures: list[dict]) -> dict:
    """
    전체 날짜 압축 데이터를 LLM에 전달하여 궤적 분석 결과를 반환.
    실패 시 ValueError를 발생시킴 (호출부에서 처리).
    """
    lectures_json = json.dumps(compressed_lectures, ensure_ascii=False, indent=2)

    prompt = f"""[블록 1 — 전체 강의 날짜별 압축 데이터]
전체 {len(compressed_lectures)}개 강의 날짜의 분석 데이터입니다. 날짜 오름차순으로 정렬되어 있습니다.
{lectures_json}

[블록 2 — 분석 지침]
{ANALYSIS_GUIDELINES}
"""

    response = client.models.generate_content(
        model=TRAJECTORY_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            temperature=0.1,
            max_output_tokens=16384,
            response_mime_type="application/json", # Robust JSON extraction
        ),
    )

    try:
        return safe_parse_json_object(response.text)
    except Exception as e:
        print(f"[trajectory raw response] {response.text}", file=sys.stderr)
        raise e

def main():
    parser = argparse.ArgumentParser(description="강의 궤적 분석")
    parser.add_argument("--output-path", default="../output/")
    parser.add_argument("--base-path", default="..")
    args = parser.parse_args()

    # STEP 1: 날짜 수집
    print("[STEP 1] 날짜 수집")
    dates = collect_dates(args.output_path)
    if not dates:
        print("[오류] output/ 디렉토리에 *_result.json 파일이 없습니다.")
        sys.exit(1)
    print(f"  → {len(dates)}개 날짜 발견: {dates[0]} ~ {dates[-1]}")

    # STEP 2+3: 압축 + 메타데이터 병합
    print("[STEP 2] 데이터 압축")
    metadata = load_metadata_by_date(args.base_path)
    compressed_lectures = []
    
    for date in dates:
        compressed = compress_lecture(date, args.output_path)
        if compressed is None:
            print(f"  → {date}: analysis 또는 result 파일 없음, 건너뜀")
            continue
        meta = metadata.get(date, {})
        compressed["subject"] = meta.get("subject")
        
        # contents를 여러 개 다 넣지 않고 첫 번째 것만 넣어서 텍스트 압축
        contents_list = meta.get("contents", [])
        compressed["contents"] = [contents_list[0]] if contents_list else []
        
        compressed_lectures.append(compressed)
    print(f"  → {len(compressed_lectures)}개 날짜 압축 완료")

    if not compressed_lectures:
        print("[오류] 분석 가능한 날짜가 없습니다.")
        sys.exit(1)

    # STEP 4: LLM 분석
    print("[STEP 4] 궤적 분석 LLM 호출")
    try:
        trajectory_result = run_trajectory_analysis(compressed_lectures)
    except Exception as e:
        print(f"[오류] 궤적 분석 실패: {type(e).__name__}: {e}")
        sys.exit(1)

    # STEP 5: 저장
    start_date = compressed_lectures[0]["date"]
    end_date = compressed_lectures[-1]["date"]
    output_filename = f"{start_date}_{end_date}_trajectory.json"
    output_file = os.path.join(args.output_path, output_filename)

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(trajectory_result, f, ensure_ascii=False, indent=2)

    print(f"[완료] 저장: {output_file}")


if __name__ == "__main__":
    main()
