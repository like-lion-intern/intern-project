# 강의 궤적 분석 파이프라인 — trajectory.md

> **Codex / 안티그래피티 전용 구현 지시서입니다.**  
> 이 파일은 프로젝트 루트에 위치합니다.  
> 이 파일을 끝까지 읽은 후 구현을 시작합니다.

---

## 0. 역할 및 목적

`trajectory.py`는 단일 강의 분석 파이프라인(`pipeline.py`)이 생성한 **전체 강의 날짜의 결과물을 종합**하여 강사의 강의 궤적을 분석하는 스크립트입니다.

단일 강의 분석이 "이 날 강의가 어땠는지"를 진단한다면,  
궤적 분석은 "이 강사가 전체 커리큘럼을 통해 어떻게 변해왔는지"를 진단합니다.

---

## 1. 디렉토리 구조

```
프로젝트 루트/
├── output/
│   ├── 2026-02-02_analysis.json   ← pipeline.py가 생성한 날짜별 analysis
│   ├── 2026-02-02_result.json     ← pipeline.py가 생성한 날짜별 result
│   ├── 2026-02-03_analysis.json
│   ├── 2026-02-03_result.json
│   ├── ...
│   └── {date}_trajectory.json    ← trajectory.py 최종 출력
├── 강의 스크립트/
│   └── 강의 메타데이터.csv
└── new_pipeline/
    └── trajectory.py              ← 신규 구현 대상
```

---

## 2. 입력 데이터 구조

### 2-1. {date}_analysis.json (pipeline.py 출력)

```json
{
  "item_results": [
    {
      "item_name": "불필요한 반복 표현",
      "label": "weak",
      "confidence": 0.8,
      "evidence": [
        {
          "span_text": "...",
          "context_before": ["..."],
          "reason": "담화표지어 밀도가 1000토큰당 120.997로 높고..."
        }
      ]
    }
  ]
}
```

### 2-2. {date}_result.json (pipeline.py 출력)

```json
{
  "lecture_summary": {
    "overall_weak_categories": ["수강생 상호작용", "언어 표현 품질"],
    "curriculum_match": {
      "planned_contents": ["JavaScript 기본 문법"],
      "score": 20,
      "reason": "강의 내용은 주로 데이터베이스(MySQL) 쿼리..."
    }
  },
  "category_results": [
    {
      "category_name": "언어 표현 품질",
      "heuristic_score": 2.74,
      "final_score": 2.44,
      "reason": "...",
      "top_items": [
        {
          "item_name": "불필요한 반복 표현",
          "heuristic_score": 1.0,
          "final_score": 1.27,
          "reason": "...",
          "selected_evidence": {...}
        }
      ]
    }
  ]
}
```

### 2-3. 강의 메타데이터.csv

```
course_id,course_name,date,time,subject,content,instructor,sub_instructor
kdt-backendj-21th,백엔드 부트캠프 21기: Java,2026-02-02,09:00 ~ 12:00,객체지향 프로그래밍,"데코레이터 패턴, 옵저버 패턴",김영아,"김다은, 정석현"
kdt-backendj-21th,백엔드 부트캠프 21기: Java,2026-02-05,09:00 ~ 12:00,Front-End Programming,JavaScript 기본 문법,김영아,"김다은, 정석현"
```

- 같은 날짜에 여러 row가 있을 수 있음 (오전/오후)
- trajectory에서는 날짜별로 subject와 contents만 사용

---

## 3. 핵심 설계: input 압축

`_analysis.json`과 `_result.json`에서 trajectory LLM에 필요한 것만 추출하여 압축합니다.

**버리는 것**: `span_text`, `context_before`, `heuristic_score`, `selected_evidence`  
**남기는 것**: `final_score`, `label`, `confidence`, `reason`

reason은 실제 데이터 기준으로 평균 약 60~80자입니다. 이를 **60자로 truncate**합니다.

### 날짜별 압축 구조 (compressed_lecture)

```python
{
    "date": "2026-02-05",
    "subject": "Front-End Programming",
    "contents": ["JavaScript 기본 문법"],
    "curriculum_match_score": 20,
    "curriculum_match_reason": "강의 내용은 주로 데이터베이스(MySQL)...",  # [:30]
    "category_scores": {
        "언어 표현 품질": 2.44,
        "강의 도입 및 구조": 4.33,
        "개념 설명 명확성": 2.56,
        "예시 및 실습 연계": 2.80,
        "수강생 상호작용": 2.24
    },
    "item_results": {
        "불필요한 반복 표현": {
            "label": "weak",
            "confidence": 0.8
        },
        "발화 완결성": {
            "label": "neutral",
            "confidence": 0.6
        },
        # ... 18개 전부
    }
}
```

> **reason을 제거한 이유**: LLM 입력 토큰을 줄이기 위해 `item_results`에서 `reason` 필드를 제거했습니다. `label`과 `confidence`만으로 취약 패턴 및 성장/퇴보 추이 분석에 충분합니다.

---

## 4. 구현 명세

### 4-1. 파일 위치

`new_pipeline/trajectory.py`

### 4-2. 실행 방식

```bash
cd new_pipeline
python trajectory.py --output-path ../output/ --base-path ..
```

| 인수 | 설명 | 기본값 |
|---|---|---|
| `--output-path` | `_analysis.json`, `_result.json`이 있는 디렉토리 | `../output/` |
| `--base-path` | `강의 메타데이터.csv`가 있는 루트 경로 | `..` |

### 4-3. 전체 처리 흐름

```
[STEP 1] output/ 디렉토리에서 *_result.json 파일 목록 수집
         → 날짜 파싱 → 날짜 오름차순 정렬

[STEP 2] 각 날짜별로 _analysis.json + _result.json 로드
         → compressed_lecture 구조로 압축

[STEP 3] 강의 메타데이터.csv 로드
         → 날짜별 subject, contents 매핑

[STEP 4] 전체 날짜의 compressed_lecture 리스트를 LLM에 전달
         → 4가지 분석 수행

[STEP 5] 결과를 {날짜범위}_trajectory.json으로 저장
         예: 2026-02-02_2026-02-27_trajectory.json
```

### 4-4. STEP 1: 날짜 수집 함수

```python
import os
import re

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
```

### 4-5. STEP 2: 압축 함수

```python
import json

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

    # item_results 추출 — reason 제거, label/confidence만 유지
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
```

### 4-6. STEP 3: 메타데이터 로드 함수

```python
import csv

def load_metadata_by_date(base_path: str) -> dict[str, dict]:
    """
    강의 메타데이터.csv를 로드하여 {date: {subject, contents}} 딕셔너리 반환.
    같은 날짜에 여러 row가 있으면 subject는 첫 번째, contents는 중복 제거 후 합산.
    파일이 없으면 빈 딕셔너리 반환.
    """
    csv_path = os.path.join(base_path, "강의 스크립트", "강의 메타데이터.csv")
    if not os.path.exists(csv_path):
        # Fallback: 루트 경로에서 탐색
        csv_path = os.path.join(base_path, "강의 메타데이터.csv")
        if not os.path.exists(csv_path):
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
```
### 4-6-1. JSON 파싱 보조 함수

```python
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
                candidate = text[start:] + '"}\'
                try:
                    return json.loads(candidate)
                except Exception:
                    pass

    raise ValueError(f"JSON object not found or invalid in response: {text}")
```

> 마크다운 코드블록 제거, `{}` 범위 추출, 불완전 따옴표 보정의 3단계로 LLM 응답을 안전하게 파싱합니다.


### 4-7. STEP 4: LLM 호출

#### SDK 및 초기화

```python
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

_api_key = os.getenv("GOOGLE_API_KEY")
if not _api_key:
    raise ValueError("GOOGLE_API_KEY가 .env에 설정되어 있지 않습니다.")

client = genai.Client(api_key=_api_key)
TRAJECTORY_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
```

#### System Prompt

```
당신은 강의 품질 분석 전문가입니다.

주어진 전체 강의 날짜별 분석 데이터를 바탕으로 강사의 강의 궤적을 분석합니다.

반드시 한국어만 사용하십시오.
반드시 JSON 객체만 반환하십시오. 마크다운, 코드블록, 설명문을 포함하지 마십시오.
```

#### User Prompt 구성

아래 순서로 구성합니다:

**블록 1 — 전체 강의 날짜별 압축 데이터**
```
전체 {N}개 강의 날짜의 분석 데이터입니다. 날짜 오름차순으로 정렬되어 있습니다.
{compressed_lectures를 JSON으로 직렬화, ensure_ascii=False, indent=2}
```

**블록 2 — 분석 지침**
```
위 데이터를 바탕으로 아래 4가지를 분석하십시오.

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
    "total_lectures": N
  },
  "weak_patterns": [
    {
      "item_name": "...",
      "weak_count": N,
      "total_count": N,
      "avg_confidence": 0.0,
      "pattern_description": "한국어 설명"
    }
  ],
  "growth_trends": [
    {
      "category_name": "...",
      "trend": "improving",
      "score_range": [최솟값, 최댓값],
      "notable_changes": "한국어 설명"
    }
  ],
  "curriculum_alignment": {
    "avg_score": 0.0,
    "low_score_dates": [
      {
        "date": "YYYY-MM-DD",
        "score": N,
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
}
```

#### API 호출

```python
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
            response_mime_type="application/json",  # Robust JSON extraction
        ),
    )

    try:
        return safe_parse_json_object(response.text)
    except Exception as e:
        print(f"[trajectory raw response] {response.text}", file=sys.stderr)
        raise e
```

> `ANALYSIS_GUIDELINES`는 위 블록 2의 분석 지침 텍스트를 상수로 정의한 것입니다.

### 4-8. STEP 5: 결과 저장

```python
def main():
    # ...
    start_date = dates[0]
    end_date = dates[-1]
    output_filename = f"{start_date}_{end_date}_trajectory.json"
    output_file = os.path.join(args.output_path, output_filename)

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(trajectory_result, f, ensure_ascii=False, indent=2)

    print(f"[완료] 저장: {output_file}")
```

---

## 5. 최종 출력 JSON 구조

파일명: `{start_date}_{end_date}_trajectory.json`  
저장 위치: `output/`

```json
{
  "analysis_period": {
    "start_date": "2026-02-02",
    "end_date": "2026-02-27",
    "total_lectures": 15
  },
  "weak_patterns": [
    {
      "item_name": "불필요한 반복 표현",
      "weak_count": 12,
      "total_count": 15,
      "avg_confidence": 0.78,
      "pattern_description": "전체 강의의 80%에서 weak로 나타나며, 담화표지어 밀도가 지속적으로 높게 측정됨. 특히 실습 유도 구간에서 반복 표현이 집중적으로 발생하는 패턴 확인."
    }
  ],
  "growth_trends": [
    {
      "category_name": "강의 도입 및 구조",
      "trend": "improving",
      "score_range": [2.1, 4.33],
      "notable_changes": "2026-02-05 이후 학습 목표 안내와 전날 복습 연계 항목이 꾸준히 strong으로 전환됨. Back-End Programming 구간에서 점수가 안정화됨."
    }
  ],
  "curriculum_alignment": {
    "avg_score": 42.5,
    "low_score_dates": [
      {
        "date": "2026-02-05",
        "score": 20,
        "reason": "커리큘럼 계획은 JavaScript 기본 문법이었으나 실제 강의는 MySQL 쿼리 작성 위주로 진행됨."
      }
    ],
    "overall_pattern": "Front-End Programming 구간에서 커리큘럼 일치도가 전반적으로 낮고, Back-End Programming 전환 이후 일치도가 개선되는 경향이 있음."
  },
  "subject_transitions": [
    {
      "from_subject": "객체지향 프로그래밍",
      "to_subject": "Front-End Programming",
      "transition_date": "2026-02-03",
      "score_change": {
        "개념 설명 명확성": {"before_avg": 3.8, "after_avg": 2.6, "delta": -1.2},
        "수강생 상호작용": {"before_avg": 3.2, "after_avg": 2.4, "delta": -0.8}
      },
      "adaptation_note": "subject 전환 직후 개념 설명 명확성과 수강생 상호작용 점수가 동시에 하락. 약 3~4개 강의 이후 점수가 회복되는 적응 패턴 관찰됨."
    }
  ]
}
```

---

## 6. 전체 코드 구조 (main 함수)

```python
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
        # contents는 첫 번째 항목만 사용하여 토큰 절감
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
```

---

## 7. 예외 처리

| 상황 | 처리 |
|---|---|
| `output/`에 `*_result.json` 없음 | 오류 메시지 출력 후 `sys.exit(1)` |
| 특정 날짜의 `_analysis.json` 또는 `_result.json` 없음 | 해당 날짜 건너뜀, 경고 출력 후 계속 진행 |
| `강의 메타데이터.csv` 없음 | subject, contents를 None/빈 리스트로 두고 계속 진행 |
| `GOOGLE_API_KEY` 미설정 | import 시 `ValueError` 발생 |
| Gemini API 호출 실패 | 오류 메시지 출력 후 `sys.exit(1)` (fallback 없음 — 궤적 분석은 LLM 없이 의미 없음) |
| LLM JSON 파싱 실패 | 오류 메시지 + raw 응답 출력 후 `sys.exit(1)` |
| subject 전환이 없는 경우 | `subject_transitions: []` |
| `curriculum_match_score`가 None인 날짜 | 해당 날짜를 커리큘럼 일치도 평균 계산에서 제외, "데이터 없음"으로 표기 |

---

## 8. 완료 확인

```bash
cd new_pipeline
python trajectory.py --output-path ../output/ --base-path ..

# 출력 파일 확인
ls ../output/*_trajectory.json

# 구조 검증
python -c "
import json, glob
files = glob.glob('../output/*_trajectory.json')
assert files, '결과 파일 없음'
with open(files[0], encoding='utf-8') as f:
    t = json.load(f)
assert 'analysis_period' in t
assert 'weak_patterns' in t
assert 'growth_trends' in t
assert 'curriculum_alignment' in t
assert 'subject_transitions' in t
print('trajectory.json 구조 검증 OK')
print('분석 기간:', t['analysis_period'])
print('취약 패턴 수:', len(t['weak_patterns']))
print('카테고리 추이 수:', len(t['growth_trends']))
"
```