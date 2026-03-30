# AI 강의 분석 리포트 생성기 — 기획서 v2 (plan_version2.md)

> 원본 기준: `plan.md`  
> 버전 목적: 기존 기획을 유지하되, **Evidence 고도화 + Trajectory 분석 + 생성/평가 리포트 프롬프트(prompts.py)**를 실제 코드 기준으로 통합한 실행 계획

---

## 0. v2 핵심 변화 요약

v2는 기존 단일 강의 품질 진단에서 아래 3축을 추가/강화한다.

1. **Evidence 품질 강화**
- chunk 중심 근거에서 문장/span 중심 근거로 전환
- evidence 메타데이터 확장
- supporting/contrary 분리
- validator + fallback이 포함된 3단계 selection 정책 적용

2. **Trajectory(강의 궤적) 분석 추가**
- 날짜별 결과를 압축/집계하여 기간 단위 성장·퇴보·취약 패턴 분석
- API에서 재생성/조회 가능

3. **생성/평가 리포트 레이어 추가**
- `prompts.py` 기반 리포트 합성 프롬프트를 파이프라인 산출물로 저장
- 분석 JSON과 리포트 생성(문장 합성/편집) 레이어를 분리

---

## 1. 프로젝트 목적 (기존 plan 계승)

STT 강의 스크립트를 자동 분석해 체크리스트 18개 항목(5개 카테고리)에 대한
- 정량 점수,
- 정성 근거,
- 개선 제안
을 생성하고, 강의 개선 실행까지 연결 가능한 리포트를 제공한다.

추가로 v2에서는 단일 강의 결과를 넘어 **기간 단위 강의 궤적 분석**을 제공한다.

---

## 2. v2 전체 아키텍처

1. 업로드/API
- `POST /api/v1/analyze` 업로드
- `GET /api/v1/status/{job_id}` 진행 조회
- `GET /api/v1/result/{job_id}` 결과 조회

2. Stage1 (전처리)
- STT 파싱, 세션 분할, 매크로 세그멘테이션, 청킹, feature 추출

3. Stage2 (분석)
- signal 계산(`features.py`)
- evidence 추출/리랭크(`evidence_extractor.py`, `rerank.py`)
- LLM 분석(`llm_analysis.py`)
- 스코어링(`scoring.py`)
- 프론트 호환 리포트 변환(`pipeline.py`)

4. 생성/평가 리포트 프롬프트
- `prompts.py`의 `get_report_synthesis_prompt(...)`로
  `report_synthesis_prompt.txt` 생성

5. Trajectory
- `POST /api/v1/trajectory/rebuild`
- `GET /api/v1/trajectory/latest`
- `analysis_llm/src/trajectory.py`에서 기간 집계 분석

---

## 3. 전처리/분할 계획 (plan.md 유지 + 운영 고정)

### 3-1. 데이터 입력
- STT 텍스트(날짜 포함 파일명)
- 메타데이터 CSV(subject/content/instructor)

### 3-2. 전처리 정책
- 원본 보존 우선
- timestamp wrap 보정
- session split
- macro segment + semantic chunk
- 정량 feature 추출(질문, 예시, 반복, 실습 지시 비율 등)

### 3-3. 품질 게이트
- 분할 신뢰도/발화량/근거 밀도 기준으로 저신뢰 플래그 운영
- 저신뢰 세션은 구조 항목 점수 해석 시 보수적으로 처리

---

## 4. Evidence 고도화 계획 (v2 신규 핵심)

### 4-1. Evidence 구조
기본 필드:
- `evidence_type`, `evidence_types`, `polarity`
- `matched_keywords`
- `segment_id`, `chunk_id`, `start_ts`, `end_ts`
- `parent_label`, `sub_label`
- `local_score`, `rerank_score`

### 4-2. 긍정/부정 근거 분리
- `supporting_evidence`: 기능 수행 근거
- `contrary_evidence`: 취약/문제 근거

### 4-3. Selection 3단계
1. strong/weak 후보 수집
2. 항목별 validator 필터
3. validator 통과 없음 시 weak top1 fallback 허용

### 4-4. Validator 집합
- `_is_question_like`
- `_is_participation_prompt`
- `_is_question_answer_like`
- `_is_step_sequence`
- `_is_summary_like`
- `_is_definition_like`

### 4-5. Debug 관측성
`validator_debug` 기록:
- `keyword_candidates`, `validator_passed`, `validator_rejected`
- `fallback_candidates`, `fallback_used`
- `generated_entries`, `sample_rejected_spans`

---

## 5. LLM 분석 계획 (v2 보강)

### 5-1. 입력 구조
- features (정량)
- segments (맥락)
- item별 evidence (supporting/contrary)
- lecture-level signals (보조)

### 5-2. 파싱/검증 강건화
- `safe_parse_json_object`로 JSON 객체 추출 보강
- reason 문자열 `sanitize_reason` 정리 후 검증
- 한국어 검증 완화:
  - `korean_ratio >= 0.8`
  - `english_ratio <= 0.15`

### 5-3. 커리큘럼 일치도
- JSON 응답 보정 파싱
- 최대 3회 재시도
- 실패 시 fallback reason 반환

---

## 6. 스코어링/리포트 출력 계획

### 6-1. 내부 점수 산출
- item 점수 + category 점수 + 취약 카테고리 요약

### 6-2. 프론트 호환 포맷 변환
`pipeline.py`에서 final 리포트를 프론트 스키마로 정규화:
- `overall_summary`
- `overall_strengths`, `overall_weaknesses`
- `priority_improvements`
- `category_results[].items[]`

### 6-3. prompts.py 통합 (생성/평가 리포트)
`analysis_llm/src/prompts.py`를 통해 다음을 분리 운영한다.

1. 평가 LLM(`llm_analysis.py`): JSON 강제 출력
2. 생성 LLM(`prompts.py`): Markdown 리포트 합성 프롬프트

실행 반영:
- `pipeline.py`에서 `get_report_synthesis_prompt(...)` 호출
- `outputs/<date>/report_synthesis_prompt.txt` 저장

의미:
- 점수/근거 평가와 문장형 리포트 생성을 분리해 유지보수성과 품질을 동시에 확보

---

## 7. Trajectory 분석 계획 (v2 신규)

### 7-1. 입력
- `outputs/<date>/final_report.json`
- `outputs/<date>/heuristic_report.json`
- `outputs/<date>/llm_debug.json`
- 메타데이터 CSV(subject/content)

### 7-2. 압축 규칙
- 날짜별 `category_scores`
- item별 `label/confidence`
- `curriculum_match_score/reason`
- subject/contents 병합

### 7-3. 분석 결과
- 취약 패턴(반복 weak 항목)
- 성장/퇴보 추이(카테고리)
- 커리큘럼 일치도 추이
- 과목 전환 영향(가능 시)

### 7-4. API
- `POST /api/v1/trajectory/rebuild`
- `GET /api/v1/trajectory/latest`

출력 경로:
- `outputs/trajectory/<start>_<end>_trajectory.json`

---

## 8. 운영/배포 계획

1. 로컬
- `./start_local.sh`
- 분석 완료 후 리포트 + PDF 다운로드
- trajectory 재생성/조회 API 점검

2. 배포
- Cloud Run 기준 운영
- 환경변수(LLM/DB) 분리 관리

3. 관측/장애 대응
- API 에러는 JSON detail 반환
- 프론트는 text/json 혼합 응답 안전 파싱

---

## 9. 검증 계획 (Acceptance)

1. 단일 분석
- `final_report.category_results[].items[]` 비어있지 않음
- evidence polarity 분리 확인
- `validator_debug` 기록 확인

2. 생성 프롬프트
- `report_synthesis_prompt.txt` 생성 확인
- 포함 데이터(총점/카테고리/근거) 일관성 확인

3. trajectory
- 날짜 범위/총 강의 수 정상
- 취약 패턴/추이 필드 누락 없음

4. 회귀
- 기존 `/analyze` → `/status` → `/result` 흐름 유지

---

## 10. 향후 확장 (v2.1)

1. trajectory 프론트 시각화 탭 추가
2. subject 전환 전후 비교 로직 고도화
3. 생성 리포트 자동 Markdown/PDF 산출 파이프라인 추가
4. e2e 테스트(분석+trajectory+리포트 프롬프트) 자동화

