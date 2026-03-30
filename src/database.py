from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from src.config import settings


class Base(DeclarativeBase):
    pass


# --- Lazy initialization ---
# 모듈 import 시점에 엔진을 생성하지 않습니다.
# 컨테이너 시작 직후 DB 연결 실패로 uvicorn이 포트를 열기 전에 크래시하는 문제 방지.
_async_engine = None
_AsyncSessionLocal = None


def get_engine():
    """엔진을 처음 호출 시점에 생성합니다 (lazy)."""
    global _async_engine
    if _async_engine is None:
        _async_engine = create_async_engine(
            settings.database_url,
            pool_pre_ping=True,
            echo=False,
            connect_args={"server_settings": {"jit": "off"}, "statement_cache_size": 0},
        )
    return _async_engine


def get_session_factory():
    """세션 팩토리를 처음 호출 시점에 생성합니다 (lazy)."""
    global _AsyncSessionLocal
    if _AsyncSessionLocal is None:
        _AsyncSessionLocal = async_sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _AsyncSessionLocal


async def get_db():
    """FastAPI 의존성 주입용 세션 팩토리."""
    async with get_session_factory()() as session:
        try:
            yield session
        finally:
            await session.close()


async def create_tables():
    """앱 시작 시 테이블 자동 생성."""
    # models 등록을 위해 import 필요
    import src.models  # noqa: F401
    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
