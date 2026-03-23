"""
Celery 태스크 모듈.

Worker 시작 시 e5 임베딩 모델을 메모리에 로드하고,
파이프라인 태스크에서 재사용한다.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from celery.signals import worker_init
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.celery_app import celery_app
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

# ─── Worker 전역 상태 (모델 캐시) ─────────────────────────────────────────────
_embedder_large = None   # multilingual-e5-large
_embedder_small = None   # multilingual-e5-small (rerank용)


@worker_init.connect
def load_models(**kwargs: Any) -> None:
    """Celery Worker 프로세스 시작 시 1회 임베딩 모델 로드."""
    global _embedder_large, _embedder_small

    if settings.offline_mode:
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"

    try:
        from run_pipeline import Embedder, MODEL_MAP  # scripts/run_pipeline.py
        model_id = MODEL_MAP.get(settings.embedding_model, MODEL_MAP["multilingual-e5-large"])
        _embedder_large = Embedder(
            model_id=model_id,
            device=settings.embedding_device,
            local_files_only=settings.local_files_only,
        )
        logger.info("[Worker] e5-large model loaded: %s", model_id)

        _embedder_small = Embedder(
            model_id="intfloat/multilingual-e5-small",
            device=settings.embedding_device,
            local_files_only=settings.local_files_only,
        )
        logger.info("[Worker] e5-small model loaded")
    except Exception as exc:
        logger.warning("[Worker] 임베딩 모델 로드 실패 (fallback 사용): %s", exc)


# ─── DB 동기 세션 (Celery는 sync) ─────────────────────────────────────────────
def _get_sync_session() -> Session:
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


def _save_result(
    session: Session,
    job_id: str,
    heuristic_report: dict,
    final_report: dict,
    llm_debug: dict,
) -> None:
    from src.models import Result
    result = Result(
        job_id=uuid.UUID(job_id),
        heuristic_report=heuristic_report,
        final_report=final_report,
        llm_debug=llm_debug,
    )
    session.merge(result)
    session.commit()


# ─── 파이프라인 실행 헬퍼 ──────────────────────────────────────────────────────
def _run_stage1(date: str, stt_file_path: str, output_dir: str) -> Path:
    """
    Stage 1: STT 파일 → macro_segments / semantic_chunks / features 생성.
    pre-loaded embedder를 재사용해 모델 재로딩 없이 실행.
    """
    from run_pipeline import (  # scripts/run_pipeline.py
        parse_stt_file,
        discourse_metrics,
        split_session,
        macro_segment,
        detect_topic_shifts,
        semantic_chunking,
        extract_features,
        load_terms,
        write_json,
        write_jsonl,
        build_label_profiles,
        safe_mkdir,
    )

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

    # 임베딩 (pre-loaded 모델 재사용)
    embedder = _embedder_large
    texts = [u["text"] for u in utt]
    if "e5" in settings.embedding_model:
        texts = [f"passage: {t}" for t in texts]
    embeds = embedder.encode(texts, batch_size=64) if embedder else []

    macro = macro_segment(
        utt, embeds,
        threshold=settings.macro_threshold,
        label_mode=settings.labeling_mode,
        label_profiles=build_label_profiles(embedder, settings.embedding_model) if (
            embedder and settings.labeling_mode == "e5_proto"
        ) else None,
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


def _run_stage2(date: str, stage1_out: Path) -> dict[str, Any]:
    """
    Stage 2: features.json + semantic_chunks.json → final_report.
    analysis_llm/src/pipeline.py 직접 호출.
    """
    from pipeline import run_pipeline  # analysis_llm/src/pipeline.py

    # analysis_llm이 기대하는 data/ 경로 구조 맞추기
    data_dir = stage1_out
    final_out_dir = PROJECT_ROOT / settings.output_dir / date

    result_paths = run_pipeline(
        date=date,
        base_path=str(data_dir),
        output_dir=str(final_out_dir),
        debug=True,
    )

    # JSON 파일 읽어서 반환
    def _read(path_key: str) -> dict:
        p = result_paths.get(path_key, "")
        if p and Path(p).exists():
            return json.loads(Path(p).read_text(encoding="utf-8"))
        return {}

    return {
        "heuristic_report": _read("heuristic_report_path"),
        "final_report": _read("final_report_path"),
        "llm_debug": _read("llm_debug_path"),
    }


# ─── Celery 태스크 ─────────────────────────────────────────────────────────────
@celery_app.task(bind=True, name="src.tasks.run_pipeline_task", max_retries=1)
def run_pipeline_task(self, job_id: str, date: str, stt_file_path: str) -> dict[str, Any]:
    """
    강의 분석 전체 파이프라인 Celery 태스크.

    Args:
        job_id: UUID 문자열
        date: 강의 날짜 (예: '2026-02-02')
        stt_file_path: 화자 ID 제거된 STT .txt 파일 절대 경로
    """
    session = _get_sync_session()

    try:
        # 1. 상태: running
        _update_job(session, job_id, status="running", celery_id=self.request.id)
        logger.info("[Task] %s 시작 (date=%s)", job_id, date)

        # 2. Stage 1: 전처리
        stage1_out = _run_stage1(
            date=date,
            stt_file_path=stt_file_path,
            output_dir=str(PROJECT_ROOT / settings.output_dir / date / "stage1"),
        )
        _update_job(session, job_id, progress={"stage": "stage1_done", "percent": 50})

        # 3. Stage 2: 분석 LLM
        results = _run_stage2(date=date, stage1_out=stage1_out)
        _update_job(session, job_id, progress={"stage": "stage2_done", "percent": 100})

        # 4. 결과 DB 저장
        _save_result(
            session, job_id,
            heuristic_report=results["heuristic_report"],
            final_report=results["final_report"],
            llm_debug=results["llm_debug"],
        )

        # 5. 완료
        _update_job(
            session, job_id,
            status="done",
            finished_at=datetime.now(timezone.utc),
            progress={"stage": "done", "percent": 100},
        )
        logger.info("[Task] %s 완료", job_id)
        return {"status": "done", "job_id": job_id}

    except Exception as exc:
        logger.exception("[Task] %s 실패: %s", job_id, exc)
        _update_job(
            session, job_id,
            status="failed",
            error_msg=str(exc),
            finished_at=datetime.now(timezone.utc),
        )
        raise

    finally:
        session.close()
