import os
import glob
import json
import argparse
import requests  # SDK 대신 requests 사용
from dotenv import load_dotenv
from prompts import get_report_synthesis_prompt

load_dotenv()

# ──────────────────────────────────────────────
# 등급 시스템 (A+ ~ F)
# ──────────────────────────────────────────────
GRADE_TABLE = [
    # (하한, 상한, 등급, 라벨, 이모지, 한줄 총평)
    (4.5, 5.01, "A+", "탁월",      "🏆", "전체적으로 '매우 우수'한 수준의 강의 품질입니다. 현재 수준을 유지하시길 권장합니다."),
    (4.0, 4.5,  "A",  "우수",      "🟢", "전체적으로 '우수'한 수준의 강의 품질입니다. 소수 항목만 보완하면 최상위 등급 달성이 가능합니다."),
    (3.5, 4.0,  "B+", "양호",      "🟢", "전체적으로 '양호'한 수준의 강의 품질입니다. 주요 항목을 보강하면 우수 등급 진입이 가능합니다."),
    (3.0, 3.5,  "B",  "보통",      "🟡", "전체적으로 '보통' 수준의 강의 품질입니다. 핵심 영역의 개선이 권장됩니다."),
    (2.5, 3.0,  "C",  "보통 이하", "🟡", "전체적으로 '보통 이하' 수준으로, 일부 핵심 영역의 집중 개선이 필요합니다."),
    (2.0, 2.5,  "D",  "개선 필요", "🟠", "전체적으로 '개선이 필요'한 수준입니다. 취약 카테고리에 대한 집중 개선 계획 수립을 권장합니다."),
    (0.0, 2.0,  "F",  "시급한 개선","🔴", "전체적으로 '시급한 개선'이 필요한 수준입니다. 즉각적인 교수법 컨설팅을 권장합니다."),
]

# ──────────────────────────────────────────────
# 세부 항목 4단계 라벨링
# ──────────────────────────────────────────────
ITEM_LABEL_TABLE = [
    # (하한, 상한, 라벨, 이모지)
    (4.0, 5.01, "우수",      "🟢"),
    (3.0, 4.0,  "보통",      "🟡"),
    (2.0, 3.0,  "개선 필요", "🟠"),
    (0.0, 2.0,  "가장 취약", "🔴"),
]

# ──────────────────────────────────────────────
# Evidence Trimming 설정
# ──────────────────────────────────────────────
EVIDENCE_MAX_LENGTH = 100

# ──────────────────────────────────────────────
# Fallback 메시지
# ──────────────────────────────────────────────
FALLBACK_REASON = "해당 항목에 대한 구체적인 분석 내용이 부족하여, 정량 지표에 기반한 점수만 산출되었습니다."


def _get_grade(score: float) -> dict:
    """가중 평균 점수로부터 등급 정보를 반환합니다."""
    for lo, hi, grade, label, emoji, summary in GRADE_TABLE:
        if lo <= score < hi:
            return {
                "grade": grade,
                "label": label,
                "emoji": emoji,
                "summary": summary,
            }
    # fallback
    return {"grade": "F", "label": "시급한 개선", "emoji": "🔴", "summary": GRADE_TABLE[-1][5]}


def _get_item_label(score: float) -> dict:
    """세부 항목 점수로부터 4단계 라벨 정보를 반환합니다."""
    for lo, hi, label, emoji in ITEM_LABEL_TABLE:
        if lo <= score < hi:
            return {"label": label, "emoji": emoji}
    return {"label": "가장 취약", "emoji": "🔴"}


def _trim_evidence(text: str, max_len: int = EVIDENCE_MAX_LENGTH) -> str:
    """evidence 텍스트를 max_len 자로 자르고, 초과 시 '…'을 붙입니다."""
    if not text:
        return ""
    text = text.strip()
    if len(text) <= max_len:
        return text
    return text[:max_len].rstrip() + "…"


def preprocess_result_data(result_data: dict) -> dict:
    """_result.json 데이터를 LLM에 보내기 전에 고도화합니다."""
    categories = result_data.get("category_results", [])

    all_scores = []
    for cat in categories:
        final = cat.get("final_score")
        if final is not None:
            all_scores.append(final)

    weighted_avg = round(sum(all_scores) / len(all_scores), 2) if all_scores else 0.0
    grade_info = _get_grade(weighted_avg)

    result_data.setdefault("lecture_summary", {})
    result_data["lecture_summary"]["weighted_avg"] = weighted_avg
    result_data["lecture_summary"]["grade_info"] = grade_info

    sorted_cats = sorted(categories, key=lambda c: c.get("final_score", 0))
    bottom_cats = sorted_cats[:2]
    impact_parts = [
        f"'{c['category_name']}'({c['final_score']}점)" for c in bottom_cats
    ]
    impact_sentence = (
        f"특히 {', '.join(impact_parts)}의 낮은 점수가 "
        f"전체 점수를 크게 낮추는 주요 요인으로 작용했습니다."
    )
    result_data["lecture_summary"]["score_impact_analysis"] = impact_sentence

    all_item_scores = []
    for cat in categories:
        for item in cat.get("top_items", []):
            fs = item.get("final_score", 0)
            all_item_scores.append((fs, item.get("item_name", "")))

    all_item_scores.sort(key=lambda x: x[0])
    bottom_3_names = {name for _, name in all_item_scores[:3]}

    for cat in categories:
        cat_score = cat.get("final_score", 0)
        cat["label_info"] = _get_item_label(cat_score)

        for item in cat.get("top_items", []):
            item_score = item.get("final_score", 0)
            item["label_info"] = _get_item_label(item_score)
            item["is_priority_improvement"] = (item.get("item_name", "") in bottom_3_names)

            evidence = item.get("selected_evidence")
            if evidence and isinstance(evidence, dict):
                evidence.pop("context_before", None)
                if "span_text" in evidence:
                    evidence["span_text"] = _trim_evidence(evidence["span_text"])

            reason = item.get("reason", "")
            if not reason or not reason.strip():
                item["reason"] = FALLBACK_REASON

    return result_data


def generate_final_report(date, results_dir=None, trajectory_file=None, output_dir=None):
    if results_dir is None:
        results_dir = os.path.join(os.getcwd(), "results")
    if output_dir is None:
        output_dir = results_dir

    
    result_file = os.path.join(results_dir, f"{date}_result.json")
    if not os.path.exists(result_file):
        print(f"오류: 파일을 찾을 수 없습니다: {result_file}")
        return None

    # 일별 결과 로드 및 전처리
    with open(result_file, 'r', encoding='utf-8') as f:
        result_data = json.load(f)

    if "lecture_summary" not in result_data:
        result_data["lecture_summary"] = {}
    result_data["lecture_summary"]["date"] = date

    print(f"📦 [{date}] 데이터 전처리 중... (등급 산출, 인과 분석, 트리밍)")
    result_data = preprocess_result_data(result_data)

    # 궤적 파일(trajectory) 로드
    trajectory_data = None
    if trajectory_file is None:
        trajectory_files = glob.glob(os.path.join(results_dir, "*trajectory.json"))
        if trajectory_files:
            trajectory_file = trajectory_files[0]
            
    if trajectory_file and os.path.exists(trajectory_file):
        print(f"📈 궤적(Trajectory) 파일 발견: {trajectory_file}")
        with open(trajectory_file, 'r', encoding='utf-8') as tf:
            trajectory_data = json.load(tf)
    else:
        print("⚠️ 궤적(Trajectory) 파일을 찾지 못했습니다. 일간 데이터로만 진행합니다.")

    # LLM용 최종 Payload 구성
    final_payload_for_llm = {
        "daily_result": result_data
    }
    if trajectory_data:
        final_payload_for_llm["historical_trajectory"] = trajectory_data

    prompt_text = get_report_synthesis_prompt(json.dumps(final_payload_for_llm, ensure_ascii=False, indent=2))
    
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
    headers = {'Content-Type': 'application/json'}
    payload = {
        "contents": [{"parts": [{"text": prompt_text}]}]
    }

    print(f"🤖 LLM 리포트 합성 시작... (모델: {model_name})")
    
    try:
        response = requests.post(url, headers=headers, json=payload)
        res_json = response.json()
        
        if 'candidates' in res_json:
            report_content = res_json['candidates'][0]['content']['parts'][0]['text']
            
            # LLM이 응답을 ```markdown 으로 감싸서 보낼 경우 이를 제거
            report_content = report_content.strip()
            if report_content.startswith("```markdown"):
                report_content = report_content[len("```markdown"):].strip()
            elif report_content.startswith("```"):
                report_content = report_content[3:].strip()
            
            if report_content.endswith("```"):
                report_content = report_content[:-3].strip()
        else:
            print(f"API 응답 오류: {res_json}")
            return None

        output_file = os.path.join(output_dir, f"{date}_report.md")
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(report_content)
            
        print(f"✅ 최종 리포트 생성 완료: {output_file}")
        return output_file
    except Exception as e:
        print(f"오류 발생: {e}")
        return None

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", type=str, required=True, help="생성할 리포트의 날짜 (예: 2026-02-05)")
    parser.add_argument("--results_dir", type=str, default=None, help="JSON 파일이 위치한 폴더 (ex: ../outputs_flat)")
    parser.add_argument("--trajectory", type=str, default=None, help="특정 trajectory.json 파일 직접 지정")
    parser.add_argument("--output_dir", type=str, default=None, help="결과를 저장할 폴더")
    args = parser.parse_args()
    
    generate_final_report(args.date, results_dir=args.results_dir, trajectory_file=args.trajectory, output_dir=args.output_dir)
