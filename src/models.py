import uuid
from datetime import datetime, timezone

from sqlalchemy import Text, String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Job(Base):
    __tablename__ = "jobs"

    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    celery_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    date: Mapped[str] = mapped_column(String(10))          # '2026-02-02'
    original_filename: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(
        String(20), default="pending"
    )                                                       # pending|running|done|failed
    progress: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error_msg: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    result: Mapped["Result | None"] = relationship(
        "Result", back_populates="job", uselist=False
    )

    def __repr__(self) -> str:
        return f"<Job job_id={self.job_id} date={self.date} status={self.status}>"


class Result(Base):
    __tablename__ = "results"

    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.job_id"), primary_key=True
    )
    heuristic_report: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    final_report: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    llm_debug: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )

    job: Mapped["Job"] = relationship("Job", back_populates="result")
