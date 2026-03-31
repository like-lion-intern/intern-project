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
from prompts import get_report_synthesis_prompt


def _save_json(data: dict, path: str) -> None:
    """JSON 파일 저장 유틸리티. ensure_ascii=False, indent=2 고정."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _to_frontend_report(date: str, scoring_output: Dict[str, Any]) -> Dict[str, Any]:
    """
    run_scoring 출력(간소 포맷)을 프론트엔드가 기대하는 final_report 포맷으로 변환한다.
    """
    categories_in = scoring_output.get("category_results", []) or []
    weak_categories = (scoring_output.get("lecture_summary", {}) or {}).get("overall_weak_categories", []) or []
    expected_category_items = {
        "언어 표현 품질": ["불필요한 반복 표현", "발화 완결성", "언어 일관성"],
        "강의 도입 및 구조": ["학습 목표 안내", "전날 복습 연계", "설명 순서", "핵심 내용 강조", "마무리 요약"],
        "개념 설명 명확성": ["개념 정의", "비유 및 예시 활용", "선행 개념 확인", "발화 속도 적절성"],
        "예시 및 실습 연계": ["예시 적절성", "실습 연계", "오류 대응"],
        "수강생 상호작용": ["이해 확인 질문", "참여 유도", "질문 응답 충분성"],
    }
    item_alias = {
        "질문 응답 충분": "질문 응답 충분성",
    }

    category_results = []
    for cat in categories_in:
        top_items = cat.get("top_items", []) or []
        normalized_map: Dict[str, Dict[str, Any]] = {}
        for raw_item in top_items:
            raw_name = raw_item.get("item_name", "")
            item_name = item_alias.get(raw_name, raw_name)
            if not item_name:
                continue
            reason = (raw_item.get("reason") or "").strip()
            if not reason:
                reason = f"{item_name} 항목의 근거가 제한적이어서 추가 확인이 필요합니다."
            normalized_map[item_name] = {
                "item_name": item_name,
                "heuristic_score": float(raw_item.get("heuristic_score", 3.0)),
                "final_score": float(raw_item.get("final_score", raw_item.get("heuristic_score", 3.0))),
                "reason": reason,
                "adjustment_reason": "",
                "selected_evidence": raw_item.get("selected_evidence") or [],
                "improvement_tip": f"{item_name}의 수행 근거를 더 명확히 드러내도록 발화 구조를 보강해 주세요.",
            }

        expected_items = expected_category_items.get(cat.get("category_name", ""), [])
        for missing_name in expected_items:
            if missing_name not in normalized_map:
                normalized_map[missing_name] = {
                    "item_name": missing_name,
                    "heuristic_score": 3.0,
                    "final_score": 3.0,
                    "reason": f"{missing_name} 항목 분석 데이터가 부족하여 기본값으로 채워졌습니다.",
                    "adjustment_reason": "",
                    "selected_evidence": [],
                    "improvement_tip": f"{missing_name} 관련 발화를 명시적으로 추가해 주세요.",
                }

        if expected_items:
            items = [normalized_map[name] for name in expected_items]
        else:
            items = list(normalized_map.values())

        cat_score = float(cat.get("final_score", cat.get("heuristic_score", 3.0)))
        strengths = [f"{cat.get('category_name', '해당 카테고리')} 수행이 비교적 안정적임"] if cat_score >= 3.8 else []
        weaknesses = [f"{cat.get('category_name', '해당 카테고리')} 개선이 필요함"] if cat_score < 3.2 else []
        improvements = [f"{cat.get('category_name', '해당 카테고리')}의 취약 항목 중심으로 보강"] if cat_score < 3.2 else []

        category_results.append(
            {
                "category_name": cat.get("category_name", ""),
                "heuristic_score": float(cat.get("heuristic_score", 3.0)),
                "final_score": cat_score,
                "category_summary": (cat.get("reason") or "").strip() or f"{cat.get('category_name', '해당 카테고리')} 종합 평가",
                "strengths": strengths,
                "weaknesses": weaknesses,
                "improvements": improvements,
                "items": items,
            }
        )

    # 누락 카테고리도 기본값으로 채운다.
    existing_cat_names = {c.get("category_name", "") for c in category_results}
    for cname, expected_items in expected_category_items.items():
        if cname in existing_cat_names:
            continue
        category_results.append(
            {
                "category_name": cname,
                "heuristic_score": 3.0,
                "final_score": 3.0,
                "category_summary": f"{cname} 분석 데이터가 부족하여 기본 카테고리 리포트를 생성했습니다.",
                "strengths": [],
                "weaknesses": [f"{cname} 데이터 부족"],
                "improvements": [f"{cname} 근거 데이터를 보강해 주세요."],
                "items": [
                    {
                        "item_name": name,
                        "heuristic_score": 3.0,
                        "final_score": 3.0,
                        "reason": f"{name} 항목 분석 데이터가 부족하여 기본값으로 채워졌습니다.",
                        "adjustment_reason": "",
                        "selected_evidence": [],
                        "improvement_tip": f"{name} 관련 발화를 명시적으로 추가해 주세요.",
                    }
                    for name in expected_items
                ],
            }
        )

    overall_strengths = []
    overall_weaknesses = []
    for cat in category_results:
        if float(cat.get("final_score", 0.0)) >= 3.8:
            overall_strengths.append(f"{cat.get('category_name', '')} 카테고리 수행이 안정적임")
        if float(cat.get("final_score", 0.0)) < 3.2:
            overall_weaknesses.append(f"{cat.get('category_name', '')} 카테고리 보강 필요")

    priority_improvements = (
        [f"{name} 중심 개선 우선" for name in weak_categories]
        if weak_categories
        else (overall_weaknesses[:5] or ["취약 항목 중심으로 근거 기반 발화 구조를 보강하세요."])
    )

    if not category_results:
        overall_summary = "분석 결과가 비어 있어 기본 리포트를 생성했습니다."
    else:
        avg_score = sum(float(c.get("final_score", 0.0)) for c in category_results) / len(category_results)
        overall_summary = f"강의 종합 점수는 {avg_score:.2f}/5.0이며, 취약 카테고리 중심 개선이 필요합니다."

    return {
        "lecture_id": date,
        "overall_summary": overall_summary,
        "overall_strengths": overall_strengths[:5] or ["일부 카테고리에서 기본 수행이 확인됩니다."],
        "overall_weaknesses": overall_weaknesses[:5] or ["카테고리별 세부 항목 편차를 점검해 보세요."],
        "priority_improvements": priority_improvements[:5],
        "category_results": category_results,
    }


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
    frontend_final_report = _to_frontend_report(date, final_output)

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
    synthesis_prompt_path = os.path.join(output_dir, "report_synthesis_prompt.txt")

    _save_json(heuristic_report, heuristic_path)
    _save_json(frontend_final_report, final_path)
    _save_json(llm_debug, llm_debug_path)
    with open(synthesis_prompt_path, "w", encoding="utf-8") as f:
        f.write(
            get_report_synthesis_prompt(
                json.dumps(frontend_final_report, ensure_ascii=False, indent=2)
            )
        )

    # 디버그/호환용 추가 파일
    if debug:
        _save_json(analysis_result, os.path.join(output_dir, "debug_analysis.json"))
        _save_json(evidence_by_item, os.path.join(output_dir, "debug_evidence.json"))

    return {
        "heuristic_report_path": heuristic_path,
        "final_report_path": final_path,
        "llm_debug_path": llm_debug_path,
        "report_synthesis_prompt_path": synthesis_prompt_path,
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
