# 베이스 이미지 (안정성이 검증된 3.11-slim 시리즈 사용)
FROM python:3.11-slim

# 작업 디렉토리 설정
WORKDIR /app

# 시스템 의존성 설치 (필요시)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 파이썬 환경 설정
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/app/.cache/huggingface

# 의존성 파일 복사 및 설치
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# [성능 최적화] Cloud Run Cold Start 방지를 위해 e5-small 모델 빌드 타임에 캐싱 다운로드
# (소스 코드 변경 시에도 모델 레이어 캐시를 살리기 위해 소스 복사 이전에 위치)
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('intfloat/multilingual-e5-small', device='cpu')"

# 소스코드 전체 복사 (가장 많이 바뀌므로 맨 아래에 위치)
COPY . .

# 포트 개방
EXPOSE 8080

# Uvicorn 서버 실행 (Cloud Run은 기본적으로 8080 포트를 요구합니다)
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8080"]
