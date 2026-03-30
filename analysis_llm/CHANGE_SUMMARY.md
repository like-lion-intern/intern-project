# 수정 사항 정리

## 1. Evidence 추출 구조 개선

대상 파일:
- `src/features.py`
- `src/evidence_extractor.py`
- `src/rerank.py`
- `src/llm_analysis.py`

### 1-1. 1순위 개선 적용: chunk 전체 -> 문장/span 단위 evidence

기존:
- evidence 후보가 거의 항상 chunk 전체 `text_preview`였음

변경:
- `features.py`에서 `text_preview`를 문장/짧은 span 단위로 분리
- 각 span을 기준으로 evidence entry 생성

추가된 구조:
- `sentence_spans`
- span별 `matched_keywords`
- span별 `local_score`

효과:
- evidence가 짧아지고 항목 적합도가 올라감
- `selected_evidence`가 긴 chunk 대신 더 직접적인 문장으로 잡히기 쉬워짐

### 1-2. 2순위 개선 적용: evidence 메타데이터 추가

기존:
- `span_text`, `context_before` 정도만 유지

변경:
- evidence에 다음 메타데이터 추가
  - `evidence_type`
  - `evidence_types`
  - `polarity`
  - `matched_keywords`
  - `segment_id`
  - `chunk_id`
  - `start_ts`
  - `end_ts`
  - `parent_label`
  - `sub_label`
  - `local_score`
  - `rerank_score`

효과:
- 왜 선택된 근거인지 추적 가능
- 디버깅과 규칙 조정이 쉬워짐

### 1-3. 3순위 개선 적용: positive / negative evidence 분리

기존:
- item별 evidence가 한 리스트에 섞여 있었음
- positive / negative 근거가 구조적으로 구분되지 않았음

변경:
- `evidence_extractor.py`에서 item별로 아래 구조를 반환하도록 변경

```json
{
  "supporting_evidence": [...],
  "contrary_evidence": [...]
}
```

예:
- `불필요한 반복 표현` -> `contrary_evidence` 중심
- `발화 완결성` -> `supporting_evidence` / `contrary_evidence` 모두 가능

효과:
- LLM이 긍정/부정 근거를 구분해서 해석 가능
- 잘못된 한쪽 편향을 줄일 수 있음

### 1-4. item 이름 대신 설명문 query 사용

기존:
- rerank query가 item 이름 자체였음
  - 예: `개념 정의`, `실습 연계`

변경:
- `evidence_extractor.py`에 item별 설명문 query 추가
  - 예: `핵심 개념의 의미나 정의를 직접 설명하는 발화`
  - 예: `설명을 실습 행동으로 자연스럽게 연결하는 발화`

효과:
- E5 rerank와 keyword fallback 둘 다 더 안정적으로 동작

### 1-5. evidence type 중복 span 병합

기존:
- 같은 문장이 `filler_spans`, `repetition_spans` 등으로 중복 저장될 수 있었음

변경:
- 동일 span + 동일 polarity 기준으로 병합
- `evidence_types` 리스트에 관련 타입을 함께 저장

효과:
- 같은 문장이 여러 번 반복 출력되지 않음
- 한 근거가 여러 신호에 의해 선택되었음을 보존 가능

## 2. LLM 입력 구조 수정

대상 파일:
- `src/llm_analysis.py`

### 2-1. 새 evidence 구조를 프롬프트에 반영

기존:
- item별 evidence를 단일 리스트처럼 사용

변경:
- `supporting_evidence`
- `contrary_evidence`

를 분리해서 LLM 프롬프트에 전달

추가 반영 내용:
- `evidence_type`
- `polarity`
- `rerank_score`

효과:
- LLM이 긍정 근거와 문제 근거를 혼동하지 않도록 개선

### 2-2. 한국어 검증 규칙 완화

기존:
- `english == 0` 조건 때문에 `DB`, `API` 같은 약어만 있어도 실패

변경:
- `korean_ratio >= 0.8`
- `english_ratio <= 0.15`

효과:
- 한국어 중심 문장인데 기술 약어가 조금 포함된 경우 허용
- `Non-Korean reason detected` 오탐 감소

## 3. 커리큘럼 일치도 분석 보강

대상 파일:
- `src/llm_analysis.py`

### 3-1. JSON 파싱 보정 추가

기존:
- `json.loads(raw)` 한 번 실패하면 바로 `분석 실패`

변경:
- 응답에서 JSON 객체 부분만 추출
- 일부 잘린 응답도 `score`, `reason` 복구 시도
- malformed JSON에 대한 보정 파서 추가

### 3-2. 재시도 로직 추가

기존:
- 한 번 호출 후 종료

변경:
- 최대 3회 재시도
- 재시도 프롬프트에 JSON 형식 재강조 문구 추가

### 3-3. JSON 응답 강제 옵션 추가

변경:
- `response_mime_type="application/json"` 추가

효과:
- `JSONDecodeError`
- `Unterminated string`
- 앞뒤 설명문이 섞인 응답

같은 실패 확률을 낮춤

## 4. 실행 환경/모델 관련 정리

### 4-1. 추천 실행 명령

```bash
cd /Users/jinsuhhur/coding/nlp_intern/nlp_intern_task/analysis_llm
export GOOGLE_API_KEY="유효한_키"
export GEMINI_MODEL="gemini-2.5-flash"
../.venv/bin/python3 src/pipeline.py --date 2026-02-02 --base-path ../data --output-path outputs
```

### 4-2. 메타데이터 CSV 위치

현재 코드 기준:

```text
../data/강의 메타데이터.csv
```

즉 `--base-path` 바로 아래에 있어야 함

### 4-3. 모델 기본값 관련 주의

코드 기본값은 한때 `gemini-2.0-flash`였고,
신규 사용자 기준 404가 발생할 수 있음

실행 시:

```bash
export GEMINI_MODEL="gemini-2.5-flash"
```

권장

## 5. 결과 포맷 영향

### 5-1. 입력 JSON
- 유지
- `features/<date>.json`
- `semantic_chunks/<date>.json`

### 5-2. `*_result.json`
- 스키마는 유지
- 다만 내부 `reason`, `selected_evidence` 내용은 달라질 수 있음

### 5-3. `*_evidence.json`
- 스키마 변경

기존:

```json
{
  "항목명": [
    {
      "span_text": "...",
      "context_before": ["..."]
    }
  ]
}
```

변경:

```json
{
  "항목명": {
    "supporting_evidence": [...],
    "contrary_evidence": [...]
  }
}
```

## 6. Keyword Rule 정교화 적용

대상 파일:
- `src/features.py`

### 6-1. `KEYWORD_RULES` 실제 연결

기존:
- keyword 개선안이 아이디어 수준으로만 정리되어 있었음
- 실제 evidence 추출은 여전히 예전 단순 keyword 리스트를 사용

변경:
- `features.py` 상단에 `KEYWORD_RULES` 추가
- 아래 항목들은 `strong`, `weak`, `remove_single` 규칙을 실제 signal/evidence 계산에 연결
  - `불필요한 반복 표현`
  - `발화 완결성`
  - `언어 일관성`
  - `학습 목표 안내`
  - `전날 복습 연계`
  - `설명 순서`
  - `핵심 내용 강조`
  - `마무리 요약`
  - `개념 정의`
  - `비유 및 예시 활용`
  - `선행 개념 확인`
  - `발화 속도 적절성`
  - `예시 적절성`
  - `실습 연계`
  - `오류 대응`
  - `이해 확인 질문`
  - `참여 유도`
  - `질문 응답 충분성`

추가된 보조 함수:
- `_rule_keywords`
- `_match_rule`
- `_passes_rule`

효과:
- `이해`, `같이`, `다시`, `처럼`, `의미`, `이제`, `그러면` 같은 약한 단독 키워드 오탐 감소
- item별로 stronger signal이 있을 때만 evidence 후보가 되도록 정리

### 6-2. 문장 형태 validator 추가

기존:
- keyword만 맞으면 evidence 후보가 될 수 있었음

변경:
- 아래 validator를 추가해서 특정 항목은 문장 형태까지 함께 확인
  - `_is_question_like`
  - `_is_participation_prompt`
  - `_is_question_answer_like`
  - `_is_step_sequence`
  - `_is_summary_like`
  - `_is_definition_like`

적용 항목:
- `이해 확인 질문`
- `참여 유도`
- `질문 응답 충분성`
- `설명 순서`
- `마무리 요약`
- `개념 정의`
- `실습 연계`

효과:
- 학습 목표 안내 문장이 `이해 확인 질문`으로 잘못 잡히는 문제 감소
- 자기 설명 문장이 `참여 유도`로 잘못 잡히는 문제 감소
- 단순 전환 멘트가 `설명 순서`로 잡히는 문제 감소

### 6-3. 실제 검증 결과

검증:

```bash
./.venv/bin/python3 -m py_compile analysis_llm/src/features.py analysis_llm/src/evidence_extractor.py analysis_llm/src/rerank.py analysis_llm/src/llm_analysis.py
```

실데이터 `2026-02-02` 기준 확인 결과:
- `이해 확인 질문`: 기존 오탐 evidence 제거
- `참여 유도`: 기존 오탐 evidence 제거
- `설명 순서`: 기존 전환 멘트성 evidence 제거

## 7. Evidence Selection 정책 보강

대상 파일:
- `src/features.py`

### 7-1. 3단계 evidence selection 구조 적용

기존:
- keyword 규칙이 너무 엄격해지면서 recall이 크게 줄어듦
- validator를 통과하지 못하면 evidence가 바로 비어버리는 경우가 많았음

변경:
- evidence selection을 아래 3단계로 변경
  1. 1차 후보 생성: `strong 1개` 또는 `weak 1개`만 있어도 일단 후보 수집
  2. 2차 필터: 항목별 validator 적용
  3. fallback: validator 통과 후보가 없으면 `weak candidate` 상위 1개만 제한적으로 허용

적용 방향:
- recall이 중요한 항목은 weak fallback 허용
- 오탐 위험이 큰 항목은 fallback 금지

### 7-2. fallback 허용/비허용 항목 분리

fallback 허용:
- `설명 순서`
- `마무리 요약`
- `개념 정의`
- `실습 연계`

fallback 비허용:
- `이해 확인 질문`
- `참여 유도`
- `질문 응답 충분성`

효과:
- 너무 비어버리는 문제는 완화
- 질문/참여/QA처럼 오탐이 치명적인 항목은 계속 엄격하게 유지

## 8. 언어 일관성 로직 개편

대상 파일:
- `src/features.py`

### 8-1. keyword 존재 여부 -> 전역 스타일 분포 기반으로 변경

기존:
- `언어 일관성`이 사실상 keyword 매치 기반 근거 선택에 가까웠음
- 개별 문장 단위로만 보면 강의 전반의 말투 일관성을 제대로 반영하기 어려웠음

변경:
- segment별로 아래 값을 계산
  - `formal_count`
  - `informal_count`
  - `style_label = formal / informal / mixed / none`
- lecture-level로 아래 지표 계산
  - `dominant_style`
  - `style_major_ratio`
  - `style_mixed_ratio`
  - `style_switch_ratio`
  - `formal_segment_ratio`
  - `informal_segment_ratio`

효과:
- `언어 일관성`이 문장 하나의 keyword가 아니라 강의 전체 분포를 반영하게 됨
- scoring에서 사용하는 `speech_style_consistency`, `style_shift_ratio`도 더 현실적인 값으로 계산됨

### 8-2. 언어 일관성 evidence를 설명용 대표 샘플로 변경

기존:
- keyword가 들어간 문장을 그대로 `언어 일관성` evidence로 사용

변경:
- `supporting_evidence`
  - 강의 전체에서 지배적인 말투를 대표하는 문장
- `contrary_evidence`
  - mixed 문장
  - dominant style과 반대 스타일 문장

즉 `언어 일관성` evidence는 판정용 규칙이 아니라,
전역 판정을 사람이 이해할 수 있게 보여주는 설명용 샘플 역할로 변경

### 8-3. 실데이터 검증 결과

실데이터 `2026-02-02` 기준:
- `dominant_style`: `informal`
- `style_major_ratio`: `0.6111`
- `style_mixed_ratio`: `0.3889`
- `style_switch_ratio`: `0.4706`

해석:
- 반말/비격식 말투가 우세하지만
- mixed 구간과 style switch가 적지 않아
- `언어 일관성`이 높다고 보기 어려운 상태로 계산됨

## 9. 아직 남아 있는 보완 포인트

### 9-1. `질문 응답 충분성` 추가 보완
- 현재도 `왜냐하면`이 들어간 설명 문장이 일부 evidence로 남을 수 있음
- 더 엄격하게 하려면 `질문 표현 + 답변 표현` 동시 존재를 강제하는 후처리가 필요함

### 9-2. 빈 evidence 처리 전략
- `이해 확인 질문`, `참여 유도`, `마무리 요약`, `개념 정의`는 규칙이 엄격해지면서 빈 evidence가 더 자주 나올 수 있음
- 이 경우는 억지 근거를 넣는 것보다 `evidence 없음`을 유지하는 편이 품질상 더 나음

### 9-3. keyword/패턴 추가 조정 가능 항목
- `질문 응답 충분성`
- `마무리 요약`
- `개념 정의`

이 세 항목은 실제 강의 데이터가 더 쌓이면 phrase 패턴을 추가로 보정할 여지가 있음

### 9-4. `selected_evidence` fallback
- 현재 `result.json`의 `selected_evidence`는 기본적으로 LLM이 채운 evidence를 사용
- LLM 실패 시 `evidence_by_item`에서 fallback 채우는 로직은 아직 별도 반영 전

### 9-5. 모델/쿼터 이슈
- Gemini quota 초과 또는 모델 미지원 시 여전히 fallback 결과 생성 가능
- 실제 품질 비교는 유효한 키와 사용 가능한 모델로 재실행 필요
