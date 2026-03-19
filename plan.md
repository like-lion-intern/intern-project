# AI 강의 분석 리포트 생성기 — 기획서 (plan.md)

> **목표**: STT 기반 강의 스크립트를 자동 분석하여, 체크리스트 18개 항목에 대한 정량·정성 평가 리포트를 생성하는 시스템

---

## 0. 진행 현황 업데이트 (2026-03-18)

아래 내용은 초기 기획 대비 **현재 실제 구현/실행 완료 상태**를 반영한 현황입니다.

### 0-1. 전처리/분할 파이프라인 구현 완료 항목

| 구분 | 현재 상태 | 산출물 경로(예시) |
|---|---|---|
| STT 파싱 (`<HH:MM:SS>`) | 완료 | `outputs/common/parsed/*.jsonl` |
| Timestamp wrap 보정 | 완료 (12h/24h wrap 처리) | `scripts/run_pipeline.py` |
| Session Split | 완료 (시간 gap + 키워드) | `outputs/common/session_split/*.json` |
| Discourse Marker 집계 | 완료 | `outputs/common/discourse_marker/*.json` |
| Macro Segmentation | 완료 (유사도 + gap + 전이표현 + 기능신호) | `outputs/by_model/*/macro_segments/*.json` |
| Semantic Chunking | 완료 | `outputs/by_model/*/semantic_chunks/*.json` |
| Segment/Chunk 라벨링 | 완료 (`label`, `parent_label`, `sub_label`) | `outputs/by_model/*/.../*.json` |
| 정량 Feature 추출 | 완료 (질문/예시/반복/전문용어/필러/실습지시 비율) | `outputs/by_model/*/features/*.json` |
| 결과 검증 스크립트 | 완료 | `scripts/verify_outputs.py` |

### 0-2. 모델 실험 및 현재 의사결정

- 실험 모델: `multilingual-e5-large`, `BAAI/bge-m3`
- 현재 의사결정: **macro segmentation 기준 e5 결과 채택**
- 채택 근거(요약):
  - `segment_count` 안정성: e5 평균 35.0, bge-m3 평균 123.3
  - bge-m3는 과분할 경향이 강함
  - 후속 분석 LLM 입력 단위로 e5가 문맥 보존에 유리

### 0-3. 운영/실행 방식 (보안 반영)

- 데이터 원본은 외부 업로드 없이 로컬/Google Drive 경로에서 처리
- Colab 실행 시 기본 저장 경로:
  - `/content/drive/MyDrive/preprocessing`
- 코드 경로:
  - `/content/drive/MyDrive/stt_log_code`
- 진행률 추적:
  - `progress.json` (`elapsed_sec`, `eta_sec`, `percent` 포함)

### 0-4. 기획 대비 미구현 항목 (다음 단계)

| 항목 | 상태 | 비고 |
|---|---|---|
| 카테고리별 분석 LLM 5병렬 호출 | 미구현 | 기획 존재, 코드 미연결 |
| Step 1~9 evidence/rerank/compact packet | 미구현 | 전처리 이후 분석 엔진 단계 |
| final_score / reason / improvement_tip 자동 생성 | 미구현 | 분석 LLM 단계에서 구현 예정 |
| category 재집계 및 리포트 자동 작성 | 미구현 | 중간평가 이후 구현 예정 |

---

## 1. TXT 파일 전처리 파이프라인

### 1-1. 원본 데이터 현황

| 속성 | 내용 |
|---|---|
| 파일 수 | 15개 (3주 × 5일) |
| 파일 크기 | 약 135KB ~ 265KB (평균 ~220KB) |
| 행 수 | 파일당 약 1,200 ~ 1,500줄 |
| 포맷 | `<HH:MM:SS> speaker_id: 발화 텍스트` |
| 화자 ID | 해시 형태 (예: `b54f46b0`), 날짜마다 변경됨 |
| 특이사항 | 단일 화자(강사)만 있는 날도 있고, 2~3명이 등장하는 날도 있음 (수강생 발화 포함 가능) |

### 1-2. 전처리 단계

```
[원본 TXT] → [파싱] → [화자 분리] → [시간 구간 분할] → [텍스트 정제] → [메타데이터 결합] → [분석 단위 청크]
```

#### Stage 1: 파싱 (Raw Parsing)
- 정규식으로 타임스탬프, 화자 ID, 발화 텍스트 추출
- 타임스탬프를 초 단위로 변환하여 정렬 보장
- 포맷: `{ timestamp_sec: int, speaker_id: str, text: str }`

#### Stage 2: 화자 분리 (Speaker Separation)
- **문제**: 화자 ID가 해시값이라 누가 강사인지 직접 라벨링 불가
- **해결 전략**:
  - 발화량 기반 추론 — 가장 많은 발화를 한 화자를 강사로 판별 (강의 특성상 강사 발화가 압도적으로 많음)
  - 메타데이터 CSV의 `instructor` 컬럼과 교차 검증
- 강사 발화만 추출하여 분석 대상으로 설정 (수강생 발화는 상호작용 분석에만 활용)

#### Stage 3: 시간 구간 분할 (Session Segmentation)
- 1차 세션 분할: 메타데이터 시간표 기반 **오전(09:00~12:00) / 오후(13:00~18:00)** 매핑
- 2차 매크로 분할: **도입/전개/실습/정리** 4단계로 분할
  - 도입: 시작 0~8분 + 목표/복습 신호어(`오늘`, `목표`, `어제`, `지난 시간`)
  - 정리: 종료 전 8분 + 요약 신호어(`정리`, `요약`, `마무리`, `다음 시간`)
  - 실습: 긴 무음/간격(예: 10분+) 이후 재개 구간, 코드 실행/오류 대응 신호어 기반 보조
  - 전개: 나머지 구간
- 3차 마이크로 분할: 2~3분 슬라이딩 윈도우로 정량 특징 계산
  - 발화 속도(WPM), 필러 밀도, 질문문 비율, 화자 전환 횟수
- 신뢰도 플래그:
  - `segment_split_low_conf=true` if 도입/정리 근거 구간 미검출 또는 윈도우 특징 불안정
  - 저신뢰 세션은 구조 카테고리 자동채점 제외 + human review 대상으로 라우팅

#### Stage 4: 텍스트 정제 (Text Cleaning)

##### 실제 발견된 STT 오류 유형

| 유형 | 설명 | 실제 사례 |
|---|---|---|
| 영어 기술 용어 깨짐 | 영어를 한글+영어 혼합으로 변환 | `N아I어` → NIO, `마이에큐L` → MySQL, `서브SST` → SUBSTR |
| 한글 음차 변환 | 영어 발음을 한글로 표기 (부분적 의미 파악 가능) | `콘캣` → CONCAT, `시리얼 라이저블` → Serializable |
| 완전 의미 불명 | 문맥 없이는 해석 불가능 | `실GR U딜를 다 해` → CRUD를 다 해?, `간다로C를 해서` → ? |

> 15개 파일 전체에서 영한 혼합 패턴이 파일당 약 130~270건 발견됨

##### 처리 전략: LLM 중심 + 최소 규칙 보조 (Hybrid)

- **❌ 전면 규칙 교정**: 규칙 기반 매핑 사전은 끝이 없고, 새 오류에 대응하기 어려움
- **❌ 삭제 중심 정제**: 의미 불명 텍스트를 제거하면 강의 흐름이 끊겨 구조 분석이 어려움
- **✅ 기본 전략은 LLM 해석 보조**: 전처리 단계에서 LLM을 전면 교정기로 쓰지 않고, 평가 단계에서 문맥 해석용으로 사용
  - "언어 표현 품질" 평가 시 STT 변환 오류와 강사의 실제 발화 습관을 구분하도록 지시
- **✅ 정량 지표 계산 시에만 최소 정규화 적용**: 용어 빈도/필러 비율 계산 정확도가 필요한 지점에 한해 사전 기반 보정 사용
- **✅ 제한적 LLM 교정(옵션)**: 폐쇄형 용어 후보 집합 내에서만 치환 허용 + confidence 로그 저장

##### 원본 보존 원칙

- **과도한 정제는 하지 않음** — "불필요한 반복 표현" 평가 항목 자체가 원래 발화 습관을 분석해야 하므로
- 명백히 반복된 동일 문장만 제거 (STT 중복 출력)
- 원본 텍스트는 반드시 보존하고, 정규화가 필요할 경우 별도 컬럼에 저장

##### 선택적 보조 전처리: 기술 용어 정규화 사전 (optional)

정량적 통계(필러 표현 빈도 등)를 정확히 내고 싶을 때만 최소한으로 활용:

```python
# 최소한의 기술 용어 정규화 (원본 보존, 별도 컬럼에 적용)
TERM_MAP = {
    r'마이?에?큐L|마이\s*스Q일|마이너스큐': 'MySQL',
    r'N아?I어?|N아IO': 'NIO',
    r'I이?O': 'I/O',
    r'서브SS?T': 'SUBSTR',
}
```

#### Stage 5: 메타데이터 결합 (Metadata Enrichment)
- CSV 메타데이터와 결합:
  - `date`, `subject`, `content`, `instructor` 정보 부착
  - 분석 시 "해당 강의에서 다루는 주제"를 LLM에게 맥락으로 전달 가능
- 결합 결과 형태:
  ```json
  {
    "date": "2026-02-02",
    "session": "오전",
    "subject": "객체지향 프로그래밍",
    "content": "데코레이터 패턴, 옵저버 패턴",
    "instructor": "김영아",
    "segments": [
      { "type": "도입", "text": "...", "start_sec": 0, "end_sec": 600 },
      { "type": "본론", "text": "...", "start_sec": 600, "end_sec": 3200 },
      { "type": "마무리", "text": "...", "start_sec": 3200, "end_sec": 3600 }
    ]
  }
  ```

#### Stage 6: 분석 단위 청킹 (Chunking for LLM)
- LLM 컨텍스트 윈도우 고려 (GPT-4o 기준 128k 토큰)
- 한 세션당 텍스트량이 ~120KB ≈ ~40,000자 → 충분히 1회 호출에 담을 수 있음
- **추천 전략**:
  - **세션 단위** (오전/오후)를 기본 분석 단위로 설정
  - 각 평가 항목별로 관련 segment만 추출하여 추가 맥락 제공
    - 예: "학습 목표 안내" → 도입부 segment만 전달
    - 예: "마무리 요약" → 마무리 segment만 전달

### 1-3. 팀안/개인안 비교 및 최종 전처리 결정

| 접근안 | 논리적 타당성(정확도) | 물리적 효율(시간/비용) | 리스크 |
|---|---|---|---|
| A. 규칙 기반 대규모 교정 | 중간 (명시된 패턴만 정확) | 낮음 (사전 관리 비용 큼) | 신규 STT 오류 대응 지연 |
| B. 전면 LLM 위임 (팀안) | 중간~높음 (문맥 추론 강함) | 중간 (사전 관리 없음) | 정량 카운팅 편차 가능 |
| C. Hybrid: 원본 보존 + LLM 중심 + 최소 정규화 (개인안 확장) | **높음** (맥락 추론 + 지표 안정화) | **높음** (유지보수 최소화, 재분석 비용 절감) | 정규화 사전 스코프 관리 필요 |

#### 최종 채택안: C (Hybrid)

- 분석 본문은 원본 텍스트를 기준으로 LLM이 문맥 해석
- 점수 산정에 직접 쓰이는 정량 지표(용어 빈도, 필러 비율)에만 최소 정규화 적용
- 정규화 결과는 `normalized_text` 같은 별도 컬럼으로 저장하고 `raw_text`는 항상 보존
- 분기 규칙:
  - 품질 평가/근거 인용: `raw_text` 우선
  - 통계 집계/카운팅: `normalized_text` 사용

> 결론: 팀안(LLM 중심)의 운영 단순성을 유지하면서, 개인안의 정량 안정성을 결합한 Hybrid가 정확도와 비용 모두에서 가장 효율적임.

### 1-4. v2 운영 확정안 (분석 입력 고정 규칙)

#### 확정 규칙 1) 강사 추론
- 기본 규칙: 세션 내 발화량 `top1` 화자를 강사로 사용
- 저신뢰 조건: `top1_ratio < 0.75` 또는 `margin_ratio < 0.25`
- 처리 방침: 자동 점수는 유지하되 `human_review_required=true` 플래그로 후검토 대상 지정

#### 확정 규칙 2) 세션/구간 분할
- 오후 상대시간(`01~05시`)은 오후 세션 fallback 매핑 허용
- `segment_split_low_conf=true` 세션은 **구조 항목(강의 도입 및 구조)** 자동채점 제외
  - `structure_scoring_enabled=false`로 분석 파이프라인에서 분기 처리

#### 확정 규칙 3) 텍스트 소스 사용
- 품질 평가/근거 인용: `raw_text` 사용
- 정량 집계/카운팅(필러 비율, 용어 빈도): `normalized_text` 사용
- 원칙: 정규화 텍스트는 보조 통계용이며, 의미 해석/인용에는 사용하지 않음

### 1-5. 평가 항목별 Segmentation 매핑 (v3 강화)

체크리스트 18개 항목을 동일 구간으로 평가하지 않고, 항목별 근거 구간을 고정한다.

| 카테고리 | 평가 항목 | 근거 우선 구간 | 핵심 정량 특징 | N/A 또는 Review 조건 |
|---|---|---|---|---|
| 언어 표현 품질 | 불필요한 반복 표현, 발화 완결성, 언어 일관성 | 전체 + 2~3분 마이크로 윈도우 | 필러 비율, 미완결 비율, 종결 어미 일관성 | 발화량 부족 시 N/A |
| 강의 도입 및 구조 | 학습 목표 안내, 전날 복습 연계 | 도입 0~8분 | 목표/복습 키워드 존재, 명시 시점 | 도입 구간 저신뢰 시 Review |
| 강의 도입 및 구조 | 마무리 요약 | 종료 전 8분 | 요약 키워드 존재, 핵심 재언급 횟수 | 정리 구간 저신뢰 시 Review |
| 강의 도입 및 구조 | 설명 순서, 핵심내용 강조 | 전개+실습 구간 | 개념→예시→실습 전이 패턴, 강조 문구 빈도 | 전이 패턴 미검출 시 Review |
| 개념 설명 명확성 | 개념정의, 비유/예시, 선행개념, 발화속도 | 전개 구간 | 정의문 패턴, 예시 수, 전제 설명, WPM | 근거 인용 2건 미만 시 N/A |
| 예시 및 실습 연계 | 예시 적절성, 실습 연계, 오류 대응 | 실습 구간 우선 | 실습 전환 문구, 오류 키워드 대응 턴 | 실습 구간 부재 시 N/A |
| 수강생 상호작용 | 이해 확인 질문, 참여 유도, 질문 응답 충분성 | 전 구간(질의응답 집중) | 질문문 비율, 화자 왕복(turn pair), 답변 길이 | 다화자/상호작용 희소 시 Review |

### 1-6. 자동 채점 Gate 기준 (품질 보장)

- `segment_split_low_conf=true` 세션: "강의 도입 및 구조" 자동채점 제외 (`structure_scoring_enabled=false`)
- 항목별 근거 인용이 2건 미만: 해당 항목 `N/A` 또는 `human_review_required=true`
- 다화자 세션에서 `top1_ratio < 0.75` 또는 `margin_ratio < 0.25`: 상호작용/강사 관련 항목 Review
- Review 플래그 세션은 최종 리포트에서 "자동평가 신뢰도 낮음" 배지 표시

### 1-7. 단계별 전처리 산출물 폴더 구조

전처리 결과는 단일 CSV가 아니라 검증 가능한 단계별 폴더로 저장한다.

```text
outputs/preprocessing_eda_v2/
  stage_01_parsed/
  stage_02_speaker/
  stage_03_segmentation/
  stage_04_text_cleaning/
  stage_05_enriched/
  stage_06_validation/
  stage_07_eda/
```

- Stage별 주요 파일:
  - `stage_01_parsed/parsed_utterances.csv`, `preprocessing_file_summary.csv`
  - `stage_02_speaker/instructor_session_summary.csv`, `validation_instructor_confidence.csv`
  - `stage_03_segmentation/session_segment_assignments.csv`, `validation_segment_confidence.csv`
  - `stage_04_text_cleaning/text_cleaning_diff.csv`, 정규화 검증 파일
  - `stage_05_enriched/preprocessed_utterances.csv` (분석 입력 기준본)
  - `stage_06_validation/VALIDATION_REPORT.md`, `validation_summary.json`
  - `stage_07_eda/EDA_REPORT.md`, 시각화 PNG

---

## 2. 프롬프팅 방법론

### 2-1. 전체 구조: 다단계 프롬프트 체인

단일 거대 프롬프트보다 **카테고리별 분리 × 2-Step** 방식이 정확도·설명력 모두 우수함.

```
[Session Transcript]
        │
  ┌─────┼──────┐──────┐──────┐──────┐
  ▼     ▼      ▼      ▼      ▼      ▼
Cat.1  Cat.2  Cat.3  Cat.4  Cat.5  (카테고리별 분석)
  │     │      │      │      │
  │  [Step 1: 사실 추출] × 3회 (Self-Consistency)
  │  [Step 2: Rubric 평가] × 3회 (Self-Consistency)
  │     │      │      │      │
  └─────┴──────┴──────┴──────┘
              │
         종합 리포트 생성
```

### 2-2. 프롬프트 설계 원칙

#### 핵심 원칙: 2-Step 분석 (사실 추출 → 평가 분리)

단일 프롬프트로 "분석하고 점수 매겨라"고 하면 **근거 없이 점수만 내는 문제**가 발생함.
이를 방지하기 위해 분석을 2단계로 분리:

```
[Step 1: 사실 추출 — 주관 배제]
"도입부에서 학습 목표를 언급했는가? 있다면 해당 발화를 인용하라"
"'이제', '그래서' 등 필러 표현이 각각 몇 회 등장하는가?"
→ 정량 데이터 + 인용만 수집, 점수는 매기지 않음

[Step 2: 평가 — Rubric 기반 점수 부여]
Step 1의 추출 결과 + Rubric 앵커 기준 → 점수 산출
→ "필러 표현이 분당 3.2회 → Rubric 기준 2점" 형태로 판단
```

> **왜 분리하는가?** Step 1에서는 "사실인지 아닌지"만 판단하므로 주관 개입이 최소화됨.
> Step 2에서는 이미 추출된 사실에 정량적 Rubric을 적용하므로 일관성이 높아짐.

#### 정량적 Rubric 기준

기존의 정성적 기준("과도하게 반복하지 않는가")을 **측정 가능한 수치 기준**으로 전환:

| AS-IS (정성적) ❌ | TO-BE (정량적) ✅ |
|---|---|
| 필러 표현을 과도하게 반복하지 않는가 | 필러 표현 출현율이 전체 발화의 N% 미만인가 |
| 학습 목표를 명확히 안내하는가 | 강의 시작 5분 이내에 목표/순서를 명시적으로 언급했는가 |
| 문장이 완결된 형태로 끝맺음 되는가 | 미완결 문장 비율이 전체 발화의 N% 미만인가 |

> LLM에게 **먼저 카운팅/추출을 시킨 뒤** 그 수치를 기반으로 점수를 매기게 하면
> 동일한 스크립트에 대해 일관된 점수를 낼 확률이 높아짐.

#### Self-Consistency (다수결 투표)

단일 LLM 호출의 편향을 줄이기 위해 **동일 분석을 3회 수행**하고 중앙값 채택:

- temperature 0.3~0.5로 3회 호출
- 3회 점수가 일치하면 → 해당 점수 확정
- 2:1로 갈리면 → 다수결 채택
- 3회 모두 다르면 → "판단 불확실" 플래그 + 사람 리뷰 대상으로 표시

> **비용 계산 (2-Step + Self-Consistency 반영)**:
> - Step 1(추출) 5개 카테고리 × 3회 = 15회
> - Step 2(평가) 5개 카테고리 × 3회 = 15회
> - **세션당 총 30회** 호출 (기존 단일 프롬프트 5회 대비 6배)
> - 30세션 기준 총 900회 → GPT-4o 기준 약 $45~90 추정
> - 비용 절감 전략: Step 1은 1회만 수행하고 Step 2만 3회 반복 → 세션당 20회로 감소 가능

#### Few-shot의 역할 (제한적 활용)

Few-shot 예시는 **평가 정확도 향상**보다 **출력 포맷 일관성**과 **점수 보정(calibration)** 용도로 활용:

- 팀에서 1~2개 세션을 수동 리뷰한 결과를 프롬프트에 포함
- 예시 제작 방법: LLM zero-shot 결과 → 팀 리뷰/수정 → 합의된 결과가 few-shot 예시
- **진짜 품질을 올리는 건 Rubric의 구체성과 2-step 분리**이며, few-shot은 보조적 역할

#### 기타 설계 원칙

| 원칙 | 설명 |
|---|---|
| **역할 정의** | "당신은 교육 품질 관리 전문 분석가입니다" — 도메인 전문성 부여 |
| **구조화된 출력** | JSON 스키마로 출력 형태를 강제 (Structured Output / Function Calling) |
| **가중치 반영** | 높음/중간/낮음 가중치를 프롬프트에 명시하여 스코어링에 반영 |

### 2-3. 카테고리별 프롬프트 템플릿

#### 공통 시스템 프롬프트

```
당신은 교육 컨설팅 전문가입니다. STT로 변환된 강의 스크립트를 분석하여 
강의 품질을 평가합니다.

[STT 데이터 특성 안내]
- 이 스크립트는 음성 → 텍스트(STT) 자동 변환 결과입니다.
- 영어 기술 용어(MySQL, NIO, I/O, SUBSTR 등)가 한글과 섞여 변환되어 있을 수 있습니다.
  예: "마이에큐L" = MySQL, "N아I어" = NIO, "서브SST" = SUBSTR
- 변환 오류와 강사의 실제 발화 습관을 구분하여 평가하세요.
- "언어 표현 품질" 평가 시 STT 변환 오류 자체를 감점 요인으로 삼지 마세요.

[분석 절차 — 반드시 아래 순서를 따르세요]
1. 먼저 해당 항목과 관련된 발화를 스크립트에서 찾아 인용하세요 (사실 추출)
2. 인용한 발화에 대해 정량 분석을 수행하세요 (빈도, 비율, 횟수 등)
3. 정량 분석 결과를 Rubric 앵커 기준과 대조하여 점수를 산출하세요
4. 점수에 대한 종합 분석과 개선 제안을 작성하세요

[평가 규칙]
1. 1~5점으로 평가합니다 (5: 매우 우수, 4: 우수, 3: 보통, 2: 미흡, 1: 매우 미흡)
2. N/A는 해당 항목을 평가할 수 있는 내용이 스크립트에 없을 때만 사용합니다
```

#### 예시 — 카테고리 1: 언어 표현 품질 (2-Step 적용)

**Step 1: 사실 추출 프롬프트**

```
[카테고리 1: 언어 표현 품질 — 사실 추출]

아래 강의 스크립트에서 다음 데이터를 추출하세요. 점수는 매기지 마세요.

## 추출 항목

1. **필러 표현 빈도 분석**
   - "이제", "그래서", "그러면", "이렇게", "그 다음에" 각각의 등장 횟수
   - 전체 발화 줄 수 대비 필러 표현 포함 비율 (%)
   - 필러가 한 문장에 2회 이상 등장하는 사례 인용 (최대 5건)

2. **미완결 문장 추출**
   - 문장이 중간에 끊긴 사례 인용 (최대 10건)
   - 각 사례가 STT 오류인지 실제 발화 끊김인지 판단하고 근거 기술
   - 전체 대비 미완결 문장 비율 추정 (%)

3. **존댓말/반말 일관성**
   - 존댓말 사용 사례 인용 3건
   - 반말 사용 사례 인용 3건
   - 전환이 일어나는 지점이 있다면 해당 타임스탬프 기록

## 출력 형식 (JSON)
{
  "category": "언어 표현 품질",
  "extraction": {
    "filler_analysis": {
      "counts": { "이제": N, "그래서": N, ... },
      "total_lines": N,
      "filler_ratio_pct": N,
      "worst_examples": ["인용1", ...]
    },
    "incomplete_sentences": {
      "examples": [
        { "quote": "...", "is_stt_error": true/false, "reason": "..." }
      ],
      "incomplete_ratio_pct": N
    },
    "speech_consistency": {
      "formal_examples": ["...", "...", "..."],
      "informal_examples": ["...", "...", "..."],
      "transition_points": ["HH:MM:SS", ...]
    }
  }
}
```

**Step 2: 평가 프롬프트**

```
[카테고리 1: 언어 표현 품질 — 평가]

아래는 강의 스크립트에서 추출한 사실 데이터입니다.
이 데이터와 아래 Rubric을 대조하여 각 항목의 점수를 산출하세요.

[추출 데이터]
{step1_output}

## Rubric 앵커 기준

### 불필요한 반복 표현 (가중치: 높음)
| 점수 | 기준 |
|---|---|
| 5 | 필러 비율 5% 미만, 한 문장 내 중복 사례 없음 |
| 4 | 필러 비율 5~10%, 한 문장 내 중복이 간헐적 (2건 이하) |
| 3 | 필러 비율 10~15%, 한 문장 내 중복 3~5건 |
| 2 | 필러 비율 15~25%, 한 문장 내 중복이 빈번 |
| 1 | 필러 비율 25% 이상, 강의 흐름을 심각하게 저해 |

### 발화 완결성 (가중치: 중간)
| 점수 | 기준 |
|---|---|
| 5 | 실제 미완결 문장(STT 오류 제외) 비율 5% 미만 |
| 4 | 실제 미완결 문장 비율 5~10% |
| 3 | 실제 미완결 문장 비율 10~20% |
| 2 | 실제 미완결 문장 비율 20~30% |
| 1 | 실제 미완결 문장 비율 30% 이상 |

### 언어 일관성 (가중치: 중간)
| 점수 | 기준 |
|---|---|
| 5 | 존댓말/반말이 전체에 걸쳐 완전히 일관됨 |
| 4 | 1~2회 전환이 있으나 의도적(예: 농담) |
| 3 | 3~5회 비의도적 전환 발생 |
| 2 | 빈번한 전환으로 일관성 부족 |
| 1 | 체계 없이 혼용됨 |

## 출력 형식 (JSON)
{
  "category": "언어 표현 품질",
  "items": [
    {
      "name": "불필요한 반복 표현",
      "weight": "높음",
      "measured_value": "필러 비율 12.3%",
      "rubric_match": "3점 구간 (10~15%)",
      "score": 3,
      "key_evidence": ["인용1", "인용2"],
      "analysis": "정량 근거 기반 분석",
      "improvement": "구체적 개선 제안"
    },
    ...
  ]
}
```

#### 예시 — 카테고리 2: 강의 도입 및 구조

**Step 1: 사실 추출 프롬프트**

```
[카테고리 2: 강의 도입 및 구조 — 사실 추출]

[강의 메타데이터]
- 과목: {subject} / 내용: {content} / 날짜: {date}

아래 강의 도입부(첫 10분)와 마무리(마지막 10분) 스크립트에서 추출하세요.

## 추출 항목

1. **학습 목표 관련 발화**: 시작 5분 이내에 학습 목표/순서를 안내한 발화를 인용
2. **전날 복습 관련 발화**: 이전 강의 내용을 언급한 발화를 인용
3. **설명 순서 패턴**: 개념→예시→실습 순서가 지켜진 구간 vs 아닌 구간 식별
4. **핵심 반복 강조 발화**: 중요 내용을 강조/반복한 발화 인용 (최대 5건)
5. **마무리 요약 발화**: 강의 마지막에 핵심 내용을 정리한 발화를 인용

각 항목에 대해 "해당 발화가 존재하는지(Y/N)"와 "인용"을 반환하세요.
```

**Step 2: 평가 프롬프트** — Step 1 결과 + Rubric 기준으로 점수 산출 (카테고리 1과 동일 패턴)

### 2-4. 종합 리포트 생성 프롬프트

```
당신은 교육 컨설팅 보고서 작성 전문가입니다.
아래 5개 카테고리별 분석 결과를 종합하여, 비개발자도 이해 가능한 
강의 품질 리포트를 작성하세요.

[종합 리포트 구성]
1. 요약 (Executive Summary): 핵심 강점 3가지, 주요 개선 포인트 3가지
2. 카테고리별 상세 분석: 점수, 정량 근거, 개선 방향
3. 시계열 트렌드 (제공된 경우): 주차별 변화 추이
4. 종합 점수: 가중 평균 기반 총점 (/95점) 및 5점 환산
5. 맞춤형 개선 코칭: 실질적이고 단계적인 개선 로드맵
```

---

## 3. 평가 항목 구조화 — 스코어링 체계

### 3-1. 평가 스키마 정의

```json
{
  "evaluation_schema": {
    "scale": { "min": 1, "max": 5 },
    "labels": {
      "5": "매우 우수 — 해당 항목이 체계적으로 잘 수행됨",
      "4": "우수 — 대체로 잘 수행되나 소소한 개선 여지 있음",
      "3": "보통 — 기본은 충족하나 개선이 필요한 부분 있음",
      "2": "미흡 — 해당 항목이 부족하여 개선 필요",
      "1": "매우 미흡 — 해당 항목이 거의 수행되지 않음"
    },
    "special": {
      "N/A": "스크립트에서 해당 항목을 판단할 근거가 없음"
    }
  }
}
```

### 3-2. 가중치 체계

| 가중치 등급 | 배수 | 해당 항목 수 | 항목 목록 |
|---|---|---|---|
| 높음 (핵심) | ×3 | 10개 | 불필요한 반복 표현, 학습 목표 안내, 전날 복습 연계, 개념 정의, 비유/예시 활용, 예시 적절성, 실습 연계, 이해 확인 질문, 참여 유도, 질문 응답 충분성 |
| 중간 (일반) | ×2 | 7개 | 발화 완결성, 언어 일관성, 설명 순서, 핵심 내용 강조, 선행 개념 확인, 발화 속도 적절성, 오류 대응 |
| 낮음 (참고) | ×1 | 1개 | 마무리 요약 |

> **가중 총점 계산**: `Σ(항목 점수 × 가중치)` / `Σ(5 × 가중치)` × 100 = 가중 백분율
>
> 참고: PDF 체크리스트 원문에는 총점이 /95점으로 표기되어 있으나, 18개 항목 × 5점 = 90점이 정확함.
> 가중치 적용 시 만점은 `(10×5×3) + (7×5×2) + (1×5×1) = 150 + 70 + 5 = 225점`이며,
> 가중 평균은 이를 5점 척도로 환산하여 사용.

### 3-3. 항목별 평가 세부 정의

각 항목에 대해 LLM이 일관되게 평가할 수 있도록, **1~5점 각각에 대한 앵커 기준(Rubric)**을 정의:

#### 예시: 불필요한 반복 표현

| 점수 | 앵커 기준 |
|---|---|
| 5 | 필러 포함 비율 5% 미만, 한 문장 내 중복 사례 없음 |
| 4 | 필러 포함 비율 5~10%, 한 문장 내 중복이 간헐적 (2건 이하) |
| 3 | 필러 포함 비율 10~15%, 한 문장 내 중복 3~5건 |
| 2 | 필러 포함 비율 15~25%, 한 문장 내 중복이 빈번 |
| 1 | 필러 포함 비율 25% 이상, 강의 흐름을 심각하게 저해 |

#### 예시: 학습 목표 안내

| 점수 | 앵커 기준 |
|---|---|
| 5 | 강의 시작 5분 이내 학습 목표와 진행 순서를 명확히 제시 |
| 4 | 학습 목표를 언급하나 진행 순서가 다소 불명확 |
| 3 | 오늘 할 내용을 간단히 언급하는 수준 |
| 2 | 전날 내용과 연결 없이 바로 본론으로 진입 |
| 1 | 목표/계획 언급 없이 바로 수업 시작 |

> 나머지 16개 항목도 동일한 형식으로 Rubric을 정의하여 `evaluation_rubrics.json`에 저장

### 3-4. 결과 데이터 구조

```json
{
  "lecture_id": "2026-02-02_morning",
  "date": "2026-02-02",
  "session": "오전",
  "subject": "객체지향 프로그래밍",
  "instructor": "김영아",
  "categories": [
    {
      "id": 1,
      "name": "언어 표현 품질",
      "items": [
        {
          "id": "1-1",
          "name": "불필요한 반복 표현",
          "weight": "높음",
          "weight_multiplier": 3,
          "measured_value": "필러 포함 비율 12.3%",
          "rubric_match": "3점 구간 (10~15%)",
          "score": 3,
          "self_consistency": [3, 3, 3],
          "key_evidence": ["<09:18:10> 이제 저희가 이제 내용이 하다 보니까 이제..."],
          "analysis": "'이제'가 한 문장에 3회 반복, 필러 포함 비율 12.3%로 Rubric 3점 구간 해당",
          "improvement": "연결 표현을 다양화하면 청취 경험 개선"
        }
      ],
      "category_avg": 3.33
    }
  ],
  "total_weighted_score": 170,
  "total_weighted_max": 225,
  "weighted_percentage": 75.6,
  "weighted_average_5pt": 3.78
}
```

---

## 4. 전체 파이프라인 구성

### 4-1. 파이프라인 아키텍처

```
┌──────────────────────────────────────────────────────────────┐
│                    DATA INGESTION LAYER                       │
│                                                              │
│  [TXT Files] ──┐                                             │
│  [CSV Meta]  ──┼── DataLoader ── Parser ── Preprocessor      │
│  [Rubrics]   ──┘  (evaluation_rubrics.json)                  │
└──────────────────────┬───────────────────────────────────────┘

※ PDF 체크리스트는 설계 단계에서 Rubric/프롬프트를 정의하는 참고 자료이며,
  런타임에는 그 기준이 evaluation_rubrics.json과 프롬프트 템플릿에 내재화됨.

                       ▼
┌──────────────────────────────────────────────────────────────┐
│                   ANALYSIS ENGINE LAYER                       │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐     │
│  │ Category Analyzer (×5)                              │     │
│  │  ├── Step 1: Fact Extractor (사실 추출)              │     │
│  │  ├── Step 2: Rubric Evaluator (Rubric 평가)         │     │
│  │  ├── Self-Consistency Voter (3회 다수결)             │     │
│  │  └── Response Parser (JSON validation)              │     │
│  └─────────────────────────────────────────────────────┘     │
│                        │                                     │
│                  Aggregator                                   │
│            (가중 스코어 계산, 종합)                              │
└──────────────────────┬───────────────────────────────────────┘
                       ▼
┌──────────────────────────────────────────────────────────────┐
│                   REPORT GENERATION LAYER                     │
│                                                              │
│  ├── Summary Generator (LLM)                                 │
│  ├── Chart/Visualization Builder (matplotlib/plotly)          │
│  ├── Trend Analyzer (주차별/일별 추이)                          │
│  └── Export Engine (PDF / DOCX / Dashboard)                   │
└──────────────────────────────────────────────────────────────┘
```

### 4-2. 모듈별 상세 설계

#### Module 1: `data_loader.py`
- `load_transcript(filepath)` → 타임스탬프+화자+텍스트 파싱
- `load_metadata(csv_path)` → pandas DataFrame 반환
- `load_rubrics(json_path)` → 평가 Rubric 로드
- `merge_data(transcript, metadata)` → 세션 별 구조화된 데이터 생성

#### Module 2: `preprocessor.py`
- `identify_instructor(transcript)` → 발화량 기반 강사 식별
- `segment_lecture(transcript, metadata)` → 도입/본론/마무리 분할
- `clean_text(text)` → 최소한의 텍스트 정제 (중복 제거만)
- `chunk_for_llm(segments, max_tokens)` → LLM 입력 크기 분할

#### Module 3: `prompt_engine.py`
- `build_system_prompt()` → 공통 시스템 프롬프트 (STT 특성 안내 포함)
- `build_extraction_prompt(category_id, segments, metadata)` → Step 1: 사실 추출 프롬프트
- `build_evaluation_prompt(category_id, extraction_result, rubrics)` → Step 2: Rubric 평가 프롬프트
- `build_summary_prompt(all_results)` → 종합 리포트 프롬프트
- 프롬프트 템플릿은 별도 `prompts/` 디렉토리에 텍스트 파일로 버전 관리

#### Module 4: `analyzer.py`
- `extract_facts(session_data, category_id)` → Step 1: 사실 추출 (1회)
- `evaluate_with_rubric(extraction_result, category_id)` → Step 2: Rubric 평가 (3회 반복)
- `vote_consistency(scores_list)` → Self-Consistency 다수결 투표
- `analyze_session(session_data)` → 5개 카테고리 병렬 분석 (Step 1 → Step 2 × 3)
- `analyze_batch(all_sessions)` → 전체 15일분 배치 분석
- LLM 호출 시 **JSON mode** 또는 **Structured Output** 활용으로 파싱 안정성 확보
- 재시도 로직 (rate limit, timeout, JSON 파싱 실패 시)

#### Module 5: `scorer.py`
- `calculate_weighted_score(results)` → 가중 점수 계산
- `compare_sessions(results_list)` → 세션 간 비교 분석
- `calculate_trends(results_by_date)` → 주차별 트렌드 계산

#### Module 6: `report_generator.py`
- `generate_summary(aggregated_results)` → LLM 기반 종합 요약 생성
- `create_visualizations(scores)` → 레이더 차트, 시계열 그래프 등
- `export_pdf(report_data)` → PDF 리포트 출력
- `export_docx(report_data)` → DOCX 리포트 출력

#### Module 7: `dashboard.py` (Streamlit)
- 날짜/세션 선택 UI
- 카테고리별 점수 레이더 차트
- 항목별 상세 분석 드릴다운
- 주차별 트렌드 그래프
- 강사별 비교 (데이터가 1명이므로 시간 축 비교)

### 4-3. 실행 흐름

```python
# main.py — 단일 강의 분석 예시
from data_loader import load_transcript, load_metadata, merge_data
from preprocessor import identify_instructor, segment_lecture
from analyzer import analyze_session
from scorer import calculate_weighted_score
from report_generator import generate_summary, export_pdf

# Step 1: 데이터 로드
transcript = load_transcript("강의 스크립트/2026-02-02_kdt-backendj-21th.txt")
metadata = load_metadata("강의 메타데이터.csv")

# Step 2: 전처리
instructor_id = identify_instructor(transcript)
session_data = merge_data(transcript, metadata, date="2026-02-02")
segments = segment_lecture(session_data, instructor_id)

# Step 3: 분석 (5개 카테고리 병렬)
results = analyze_session(segments)

# Step 4: 스코어링
scores = calculate_weighted_score(results)

# Step 5: 리포트 생성
summary = generate_summary(results, scores)
export_pdf(summary, filename="report_2026-02-02.pdf")
```

### 4-4. 기술 스택 정리

| 구분 | 선택 | 이유 |
|---|---|---|
| LLM | OpenAI GPT-4o | JSON mode 지원, 한국어 성능 우수, 128k 컨텍스트 |
| 프레임워크 | LangChain | 프롬프트 템플릿 관리, 체이닝, 구조화 출력 파싱 |
| 데이터 처리 | pandas + re | CSV 처리, 정규식 기반 텍스트 파싱 |
| 한국어 NLP | KoNLPy (선택) | 필러 표현 빈도 분석 등 보조 분석 시 활용 |
| 시각화 | plotly + matplotlib | 인터랙티브 차트 (대시보드), 정적 차트 (PDF) |
| 대시보드 | Streamlit | 빠른 프로토타이핑, 간편한 배포 |
| 문서 생성 | python-docx + ReportLab | DOCX/PDF 출력 |

### 4-5. 주요 고려사항 & 리스크

| 리스크 | 대응 방안 |
|---|---|
| STT 변환 품질 이슈 (오탈자, 누락) | 프롬프트에 STT 특성 명시, LLM이 맥락 추론하도록 유도 |
| LLM 평가 일관성 부족 | 2-Step 분리 + 정량적 Rubric + Self-Consistency 3회 투표 |
| 화자 식별 오류 | 발화량 기반 + 발화 내용 키워드("여러분", "수업") 이중 검증 |
| 비용 (API 호출) | 세션당 약 20회 (Step1 ×5 + Step2 ×5 ×3) × 30세션 = 600회 → 비용 절감 전략 병행 |
| "상호작용" 항목 평가 한계 (수강생 발화 부족) | 강사 발화 내 질문 패턴("되셨어요?", "이해하셨나요?")으로 간접 평가 |
