# 강의 품질 진단 파이프라인 — AGENTS.md

> **Codex 전용 구현 지시서입니다.**  
> 이 파일은 `new_pipeline/` 디렉토리 안에 위치합니다.  
> Codex는 이 파일을 먼저 끝까지 읽고, 아래 **구현 순서**에 따라 파일을 하나씩 완성한 뒤 다음 파일로 넘어갑니다.

---

## 📌 알려진 데이터 품질 이슈 (구현 시 참고)

**STT 전사 오염**: `text_preview`에 전문 용어가 발음 그대로 전사된 경우가 있음.
예) `InputStream` → `인풋스트림`, `MySQL` → `마이에스q엘`, `BufferedOutputStream` → `버퍼도 아웃풋 스`

- **현재 파이프라인에서는 정제 없이 그대로 사용한다.** Gemini가 Java 도메인 지식으로 맥락상 충분히 읽을 수 있는 수준.
- `features.json`의 `term_density_per_1k_tokens`가 `0.0`인 것도 이 오염 때문일 가능성이 높음. 현재는 무시하고 진행.
- **향후 인지 부하(전문 용어 밀도) 평가 item을 추가할 때 STT 전처리 정제를 같이 설계할 것.**

---

## ⚡ 구현 시작 전 필수 확인

```
new_pipeline/
├── .env                  ← GOOGLE_API_KEY, GEMINI_MODEL, E5_MODEL_NAME 설정 필요
├── features.py           ← 수정 가능 (키워드 사전 등)
├── loader.py             ← 수정 가능 (load_curriculum 함수 추가됨)
├── rerank.py             ← 섹션 TASK-1에서만 제한적 수정
├── evidence_extractor.py ← TASK-2에서 신규 생성
├── llm_analysis.py       ← TASK-3에서 신규 작성
├── scoring.py            ← TASK-4에서 신규 작성
└── pipeline.py           ← TASK-5에서 신규 작성
```

**.env 필요 키:**
```
GOOGLE_API_KEY=your_key_here
GEMINI_MODEL=gemini-2.5-flash
E5_MODEL_NAME=intfloat/multilingual-e5-small
```

**필요 패키지:**
```bash
pip install google-genai python-dotenv transformers torch
```

**시작 전 실행할 것:**
```bash
cat features.py    # 기존 코드 구조 파악
cat loader.py      # 기존 코드 구조 파악
cat rerank.py      # 수정 전 전체 내용 파악
```

---

## 📋 전체 구현 순서 (이 순서를 반드시 지킨다)

- [ ] **TASK-1**: `rerank.py` 수정 
- [ ] **TASK-2**: `evidence_extractor.py` 신규 생성
- [ ] **TASK-3**: `llm_analysis.py` 신규 작성
- [ ] **TASK-4**: `scoring.py` 신규 작성
- [ ] **TASK-5**: `pipeline.py` 신규 작성
- [ ] **TASK-6**: 실행 테스트

---

## 🔒 전역 제약 (모든 TASK에서 예외 없이 적용)

1. `rerank.py`는 **TASK-1에 명시된 세 곳만** 수정한다
2. 명세에 없는 함수·필드·파라미터를 **임의로 추가하지 않는다**
3. 반복되는 코드라도 **"이하 동일" 처리 없이 전부 명시적으로 작성한다**
4. `support_strength` 필드는 LLM 출력 어디에도 **포함하지 않는다**
5. `final_score = heuristic_score * h_weight + llm_score * (1 - h_weight)` 공식을 사용한다. **h_weight는 item별로 다르다** (ITEM_HEURISTIC_WEIGHT 참조)
6. API 키와 모델명은 `.env`에서만 읽는다. **코드에 하드코딩 금지**
7. 모든 파일 저장 시 `encoding="utf-8"`, JSON 출력 시 `ensure_ascii=False, indent=2`
8. LLM SDK는 반드시 `google-genai` (`from google import genai`)를 사용한다. `google.generativeai`는 deprecated이므로 사용 금지.

---

## 📁 배경 지식: 데이터 구조

### features/{date}.json
```json
{
  "date": "2026-02-02",
  "features": {
    "utterance_count": 1484,
    "token_count": 20449,
    "question_count": 70,
    "example_count": 5,
    "practice_directive_ratio": 0.0189,
    "term_density_per_1k_tokens": 0.0,
    "repetition_count": 30,
    "discourse_marker_per_1k_tokens": {
      "이제": 6.895,
      "그러면": 4.303,
      "그래서": 7.678,
      "자": 22.153,
      "음": 12.177,
      "어": 51.347,
      "일단": 4.01
    }
  }
}
```

### semantic_chunks/{date}.json
```json
{
  "date": "2026-02-02",
  "chunks": [
    {
      "segment_id": "seg_01",
      "parent_label": "실습 유도",
      "sub_label": "practice_explanation",
      "chunk_id": "seg_01_chunk_01",
      "start_idx": 0,
      "end_idx": 71,
      "start_ts": "09:11:17",
      "end_ts": "09:22:25",
      "utterance_count": 72,
      "text_preview": "여러분 오늘 수업 진행하도록 하겠습니다...",
      "avg_adjacent_sim": 0.8606
    }
  ]
}
```

### 강의 메타데이터.csv (상위 폴더에 위치)
```
course_id,course_name,date,time,subject,content,instructor,sub_instructor
kdt-backendj-21th,백엔드 부트캠프 21기: Java,2026-02-05,09:00 ~ 12:00,Front-End Programming,JavaScript 기본 문법,김영아,"김다은, 정석현"
```
- 같은 날짜에 여러 row가 있을 수 있음 (오전/오후)
- `load_curriculum(date, base_path)`으로 로드, 같은 날짜의 content를 모두 합쳐서 반환

**실제 데이터 특성 (2026-02-02 기준):**
- 전체 20개 segment, `parent_label` 전체 `"실습 유도"` 단일값
- `sub_label` 3종: `practice_explanation` / `practice_instruction` / `practice_example`
- `seg_01` = 사실상 도입부 (목표·복습 언급 유일)
- `seg_20` = 마지막 segment (DB 설치 안내로 전환, 명시적 요약 없음)
- `start_ts` / `end_ts`는 `"HH:MM:SS"` 형식의 문자열

---

## 📊 평가 카테고리 · 아이템 · 가중치 (전체 18개)

가중치: **높음=3 / 중간=2 / 낮음=1 / 해당없음=0.5**  
*(전체가 실습 유도 강의인 특성을 반영하여 설계됨)*

| category_name | item_name | 가중치 숫자 | 근거 요약 |
|---|---|---|---|
| 언어 표현 품질 | 불필요한 반복 표현 | 3 | 전 segment 평가 가능, discourse_marker 최우선 |
| 언어 표현 품질 | 발화 완결성 | 2 | 전 segment 가능, 라이브코딩 특성상 완화 적용 |
| 언어 표현 품질 | 언어 일관성 | 2 | 부트캠프 특성상 혼용 구조적 발생 |
| 강의 도입 및 구조 | 학습 목표 안내 | 2 | seg_01 1개에서만 평가 가능 |
| 강의 도입 및 구조 | 전날 복습 연계 | 2 | seg_01~02 일부 등장 |
| 강의 도입 및 구조 | 설명 순서 | 1 | 실습 유도 흐름에서 전통적 순서 분리 불명확 |
| 강의 도입 및 구조 | 핵심 내용 강조 | 2 | practice_explanation에서 강조 발화 평가 |
| 강의 도입 및 구조 | 마무리 요약 | 0.5 | seg_20이 DB 설치 안내로 전환, 사실상 평가 불가 |
| 개념 설명 명확성 | 개념 정의 | 2 | practice_explanation에서 개념 설명 등장 |
| 개념 설명 명확성 | 비유 및 예시 활용 | 2 | practice_explanation/practice_example 등장 |
| 개념 설명 명확성 | 선행 개념 확인 | 1 | 실습 중심 강의에서 명시 발화 드묾 |
| 개념 설명 명확성 | 발화 속도 적절성 | 3 | 전체 강의 기반, 라이브코딩 중 빠른 속도 흔함 |
| 예시 및 실습 연계 | 예시 적절성 | 3 | 전 segment 평가, 실무 연관성이 핵심 |
| 예시 및 실습 연계 | 실습 연계 | 3 | 전체 20개 segment가 실습 유도, 최핵심 |
| 예시 및 실습 연계 | 오류 대응 | 2 | practice_instruction에서 오류 대응 발화 |
| 수강생 상호작용 | 이해 확인 질문 | 3 | 전 segment "됐어요?" 등 평가 |
| 수강생 상호작용 | 참여 유도 | 3 | 전 segment 실습 유도 표현 |
| 수강생 상호작용 | 질문 응답 충분성 | 2 | STT 특성상 수강생 발화 구분 어려움 |

---

## 📁 TASK-0: `features.py` 및 `loader.py` 수정

### features.py — 키워드 사전 수정

원본에서 아래 키워드 목록을 반드시 이 버전으로 교체한다.

**practice_keywords** (실습 연계 heuristic이 실제 강의를 못 잡는 문제 수정):
```python
practice_keywords = [
    "실습", "해보", "따라", "눌러보", "직접", "구현", "해봅시다",
    "실행", "작성", "풀어", "해보세요", "한번 해보", "작성해",
    "코딩", "쿼리", "입력해", "써봐", "구현해",
]
```

**summary_keywords** (마무리 요약 evidence 추출 개선):
```python
summary_keywords = [
    "정리", "요약", "마무리", "여기까지", "끝내", "정리하면",
    "수고하셨", "마치겠습니다", "쉬겠습니다", "끝입니다", "마칩니다", "이상입니다",
]
```

**repetition_spans evidence 버그 수정** (기존: lecture-level repetition_count + 이중 조건으로 거의 안 걸림):
```python
# 기존 (버그)
"repetition_spans": [text] if repetition_count > 0 and _contains_any(text, ["다시", "또", "한번 더"]) else [],

# 수정 (filler가 3개 이상인 segment를 반복 표현 후보로 봄)
"repetition_spans": [text] if filler_count_seg >= 3 else [],
```

**segment text_preview normalize 적용** — evidence_extractor와 매칭 일치를 위해 segment 저장 시 반드시 `_normalize_text()` 적용:
```python
text = _normalize_text(chunk.get("text_preview", ""))
# ... (계산 후)
segments.append({
    ...
    "text_preview": text,  # normalize된 text 저장
})
```

### loader.py — load_curriculum 함수 추가

```python
import csv

def load_curriculum(date: str, base_path: str = "..") -> dict:
    """
    강의 메타데이터.csv에서 해당 날짜의 커리큘럼 정보를 로드.
    같은 날짜에 content가 여러 개인 경우 모두 합쳐서 반환.
    없으면 None 반환.
    """
    csv_path = os.path.join(base_path, "강의 메타데이터.csv")
    if not os.path.exists(csv_path):
        return None

    matched_rows = []
    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("date", "").strip() == date:
                matched_rows.append(row)

    if not matched_rows:
        return None

    seen = set()
    unique_contents = []
    for row in matched_rows:
        c = row.get("content", "").strip()
        if c and c not in seen:
            seen.add(c)
            unique_contents.append(c)

    first = matched_rows[0]
    return {
        "date": date,
        "course_name": first.get("course_name", "").strip(),
        "subject": first.get("subject", "").strip(),
        "contents": unique_contents,
        "instructor": first.get("instructor", "").strip(),
    }
```

---

## 📁 TASK-1: `rerank.py` 수정

> **수정 범위: 딱 3곳만. 나머지 함수는 건드리지 않는다.**

### 수정 1 — 파일 최상단에 추가
```python
from __future__ import annotations
from dotenv import load_dotenv
load_dotenv()
```

### 수정 2 — `E5Reranker.__init__` 시그니처 변경
```python
# 변경 후
def __init__(self, model_name: str = None):
    model_name = model_name or os.getenv("E5_MODEL_NAME", "intfloat/multilingual-e5-small")
    # 이하 기존 코드 동일
```

### 수정 3 — `get_reranker()` 시그니처 변경
```python
# 변경 후
def get_reranker(model_name: str = None):
    # 이하 기존 코드 동일
```

### ✅ TASK-1 완료 확인
```bash
python -c "from rerank import get_reranker; print('rerank import OK')"
```

---

## 📁 TASK-2: `evidence_extractor.py` 신규 생성

### 파일 위치: `new_pipeline/evidence_extractor.py`

### 핵심 변경사항 (원본 명세 대비)
- **top_k=2** (원본 3에서 변경 — 프롬프트 토큰 절약)
- **context_before 1개만, context_after 없음** (원본 앞뒤 3개에서 변경)
- **normalize_text 매칭** — features.py가 normalize_text 적용 후 segment에 저장하므로, chunk_texts도 동일하게 normalize해야 chunk_idx를 정확히 찾을 수 있음

### 전체 구현 내용

```python
from __future__ import annotations

import re
from typing import List, Dict, Any
from rerank import rerank_evidence


def _normalize_text(text: str) -> str:
    """features.py와 동일한 normalize 함수 — chunk_texts 매칭 일치를 위해 필요"""
    return re.sub(r"\s+", " ", str(text)).strip()


ITEM_EVIDENCE_KEYS: Dict[str, List[str]] = {
    "불필요한 반복 표현": ["filler_spans", "repetition_spans", "language_expression_evidence"],
    "발화 완결성":        ["incomplete_sentence_spans", "completion_evidence"],
    "언어 일관성":        ["style_shift_spans", "speech_style_evidence"],
    "학습 목표 안내":     ["objective_intro_spans", "intro_evidence"],
    "전날 복습 연계":     ["review_bridge_spans", "bridge_evidence"],
    "설명 순서":          ["structure_flow_spans", "transition_evidence", "structure_evidence"],
    "핵심 내용 강조":     ["emphasis_spans", "highlight_evidence"],
    "마무리 요약":        ["closing_summary_spans", "summary_evidence"],
    "개념 정의":          ["definition_spans", "concept_definition_evidence"],
    "비유 및 예시 활용":  ["example_spans", "example_evidence", "analogy_spans"],
    "선행 개념 확인":     ["prerequisite_bridge_spans", "prerequisite_evidence"],
    "발화 속도 적절성":   ["pace_evidence", "rapid_transition_spans"],
    "예시 적절성":        ["practical_example_spans", "practical_example_evidence"],
    "실습 연계":          ["practice_transition_spans", "practice_evidence"],
    "오류 대응":          ["error_response_spans", "error_evidence"],
    "이해 확인 질문":     ["understanding_check_spans", "question_spans", "interaction_evidence"],
    "참여 유도":          ["engagement_spans", "interaction_prompt_spans", "engagement_evidence"],
    "질문 응답 충분성":   ["qa_response_spans", "qa_evidence", "followup_spans"],
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

    top_texts = rerank_evidence(item_name, candidates_with_idx, top_k=2)

    result = []
    # normalize_text 적용 — features.py의 segment text_preview와 일치시킴
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
                "context_before": [],
            })
            continue

        context_before = chunk_texts_normalized[max(0, chunk_idx - 1):chunk_idx]

        result.append({
            "span_text": span_text,
            "context_before": context_before,
        })

    return result
```

### ✅ TASK-2 완료 확인
```bash
python -c "
from evidence_extractor import ITEM_EVIDENCE_KEYS, extract_evidence
assert len(ITEM_EVIDENCE_KEYS) == 18, f'항목 수 오류: {len(ITEM_EVIDENCE_KEYS)}'
print('evidence_extractor import OK, 항목 수:', len(ITEM_EVIDENCE_KEYS))
"
```

---

## 📁 TASK-3: `llm_analysis.py` 신규 작성

### 파일 위치: `new_pipeline/llm_analysis.py`

### SDK 및 초기화
```python
from __future__ import annotations
import json
import os
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

_api_key = os.getenv("GOOGLE_API_KEY")
if not _api_key:
    raise ValueError("GOOGLE_API_KEY가 .env에 설정되어 있지 않습니다.")

client = genai.Client(api_key=_api_key)
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
```

### System Prompt
```
당신은 강의 품질 진단 전문가입니다.
주어진 강의의 정량적 피쳐, segment 텍스트, 근거 문장을 종합하여 각 평가 항목(item)의 상태를 분석합니다.
정량적 피쳐(features)와 실제 발화 내용(evidence)을 중심으로 분석하며, 시그널(signals)은 보조 힌트로만 참고합니다.
반드시 아래 JSON 형식으로만 응답하십시오. 다른 텍스트나 마크다운 코드 블록은 포함하지 마십시오.
```

### 프롬프트 구성 — 토큰 절약 처리

LLM에 넘기기 전 반드시 아래와 같이 트리밍한다:

```python
# segments text_preview 150자 제한
segments_json = json.dumps([
    {
        "segment_id": seg.get("segment_id"),
        "parent_label": seg.get("parent_label"),
        "sub_label": seg.get("sub_label"),
        "utterance_count": seg.get("weight"),
        "text_preview": (seg.get("text_preview") or "")[:150],
    }
    for seg in signals_output.get("segments", [])
], ensure_ascii=False, indent=2)

# evidence span_text 100자, context_before 1개로 트리밍
trimmed_evidence = {}
for item_name, evs in evidence_by_item.items():
    trimmed_evidence[item_name] = [
        {
            "span_text": ev.get("span_text", "")[:100],
            "context_before": ev.get("context_before", [])[-1:],
            "context_after": ev.get("context_after", [])[:1],
        }
        for ev in evs[:1]
    ]
evidence_json = json.dumps(trimmed_evidence, ensure_ascii=False, indent=2)
```

### 분석 지침 (User Prompt 안에 포함)

블록 1~5를 순서대로 포함하고, 아래 지침을 추가한다:

```
1. 분석의 주된 근거는 정량적 피쳐(features)와 실제 발화 텍스트(evidence의 span_text, context)입니다.

2. 정량적 피쳐에서 아래 수치를 반드시 확인하고 분석에 반영합니다:
   - discourse_marker_per_1k_tokens
   - repetition_count
   - question_count
   - example_count
   - practice_directive_ratio

3. sub_label에 따라 분석 비중을 다르게 적용합니다 (practice_explanation / practice_instruction / practice_example)

4. label: "weak" / "neutral" / "strong"

5. confidence: 0.0 ~ 1.0

6. reason은 반드시 한국어로만 작성합니다. 다른 언어(영어, 벵골어 등)를 절대 혼용하지 마십시오.
   정량적 피쳐에 명시된 수치를 인용할 때는 반드시 features 블록에 있는 값 그대로만 사용하고 임의로 수치를 만들지 마십시오.

7. support_strength 필드는 절대 포함하지 않습니다.
```

### API 호출
```python
response = client.models.generate_content(
    model=MODEL_NAME,
    contents=prompt,
    config=types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        temperature=0.1,
        max_output_tokens=16384,
        # response_mime_type 사용 금지 — 한국어 긴 텍스트에서 JSON 잘림 버그 발생
    ),
)

# 마크다운 코드블록 제거 (Gemini가 ```json으로 감싸서 응답할 수 있음)
raw_text = response.text.strip()
if raw_text.startswith("```"):
    lines = raw_text.split("\n")
    lines = lines[1:]  # 첫 줄(```json 등) 제거
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    raw_text = "\n".join(lines).strip()
```

### 커리큘럼 일치도 분석 함수 추가

```python
def analyze_curriculum_match(
    curriculum: dict,
    signals_output: dict,
) -> dict:
    """
    커리큘럼 content와 실제 강의 segment 내용의 일치도를 LLM으로 분석.
    반환: {"score": int(0~100), "reason": str}
    curriculum이 None이면 {"score": None, "reason": "커리큘럼 정보 없음"} 반환.
    score 기준:
      90~100: 계획된 내용이 충실히 다뤄짐
      70~89: 대부분 일치하나 일부 누락
      50~69: 절반 정도 일치
      30~49: 부분적으로만 연관
      0~29: 거의 관련 없음
    """
```

### fallback 반환 구조
```python
FALLBACK = {
    "item_results": [
        {"item_name": name, "label": "neutral", "confidence": 0.5, "evidence": []}
        for name in ALL_ITEMS
    ]
}

# run_analysis fallback 시 stderr에 에러 출력
def run_analysis(...) -> dict:
    try:
        return analyze_items(...)
    except Exception as e:
        import sys
        print(f"[llm_analysis] LLM 분석 실패, fallback 사용: {type(e).__name__}: {e}", file=sys.stderr)
        return {fallback}
```

### ✅ TASK-3 완료 확인
```bash
python -c "
from llm_analysis import run_analysis, analyze_curriculum_match
print('llm_analysis import OK')
"
```

---

## 📁 TASK-4: `scoring.py` 신규 작성

### 파일 위치: `new_pipeline/scoring.py`

### 스코어링 철학
| 구성 요소 | 역할 | 기여 비중 |
|---|---|---|
| heuristic_score | 수치 기반 신호 (키워드 밀도, 발화 속도 등) | item별 상이 (h_weight) |
| LLM label + confidence | 실제 발화 내용 기반 판단 | 1 - h_weight |

### ITEM_HEURISTIC_WEIGHT — item별 heuristic:LLM 비중

```python
# 수치 측정 가능 → 0.5:0.5
# 수치 있지만 맥락도 중요 → 0.3:0.7
# 발화 맥락이 핵심 → 0.2:0.8
ITEM_HEURISTIC_WEIGHT = {
    "불필요한 반복 표현": 0.5,   # discourse_marker 수치 직접 측정
    "발화 속도 적절성":   0.5,   # words_per_minute 직접 측정
    "발화 완결성":        0.3,
    "언어 일관성":        0.3,
    "학습 목표 안내":     0.3,
    "전날 복습 연계":     0.3,
    "설명 순서":          0.3,
    "개념 정의":          0.3,
    "선행 개념 확인":     0.3,
    "이해 확인 질문":     0.3,
    "핵심 내용 강조":     0.2,   # 발화 맥락 필수
    "마무리 요약":        0.2,
    "비유 및 예시 활용":  0.2,
    "예시 적절성":        0.2,
    "실습 연계":          0.2,
    "오류 대응":          0.2,
    "참여 유도":          0.2,
    "질문 응답 충분성":   0.2,
}
```

### final_score 계산 공식
```python
LABEL_BASE_SCORE = {"strong": 4.5, "neutral": 3.0, "weak": 2.5}
LABEL_ADJUSTMENT = {"strong": +1.0, "neutral": 0.0, "weak": -1.2}

def calc_final_score(heuristic_score: float, label: str, confidence: float, item_name: str = "") -> float:
    label_base = LABEL_BASE_SCORE.get(label, 3.0)
    label_adj = LABEL_ADJUSTMENT.get(label, 0.0)
    llm_score = label_base + label_adj * confidence
    llm_score = max(1.0, min(5.0, llm_score))
    h_weight = ITEM_HEURISTIC_WEIGHT.get(item_name, 0.4)
    l_weight = round(1.0 - h_weight, 1)
    final = heuristic_score * h_weight + llm_score * l_weight
    return round(max(1.0, min(5.0, final)), 2)
```

> **변경 포인트**: weak 기준값 1.8 → 2.5 (점수 과소평가 방지), h_weight를 item별로 다르게 적용

### overall_weak_categories 기준
```python
# final_score < 2.8인 category만 (기존 < 3.0에서 변경 — 과도한 weak 분류 방지)
overall_weak_categories = [
    category["category_name"]
    for category in sorted(
        [c for c in category_results if c["final_score"] < 2.8],
        key=lambda x: x["final_score"],
    )
]
```

### top_items 출력 구조 (adjustment_reason 제거됨)
```python
top_items.append({
    "item_name": item["item_name"],
    "heuristic_score": item["heuristic_score"],
    "final_score": item["final_score"],
    "reason": item["reason"],
    "selected_evidence": item["selected_evidence"],
    # adjustment_reason 필드 없음
})
```

### ITEM_WEIGHT 및 CATEGORY_ITEMS
```python
ITEM_WEIGHT = {
    "불필요한 반복 표현": 3, "발화 완결성": 2, "언어 일관성": 2,
    "학습 목표 안내": 2, "전날 복습 연계": 2, "설명 순서": 1,
    "핵심 내용 강조": 2, "마무리 요약": 0.5,
    "개념 정의": 2, "비유 및 예시 활용": 2, "선행 개념 확인": 1, "발화 속도 적절성": 3,
    "예시 적절성": 3, "실습 연계": 3, "오류 대응": 2,
    "이해 확인 질문": 3, "참여 유도": 3, "질문 응답 충분성": 2,
}

CATEGORY_ITEMS = {
    "언어 표현 품질": ["불필요한 반복 표현", "발화 완결성", "언어 일관성"],
    "강의 도입 및 구조": ["학습 목표 안내", "전날 복습 연계", "설명 순서", "핵심 내용 강조", "마무리 요약"],
    "개념 설명 명확성": ["개념 정의", "비유 및 예시 활용", "선행 개념 확인", "발화 속도 적절성"],
    "예시 및 실습 연계": ["예시 적절성", "실습 연계", "오류 대응"],
    "수강생 상호작용": ["이해 확인 질문", "참여 유도", "질문 응답 충분성"],
}
```

### ✅ TASK-4 완료 확인
```bash
python -c "
from scoring import run_scoring, ITEM_WEIGHT, CATEGORY_ITEMS, ITEM_HEURISTIC_WEIGHT
assert len(ITEM_WEIGHT) == 18
assert len(ITEM_HEURISTIC_WEIGHT) == 18
assert len(CATEGORY_ITEMS) == 5
print('scoring import OK')
"
```

---

## 📁 TASK-5: `pipeline.py` 신규 작성

### 파일 위치: `new_pipeline/pipeline.py`

### 출력 파일 3개 (디버깅용 중간 결과 포함)

| 파일명 | 생성 시점 | 내용 |
|---|---|---|
| `{date}_evidence.json` | STEP 3 완료 직후 | item별 top_2 evidence + 앞 맥락 1개 |
| `{date}_analysis.json` | STEP 4 완료 직후 | LLM이 분석한 item별 label + confidence + reason |
| `{date}_result.json` | STEP 6 완료 직후 | 최종 scoring 결과 + curriculum_match |

### 실행 방식
```bash
python pipeline.py --date 2026-02-02 --base-path .. --output-path ./output/
```

### 전체 코드
```python
import argparse
import json
import os
import sys
from dotenv import load_dotenv

load_dotenv()

from loader import load_data, load_curriculum
from features import calculate_signals
from evidence_extractor import extract_evidence, ITEM_EVIDENCE_KEYS
from llm_analysis import run_analysis, analyze_curriculum_match
from scoring import run_scoring


def _save_json(data: dict, path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser(description="강의 품질 진단 파이프라인")
    parser.add_argument("--date", required=True)
    parser.add_argument("--base-path", default="..")
    parser.add_argument("--output-path", default="../output/")
    args = parser.parse_args()

    os.makedirs(args.output_path, exist_ok=True)

    # STEP 1: 데이터 로드
    try:
        print(f"[STEP 1] 데이터 로드: {args.date}")
        features_data, chunks_data = load_data(args.date, args.base_path)
        chunks = chunks_data.get("chunks", [])
    except FileNotFoundError as e:
        print(f"[오류] {e}")
        sys.exit(1)

    # STEP 1-1: 커리큘럼 메타데이터 로드
    curriculum = load_curriculum(args.date, args.base_path)
    if curriculum:
        print(f"  → 커리큘럼: {curriculum['subject']} / {', '.join(curriculum['contents'])}")
    else:
        print(f"  → 커리큘럼 정보 없음")

    # STEP 2: 시그널 계산
    print(f"[STEP 2] 시그널 계산")
    signals_output = calculate_signals(features_data, chunks_data)

    # STEP 3: Evidence 추출
    print(f"[STEP 3] Evidence 추출")
    evidence_by_item = {}
    for item_name in ITEM_EVIDENCE_KEYS.keys():
        evidence_by_item[item_name] = extract_evidence(item_name, chunks, signals_output)
    _save_json(evidence_by_item, os.path.join(args.output_path, f"{args.date}_evidence.json"))

    # STEP 4: LLM 분석
    print(f"[STEP 4] LLM 분석")
    analysis_result = run_analysis(features_data, signals_output, evidence_by_item)
    _save_json(analysis_result, os.path.join(args.output_path, f"{args.date}_analysis.json"))

    # STEP 5: 스코어링
    print(f"[STEP 5] 스코어링")
    final_output = run_scoring(features_data, signals_output, analysis_result, chunks)

    # STEP 6: 커리큘럼 일치도 분석 → lecture_summary에 추가
    print(f"[STEP 6] 커리큘럼 일치도 분석")
    curriculum_match = analyze_curriculum_match(curriculum, signals_output)
    final_output["lecture_summary"]["curriculum_match"] = {
        "planned_contents": curriculum["contents"] if curriculum else [],
        "score": curriculum_match["score"],
        "reason": curriculum_match["reason"],
    }

    result_file = os.path.join(args.output_path, f"{args.date}_result.json")
    _save_json(final_output, result_file)
    print(f"  → 저장: {result_file}")


if __name__ == "__main__":
    main()
```

### ✅ TASK-5 완료 확인
```bash
python pipeline.py --date 2026-02-05 --base-path .. --output-path ./output/
```

---

## 🧪 TASK-6: 최종 통합 테스트

```bash
# 1. 전체 import 확인
python -c "
from rerank import get_reranker
from evidence_extractor import ITEM_EVIDENCE_KEYS, extract_evidence
from llm_analysis import run_analysis, analyze_curriculum_match
from scoring import run_scoring, ITEM_WEIGHT, CATEGORY_ITEMS, ITEM_HEURISTIC_WEIGHT
print('모든 모듈 import OK')
"

# 2. 파이프라인 실행
python pipeline.py --date 2026-02-05 --base-path .. --output-path ./output/

# 3. evidence 구조 확인
python -c "
import json
with open('./output/2026-02-05_evidence.json', encoding='utf-8') as f:
    ev = json.load(f)
assert len(ev) == 18
for item_name, evs in ev.items():
    for e in evs:
        assert 'span_text' in e
        assert 'context_before' in e
print('evidence.json OK — item 수:', len(ev))
"

# 4. analysis 구조 확인
python -c "
import json
with open('./output/2026-02-05_analysis.json', encoding='utf-8') as f:
    an = json.load(f)
assert len(an['item_results']) == 18
for item in an['item_results']:
    assert item['label'] in ('strong', 'neutral', 'weak')
    assert 'support_strength' not in item
    for e in item['evidence']:
        assert 'support_strength' not in e
print('analysis.json OK')
"

# 5. result 구조 확인
python -c "
import json
with open('./output/2026-02-05_result.json', encoding='utf-8') as f:
    result = json.load(f)
assert len(result['category_results']) == 5
assert 'curriculum_match' in result['lecture_summary']
for cat in result['category_results']:
    for item in cat['top_items']:
        assert 'selected_evidence' in item
        assert 'adjustment_reason' not in item  # 제거됨
print('result.json OK — category 수:', len(result['category_results']))
"
```

---

## 📊 최종 출력 JSON 구조

### {date}_result.json
```json
{
  "lecture_summary": {
    "overall_weak_categories": ["카테고리명"],
    "curriculum_match": {
      "planned_contents": ["JavaScript 기본 문법"],
      "score": 35,
      "reason": "실제 강의는 SQL/DB 내용이 주를 이루고 있어 커리큘럼과 거의 일치하지 않습니다."
    }
  },
  "category_results": [
    {
      "category_name": "언어 표현 품질",
      "heuristic_score": 2.74,
      "final_score": 2.75,
      "reason": "...",
      "top_items": [
        {
          "item_name": "불필요한 반복 표현",
          "heuristic_score": 1.0,
          "final_score": 2.0,
          "reason": "...",
          "selected_evidence": {
            "span_text": "...",
            "context_before": ["..."],
            "context_after": []
          }
        }
      ]
    }
  ]
}
```

**규칙:**
- `overall_weak_categories`: `final_score < 2.8`인 category만, 점수 낮은 순 정렬
- `selected_evidence`: evidence 목록 중 `reason`이 있는 첫 번째 evidence 사용. 없으면 `null`
- `adjustment_reason` 필드 없음 (제거됨)

---

## ⚠️ 예외 처리 요약

| 상황 | 처리 |
|---|---|
| `features/{date}.json` 없음 | `FileNotFoundError` → `pipeline.py`에서 catch, 오류 출력 후 `sys.exit(1)` |
| `semantic_chunks/{date}.json` 없음 | 동일 |
| `강의 메타데이터.csv` 없음 또는 날짜 미발견 | `load_curriculum()` → `None` 반환, curriculum_match score=None |
| E5 모델 로드 실패 | `rerank.py` 내부 fallback (키워드 overlap) 자동 사용, stderr 출력 |
| `GOOGLE_API_KEY` 미설정 | `llm_analysis.py` import 시 `ValueError` 발생 |
| Gemini API 호출 실패 / JSON 파싱 실패 | fallback: 전체 18개 item `label="neutral"`, `confidence=0.5`, `evidence=[]`, stderr 출력 |
| 커리큘럼 일치도 분석 실패 | `{"score": None, "reason": "분석 실패"}` 반환, stderr 출력 |
| evidence 0개인 item | `selected_evidence: null` (키는 반드시 존재) |
| `start_ts`/`end_ts` 파싱 실패 | `_parse_ts_to_seconds()` → `0.0`, `duration_min = 1.0` fallback |
| chunks 빈 리스트 | `words_per_minute = token_count / 1.0` fallback |
