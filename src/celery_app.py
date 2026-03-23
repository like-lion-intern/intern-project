from celery import Celery

from src.config import settings

# PostgreSQL을 Celery 브로커 + 결과 백엔드로 사용
# sqla+: SQLAlchemy transport (폴링 방식)
# db+:   SQLAlchemy result backend
celery_app = Celery(
    "lecture_pipeline",
    broker=f"sqla+{settings.database_url_sync}",
    backend=f"db+{settings.database_url_sync}",
    include=["src.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    task_acks_late=True,          # Worker 죽어도 작업 재시도
    worker_prefetch_multiplier=1, # 한 번에 1개씩만 처리 (무거운 파이프라인)
    result_expires=60 * 60 * 24, # 결과 24시간 보관
)
