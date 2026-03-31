"""
분석 API 라우터.

POST /analyze       - STT 파일 업로드 → job 생성 → 백그라운드 스레드 실행
GET  /status/{id}  - job 상태 + progress 조회
GET  /result/{id}  - 최종 분석 결과 반환
GET  /health       - API/DB 상태 확인
"""
from __future__ import annotations

import json
import re
import sys
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
RESULT_FILE_PATTERN = re.compile(r"^(\d{4}-\d{2}-\d{2})_result\.json$")


def _load_build_trajectory_report():
    """
    analysis_llm/src/trajectory.py의 build_trajectory_report를 동적으로 로드한다.
    """
    trajectory_src = Path(settings.project_root) / "analysis_llm" / "src"
    if str(trajectory_src) not in sys.path:
        sys.path.insert(0, str(trajectory_src))
    from trajectory import build_trajectory_report  # type: ignore
    return build_trajectory_report


def _collect_result_dates(output_root: Path) -> list[str]:
    """trajectory 생성에 사용 가능한 결과(result) 날짜를 수집한다."""
    dates: set[str] = set()
    if not output_root.exists():
        return []
    for p in output_root.rglob("*_result.json"):
        m = RESULT_FILE_PATTERN.match(p.name)
        if m:
            dates.add(m.group(1))
    return sorted(dates)


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


@router.post("/trajectory/rebuild")
async def rebuild_trajectory() -> dict:
    """
    outputs 전체 날짜 결과를 집계해 trajectory 리포트를 다시 생성한다.
    """
    try:
        build_trajectory_report = _load_build_trajectory_report()

        output_root = str(Path(settings.project_root) / settings.output_dir)
        project_root = str(Path(settings.project_root))
        out_path = build_trajectory_report(output_root=output_root, project_root=project_root)
        if not out_path:
            raise HTTPException(status_code=404, detail="trajectory 생성 대상 결과 파일이 없습니다.")
        payload = json.loads(Path(out_path).read_text(encoding="utf-8"))
        return {"path": out_path, "trajectory": payload}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"trajectory 생성 실패: {exc}")


@router.get("/trajectory/latest")
async def get_latest_trajectory() -> dict:
    """
    가장 최근 trajectory 리포트를 반환한다.
    """
    trajectory_dir = Path(settings.project_root) / settings.output_dir / "trajectory"
    if not trajectory_dir.exists():
        raise HTTPException(status_code=404, detail="trajectory 디렉토리가 없습니다.")

    files = sorted(trajectory_dir.glob("*_trajectory.json"))
    if not files:
        raise HTTPException(status_code=404, detail="trajectory 파일이 없습니다.")

    latest = files[-1]
    try:
        payload = json.loads(latest.read_text(encoding="utf-8"))
        return {"path": str(latest), "trajectory": payload}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"trajectory 파일 파싱 실패: {exc}")


@router.get("/trajectory/summary")
async def get_trajectory_summary() -> dict:
    """
    궤적 분석 UX용 요약 정보:
    - 현재 궤적 분석 가능한 강의(result) 개수
    - 날짜 범위
    - 최신 trajectory 파일 존재 여부
    """
    output_root = Path(settings.project_root) / settings.output_dir
    dates = _collect_result_dates(output_root)

    trajectory_dir = output_root / "trajectory"
    latest_path = ""
    latest_exists = False
    trajectory_file_count = 0
    if trajectory_dir.exists():
        files = sorted(trajectory_dir.glob("*_trajectory.json"))
        trajectory_file_count = len(files)
        if files:
            latest_path = str(files[-1])
            latest_exists = True

    return {
        "available_lecture_count": len(dates),
        "date_range": {
            "start_date": dates[0] if dates else None,
            "end_date": dates[-1] if dates else None,
        },
        "latest_trajectory_exists": latest_exists,
        "latest_trajectory_path": latest_path,
        "trajectory_file_count": trajectory_file_count,
    }
