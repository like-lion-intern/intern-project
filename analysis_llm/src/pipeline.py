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
    """JSON 파일 저장 유틸리티. ensure_ascii=False, indent=2 고정."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser(description="강의 품질 진단 파이프라인")
    parser.add_argument("--date", required=True, help="처리할 강의 날짜 (YYYY-MM-DD)")
    parser.add_argument("--base-path", default="..", help="features/, semantic_chunks/ 루트 경로")
    parser.add_argument("--output-path", default="../output/", help="결과 JSON 저장 경로")
    args = parser.parse_args()

    os.makedirs(args.output_path, exist_ok=True)

    # STEP 1: 데이터 로드
    try:
        print(f"[STEP 1] 데이터 로드: {args.date}")
        features_data, chunks_data = load_data(args.date, args.base_path)
        chunks = chunks_data.get("chunks", [])
    except FileNotFoundError as e:
        print(f"[오류] 데이터 파일을 찾을 수 없습니다: {e}")
        sys.exit(1)

    # STEP 1-1: 커리큘럼 메타데이터 로드
    curriculum = load_curriculum(args.date, args.base_path)
    if curriculum:
        print(f"  → 커리큘럼: {curriculum['subject']} / {', '.join(curriculum['contents'])}")
    else:
        print(f"  → 커리큘럼 정보 없음 (강의_메타데이터.csv에서 {args.date} 미발견)")

    # STEP 2: 시그널 계산
    print(f"[STEP 2] 시그널 계산")
    signals_output = calculate_signals(features_data, chunks_data)
    validator_debug = signals_output.get("validator_debug", {})

    validator_debug_file = os.path.join(args.output_path, f"{args.date}_validator_debug.json")
    _save_json(validator_debug, validator_debug_file)
    print(f"  → validator debug 저장: {validator_debug_file}")

    # STEP 3: Evidence 추출 → {date}_evidence.json 저장
    print(f"[STEP 3] Evidence 추출")
    evidence_by_item = {}
    for item_name in ITEM_EVIDENCE_KEYS.keys():
        evidence_by_item[item_name] = extract_evidence(item_name, chunks, signals_output)

    evidence_file = os.path.join(args.output_path, f"{args.date}_evidence.json")
    _save_json(evidence_by_item, evidence_file)
    print(f"  → 저장: {evidence_file}")

    # STEP 4: LLM 분석 → {date}_analysis.json 저장
    print(f"[STEP 4] LLM 분석")
    analysis_result = run_analysis(features_data, signals_output, evidence_by_item)

    analysis_file = os.path.join(args.output_path, f"{args.date}_analysis.json")
    _save_json(analysis_result, analysis_file)
    print(f"  → 저장: {analysis_file}")

    # STEP 5: 스코어링 → {date}_result.json 저장
    print(f"[STEP 5] 스코어링")
    final_output = run_scoring(features_data, signals_output, analysis_result, chunks)

    # STEP 6: 커리큘럼 일치도 분석 → lecture_summary에 추가
    print(f"[STEP 6] 커리큘럼 일치도 분석")
    curriculum_match = analyze_curriculum_match(curriculum, signals_output)
    score_str = f"{curriculum_match['score']}점" if curriculum_match["score"] is not None else "분석불가"
    print(f"  → 커리큘럼 일치도: {score_str}")

    final_output["lecture_summary"]["curriculum_match"] = {
        "planned_contents": curriculum["contents"] if curriculum else [],
        "score": curriculum_match["score"],
        "reason": curriculum_match["reason"],
    }

    result_file = os.path.join(args.output_path, f"{args.date}_result.json")
    _save_json(final_output, result_file)
    print(f"  → 저장: {result_file}")

    print(f"\n[완료] 출력 파일 4개:")
    print(f"  1. {validator_debug_file}  ← validator 디버그 결과")
    print(f"  2. {evidence_file}         ← evidence 추출 결과")
    print(f"  3. {analysis_file}         ← LLM 분석 결과")
    print(f"  4. {result_file}           ← 최종 scoring 결과")


if __name__ == "__main__":
    main()

