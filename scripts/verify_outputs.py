from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def exists_count(folder: Path, pattern: str) -> int:
    return len(list(folder.glob(pattern))) if folder.exists() else 0


def check_common(root: Path, expected_days: int) -> list[str]:
    errs: list[str] = []
    common = root / "common"
    parsed_n = exists_count(common / "parsed", "*.jsonl")
    disc_n = exists_count(common / "discourse_marker", "20*.json")
    split_n = exists_count(common / "session_split", "20*.json")
    if parsed_n != expected_days:
        errs.append(f"parsed count mismatch: {parsed_n} != {expected_days}")
    if disc_n != expected_days:
        errs.append(f"discourse count mismatch: {disc_n} != {expected_days}")
    if split_n != expected_days:
        errs.append(f"session split count mismatch: {split_n} != {expected_days}")

    sample = common / "parsed" / "2026-02-02.jsonl"
    if sample.exists():
        first = sample.read_text(encoding="utf-8").splitlines()[0]
        obj = json.loads(first)
        for k in ["line_idx", "timestamp", "elapsed_seconds", "text"]:
            if k not in obj:
                errs.append(f"parsed schema missing key: {k}")
    else:
        errs.append("parsed sample missing: 2026-02-02.jsonl")
    return errs


def check_model(root: Path, model_folder: str, expected_days: int) -> list[str]:
    errs: list[str] = []
    base = root / "by_model" / model_folder
    for sub, pat in [
        ("macro_segments", "20*.json"),
        ("topic_shift", "20*.json"),
        ("semantic_chunks", "20*.json"),
        ("features", "20*.json"),
    ]:
        c = exists_count(base / sub, pat)
        if c != expected_days:
            errs.append(f"{model_folder}/{sub} count mismatch: {c} != {expected_days}")
        if not (base / sub / "summary.csv").exists():
            errs.append(f"{model_folder}/{sub}/summary.csv missing")
    return errs


def quick_stats(root: Path, model_folder: str) -> dict:
    p = root / "by_model" / model_folder / "macro_segments" / "summary.csv"
    if not p.exists():
        return {}
    rows = list(csv.DictReader(p.open(encoding="utf-8")))
    if not rows:
        return {}
    avg_seg = sum(float(r.get("segment_count", 0)) for r in rows) / len(rows)
    avg_runtime = sum(float(r.get("runtime_sec", 0)) for r in rows) / len(rows)
    return {"model": model_folder, "date_count": len(rows), "avg_segment_count": round(avg_seg, 3), "avg_runtime_sec": round(avg_runtime, 3)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output-dir", default="outputs")
    ap.add_argument("--expected-days", type=int, default=15)
    args = ap.parse_args()

    root = Path(args.output_dir)
    all_errs: list[str] = []
    all_errs.extend(check_common(root, args.expected_days))
    all_errs.extend(check_model(root, "multilingual-e5-large", args.expected_days))
    all_errs.extend(check_model(root, "BAAI__bge-m3", args.expected_days))

    print("== Verification Summary ==")
    if all_errs:
        print("FAIL")
        for e in all_errs:
            print("-", e)
    else:
        print("PASS")

    for model in ["multilingual-e5-large", "BAAI__bge-m3"]:
        s = quick_stats(root, model)
        if s:
            print(s)


if __name__ == "__main__":
    main()
