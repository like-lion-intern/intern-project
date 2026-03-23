import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class AnalyzeResponse(BaseModel):
    job_id: uuid.UUID
    date: str
    status: str
    message: str = "분석 작업이 등록되었습니다."


class StatusResponse(BaseModel):
    job_id: uuid.UUID
    date: str
    status: str                         # pending | running | done | failed
    progress: dict[str, Any] | None     # run_pipeline.py progress JSON
    error_msg: str | None
    created_at: datetime
    finished_at: datetime | None


class ResultResponse(BaseModel):
    job_id: uuid.UUID
    date: str
    final_report: dict[str, Any]
    heuristic_report: dict[str, Any] | None = None
    llm_debug: dict[str, Any] | None = None


class HealthResponse(BaseModel):
    api: str = "ok"
    worker: str                         # "ok" | "no_workers"
    db: str = "ok"
