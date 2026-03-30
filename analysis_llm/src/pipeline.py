from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Dict, Any

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


def run_pipeline(
    date: str,
    base_path: str = ".",
    output_dir: str | None = None,
    debug: bool = False,
) -> Dict[str, str]:
    """
    Stage2 파이프라인 실행.

    src/runner.py가 기대하는 반환 형식과 파일명을 유지한다.
    반환:
      {
        "heuristic_report_path": ".../heuristic_report.json",
        "final_report_path": ".../final_report.json",
        "llm_debug_path": ".../llm_debug.json",
      }
    """
    output_dir = os.path.abspath(output_dir or os.path.join("outputs", date))
    os.makedirs(output_dir, exist_ok=True)

    # STEP 1: 데이터 로드
    features_data, chunks_data = load_data(date, base_path)
    chunks = chunks_data.get("chunks", [])

    # STEP 1-1: 커리큘럼 메타데이터 로드
    curriculum = load_curriculum(date, base_path)

    # STEP 2: 시그널 계산
    signals_output = calculate_signals(features_data, chunks_data)

    # STEP 3: Evidence 추출
    evidence_by_item = {}
    for item_name in ITEM_EVIDENCE_KEYS.keys():
        evidence_by_item[item_name] = extract_evidence(item_name, chunks, signals_output)

    # STEP 4: LLM 분석
    analysis_result = run_analysis(features_data, signals_output, evidence_by_item)

    # STEP 5: 스코어링
    final_output = run_scoring(features_data, signals_output, analysis_result, chunks)

    # STEP 6: 커리큘럼 일치도 분석
    curriculum_match = analyze_curriculum_match(curriculum, signals_output)
    final_output.setdefault("lecture_summary", {})["curriculum_match"] = {
        "planned_contents": curriculum["contents"] if curriculum else [],
        "score": curriculum_match.get("score"),
        "reason": curriculum_match.get("reason"),
    }

    # runner 호환 파일
    heuristic_report = {
        "lecture_id": date,
        "lecture_signals": signals_output.get("lecture_signals", {}),
        "item_results": analysis_result.get("item_results", []),
        "validator_debug": signals_output.get("validator_debug", {}),
    }
    llm_debug = {
        "success": True,
        "item_result_count": len(analysis_result.get("item_results", [])),
        "curriculum_match": final_output.get("lecture_summary", {}).get("curriculum_match", {}),
    }

    heuristic_path = os.path.join(output_dir, "heuristic_report.json")
    final_path = os.path.join(output_dir, "final_report.json")
    llm_debug_path = os.path.join(output_dir, "llm_debug.json")

    _save_json(heuristic_report, heuristic_path)
    _save_json(final_output, final_path)
    _save_json(llm_debug, llm_debug_path)

    # 디버그/호환용 추가 파일
    if debug:
        _save_json(analysis_result, os.path.join(output_dir, "debug_analysis.json"))
        _save_json(evidence_by_item, os.path.join(output_dir, "debug_evidence.json"))

    return {
        "heuristic_report_path": heuristic_path,
        "final_report_path": final_path,
        "llm_debug_path": llm_debug_path,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="강의 품질 진단 파이프라인")
    parser.add_argument("--date", required=True, help="처리할 강의 날짜 (YYYY-MM-DD)")
    parser.add_argument("--base-path", default=".", help="features/, semantic_chunks/ 루트 경로")
    parser.add_argument("--output-path", default="../output/", help="결과 JSON 저장 경로")
    parser.add_argument("--debug", action="store_true", help="디버그 산출물 저장")
    args = parser.parse_args()

    try:
        result = run_pipeline(
            date=args.date,
            base_path=args.base_path,
            output_dir=args.output_path,
            debug=args.debug,
        )
    except FileNotFoundError as e:
        print(f"[오류] 데이터 파일을 찾을 수 없습니다: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"[오류] 파이프라인 실행 실패: {e}")
        sys.exit(1)

    print("[완료] 출력 파일")
    print(f"  - heuristic: {result['heuristic_report_path']}")
    print(f"  - final    : {result['final_report_path']}")
    print(f"  - llm_debug: {result['llm_debug_path']}")


if __name__ == "__main__":
    main()
