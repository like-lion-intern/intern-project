"""
분석 API 라우터.

POST /analyze       - STT 파일 업로드 → job 생성 → 백그라운드 스레드 실행
GET  /status/{id}  - job 상태 + progress 조회
GET  /result/{id}  - 최종 분석 결과 반환
GET  /health       - API/DB 상태 확인
"""
from __future__ import annotations

import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.database import get_db
from src.models import Job, Result
from src.runner import run_pipeline_thread
from src.schemas import AnalyzeResponse, HealthResponse, ResultResponse, StatusResponse

router = APIRouter()

# ─── 헬퍼 ─────────────────────────────────────────────────────────────────────
DATE_PATTERN = re.compile(r"(\d{4}-\d{2}-\d{2})")


def _extract_date(filename: str) -> str:
    m = DATE_PATTERN.search(filename)
    if not m:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"파일명에서 날짜를 찾을 수 없습니다: {filename}",
        )
    return m.group(1)


async def _save_upload(file: UploadFile, date: str) -> str:
    tmp_dir = Path(settings.project_root) / settings.upload_tmp_dir
    tmp_dir.mkdir(parents=True, exist_ok=True)
    dest = tmp_dir / f"{date}_{uuid.uuid4().hex[:8]}.txt"
    content = await file.read()
    dest.write_bytes(content)
    return str(dest)


# ─── 엔드포인트 ───────────────────────────────────────────────────────────────
@router.post("/analyze", response_model=AnalyzeResponse, status_code=status.HTTP_202_ACCEPTED)
async def analyze(
    file: UploadFile = File(..., description="화자 ID 제거된 STT .txt 파일"),
    db: AsyncSession = Depends(get_db),
) -> AnalyzeResponse:
    """STT 파일을 받아 백그라운드 스레드에서 파이프라인을 실행한다."""
    date = _extract_date(file.filename or "")
    stt_path = await _save_upload(file, date)

    try:
        job = Job(date=date, original_filename=file.filename or "", status="pending")
        db.add(job)
        await db.flush()
        job_id = str(job.job_id)
        await db.commit()
    except Exception as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"DB 연결 실패 또는 저장 오류: {exc}",
        )

    # ── fork 없이 단순 스레드로 실행 (macOS SIGSEGV 회피) ──
    t = threading.Thread(
        target=run_pipeline_thread,
        args=(job_id, date, stt_path),
        daemon=True,
        name=f"pipeline-{job_id[:8]}",
    )
    t.start()

    return AnalyzeResponse(job_id=job.job_id, date=date, status="pending")


@router.get("/status/{job_id}", response_model=StatusResponse)
async def get_status(job_id: str, db: AsyncSession = Depends(get_db)) -> StatusResponse:
    try:
        uid = uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="유효하지 않은 job_id 형식입니다.")

    try:
        job = await db.get(Job, uid)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"DB 조회 실패: {exc}",
        )
    if job is None:
        raise HTTPException(status_code=404, detail="해당 job을 찾을 수 없습니다.")

    return StatusResponse(
        job_id=job.job_id,
        date=job.date,
        status=job.status,
        progress=job.progress,
        error_msg=job.error_msg,
        created_at=job.created_at,
        finished_at=job.finished_at,
    )


@router.get("/result/{job_id}", response_model=ResultResponse)
async def get_result(job_id: str, db: AsyncSession = Depends(get_db)) -> ResultResponse:
    try:
        uid = uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="유효하지 않은 job_id 형식입니다.")

    try:
        job = await db.get(Job, uid)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"DB 조회 실패: {exc}",
        )
    if job is None:
        raise HTTPException(status_code=404, detail="해당 job을 찾을 수 없습니다.")
    if job.status != "done":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"분석이 아직 완료되지 않았습니다 (현재 상태: {job.status}).",
        )

    try:
        stmt = select(Result).where(Result.job_id == uid)
        res = await db.scalar(stmt)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"결과 조회 실패: {exc}",
        )
    if res is None:
        raise HTTPException(status_code=404, detail="결과 데이터를 찾을 수 없습니다.")

    return ResultResponse(
        job_id=job.job_id,
        date=job.date,
        final_report=res.final_report or {},
        heuristic_report=res.heuristic_report,
        llm_debug=res.llm_debug,
    )


@router.get("/health", response_model=HealthResponse)
async def health(db: AsyncSession = Depends(get_db)) -> HealthResponse:
    try:
        await db.execute(select(1))
        db_status = "ok"
    except Exception:
        db_status = "error"

    return HealthResponse(api="ok", worker="thread", db=db_status)
