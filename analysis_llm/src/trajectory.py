from __future__ import annotations

import csv
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()

try:
    from google import genai
    from google.genai import types
except Exception:
    genai = None
    types = None


TRAJECTORY_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
SYSTEM_PROMPT = """당신은 강의 품질 분석 전문가입니다.
주어진 전체 강의 날짜별 분석 데이터를 바탕으로 강사의 강의 궤적을 분석합니다.
반드시 한국어만 사용하십시오.
반드시 JSON 객체만 반환하십시오. 마크다운, 코드블록, 설명문을 포함하지 마십시오."""

ANALYSIS_GUIDELINES = """위 데이터를 바탕으로 아래 4가지를 분석하십시오.
[분석 1] 강사 취약 패턴: weak 반복 항목 중심(최대 5개)
[분석 2] 성장/퇴보 추이: 카테고리별 변화
[분석 3] 커리큘럼 일치도 추이: 저점 날짜(최대 3개)
[분석 4] subject 전환 시 변화: 전환 최대 2개
반드시 JSON으로만 답하십시오."""


def _safe_parse_json_object(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```json\s*", "", text)
        text = re.sub(r"^```\s*", "", text)
        text = re.sub(r"\s*```$", "", text).strip()
    try:
        return json.loads(text)
    except Exception:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start != -1:
        candidate = text[start : end + 1] if (end != -1 and end > start) else (text[start:] + "}")
        try:
            return json.loads(candidate)
        except Exception:
            if candidate.count('"') % 2 != 0:
                candidate = text[start:] + '"}'
                return json.loads(candidate)
    raise ValueError("trajectory json parse failed")


def collect_dates(output_root: Path) -> list[str]:
    dates = []
    pattern = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    if not output_root.exists():
        return dates
    for entry in output_root.iterdir():
        if not entry.is_dir() or not pattern.match(entry.name):
            continue
        if (entry / "final_report.json").exists():
            dates.append(entry.name)
    return sorted(dates)


def load_metadata_by_date(project_root: Path) -> dict[str, dict[str, Any]]:
    candidates = [
        project_root / "project-data" / "강의 메타데이터.csv",
        project_root / "강의 스크립트" / "강의 메타데이터.csv",
        project_root / "강의 메타데이터.csv",
    ]
    csv_path = next((p for p in candidates if p.exists()), None)
    if not csv_path:
        return {}

    result: dict[str, dict[str, Any]] = {}
    with csv_path.open(encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            date = (row.get("date") or "").strip()
            if not date:
                continue
            subject = (row.get("subject") or "").strip()
            content = (row.get("content") or "").strip()
            if date not in result:
                result[date] = {"subject": subject, "contents": []}
            if content and content not in result[date]["contents"]:
                result[date]["contents"].append(content)
    return result


def compress_lecture(date: str, output_root: Path) -> dict[str, Any] | None:
    date_dir = output_root / date
    final_path = date_dir / "final_report.json"
    heuristic_path = date_dir / "heuristic_report.json"
    llm_debug_path = date_dir / "llm_debug.json"
    if not final_path.exists() or not heuristic_path.exists():
        return None

    final_report = json.loads(final_path.read_text(encoding="utf-8"))
    heuristic_report = json.loads(heuristic_path.read_text(encoding="utf-8"))
    llm_debug = json.loads(llm_debug_path.read_text(encoding="utf-8")) if llm_debug_path.exists() else {}

    category_scores = {
        cat.get("category_name", ""): cat.get("final_score", cat.get("heuristic_score", 3.0))
        for cat in final_report.get("category_results", [])
        if cat.get("category_name")
    }

    curriculum_match = llm_debug.get("curriculum_match", {}) if isinstance(llm_debug, dict) else {}
    curriculum_match_score = curriculum_match.get("score")
    curriculum_match_reason = (curriculum_match.get("reason") or "")[:30]

    item_results = {}
    for item in heuristic_report.get("item_results", []) or []:
        item_name = item.get("item_name")
        if not item_name:
            continue
        item_results[item_name] = {
            "label": item.get("label", "neutral"),
            "confidence": item.get("confidence", 0.5),
        }

    return {
        "date": date,
        "subject": None,
        "contents": [],
        "curriculum_match_score": curriculum_match_score,
        "curriculum_match_reason": curriculum_match_reason,
        "category_scores": category_scores,
        "item_results": item_results,
    }


def _fallback_trajectory(lectures: list[dict[str, Any]]) -> dict[str, Any]:
    start_date = lectures[0]["date"]
    end_date = lectures[-1]["date"]

    weak_counter: dict[str, list[float]] = {}
    scores: dict[str, list[float]] = {}
    curriculum_scores = []

    for lec in lectures:
        for k, v in (lec.get("category_scores") or {}).items():
            scores.setdefault(k, []).append(float(v))
        s = lec.get("curriculum_match_score")
        if isinstance(s, (int, float)):
            curriculum_scores.append(float(s))
        for item_name, info in (lec.get("item_results") or {}).items():
            if info.get("label") == "weak":
                weak_counter.setdefault(item_name, []).append(float(info.get("confidence", 0.5)))

    weak_patterns = []
    total_count = len(lectures)
    for item_name, confs in sorted(weak_counter.items(), key=lambda kv: (-len(kv[1]), -sum(kv[1]) / len(kv[1]))):
        weak_patterns.append(
            {
                "item_name": item_name,
                "weak_count": len(confs),
                "total_count": total_count,
                "avg_confidence": round(sum(confs) / len(confs), 3),
                "pattern_description": "여러 날짜에서 반복적으로 weak로 관찰되었습니다.",
            }
        )
        if len(weak_patterns) >= 5:
            break

    growth_trends = []
    for category_name, vals in scores.items():
        first, last = vals[0], vals[-1]
        if last - first > 0.3:
            trend = "improving"
        elif first - last > 0.3:
            trend = "declining"
        elif max(vals) - min(vals) > 0.8:
            trend = "fluctuating"
        else:
            trend = "stable"
        growth_trends.append(
            {
                "category_name": category_name,
                "trend": trend,
                "score_range": [round(min(vals), 2), round(max(vals), 2)],
                "notable_changes": "날짜별 점수 변동을 바탕으로 추이를 요약했습니다.",
            }
        )

    avg_score = round(sum(curriculum_scores) / len(curriculum_scores), 2) if curriculum_scores else 0.0
    low_score_dates = []
    for lec in lectures:
        s = lec.get("curriculum_match_score")
        if isinstance(s, (int, float)) and s < 50:
            low_score_dates.append(
                {
                    "date": lec["date"],
                    "score": int(s),
                    "reason": (lec.get("curriculum_match_reason") or "일치도 낮음")[:80],
                }
            )
            if len(low_score_dates) >= 3:
                break

    return {
        "analysis_period": {
            "start_date": start_date,
            "end_date": end_date,
            "total_lectures": len(lectures),
        },
        "weak_patterns": weak_patterns,
        "growth_trends": growth_trends,
        "curriculum_alignment": {
            "avg_score": avg_score,
            "low_score_dates": low_score_dates,
            "overall_pattern": "날짜별 일치도와 카테고리 점수 변화를 종합했습니다.",
        },
        "subject_transitions": [],
    }


def run_trajectory_analysis(lectures: list[dict[str, Any]]) -> dict[str, Any]:
    if not lectures:
        raise ValueError("no lectures")
    if genai is None:
        return _fallback_trajectory(lectures)

    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return _fallback_trajectory(lectures)

    client = genai.Client(api_key=api_key)
    prompt = (
        f"[블록 1 — 전체 강의 날짜별 압축 데이터]\n{json.dumps(lectures, ensure_ascii=False, indent=2)}\n\n"
        f"[블록 2 — 분석 지침]\n{ANALYSIS_GUIDELINES}\n"
    )

    response = client.models.generate_content(
        model=TRAJECTORY_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            temperature=0.1,
            max_output_tokens=8192,
            response_mime_type="application/json",
        ),
    )
    return _safe_parse_json_object(response.text)


def build_trajectory_report(output_root: str, project_root: str) -> str | None:
    output_root_path = Path(output_root)
    project_root_path = Path(project_root)

    dates = collect_dates(output_root_path)
    if not dates:
        return None

    metadata = load_metadata_by_date(project_root_path)
    lectures = []
    for date in dates:
        compressed = compress_lecture(date, output_root_path)
        if compressed is None:
            continue
        meta = metadata.get(date, {})
        compressed["subject"] = meta.get("subject")
        contents = meta.get("contents", [])
        compressed["contents"] = [contents[0]] if contents else []
        lectures.append(compressed)

    if not lectures:
        return None

    result = run_trajectory_analysis(lectures)
    result.setdefault("generated_at", datetime.utcnow().isoformat() + "Z")

    trajectory_dir = output_root_path / "trajectory"
    trajectory_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{lectures[0]['date']}_{lectures[-1]['date']}_trajectory.json"
    out_path = trajectory_dir / filename
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(out_path)
