#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

VENV_DIR="${VENV_DIR:-.venv}"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8080}"
START_DB="${START_DB:-1}"
USE_ENV_DB="${USE_ENV_DB:-0}"
PG_CONTAINER_NAME="${PG_CONTAINER_NAME:-intern-pg}"
PG_PASSWORD="${PG_PASSWORD:-password}"
PG_DATABASE="${PG_DATABASE:-lecturedb}"
PG_PORT="${PG_PORT:-5432}"

echo "[local] project root: $ROOT_DIR"

if [ ! -d "$VENV_DIR" ]; then
  echo "[local] creating virtualenv: $VENV_DIR"
  python3 -m venv "$VENV_DIR"
fi

echo "[local] activating virtualenv"
source "$VENV_DIR/bin/activate"

echo "[local] installing requirements"
pip install -r requirements.txt

if [ ! -f ".env" ]; then
  echo "[error] .env 파일이 없습니다."
  echo "        예시:"
  echo "        DATABASE_URL=postgresql+asyncpg://postgres:${PG_PASSWORD}@localhost:${PG_PORT}/${PG_DATABASE}"
  echo "        DATABASE_URL_SYNC=postgresql+psycopg2://postgres:${PG_PASSWORD}@localhost:${PG_PORT}/${PG_DATABASE}"
  echo "        OPENAI_API_KEY=..."
  echo "        GOOGLE_API_KEY=... (optional)"
  exit 1
fi

echo "[local] loading .env"
set -a
source .env
set +a

# 로컬 테스트 기본값:
# START_DB=1 이고 USE_ENV_DB!=1 이면 로컬 PostgreSQL URL로 강제 설정한다.
if [ "$START_DB" = "1" ] && [ "$USE_ENV_DB" != "1" ]; then
  export DATABASE_URL="postgresql+asyncpg://postgres:${PG_PASSWORD}@localhost:${PG_PORT}/${PG_DATABASE}"
  export DATABASE_URL_SYNC="postgresql+psycopg2://postgres:${PG_PASSWORD}@localhost:${PG_PORT}/${PG_DATABASE}"
  echo "[local] using local DB urls:"
  echo "        DATABASE_URL=$DATABASE_URL"
  echo "        DATABASE_URL_SYNC=$DATABASE_URL_SYNC"
fi

if [ -z "${OPENAI_API_KEY:-}" ] && [ -n "${CHAT_GPT_API:-}" ]; then
  export OPENAI_API_KEY="$CHAT_GPT_API"
fi

required_vars=("DATABASE_URL" "DATABASE_URL_SYNC" "OPENAI_API_KEY")
for var_name in "${required_vars[@]}"; do
  if [ -z "${!var_name:-}" ]; then
    echo "[error] 필수 환경변수 누락: $var_name"
    exit 1
  fi
done

if [ "$START_DB" = "1" ]; then
  if command -v docker >/dev/null 2>&1; then
    if docker ps -a --format '{{.Names}}' | grep -qx "$PG_CONTAINER_NAME"; then
      if ! docker ps --format '{{.Names}}' | grep -qx "$PG_CONTAINER_NAME"; then
        echo "[local] starting existing postgres container: $PG_CONTAINER_NAME"
        docker start "$PG_CONTAINER_NAME" >/dev/null
      else
        echo "[local] postgres container already running: $PG_CONTAINER_NAME"
      fi
    else
      echo "[local] creating postgres container: $PG_CONTAINER_NAME"
      docker run --name "$PG_CONTAINER_NAME" \
        -e POSTGRES_PASSWORD="$PG_PASSWORD" \
        -e POSTGRES_DB="$PG_DATABASE" \
        -p "${PG_PORT}:5432" \
        -d postgres:16 >/dev/null
    fi
  else
    echo "[warn] docker가 없어 DB 자동 기동을 건너뜁니다. START_DB=0과 동일하게 진행합니다."
  fi
fi

echo "[local] starting FastAPI server at http://localhost:${PORT}"
echo "[local] frontend: http://localhost:${PORT}/site/index.html"
exec uvicorn src.main:app --reload --host "$HOST" --port "$PORT"
