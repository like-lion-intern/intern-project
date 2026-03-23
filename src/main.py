"""
FastAPI 애플리케이션 진입점.
"""
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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
    logger.info("서버 시작: DB 테이블 생성 중...")
    await create_tables()
    logger.info("DB 테이블 준비 완료.")

    if settings.google_api_key:
        os.environ["GOOGLE_API_KEY"] = settings.google_api_key
        os.environ["GEMINI_MODEL"] = settings.gemini_model

    yield
    logger.info("서버 종료.")


app = FastAPI(
    title="강의 분석 파이프라인 API",
    description=(
        "STT 파일을 업로드하면 e5 임베딩 기반 전처리 → Gemini LLM 분석 → "
        "체크리스트 18개 항목 평가 리포트를 생성합니다."
    ),
    version="2.0.0",
    lifespan=lifespan,
)

# 브라우저에서 file:// 로 열 때 CORS 에러 방지
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(analyze_router, prefix="/api/v1", tags=["analyze"])


@app.get("/", include_in_schema=False)
async def root():
    return {"message": "강의 분석 API 서버가 실행 중입니다. /docs 에서 API 문서를 확인하세요."}
