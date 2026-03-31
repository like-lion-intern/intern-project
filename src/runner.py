"""
파이프라인 실행 모듈 (Celery 없이 스레드에서 직접 실행).

macOS에서 fork() + PyTorch 네이티브 라이브러리가 SIGSEGV를 
유발하는 문제를 피하기 위해 Celery를 사용하지 않고,
threading.Thread로 파이프라인을 백그라운드 실행한다.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import uuid
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.config import settings

# ─── 경로 설정 ────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(settings.project_root).resolve()
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
ANALYSIS_DIR = PROJECT_ROOT / "analysis_llm" / "src"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
if str(ANALYSIS_DIR) not in sys.path:
    sys.path.insert(0, str(ANALYSIS_DIR))

logger = logging.getLogger(__name__)

# ─── 임베딩 모델 singleton (스레드 내 1회 로드) ──────────────────────────────
_embedder_large = None
_embedder_small = None
_models_loaded = False
_model_lock = threading.Lock()


def _ensure_models_loaded() -> None:
    """Embedder를 singleton으로 로드한다. 실패 시 None으로 유지."""
    global _embedder_large, _embedder_small, _models_loaded
    with _model_lock:
        if _models_loaded:
            return

    if settings.offline_mode:
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"

    try:
        from run_pipeline import Embedder, MODEL_MAP
        model_id = MODEL_MAP.get(settings.embedding_model, MODEL_MAP["multilingual-e5-large"])
        _embedder_large = Embedder(
            model_id=model_id,
            device=settings.embedding_device,
            local_files_only=settings.local_files_only,
        )
        logger.info("[Runner] Embedder(large) 로드 완료: %s", model_id)

        _embedder_small = Embedder(
            model_id="intfloat/multilingual-e5-small",
            device=settings.embedding_device,
            local_files_only=settings.local_files_only,
        )
        logger.info("[Runner] Embedder(small) 로드 완료")
    except Exception as exc:
        logger.warning("[Runner] Embedder 로드 실패 — 임베딩 없이 rule-only 모드로 실행: %s", exc)

    with _model_lock:
        _models_loaded = True


# ─── DB 세션 ──────────────────────────────────────────────────────────────────
def _get_session() -> Session:
    engine = create_engine(settings.database_url_sync, pool_pre_ping=True)
    return Session(engine)


def _update_job(session: Session, job_id: str, **kwargs: Any) -> None:
    from src.models import Job
    job = session.get(Job, uuid.UUID(job_id))
    if job is None:
        return
    for key, val in kwargs.items():
        setattr(job, key, val)
    session.commit()


def _save_result(session: Session, job_id: str, heuristic_report: dict,
                 final_report: dict, llm_debug: dict) -> None:
    from src.models import Result
    result = Result(
        job_id=uuid.UUID(job_id),
        heuristic_report=heuristic_report,
        final_report=final_report,
        llm_debug=llm_debug,
    )
    session.merge(result)
    session.commit()


# ─── Stage 1 ─────────────────────────────────────────────────────────────────
def _run_stage1(date: str, stt_file_path: str, output_dir: str) -> Path:
    from run_pipeline import (
        parse_stt_file, discourse_metrics, split_session,
        macro_segment, detect_topic_shifts, semantic_chunking,
        extract_features, load_terms, write_json, write_jsonl,
        build_label_profiles, safe_mkdir, Embedder, MODEL_MAP,
    )

    _ensure_models_loaded()

    base = PROJECT_ROOT
    out = Path(output_dir)
    safe_mkdir(out)

    utt = parse_stt_file(Path(stt_file_path))
    disc = discourse_metrics(utt)
    split = split_session(utt)
    terms = load_terms(base)

    write_jsonl(out / "parsed" / f"{date}.jsonl", utt)
    write_json(out / "discourse_marker" / f"{date}.json", disc)
    write_json(out / "session_split" / f"{date}.json", split)

    # singleton embedder가 없으면 스레드에서 직접 재시도
    # (lifespan에서 OPENAI_API_KEY를 주입한 이후이므로 여기서는 키가 있어야 함)
    embedder = _embedder_large
    if embedder is None:
        try:
            model_id = MODEL_MAP.get(settings.embedding_model, MODEL_MAP["multilingual-e5-large"])
            embedder = Embedder(
                model_id=model_id,
                device=settings.embedding_device,
                local_files_only=settings.local_files_only,
            )
            logger.info("[Stage1] Embedder 스레드 내 재생성 성공: %s", model_id)
        except Exception as exc:
            raise RuntimeError(
                f"[Stage1] Embedder 생성 실패. OPENAI_API_KEY 환경변수를 확인하세요: {exc}"
            ) from exc

    texts = [u["text"] for u in utt]
    # OpenAI 임베딩 모델은 e5 prefix 불필요
    embeds = embedder.encode(texts, batch_size=512)
    logger.info("[Stage1] 임베딩 완료: %d벡터", len(embeds))

    macro = macro_segment(
        utt, embeds,
        threshold=settings.macro_threshold,
        label_mode=settings.labeling_mode,
        label_profiles=build_label_profiles(embedder, settings.embedding_model)
        if settings.labeling_mode == "e5_proto" else None,
    )
    shifts = detect_topic_shifts(utt, embeds, drop_threshold=settings.shift_drop_threshold)
    chunks = semantic_chunking(macro, utt, embeds, sim_threshold=settings.chunk_sim_threshold)
    feats = extract_features(utt, disc, terms)

    write_json(out / "macro_segments" / f"{date}.json", {"date": date, "segments": macro})
    write_json(out / "topic_shift" / f"{date}.json", {"date": date, "topic_shifts": shifts})
    write_json(out / "semantic_chunks" / f"{date}.json", {"date": date, "chunks": chunks})
    write_json(out / "features" / f"{date}.json", {"date": date, "features": feats})

    logger.info("[Stage1] %s 완료: seg=%d chunk=%d", date, len(macro), len(chunks))
    return out


# ─── Stage 2 ─────────────────────────────────────────────────────────────────
def _run_stage2(date: str, stage1_out: Path) -> dict[str, Any]:
    from pipeline import run_pipeline  # analysis_llm/src/pipeline.py
    final_out_dir = PROJECT_ROOT / settings.output_dir / date

    result_paths = run_pipeline(
        date=date,
        base_path=str(stage1_out),
        output_dir=str(final_out_dir),
        debug=True,
    )

    def _read(key: str) -> dict:
        p = result_paths.get(key, "")
        if p and Path(p).exists():
            return json.loads(Path(p).read_text(encoding="utf-8"))
        return {}

    return {
        "heuristic_report": _read("heuristic_report_path"),
        "final_report": _read("final_report_path"),
        "llm_debug": _read("llm_debug_path"),
    }


# ─── 메인 실행 함수 (스레드에서 호출) ────────────────────────────────────────
def run_pipeline_thread(job_id: str, date: str, stt_file_path: str) -> None:
    """threading.Thread에서 호출되는 파이프라인 실행 함수."""
    session = _get_session()
    try:
        _update_job(session, job_id, status="running")
        logger.info("[Runner] %s 시작 (date=%s)", job_id, date)

        stage1_out = _run_stage1(
            date=date,
            stt_file_path=stt_file_path,
            output_dir=str(PROJECT_ROOT / settings.output_dir / date / "stage1"),
        )
        _update_job(session, job_id, progress={"stage": "stage1_done", "percent": 50})

        results = _run_stage2(date=date, stage1_out=stage1_out)
        _update_job(session, job_id, progress={"stage": "stage2_done", "percent": 100})

        _save_result(
            session, job_id,
            heuristic_report=results["heuristic_report"],
            final_report=results["final_report"],
            llm_debug=results["llm_debug"],
        )

        _update_job(
            session, job_id,
            status="done",
            finished_at=datetime.now(timezone.utc),
            progress={"stage": "done", "percent": 100},
        )
        logger.info("[Runner] %s 완료", job_id)

    except Exception as exc:
        logger.exception("[Runner] %s 실패: %s", job_id, exc)
        _update_job(
            session, job_id,
            status="failed",
            error_msg=str(exc),
            finished_at=datetime.now(timezone.utc),
        )
    finally:
        session.close()
