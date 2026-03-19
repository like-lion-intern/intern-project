# 코드 설명 및 실행 가이드

## 1. 현재 코드의 목적

현재 `src/` 안의 코드는 원본 STT 파일을 처음부터 직접 전처리하는 코드가 아니라, 이미 정리된 `data/features/*.json`과 `data/semantic_chunks/*.json`을 입력으로 받아 강의 분석 결과를 생성하는 파이프라인입니다.

즉, 현재 구현 범위는 다음 흐름에 해당합니다.

`입력 데이터 로드 -> lecture/segment signal 계산 -> evidence 수집 및 rerank -> heuristic scoring -> LLM 분석 -> 최종 report JSON 생성`

## 2. 전체 파이프라인

| 단계 | 입력 | 처리 내용 | 출력 |
|---|---|---|---|
| 1. 데이터 로드 | `data/features/<date>.json`, `data/semantic_chunks/<date>.json` | 날짜 기준 입력 파일을 불러옵니다. | feature 데이터, semantic chunk 데이터 |
| 2. signal 계산 | feature 데이터, semantic chunk 데이터 | lecture-level / segment-level signal과 evidence를 계산합니다. | `feature_bundle` |
| 3. evidence 구성 | `feature_bundle` | 체크리스트 항목별로 관련 signal과 evidence 후보를 모읍니다. | item별 후보 evidence |
| 4. evidence rerank | item context, candidate evidence | `multilingual-e5-small` 또는 fallback keyword 방식으로 상위 evidence를 고릅니다. | top-k evidence |
| 5. heuristic scoring | signal, evidence | 체크리스트 18개 항목에 대한 휴리스틱 점수를 계산합니다. | item/category heuristic score |
| 6. LLM 분석 | prompt packet | Gemini가 heuristic 결과를 해석해 final score, reason, improvement tip을 생성합니다. | LLM 결과 JSON |
| 7. 최종 리포트 생성 | heuristic report, LLM 결과 | 휴리스틱 결과와 LLM 결과를 합쳐 최종 report를 만듭니다. | `final_report.json` |

## 3. 파일별 설명

### 3-1. `src/loader.py`

역할:
- 날짜별 입력 파일을 읽는 로더입니다.
- 현재는 `data/features/<date>.json`과 `data/semantic_chunks/<date>.json`을 기본 입력으로 사용합니다.
- 호환성을 위해 `features/`, `semantic_chunks/` 구조도 fallback으로 탐색합니다.

핵심 함수:
- `load_data(date, base_path=".")`

### 3-2. `src/features.py`

역할:
- lecture-level signal과 segment-level signal을 계산합니다.
- semantic chunk를 기반으로 각 segment의 evidence를 만듭니다.

주요 계산 항목:
- 반복 표현 관련 signal
- discourse marker 관련 signal
- 질문 수, 예시 수, 실습 지시 비율
- 학습 목표 안내, 복습 연계, 마무리 요약
- 개념 정의, 예시/비유, 선행 개념 연결
- 참여 유도, 이해 확인 질문, 질문 응답

출력 구조:
- `lecture_signals`
- `segments`
  - `signals`
  - `evidence`
  - `parent_label`
  - `sub_label`

### 3-3. `src/scoring.py`

역할:
- 체크리스트 5개 카테고리, 18개 항목에 대한 scoring rule을 정의합니다.
- signal을 휴리스틱 점수로 바꾸고, 항목별 evidence를 수집합니다.
- LLM에 전달할 `prompt_packet`을 만듭니다.

주요 기능:
- 항목별 signal rule 정의
- segment/lecture signal 집계
- evidence 수집 및 dedupe
- heuristic score 계산
- category packet / prompt packet 생성

### 3-4. `src/rerank.py`

역할:
- evidence 후보 문장들 중에서 항목에 가장 적합한 근거를 다시 정렬합니다.

동작 방식:
- 우선 `intfloat/multilingual-e5-small` 임베딩 모델을 사용합니다.
- 모델 로드가 실패하면 keyword overlap 기반 fallback으로 동작합니다.

### 3-5. `src/llm_analysis.py`

역할:
- heuristic scoring 결과를 LLM이 교육적 관점에서 다시 해석하도록 합니다.
- final score, adjustment reason, category summary, improvement tip을 생성합니다.

주의:
- `GOOGLE_API_KEY`가 설정되지 않으면 실제 LLM 호출 대신 fallback 결과를 만듭니다.

### 3-6. `src/pipeline.py`

역할:
- 전체 실행 진입점입니다.
- 각 모듈을 순서대로 호출해 최종 report를 생성합니다.

실행 순서:
1. `load_data`
2. `calculate_signals`
3. `build_prompt_packet`
4. `build_heuristic_report`
5. `analyze_with_llm`
6. `build_final_report`
7. 결과 JSON 저장

## 4. 현재 파이프라인과 `파이프라인.md`의 대응 관계

| `파이프라인.md` 단계 | 현재 코드 반영 여부 | 설명 |
|---|---|---|
| 데이터 전처리 | 부분 반영 | raw STT를 직접 처리하지는 않고, 전처리 산출물인 `features.json`, `semantic_chunks.json`을 입력으로 사용합니다. |
| macro segmentation / sub-label | 부분 반영 | segment를 새로 생성하지는 않지만, 이미 들어 있는 `parent_label`, `sub_label`을 활용합니다. |
| 정량 Feature 추출 | 구현 | `features.py`에서 lecture/segment signal을 계산합니다. |
| 분석 LLM Segment Analysis | 구현 | `scoring.py`와 `llm_analysis.py`가 evidence 기반 prompt를 만들고 분석합니다. |
| 강의 수준 집계 + Scoring | 구현 | heuristic baseline + LLM 보정 구조로 final score를 만듭니다. |
| Trajectory 분석 | 미구현 | 현재 코드에는 포함되어 있지 않습니다. |
| 리포트 생성 | 부분 구현 | `final_report.json`은 생성하지만 PDF/DOCX/대시보드 출력은 아직 없습니다. |

## 5. 입력 데이터 구조

현재 기본 입력 경로는 다음과 같습니다.

```text
data/
  features/
    2026-02-02.json
    2026-02-03.json
    ...
  semantic_chunks/
    2026-02-02.json
    2026-02-03.json
    ...
```

## 6. 출력 구조

실행 결과는 기본적으로 `outputs/<date>/` 아래에 저장됩니다.

예시:

```text
outputs/
  2026-02-02/
    heuristic_report.json
    final_report.json
    debug_packet.json
    llm_debug.json
```

파일 설명:
- `heuristic_report.json`: 휴리스틱 점수와 item별 signal/evidence
- `final_report.json`: 최종 분석 결과
- `debug_packet.json`: feature bundle과 prompt packet
- `llm_debug.json`: LLM 호출 성공 여부와 raw debug 정보

## 7. 실행 명령어

### 7-1. 기본 실행

```bash
python3 src/pipeline.py --date 2026-02-02
```

이 명령은 아래와 같이 동작합니다.
- 입력: `data/`
- 출력: `outputs/2026-02-02/`

### 7-2. 디버그 포함 실행

```bash
python3 src/pipeline.py --date 2026-02-02 --debug
```

이 명령은 `debug_packet.json`, `llm_debug.json`까지 함께 저장합니다.

### 7-3. 출력 폴더 직접 지정

```bash
python3 src/pipeline.py --date 2026-02-02 --output_dir outputs/custom_run_2026-02-02 --debug
```

### 7-4. 입력 경로 직접 지정

```bash
python3 src/pipeline.py --date 2026-02-02 --base_path data --debug
```

## 8. LLM 사용 시 주의사항

실제 Gemini 분석을 사용하려면 환경변수 `GOOGLE_API_KEY`가 필요합니다.

예시:

```bash
export GOOGLE_API_KEY="YOUR_API_KEY"
python3 src/pipeline.py --date 2026-02-02 --debug
```

API 키가 없으면 fallback 결과가 생성되며, 이 경우 `llm_debug.json`에 `LLM_NOT_CONFIGURED`가 기록됩니다.
