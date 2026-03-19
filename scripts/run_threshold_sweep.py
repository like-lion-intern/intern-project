from __future__ import annotations

import argparse
import csv
import subprocess
import time
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def read_comparison(csv_path: Path) -> list[dict[str, str]]:
    if not csv_path.exists():
        return []
    with csv_path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output-root", default="outputs_sweep")
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--python-bin", default=sys.executable, help="python executable for launching run_pipeline.py")
    parser.add_argument("--upload", action="store_true")
    parser.add_argument("--hf-repo-id", default="youngyoung00/lectures")
    parser.add_argument("--hf-token", default="")
    parser.add_argument("--e5-thresholds", nargs="+", default=["0.22", "0.24", "0.25"])
    parser.add_argument("--bge-thresholds", nargs="+", default=["0.55", "0.60", "0.65"])
    parser.add_argument("--progress-file", default="", help="path to sweep progress json")
    args = parser.parse_args()

    root = Path(args.project_root).resolve()
    this_dir = Path(__file__).resolve().parent
    pipeline_script = root / "scripts" / "run_pipeline.py"
    if not pipeline_script.exists():
        pipeline_script = this_dir / "run_pipeline.py"
    if not pipeline_script.exists():
        raise FileNotFoundError(
            f"run_pipeline.py not found. tried: {root / 'scripts' / 'run_pipeline.py'} and {this_dir / 'run_pipeline.py'}"
        )
    output_root = root / args.output_root
    output_root.mkdir(parents=True, exist_ok=True)

    leaderboard: list[dict[str, str]] = []
    combos = [(e5_t, bge_t) for e5_t in args.e5_thresholds for bge_t in args.bge_thresholds]
    total_runs = len(combos)
    started = time.perf_counter()
    started_at = now_iso()

    for run_idx, (e5_t, bge_t) in enumerate(combos, start=1):
            run_name = f"e5_{e5_t}_bge_{bge_t}".replace(".", "p")
            out_dir = output_root / run_name
            cmd = [
                args.python_bin,
                str(pipeline_script),
                "--project-root",
                str(root),
                "--input-dir",
                args.input_dir,
                "--output-dir",
                str(out_dir),
                "--models",
                "multilingual-e5-large",
                "BAAI/bge-m3",
                "--device",
                args.device,
                "--batch-size",
                str(args.batch_size),
                "--model-shift-thresholds",
                f"multilingual-e5-large={e5_t}",
                f"BAAI/bge-m3={bge_t}",
            ]
            if args.progress_file:
                cmd += ["--progress-file", args.progress_file]
            if args.upload:
                cmd += ["--upload", "--hf-repo-id", args.hf_repo_id, "--hf-token", args.hf_token]

            print(f"[RUN] {run_idx}/{total_runs}: {run_name}")
            subprocess.run(cmd, check=True)
            if args.progress_file:
                elapsed = time.perf_counter() - started
                eta = (elapsed / max(run_idx, 1)) * max(total_runs - run_idx, 0)
                Path(args.progress_file).parent.mkdir(parents=True, exist_ok=True)
                Path(args.progress_file).write_text(
                    json.dumps(
                        {
                            "stage": "sweep",
                            "run_name": run_name,
                            "run_done": run_idx,
                            "run_total": total_runs,
                            "percent": round(run_idx / max(total_runs, 1) * 100, 2),
                            "started_at": started_at,
                            "updated_at": now_iso(),
                            "elapsed_sec": round(elapsed, 2),
                            "eta_sec": round(eta, 2),
                        },
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )

            rows = read_comparison(out_dir / "comparison" / "model_comparison.csv")
            for row in rows:
                leaderboard.append(
                    {
                        "run_name": run_name,
                        "run_index": str(run_idx),
                        "run_total": str(total_runs),
                        "e5_shift_threshold": e5_t,
                        "bge_shift_threshold": bge_t,
                        **row,
                    }
                )

    leaderboard_path = output_root / "leaderboard.csv"
    if leaderboard:
        keys = list(leaderboard[0].keys())
        with leaderboard_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            writer.writerows(leaderboard)
    print(f"[DONE] leaderboard: {leaderboard_path}")
    if args.progress_file:
        Path(args.progress_file).write_text(
            json.dumps(
                {
                    "stage": "done",
                    "run_done": total_runs,
                    "run_total": total_runs,
                    "percent": 100.0,
                    "started_at": started_at,
                    "updated_at": now_iso(),
                    "elapsed_sec": round(time.perf_counter() - started, 2),
                    "eta_sec": 0.0,
                    "leaderboard": str(leaderboard_path),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
