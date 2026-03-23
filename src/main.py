"""
FastAPI 애플리케이션 진입점.
"""
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.config import settings
from src.database import create_tables
from src.routers.analyze import router as analyze_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """애플리케이션 시작/종료 시 실행."""
    # 시작
    logger.info("서버 시작: DB 테이블 생성 중...")
    await create_tables()
    logger.info("DB 테이블 준비 완료.")

    # Gemini API 키 환경변수 설정
    if settings.google_api_key:
        os.environ["GOOGLE_API_KEY"] = settings.google_api_key
        os.environ["GEMINI_MODEL"] = settings.gemini_model

    yield

    # 종료
    logger.info("서버 종료.")


app = FastAPI(
    title="강의 분석 파이프라인 API",
    description=(
        "STT 파일을 업로드하면 e5 임베딩 기반 전처리 → Gemini LLM 분석 → "
        "체크리스트 18개 항목 평가 리포트를 생성합니다."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(analyze_router, prefix="/api/v1", tags=["analyze"])


@app.get("/", include_in_schema=False)
async def root():
    return {"message": "강의 분석 API 서버가 실행 중입니다. /docs 에서 API 문서를 확인하세요."}
