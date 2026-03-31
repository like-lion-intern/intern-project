from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # PostgreSQL
    database_url: str = "postgresql+asyncpg://postgres:password@localhost:5432/lecturedb"
    # Celery는 sync driver 필요
    database_url_sync: str = "postgresql+psycopg2://postgres:password@localhost:5432/lecturedb"

    # Gemini
    google_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"

    # OpenAI (rerank용 임베딩)
    # .env에서 OPENAI_API_KEY 또는 CHAT_GPT_API 둘 다 지원
    openai_api_key: str = ""   # OPENAI_API_KEY env var
    chat_gpt_api: str = ""     # CHAT_GPT_API env var (레거시 지원)

    @property
    def resolved_openai_api_key(self) -> str:
        """OPENAI_API_KEY 우선, 없으면 CHAT_GPT_API 사용."""
        return self.openai_api_key or self.chat_gpt_api

    # Embedding model
    embedding_model: str = "multilingual-e5-large"  # or "BAAI/bge-m3"
    embedding_device: str = "cpu"                   # "cpu" | "cuda" | "mps"
    local_files_only: bool = False
    offline_mode: bool = False

    # Paths
    project_root: str = "."
    stt_input_dir: str = "stt_log_removed"       # 화자 ID 제거된 STT 파일 경로
    output_dir: str = "outputs"
    upload_tmp_dir: str = "tmp_uploads"           # 업로드 임시 저장 경로

    # Pipeline hyperparams
    macro_threshold: float = 1.05
    shift_drop_threshold: float = 0.28
    chunk_sim_threshold: float = 0.74
    labeling_mode: str = "rule"                   # "rule" | "e5_proto"


settings = Settings()
