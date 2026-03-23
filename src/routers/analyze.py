"""
분석 API 라우터.

POST /analyze       - STT 파일 업로드 → job 생성 → Celery task 등록
GET  /status/{id}  - job 상태 + progress 조회
GET  /result/{id}  - 최종 분석 결과 반환
GET  /health       - API/Worker/DB 상태 확인
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.celery_app import celery_app
from src.config import settings
from src.database import get_db
from src.models import Job, Result
from src.schemas import AnalyzeResponse, HealthResponse, ResultResponse, StatusResponse
from src.tasks import run_pipeline_task

router = APIRouter()

# ─── 헬퍼 ─────────────────────────────────────────────────────────────────────
DATE_PATTERN = re.compile(r"(\d{4}-\d{2}-\d{2})")


def _extract_date(filename: str) -> str:
    """파일명에서 날짜 추출. 예: '2026-02-02_kdt-backendj-21th.txt' → '2026-02-02'"""
    m = DATE_PATTERN.search(filename)
    if not m:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"파일명에서 날짜를 찾을 수 없습니다: {filename}",
        )
    return m.group(1)


async def _save_upload(file: UploadFile, date: str) -> str:
    """업로드 파일을 tmp_uploads/<date>.txt 에 저장 후 경로 반환."""
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
    """STT 파일을 받아 파이프라인 분석 작업을 비동기로 등록한다."""
    date = _extract_date(file.filename or "")
    stt_path = await _save_upload(file, date)

    # Job 레코드 생성
    job = Job(date=date, original_filename=file.filename or "", status="pending")
    db.add(job)
    await db.flush()  # job_id 확정

    # Celery task 등록
    task = run_pipeline_task.delay(str(job.job_id), date, stt_path)
    job.celery_id = task.id
    await db.commit()

    return AnalyzeResponse(job_id=job.job_id, date=date, status="pending")


@router.get("/status/{job_id}", response_model=StatusResponse)
async def get_status(job_id: str, db: AsyncSession = Depends(get_db)) -> StatusResponse:
    """job의 현재 상태와 진행률을 반환한다."""
    try:
        uid = uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="유효하지 않은 job_id 형식입니다.")

    job = await db.get(Job, uid)
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
    """분석이 완료된 job의 최종 리포트를 반환한다."""
    try:
        uid = uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="유효하지 않은 job_id 형식입니다.")

    job = await db.get(Job, uid)
    if job is None:
        raise HTTPException(status_code=404, detail="해당 job을 찾을 수 없습니다.")
    if job.status != "done":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"분석이 아직 완료되지 않았습니다 (현재 상태: {job.status}).",
        )

    stmt = select(Result).where(Result.job_id == uid)
    res = await db.scalar(stmt)
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
    """API 서버, Celery Worker, DB 상태를 확인한다."""
    # DB 연결 확인
    try:
        await db.execute(select(1))
        db_status = "ok"
    except Exception:
        db_status = "error"

    # Celery Worker 확인 (ping)
    try:
        inspect = celery_app.control.inspect(timeout=1.0)
        active = inspect.active()
        worker_status = "ok" if active else "no_workers"
    except Exception:
        worker_status = "no_workers"

    return HealthResponse(api="ok", worker=worker_status, db=db_status)
