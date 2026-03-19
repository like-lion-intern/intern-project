# pipeline.py
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Dict, Any


CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
if CURRENT_DIR not in sys.path:
    sys.path.append(CURRENT_DIR)

from loader import load_data
from features import calculate_signals
from scoring import build_prompt_packet, build_category_packets, normalize_feature_bundle
from llm_analysis import analyze_with_llm


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def build_heuristic_report(lecture_id: str, feature_bundle: Dict[str, Any], prompt_packet: Dict[str, Any]) -> Dict[str, Any]:
    normalized = normalize_feature_bundle(feature_bundle)

    categories_out = []
    for cat in prompt_packet.get("categories", []):
        category_items = []
        for item in cat.get("items", []):
            category_items.append({
                "item_name": item.get("item_name"),
                "heuristic_score": item.get("heuristic_score"),
                "aggregated_signals": item.get("aggregated_signals", {}),
                "signal_subscores": item.get("signal_subscores", {}),
                "selected_evidence": item.get("top_evidence", []),
                "item_context": item.get("item_context", ""),
            })

        categories_out.append({
            "category_name": cat.get("category_name"),
            "heuristic_score": cat.get("category_context", {}).get("category_heuristic_score", 0.0),
            "items": category_items,
        })

    return {
        "lecture_id": lecture_id,
        "lecture_signals": feature_bundle.get("lecture_signals", {}),
        "normalized_segments": normalized.get("segments", []),
        "categories": categories_out,
    }


def build_final_report(lecture_id: str, heuristic_report: Dict[str, Any], llm_result: Dict[str, Any]) -> Dict[str, Any]:
    heuristic_cat_map = {
        c["category_name"]: c
        for c in heuristic_report.get("categories", [])
    }

    category_results = []
    for cat in llm_result.get("category_results", []):
        h_cat = heuristic_cat_map.get(cat.get("category_name"), {})
        h_item_map = {i["item_name"]: i for i in h_cat.get("items", [])}

        fixed_items = []
        for item in cat.get("items", []):
            h_item = h_item_map.get(item.get("item_name"), {})
            fixed_items.append({
                "item_name": item.get("item_name"),
                "heuristic_score": item.get("heuristic_score", h_item.get("heuristic_score", 0.0)),
                "final_score": item.get("final_score", item.get("heuristic_score", h_item.get("heuristic_score", 0.0))),
                "aggregated_signals": h_item.get("aggregated_signals", {}),
                "signal_subscores": h_item.get("signal_subscores", {}),
                "selected_evidence": item.get("selected_evidence", h_item.get("selected_evidence", [])),
                "reason": item.get("reason", ""),
                "adjustment_reason": item.get("adjustment_reason", ""),
                "improvement_tip": item.get("improvement_tip", ""),
            })

        category_results.append({
            "category_name": cat.get("category_name"),
            "heuristic_score": cat.get("heuristic_score", h_cat.get("heuristic_score", 0.0)),
            "final_score": cat.get("final_score", cat.get("heuristic_score", h_cat.get("heuristic_score", 0.0))),
            "category_summary": cat.get("category_summary", ""),
            "strengths": cat.get("strengths", []),
            "weaknesses": cat.get("weaknesses", []),
            "improvements": cat.get("improvements", []),
            "items": fixed_items,
        })

    return {
        "lecture_id": lecture_id,
        "overall_summary": llm_result.get("overall_summary", ""),
        "overall_strengths": llm_result.get("overall_strengths", []),
        "overall_weaknesses": llm_result.get("overall_weaknesses", []),
        "priority_improvements": llm_result.get("priority_improvements", []),
        "category_results": category_results,
    }


def save_json(path: str, data: Dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def run_pipeline(date: str, base_path: str = ".", output_dir: str | None = None, debug: bool = False) -> Dict[str, Any]:
    base_path = os.path.abspath(base_path)
    output_dir = os.path.abspath(output_dir or os.path.join(PROJECT_ROOT, "outputs", date))
    ensure_dir(output_dir)

    print(f"--- Starting Pipeline for Date: {date} ---")
    print(f"Base path: {base_path}")
    print(f"Output dir: {output_dir}")

    # Step 1
    print("Step 1: Loading data...")
    features_json, chunks_json = load_data(date, base_path)

    # Step 2~6
    print("Step 2-6: Calculating lecture/segment signals...")
    feature_bundle = calculate_signals(features_json, chunks_json)

    # Step 7
    print("Step 7: Building prompt packet and heuristic report...")
    prompt_packet = build_prompt_packet(date, feature_bundle)
    heuristic_report = build_heuristic_report(date, feature_bundle, prompt_packet)

    heuristic_path = os.path.join(output_dir, "heuristic_report.json")
    save_json(heuristic_path, heuristic_report)
    print(f"Saved: {heuristic_path}")

    if debug:
        debug_payload = {
            "lecture_id": date,
            "feature_bundle": feature_bundle,
            "prompt_packet": prompt_packet,
        }
        debug_path = os.path.join(output_dir, "debug_packet.json")
        save_json(debug_path, debug_payload)
        print(f"Saved: {debug_path}")

    # Step 8
    print("Step 8: Running LLM analysis...")
    llm_result, llm_debug = analyze_with_llm(prompt_packet)

    if debug:
        llm_debug_path = os.path.join(output_dir, "llm_debug.json")
        save_json(llm_debug_path, llm_debug)
        print(f"Saved: {llm_debug_path}")

    # Step 9
    print("Step 9: Building final report...")
    final_report = build_final_report(date, heuristic_report, llm_result)

    final_path = os.path.join(output_dir, "final_report.json")
    save_json(final_path, final_report)
    print(f"Saved: {final_path}")

    print("--- Pipeline Completed ---")
    return {
        "heuristic_report_path": heuristic_path,
        "final_report_path": final_path,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", type=str, default="2026-02-02")
    parser.add_argument("--base_path", type=str, default="data")
    parser.add_argument("--output_dir", type=str, default=None)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    run_pipeline(
        date=args.date,
        base_path=args.base_path,
        output_dir=args.output_dir,
        debug=args.debug,
    )
