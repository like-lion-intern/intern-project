from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
import statistics
import time
from datetime import datetime, timezone
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any


LINE_RE = re.compile(r"^<(?P<h>\d{2}):(?P<m>\d{2}):(?P<s>\d{2})>\s*(?P<text>.*)$")
TRANSITION_TERMS = ["자 이제", "그러면 이제", "다음으로", "이번에는", "그 다음", "정리하면", "여기까지", "마무리"]
SESSION_HINT_TERMS = ["점심", "오후", "쉬었다가", "쉬고", "재입실", "오도록 하겠습니다", "오후에"]
DISCOURSE_MARKERS = ["이제", "그러면", "그래서", "자", "음", "어", "일단"]
PRACTICE_CUES = ["실습", "해보세요", "해볼게요", "따라", "직접", "구현해", "작성해"]
EXAMPLE_CUES = ["예를 들어", "예시", "가령", "예를 들면"]
QUESTION_CUES = ["?", "인가요", "맞죠", "되셨죠", "아시겠죠", "이해", "질문"]
EXPLANATION_CUES = ["설명", "의미", "원리", "왜", "정리", "개념", "구조", "흐름"]

MODEL_MAP = {
    "multilingual-e5-large": "intfloat/multilingual-e5-large",
    "BAAI/bge-m3": "BAAI/bge-m3",
}

LABEL_RULES: dict[str, dict[str, Any]] = {
    "도입": {"cues": ["오늘", "진행", "순서", "오늘은", "해보도록", "목표"], "early_bias": 1.2},
    "복습": {"cues": ["어제", "복습", "지난 시간", "이전에"], "early_bias": 1.1},
    "개념 설명": {"cues": ["개념", "의미", "정의", "원리", "구조", "조건"], "mid_bias": 0.4},
    "예제 설명": {"cues": ["예를 들어", "예시", "코드", "실행", "보시면"], "mid_bias": 0.6},
    "실습 유도": {"cues": PRACTICE_CUES, "mid_bias": 0.7},
    "정리": {"cues": ["정리", "마무리", "요약", "끝내"], "late_bias": 1.4},
}

LABEL_PROTOTYPES: dict[str, list[str]] = {
    "도입": [
        "오늘 수업 목표와 전체 진행 순서를 안내합니다.",
        "이번 시간에 무엇을 배울지 소개합니다.",
    ],
    "복습": [
        "지난 시간에 배운 내용을 다시 정리합니다.",
        "이전 수업 내용을 간단히 복습합니다.",
    ],
    "개념 설명": [
        "핵심 개념의 정의와 원리를 설명합니다.",
        "개념의 구조와 의미를 상세히 풀이합니다.",
    ],
    "예제 설명": [
        "예시 코드를 통해 개념 적용 방법을 설명합니다.",
        "구체적인 예제를 단계별로 해설합니다.",
    ],
    "실습 유도": [
        "직접 따라 하며 실습을 진행하도록 안내합니다.",
        "지금부터 코드를 작성하고 실행해 보라고 지시합니다.",
    ],
    "정리": [
        "오늘 학습 내용을 요약하고 마무리합니다.",
        "핵심 포인트를 다시 정리하며 수업을 끝냅니다.",
    ],
}


def safe_mkdir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_json(path: Path, payload: Any) -> None:
    safe_mkdir(path.parent)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    safe_mkdir(path.parent)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    safe_mkdir(path.parent)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    keys = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)


def write_progress(progress_path: Path | None, payload: dict[str, Any]) -> None:
    if progress_path is None:
        return
    safe_mkdir(progress_path.parent)
    progress_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def normalize(v: list[float]) -> list[float]:
    n = math.sqrt(sum(x * x for x in v))
    if n == 0:
        return v
    return [x / n for x in v]


def mean_vector(vectors: list[list[float]]) -> list[float]:
    if not vectors:
        return []
    dims = len(vectors[0])
    acc = [0.0] * dims
    for v in vectors:
        for i in range(dims):
            acc[i] += v[i]
    return normalize([x / len(vectors) for x in acc])


@dataclass
class Embedder:
    model_id: str
    device: str = "cpu"
    local_files_only: bool = False

    def __post_init__(self) -> None:
        from sentence_transformers import SentenceTransformer
        import torch
        try:
            self.model = SentenceTransformer(
                self.model_id,
                device=self.device,
                trust_remote_code=True,
                local_files_only=self.local_files_only,
            )
            
            # [최적화] CPU 환경을 위한 INT8 동적 양자화 적용
            if self.device == "cpu":
                torch.backends.quantized.engine = 'qnnpack' if 'qnnpack' in torch.backends.quantized.supported_engines else 'fbgemm'
                self.model = torch.ao.quantization.quantize_dynamic(
                    self.model, {torch.nn.Linear}, dtype=torch.qint8
                )
        except Exception:
            # Fallback for environments without CUDA/MPS support.
            self.device = "cpu"
            self.model = SentenceTransformer(
                self.model_id,
                device=self.device,
                trust_remote_code=True,
                local_files_only=self.local_files_only,
            )
            # [최적화] CPU Fallback 환경에도 INT8 양자화 적용
            torch.backends.quantized.engine = 'qnnpack' if 'qnnpack' in torch.backends.quantized.supported_engines else 'fbgemm'
            self.model = torch.ao.quantization.quantize_dynamic(
                self.model, {torch.nn.Linear}, dtype=torch.qint8
            )

    def encode(self, texts: list[str], batch_size: int = 64) -> list[list[float]]:
        vectors = self.model.encode(
            texts,
            batch_size=batch_size,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return [v.tolist() for v in vectors]


def parse_stt_file(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0
    prev_raw = -1
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
        m = LINE_RE.match(line.strip())
        if not m:
            continue
        h, mm, s = int(m.group("h")), int(m.group("m")), int(m.group("s"))
        raw = h * 3600 + mm * 60 + s
        if prev_raw >= 0 and raw < prev_raw:
            # STT logs often use 12-hour style clock without AM/PM.
            # If time goes from late morning/noon to early hour, treat it as +12h wrap.
            prev_h = prev_raw // 3600
            cur_h = raw // 3600
            if prev_h >= 11 and cur_h <= 5:
                offset += 12 * 3600
            else:
                offset += 24 * 3600
        prev_raw = raw
        rows.append(
            {
                "line_idx": i,
                "timestamp": f"{h:02d}:{mm:02d}:{s:02d}",
                "elapsed_seconds": raw + offset,
                "text": m.group("text").strip(),
            }
        )
    return rows


def discourse_metrics(utterances: list[dict[str, Any]]) -> dict[str, Any]:
    full_text = " ".join(u["text"] for u in utterances)
    token_count = max(len(re.findall(r"\S+", full_text)), 1)
    total_counts = {m: full_text.count(m) for m in DISCOURSE_MARKERS}
    per_k = {m: round(c / token_count * 1000, 3) for m, c in total_counts.items()}

    bins: dict[int, dict[str, int]] = defaultdict(lambda: {m: 0 for m in DISCOURSE_MARKERS})
    start = utterances[0]["elapsed_seconds"] if utterances else 0
    for u in utterances:
        idx = (u["elapsed_seconds"] - start) // 600
        for m in DISCOURSE_MARKERS:
            bins[idx][m] += u["text"].count(m)
    time_bins = [{"bin_10min": int(k), **v} for k, v in sorted(bins.items())]
    return {"token_count": token_count, "total_counts": total_counts, "per_1k_tokens": per_k, "time_bins": time_bins}


def choose_label(text: str, ratio: float) -> str:
    best_label = "개념 설명"
    best_score = -1.0
    for label, rule in LABEL_RULES.items():
        score = float(sum(text.count(c) for c in rule["cues"]))
        if ratio <= 0.2:
            score += float(rule.get("early_bias", 0.0))
        if 0.2 < ratio < 0.8:
            score += float(rule.get("mid_bias", 0.0))
        if ratio >= 0.8:
            score += float(rule.get("late_bias", 0.0))
        if score > best_score:
            best_score = score
            best_label = label
    return best_label


def count_cues(text: str, cues: list[str]) -> int:
    return sum(text.count(c) for c in cues)


def classify_chunk_sub_label(parent_label: str, text: str) -> str:
    """Assign finer-grained labels inside practice segments."""
    if parent_label != "실습 유도":
        return "general"

    instruction_score = count_cues(text, PRACTICE_CUES) + count_cues(text, ["클릭", "입력", "실행", "작성"])
    example_score = count_cues(text, EXAMPLE_CUES) + count_cues(text, ["샘플", "예제", "케이스"])
    explanation_score = count_cues(text, EXPLANATION_CUES)

    if instruction_score >= example_score and instruction_score >= explanation_score and instruction_score > 0:
        return "practice_instruction"
    if example_score >= explanation_score and example_score > 0:
        return "practice_example"
    return "practice_explanation"


def split_session(utterances: list[dict[str, Any]]) -> dict[str, Any]:
    if len(utterances) < 5:
        return {"is_split": False, "split_index": None, "confidence": 0.0}
    candidates = []
    for i in range(1, len(utterances)):
        prev, cur = utterances[i - 1], utterances[i]
        gap = cur["elapsed_seconds"] - prev["elapsed_seconds"]
        score = 0.0
        if gap >= 20 * 60:
            score += 0.6
        if gap >= 10 * 60:
            score += 0.2
        around = f"{prev['text']} {cur['text']}"
        if any(k in around for k in SESSION_HINT_TERMS):
            score += 0.3
        ratio = i / len(utterances)
        if 0.2 <= ratio <= 0.8:
            score += 0.1
        if score > 0:
            candidates.append((i, min(score, 1.0), gap))
    if not candidates:
        return {"is_split": False, "split_index": None, "confidence": 0.0}
    i, conf, gap = sorted(candidates, key=lambda x: (x[1], x[2]), reverse=True)[0]
    return {"is_split": conf >= 0.6, "split_index": i, "confidence": round(conf, 3), "gap_seconds": gap}


def boundary_scores(utterances: list[dict[str, Any]], embeddings: list[list[float]]) -> list[dict[str, Any]]:
    rows = []
    prev_label = choose_label(utterances[0]["text"], 0.0)
    for i in range(1, len(utterances)):
        prev, cur = utterances[i - 1], utterances[i]
        sim = cosine(embeddings[i - 1], embeddings[i])
        gap = cur["elapsed_seconds"] - prev["elapsed_seconds"]
        ratio = i / max(len(utterances) - 1, 1)
        label = choose_label(cur["text"], ratio)
        score = (1 - sim) * 1.5
        if gap >= 5 * 60:
            score += 0.35
        if gap >= 15 * 60:
            score += 0.75
        if any(t in (prev["text"] + " " + cur["text"]) for t in TRANSITION_TERMS):
            score += 0.6
        if prev_label != label:
            score += 0.4
        rows.append({"index": i, "score": round(score, 4), "sim": round(sim, 4), "gap_seconds": gap})
        prev_label = label
    return rows


def build_label_profiles(embedder: Embedder, model_key: str) -> dict[str, list[float]]:
    profiles: dict[str, list[float]] = {}
    for label, sents in LABEL_PROTOTYPES.items():
        texts = [f"passage: {s}" for s in sents] if "e5" in model_key else sents
        vectors = embedder.encode(texts, batch_size=16)
        profiles[label] = mean_vector(vectors)
    return profiles


def choose_label_by_profile(segment_embedding: list[float], label_profiles: dict[str, list[float]]) -> tuple[str, float]:
    best_label = "개념 설명"
    best_score = -1.0
    for label, prof in label_profiles.items():
        score = cosine(segment_embedding, prof)
        if score > best_score:
            best_score = score
            best_label = label
    return best_label, round(best_score, 4)


def macro_segment(
    utterances: list[dict[str, Any]],
    embeddings: list[list[float]],
    threshold: float = 1.05,
    label_mode: str = "rule",
    label_profiles: dict[str, list[float]] | None = None,
) -> list[dict[str, Any]]:
    if not utterances:
        return []
    scores = boundary_scores(utterances, embeddings)
    boundaries = [s["index"] for s in scores if s["score"] >= threshold]
    filtered = []
    last = 0
    for b in boundaries:
        if b - last >= 8:
            filtered.append(b)
            last = b
    if len(utterances) - last < 8 and filtered:
        filtered.pop()

    segments = []
    starts = [0] + filtered
    ends = filtered + [len(utterances)]
    for i, (s, e) in enumerate(zip(starts, ends), start=1):
        part = utterances[s:e]
        text = " ".join(x["text"] for x in part)
        label_votes = Counter(choose_label(u["text"], j / max(len(part) - 1, 1)) for j, u in enumerate(part))
        rule_label = label_votes.most_common(1)[0][0]
        label = rule_label
        label_score = None
        label_source = "rule"
        if label_mode == "e5_proto" and label_profiles:
            seg_emb = mean_vector(embeddings[s:e])
            label, label_score = choose_label_by_profile(seg_emb, label_profiles)
            label_source = "e5_prototype"
        segments.append(
            {
                "segment_id": f"seg_{i:02d}",
                "start_idx": s,
                "end_idx": e - 1,
                "start_ts": part[0]["timestamp"],
                "end_ts": part[-1]["timestamp"],
                "utterance_count": len(part),
                "label": label,
                "rule_label": rule_label,
                "label_source": label_source,
                "label_score": label_score,
                "text": text,
                "text_preview": text[:400],
            }
        )
    return segments


def detect_topic_shifts(utterances: list[dict[str, Any]], embeddings: list[list[float]], drop_threshold: float = 0.28) -> list[dict[str, Any]]:
    if len(utterances) < 3:
        return []
    sims = [cosine(embeddings[i - 1], embeddings[i]) for i in range(1, len(embeddings))]
    shifts = []
    for i in range(1, len(sims) - 1):
        prev_s, cur_s, next_s = sims[i - 1], sims[i], sims[i + 1]
        if cur_s <= prev_s and cur_s <= next_s and (1 - cur_s) >= drop_threshold:
            shifts.append(
                {
                    "index": i + 1,
                    "timestamp": utterances[i + 1]["timestamp"],
                    "similarity": round(cur_s, 4),
                    "drop_strength": round(1 - cur_s, 4),
                }
            )
    return shifts


def semantic_chunking(segment_rows: list[dict[str, Any]], utterances: list[dict[str, Any]], embeddings: list[list[float]], sim_threshold: float = 0.74) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    for seg in segment_rows:
        s, e = seg["start_idx"], seg["end_idx"] + 1
        if e - s <= 1:
            continue
        start = s
        chunk_id = 1
        for i in range(s + 1, e):
            sim = cosine(embeddings[i - 1], embeddings[i])
            if sim < sim_threshold and (i - start) >= 5:
                part = utterances[start:i]
                part_text = " ".join(x["text"] for x in part)
                chunks.append(
                    {
                        "segment_id": seg["segment_id"],
                        "parent_label": seg["label"],
                        "sub_label": classify_chunk_sub_label(seg["label"], part_text),
                        "chunk_id": f"{seg['segment_id']}_chunk_{chunk_id:02d}",
                        "start_idx": start,
                        "end_idx": i - 1,
                        "start_ts": part[0]["timestamp"],
                        "end_ts": part[-1]["timestamp"],
                        "utterance_count": len(part),
                        "text": part_text,
                        "text_preview": part_text[:280],
                        "avg_adjacent_sim": round(
                            statistics.mean(cosine(embeddings[j - 1], embeddings[j]) for j in range(start + 1, i)), 4
                        )
                        if i - start > 1
                        else 1.0,
                    }
                )
                start = i
                chunk_id += 1
        tail = utterances[start:e]
        tail_text = " ".join(x["text"] for x in tail)
        chunks.append(
            {
                "segment_id": seg["segment_id"],
                "parent_label": seg["label"],
                "sub_label": classify_chunk_sub_label(seg["label"], tail_text),
                "chunk_id": f"{seg['segment_id']}_chunk_{chunk_id:02d}",
                "start_idx": start,
                "end_idx": e - 1,
                "start_ts": tail[0]["timestamp"],
                "end_ts": tail[-1]["timestamp"],
                "utterance_count": len(tail),
                "text": tail_text,
                "text_preview": tail_text[:280],
                "avg_adjacent_sim": round(
                    statistics.mean(cosine(embeddings[j - 1], embeddings[j]) for j in range(start + 1, e)), 4
                )
                if e - start > 1
                else 1.0,
            }
        )
    return chunks


def load_terms(base: Path) -> set[str]:
    terms = set()
    core = base / "project-data" / "dictionaries" / "term_map_core.json"
    if core.exists():
        payload = json.loads(core.read_text(encoding="utf-8"))
        for k, v in payload.items():
            terms.add(k)
            if isinstance(v, str):
                terms.add(v)
            elif isinstance(v, list):
                terms.update(str(x) for x in v)
    return {t for t in terms if t}


def extract_features(utterances: list[dict[str, Any]], discourse: dict[str, Any], terms: set[str]) -> dict[str, Any]:
    texts = [u["text"] for u in utterances]
    full = " ".join(texts)
    token_count = max(len(re.findall(r"\S+", full)), 1)

    question_count = sum(1 for t in texts if any(c in t for c in QUESTION_CUES))
    example_count = sum(1 for t in texts if any(c in t for c in EXAMPLE_CUES))
    practice_count = sum(1 for t in texts if any(c in t for c in PRACTICE_CUES))
    repetition_count = sum(max(full.count(x) - 1, 0) for x in ["그러니까", "정리하면", "다시 한번", "쉽게 말해"])
    term_hits = sum(full.count(t) for t in terms if len(t) >= 2)

    return {
        "utterance_count": len(utterances),
        "token_count": token_count,
        "question_count": question_count,
        "example_count": example_count,
        "practice_directive_ratio": round(practice_count / max(len(utterances), 1), 4),
        "term_density_per_1k_tokens": round(term_hits / token_count * 1000, 3),
        "repetition_count": repetition_count,
        "discourse_marker_per_1k_tokens": discourse["per_1k_tokens"],
    }


def summarize_model_day(
    date: str,
    macro_segments: list[dict[str, Any]],
    topic_shifts: list[dict[str, Any]],
    chunks: list[dict[str, Any]],
    runtime_sec: float,
) -> dict[str, Any]:
    seg_lengths = [s["utterance_count"] for s in macro_segments]
    chunk_sims = [c["avg_adjacent_sim"] for c in chunks]
    return {
        "date": date,
        "segment_count": len(macro_segments),
        "topic_shift_count": len(topic_shifts),
        "chunk_count": len(chunks),
        "avg_segment_len": round(statistics.mean(seg_lengths), 3) if seg_lengths else 0.0,
        "segment_len_std": round(statistics.pstdev(seg_lengths), 3) if len(seg_lengths) > 1 else 0.0,
        "avg_chunk_intra_sim": round(statistics.mean(chunk_sims), 4) if chunk_sims else 0.0,
        "runtime_sec": round(runtime_sec, 3),
    }


def upload_folder(local_folder: Path, repo_id: str, token: str, path_in_repo: str) -> None:
    from huggingface_hub import HfApi
    from huggingface_hub.errors import RepositoryNotFoundError

    api = HfApi(token=token)
    try:
        api.repo_info(repo_id=repo_id, repo_type="dataset")
    except RepositoryNotFoundError:
        api.create_repo(repo_id=repo_id, repo_type="dataset", private=False, exist_ok=True)
    api.upload_folder(
        folder_path=str(local_folder),
        repo_id=repo_id,
        path_in_repo=path_in_repo,
        repo_type="dataset",
    )


def run(args: argparse.Namespace) -> None:
    started = time.perf_counter()
    started_at = now_iso()
    if args.offline_mode:
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"

    base = Path(args.project_root).resolve()
    input_dir = base / args.input_dir
    output_dir = base / args.output_dir
    common_dir = output_dir / "common"
    by_model_dir = output_dir / "by_model"
    comparison_dir = output_dir / "comparison"

    safe_mkdir(output_dir)
    safe_mkdir(common_dir)
    safe_mkdir(by_model_dir)
    safe_mkdir(comparison_dir)
    progress_path = Path(args.progress_file).resolve() if args.progress_file else None

    terms = load_terms(base)
    parsed_rows_all: list[dict[str, Any]] = []
    split_manifest: list[dict[str, Any]] = []
    discourse_summary: list[dict[str, Any]] = []
    parsed_by_date: dict[str, list[dict[str, Any]]] = {}

    files = sorted(input_dir.glob("*.txt"))
    if args.max_files > 0:
        files = files[: args.max_files]

    total_files = len(files)
    for file_idx, file in enumerate(files, start=1):
        date = file.stem
        utt = parse_stt_file(file)
        parsed_by_date[date] = utt
        write_jsonl(common_dir / "parsed" / f"{date}.jsonl", utt)
        parsed_rows_all.append({"date": date, "utterance_count": len(utt), "path": str(file)})

        disc = discourse_metrics(utt)
        write_json(common_dir / "discourse_marker" / f"{date}.json", disc)
        discourse_summary.append({"date": date, "token_count": disc["token_count"], **disc["total_counts"]})

        split = split_session(utt)
        write_json(common_dir / "session_split" / f"{date}.json", split)
        split_manifest.append({"date": date, **split})
        print(f"[common] {file_idx}/{total_files} parsed: {date}")
        write_progress(
            progress_path,
            {
                "stage": "common",
                "current_date": date,
                "done": file_idx,
                "total": total_files,
                "percent": round(file_idx / max(total_files, 1) * 100, 2),
                "started_at": started_at,
                "updated_at": now_iso(),
                "elapsed_sec": round(time.perf_counter() - started, 2),
            },
        )

    write_csv(common_dir / "parsed_summary.csv", parsed_rows_all)
    write_csv(common_dir / "discourse_marker" / "summary.csv", discourse_summary)
    write_csv(common_dir / "session_split" / "manifest.csv", split_manifest)

    if args.upload and args.hf_token and args.hf_repo_id:
        try:
            upload_folder(common_dir, args.hf_repo_id, args.hf_token, "outputs/common")
        except Exception as e:
            print(f"[WARN] common upload failed: {e}")

    comparison_rows: list[dict[str, Any]] = []
    model_shift_overrides = parse_model_float_overrides(args.model_shift_thresholds)
    if args.common_only:
        return

    model_total = len(args.models)
    for model_idx, model_key in enumerate(args.models, start=1):
        if model_key not in MODEL_MAP:
            raise ValueError(f"Unsupported model key: {model_key}")
        model_id = MODEL_MAP[model_key]
        safe_model_key = model_key.replace("/", "__")
        out_root = by_model_dir / safe_model_key
        safe_mkdir(out_root)
        embedder = Embedder(model_id=model_id, device=args.device, local_files_only=args.local_files_only)
        shift_threshold = model_shift_overrides.get(model_key, args.shift_drop_threshold)
        label_profiles = None
        if args.labeling_mode == "e5_proto":
            label_profiles = build_label_profiles(embedder, model_key)

        model_day_rows = []
        parsed_items = list(parsed_by_date.items())
        for date_idx, (date, utterances) in enumerate(parsed_items, start=1):
            if not utterances:
                continue
            t0 = time.perf_counter()
            texts = [u["text"] for u in utterances]
            if "e5" in model_key:
                texts = [f"passage: {t}" for t in texts]
            embeds = embedder.encode(texts, batch_size=args.batch_size)

            macro = macro_segment(
                utterances,
                embeds,
                threshold=args.macro_threshold,
                label_mode=args.labeling_mode,
                label_profiles=label_profiles,
            )
            shifts = detect_topic_shifts(utterances, embeds, drop_threshold=shift_threshold)
            chunks = semantic_chunking(macro, utterances, embeds, sim_threshold=args.chunk_sim_threshold)

            disc = json.loads((common_dir / "discourse_marker" / f"{date}.json").read_text(encoding="utf-8"))
            feats = extract_features(utterances, disc, terms)
            runtime_sec = time.perf_counter() - t0
            model_day = summarize_model_day(date, macro, shifts, chunks, runtime_sec)
            model_day_rows.append(model_day)

            write_json(out_root / "macro_segments" / f"{date}.json", {"date": date, "segments": macro})
            write_json(out_root / "topic_shift" / f"{date}.json", {"date": date, "topic_shifts": shifts})
            write_json(out_root / "semantic_chunks" / f"{date}.json", {"date": date, "chunks": chunks})
            write_json(out_root / "features" / f"{date}.json", {"date": date, "features": feats})
            print(f"[model:{model_key}] {date_idx}/{len(parsed_items)} done: {date}")
            global_done = (model_idx - 1) * len(parsed_items) + date_idx
            global_total = model_total * len(parsed_items)
            write_progress(
                progress_path,
                {
                    "stage": "model",
                    "model": model_key,
                    "current_date": date,
                    "model_done": date_idx,
                    "model_total": len(parsed_items),
                    "all_done": global_done,
                    "all_total": global_total,
                    "percent": round(global_done / max(global_total, 1) * 100, 2),
                    "started_at": started_at,
                    "updated_at": now_iso(),
                    "elapsed_sec": round(time.perf_counter() - started, 2),
                    "eta_sec": round(
                        ((time.perf_counter() - started) / max(global_done, 1)) * max(global_total - global_done, 0),
                        2,
                    ),
                },
            )

        write_csv(out_root / "macro_segments" / "summary.csv", model_day_rows)
        write_csv(out_root / "topic_shift" / "summary.csv", model_day_rows)
        write_csv(out_root / "semantic_chunks" / "summary.csv", model_day_rows)
        write_csv(out_root / "features" / "summary.csv", model_day_rows)

        if model_day_rows:
            avg_runtime = statistics.mean(r["runtime_sec"] for r in model_day_rows)
            avg_seg_std = statistics.mean(r["segment_len_std"] for r in model_day_rows)
            avg_chunk_sim = statistics.mean(r["avg_chunk_intra_sim"] for r in model_day_rows)
            avg_segment_count = statistics.mean(r["segment_count"] for r in model_day_rows)
            avg_topic_shift_count = statistics.mean(r["topic_shift_count"] for r in model_day_rows)
            avg_chunk_per_segment = statistics.mean(
                (r["chunk_count"] / max(r["segment_count"], 1)) for r in model_day_rows
            )
            quality_score = round((avg_chunk_sim * 60) - (avg_seg_std * 2), 3)
            speed_cost_score = round(100 / (1 + avg_runtime), 3)
        else:
            quality_score = 0.0
            speed_cost_score = 0.0
            avg_runtime = 0.0
            avg_segment_count = 0.0
            avg_topic_shift_count = 0.0
            avg_chunk_per_segment = 0.0
            avg_chunk_sim = 0.0

        gate_pass = (
            20 <= avg_segment_count <= 80
            and 5 <= avg_topic_shift_count <= 120
            and 1.0 <= avg_chunk_per_segment <= 3.5
            and avg_chunk_sim >= 0.60
        )

        comparison_rows.append(
            {
                "model_key": model_key,
                "model_id": model_id,
                "date_count": len(model_day_rows),
                "shift_drop_threshold": shift_threshold,
                "avg_segment_count": round(avg_segment_count, 3),
                "avg_topic_shift_count": round(avg_topic_shift_count, 3),
                "avg_chunk_per_segment": round(avg_chunk_per_segment, 3),
                "avg_chunk_intra_sim": round(avg_chunk_sim, 4) if model_day_rows else 0.0,
                "avg_runtime_sec": round(avg_runtime, 3),
                "quality_proxy_score": quality_score,
                "speed_cost_proxy_score": speed_cost_score,
                "analysis_llm_gate_pass": gate_pass,
            }
        )

        if args.upload and args.hf_token and args.hf_repo_id:
            try:
                upload_folder(out_root, args.hf_repo_id, args.hf_token, f"outputs/by_model/{safe_model_key}")
            except Exception as e:
                print(f"[WARN] model upload failed ({model_key}): {e}")

    write_csv(comparison_dir / "model_comparison.csv", comparison_rows)
    write_json(comparison_dir / "model_comparison.json", comparison_rows)

    lines = [
        "# Model Comparison Report",
        "",
        "## 품질 관점",
        "- `quality_proxy_score`: chunk 응집도(인접 유사도)와 분할 안정성(세그먼트 길이 분산) 기반 지표",
        "",
        "## 속도/비용 관점",
        "- `speed_cost_proxy_score`: 평균 실행 시간 기반 역수 지표 (높을수록 유리)",
        "",
        "## 결과 요약",
    ]
    for row in comparison_rows:
        lines.append(
            f"- {row['model_key']}: 품질 {row['quality_proxy_score']}, 속도/비용 {row['speed_cost_proxy_score']}, "
            f"평균시간 {row['avg_runtime_sec']}s, 평균세그먼트 {row['avg_segment_count']}, "
            f"평균토픽시프트 {row['avg_topic_shift_count']}, 게이트통과={row['analysis_llm_gate_pass']}"
        )
    (comparison_dir / "model_comparison_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    if args.upload and args.hf_token and args.hf_repo_id:
        try:
            upload_folder(comparison_dir, args.hf_repo_id, args.hf_token, "outputs/comparison")
        except Exception as e:
            print(f"[WARN] comparison upload failed: {e}")
    write_progress(
        progress_path,
        {
            "stage": "done",
            "percent": 100.0,
            "started_at": started_at,
            "updated_at": now_iso(),
            "elapsed_sec": round(time.perf_counter() - started, 2),
            "eta_sec": 0.0,
            "output_dir": str(output_dir),
            "comparison_csv": str(comparison_dir / "model_comparison.csv"),
        },
    )


def parse_model_float_overrides(pairs: list[str]) -> dict[str, float]:
    out: dict[str, float] = {}
    for item in pairs:
        if "=" not in item:
            continue
        key, val = item.split("=", 1)
        key = key.strip()
        try:
            out[key] = float(val.strip())
        except ValueError:
            continue
    return out


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--input-dir", default="stt_log_removed")
    parser.add_argument("--output-dir", default="outputs")
    parser.add_argument("--models", nargs="+", default=["multilingual-e5-large", "BAAI/bge-m3"])
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--macro-threshold", type=float, default=1.05)
    parser.add_argument("--shift-drop-threshold", type=float, default=0.28)
    parser.add_argument("--chunk-sim-threshold", type=float, default=0.74)
    parser.add_argument("--labeling-mode", choices=["rule", "e5_proto"], default="rule")
    parser.add_argument(
        "--model-shift-thresholds",
        nargs="*",
        default=[],
        help='per-model override, e.g. "multilingual-e5-large=0.15" "BAAI/bge-m3=0.45"',
    )
    parser.add_argument("--upload", action="store_true")
    parser.add_argument("--hf-repo-id", default="youngyoung00/lectures")
    parser.add_argument("--hf-token", default="")
    parser.add_argument("--common-only", action="store_true")
    parser.add_argument("--max-files", type=int, default=0, help="for smoke test; 0 means all files")
    parser.add_argument("--local-files-only", action="store_true", help="load models from local HF cache only")
    parser.add_argument("--offline-mode", action="store_true", help="force HF/transformers offline mode")
    parser.add_argument("--progress-file", default="", help="path to JSON progress file")
    return parser.parse_args()


if __name__ == "__main__":
    run(parse_args())
